"""
Servicios de reportes para /reportes.

Todas las funciones son PURAS: reciben session + filtros dict, retornan
data structures. NO hacen render, NO devuelven Response. El router las
compone.

Filtros soportados (siempre dict, claves opcionales):
    facultad_id: Optional[int]
    desde: Optional[date]
    hasta: Optional[date]
    coord_owner_id: Optional[UUID]  # si coordinador, restringe a sus convs

Las queries con `coord_owner_id` aplican filtro
`Convocatoria.created_by == coord_owner_id` en todas las CTEs.
"""
import csv
import io
from datetime import date, datetime
from typing import Any, Optional

from sqlmodel import Session, select

from app.models import (
    Convocatoria,
    ConvocatoriaStatus,
    Facultad,
    Materia,
    Monitor,
    Postulacion,
    User,
)
from app.services.transiciones import (
    POST_ADJUDICADA,
    POST_APROBADA,
    POST_CANCELADA,
    POST_NO_ADJUDICADA,
    POST_RECHAZADA,
)


_ESTADOS_NO_CANCELADAS = (
    "ENVIADA",
    "EN_REVISION",
    POST_APROBADA,
    POST_RECHAZADA,
    POST_ADJUDICADA,
    POST_NO_ADJUDICADA,
)


# ============================================================
# Builders de query con filtros + ACL
# ============================================================


def _convocatorias_visibles_stmt(filtros: dict):
    stmt = select(Convocatoria)
    if filtros.get("coord_owner_id") is not None:
        stmt = stmt.where(Convocatoria.created_by == filtros["coord_owner_id"])
    if filtros.get("facultad_id") is not None:
        stmt = stmt.where(Convocatoria.facultad_id == filtros["facultad_id"])
    return stmt


def _postulaciones_visibles_stmt(filtros: dict):
    stmt = (
        select(Postulacion, Convocatoria)
        .join(Convocatoria, Postulacion.convocatoria_id == Convocatoria.id)
        .where(Postulacion.estado != POST_CANCELADA)
    )
    if filtros.get("coord_owner_id") is not None:
        stmt = stmt.where(Convocatoria.created_by == filtros["coord_owner_id"])
    if filtros.get("facultad_id") is not None:
        stmt = stmt.where(Convocatoria.facultad_id == filtros["facultad_id"])
    if filtros.get("desde"):
        stmt = stmt.where(Postulacion.created_at >= filtros["desde"])
    if filtros.get("hasta"):
        hasta_dt = datetime.combine(filtros["hasta"], datetime.max.time())
        stmt = stmt.where(Postulacion.created_at <= hasta_dt)
    return stmt


# ============================================================
# KPIs y tablas
# ============================================================


def kpis_globales(session: Session, filtros: dict) -> dict[str, Any]:
    convs = session.exec(_convocatorias_visibles_stmt(filtros)).all()
    convs_activas = [
        c for c in convs
        if c.status in (
            ConvocatoriaStatus.PUBLICADA,
            ConvocatoriaStatus.CERRADA,
            ConvocatoriaStatus.ADJUDICADA,
        )
    ]
    postulaciones = session.exec(_postulaciones_visibles_stmt(filtros)).all()
    total_postulaciones = len(postulaciones)
    adjudicadas = sum(1 for p, _c in postulaciones if p.estado == POST_ADJUDICADA)
    tasa = (adjudicadas / total_postulaciones * 100.0) if total_postulaciones > 0 else 0.0
    return {
        "convocatorias_activas": len(convs_activas),
        "postulaciones_total": total_postulaciones,
        "monitorias_adjudicadas": adjudicadas,
        "tasa_adjudicacion": tasa,
    }


