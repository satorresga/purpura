# Deploy — Proyecto PÚRPURA

Despliegue en VPS Hetzner Ubuntu 24.04 LTS con Docker Compose.

## Pre-requisitos en el VPS
- Ubuntu 24.04 (probado).
- Docker Engine + docker-compose-plugin instalados (ver Prompt C).
- Puerto 80 abierto en el firewall (ufw allow 80/tcp).
- Git instalado.
- 1+ GB RAM, 5+ GB libres en disco.

## Primer deploy

```bash
# En el VPS, como root o con sudo:
cd /srv
git clone <repo-url> purpura
cd purpura/deploy
cp .env.prod.example .env
nano .env       # generar y pegar valores reales
docker compose up -d --build
docker compose logs -f app    # verificar arranque
# Otra terminal:
docker compose run --rm app uv run seed   # solo primera vez
```

La app queda accesible en `http://<IP_VPS>` (puerto 80).

## Generar secretos seguros
En tu PC local:
```powershell
uv run python -c "import secrets; print('POSTGRES_PASSWORD=' + secrets.token_urlsafe(24))"
uv run python -c "import secrets; print('SESSION_SECRET_KEY=' + secrets.token_urlsafe(48))"
```

## Deploy de cambios (sin perder datos)
```bash
cd /srv/purpura
git pull
cd deploy
docker compose up -d --build app    # rebuilda solo app, db queda intacta
```

## Backup manual de la BD
```bash
docker compose exec -T db pg_dump -U purpura purpura > backup_$(date +%Y%m%d).sql
```

## Reset completo (destruye datos)
```bash
docker compose down -v
docker compose up -d --build
docker compose run --rm app uv run seed
```
