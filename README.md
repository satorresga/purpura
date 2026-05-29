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

## Modelo de datos

8 tablas en PostgreSQL. Sprint 1 (`users`, `convocatorias`, `audit_log`) intacto;
Release 1 añade catálogos (`facultades`, `materias`) y transaccional
(`postulaciones`, `monitores`, `notificaciones`).

| Tabla | PK | Propósito | FKs |
|---|---|---|---|
| `users` | UUID | Cuentas (8 seed + admin) con rol (administrador/coordinador/docente/estudiante) | — |
| `facultades` | int | Catálogo 7 facultades UdeM con color institucional | — |
| `materias` | int | Catálogo 12 materias con código y créditos | → `facultades` |
| `convocatorias` | UUID | Solicitudes de monitoría (BORRADOR/PUBLICADA/CERRADA/ARCHIVADA/ADJUDICADA) | → `users.created_by`, `facultades`, `materias` |
| `postulaciones` | int | Aplicación de un estudiante a una convocatoria. UNIQUE(convocatoria, estudiante) | → `convocatorias`, `users` (estudiante y decididor) |
| `monitores` | int | Adjudicación efectiva de un postulante aprobado | → `postulaciones` (UQ), `convocatorias`, `users` |
| `notificaciones` | int | Bandeja por usuario (leída/no leída) | → `users` |
| `audit_log` | int | Registro append-only de acciones (LOGIN, CREATE_CONVOCATORIA, POSTULAR, …) | soft refs |

Sin Alembic: el arranque de FastAPI llama `SQLModel.metadata.create_all` + `run_migrations()`
(en `app/db.py`), que aplica `ALTER TABLE ADD COLUMN IF NOT EXISTS` sobre `convocatorias`
y `ALTER TYPE ... ADD VALUE IF NOT EXISTS 'adjudicada'` de forma idempotente.

## Equipo
Felipe Cano · José Carlos Jiménez · Santiago Torres · Sebastián Rendón
