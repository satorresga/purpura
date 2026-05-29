from datetime import datetime, timedelta

from sqlmodel import Session, select

from app.auth import hash_password
from app.db import engine, init_db, run_migrations
from app.models import (
    Convocatoria,
    ConvocatoriaStatus,
    Facultad,
    Materia,
    Postulacion,
    User,
    UserRole,
)


SEED_FACULTADES = [
    ("Ingenierías", "ingenierias", "#708F51"),
    ("Ciencias Económicas y Administrativas", "economicas", "#497DA0"),
    ("Derecho", "derecho", "#771F1A"),
    ("Comunicación", "comunicacion", "#52507E"),
    ("Ciencias Sociales y Humanas", "psicologia", "#E4BA35"),
    ("Ciencias Básicas", "computacion", "#7EB89B"),
    ("Diseño", "diseno", "#CF6528"),
]


SEED_MATERIAS = [
    ("ISI-301", "Bases de Datos", "ingenierias", 3),
    ("ISI-405", "Algoritmos y Estructuras", "ingenierias", 3),
    ("ISI-502", "Ingeniería de Software", "ingenierias", 3),
    ("ECO-201", "Microeconomía", "economicas", 3),
    ("ADM-301", "Gestión Organizacional", "economicas", 3),
    ("DER-101", "Derecho Constitucional", "derecho", 3),
    ("DER-205", "Derecho Civil", "derecho", 3),
    ("COM-201", "Comunicación Estratégica", "comunicacion", 3),
    ("PSI-301", "Psicología Cognitiva", "psicologia", 3),
    ("MAT-201", "Cálculo Diferencial", "computacion", 4),
    ("MAT-301", "Álgebra Lineal", "computacion", 4),
    ("DIS-201", "Fundamentos de Diseño", "diseno", 3),
]


SEED_USERS = [
    ("admin@purpura.local", "Admin2026!", "Admin PÚRPURA", UserRole.ADMINISTRADOR),
    ("coord.ing@udem.edu.co", "Coord2026!", "Ana Coordinadora Ingeniería", UserRole.COORDINADOR),
    ("coord.com@udem.edu.co", "Coord2026!", "Luis Coordinador Comunicaciones", UserRole.COORDINADOR),
    ("coord.der@udem.edu.co", "Coord2026!", "Andrea Coordinadora Derecho", UserRole.COORDINADOR),
    ("docente1@udem.edu.co", "Docente2026!", "Marta Docente", UserRole.DOCENTE),
    ("docente2@udem.edu.co", "Docente2026!", "Pedro Docente", UserRole.DOCENTE),
    ("estudiante1@udem.edu.co", "Estudiante2026!", "Juan Estudiante", UserRole.ESTUDIANTE),
    ("estudiante2@udem.edu.co", "Estudiante2026!", "Sofia Estudiante", UserRole.ESTUDIANTE),
    ("estudiante3@udem.edu.co", "Estudiante2026!", "Carlos Estudiante", UserRole.ESTUDIANTE),
]


def _seed_facultades(session: Session) -> tuple[int, int]:
    created = existing = 0
    for nombre, codigo, color in SEED_FACULTADES:
        if session.exec(select(Facultad).where(Facultad.codigo == codigo)).first():
            existing += 1
            continue
        session.add(Facultad(nombre=nombre, codigo=codigo, color_hex=color))
        created += 1
    session.commit()
    return created, existing


def _seed_materias(session: Session) -> tuple[int, int]:
    created = existing = 0
    facultades = {
        f.codigo: f.id
        for f in session.exec(select(Facultad)).all()
    }
    for codigo, nombre, facultad_codigo, creditos in SEED_MATERIAS:
        if session.exec(select(Materia).where(Materia.codigo == codigo)).first():
            existing += 1
            continue
        facultad_id = facultades.get(facultad_codigo)
        if facultad_id is None:
            continue
        session.add(
            Materia(
                facultad_id=facultad_id,
                codigo=codigo,
                nombre=nombre,
                creditos=creditos,
            )
        )
        created += 1
    session.commit()
    return created, existing


_DATOS_ACADEMICOS = {
    "estudiante1@udem.edu.co": (4.5, 80, 6),
    "estudiante2@udem.edu.co": (3.2, 60, 5),
    "estudiante3@udem.edu.co": (None, None, None),
}


def _seed_users(session: Session) -> tuple[int, int]:
    created = existing = 0
    for email, password, full_name, role in SEED_USERS:
        if session.exec(select(User).where(User.email == email)).first():
            existing += 1
            continue
        session.add(
            User(
                email=email,
                password_hash=hash_password(password),
                full_name=full_name,
                role=role,
            )
        )
        created += 1
    session.commit()

    for email, (promedio, creditos, semestre) in _DATOS_ACADEMICOS.items():
        user = session.exec(select(User).where(User.email == email)).first()
        if user is None:
            continue
        user.promedio_acumulado = promedio
        user.creditos_aprobados = creditos
        user.semestre_actual = semestre
        session.add(user)
    session.commit()
    return created, existing


