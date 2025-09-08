from flask import Flask, request, jsonify
from flask_pymongo import PyMongo
from bson.objectid import ObjectId
from functools import wraps

app = Flask(__name__)

# Configuração MongoDB (ajuste a URI para o seu cluster Atlas)
app.config["MONGO_URI"] = "mongodb://localhost:27017/notesdb"
mongo = PyMongo(app)

# Middleware simples para simular Auth0
def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get("Authorization", None)
        if not token:
            return jsonify({"error": "Token missing"}), 401
        # Aqui poderia validar com Auth0 de verdade
        return f(*args, **kwargs)
    return decorated

@app.route("/notes", methods=["GET"])
@requires_auth
def get_notes():
    notes = mongo.db.notes.find()
    output = []
    for note in notes:
        output.append({
            "id": str(note["_id"]),
            "title": note["title"],
            "content": note["content"]
        })
    return jsonify(output)

@app.route("/notes", methods=["POST"])
@requires_auth
def create_note():
    data = request.json
    if not data or "title" not in data or "content" not in data:
        return jsonify({"error": "Missing title or content"}), 400

    note_id = mongo.db.notes.insert_one({
        "title": data["title"],
        "content": data["content"]
    }).inserted_id

    return jsonify({
        "id": str(note_id),
        "title": data["title"],
        "content": data["content"]
    }), 201

@app.route("/notes/<id>", methods=["PUT"])
@requires_auth
def update_note(id):
    data = request.json
    updated = mongo.db.notes.find_one_and_update(
        {"_id": ObjectId(id)},
        {"$set": {"title": data.get("title"), "content": data.get("content")}},
        return_document=True
    )
    if not updated:
        return jsonify({"error": "Note not found"}), 404
    return jsonify({
        "id": str(updated["_id"]),
        "title": updated["title"],
        "content": updated["content"]
    })

@app.route("/notes/<id>", methods=["DELETE"])
@requires_auth
def delete_note(id):
    result = mongo.db.notes.delete_one({"_id": ObjectId(id)})
    if result.deleted_count == 0:
        return jsonify({"error": "Note not found"}), 404
    return jsonify({"message": "Note deleted"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
