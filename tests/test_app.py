import pytest
from app import app, mongo
from bson.objectid import ObjectId

@pytest.fixture
def client():
    app.config["TESTING"] = True
    app.config["MONGO_URI"] = "mongodb://localhost:27017/notes_testdb"
    with app.app_context():
        mongo.db.notes.delete_many({})  # limpa antes dos testes
    client = app.test_client()
    yield client
    with app.app_context():
        mongo.db.notes.delete_many({})  # limpa depois dos testes

def test_create_note(client):
    res = client.post(
        "/notes",
        json={"title": "Minha Nota", "content": "Conteúdo da nota"},
        headers={"Authorization": "fake-token"}
    )
    assert res.status_code == 201
    assert res.json["title"] == "Minha Nota"

def test_get_notes(client):
    client.post(
        "/notes",
        json={"title": "Outra Nota", "content": "Mais conteúdo"},
        headers={"Authorization": "fake-token"}
    )
    res = client.get("/notes", headers={"Authorization": "fake-token"})
    assert res.status_code == 200
    assert len(res.json) > 0

def test_update_note(client):
    res = client.post(
        "/notes",
        json={"title": "Antiga Nota", "content": "Velho conteúdo"},
        headers={"Authorization": "fake-token"}
    )
    note_id = res.json["id"]
    update_res = client.put(
        f"/notes/{note_id}",
        json={"title": "Nota Atualizada"},
        headers={"Authorization": "fake-token"}
    )
    assert update_res.status_code == 200
    assert update_res.json["title"] == "Nota Atualizada"

def test_delete_note(client):
    res = client.post(
        "/notes",
        json={"title": "Nota Apagar", "content": "Deletar depois"},
        headers={"Authorization": "fake-token"}
    )
    note_id = res.json["id"]
    delete_res = client.delete(f"/notes/{note_id}", headers={"Authorization": "fake-token"})
    assert delete_res.status_code == 200
    assert delete_res.json["message"] == "Note deleted"
