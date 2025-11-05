# app.py (notes service - versão ajustada)
import os
from dotenv import load_dotenv
from flask import Flask, request, jsonify, make_response
from flask_pymongo import PyMongo
from bson.objectid import ObjectId
from bson.errors import InvalidId
from pymongo import ReturnDocument
from flask_cors import CORS
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import time
import logging

from auth import requires_auth, register_auth_error_handlers

# ---------------------------------------------------------------------
# Configuração inicial
# ---------------------------------------------------------------------
load_dotenv()
app = Flask(__name__)

# logging
logging.basicConfig(level=logging.DEBUG)
app.logger.setLevel(logging.DEBUG)

# ---------------------------------------------------------------------
# Configuração do MongoDB
# ---------------------------------------------------------------------
app.config["MONGO_URI"] = os.getenv("MONGO_URI", "mongodb://localhost:27017/notesdb")
mongo = PyMongo(app)

# URL do tasks-service (respeita env TASKS_SERVICE_URL)
TASKS_SERVICE_URL = os.getenv("TASKS_SERVICE_URL", os.getenv("TASKS_URL", "http://localhost:8080")).rstrip("/")

# ---------------------------------------------------------------------
# Configuração de origens CORS (lê FRONTEND_ORIGINS ou CORS_ORIGINS)
# ---------------------------------------------------------------------
_raw_origins = os.getenv("FRONTEND_ORIGINS") or os.getenv("CORS_ORIGINS") or "http://localhost:5173"
_raw_origins = _raw_origins.strip()
if _raw_origins == "*" or _raw_origins.lower() == "any":
    cors_origins = "*"
else:
    cors_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()]

CORS(
    app,
    resources={r"/*": {"origins": cors_origins}},
    supports_credentials=True,
    methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "Accept", "Idempotency-Key"],
)

# ---------------------------------------------------------------------
# Registro de handlers de erro do Auth0 (assume auth.py presente)
# ---------------------------------------------------------------------
register_auth_error_handlers(app)

# ---------------------------------------------------------------------
# Preflight OPTIONS rápido (responde antes de decorators)
# ---------------------------------------------------------------------
@app.before_request
def handle_preflight():
    if request.method != "OPTIONS":
        return None

    origin = request.headers.get("Origin")
    allowed_origin = None

    if cors_origins == "*":
        allowed_origin = "*" if origin else "*"
    else:
        if origin and origin in cors_origins:
            allowed_origin = origin

    resp = make_response("", 204)
    if allowed_origin:
        resp.headers["Access-Control-Allow-Origin"] = allowed_origin
        resp.headers["Vary"] = "Origin"
        resp.headers["Access-Control-Allow-Methods"] = "GET,POST,PUT,DELETE,OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Authorization,Content-Type,Accept,Idempotency-Key"
        resp.headers["Access-Control-Allow-Credentials"] = "true"
        resp.headers["Access-Control-Max-Age"] = "3600"
    return resp

# ---------------------------------------------------------------------
# HTTP session com retry para calls ao tasks-service
# ---------------------------------------------------------------------
def make_http_session():
    session = requests.Session()
    retries = Retry(total=2, backoff_factor=0.2, status_forcelist=[500,502,503,504], raise_on_status=False)
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session

_http_session = make_http_session()

# ---------------------------------------------------------------------
# Health / Ready
# ---------------------------------------------------------------------
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "notes"}), 200

@app.route("/ready", methods=["GET"])
def ready():
    try:
        mongo.db.command("ping")
        return jsonify({"ready": True}), 200
    except Exception:
        return jsonify({"ready": False}), 503

# ---------------------------------------------------------------------
# Logging: não logar Authorization
# ---------------------------------------------------------------------
@app.before_request
def log_request_info():
    if request.method == "OPTIONS":
        return
    hdrs = {k: v for k, v in request.headers.items() if k in ("Host", "Origin", "Content-Type")}
    body_preview = request.get_data(as_text=True)[:500] if request.data else ""
    app.logger.debug("Incoming request: %s %s headers=%s body_preview=%s", request.method, request.path, hdrs, body_preview)

# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
def validate_task_id_hybrid(task_id):
    # 1) tenta ObjectId local
    try:
        _id = ObjectId(task_id)
    except Exception:
        return False, "invalid_id", None

    snap = mongo.db.task_snapshots.find_one({"_id": _id})
    if snap:
        return True, "ok", snap

    # 2) fallback sync para tasks-service
    try:
        url = f"{TASKS_SERVICE_URL}/tarefas/{task_id}"
        r = _http_session.get(url, timeout=1.0)
        if r.status_code == 200:
            task = r.json()
            # persist snapshot local (não falha a criação da nota)
            try:
                doc = {
                    "_id": ObjectId(task_id),
                    "titulo": task.get("titulo") or task.get("title"),
                    "descricao": task.get("descricao") or task.get("description"),
                    "owner": task.get("owner") if isinstance(task, dict) else None,
                    "status": task.get("status", "open"),
                    "criado_em": task.get("criado_em", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
                    "atualizado_em": task.get("atualizado_em", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
                }
                mongo.db.task_snapshots.replace_one({"_id": ObjectId(task_id)}, doc, upsert=True)
            except Exception as e:
                app.logger.warning("Falha ao persistir snapshot vindo do tasks-service: %s", e)
            return True, "ok", task
        elif r.status_code == 404:
            return False, "not_found", None
        else:
            return None, "unavailable", None
    except requests.RequestException as e:
        app.logger.warning("Fallback sync para tasks-service falhou: %s", e)
        return None, "unavailable", None

# Idempotency helpers
def get_idempotency_record(collection_name, idempotency_key):
    if not idempotency_key:
        return None
    return mongo.db.idempotency.find_one({"collection": collection_name, "idempotency_key": idempotency_key})

def save_idempotency_record(collection_name, idempotency_key, resource):
    if not idempotency_key:
        return
    mongo.db.idempotency.replace_one(
        {"collection": collection_name, "idempotency_key": idempotency_key},
        {"collection": collection_name, "idempotency_key": idempotency_key, "resource": resource},
        upsert=True
    )

# ---------------------------------------------------------------------
# Rotas da API
# ---------------------------------------------------------------------
@app.route("/notes", methods=["GET"])
@requires_auth()
def get_notes():
    notes = mongo.db.notes.find()
    output = []
    for note in notes:
        tid = note.get("task_id")
        if isinstance(tid, ObjectId):
            tid = str(tid)
        output.append({
            "id": str(note["_id"]),
            "title": note.get("title") or note.get("titulo"),
            "content": note.get("content") or note.get("conteudo"),
            "task_id": tid
        })
    return jsonify(output), 200

@app.route("/tarefas/<task_id>/notes", methods=["GET"])
@requires_auth()  # manter mesma política de autenticação do GET /notes
def get_notes_for_task(task_id):
    """
    Lista as notas vinculadas a uma task (task_id).
    Usa validate_task_id_hybrid para garantir que a task existe (ou retornar erro apropriado).
    """
    # 1) validação da task (reaproveita helper já implementado)
    valid, reason, snapshot = validate_task_id_hybrid(task_id)
    if valid is True:
        # 2) buscar notas locais vinculadas à task
        try:
            from bson.objectid import ObjectId
            _oid = ObjectId(task_id)
        except Exception:
            return jsonify({"error": "Invalid task_id"}), 400

        notes_cursor = mongo.db.notes.find({"task_id": _oid})
        notes = []
        for n in notes_cursor:
            notes.append({
                "id": str(n["_id"]),
                "title": n.get("title"),
                "content": n.get("content"),
                "task_id": str(n.get("task_id")) if n.get("task_id") else None,
                "autor": n.get("autor"),
                "criado_em": n.get("criado_em")
            })
        return jsonify(notes), 200

    elif valid is False:
        # task inválida ou não encontrada
        if reason == "invalid_id":
            return jsonify({"error": "Invalid task_id"}), 400
        return jsonify({"error": "Task not found"}), 404
    else:
        # unavailable
        return jsonify({"error": "Não foi possível validar a task no momento. Tente novamente mais tarde."}), 503


@app.route("/notes", methods=["POST"])
@requires_auth(required_scope="create:notes")
def create_note():
    data = request.json or {}
    # aceita pt/br e en
    title = data.get("title") or data.get("titulo")
    content = data.get("content") or data.get("conteudo")
    task_id = data.get("task_id") or data.get("taskId")

    if not title or not content or not task_id:
        return jsonify({"error": "Missing title/content/task_id"}), 400

    # idempotency header
    idempotency_key = request.headers.get("Idempotency-Key")
    existing = get_idempotency_record("notes", idempotency_key)
    if existing:
        return jsonify(existing["resource"]), 200

    valid, reason, snapshot = validate_task_id_hybrid(task_id)
    if valid is True:
        try:
            db_task_id = ObjectId(task_id)
        except Exception:
            # se por algum motivo ObjectId falhar (já validamos antes), guardamos como string
            db_task_id = task_id

        note_doc = {
            "title": title,
            "content": content,
            "task_id": db_task_id,
            "autor": getattr(request, "current_user", {}).get("sub") if hasattr(request, "current_user") else None,
            "criado_em": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        }
        note_id = mongo.db.notes.insert_one(note_doc).inserted_id
        resource = {"id": str(note_id), "title": title, "content": content, "task_id": str(db_task_id)}
        save_idempotency_record("notes", idempotency_key, resource)
        return jsonify(resource), 201
    elif valid is False:
        if reason == "invalid_id":
            return jsonify({"error": "Invalid task_id"}), 400
        return jsonify({"error": "Task not found"}), 400
    else:
        return jsonify({"error": "Task service unavailable. Tente novamente mais tarde."}), 503

@app.route("/notes/<id>", methods=["PUT"])
@requires_auth(required_scope="update:notes")
def update_note(id):
    try:
        _id = ObjectId(id)
    except InvalidId:
        return jsonify({"error": "Invalid id"}), 400

    data = request.json or {}
    updated = mongo.db.notes.find_one_and_update(
        {"_id": _id},
        {"$set": {"title": data.get("title") or data.get("titulo"), "content": data.get("content") or data.get("conteudo")}},
        return_document=ReturnDocument.AFTER,
    )
    if not updated:
        return jsonify({"error": "Note not found"}), 404

    return jsonify({"id": str(updated["_id"]), "title": updated.get("title"), "content": updated.get("content")}), 200

@app.route("/notes/<id>", methods=["DELETE"])
@requires_auth(required_scope="delete:notes")
def delete_note(id):
    try:
        _id = ObjectId(id)
    except InvalidId:
        return jsonify({"error": "Invalid id"}), 400

    result = mongo.db.notes.delete_one({"_id": _id})
    if result.deleted_count == 0:
        return jsonify({"error": "Note not found"}), 404
    return jsonify({"message": "Note deleted"}), 200

# ---------------------------------------------------------------------
# Inicialização
# ---------------------------------------------------------------------
if __name__ == "__main__":
    try:
        mongo.db.notes.create_index([("task_id", 1)])
        mongo.db.task_snapshots.create_index([("_id", 1)])
        mongo.db.idempotency.create_index([("collection", 1), ("idempotency_key", 1)], unique=True, sparse=True)
    except Exception as e:
        app.logger.warning("Falha ao criar índices iniciais: %s", e)

    port = int(os.getenv("PORT", 5002))
    debug = os.getenv("FLASK_DEBUG", "false").lower() in ("1", "true", "yes")
    app.run(host="0.0.0.0", port=port, debug=debug)