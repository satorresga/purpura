import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Column, Field, SQLModel


class UserRole(str, enum.Enum):
    ADMINISTRADOR = "administrador"
    COORDINADOR = "coordinador"
    DOCENTE = "docente"
    ESTUDIANTE = "estudiante"


class ConvocatoriaStatus(str, enum.Enum):
    BORRADOR = "borrador"
    PUBLICADA = "publicada"
    CERRADA = "cerrada"
    ARCHIVADA = "archivada"


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    email: str = Field(unique=True, index=True, max_length=255)
    password_hash: str = Field(max_length=255)
    full_name: str = Field(max_length=255)
    role: UserRole = Field(index=True)
    is_active: bool = Field(default=True)
    last_login_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Convocatoria(SQLModel, table=True):
    __tablename__ = "convocatorias"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    codigo: str = Field(unique=True, index=True, max_length=50)
    titulo: str = Field(max_length=255)
    descripcion: Optional[str] = None
    facultad: str = Field(max_length=255)
    asignatura: str = Field(max_length=255)
    cupos: int
    fecha_apertura: datetime
    fecha_cierre: datetime
    requisitos: dict = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default="{}"),
    )
    status: ConvocatoriaStatus = Field(
        default=ConvocatoriaStatus.BORRADOR, index=True
    )
    created_by: uuid.UUID = Field(foreign_key="users.id", index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class AuditLog(SQLModel, table=True):
    __tablename__ = "audit_log"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[uuid.UUID] = Field(default=None, index=True)
    action: str = Field(max_length=100, index=True)
    entity_type: Optional[str] = Field(default=None, max_length=100)
    entity_id: Optional[uuid.UUID] = None
    payload: Optional[dict] = Field(default=None, sa_column=Column(JSONB))
    ip_address: Optional[str] = Field(default=None, max_length=64)
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
