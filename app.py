from flask import Flask, request, jsonify
from flask_pymongo import PyMongo
from bson.objectid import ObjectId
from pymongo import ReturnDocument
import os
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

app = Flask(__name__)

app.config["MONGO_URI"] = os.getenv("MONGO_URI")
mongo = PyMongo(app)

@app.route("/notes", methods=["GET"])
def get_notes():
    notes = mongo.db.notes.find()
    output = []
    for note in notes:
        output.append({
            "id": str(note["_id"]),
            "title": note["title"],
            "content": note["content"]
        })
    return jsonify(output), 200

@app.route("/notes", methods=["POST"])
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
def update_note(id):
    data = request.json
    updated = mongo.db.notes.find_one_and_update(
        {"_id": ObjectId(id)},
        {"$set": {"title": data.get("title"), "content": data.get("content")}},
        return_document=ReturnDocument.AFTER
    )
    if not updated:
        return jsonify({"error": "Note not found"}), 404
    return jsonify({
        "id": str(updated["_id"]),
        "title": updated["title"],
        "content": updated["content"]
    }), 200

@app.route("/notes/<id>", methods=["DELETE"])
def delete_note(id):
    result = mongo.db.notes.delete_one({"_id": ObjectId(id)})
    if result.deleted_count == 0:
        return jsonify({"error": "Note not found"}), 404
    return jsonify({"message": "Note deleted"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5002, debug=True)
