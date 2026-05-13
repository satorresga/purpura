"""
Validación E2E manual del MVP Sprint 1.
Lanza uvicorn, abre Chromium, ejecuta 7 escenarios, reporta resultados.

Uso:
    uv run python -m tests.manual_e2e

Requisitos:
    - Postgres nativo corriendo (servicio postgresql-x64-16).
    - Seed ya ejecutado (8 usuarios + 2 convocatorias).
    - Puerto 8000 libre.
"""

import subprocess
import time
import sys
import socket
from pathlib import Path
from contextlib import contextmanager

from playwright.sync_api import sync_playwright, Page
from sqlmodel import Session, delete

from app.db import engine
from app.models import Convocatoria

BASE_URL = "http://localhost:8000"
SHOTS_DIR = Path(__file__).parent / "screenshots"
SHOTS_DIR.mkdir(exist_ok=True)
SLOW_MO_MS = 400
SERVER_BOOT_TIMEOUT_S = 20

CRED_COORD = ("coord.ing@udem.edu.co", "Coord2026!")
CRED_ESTUDIANTE = ("estudiante1@udem.edu.co", "Estudiante2026!")
TEST_CODIGO = "MON-2026-01-E2E1"

results: list[tuple[str, bool, str]] = []


def shot(page: Page, name: str) -> None:
    page.screenshot(path=str(SHOTS_DIR / f"{name}.png"), full_page=True)


def wait_for_server() -> None:
    """Hace polling hasta que /login responda 200 o se agote el timeout."""
    import urllib.request
    deadline = time.time() + SERVER_BOOT_TIMEOUT_S
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{BASE_URL}/login", timeout=2) as r:
                if r.status == 200:
                    return
        except Exception:
            time.sleep(0.5)
    raise RuntimeError(f"Servidor no respondió en {SERVER_BOOT_TIMEOUT_S}s")


def port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


UVICORN_LOG = SHOTS_DIR.parent / "uvicorn_e2e.log"


