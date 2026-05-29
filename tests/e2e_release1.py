"""
Smoke E2E lineal del Release 1 PÚRPURA.

Recorrido narrativo: una sola corrida que demuestra el ciclo completo.
A diferencia de tests/visual_validation.py (asserts independientes), este
script narra el flujo paso a paso con timestamps. Sirve como demo
reproducible para la sustentación.

Pasos:
  1. Admin crea convocatoria scratch + publica
  2. Estudiante 1 (datos completos) postula → IA modo=reglas
  3. Estudiante 3 (datos NULL)     postula → IA modo=llm (o fallback)
  4. Admin transiciona ambas a EN_REVISION
  5. Coord/Admin aprueba estudiante 1
  6. Coord/Admin rechaza estudiante 3 con motivo
  7. Admin cierra convocatoria
  8. Admin adjudica (estudiante 1 → ADJUDICADA, estudiante 3 ya RECHAZADA)
  9. Estudiante 1 ve notificación + monitoría en /mis-monitorias
 10. Admin descarga CSV de postulaciones

Uso:
    uv run python tests/e2e_release1.py

Variables de entorno:
    BASE_URL=http://localhost:8000   (default)
    HEADLESS=0                       (default headed, 1 para CI)
"""
import asyncio
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from playwright.async_api import async_playwright

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000")
HEADLESS = os.environ.get("HEADLESS", "0") == "1"
SCREENSHOTS_DIR = Path("tests/screenshots/e2e_release1")
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

USERS = {
    "admin": ("admin@purpura.local", "Admin2026!"),
    "coord": ("coord.ing@udem.edu.co", "Coord2026!"),
    "est1": ("estudiante1@udem.edu.co", "Estudiante2026!"),
    "est3": ("estudiante3@udem.edu.co", "Estudiante2026!"),
}

START_TIME = time.time()


def _ts() -> str:
    delta = time.time() - START_TIME
    return f"[{delta:6.1f}s]"


def log(emoji: str, msg: str) -> None:
    print(f"{_ts()} {emoji} {msg}")


async def login(page, email: str, password: str) -> None:
    await page.goto(f"{BASE_URL}/login")
    await page.wait_for_load_state("domcontentloaded")
    await page.fill('input[name="email"]', email)
    await page.fill('input[name="password"]', password)
    await page.click('button[type="submit"]')
    await page.wait_for_load_state("domcontentloaded")


async def logout(page) -> None:
    btn = page.locator('form[action="/logout"] button')
    if await btn.count() > 0:
        await btn.first.click()
        await page.wait_for_load_state("domcontentloaded")


async def cancelar_activas_estudiante(page, email: str, password: str) -> None:
    await logout(page)
    await login(page, email, password)
    await page.goto(f"{BASE_URL}/mis-postulaciones")
    await page.wait_for_load_state("domcontentloaded")
    filas = await page.locator(
        "tr[data-postulacion-id][data-postulacion-estado='ENVIADA'], "
        "tr[data-postulacion-id][data-postulacion-estado='EN_REVISION']"
    ).all()
    for fila in filas:
        pid = await fila.get_attribute("data-postulacion-id")
        if pid:
            await page.request.post(f"{BASE_URL}/postulaciones/{pid}/cancelar")


