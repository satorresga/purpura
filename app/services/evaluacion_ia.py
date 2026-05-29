"""
Evaluación automática híbrida de postulaciones.

Estrategia:
1. Si los datos del estudiante son suficientes para aplicar reglas
   determinísticas → decide AUTO_APTO / AUTO_NO_APTO.
2. Si los datos son insuficientes → invoca Claude Haiku con prompt
   estructurado y persiste la sugerencia.
3. Si la API falla (timeout, rate limit, key faltante, etc.) → fallback
   REVISAR_MANUAL sin levantar excepción al caller.

La función es PURA: recibe objetos, retorna dict, no toca DB. El router
es responsable de persistir el resultado en Postulacion.evaluacion_ia_ultima
y en historial_estados.

Constraint ético: el output se llama `decision_sugerida`, nunca `decision`.
El coordinador / administrador es quien decide. Esta capa es asesoría.
"""
import json
import logging
import os
import re
from datetime import datetime
from typing import Any, Optional

LOGGER = logging.getLogger(__name__)

ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"
_TIMEOUT_SEC = 10
_MAX_TOKENS = 300
_TEMPERATURE = 0.2

_PROMPT_SISTEMA = (
    "Eres un asistente de validación académica del programa de monitorías "
    "de la Universidad de Medellín. Recibes datos de una postulación a una "
    "convocatoria y debes sugerir si el estudiante es APTO, NO_APTO, o si "
    "requiere REVISAR_MANUAL.\n\n"
    "Reglas:\n"
    "- Si el estudiante claramente cumple los requisitos publicados → APTO.\n"
    "- Si claramente no los cumple → NO_APTO.\n"
    "- Si los datos son insuficientes o ambiguos → REVISAR_MANUAL.\n"
    "- Nunca decides 'aprobar' o 'rechazar' — solo sugieres. El coordinador "
    "toma la decisión final.\n\n"
    "Responde ÚNICAMENTE con JSON válido, sin markdown ni texto extra:\n"
    '{"decision": "APTO" | "NO_APTO" | "REVISAR_MANUAL", '
    '"confianza": 0.0-1.0, '
    '"justificacion": "explicación breve en español, máx 200 caracteres"}'
)


def _utcnow_iso() -> str:
    return datetime.utcnow().isoformat()


def _aplicar_reglas(postulacion, convocatoria) -> tuple[bool, list[dict]]:
    """Retorna (datos_suficientes_para_decidir, checks).

    Solo aplica reglas cuando la convocatoria publica `promedio_minimo`
    y el estudiante reportó `promedio_acumulado > 0`. Los créditos y
    semestre no están disponibles en el modelo User → se delegan al LLM.
    """
    checks: list[dict] = []
    requisitos = convocatoria.requisitos or {}

    promedio_minimo = requisitos.get("promedio_minimo")
    promedio_actual = postulacion.promedio_acumulado or 0.0

    if promedio_minimo is None or promedio_actual <= 0:
        return False, checks

    try:
        minimo = float(promedio_minimo)
    except (TypeError, ValueError):
        return False, checks

    checks.append(
        {
            "regla": "promedio_minimo",
            "esperado": f">= {minimo:.1f}",
            "actual": round(float(promedio_actual), 2),
            "ok": float(promedio_actual) >= minimo,
        }
    )
    return True, checks


def _resumen_reglas(checks: list[dict]) -> str:
    fallidos = [c for c in checks if not c["ok"]]
    if not fallidos:
        return "Cumple los requisitos automáticos: " + ", ".join(
            f"{c['regla']} {c['actual']} {c['esperado']}" for c in checks
        ) + "."
    return "No cumple: " + "; ".join(
        f"{c['regla']} actual {c['actual']} vs esperado {c['esperado']}"
        for c in fallidos
    ) + "."


def _construir_user_message(postulacion, convocatoria, estudiante) -> str:
    facultad_nombre = "no especificada"
    materia_nombre = "no especificada"
    if getattr(convocatoria, "asignatura", None):
        materia_nombre = convocatoria.asignatura
    if getattr(convocatoria, "facultad", None):
        facultad_nombre = convocatoria.facultad

    return (
        f"Convocatoria: {convocatoria.titulo}\n"
        f"Código: {convocatoria.codigo}\n"
        f"Facultad: {facultad_nombre}\n"
        f"Asignatura/materia: {materia_nombre}\n"
        f"Requisitos publicados:\n"
        f"{json.dumps(convocatoria.requisitos or {}, indent=2, ensure_ascii=False)}\n\n"
        f"Estudiante:\n"
        f"- Email: {estudiante.email}\n"
        f"- Nombre: {estudiante.full_name or 'no especificado'}\n"
        f"- Promedio acumulado declarado: "
        f"{postulacion.promedio_acumulado if postulacion.promedio_acumulado else 'no registrado'}\n"
        f"- Créditos aprobados: no disponible en el sistema\n"
        f"- Semestre actual: no disponible en el sistema\n\n"
        f"Motivación del estudiante:\n{postulacion.motivacion or 'no proporcionada'}\n\n"
        "Evalúa según las reglas y responde JSON."
    )