def metricas_por_facultad(session: Session, filtros: dict) -> list[dict[str, Any]]:
    facultades = session.exec(select(Facultad).order_by(Facultad.nombre)).all()
    convs = session.exec(_convocatorias_visibles_stmt(filtros)).all()
    posts = session.exec(_postulaciones_visibles_stmt(filtros)).all()

    convs_por_fac: dict[int, list[Convocatoria]] = {}
    for c in convs:
        if c.facultad_id is not None:
            convs_por_fac.setdefault(c.facultad_id, []).append(c)

    posts_por_fac: dict[int, list[Postulacion]] = {}
    for p, c in posts:
        if c.facultad_id is not None:
            posts_por_fac.setdefault(c.facultad_id, []).append(p)

    resultado: list[dict[str, Any]] = []
    for f in facultades:
        f_convs = convs_por_fac.get(f.id, [])
        f_posts = posts_por_fac.get(f.id, [])
        total = len(f_posts)
        adj = sum(1 for p in f_posts if p.estado == POST_ADJUDICADA)
        tasa = (adj / total * 100.0) if total > 0 else 0.0
        if f_convs or f_posts:
            resultado.append(
                {
                    "facultad_id": f.id,
                    "codigo": f.codigo,
                    "nombre": f.nombre,
                    "color_hex": f.color_hex,
                    "convocatorias": len(f_convs),
                    "postulaciones": total,
                    "adjudicadas": adj,
                    "tasa": tasa,
                }
            )
    return resultado


def metricas_por_convocatoria(session: Session, filtros: dict) -> list[dict[str, Any]]:
    rows = session.exec(
        _convocatorias_visibles_stmt(filtros).order_by(Convocatoria.created_at.desc())
    ).all()
    if not rows:
        return []

    ids = [c.id for c in rows]
    posts_rows = session.exec(
        select(Postulacion).where(Postulacion.convocatoria_id.in_(ids))
    ).all()
    posts_por_conv: dict[Any, list[Postulacion]] = {}
    for p in posts_rows:
        posts_por_conv.setdefault(p.convocatoria_id, []).append(p)

    resultado: list[dict[str, Any]] = []
    for c in rows:
        pp = posts_por_conv.get(c.id, [])
        activos = [p for p in pp if p.estado != POST_CANCELADA]
        aprobadas = sum(1 for p in activos if p.estado == POST_APROBADA)
        rechazadas = sum(1 for p in activos if p.estado == POST_RECHAZADA)
        adjudicadas = sum(1 for p in activos if p.estado == POST_ADJUDICADA)
        no_adj = sum(1 for p in activos if p.estado == POST_NO_ADJUDICADA)
        total = len(activos)
        resultado.append(
            {
                "id": c.id,
                "codigo": c.codigo,
                "titulo": c.titulo,
                "estado": c.status.value if c.status else "",
                "cupos": c.cupos,
                "postulaciones_total": total,
                "aprobadas": aprobadas,
                "rechazadas": rechazadas,
                "adjudicadas": adjudicadas,
                "no_adjudicadas": no_adj,
            }
        )
    return resultado


# ============================================================
# Exportes CSV
# ============================================================


def _csv_writer(headers: list[str]) -> tuple[io.StringIO, "csv._writer"]:
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(headers)
    return output, writer


def exportar_postulaciones_csv(session: Session, filtros: dict) -> str:
    output, writer = _csv_writer(
        [
            "id",
            "estudiante_email",
            "estudiante_nombre",
            "convocatoria_codigo",
            "convocatoria_titulo",
            "facultad",
            "estado",
            "decision_ia",
            "ia_modo",
            "ia_confianza",
            "created_at",
            "updated_at",
        ]
    )
    posts = session.exec(_postulaciones_visibles_stmt(filtros)).all()
    if not posts:
        return output.getvalue()

    user_ids = {p.estudiante_id for p, _c in posts}
    users = {
        u.id: u
        for u in session.exec(select(User).where(User.id.in_(user_ids))).all()
    }
    fac_ids = {c.facultad_id for _p, c in posts if c.facultad_id is not None}
    facultades = {
        f.id: f
        for f in (
            session.exec(
                select(Facultad).where(Facultad.id.in_(fac_ids))
            ).all()
            if fac_ids
            else []
        )
    }

    for p, c in posts:
        u = users.get(p.estudiante_id)
        f = facultades.get(c.facultad_id) if c.facultad_id else None
        ev = p.evaluacion_ia_ultima or {}
        writer.writerow(
            [
                p.id,
                u.email if u else "",
                (u.full_name if u else "") or "",
                c.codigo,
                c.titulo,
                f.nombre if f else "",
                p.estado,
                ev.get("decision_sugerida", ""),
                ev.get("modo", ""),
                ev.get("confianza", ""),
                p.created_at.isoformat() if p.created_at else "",
                p.updated_at.isoformat() if p.updated_at else "",
            ]
        )
    return output.getvalue()


