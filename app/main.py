import re
from datetime import datetime
from typing import Optional

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select
from starlette.middleware.sessions import SessionMiddleware

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
from app.models import Convocatoria, ConvocatoriaStatus, User, UserRole

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
def root(user: Optional[User] = Depends(get_current_user)):
    if user is not None:
        return RedirectResponse("/dashboard", status_code=303)
    return RedirectResponse("/login", status_code=303)


@app.get("/login")
def login_get(
    request: Request,
    user: Optional[User] = Depends(get_current_user),
):
    if user is not None:
        return RedirectResponse("/dashboard", status_code=303)
    return templates.TemplateResponse(
        request,
        "login.html",
        {"user": None, "error": None},
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
    rows = session.exec(
        select(Convocatoria, User).join(
            User, Convocatoria.created_by == User.id
        )
    ).all()
    convocatorias = [
        {
            "id": conv.id,
            "codigo": conv.codigo,
            "titulo": conv.titulo,
            "facultad": conv.facultad,
            "asignatura": conv.asignatura,
            "cupos": conv.cupos,
            "fecha_apertura": conv.fecha_apertura,
            "fecha_cierre": conv.fecha_cierre,
            "status": conv.status,
            "created_by_full_name": creator.full_name,
        }
        for conv, creator in rows
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
