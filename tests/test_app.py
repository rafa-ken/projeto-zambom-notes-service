import pytest
import mongomock
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


# ----------------- TESTES DE ERRO ----------------- #
def test_create_note_missing_fields(client):
    res = client.post(
        "/notes",
        json={"title": "Só título"},
        headers={"Authorization": "fake-token"}
    )
    assert res.status_code == 400
    assert "error" in res.json

def test_update_note_not_found(client):
    res = client.put(
        "/notes/000000000000000000000000",  # ObjectId inválido
        json={"title": "Não existe"},
        headers={"Authorization": "fake-token"}
    )
    assert res.status_code in (400, 404)

def test_delete_note_not_found(client):
    res = client.delete(
        "/notes/000000000000000000000000",
        headers={"Authorization": "fake-token"}
    )
    assert res.status_code in (400, 404)

def test_get_notes_without_token(client):
    res = client.get("/notes")
    assert res.status_code == 401
    assert res.json["error"] == "Token missing"

def test_create_note_without_token(client):
    res = client.post("/notes", json={"title": "Sem token", "content": "Erro"})
    assert res.status_code == 401
