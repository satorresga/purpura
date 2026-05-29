"""
Validación visual de identidad gráfica UdeM aplicada en P01.

Uso:
  1. uv run uvicorn app.main:app --reload   (en otra terminal)
  2. uv run python tests/visual_validation.py

Variables de entorno opcionales:
  BASE_URL=http://localhost:8000   (default)
  HEADLESS=0                       (default headed, 1 para CI)
  SLOW_MO=350                      (ms, default 350)
"""
import asyncio
import os
import sys
from pathlib import Path

from playwright.async_api import async_playwright, expect

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
HEADLESS = os.getenv("HEADLESS", "0") == "1"
SLOW_MO = int(os.getenv("SLOW_MO", "350"))

SCREENSHOTS_DIR = Path("tests/screenshots/p01_validation")
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
SCREENSHOTS_LOGO_DIR = Path("tests/screenshots/p01_logo_smoke")
SCREENSHOTS_LOGO_DIR.mkdir(parents=True, exist_ok=True)

# El seed P00 conservó admin@purpura.local del Sprint 1 (no admin@udem.edu.co
# que asumió el prompt). Las otras credenciales coinciden con el seed real.
USERS = {
    "admin":      ("admin@purpura.local",     "Admin2026!"),
    "coord":      ("coord.ing@udem.edu.co",   "Coord2026!"),
    "estudiante": ("estudiante1@udem.edu.co", "Estudiante2026!"),
}

# Paleta UdeM oficial (CSS computado devuelve rgb())
UDEM_RED        = "rgb(194, 38, 43)"    # #C2262B
UDEM_BLUE_DARK  = "rgb(43, 68, 95)"     # #2B445F
UDEM_GOLD_LIGHT = "rgb(234, 186, 61)"   # #EABA3D

results = []


def record(check_id, descripcion, ok, detalle=""):
    status = "[ OK ]" if ok else "[FAIL]"
    line = f"  {status}  {check_id}  {descripcion}"
    if detalle:
        line += f"  | {detalle}"
    print(line)
    results.append((check_id, descripcion, ok, detalle))


async def login(page, email, password):
    await page.goto(f"{BASE_URL}/login")
    await page.fill('input[name="email"]', email)
    await page.fill('input[name="password"]', password)
    await page.click('button[type="submit"]')
    await page.wait_for_load_state("domcontentloaded")


async def logout(page):
    btn = page.locator('form[action="/logout"] button')
    if await btn.count() > 0:
        await btn.first.click()
    else:
        await page.goto(f"{BASE_URL}/logout")
    await page.wait_for_load_state("domcontentloaded")


async def shot(page, name):
    await page.screenshot(path=str(SCREENSHOTS_DIR / f"{name}.png"), full_page=True)


async def computed_style(page, selector, prop):
    return await page.evaluate(
        f"""() => {{
            const el = document.querySelector({selector!r});
            if (!el) return null;
            return getComputedStyle(el).getPropertyValue({prop!r}).trim();
        }}"""
    )


