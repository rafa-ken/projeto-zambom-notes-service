# 📒 Notes Service

Serviço responsável pelo **CRUD de anotações**.

## 🚀 Funcionalidades
- Criar anotação (`POST /notes`)
- Listar anotações (`GET /notes`)
- Atualizar anotação (`PUT /notes/<id>`)
- Deletar anotação (`DELETE /notes/<id>`)

## 🏗 Arquitetura
- Python 3.10
- Flask + MongoDB (Flask-PyMongo)
- Testes com Pytest
- Autenticação OAuth2 via Auth0 (simulada nesta fase)
- Docker + GitHub Actions

## Como rodar localmente
```bash
pip install -r requirements.txt
python app.py
```

## Como rodar com Docker
```bash
docker build -t your-dockerhub-username/notes-service .
docker run -p 5002:5000 your-dockerhub-username/notes-service
```

## Testes
```bash
pytest -v
```

