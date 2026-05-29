"""
Helper fault-tolerant para crear notificaciones.

Si la inserción falla por cualquier razón, log warning y devuelve None.
Nunca lanza al caller: las notificaciones son secundarias al flujo
principal (transición de estado, adjudicación, etc.) y NO deben
romperlo.
"""
import logging
import uuid
from typing import Optional

from sqlmodel import Session

from app.models import Notificacion

LOGGER = logging.getLogger(__name__)


def crear_notificacion(
    session: Session,
    usuario_id: uuid.UUID,
    titulo: str,
    cuerpo: str,
    url_destino: Optional[str] = None,
) -> Optional[Notificacion]:
    """Inserta una notificación. NO hace commit — el caller lo hace.

    Devuelve la Notificacion creada o None si algo falló.
    Limita titulo a 255 y cuerpo es text libre.
    """
    try:
        notif = Notificacion(
            usuario_id=usuario_id,
            titulo=(titulo or "")[:255],
            cuerpo=cuerpo or "",
            url_destino=(url_destino or None) and url_destino[:512],
            leida=False,
        )
        session.add(notif)
        return notif
    except Exception as exc:
        LOGGER.warning(
            "No se pudo crear notificación para %s: %s", usuario_id, exc
        )
        return None