@contextmanager
def uvicorn_server():
    if port_in_use(8000):
        raise RuntimeError("Puerto 8000 en uso. Cerra el servidor previo y reintenta.")
    log = open(UVICORN_LOG, "w", encoding="utf-8")
    proc = subprocess.Popen(
        ["uv", "run", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
        stdout=log,
        stderr=subprocess.STDOUT,
        shell=False,
    )
    try:
        wait_for_server()
        yield proc
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.close()


def cleanup_test_data() -> None:
    """Borra la convocatoria de test si quedó de una corrida previa."""
    with Session(engine) as s:
        s.exec(delete(Convocatoria).where(Convocatoria.codigo == TEST_CODIGO))
        s.commit()


def record(name: str, ok: bool, msg: str = "") -> None:
    results.append((name, ok, msg))
    status = "[OK]" if ok else "[FAIL]"
    print(f"  {status} {name}{(' -- ' + msg) if msg else ''}")


def test_01_redirect_login(page: Page) -> None:
    page.goto(f"{BASE_URL}/")
    page.wait_for_url("**/login")
    shot(page, "01_redirect_login")
    record("Test 01 - GET / redirige a /login", "/login" in page.url)


def test_02_login_coordinador(page: Page) -> None:
    email, password = CRED_COORD
    page.fill('input[name="email"]', email)
    page.fill('input[name="password"]', password)
    page.click('form[action="/login"] button[type="submit"]')
    page.wait_for_url("**/dashboard")
    content = page.content()
    shot(page, "02_dashboard_coord")
    checks = [
        ("URL = /dashboard", page.url.endswith("/dashboard")),
        ("Nombre del coordinador visible", "Ana Coordinadora" in content),
        ("Badge rol coordinador", "coordinador" in content.lower()),
        ("Link a crear convocatoria existe", page.locator('a[href="/convocatorias/crear"]').count() > 0),
    ]
    for name, ok in checks:
        record(f"Test 02 - {name}", ok)


def test_03_crear_convocatoria(page: Page) -> None:
    page.click('a[href="/convocatorias/crear"]')
    page.wait_for_url("**/convocatorias/crear")

    from datetime import datetime, timedelta
    ahora = datetime.now()
    f_ap = (ahora + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
    f_ci = (ahora + timedelta(days=15)).strftime("%Y-%m-%dT%H:%M")

    page.fill('input[name="codigo"]', TEST_CODIGO)
    page.fill('input[name="titulo"]', "Convocatoria E2E Test")
    page.select_option('select[name="facultad"]', label="Ingeniería")
    page.fill('input[name="asignatura"]', "Test Asignatura E2E")
    page.fill('textarea[name="descripcion"]', "Generada por Playwright")
    page.fill('input[name="cupos"]', "2")
    page.fill('input[name="fecha_apertura"]', f_ap)
    page.fill('input[name="fecha_cierre"]', f_ci)
    page.fill('input[name="promedio_minimo"]', "3.5")
    page.fill('input[name="creditos_minimos"]', "40")
    page.fill('input[name="semestre_minimo"]', "3")

    page.click('form[action="/convocatorias/crear"] button[type="submit"]')
    try:
        page.wait_for_url("**/convocatorias", timeout=10000)
    except Exception:
        shot(page, "03_submit_failed")
        record(
            "Test 03 - Crear convocatoria redirige a /convocatorias",
            False,
            f"URL actual: {page.url}",
        )
        return
    shot(page, "03_convocatoria_creada")
    content = page.content()
    record("Test 03 - Crear convocatoria redirige a /convocatorias", page.url.endswith("/convocatorias"))
    record("Test 03 - Codigo TEST aparece en listado", TEST_CODIGO in content)
    record("Test 03 - Status 'borrador' visible", "borrador" in content.lower())


def test_04_listado(page: Page) -> None:
    page.goto(f"{BASE_URL}/convocatorias")
    filas = page.locator("table tbody tr").count()
    shot(page, "04_listado_convocatorias")
    record(f"Test 04 - Listado tiene >=3 filas (vio {filas})", filas >= 3)


def test_05_logout(page: Page) -> None:
    page.locator('form[action="/logout"] button').click()
    page.wait_for_url("**/login")
    shot(page, "05_logout")
    record("Test 05 - Logout redirige a /login", page.url.endswith("/login"))


def test_06_login_estudiante(page: Page) -> None:
    email, password = CRED_ESTUDIANTE
    page.fill('input[name="email"]', email)
    page.fill('input[name="password"]', password)
    page.click('form[action="/login"] button[type="submit"]')
    page.wait_for_url("**/dashboard")
    shot(page, "06_dashboard_estudiante")
    link_crear = page.locator('a[href="/convocatorias/crear"]').count()
    record("Test 06 - Estudiante NO ve link 'Crear convocatoria'", link_crear == 0)


def test_07_rbac_directo(page: Page) -> None:
    response = page.goto(f"{BASE_URL}/convocatorias/crear")
    shot(page, "07_estudiante_403")
    status = response.status if response else 0
    content = page.content().lower()
    record(f"Test 07 - Status 403 al acceder directo (vio {status})", status == 403)
    record("Test 07 - Pagina muestra mensaje de permisos", "permiso" in content or "denegado" in content)


def main() -> int:
    print("=" * 60)
    print("Validacion E2E - MVP Sprint 1 Proyecto PURPURA")
    print("=" * 60)

    cleanup_test_data()

    with uvicorn_server():
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False, slow_mo=SLOW_MO_MS)
            ctx = browser.new_context(viewport={"width": 1280, "height": 800})
            page = ctx.new_page()

            try:
                test_01_redirect_login(page)
                test_02_login_coordinador(page)
                test_03_crear_convocatoria(page)
                test_04_listado(page)
                test_05_logout(page)
                test_06_login_estudiante(page)
                test_07_rbac_directo(page)
            except Exception as e:
                record("EXCEPCION inesperada", False, str(e))
                page.screenshot(path=str(SHOTS_DIR / "ZZ_exception.png"), full_page=True)
            finally:
                ctx.close()
                browser.close()

    cleanup_test_data()

    print()
    print("=" * 60)
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    print(f"Resumen: {passed}/{total} checks OK")
    print(f"Screenshots: {SHOTS_DIR}")
    print("=" * 60)
    if passed != total:
        print()
        print("FALLOS:")
        for name, ok, msg in results:
            if not ok:
                print(f"  [FAIL] {name}{(' -- ' + msg) if msg else ''}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
