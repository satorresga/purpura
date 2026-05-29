import re
import uuid
from datetime import datetime
from typing import Optional

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select
from starlette.middleware.sessions import SessionMiddleware

from sqlalchemy import text as sa_text

from app.services.adjudicacion import (
    AdjudicacionInvalidaError,
    adjudicar_convocatoria,
)
from app.services.evaluacion_ia import evaluar_postulacion
from app.services.transiciones import (
    POST_APROBADA,
    POST_CANCELADA,
    POST_EN_REVISION,
    POST_ENVIADA,
    POST_RECHAZADA,
    PermisoInsuficienteError,
    TransicionInvalidaError,
    transicionar_estado,
    transicionar_postulacion,
    transiciones_disponibles,
)

from app.auth import (
    get_current_user,
    hash_password,  # noqa: F401
    log_audit,
    require_login,
    require_role,
    verify_password,
)
from app.config import get_settings
from app.db import get_session, init_db, run_migrations
from app.models import (
    Convocatoria,
    ConvocatoriaStatus,
    Facultad,
    Materia,
    Notificacion,
    Postulacion,
    User,
    UserRole,
)

settings = get_settings()

app = FastAPI(title="Proyecto PÚRPURA", version="0.1.0")

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SESSION_SECRET_KEY,
    max_age=8 * 3600,
    same_site="lax",
    https_only=settings.SESSION_COOKIE_SECURE,
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

CODIGO_REGEX = re.compile(r"^MON-\d{4}-\d{2}-[A-Z0-9]+$")


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    run_migrations()


@app.exception_handler(HTTPException)
async def http_exc_handler(request: Request, exc: HTTPException):
    if exc.status_code == 303 and exc.headers and "Location" in exc.headers:
        return RedirectResponse(url=exc.headers["Location"], status_code=303)
    if exc.status_code == 403:
        return templates.TemplateResponse(
            request,
            "base.html",
            {"user": None, "error_403": exc.detail},
            status_code=403,
        )
    raise exc


@app.get("/")
def root(
    request: Request,
    user: Optional[User] = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    if user is not None:
        return RedirectResponse("/dashboard", status_code=303)

    rows = session.exec(
        select(Convocatoria, Facultad, Materia)
        .outerjoin(Facultad, Convocatoria.facultad_id == Facultad.id)
        .outerjoin(Materia, Convocatoria.materia_id == Materia.id)
        .where(Convocatoria.status == ConvocatoriaStatus.PUBLICADA)
        .order_by(Convocatoria.fecha_apertura.desc())
        .limit(3)
    ).all()
    convocatorias = [
        {
            "id": c.id,
            "titulo": c.titulo,
            "descripcion": c.descripcion,
            "cupos": c.cupos,
            "facultad": f,
            "materia": m,
            "estado_publico": "ABIERTA",
        }
        for c, f, m in rows
    ]
    return templates.TemplateResponse(
        request,
        "landing.html",
        {"user": None, "convocatorias": convocatorias},
    )


@app.get("/login")
def login_get(
    request: Request,
    rol: str = "estudiante",
    user: Optional[User] = Depends(get_current_user),
):
    if user is not None:
        return RedirectResponse("/dashboard", status_code=303)
    if rol not in ("estudiante", "coordinador", "administrador"):
        rol = "estudiante"
    return templates.TemplateResponse(
        request,
        "login.html",
        {"user": None, "error": None, "rol_preferido": rol},
    )


@app.get("/documentacion")
def documentacion(request: Request):
    """Documentación pública del sistema. Accesible con o sin sesión."""
    return templates.TemplateResponse(
        request,
        "documentacion.html",
        {"user": None},
    )


@app.get("/reportes")
def reportes(
    request: Request,
    user: User = Depends(
        require_role(UserRole.COORDINADOR, UserRole.ADMINISTRADOR)
    ),
):
    """Stub honesto: el módulo de reportes está planeado para R2 (P08)."""
    return templates.TemplateResponse(
        request,
        "reportes.html",
        {"user": user},
    )


@app.post("/login")
def login_post(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    session: Session = Depends(get_session),
):
    user = session.exec(
        select(User).where(User.email == email.strip().lower())
    ).first()
    if (
        user is None
        or not user.is_active
        or not verify_password(password, user.password_hash)
    ):
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "user": None,
                "error": "Credenciales inválidas",
            },
            status_code=200,
        )

    request.session["user_id"] = str(user.id)
    request.session["email"] = user.email
    request.session["nombre_completo"] = user.full_name
    request.session["rol"] = user.role.value
    user.last_login_at = datetime.utcnow()
    session.add(user)
    session.commit()
    log_audit(session, user_id=user.id, action="LOGIN", request=request)
    return RedirectResponse("/dashboard", status_code=303)


@app.post("/logout")
def logout(
    request: Request,
    user: Optional[User] = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    if user is not None:
        log_audit(session, user_id=user.id, action="LOGOUT", request=request)
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@app.get("/dashboard")
def dashboard(
    request: Request,
    user: User = Depends(require_login),
):
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"user": user},
    )