async def main():
    print("\n" + "=" * 72)
    print(" VALIDACIÓN VISUAL P01 — IDENTIDAD GRÁFICA UNIVERSIDAD DE MEDELLÍN")
    print("=" * 72)
    print(f"  BASE_URL: {BASE_URL}")
    print(f"  HEADED:   {not HEADLESS}")
    print(f"  SLOW_MO:  {SLOW_MO}ms")
    print(f"  Screenshots → {SCREENSHOTS_DIR.absolute()}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=HEADLESS, slow_mo=SLOW_MO)
        ctx = await browser.new_context(viewport={"width": 1366, "height": 900})
        ctx.set_default_timeout(60000)
        ctx.set_default_navigation_timeout(60000)
        page = await ctx.new_page()

        # ============================================
        # ESCENARIO 1 — Pantalla de login (sin autenticar)
        # ============================================
        print("\n  Escenario 1 — Login institucional")
        await page.goto(f"{BASE_URL}/login")
        await page.wait_for_load_state("domcontentloaded")
        await shot(page, "01_login")

        try:
            alt = await page.locator(".marca-institucional img").first.get_attribute("alt")
            ok = alt is not None and "Universidad de Medellín" in alt
            record("V01", "Marca 'Universidad de Medellín' en alt del logo",
                   ok, f"alt: {alt}")
        except Exception as e:
            record("V01", "Marca 'Universidad de Medellín' en alt del logo", False, str(e)[:80])

        try:
            count = await page.locator("img[src*='logosimbolo-udem']").count()
            record("V02", "Logosímbolo oficial UdeM presente",
                   count > 0, f"encontrados: {count}")
        except Exception as e:
            record("V02", "Logosímbolo oficial UdeM presente", False, str(e)[:80])

        bc = await computed_style(page, ".login-card", "border-top-color")
        record("V03", "Borde superior rojo en login card",
               bc == UDEM_RED, f"actual: {bc}")

        ff = await computed_style(page, "body", "font-family")
        record("V04", "Tipografía Open Sans en body",
               ff is not None and "Open Sans" in ff, f"actual: {ff}")

        try:
            await expect(page.locator("text=Vigilada MinEducación").first).to_be_visible(timeout=3000)
            record("V05", "Sello 'Vigilada MinEducación' en footer", True)
        except Exception as e:
            record("V05", "Sello 'Vigilada MinEducación' en footer", False, str(e)[:80])

        try:
            await expect(page.locator("text=Ciencia y Libertad").first).to_be_visible(timeout=3000)
            record("V06", "Lema 'Ciencia y Libertad' presente", True)
        except Exception as e:
            record("V06", "Lema 'Ciencia y Libertad' presente", False, str(e)[:80])

        # ============================================
        # ESCENARIO 2 — Dashboard admin
        # ============================================
        print("\n  Escenario 2 — Dashboard administrador")
        await login(page, *USERS["admin"])
        await shot(page, "02_dashboard_admin")

        bb = await computed_style(page, ".udem-navbar", "border-bottom-color")
        record("V07", "Navbar con borde inferior rojo institucional",
               bb == UDEM_RED, f"actual: {bb}")

        try:
            convs    = await page.locator('nav a:has-text("Convocatorias")').count()
            reportes = await page.locator('nav a:has-text("Reportes")').count()
            panel    = await page.locator('nav a:has-text("Panel")').count()
            ok = convs >= 1 and reportes >= 1 and panel >= 1
            record("V08", "Admin ve links Convocatorias/Reportes/Panel",
                   ok, f"C:{convs} R:{reportes} P:{panel}")
        except Exception as e:
            record("V08", "Admin ve links Convocatorias/Reportes/Panel", False, str(e)[:80])

        try:
            rol_text = await page.locator(".rol-badge").first.text_content()
            ok = rol_text and "administrador" in rol_text.lower()
            record("V09", "Badge de rol 'administrador' en navbar",
                   ok, f"texto: {rol_text.strip() if rol_text else None}")
        except Exception as e:
            record("V09", "Badge de rol 'administrador' en navbar", False, str(e)[:80])

        bg = await computed_style(page, ".udem-footer", "background-color")
        record("V10", "Footer con fondo azul oscuro institucional",
               bg == UDEM_BLUE_DARK, f"actual: {bg}")

        # ============================================
        # ESCENARIO 3 — Listado de convocatorias (coord)
        # ============================================
        print("\n  Escenario 3 — Listado convocatorias (coordinador)")
        await logout(page)
        await login(page, *USERS["coord"])
        await page.goto(f"{BASE_URL}/convocatorias")
        await page.wait_for_load_state("domcontentloaded")
        await shot(page, "03_convocatorias_coord")

        thead_bg = await computed_style(page, ".udem-table thead", "background-color")
        record("V11", "Tabla con thead azul oscuro institucional",
               thead_bg == UDEM_BLUE_DARK, f"actual: {thead_bg}")

        try:
            chips = await page.locator(".chip-facultad").count()
            record("V12", "Al menos 5 chips de facultad en listado",
                   chips >= 5, f"chips: {chips}")
        except Exception as e:
            record("V12", "Al menos 5 chips de facultad en listado", False, str(e)[:80])

        try:
            chip_bg = await page.locator(".chip-facultad.fac-ingenierias").first.evaluate(
                "el => getComputedStyle(el).backgroundColor"
            )
            ok = chip_bg == "rgb(112, 143, 81)"  # #708F51
            record("V13", "Chip Ingenierías con verde institucional #708F51",
                   ok, f"actual: {chip_bg}")
        except Exception as e:
            record("V13", "Chip Ingenierías con verde institucional #708F51", False, str(e)[:80])

        try:
            badges = await page.locator(".badge-estado").count()
            record("V14", "Badges de estado presentes en listado",
                   badges >= 5, f"badges: {badges}")
        except Exception as e:
            record("V14", "Badges de estado presentes en listado", False, str(e)[:80])

        # ============================================
        # ESCENARIO 4 — Dashboard y nav estudiante (RBAC visual)
        # ============================================
        print("\n  Escenario 4 — Dashboard estudiante (RBAC visual)")
        await logout(page)
        await login(page, *USERS["estudiante"])
        await shot(page, "04_dashboard_estudiante")

        try:
            reportes = await page.locator('nav a:has-text("Reportes")').count()
            panel    = await page.locator('nav a:has-text("Panel")').count()
            ok = reportes == 0 and panel == 0
            record("V15", "Estudiante NO ve Reportes/Panel (RBAC visual)",
                   ok, f"R:{reportes} P:{panel}")
        except Exception as e:
            record("V15", "Estudiante NO ve Reportes/Panel (RBAC visual)", False, str(e)[:80])

        try:
            ab  = await page.locator('nav a:has-text("Convocatorias")').count()
            mp  = await page.locator('nav a:has-text("Mis postulaciones")').count()
            mm  = await page.locator('nav a:has-text("Mis monitorías")').count()
            ok = ab >= 1 and mp >= 1 and mm >= 1
            record("V16", "Estudiante ve Convocatorias/Mis postulaciones/Mis monitorías",
                   ok, f"C:{ab} MP:{mp} MM:{mm}")
        except Exception as e:
            record("V16", "Estudiante ve Convocatorias/Mis postulaciones/Mis monitorías", False, str(e)[:80])

        try:
            rol_text = await page.locator(".rol-badge").first.text_content()
            ok = rol_text and "estudiante" in rol_text.lower()
            record("V17", "Badge de rol 'estudiante' en navbar",
                   ok, f"texto: {rol_text.strip() if rol_text else None}")
        except Exception as e:
            record("V17", "Badge de rol 'estudiante' en navbar", False, str(e)[:80])

        # ============================================
        # ESCENARIO 5 — Footer y créditos del equipo
        # ============================================
        print("\n  Escenario 5 — Footer institucional")
        try:
            await expect(
                page.locator("text=/Felipe Cano|Sebasti.n Rend.n|Santiago Torres/").first
            ).to_be_visible(timeout=3000)
            record("V18", "Créditos del equipo visibles en footer", True)
        except Exception as e:
            record("V18", "Créditos del equipo visibles en footer", False, str(e)[:80])

        # ============================================
        # ESCENARIO 6 — Logo oficial UdeM en sus 3 contextos
        # ============================================
        print("\n  Escenario 6 — Logo oficial UdeM (login/navbar/footer)")
        await logout(page)
        await page.goto(f"{BASE_URL}/login")
        await page.wait_for_load_state("domcontentloaded")
        try:
            logo = page.locator(".marca-institucional img").first
            await expect(logo).to_be_visible(timeout=5000)
            src = await logo.get_attribute("src") or ""
            box = await logo.bounding_box()
            h = box["height"] if box else 0
            ok = "logosimbolo-udem-color.png" in src and h >= 60
            record("V19", "Login: logo color, height >= 60",
                   ok, f"src={src.rsplit('/', 1)[-1]} h={h:.0f}")
            await page.screenshot(path=str(SCREENSHOTS_LOGO_DIR / "19_login_logo.png"))
        except Exception as e:
            record("V19", "Login: logo color, height >= 60", False, str(e)[:80])

        await login(page, *USERS["admin"])
        try:
            logo = page.locator(".udem-navbar .logosimbolo img").first
            await expect(logo).to_be_visible(timeout=5000)
            src = await logo.get_attribute("src") or ""
            box = await logo.bounding_box()
            h = box["height"] if box else 0
            ok = "logosimbolo-udem-color.png" in src and h >= 40
            record("V20", "Navbar: logo color, height >= 40",
                   ok, f"src={src.rsplit('/', 1)[-1]} h={h:.0f}")
            await page.screenshot(path=str(SCREENSHOTS_LOGO_DIR / "20_navbar_logo.png"))
        except Exception as e:
            record("V20", "Navbar: logo color, height >= 40", False, str(e)[:80])

        try:
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(500)
            logo = page.locator("footer img").first
            await expect(logo).to_be_visible(timeout=5000)
            src = await logo.get_attribute("src") or ""
            box = await logo.bounding_box()
            h = box["height"] if box else 0
            ok = "logosimbolo-udem-blanco.png" in src and h >= 40
            record("V21", "Footer: logo blanco, height >= 40",
                   ok, f"src={src.rsplit('/', 1)[-1]} h={h:.0f}")
            await page.screenshot(path=str(SCREENSHOTS_LOGO_DIR / "21_footer_logo.png"))
        except Exception as e:
            record("V21", "Footer: logo blanco, height >= 40", False, str(e)[:80])

        await browser.close()

    # ============================================
    # RESUMEN
    # ============================================
    total = len(results)
    ok_count = sum(1 for r in results if r[2])
    fail_count = total - ok_count

    print("\n" + "=" * 72)
    print(f"  TOTAL: {total}    PASADOS: {ok_count}    FALLIDOS: {fail_count}")
    print("=" * 72)

    if fail_count > 0:
        print("\n  Fallos detectados:")
        for cid, desc, ok, det in results:
            if not ok:
                print(f"    {cid}  {desc}")
                if det:
                    print(f"          → {det}")
        print(f"\n  Screenshots para revisar: {SCREENSHOTS_DIR.absolute()}")
        print("\n  VEREDICTO: ROJO — corregir antes de pasar a P02.\n")
        sys.exit(1)
    else:
        print(f"\n  Screenshots: {SCREENSHOTS_DIR.absolute()}")
        print("\n  VEREDICTO: VERDE — identidad gráfica UdeM correctamente aplicada.")
        print("              Listo para push a VPS y arrancar P02.\n")
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
