# Proyecto PÚRPURA — MVP Sprint 1

Sistema de Gestión de Monitorías Académicas — Universidad de Medellín.

## Stack
FastAPI · SQLModel · PostgreSQL 16 · Jinja2 · Bootstrap 5.3 · Alpine.js

## Cómo correr en local

1. Copiar `.env.example` a `.env` y generar SESSION_SECRET_KEY:
   `uv run python -c "import secrets; print(secrets.token_urlsafe(48))"`
2. Levantar Postgres: `docker compose up -d db`
3. Instalar dependencias: `uv sync`
4. Seed inicial: `uv run seed`
5. Servidor: `uv run uvicorn app.main:app --reload`
6. Abrir http://localhost:8000

## Credenciales de prueba (SOLO dev)
- admin@purpura.local / Admin2026!
- coord.ing@udem.edu.co / Coord2026!
- docente1@udem.edu.co / Docente2026!
- estudiante1@udem.edu.co / Estudiante2026!

## Endpoints
Swagger en http://localhost:8000/docs

## Equipo
Felipe Cano · José Carlos Jiménez · Santiago Torres · Sebastián Rendón
