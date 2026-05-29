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

from app.services.transiciones import (
    PermisoInsuficienteError,
    TransicionInvalidaError,
    transicionar_estado,
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
