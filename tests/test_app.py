import pytest
import mongomock
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import app, mongo

@pytest.fixture
def client():
    app.config["TESTING"] = True

    # Mocka o MongoDB com mongomock
    mongo.cx = mongomock.MongoClient()
    mongo.db = mongo.cx["notes_testdb"]

    client = app.test_client()
    yield client
    mongo.db.notes.delete_many({})  # limpa após cada teste


# ----------------- TESTES FELIZES ----------------- #
def test_create_note(client):
    res = client.post(
        "/notes",
        json={"title": "Minha Nota", "content": "Conteúdo da nota"}
    )
    assert res.status_code == 201
    assert res.json["title"] == "Minha Nota"

def test_get_notes(client):
    client.post(
        "/notes",
        json={"title": "Outra Nota", "content": "Mais conteúdo"}
    )
    res = client.get("/notes")
    assert res.status_code == 200
    assert len(res.json) > 0

def test_update_note(client):
    res = client.post(
        "/notes",
        json={"title": "Antiga Nota", "content": "Velho conteúdo"}
    )
    note_id = res.json["id"]
    update_res = client.put(
        f"/notes/{note_id}",
        json={"title": "Nota Atualizada"}
    )
    assert update_res.status_code == 200
    assert update_res.json["title"] == "Nota Atualizada"

def test_delete_note(client):
    res = client.post(
        "/notes",
        json={"title": "Nota Apagar", "content": "Deletar depois"}
    )
    note_id = res.json["id"]
    delete_res = client.delete(f"/notes/{note_id}")
    assert delete_res.status_code == 200
    assert delete_res.json["message"] == "Note deleted"


# ----------------- TESTES DE ERRO ----------------- #
def test_create_note_missing_fields(client):
    res = client.post("/notes", json={"title": "Só título"})
    assert res.status_code == 400
    assert "error" in res.json

def test_update_note_not_found(client):
    res = client.put(
        "/notes/000000000000000000000000",  # ObjectId inválido
        json={"title": "Não existe"}
    )
    assert res.status_code in (400, 404)

def test_delete_note_not_found(client):
    res = client.delete("/notes/000000000000000000000000")
    assert res.status_code in (400, 404)
