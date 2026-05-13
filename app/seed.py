from datetime import datetime, timedelta

from sqlmodel import Session, select

from app.auth import hash_password
from app.db import engine, init_db
from app.models import Convocatoria, ConvocatoriaStatus, User, UserRole

SEED_USERS = [
    ("admin@purpura.local", "Admin2026!", "Admin PÚRPURA", UserRole.ADMINISTRADOR),
    ("coord.ing@udem.edu.co", "Coord2026!", "Ana Coordinadora Ingeniería", UserRole.COORDINADOR),
    ("coord.com@udem.edu.co", "Coord2026!", "Luis Coordinador Comunicaciones", UserRole.COORDINADOR),
    ("docente1@udem.edu.co", "Docente2026!", "Marta Docente", UserRole.DOCENTE),
    ("docente2@udem.edu.co", "Docente2026!", "Pedro Docente", UserRole.DOCENTE),
    ("estudiante1@udem.edu.co", "Estudiante2026!", "Juan Estudiante", UserRole.ESTUDIANTE),
    ("estudiante2@udem.edu.co", "Estudiante2026!", "Sofia Estudiante", UserRole.ESTUDIANTE),
    ("estudiante3@udem.edu.co", "Estudiante2026!", "Carlos Estudiante", UserRole.ESTUDIANTE),
]


def main() -> None:
    init_db()

    users_created = 0
    users_existing = 0
    convs_created = 0
    convs_existing = 0

    with Session(engine) as session:
        for email, password, full_name, role in SEED_USERS:
            existing = session.exec(select(User).where(User.email == email)).first()
            if existing is not None:
                users_existing += 1
                continue
            user = User(
                email=email,
                password_hash=hash_password(password),
                full_name=full_name,
                role=role,
            )
            session.add(user)
            users_created += 1
        session.commit()

        coord_ing = session.exec(
            select(User).where(User.email == "coord.ing@udem.edu.co")
        ).first()
        if coord_ing is None:
            print(
                f"Usuarios creados: {users_created}, ya existían: {users_existing}. "
                f"Convocatorias creadas: 0, ya existían: 0."
            )
            return

        now = datetime.utcnow()
        seed_convocatorias = [
            {
                "codigo": "MON-2026-01-CALC1",
                "titulo": "Monitoría Cálculo I",
                "facultad": "Ingeniería",
                "asignatura": "Cálculo I",
                "cupos": 2,
                "fecha_apertura": now + timedelta(days=1),
                "fecha_cierre": now + timedelta(days=15),
                "requisitos": {
                    "promedio_minimo": 3.8,
                    "creditos_minimos": 60,
                    "semestre_minimo": 4,
                },
            },
            {
                "codigo": "MON-2026-01-PROG1",
                "titulo": "Monitoría Programación I",
                "facultad": "Ingeniería",
                "asignatura": "Programación I",
                "cupos": 3,
                "fecha_apertura": now + timedelta(days=1),
                "fecha_cierre": now + timedelta(days=20),
                "requisitos": {
                    "promedio_minimo": 3.5,
                    "creditos_minimos": 40,
                    "semestre_minimo": 3,
                },
            },
        ]

        for data in seed_convocatorias:
            existing = session.exec(
                select(Convocatoria).where(Convocatoria.codigo == data["codigo"])
            ).first()
            if existing is not None:
                convs_existing += 1
                continue
            conv = Convocatoria(
                codigo=data["codigo"],
                titulo=data["titulo"],
                descripcion=None,
                facultad=data["facultad"],
                asignatura=data["asignatura"],
                cupos=data["cupos"],
                fecha_apertura=data["fecha_apertura"],
                fecha_cierre=data["fecha_cierre"],
                requisitos=data["requisitos"],
                status=ConvocatoriaStatus.BORRADOR,
                created_by=coord_ing.id,
            )
            session.add(conv)
            convs_created += 1
        session.commit()

    print(
        f"Usuarios creados: {users_created}, ya existían: {users_existing}. "
        f"Convocatorias creadas: {convs_created}, ya existían: {convs_existing}."
    )


if __name__ == "__main__":
    main()
