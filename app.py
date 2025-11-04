# app.py (notes service - versão corrigida com CORS completo)
import os
from dotenv import load_dotenv
from flask import Flask, request, jsonify, g, make_response
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
# Configuração do CORS
# ---------------------------------------------------------------------
cors_origins = os.getenv("FRONTEND_ORIGINS", "*")
if cors_origins != "*":
    cors_origins = [origin.strip() for origin in cors_origins.split(",")]

CORS(
    app,
    resources={r"/*": {
        "origins": cors_origins,
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"],
        "expose_headers": ["Content-Type"],
        "supports_credentials": True,
        "max_age": 3600
    }}
)

# ---------------------------------------------------------------------
# Responde preflight OPTIONS antes de qualquer autenticação
# ---------------------------------------------------------------------
@app.before_request
def handle_preflight():
    if request.method == "OPTIONS":
        origin = request.headers.get("Origin")
        allowed_origin = None
        if cors_origins == "*" or origin in cors_origins:
            allowed_origin = origin if origin else "*"

        resp = make_response("", 204)
        if allowed_origin:
            resp.headers["Access-Control-Allow-Origin"] = allowed_origin
            resp.headers["Vary"] = "Origin"
            resp.headers["Access-Control-Allow-Methods"] = "GET,POST,PUT,DELETE,OPTIONS"
            resp.headers["Access-Control-Allow-Headers"] = "Authorization,Content-Type,Accept"
            resp.headers["Access-Control-Allow-Credentials"] = "true"
            resp.headers["Access-Control-Max-Age"] = "3600"
        return resp

# ---------------------------------------------------------------------
# Configuração MongoDB
# ---------------------------------------------------------------------
app.config["MONGO_URI"] = os.getenv("MONGO_URI", "mongodb://localhost:27017/notesdb")
mongo = PyMongo(app)

# ---------------------------------------------------------------------
# Registro de handlers de erro do Auth0
# ---------------------------------------------------------------------
register_auth_error_handlers(app)

# ---------------------------------------------------------------------
# Garante headers CORS em todas as respostas
# ---------------------------------------------------------------------
@app.after_request
def after_request(response):
    origin = request.headers.get("Origin")
    if origin:
        if cors_origins == "*" or origin in cors_origins:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Vary"] = "Origin"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization,Accept"
            response.headers["Access-Control-Allow-Methods"] = "GET,POST,PUT,DELETE,OPTIONS"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Max-Age"] = "3600"
    return response

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