@app.get("/convocatorias")
def convocatorias_list(
    request: Request,
    user: User = Depends(require_login),
    session: Session = Depends(get_session),
):
    stmt = (
        select(Convocatoria, User, Facultad, Materia)
        .join(User, Convocatoria.created_by == User.id)
        .outerjoin(Facultad, Convocatoria.facultad_id == Facultad.id)
        .outerjoin(Materia, Convocatoria.materia_id == Materia.id)
    )
    if user.role == UserRole.ESTUDIANTE:
        stmt = stmt.where(Convocatoria.status == ConvocatoriaStatus.PUBLICADA)
    else:
        stmt = stmt.where(Convocatoria.status != ConvocatoriaStatus.ARCHIVADA)

    rows = session.exec(stmt).all()
    convocatorias = [
        {
            "id": conv.id,
            "codigo": conv.codigo,
            "titulo": conv.titulo,
            "facultad": facultad_obj,
            "materia": materia_obj,
            "asignatura": conv.asignatura,
            "cupos": conv.cupos,
            "semestre": conv.semestre,
            "fecha_apertura": conv.fecha_apertura,
            "fecha_cierre": conv.fecha_cierre,
            "status": conv.status.value if conv.status else None,
            "created_by_full_name": creator.full_name,
            "created_by_id": conv.created_by,
            "puede_editar": (
                conv.status == ConvocatoriaStatus.BORRADOR
                and (
                    user.role == UserRole.ADMINISTRADOR
                    or (
                        user.role == UserRole.COORDINADOR
                        and conv.created_by == user.id
                    )
                )
            ),
        }
        for conv, creator, facultad_obj, materia_obj in rows
    ]
    return templates.TemplateResponse(
        request,
        "convocatorias_list.html",
        {"user": user, "convocatorias": convocatorias},
    )


@app.get("/convocatorias/crear")
def convocatorias_crear_get(
    request: Request,
    user: User = Depends(
        require_role(UserRole.COORDINADOR, UserRole.ADMINISTRADOR)
    ),
):
    return templates.TemplateResponse(
        request,
        "convocatorias_form.html",
        {"user": user, "error": None, "form": {}},
    )


