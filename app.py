# app.py (notes service - versão corrigida com CORS completo)
import os
from dotenv import load_dotenv
from flask import Flask, request, jsonify, make_response
from flask_pymongo import PyMongo
from bson.objectid import ObjectId
from bson.errors import InvalidId
from pymongo import ReturnDocument
from flask_cors import CORS

from auth import requires_auth, register_auth_error_handlers

# ---------------------------------------------------------------------
# Configuração inicial
# ---------------------------------------------------------------------
load_dotenv()
app = Flask(__name__)

# ---------------------------------------------------------------------
# Configuração do MongoDB
# ---------------------------------------------------------------------
app.config["MONGO_URI"] = os.getenv("MONGO_URI", "mongodb://localhost:27017/notesdb")
mongo = PyMongo(app)

# ---------------------------------------------------------------------
# Configuração de origens CORS (padrão: http://localhost:5173)
# - CORS_ORIGINS pode ser "*" ou uma lista separada por vírgula.
# ---------------------------------------------------------------------
_raw_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173").strip()
if _raw_origins == "*" or _raw_origins.lower() == "any":
    cors_origins = "*"   # allow any origin (não combine com credentials=True)
else:
    # converte em lista e remove espaços
    cors_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()]

# Use flask-cors para respostas "normais"
CORS(
    app,
    resources={r"/*": {"origins": cors_origins}},
    supports_credentials=True,
    methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "Accept"],
)

# ---------------------------------------------------------------------
# Registro de handlers de erro do Auth0
# ---------------------------------------------------------------------
register_auth_error_handlers(app)

# ---------------------------------------------------------------------
# Responde preflight OPTIONS antes de qualquer autenticação (protege contra
# decorators que exigem auth que poderiam bloquear o preflight)
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
        # cors_origins é lista de origens
        if origin and origin in cors_origins:
            allowed_origin = origin

    resp = make_response("", 204)
    if allowed_origin:
        resp.headers["Access-Control-Allow-Origin"] = allowed_origin
        resp.headers["Vary"] = "Origin"
        resp.headers["Access-Control-Allow-Methods"] = "GET,POST,PUT,DELETE,OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Authorization,Content-Type,Accept"
        # Only include credentials header if you actually support credentials
        resp.headers["Access-Control-Allow-Credentials"] = "true"
        resp.headers["Access-Control-Max-Age"] = "3600"
    return resp

# ---------------------------------------------------------------------
# Rotas da API
# ---------------------------------------------------------------------
@app.route("/notes", methods=["GET"])
@requires_auth()
def get_notes():
    notes = mongo.db.notes.find()
    output = [
        {"id": str(note["_id"]), "title": note.get("title"), "content": note.get("content")}
        for note in notes
    ]
    return jsonify(output), 200


@app.route("/notes", methods=["POST"])
@requires_auth(required_scope="create:notes")
def create_note():
    data = request.json
    if not data or "title" not in data or "content" not in data:
        return jsonify({"error": "Missing title or content"}), 400

    note = {"title": data["title"], "content": data["content"]}
    note_id = mongo.db.notes.insert_one(note).inserted_id
    return jsonify({"id": str(note_id), **note}), 201


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
        {"$set": {"title": data.get("title"), "content": data.get("content")}},
        return_document=ReturnDocument.AFTER,
    )
    if not updated:
        return jsonify({"error": "Note not found"}), 404

    return jsonify({"id": str(updated["_id"]), "title": updated["title"], "content": updated["content"]}), 200


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
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5002)), debug=True)
