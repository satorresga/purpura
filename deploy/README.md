# Deploy en VPS

Este docker-compose se usa para el deploy en VPS de $5/mes (Hetzner CX22
o DigitalOcean Basic), NO para desarrollo local en esta máquina.

En desarrollo local usamos PostgreSQL 16 nativo de Windows porque Docker
Desktop tuvo problemas de red para hacer pull contra Docker Hub.

Para deploy en el VPS:
    scp -r . user@servidor:/srv/purpura
    ssh user@servidor
    cd /srv/purpura/deploy
    docker compose up -d
    # luego mover/ajustar app/ y hacer uv sync, uv run seed, uvicorn