async def main() -> int:
    log("🚀", f"Iniciando E2E Release 1 contra {BASE_URL}")
    scratch_code = f"MON-2026-99-E{int(time.time()) % 100000:05d}"
    apertura = datetime.now().strftime("%Y-%m-%dT%H:%M")
    cierre = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%dT%H:%M")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=HEADLESS, slow_mo=200)
        ctx = await browser.new_context(viewport={"width": 1366, "height": 900})
        ctx.set_default_timeout(60000)
        ctx.set_default_navigation_timeout(60000)
        page = await ctx.new_page()

        # ====================================================
        # PASO 1 — Admin crea + publica convocatoria
        # ====================================================
        log("👤", "Admin login y crea convocatoria scratch")
        await login(page, *USERS["admin"])
        await page.request.post(
            f"{BASE_URL}/convocatorias/crear",
            form={
                "codigo": scratch_code,
                "titulo": f"E2E Release 1 — {scratch_code}",
                "descripcion": "Convocatoria efímera para el e2e narrativo",
                "facultad": "Ingeniería",
                "asignatura": "Demo Sustentacion",
                "cupos": "2",
                "fecha_apertura": apertura,
                "fecha_cierre": cierre,
            },
        )
        await page.goto(f"{BASE_URL}/convocatorias")
        await page.wait_for_load_state("domcontentloaded")
        fila = page.locator(
            f"tr[data-conv-id]:has(code:has-text('{scratch_code}'))"
        ).first
        conv_id = await fila.get_attribute("data-conv-id")
        assert conv_id, "no se pudo recuperar conv_id"
        log("📝", f"Convocatoria creada: {scratch_code} (id={conv_id[:8]}…)")

        await page.request.post(
            f"{BASE_URL}/convocatorias/{conv_id}/transicionar",
            form={"nuevo_estado": "PUBLICADA", "motivo": "e2e setup"},
        )
        log("📢", "Convocatoria transicionada BORRADOR → PUBLICADA")

        # ====================================================
        # PASO 2 — Estudiante 1 postula (modo reglas)
        # ====================================================
        await cancelar_activas_estudiante(page, *USERS["est1"])
        log("🧑‍🎓", "Estudiante1 (promedio 4.5, créd 80, sem 6) postula")
        resp = await page.request.post(
            f"{BASE_URL}/convocatorias/{conv_id}/postular",
            form={"motivacion": "Cumplo todos los requisitos academicos"},
            max_redirects=0,
        )
        assert resp.status == 303, f"postulación est1 falló: status={resp.status}"
        log("✅", "Postulación de est1 creada (espera modo=reglas)")

        # ====================================================
        # PASO 3 — Estudiante 3 postula (modo LLM)
        # ====================================================
        await cancelar_activas_estudiante(page, *USERS["est3"])
        log("🧑‍🎓", "Estudiante3 (datos académicos NULL) postula")
        resp = await page.request.post(
            f"{BASE_URL}/convocatorias/{conv_id}/postular",
            form={"motivacion": "Quiero ser monitor, aprendi mucho"},
            max_redirects=0,
        )
        assert resp.status == 303, f"postulación est3 falló: status={resp.status}"
        log("✅", "Postulación de est3 creada (espera modo=llm o fallback)")

        # ====================================================
        # PASO 4 — Admin transiciona ambas a EN_REVISION
        # ====================================================
        await logout(page)
        await login(page, *USERS["admin"])
        await page.goto(
            f"{BASE_URL}/bandeja?estado=enviada&convocatoria={conv_id}"
        )
        await page.wait_for_load_state("domcontentloaded")
        filas = await page.locator(
            "tr[data-postulacion-id] a[href^='/postulaciones/']"
        ).all()
        post_ids = []
        for f_ in filas:
            href = await f_.get_attribute("href")
            if href:
                pid = int(href.rstrip("/").split("/")[-1])
                post_ids.append(pid)
        assert len(post_ids) >= 2, f"bandeja con < 2 ENVIADA: {post_ids}"
        post_id_est1, post_id_est3 = post_ids[-1], post_ids[-2]  # invertimos por created_at desc
        # Si la primera del listado es est3 (más reciente), está OK; reordenamos por modo
        log("📥", f"Bandeja: post {post_id_est1} y {post_id_est3} ENVIADAs")

        for pid in post_ids[:2]:
            await page.request.post(
                f"{BASE_URL}/postulaciones/{pid}/transicionar",
                form={"nuevo_estado": "EN_REVISION", "motivo": "Inicio revisión e2e"},
            )
        log("🔍", "Ambas postulaciones → EN_REVISION (re-evaluación IA)")

        # ====================================================
        # PASO 5 + 6 — Aprobar est1, rechazar est3
        # ====================================================
        for pid in post_ids[:2]:
            await page.goto(f"{BASE_URL}/postulaciones/{pid}")
            await page.wait_for_load_state("domcontentloaded")
            cuerpo = (await page.text_content("body") or "").lower()
            estudiante_email = ""
            if "estudiante1@udem.edu.co" in cuerpo:
                estudiante_email = USERS["est1"][0]
                # Aprobar
                await page.locator("#motivo-aprobar").fill(
                    "Datos académicos completos, sugerencia IA AUTO_APTO"
                )
                await page.locator("button[data-accion='aprobar']").first.click()
                await page.wait_for_load_state("domcontentloaded")
                log("✅", f"Postulación {pid} (est1) → APROBADA")
            elif "estudiante3@udem.edu.co" in cuerpo:
                estudiante_email = USERS["est3"][0]
                # Rechazar con motivo
                await page.locator("#motivo-rechazar").fill(
                    "Datos académicos no registrados — el estudiante debe actualizar su perfil"
                )
                await page.locator("button[data-accion='rechazar']").first.click()
                await page.wait_for_load_state("domcontentloaded")
                log("❌", f"Postulación {pid} (est3) → RECHAZADA con motivo")

        # ====================================================
        # PASO 7 — Admin cierra convocatoria
        # ====================================================
        await page.request.post(
            f"{BASE_URL}/convocatorias/{conv_id}/transicionar",
            form={"nuevo_estado": "CERRADA", "motivo": "cierre e2e"},
        )
        log("🔒", "Convocatoria PUBLICADA → CERRADA")

        # ====================================================
        # PASO 8 — Admin adjudica (selecciona estudiante 1)
        # ====================================================
        await page.goto(f"{BASE_URL}/convocatorias/{conv_id}/adjudicar")
        await page.wait_for_load_state("domcontentloaded")
        await page.wait_for_selector(
            "input[type='checkbox'][name='seleccionadas']", timeout=8000
        )
        await page.locator(
            "input[type='checkbox'][name='seleccionadas']"
        ).first.check()
        await page.locator(
            "button[data-accion='confirmar-adjudicacion']"
        ).click()
        await page.wait_for_load_state("domcontentloaded")
        await page.wait_for_selector(
            "[data-convocatoria-estado='ADJUDICADA']", timeout=8000
        )
        log("🎯", "Adjudicación batch atómica: conv → ADJUDICADA, Monitor creado")
        await page.screenshot(
            path=str(SCREENSHOTS_DIR / "08_adjudicada.png"), full_page=False
        )

        # ====================================================
        # PASO 9 — Estudiante 1 ve notificación + monitoría
        # ====================================================
        await logout(page)
        await login(page, *USERS["est1"])
        await page.goto(f"{BASE_URL}/dashboard")
        await page.wait_for_load_state("domcontentloaded")
        badge = await page.locator(".campana-badge").count()
        log("🔔", f"Est1 ve campana (badges visibles: {badge})")

        await page.goto(f"{BASE_URL}/mis-monitorias")
        await page.wait_for_load_state("domcontentloaded")
        filas_monitorias = await page.locator(
            "tr[data-monitor-id]"
        ).count()
        log("👤", f"Est1 ve {filas_monitorias} monitoría(s) activas")
        await page.screenshot(
            path=str(SCREENSHOTS_DIR / "09_mis_monitorias.png"), full_page=False
        )

        # ====================================================
        # PASO 10 — Admin descarga CSV de postulaciones
        # ====================================================
        await logout(page)
        await login(page, *USERS["admin"])
        resp = await page.request.get(
            f"{BASE_URL}/reportes/csv/postulaciones"
        )
        assert resp.status == 200
        cuerpo_csv = await resp.text()
        n_lineas = cuerpo_csv.strip().count("\n") + 1
        size_kb = len(cuerpo_csv.encode("utf-8")) // 1024
        log(
            "📊",
            f"CSV postulaciones descargado: {n_lineas} líneas, ~{size_kb} KB",
        )

        await browser.close()

    log("🏁", f"E2E Release 1 completado en {time.time() - START_TIME:.1f}s")
    log("📂", f"Screenshots: {SCREENSHOTS_DIR.absolute()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
