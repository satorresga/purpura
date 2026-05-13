import uuid
from typing import Optional

import bcrypt
from fastapi import Depends, HTTPException, Request
from sqlmodel import Session, select

from app.db import get_session
from app.models import AuditLog, User, UserRole


def hash_password(plain: str) -> str:
    """Hash bcrypt del password. Trunca a 72 bytes (límite del algoritmo)."""
    password_bytes = plain.encode("utf-8")[:72]
    hashed = bcrypt.hashpw(password_bytes, bcrypt.gensalt(rounds=12))
    return hashed.decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Verifica password contra hash bcrypt. Truncado al mismo límite."""
    try:
        password_bytes = plain.encode("utf-8")[:72]
        return bcrypt.checkpw(password_bytes, hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def get_current_user(
    request: Request,
    session: Session = Depends(get_session),
) -> Optional[User]:
    user_id_raw = request.session.get("user_id")
    if not user_id_raw:
        return None
    try:
        user_id = uuid.UUID(user_id_raw)
    except (ValueError, TypeError):
        request.session.clear()
        return None
    user = session.exec(select(User).where(User.id == user_id)).first()
    if user is None or not user.is_active:
        request.session.clear()
        return None
    return user


def require_login(user: Optional[User] = Depends(get_current_user)) -> User:
    if user is None:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    return user


def require_role(*allowed: UserRole):
    def _dep(user: User = Depends(require_login)) -> User:
        if user.role not in allowed:
            raise HTTPException(
                status_code=403,
                detail="No tienes permisos para esta acción",
            )
        return user

    return _dep


def log_audit(
    session: Session,
    *,
    user_id: Optional[uuid.UUID],
    action: str,
    request: Request,
    entity_type: Optional[str] = None,
    entity_id: Optional[uuid.UUID] = None,
    payload: Optional[dict] = None,
) -> None:
    ip = request.client.host if request.client else None
    entry = AuditLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=payload,
        ip_address=ip,
    )
    session.add(entry)
    session.commit()