def _parsear_json_defensivo(texto: str) -> dict[str, Any]:
    """Intenta parsear JSON. Si viene con markdown fences o texto extra,
    extrae el primer bloque que parezca JSON."""
    if not texto:
        return {}
    texto = texto.strip()
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[^{}]*\}", texto, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}
    return {}


_DECISION_LLM_A_INTERNA = {
    "APTO": "AUTO_APTO",
    "NO_APTO": "AUTO_NO_APTO",
    "REVISAR_MANUAL": "REVISAR_MANUAL",
}


def _invocar_haiku(postulacion, convocatoria, estudiante) -> dict[str, Any]:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY no configurada")

    from anthropic import Anthropic

    client = Anthropic(api_key=api_key, timeout=_TIMEOUT_SEC)
    user_message = _construir_user_message(postulacion, convocatoria, estudiante)

    resp = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=_MAX_TOKENS,
        temperature=_TEMPERATURE,
        system=_PROMPT_SISTEMA,
        messages=[{"role": "user", "content": user_message}],
    )

    texto_resp = ""
    if resp.content:
        primer = resp.content[0]
        texto_resp = getattr(primer, "text", "") or ""
    parsed = _parsear_json_defensivo(texto_resp)

    decision_llm = parsed.get("decision", "REVISAR_MANUAL")
    if not isinstance(decision_llm, str):
        decision_llm = "REVISAR_MANUAL"
    decision_sugerida = _DECISION_LLM_A_INTERNA.get(
        decision_llm.upper(), "REVISAR_MANUAL"
    )

    confianza_raw = parsed.get("confianza", 0.5)
    try:
        confianza = max(0.0, min(1.0, float(confianza_raw)))
    except (TypeError, ValueError):
        confianza = 0.5

    justificacion = parsed.get("justificacion") or "(sin justificación)"
    if not isinstance(justificacion, str):
        justificacion = str(justificacion)
    justificacion = justificacion[:300]

    tokens_in = 0
    tokens_out = 0
    if getattr(resp, "usage", None):
        tokens_in = getattr(resp.usage, "input_tokens", 0) or 0
        tokens_out = getattr(resp.usage, "output_tokens", 0) or 0

    return {
        "decision_sugerida": decision_sugerida,
        "confianza": confianza,
        "modo": "llm",
        "justificacion": justificacion,
        "checks": [],
        "modelo": ANTHROPIC_MODEL,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
    }


def evaluar_postulacion(
    postulacion, convocatoria, estudiante
) -> dict[str, Any]:
    """Evalúa una postulación y retorna un dict serializable.

    Nunca lanza excepción al caller: si todo falla, retorna fallback
    con decision_sugerida='REVISAR_MANUAL'.
    """
    base = {"evaluado_at": _utcnow_iso()}

    try:
        suficientes, checks = _aplicar_reglas(postulacion, convocatoria)
    except Exception as exc:  # defensivo total
        LOGGER.warning("Falla aplicando reglas: %s", exc)
        suficientes, checks = False, []

    if suficientes:
        todos_ok = all(c["ok"] for c in checks)
        return {
            **base,
            "decision_sugerida": "AUTO_APTO" if todos_ok else "AUTO_NO_APTO",
            "confianza": 1.0,
            "modo": "reglas",
            "justificacion": _resumen_reglas(checks),
            "checks": checks,
            "modelo": "reglas-v1",
        }

    try:
        llm_result = _invocar_haiku(postulacion, convocatoria, estudiante)
        return {**base, **llm_result}
    except Exception as exc:
        LOGGER.warning(
            "Evaluación IA cae en fallback por %s: %s",
            type(exc).__name__,
            exc,
        )
        return {
            **base,
            "decision_sugerida": "REVISAR_MANUAL",
            "confianza": 0.0,
            "modo": "fallback",
            "justificacion": (
                f"Evaluación automática no disponible "
                f"({type(exc).__name__}). Se requiere revisión manual."
            ),
            "checks": [],
            "modelo": "fallback",
        }


def get_ultima_evaluacion(postulacion) -> Optional[dict[str, Any]]:
    """Recupera la evaluación más reciente, priorizando el campo dedicado.

    Si el campo `evaluacion_ia_ultima` está poblado, lo retorna directo.
    Sino, escanea `historial_estados` buscando el último evento
    tipo='evaluacion_ia'.
    """
    directo = getattr(postulacion, "evaluacion_ia_ultima", None)
    if directo:
        return directo
    historial = postulacion.historial_estados or []
    for evento in reversed(historial):
        if isinstance(evento, dict) and evento.get("tipo") == "evaluacion_ia":
            return {k: v for k, v in evento.items() if k != "tipo"}
    return None