def exportar_convocatorias_csv(session: Session, filtros: dict) -> str:
    output, writer = _csv_writer(
        [
            "id",
            "codigo",
            "titulo",
            "estado",
            "facultad",
            "materia_codigo",
            "materia_nombre",
            "semestre",
            "cupos",
            "fecha_apertura",
            "fecha_cierre",
            "postulaciones_total",
            "aprobadas",
            "rechazadas",
            "adjudicadas",
            "no_adjudicadas",
        ]
    )
    metricas = metricas_por_convocatoria(session, filtros)
    if not metricas:
        return output.getvalue()

    ids = [m["id"] for m in metricas]
    rows = session.exec(
        select(Convocatoria, Facultad, Materia)
        .outerjoin(Facultad, Convocatoria.facultad_id == Facultad.id)
        .outerjoin(Materia, Convocatoria.materia_id == Materia.id)
        .where(Convocatoria.id.in_(ids))
    ).all()
    info = {c.id: (c, f, m) for c, f, m in rows}

    for met in metricas:
        c, f, m = info.get(met["id"], (None, None, None))
        if c is None:
            continue
        writer.writerow(
            [
                str(c.id),
                c.codigo,
                c.titulo,
                met["estado"],
                f.nombre if f else "",
                m.codigo if m else "",
                m.nombre if m else "",
                c.semestre,
                c.cupos,
                c.fecha_apertura.isoformat() if c.fecha_apertura else "",
                c.fecha_cierre.isoformat() if c.fecha_cierre else "",
                met["postulaciones_total"],
                met["aprobadas"],
                met["rechazadas"],
                met["adjudicadas"],
                met["no_adjudicadas"],
            ]
        )
    return output.getvalue()


def exportar_monitores_csv(session: Session, filtros: dict) -> str:
    output, writer = _csv_writer(
        [
            "id",
            "estudiante_email",
            "estudiante_nombre",
            "convocatoria_codigo",
            "convocatoria_titulo",
            "facultad",
            "semestre",
            "fecha_adjudicacion",
            "estado",
        ]
    )

    stmt = (
        select(Monitor, Convocatoria, Facultad, User)
        .join(Convocatoria, Monitor.convocatoria_id == Convocatoria.id)
        .join(User, Monitor.estudiante_id == User.id)
        .outerjoin(Facultad, Convocatoria.facultad_id == Facultad.id)
    )
    if filtros.get("coord_owner_id") is not None:
        stmt = stmt.where(Convocatoria.created_by == filtros["coord_owner_id"])
    if filtros.get("facultad_id") is not None:
        stmt = stmt.where(Convocatoria.facultad_id == filtros["facultad_id"])
    if filtros.get("desde"):
        stmt = stmt.where(Monitor.fecha_adjudicacion >= filtros["desde"])
    if filtros.get("hasta"):
        stmt = stmt.where(Monitor.fecha_adjudicacion <= filtros["hasta"])

    rows = session.exec(stmt.order_by(Monitor.fecha_adjudicacion.desc())).all()
    for monitor, conv, fac, est in rows:
        writer.writerow(
            [
                monitor.id,
                est.email if est else "",
                (est.full_name if est else "") or "",
                conv.codigo,
                conv.titulo,
                fac.nombre if fac else "",
                monitor.semestre,
                monitor.fecha_adjudicacion.isoformat()
                if monitor.fecha_adjudicacion
                else "",
                monitor.estado,
            ]
        )
    return output.getvalue()