def _seed_convocatorias_legacy(session: Session) -> tuple[int, int]:
    """Convocatorias del Sprint 1 (sin facultad_id/materia_id). Solo se crean
    si no existen ya, para mantener compatibilidad con entornos limpios."""
    coord_ing = session.exec(
        select(User).where(User.email == "coord.ing@udem.edu.co")
    ).first()
    if coord_ing is None:
        return 0, 0

    now = datetime.utcnow()
    legacy = [
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

    created = existing = 0
    for data in legacy:
        if session.exec(
            select(Convocatoria).where(Convocatoria.codigo == data["codigo"])
        ).first():
            existing += 1
            continue
        session.add(
            Convocatoria(
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
                semestre="2026-1",
            )
        )
        created += 1
    session.commit()
    return created, existing


def _seed_convocatorias_r1(session: Session) -> tuple[int, int]:
    """Convocatorias del Release 1 (con facultad_id y materia_id)."""
    users = {
        u.email: u
        for u in session.exec(select(User)).all()
    }
    facultades = {
        f.codigo: f.id for f in session.exec(select(Facultad)).all()
    }
    materias = {
        m.codigo: m.id for m in session.exec(select(Materia)).all()
    }

    nuevas = [
        {
            "codigo": "MON-2026-01-ISI301",
            "titulo": "Monitoría Bases de Datos 2026-1",
            "facultad_codigo": "ingenierias",
            "materia_codigo": "ISI-301",
            "cupos": 2,
            "promedio_minimo": 4.0,
            "semestre": "2026-1",
            "fecha_apertura": datetime(2026, 4, 1),
            "fecha_cierre": datetime(2026, 6, 30),
            "status": ConvocatoriaStatus.PUBLICADA,
            "creador_email": "coord.ing@udem.edu.co",
            "descripcion": (
                "Haber aprobado Bases de Datos con nota mínima 4.0. "
                "Disponibilidad de 8 horas semanales."
            ),
        },
        {
            "codigo": "MON-2026-01-ISI405",
            "titulo": "Monitoría Algoritmos y Estructuras 2026-1",
            "facultad_codigo": "ingenierias",
            "materia_codigo": "ISI-405",
            "cupos": 1,
            "promedio_minimo": 4.2,
            "semestre": "2026-1",
            "fecha_apertura": datetime(2026, 4, 15),
            "fecha_cierre": datetime(2026, 7, 15),
            "status": ConvocatoriaStatus.PUBLICADA,
            "creador_email": "coord.ing@udem.edu.co",
            "descripcion": (
                "Experiencia previa en algoritmos. Promedio mínimo 4.2."
            ),
        },
        {
            "codigo": "MON-2026-01-DER101",
            "titulo": "Monitoría Derecho Constitucional 2026-1",
            "facultad_codigo": "derecho",
            "materia_codigo": "DER-101",
            "cupos": 1,
            "promedio_minimo": 3.8,
            "semestre": "2026-1",
            "fecha_apertura": datetime(2026, 5, 1),
            "fecha_cierre": datetime(2026, 7, 1),
            "status": ConvocatoriaStatus.BORRADOR,
            "creador_email": "coord.der@udem.edu.co",
            "descripcion": "Conocimiento sólido del bloque de constitucionalidad.",
        },
        {
            "codigo": "MON-2025-02-MAT201",
            "titulo": "Monitoría Cálculo Diferencial 2025-2",
            "facultad_codigo": "computacion",
            "materia_codigo": "MAT-201",
            "cupos": 1,
            "promedio_minimo": 3.5,
            "semestre": "2025-2",
            "fecha_apertura": datetime(2025, 11, 1),
            "fecha_cierre": datetime(2025, 12, 15),
            "status": ConvocatoriaStatus.CERRADA,
            "creador_email": "admin@purpura.local",
            "descripcion": None,
        },
        {
            "codigo": "MON-2026-01-PSI301",
            "titulo": "Monitoría Psicología Cognitiva 2026-1",
            "facultad_codigo": "psicologia",
            "materia_codigo": "PSI-301",
            "cupos": 2,
            "promedio_minimo": 3.7,
            "semestre": "2026-1",
            "fecha_apertura": datetime(2026, 5, 15),
            "fecha_cierre": datetime(2026, 7, 30),
            "status": ConvocatoriaStatus.BORRADOR,
            "creador_email": "admin@purpura.local",
            "descripcion": None,
        },
    ]

    created = existing = 0
    for data in nuevas:
        if session.exec(
            select(Convocatoria).where(Convocatoria.codigo == data["codigo"])
        ).first():
            existing += 1
            continue
        creador = users.get(data["creador_email"])
        if creador is None:
            continue
        requisitos: dict = {"promedio_minimo": data["promedio_minimo"]}
        if data["descripcion"]:
            requisitos["descripcion"] = data["descripcion"]
        session.add(
            Convocatoria(
                codigo=data["codigo"],
                titulo=data["titulo"],
                descripcion=data["descripcion"],
                facultad=data["facultad_codigo"],
                asignatura=data["materia_codigo"],
                cupos=data["cupos"],
                fecha_apertura=data["fecha_apertura"],
                fecha_cierre=data["fecha_cierre"],
                requisitos=requisitos,
                status=data["status"],
                created_by=creador.id,
                facultad_id=facultades.get(data["facultad_codigo"]),
                materia_id=materias.get(data["materia_codigo"]),
                semestre=data["semestre"],
            )
        )
        created += 1
    session.commit()
    return created, existing


def _seed_postulaciones(session: Session) -> tuple[int, int]:
    users = {
        u.email: u
        for u in session.exec(select(User)).all()
    }
    convocatorias = {
        c.codigo: c
        for c in session.exec(select(Convocatoria)).all()
    }

    coord_ing_id = users["coord.ing@udem.edu.co"].id if "coord.ing@udem.edu.co" in users else None
    now = datetime.utcnow()

    rows = [
        {
            "conv_codigo": "MON-2026-01-ISI301",
            "estudiante_email": "estudiante1@udem.edu.co",
            "promedio": 4.5,
            "motivacion": (
                "Tengo interés genuino en bases de datos relacionales y NoSQL. "
                "He cursado la materia con buenas notas y quiero acompañar a otros "
                "estudiantes que estén pasando por las mismas dificultades que yo "
                "enfrenté el semestre pasado."
            ),
            "estado": "ENVIADA",
            "decidida_por_id": None,
            "decidida_en": None,
        },
        {
            "conv_codigo": "MON-2026-01-ISI301",
            "estudiante_email": "estudiante2@udem.edu.co",
            "promedio": 4.1,
            "motivacion": "Quiero ayudar a otros estudiantes.",
            "estado": "ENVIADA",
            "decidida_por_id": None,
            "decidida_en": None,
        },
        {
            "conv_codigo": "MON-2026-01-ISI301",
            "estudiante_email": "estudiante3@udem.edu.co",
            "promedio": 3.8,
            "motivacion": (
                "Necesito el ingreso de monitor para mantenerme en la universidad."
            ),
            "estado": "ENVIADA",
            "decidida_por_id": None,
            "decidida_en": None,
        },
        {
            "conv_codigo": "MON-2026-01-ISI405",
            "estudiante_email": "estudiante1@udem.edu.co",
            "promedio": 4.5,
            "motivacion": (
                "Mi tesis es sobre estructuras de datos no convencionales, "
                "específicamente B-trees y árboles de Merkle aplicados a sistemas "
                "distribuidos. Me interesa enormemente acompañar a estudiantes en "
                "este recorrido."
            ),
            "estado": "APROBADA",
            "decidida_por_id": coord_ing_id,
            "decidida_en": now,
        },
        {
            "conv_codigo": "MON-2026-01-ISI405",
            "estudiante_email": "estudiante2@udem.edu.co",
            "promedio": 4.0,
            "motivacion": "Buena experiencia con algoritmos competitivos.",
            "estado": "ENVIADA",
            "decidida_por_id": None,
            "decidida_en": None,
        },
        {
            "conv_codigo": "MON-2026-01-ISI405",
            "estudiante_email": "estudiante3@udem.edu.co",
            "promedio": 3.6,
            "motivacion": "Quiero la monitoría.",
            "estado": "RECHAZADA",
            "decidida_por_id": coord_ing_id,
            "decidida_en": now,
        },
    ]

    created = existing = 0
    for data in rows:
        conv = convocatorias.get(data["conv_codigo"])
        estudiante = users.get(data["estudiante_email"])
        if conv is None or estudiante is None:
            continue
        already = session.exec(
            select(Postulacion).where(
                Postulacion.convocatoria_id == conv.id,
                Postulacion.estudiante_id == estudiante.id,
            )
        ).first()
        if already is not None:
            existing += 1
            continue
        session.add(
            Postulacion(
                convocatoria_id=conv.id,
                estudiante_id=estudiante.id,
                promedio_acumulado=data["promedio"],
                motivacion=data["motivacion"],
                estado=data["estado"],
                decidida_por=data["decidida_por_id"],
                decidida_en=data["decidida_en"],
            )
        )
        created += 1
    session.commit()
    return created, existing


def main() -> None:
    init_db()
    run_migrations()

    with Session(engine) as session:
        fac_c, fac_e = _seed_facultades(session)
        mat_c, mat_e = _seed_materias(session)
        usr_c, usr_e = _seed_users(session)
        leg_c, leg_e = _seed_convocatorias_legacy(session)
        new_c, new_e = _seed_convocatorias_r1(session)
        pos_c, pos_e = _seed_postulaciones(session)

    print(
        f"Facultades creadas: {fac_c}, ya existían: {fac_e}. "
        f"Materias creadas: {mat_c}, ya existían: {mat_e}. "
        f"Usuarios creados: {usr_c}, ya existían: {usr_e}. "
        f"Convocatorias creadas: {leg_c + new_c} ({leg_c} legacy + {new_c} R1), "
        f"ya existían: {leg_e + new_e}. "
        f"Postulaciones creadas: {pos_c}, ya existían: {pos_e}."
    )


if __name__ == "__main__":
    main()