def _parse_optional_number(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    v = value.strip()
    if not v:
        return None
    return float(v)


@app.post("/convocatorias/crear")
def convocatorias_crear_post(
    request: Request,
    codigo: str = Form(...),
    titulo: str = Form(...),
    descripcion: Optional[str] = Form(None),
    facultad: str = Form(...),
    asignatura: str = Form(...),
    cupos: int = Form(...),
    fecha_apertura: str = Form(...),
    fecha_cierre: str = Form(...),
    promedio_minimo: Optional[str] = Form(None),
    creditos_minimos: Optional[str] = Form(None),
    semestre_minimo: Optional[str] = Form(None),
    user: User = Depends(
        require_role(UserRole.COORDINADOR, UserRole.ADMINISTRADOR)
    ),
    session: Session = Depends(get_session),
):
    form_data = {
        "codigo": codigo,
        "titulo": titulo,
        "descripcion": descripcion or "",
        "facultad": facultad,
        "asignatura": asignatura,
        "cupos": cupos,
        "fecha_apertura": fecha_apertura,
        "fecha_cierre": fecha_cierre,
        "promedio_minimo": promedio_minimo or "",
        "creditos_minimos": creditos_minimos or "",
        "semestre_minimo": semestre_minimo or "",
    }

    def render_error(msg: str):
        return templates.TemplateResponse(
            request,
            "convocatorias_form.html",
            {
                "user": user,
                "error": msg,
                "form": form_data,
            },
            status_code=200,
        )

    codigo_norm = codigo.strip().upper()
    if not CODIGO_REGEX.match(codigo_norm):
        return render_error(
            "El código debe seguir el formato MON-AAAA-NN-XXXX (ej. MON-2026-01-CALC1)."
        )

    if cupos <= 0:
        return render_error("Los cupos deben ser mayores a 0.")

    try:
        apertura_dt = datetime.fromisoformat(fecha_apertura)
        cierre_dt = datetime.fromisoformat(fecha_cierre)
    except ValueError:
        return render_error("Las fechas tienen un formato inválido.")

    if cierre_dt <= apertura_dt:
        return render_error(
            "La fecha de cierre debe ser posterior a la fecha de apertura."
        )

    existing = session.exec(
        select(Convocatoria).where(Convocatoria.codigo == codigo_norm)
    ).first()
    if existing is not None:
        return render_error(f"Ya existe una convocatoria con el código {codigo_norm}.")

    requisitos: dict = {}
    try:
        prom = _parse_optional_number(promedio_minimo)
        cred = _parse_optional_number(creditos_minimos)
        sem = _parse_optional_number(semestre_minimo)
    except ValueError:
        return render_error("Los requisitos numéricos no son válidos.")

    if prom is not None:
        requisitos["promedio_minimo"] = prom
    if cred is not None:
        requisitos["creditos_minimos"] = int(cred)
    if sem is not None:
        requisitos["semestre_minimo"] = int(sem)

    conv = Convocatoria(
        codigo=codigo_norm,
        titulo=titulo.strip(),
        descripcion=(descripcion.strip() if descripcion else None),
        facultad=facultad.strip(),
        asignatura=asignatura.strip(),
        cupos=cupos,
        fecha_apertura=apertura_dt,
        fecha_cierre=cierre_dt,
        requisitos=requisitos,
        status=ConvocatoriaStatus.BORRADOR,
        created_by=user.id,
    )
    session.add(conv)
    session.commit()
    session.refresh(conv)

    log_audit(
        session,
        user_id=user.id,
        action="CREATE_CONVOCATORIA",
        request=request,
        entity_type="convocatoria",
        entity_id=conv.id,
        payload={"codigo": conv.codigo, "titulo": conv.titulo},
    )

    return RedirectResponse("/convocatorias", status_code=303)


def _flash(request: Request, level: str, msg: str) -> None:
    """Apila un mensaje flash en la sesión para que base.html lo renderice."""
    bag = request.session.get("flash", [])
    bag.append([level, msg])
    request.session["flash"] = bag


def _load_convocatoria_or_404(
    session: Session, conv_id: uuid.UUID
) -> tuple[Convocatoria, User, Optional[Facultad], Optional[Materia]]:
    row = session.exec(
        select(Convocatoria, User, Facultad, Materia)
        .join(User, Convocatoria.created_by == User.id)
        .outerjoin(Facultad, Convocatoria.facultad_id == Facultad.id)
        .outerjoin(Materia, Convocatoria.materia_id == Materia.id)
        .where(Convocatoria.id == conv_id)
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Convocatoria no encontrada")
    return row


@app.get("/convocatorias/archivadas")
def convocatorias_archivadas(
    request: Request,
    user: User = Depends(require_role(UserRole.ADMINISTRADOR)),
    session: Session = Depends(get_session),
):
    rows = session.exec(
        select(Convocatoria, User, Facultad, Materia)
        .join(User, Convocatoria.created_by == User.id)
        .outerjoin(Facultad, Convocatoria.facultad_id == Facultad.id)
        .outerjoin(Materia, Convocatoria.materia_id == Materia.id)
        .where(Convocatoria.status == ConvocatoriaStatus.ARCHIVADA)
        .order_by(Convocatoria.updated_at.desc())
    ).all()
    convocatorias = [
        {
            "id": conv.id,
            "codigo": conv.codigo,
            "titulo": conv.titulo,
            "facultad": facultad_obj,
            "semestre": conv.semestre,
            "status": conv.status.value,
            "updated_at": conv.updated_at,
            "created_by_full_name": creator.full_name,
        }
        for conv, creator, facultad_obj, materia_obj in rows
    ]
    return templates.TemplateResponse(
        request,
        "convocatorias_archivadas.html",
        {"user": user, "convocatorias": convocatorias},
    )


@app.get("/convocatorias/{conv_id}")
def convocatorias_detalle(
    request: Request,
    conv_id: uuid.UUID,
    user: User = Depends(require_login),
    session: Session = Depends(get_session),
):
    conv, creator, facultad_obj, materia_obj = _load_convocatoria_or_404(
        session, conv_id
    )
    transiciones = transiciones_disponibles(conv, user)
    puede_editar = (
        conv.status == ConvocatoriaStatus.BORRADOR
        and (
            user.role == UserRole.ADMINISTRADOR
            or (
                user.role == UserRole.COORDINADOR
                and conv.created_by == user.id
            )
        )
    )

    monitores_info = None
    if conv.status == ConvocatoriaStatus.ADJUDICADA:
        from app.models import Monitor

        monitor_rows = session.exec(
            select(Monitor, User)
            .join(User, Monitor.estudiante_id == User.id)
            .where(Monitor.convocatoria_id == conv.id)
            .order_by(Monitor.fecha_adjudicacion.desc())
        ).all()
        total = len(monitor_rows)
        if user.role in (UserRole.ADMINISTRADOR, UserRole.COORDINADOR):
            monitores_info = {
                "total": total,
                "lista": [
                    {
                        "nombre": est.full_name or est.email,
                        "email": est.email,
                        "fecha": m.fecha_adjudicacion,
                        "postulacion_id": m.postulacion_id,
                    }
                    for m, est in monitor_rows
                ],
            }
        else:
            monitores_info = {"total": total, "lista": None}

    postulacion_activa: Optional[Postulacion] = None
    postulacion_historica: Optional[Postulacion] = None
    puede_postular = False
    puede_cancelar_postulacion = False
    if user.role == UserRole.ESTUDIANTE:
        postulacion_activa = session.exec(
            select(Postulacion)
            .where(Postulacion.convocatoria_id == conv.id)
            .where(Postulacion.estudiante_id == user.id)
            .where(Postulacion.estado != POST_CANCELADA)
        ).first()
        if postulacion_activa is None:
            postulacion_historica = session.exec(
                select(Postulacion)
                .where(Postulacion.convocatoria_id == conv.id)
                .where(Postulacion.estudiante_id == user.id)
                .order_by(Postulacion.created_at.desc())
            ).first()
        if conv.status == ConvocatoriaStatus.PUBLICADA:
            if postulacion_activa is None:
                puede_postular = True
            elif postulacion_activa.estado in (POST_ENVIADA, POST_EN_REVISION):
                puede_cancelar_postulacion = True

    return templates.TemplateResponse(
        request,
        "convocatorias_detalle.html",
        {
            "user": user,
            "convocatoria": conv,
            "facultad": facultad_obj,
            "materia": materia_obj,
            "creator": creator,
            "transiciones": transiciones,
            "puede_editar": puede_editar,
            "postulacion_activa": postulacion_activa,
            "postulacion_historica": postulacion_historica,
            "puede_postular": puede_postular,
            "puede_cancelar_postulacion": puede_cancelar_postulacion,
            "monitores_info": monitores_info,
        },
    )


@app.get("/convocatorias/{conv_id}/editar")
def convocatorias_editar_get(
    request: Request,
    conv_id: uuid.UUID,
    user: User = Depends(
        require_role(UserRole.COORDINADOR, UserRole.ADMINISTRADOR)
    ),
    session: Session = Depends(get_session),
):
    conv, _creator, facultad_obj, materia_obj = _load_convocatoria_or_404(
        session, conv_id
    )
    if conv.status != ConvocatoriaStatus.BORRADOR:
        _flash(
            request,
            "warning",
            "Solo se pueden editar convocatorias en estado BORRADOR.",
        )
        return RedirectResponse(f"/convocatorias/{conv.id}", status_code=303)
    if user.role == UserRole.COORDINADOR and conv.created_by != user.id:
        raise HTTPException(
            status_code=403,
            detail="Solo el coordinador que creó la convocatoria puede editarla.",
        )
    form = {
        "titulo": conv.titulo,
        "descripcion": conv.descripcion or "",
        "facultad": conv.facultad,
        "asignatura": conv.asignatura,
        "cupos": conv.cupos,
        "fecha_apertura": conv.fecha_apertura.strftime("%Y-%m-%dT%H:%M"),
        "fecha_cierre": conv.fecha_cierre.strftime("%Y-%m-%dT%H:%M"),
        "promedio_minimo": str(conv.requisitos.get("promedio_minimo", "")),
        "creditos_minimos": str(conv.requisitos.get("creditos_minimos", "")),
        "semestre_minimo": str(conv.requisitos.get("semestre_minimo", "")),
    }
    return templates.TemplateResponse(
        request,
        "convocatorias_editar.html",
        {
            "user": user,
            "convocatoria": conv,
            "form": form,
            "error": None,
        },
    )


@app.post("/convocatorias/{conv_id}/editar")
def convocatorias_editar_post(
    request: Request,
    conv_id: uuid.UUID,
    titulo: str = Form(...),
    descripcion: Optional[str] = Form(None),
    facultad: str = Form(...),
    asignatura: str = Form(...),
    cupos: int = Form(...),
    fecha_apertura: str = Form(...),
    fecha_cierre: str = Form(...),
    promedio_minimo: Optional[str] = Form(None),
    creditos_minimos: Optional[str] = Form(None),
    semestre_minimo: Optional[str] = Form(None),
    user: User = Depends(
        require_role(UserRole.COORDINADOR, UserRole.ADMINISTRADOR)
    ),
    session: Session = Depends(get_session),
):
    conv, _creator, facultad_obj, materia_obj = _load_convocatoria_or_404(
        session, conv_id
    )
    if conv.status != ConvocatoriaStatus.BORRADOR:
        _flash(
            request,
            "warning",
            "Solo se pueden editar convocatorias en estado BORRADOR.",
        )
        return RedirectResponse(f"/convocatorias/{conv.id}", status_code=303)
    if user.role == UserRole.COORDINADOR and conv.created_by != user.id:
        raise HTTPException(
            status_code=403,
            detail="Solo el coordinador que creó la convocatoria puede editarla.",
        )

    form_data = {
        "titulo": titulo,
        "descripcion": descripcion or "",
        "facultad": facultad,
        "asignatura": asignatura,
        "cupos": cupos,
        "fecha_apertura": fecha_apertura,
        "fecha_cierre": fecha_cierre,
        "promedio_minimo": promedio_minimo or "",
        "creditos_minimos": creditos_minimos or "",
        "semestre_minimo": semestre_minimo or "",
    }

    def render_error(msg: str):
        return templates.TemplateResponse(
            request,
            "convocatorias_editar.html",
            {
                "user": user,
                "convocatoria": conv,
                "form": form_data,
                "error": msg,
            },
            status_code=200,
        )

    if cupos <= 0:
        return render_error("Los cupos deben ser mayores a 0.")
    try:
        apertura_dt = datetime.fromisoformat(fecha_apertura)
        cierre_dt = datetime.fromisoformat(fecha_cierre)
    except ValueError:
        return render_error("Las fechas tienen un formato inválido.")
    if cierre_dt <= apertura_dt:
        return render_error(
            "La fecha de cierre debe ser posterior a la fecha de apertura."
        )

    requisitos: dict = dict(conv.requisitos or {})
    try:
        prom = _parse_optional_number(promedio_minimo)
        cred = _parse_optional_number(creditos_minimos)
        sem = _parse_optional_number(semestre_minimo)
    except ValueError:
        return render_error("Los requisitos numéricos no son válidos.")
    if prom is not None:
        requisitos["promedio_minimo"] = prom
    else:
        requisitos.pop("promedio_minimo", None)
    if cred is not None:
        requisitos["creditos_minimos"] = int(cred)
    else:
        requisitos.pop("creditos_minimos", None)
    if sem is not None:
        requisitos["semestre_minimo"] = int(sem)
    else:
        requisitos.pop("semestre_minimo", None)

    conv.titulo = titulo.strip()
    conv.descripcion = descripcion.strip() if descripcion else None
    conv.facultad = facultad.strip()
    conv.asignatura = asignatura.strip()
    conv.cupos = cupos
    conv.fecha_apertura = apertura_dt
    conv.fecha_cierre = cierre_dt
    conv.requisitos = requisitos
    conv.updated_at = datetime.utcnow()
    session.add(conv)
    session.commit()
    log_audit(
        session,
        user_id=user.id,
        action="EDIT_CONVOCATORIA",
        request=request,
        entity_type="convocatoria",
        entity_id=conv.id,
        payload={"codigo": conv.codigo},
    )
    _flash(request, "success", f"Convocatoria {conv.codigo} actualizada.")
    return RedirectResponse(f"/convocatorias/{conv.id}", status_code=303)


@app.post("/convocatorias/{conv_id}/transicionar")
def convocatorias_transicionar(
    request: Request,
    conv_id: uuid.UUID,
    nuevo_estado: str = Form(...),
    motivo: str = Form(""),
    user: User = Depends(
        require_role(UserRole.COORDINADOR, UserRole.ADMINISTRADOR)
    ),
    session: Session = Depends(get_session),
):
    conv, _creator, _f, _m = _load_convocatoria_or_404(session, conv_id)
    try:
        nuevo = ConvocatoriaStatus(nuevo_estado.lower())
    except ValueError:
        _flash(request, "danger", f"Estado '{nuevo_estado}' no es válido.")
        return RedirectResponse(f"/convocatorias/{conv.id}", status_code=303)

    accion_audit = f"TRANSICION_{conv.status.value.upper()}_TO_{nuevo.value.upper()}"
    estado_origen = conv.status.value
    try:
        transicionar_estado(conv, nuevo, user, motivo=motivo)
    except TransicionInvalidaError as e:
        _flash(request, "danger", f"Transición no permitida: {e}")
        return RedirectResponse(f"/convocatorias/{conv.id}", status_code=303)
    except PermisoInsuficienteError as e:
        _flash(request, "danger", f"Permiso insuficiente: {e}")
        return RedirectResponse(f"/convocatorias/{conv.id}", status_code=303)

    session.add(conv)
    session.commit()
    log_audit(
        session,
        user_id=user.id,
        action=accion_audit,
        request=request,
        entity_type="convocatoria",
        entity_id=conv.id,
        payload={
            "from": estado_origen,
            "to": nuevo.value,
            "motivo": motivo,
        },
    )
    _flash(
        request,
        "success",
        f"Convocatoria {conv.codigo}: {estado_origen} → {nuevo.value}.",
    )
    return RedirectResponse(f"/convocatorias/{conv.id}", status_code=303)


# ============================================================
# Postulaciones (P03)
# ============================================================

_MOTIVACION_DEFAULT = (
    "Postulación enviada desde el detalle de la convocatoria. "
    "El estudiante aceptó los requisitos y solicita revisión."
)


def _registrar_evaluacion_ia(
    postulacion: Postulacion,
    convocatoria: Convocatoria,
    estudiante: User,
    user: User,
    trigger: str,
) -> dict:
    """Ejecuta evaluación y persiste en el objeto. Caller hace commit."""
    resultado = evaluar_postulacion(postulacion, convocatoria, estudiante)
    postulacion.evaluacion_ia_ultima = resultado
    historial = list(postulacion.historial_estados or [])
    historial.append(
        {
            "tipo": "evaluacion_ia",
            "trigger": trigger,
            "by_user_id": str(user.id),
            "by_email": user.email,
            **resultado,
        }
    )
    postulacion.historial_estados = historial
    return resultado


@app.post("/convocatorias/{conv_id}/postular")
def postular_post(
    request: Request,
    conv_id: uuid.UUID,
    motivacion: str = Form(default=_MOTIVACION_DEFAULT),
    user: User = Depends(require_role(UserRole.ESTUDIANTE)),
    session: Session = Depends(get_session),
):
    conv = session.exec(
        select(Convocatoria).where(Convocatoria.id == conv_id)
    ).first()
    if conv is None:
        raise HTTPException(status_code=404, detail="Convocatoria no encontrada")
    if conv.status != ConvocatoriaStatus.PUBLICADA:
        _flash(
            request,
            "danger",
            "Solo se puede postular a convocatorias PUBLICADAS.",
        )
        return RedirectResponse(f"/convocatorias/{conv.id}", status_code=303)

    existing = session.exec(
        select(Postulacion)
        .where(Postulacion.convocatoria_id == conv.id)
        .where(Postulacion.estudiante_id == user.id)
        .where(Postulacion.estado != POST_CANCELADA)
    ).first()
    if existing is not None:
        _flash(
            request,
            "warning",
            f"Ya tienes una postulación activa para {conv.codigo} (estado: {existing.estado}).",
        )
        return RedirectResponse(f"/convocatorias/{conv.id}", status_code=303)

    motivacion_final = (motivacion or "").strip() or _MOTIVACION_DEFAULT

    historial_inicial = [
        {
            "from": "(creación)",
            "to": POST_ENVIADA,
            "by_user_id": str(user.id),
            "by_email": user.email,
            "motivo": "Postulación creada",
            "at": datetime.utcnow().isoformat(),
        },
        {
            "tipo": "validacion_inicial",
            "promedio_validado": False,
            "creditos_validados": False,
            "razon": "datos_academicos_incompletos_en_modelo_user",
            "manual_review": True,
            "at": datetime.utcnow().isoformat(),
        },
    ]

    postulacion = Postulacion(
        convocatoria_id=conv.id,
        estudiante_id=user.id,
        promedio_acumulado=0.0,
        motivacion=motivacion_final,
        decision_automatica="REVISAR",
        justificacion_automatica="Datos académicos del estudiante no disponibles en el modelo User; requiere revisión manual.",
        estado=POST_ENVIADA,
        historial_estados=historial_inicial,
    )
    session.add(postulacion)
    session.flush()

    _registrar_evaluacion_ia(postulacion, conv, user, user, trigger="postular")

    notif = Notificacion(
        usuario_id=conv.created_by,
        titulo=f"Nueva postulación en {conv.codigo}",
        cuerpo=(
            f"{user.full_name} ({user.email}) postuló a tu convocatoria "
            f"{conv.titulo}. Requiere revisión manual de requisitos."
        ),
        url_destino=f"/convocatorias/{conv.id}",
        leida=False,
    )
    session.add(notif)
    session.commit()
    session.refresh(postulacion)

    log_audit(
        session,
        user_id=user.id,
        action="POSTULAR",
        request=request,
        entity_type="postulacion",
        entity_id=None,
        payload={"postulacion_id": postulacion.id, "convocatoria": conv.codigo},
    )
    _flash(
        request,
        "success",
        f"Postulación enviada a {conv.codigo}. Te avisaremos cuando haya revisión.",
    )
    return RedirectResponse("/mis-postulaciones", status_code=303)


@app.get("/mis-postulaciones")
def mis_postulaciones(
    request: Request,
    user: User = Depends(require_role(UserRole.ESTUDIANTE)),
    session: Session = Depends(get_session),
):
    rows = session.exec(
        select(Postulacion, Convocatoria, Facultad)
        .join(Convocatoria, Postulacion.convocatoria_id == Convocatoria.id)
        .outerjoin(Facultad, Convocatoria.facultad_id == Facultad.id)
        .where(Postulacion.estudiante_id == user.id)
        .order_by(Postulacion.created_at.desc())
    ).all()
    postulaciones = [
        {
            "id": post.id,
            "estado": post.estado,
            "created_at": post.created_at,
            "updated_at": post.updated_at,
            "convocatoria_id": conv.id,
            "convocatoria_codigo": conv.codigo,
            "convocatoria_titulo": conv.titulo,
            "convocatoria_status": conv.status.value,
            "facultad": facultad_obj,
            "puede_cancelar": (
                post.estado in (POST_ENVIADA, POST_EN_REVISION)
                and conv.status == ConvocatoriaStatus.PUBLICADA
            ),
        }
        for post, conv, facultad_obj in rows
    ]
    return templates.TemplateResponse(
        request,
        "mis_postulaciones.html",
        {"user": user, "postulaciones": postulaciones},
    )


@app.post("/postulaciones/{post_id}/cancelar")
def postulacion_cancelar(
    request: Request,
    post_id: int,
    user: User = Depends(require_role(UserRole.ESTUDIANTE)),
    session: Session = Depends(get_session),
):
    postulacion = session.exec(
        select(Postulacion).where(Postulacion.id == post_id)
    ).first()
    if postulacion is None:
        raise HTTPException(status_code=404, detail="Postulación no encontrada")
    if postulacion.estudiante_id != user.id:
        raise HTTPException(
            status_code=403,
            detail="Solo puedes cancelar tus propias postulaciones.",
        )
    conv = session.exec(
        select(Convocatoria).where(Convocatoria.id == postulacion.convocatoria_id)
    ).first()
    if conv is None:
        raise HTTPException(status_code=404, detail="Convocatoria no encontrada")
    if conv.status != ConvocatoriaStatus.PUBLICADA:
        _flash(
            request,
            "warning",
            "Solo se puede cancelar mientras la convocatoria sigue PUBLICADA.",
        )
        return RedirectResponse("/mis-postulaciones", status_code=303)

    try:
        transicionar_postulacion(
            postulacion,
            POST_CANCELADA,
            user,
            conv,
            motivo="cancelación voluntaria del estudiante",
        )
    except (TransicionInvalidaError, PermisoInsuficienteError) as e:
        _flash(request, "danger", str(e))
        return RedirectResponse("/mis-postulaciones", status_code=303)

    session.add(postulacion)
    session.commit()
    log_audit(
        session,
        user_id=user.id,
        action="POSTULACION_CANCELAR",
        request=request,
        entity_type="postulacion",
        entity_id=None,
        payload={"postulacion_id": postulacion.id, "convocatoria": conv.codigo},
    )
    _flash(
        request,
        "success",
        f"Postulación a {conv.codigo} cancelada.",
    )
    return RedirectResponse("/mis-postulaciones", status_code=303)


# ============================================================
# Bandeja del coordinador (P04)
# ============================================================


def _puede_ver_postulacion(user: User, conv: Convocatoria) -> bool:
    """Admin ve todas. Coord ve solo las de convocatorias que creó."""
    if user.role == UserRole.ADMINISTRADOR:
        return True
    if user.role == UserRole.COORDINADOR:
        return conv.created_by == user.id
    return False


@app.get("/bandeja")
def bandeja(
    request: Request,
    convocatoria: Optional[str] = None,
    estado: str = "activas",
    warning: Optional[str] = None,
    ia: Optional[str] = None,
    user: User = Depends(
        require_role(UserRole.COORDINADOR, UserRole.ADMINISTRADOR)
    ),
    session: Session = Depends(get_session),
):
    convocatorias_stmt = select(Convocatoria).where(
        Convocatoria.status.in_(
            [ConvocatoriaStatus.PUBLICADA, ConvocatoriaStatus.CERRADA]
        )
    )
    if user.role == UserRole.COORDINADOR:
        convocatorias_stmt = convocatorias_stmt.where(
            Convocatoria.created_by == user.id
        )
    convs_visibles = session.exec(
        convocatorias_stmt.order_by(Convocatoria.codigo)
    ).all()
    ids_visibles = [c.id for c in convs_visibles]

    if not ids_visibles:
        postulaciones: list[dict] = []
    else:
        stmt = (
            select(Postulacion, Convocatoria, User)
            .join(Convocatoria, Postulacion.convocatoria_id == Convocatoria.id)
            .join(User, Postulacion.estudiante_id == User.id)
            .where(Postulacion.convocatoria_id.in_(ids_visibles))
        )

        estado_norm = (estado or "activas").lower()
        if estado_norm == "enviada":
            stmt = stmt.where(Postulacion.estado == POST_ENVIADA)
        elif estado_norm == "en_revision":
            stmt = stmt.where(Postulacion.estado == POST_EN_REVISION)
        elif estado_norm == "todas":
            pass
        else:  # activas (default)
            stmt = stmt.where(
                Postulacion.estado.in_([POST_ENVIADA, POST_EN_REVISION])
            )

        if convocatoria:
            try:
                conv_uuid = uuid.UUID(convocatoria)
                stmt = stmt.where(Postulacion.convocatoria_id == conv_uuid)
            except ValueError:
                pass

        if warning == "true":
            stmt = stmt.where(
                sa_text(
                    "postulaciones.historial_estados @> "
                    "'[{\"manual_review\": true}]'::jsonb"
                )
            )

        ia_filtro = (ia or "").lower()
        _IA_MAP = {
            "apto": "AUTO_APTO",
            "no_apto": "AUTO_NO_APTO",
            "revisar": "REVISAR_MANUAL",
        }
        if ia_filtro in _IA_MAP:
            stmt = stmt.where(
                sa_text(
                    "postulaciones.evaluacion_ia_ultima->>'decision_sugerida' = :decision"
                ).bindparams(decision=_IA_MAP[ia_filtro])
            )

        rows = session.exec(
            stmt.order_by(Postulacion.created_at.desc())
        ).all()
        postulaciones = [
            {
                "id": post.id,
                "estado": post.estado,
                "created_at": post.created_at,
                "decision_automatica": post.decision_automatica,
                "convocatoria_id": conv.id,
                "convocatoria_codigo": conv.codigo,
                "convocatoria_titulo": conv.titulo,
                "estudiante_nombre": estudiante.full_name or estudiante.email,
                "estudiante_email": estudiante.email,
                "tiene_warning": any(
                    isinstance(ev, dict) and ev.get("manual_review") is True
                    for ev in (post.historial_estados or [])
                ),
                "evaluacion": post.evaluacion_ia_ultima,
            }
            for post, conv, estudiante in rows
        ]

    return templates.TemplateResponse(
        request,
        "bandeja.html",
        {
            "user": user,
            "postulaciones": postulaciones,
            "convocatorias_filtro": convs_visibles,
            "filtro_estado": (estado or "activas").lower(),
            "filtro_convocatoria": convocatoria or "",
            "filtro_warning": warning == "true",
            "filtro_ia": (ia or "").lower(),
        },
    )


def _load_postulacion_or_404(
    session: Session, post_id: int, user: User
) -> tuple[Postulacion, Convocatoria, User]:
    row = session.exec(
        select(Postulacion, Convocatoria, User)
        .join(Convocatoria, Postulacion.convocatoria_id == Convocatoria.id)
        .join(User, Postulacion.estudiante_id == User.id)
        .where(Postulacion.id == post_id)
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Postulación no encontrada")
    post, conv, estudiante = row
    if not _puede_ver_postulacion(user, conv):
        raise HTTPException(
            status_code=403,
            detail="Solo el coordinador owner o un administrador pueden ver esta postulación.",
        )
    return post, conv, estudiante


@app.get("/postulaciones/{post_id}")
def postulacion_detalle(
    request: Request,
    post_id: int,
    user: User = Depends(
        require_role(UserRole.COORDINADOR, UserRole.ADMINISTRADOR)
    ),
    session: Session = Depends(get_session),
):
    post, conv, estudiante = _load_postulacion_or_404(session, post_id, user)
    es_owner_o_admin = (
        user.role == UserRole.ADMINISTRADOR or conv.created_by == user.id
    )
    puede_iniciar_revision = post.estado == POST_ENVIADA and es_owner_o_admin
    puede_anotar = post.estado == POST_EN_REVISION and es_owner_o_admin
    puede_decidir = post.estado == POST_EN_REVISION and es_owner_o_admin
    return templates.TemplateResponse(
        request,
        "postulacion_detalle.html",
        {
            "user": user,
            "postulacion": post,
            "convocatoria": conv,
            "estudiante": estudiante,
            "puede_iniciar_revision": puede_iniciar_revision,
            "puede_anotar": puede_anotar,
            "puede_decidir": puede_decidir,
        },
    )


@app.post("/postulaciones/{post_id}/transicionar")
def postulacion_transicionar(
    request: Request,
    post_id: int,
    nuevo_estado: str = Form(...),
    motivo: str = Form(""),
    user: User = Depends(
        require_role(UserRole.COORDINADOR, UserRole.ADMINISTRADOR)
    ),
    session: Session = Depends(get_session),
):
    post, conv, estudiante = _load_postulacion_or_404(session, post_id, user)
    estado_origen = post.estado
    nuevo_norm = nuevo_estado.upper()
    if nuevo_norm == POST_RECHAZADA and not (motivo or "").strip():
        _flash(
            request,
            "danger",
            "El motivo es obligatorio al rechazar una postulación.",
        )
        return RedirectResponse(f"/postulaciones/{post.id}", status_code=303)
    try:
        transicionar_postulacion(
            post, nuevo_norm, user, conv, motivo=motivo
        )
    except TransicionInvalidaError as e:
        _flash(request, "danger", f"Transición no permitida: {e}")
        return RedirectResponse(f"/postulaciones/{post.id}", status_code=303)
    except PermisoInsuficienteError as e:
        _flash(request, "danger", f"Permiso insuficiente: {e}")
        return RedirectResponse(f"/postulaciones/{post.id}", status_code=303)

    if post.estado == POST_EN_REVISION:
        _registrar_evaluacion_ia(
            post, conv, estudiante, user, trigger="iniciar_revision"
        )

    session.add(post)
    session.commit()
    log_audit(
        session,
        user_id=user.id,
        action=f"POSTULACION_{estado_origen}_TO_{post.estado}",
        request=request,
        entity_type="postulacion",
        entity_id=None,
        payload={
            "postulacion_id": post.id,
            "convocatoria": conv.codigo,
            "from": estado_origen,
            "to": post.estado,
            "motivo": motivo,
        },
    )
    _flash(
        request,
        "success",
        f"Postulación {post.id}: {estado_origen} → {post.estado}.",
    )
    return RedirectResponse(f"/postulaciones/{post.id}", status_code=303)


@app.post("/postulaciones/{post_id}/nota")
def postulacion_nota(
    request: Request,
    post_id: int,
    nota: str = Form(...),
    user: User = Depends(
        require_role(UserRole.COORDINADOR, UserRole.ADMINISTRADOR)
    ),
    session: Session = Depends(get_session),
):
    post, conv, _est = _load_postulacion_or_404(session, post_id, user)
    nota_limpia = (nota or "").strip()
    if not nota_limpia:
        _flash(request, "warning", "La nota no puede estar vacía.")
        return RedirectResponse(f"/postulaciones/{post.id}", status_code=303)

    historial = list(post.historial_estados or [])
    historial.append(
        {
            "tipo": "nota_coord",
            "by_user_id": str(user.id),
            "by_email": user.email,
            "nota": nota_limpia,
            "at": datetime.utcnow().isoformat(),
        }
    )
    post.historial_estados = historial
    post.updated_at = datetime.utcnow()
    session.add(post)
    session.commit()
    log_audit(
        session,
        user_id=user.id,
        action="POSTULACION_NOTA",
        request=request,
        entity_type="postulacion",
        entity_id=None,
        payload={"postulacion_id": post.id, "convocatoria": conv.codigo},
    )
    _flash(request, "success", "Nota agregada al historial.")
    return RedirectResponse(f"/postulaciones/{post.id}", status_code=303)


# ============================================================
# Adjudicación batch (P06)
# ============================================================


def _load_aprobadas_de_convocatoria(
    session: Session, conv_id: uuid.UUID
) -> list[tuple[Postulacion, User]]:
    rows = session.exec(
        select(Postulacion, User)
        .join(User, Postulacion.estudiante_id == User.id)
        .where(Postulacion.convocatoria_id == conv_id)
        .where(Postulacion.estado == POST_APROBADA)
        .order_by(Postulacion.created_at.asc())
    ).all()
    return [(post, est) for post, est in rows]


@app.get("/convocatorias/{conv_id}/adjudicar")
def convocatorias_adjudicar_get(
    request: Request,
    conv_id: uuid.UUID,
    user: User = Depends(require_role(UserRole.ADMINISTRADOR)),
    session: Session = Depends(get_session),
):
    conv, _creator, _f, _m = _load_convocatoria_or_404(session, conv_id)
    if conv.status != ConvocatoriaStatus.CERRADA:
        _flash(
            request,
            "warning",
            "Cierre la convocatoria primero antes de adjudicar.",
        )
        return RedirectResponse(f"/convocatorias/{conv.id}", status_code=303)

    rows = _load_aprobadas_de_convocatoria(session, conv.id)
    aprobadas = [
        {
            "id": post.id,
            "estudiante_nombre": est.full_name or est.email,
            "estudiante_email": est.email,
            "promedio": post.promedio_acumulado,
            "evaluacion": post.evaluacion_ia_ultima,
        }
        for post, est in rows
    ]
    return templates.TemplateResponse(
        request,
        "convocatorias_adjudicar.html",
        {
            "user": user,
            "convocatoria": conv,
            "aprobadas": aprobadas,
        },
    )


@app.post("/convocatorias/{conv_id}/adjudicar")
def convocatorias_adjudicar_post(
    request: Request,
    conv_id: uuid.UUID,
    seleccionadas: list[int] = Form(default=[]),
    user: User = Depends(require_role(UserRole.ADMINISTRADOR)),
    session: Session = Depends(get_session),
):
    conv, _creator, _f, _m = _load_convocatoria_or_404(session, conv_id)
    rows = _load_aprobadas_de_convocatoria(session, conv.id)
    postulaciones_aprobadas = [post for post, _ in rows]

    try:
        monitores, resumen = adjudicar_convocatoria(
            conv, postulaciones_aprobadas, seleccionadas, user
        )
    except AdjudicacionInvalidaError as e:
        session.rollback()
        _flash(request, "danger", f"No se pudo adjudicar: {e}")
        return RedirectResponse(
            f"/convocatorias/{conv.id}/adjudicar", status_code=303
        )
    except (TransicionInvalidaError, PermisoInsuficienteError) as e:
        session.rollback()
        _flash(request, "danger", f"Error en transición batch: {e}")
        return RedirectResponse(
            f"/convocatorias/{conv.id}/adjudicar", status_code=303
        )

    for post in postulaciones_aprobadas:
        session.add(post)
    for monitor in monitores:
        session.add(monitor)
    session.add(conv)

    try:
        session.commit()
    except Exception as e:
        session.rollback()
        _flash(request, "danger", f"Error al persistir la adjudicación: {e}")
        return RedirectResponse(
            f"/convocatorias/{conv.id}/adjudicar", status_code=303
        )

    log_audit(
        session,
        user_id=user.id,
        action="ADJUDICAR_CONVOCATORIA",
        request=request,
        entity_type="convocatoria",
        entity_id=conv.id,
        payload={
            "codigo": conv.codigo,
            "adjudicadas": resumen["adjudicadas"],
            "no_adjudicadas": resumen["no_adjudicadas"],
            "cupos_libres": resumen["cupos_libres"],
        },
    )
    _flash(
        request,
        "success",
        f"Adjudicación completada: {resumen['adjudicadas']} monitores asignados, "
        f"{resumen['no_adjudicadas']} no adjudicadas.",
    )
    return RedirectResponse(f"/convocatorias/{conv.id}", status_code=303)

