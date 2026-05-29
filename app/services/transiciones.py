"""
Máquina de estados de Convocatoria.

Mapa de transiciones permitidas y función pura `transicionar_estado(...)`.
NO hace commit. El caller (router) es responsable de persistir y manejar
mensajes flash.
"""
from datetime import datetime
from typing import Tuple

from app.models import Convocatoria, ConvocatoriaStatus, User, UserRole


class TransicionInvalidaError(Exception):
    """La transición entre estados no está permitida por el mapa."""


class PermisoInsuficienteError(Exception):
    """El usuario no tiene rol u ownership para realizar la transición."""


_ADMIN_AND_COORD_OWNER: Tuple[str, ...] = ("admin", "coord_owner")
_ADMIN_ONLY: Tuple[str, ...] = ("admin",)

TRANSICIONES: dict[
    Tuple[ConvocatoriaStatus, ConvocatoriaStatus], Tuple[str, ...]
] = {
    (ConvocatoriaStatus.BORRADOR,   ConvocatoriaStatus.PUBLICADA):   _ADMIN_AND_COORD_OWNER,
    (ConvocatoriaStatus.BORRADOR,   ConvocatoriaStatus.ARCHIVADA):   _ADMIN_AND_COORD_OWNER,
    (ConvocatoriaStatus.PUBLICADA,  ConvocatoriaStatus.CERRADA):     _ADMIN_AND_COORD_OWNER,
    (ConvocatoriaStatus.PUBLICADA,  ConvocatoriaStatus.BORRADOR):    _ADMIN_ONLY,
    (ConvocatoriaStatus.CERRADA,    ConvocatoriaStatus.ADJUDICADA):  _ADMIN_AND_COORD_OWNER,
    (ConvocatoriaStatus.CERRADA,    ConvocatoriaStatus.PUBLICADA):   _ADMIN_ONLY,
    (ConvocatoriaStatus.ADJUDICADA, ConvocatoriaStatus.ARCHIVADA):   _ADMIN_AND_COORD_OWNER,
}


def transiciones_disponibles(
    conv: Convocatoria, usuario: User
) -> list[ConvocatoriaStatus]:
    """Lista los estados a los que ``usuario`` puede llevar ``conv``.

    Útil para renderizar botones de transición contextuales en la UI.
    """
    resultado: list[ConvocatoriaStatus] = []
    for (origen, destino), perfiles in TRANSICIONES.items():
        if origen != conv.status:
            continue
        if _puede(usuario, perfiles, conv):
            resultado.append(destino)
    return resultado


def transicionar_estado(
    conv: Convocatoria,
    nuevo_estado: ConvocatoriaStatus,
    usuario: User,
    motivo: str = "",
) -> Convocatoria:
    """Valida + muta el estado de ``conv``. No persiste.

    Levanta:
        TransicionInvalidaError: si (estado_actual, nuevo_estado) no está
            en TRANSICIONES.
        PermisoInsuficienteError: si el rol u ownership no autorizan la
            transición.
    """
    key = (conv.status, nuevo_estado)
    if key not in TRANSICIONES:
        raise TransicionInvalidaError(
            f"Transición {conv.status.value} → {nuevo_estado.value} no permitida"
        )
    if not _puede(usuario, TRANSICIONES[key], conv):
        raise PermisoInsuficienteError(
            f"Usuario {usuario.email} no puede transicionar de "
            f"{conv.status.value} a {nuevo_estado.value}"
        )

    historial = list(conv.historial_estados or [])
    historial.append(
        {
            "from": conv.status.value,
            "to": nuevo_estado.value,
            "by_user_id": str(usuario.id),
            "by_email": usuario.email,
            "motivo": motivo,
            "at": datetime.utcnow().isoformat(),
        }
    )
    conv.historial_estados = historial
    conv.status = nuevo_estado
    conv.updated_at = datetime.utcnow()
    return conv


def _puede(usuario: User, perfiles: Tuple[str, ...], conv: Convocatoria) -> bool:
    if usuario.role == UserRole.ADMINISTRADOR:
        return True
    if usuario.role == UserRole.COORDINADOR:
        return "coord_owner" in perfiles and conv.created_by == usuario.id
    return False
