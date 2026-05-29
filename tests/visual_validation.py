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
import re
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
SCREENSHOTS_LANDING_DIR = Path("tests/screenshots/p015b_smoke")
SCREENSHOTS_LANDING_DIR.mkdir(parents=True, exist_ok=True)

# El seed P00 conservó admin@purpura.local del Sprint 1 (no admin@udem.edu.co
# que asumió el prompt). Las otras credenciales coinciden con el seed real.
USERS = {
    "admin":      ("admin@purpura.local",     "Admin2026!"),
    "coord":      ("coord.ing@udem.edu.co",   "Coord2026!"),
    "estudiante": ("estudiante1@udem.edu.co", "Estudiante2026!"),
}

# Paleta Figma del equipo PÚRPURA (CSS computado devuelve rgb())
UDEM_RED    = "rgb(200, 32, 45)"   # #C8202D
UDEM_BLACK  = "rgb(26, 26, 26)"    # #1A1A1A (footer)
UDEM_BLUE   = "rgb(43, 82, 120)"   # #2B5278 (table thead)
UDEM_BORDER = "rgb(229, 227, 221)" # #E5E3DD (navbar bottom)

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
            alt = await page.locator("header .logosimbolo img").first.get_attribute("alt")
            ok = alt is not None and "Universidad de Medellín" in alt
            record("V01", "Marca 'Universidad de Medellín' en alt del logo navbar",
                   ok, f"alt: {alt}")
        except Exception as e:
            record("V01", "Marca 'Universidad de Medellín' en alt del logo navbar",
                   False, str(e)[:80])

        try:
            count = await page.locator("img[src*='logosimbolo-udem']").count()
            record("V02", "Logosímbolo oficial UdeM presente",
                   count > 0, f"encontrados: {count}")
        except Exception as e:
            record("V02", "Logosímbolo oficial UdeM presente", False, str(e)[:80])

        bc = await computed_style(page, ".role-tabs-label", "background-color")
        record("V03", "Card login con franja roja Figma (label tabs)",
               bc == UDEM_RED, f"actual: {bc}")

        ff = await computed_style(page, "body", "font-family")
        record("V04", "Tipografía Roboto en body (Figma)",
               ff is not None and "Roboto" in ff, f"actual: {ff}")

        try:
            await expect(page.locator("text=Vigilada MinEducación").first).to_be_visible(timeout=3000)
            record("V05", "Sello 'Vigilada MinEducación' en footer", True)
        except Exception as e:
            record("V05", "Sello 'Vigilada MinEducación' en footer", False, str(e)[:80])

        try:
            alt = await page.locator("header .logosimbolo img").first.get_attribute("alt")
            ok = alt is not None and "Ciencia y Libertad" in alt
            record("V06", "Lema 'Ciencia y Libertad' en alt del logo navbar",
                   ok, f"alt: {alt}")
        except Exception as e:
            record("V06", "Lema 'Ciencia y Libertad' en alt del logo navbar",
                   False, str(e)[:80])

        # ============================================
        # ESCENARIO 2 — Dashboard admin
        # ============================================
        print("\n  Escenario 2 — Dashboard administrador")
        await login(page, *USERS["admin"])
        await shot(page, "02_dashboard_admin")

        bb = await computed_style(page, ".udem-navbar", "border-bottom-color")
        record("V07", "Navbar con borde inferior gris claro (Figma fino)",
               bb == UDEM_BORDER, f"actual: {bb}")

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
        record("V10", "Footer con fondo negro institucional (Figma)",
               bg == UDEM_BLACK, f"actual: {bg}")

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
        record("V11", "Tabla con thead azul Figma",
               thead_bg == UDEM_BLUE, f"actual: {thead_bg}")

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
            logo = page.locator("header .logosimbolo img").first
            await expect(logo).to_be_visible(timeout=5000)
            src = await logo.get_attribute("src") or ""
            box = await logo.bounding_box()
            h = box["height"] if box else 0
            ok = "logosimbolo-udem-color.png" in src and h >= 40
            record("V19", "Pantalla login: logo color en navbar, height >= 40",
                   ok, f"src={src.rsplit('/', 1)[-1]} h={h:.0f}")
            await page.screenshot(path=str(SCREENSHOTS_LOGO_DIR / "19_login_logo.png"))
        except Exception as e:
            record("V19", "Pantalla login: logo color en navbar, height >= 40",
                   False, str(e)[:80])

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

        # ============================================
        # ESCENARIO 7 — Landing pública + login con tabs (P01.5b)
        # ============================================
        print("\n  Escenario 7 — Landing pública + login con tabs")
        await ctx.clear_cookies()
        await page.goto(f"{BASE_URL}/")
        await page.wait_for_load_state("domcontentloaded")
        try:
            await page.wait_for_selector(".landing-hero", timeout=10000)
            h1_text = await page.locator(".landing-hero h1").first.text_content()
            ok = h1_text and "Monitorías académicas" in h1_text
            record("V22", "Landing: hero con título 'Monitorías académicas'",
                   ok, f"h1: {h1_text.strip() if h1_text else None}")
            await page.screenshot(
                path=str(SCREENSHOTS_LANDING_DIR / "22_landing_hero.png"),
                full_page=True,
            )
        except Exception as e:
            record("V22", "Landing: hero con título 'Monitorías académicas'",
                   False, str(e)[:80])

        try:
            bg_image = await page.locator(".landing-hero").first.evaluate(
                "el => getComputedStyle(el).backgroundImage"
            )
            ok = bg_image is not None and "200, 32, 45" in bg_image
            record("V23", "Landing: hero con gradient rojo Figma",
                   ok, f"bg: {(bg_image or '')[:70]}")
        except Exception as e:
            record("V23", "Landing: hero con gradient rojo Figma",
                   False, str(e)[:80])

        try:
            stats = await page.locator(".stat").count()
            record("V24", "Landing: 4 stats (72/60K+/7/ACREDITADA)",
                   stats == 4, f"stats: {stats}")
        except Exception as e:
            record("V24", "Landing: 4 stats (72/60K+/7/ACREDITADA)",
                   False, str(e)[:80])

        try:
            perfiles = await page.locator(".perfil").count()
            record("V25", "Landing: 3 perfiles de comunidad",
                   perfiles == 3, f"perfiles: {perfiles}")
        except Exception as e:
            record("V25", "Landing: 3 perfiles de comunidad",
                   False, str(e)[:80])

        try:
            seccion = page.locator("#convocatorias").first
            visible = await seccion.is_visible()
            record("V26", "Landing: sección #convocatorias visible",
                   visible, f"visible={visible}")
        except Exception as e:
            record("V26", "Landing: sección #convocatorias visible",
                   False, str(e)[:80])

        try:
            await page.goto(f"{BASE_URL}/login")
            await page.wait_for_load_state("domcontentloaded")
            await page.wait_for_selector(".role-tab[data-rol='coordinador']", timeout=8000)
            await page.click(".role-tab[data-rol='coordinador']")
            await page.wait_for_timeout(400)
            tab_coord = page.locator(".role-tab[data-rol='coordinador']").first
            bg_coord = await tab_coord.evaluate(
                "el => getComputedStyle(el).backgroundColor"
            )
            ok = bg_coord == "rgb(200, 32, 45)"
            record("V27", "Login: tab coordinador activo rojo Figma",
                   ok, f"bg: {bg_coord}")
            await page.screenshot(
                path=str(SCREENSHOTS_LANDING_DIR / "27_login_tabs.png"),
                full_page=False,
            )
        except Exception as e:
            record("V27", "Login: tab coordinador activo rojo Figma",
                   False, str(e)[:80])

        # ============================================
        # ESCENARIO 8 — Documentación pública (P01.5c)
        # ============================================
        print("\n  Escenario 8 — Documentación pública")
        await page.goto(f"{BASE_URL}/documentacion")
        await page.wait_for_load_state("domcontentloaded")
        try:
            await page.wait_for_selector(".doc-hero", timeout=10000)
            h1_text = await page.locator(".doc-hero h1").first.text_content()
            cards = await page.locator(".doc-card").count()
            ok = h1_text and "Documentación" in h1_text and cards == 6
            record("V28", "Documentación: hero + 6 cards",
                   ok, f"h1='{(h1_text or '').strip()}' cards={cards}")
            await page.screenshot(
                path=str(SCREENSHOTS_LANDING_DIR / "28_documentacion.png"),
                full_page=True,
            )
        except Exception as e:
            record("V28", "Documentación: hero + 6 cards", False, str(e)[:80])

        await ctx.clear_cookies()
        await page.goto(f"{BASE_URL}/")
        await page.wait_for_load_state("domcontentloaded")
        try:
            await page.wait_for_selector(".navbar-links", timeout=8000)
            doc_link = page.locator(".navbar-links a[href='/documentacion']").first
            visible = await doc_link.is_visible()
            record("V29", "Navbar global: link Documentación visible sin sesión",
                   visible, f"visible={visible}")
        except Exception as e:
            record("V29", "Navbar global: link Documentación visible sin sesión",
                   False, str(e)[:80])

        # ============================================
        # ESCENARIO 9 — CRUD + transiciones de convocatorias (P02)
        # ============================================
        print("\n  Escenario 9 — CRUD + transiciones (P02)")
        await ctx.clear_cookies()
        await login(page, *USERS["admin"])
        await page.goto(f"{BASE_URL}/convocatorias")
        await page.wait_for_load_state("domcontentloaded")
        href_detalle = None
        href_borrador = None
        try:
            await page.wait_for_selector("tr[data-conv-id]", timeout=8000)
            primera = page.locator(
                "tr[data-conv-id] a[href^='/convocatorias/']:not([href*='editar']):not([href*='archiv'])"
            ).first
            href_detalle = await primera.get_attribute("href")
            await primera.click()
            await page.wait_for_load_state("domcontentloaded")
            await page.wait_for_selector("h1", timeout=8000)
            botones = await page.locator("button.btn-transicion").count()
            ok = (
                href_detalle
                and re.match(r"^/convocatorias/[a-f0-9-]+$", href_detalle)
                and botones >= 1
            )
            record(
                "V30",
                "Admin: detalle convocatoria con botones de transición",
                ok,
                f"href={href_detalle} botones={botones}",
            )
            await page.screenshot(
                path=str(SCREENSHOTS_LANDING_DIR / "30_detalle_admin.png"),
                full_page=False,
            )
        except Exception as e:
            record(
                "V30",
                "Admin: detalle convocatoria con botones de transición",
                False,
                str(e)[:80],
            )

        try:
            await logout(page)
            await login(page, *USERS["estudiante"])
            if href_detalle:
                await page.goto(f"{BASE_URL}{href_detalle}")
                await page.wait_for_load_state("domcontentloaded")
                url_final = page.url
                botones_est = await page.locator("button.btn-transicion").count()
                ok = botones_est == 0
                record(
                    "V31",
                    "Estudiante: detalle sin botones de transición",
                    ok,
                    f"botones={botones_est} url={url_final}",
                )
            else:
                record(
                    "V31",
                    "Estudiante: detalle sin botones de transición",
                    False,
                    "V30 no produjo href_detalle",
                )
        except Exception as e:
            record(
                "V31",
                "Estudiante: detalle sin botones de transición",
                False,
                str(e)[:80],
            )

        try:
            await logout(page)
            await login(page, *USERS["admin"])
            await page.goto(f"{BASE_URL}/convocatorias")
            await page.wait_for_load_state("domcontentloaded")
            borrador_row = page.locator(
                "tr[data-conv-id][data-conv-status='borrador']"
            ).first
            conv_id = await borrador_row.get_attribute("data-conv-id")
            if not conv_id:
                raise RuntimeError("No hay convocatoria BORRADOR en el listado")
            resp = await page.request.post(
                f"{BASE_URL}/convocatorias/{conv_id}/transicionar",
                form={"nuevo_estado": "ADJUDICADA", "motivo": "smoke V32"},
                max_redirects=0,
            )
            await page.goto(f"{BASE_URL}/convocatorias/{conv_id}")
            await page.wait_for_load_state("domcontentloaded")
            alert_danger = await page.locator(".alert-danger").count()
            status_code = resp.status
            ok = status_code in (303, 400, 422) and alert_danger >= 1
            record(
                "V32",
                "Transición inválida BORRADOR→ADJUDICADA rechazada con flash",
                ok,
                f"status={status_code} alert_danger={alert_danger}",
            )
        except Exception as e:
            record(
                "V32",
                "Transición inválida BORRADOR→ADJUDICADA rechazada con flash",
                False,
                str(e)[:80],
            )

        try:
            await page.goto(f"{BASE_URL}/convocatorias/archivadas")
            await page.wait_for_load_state("domcontentloaded")
            await page.wait_for_selector("h1", timeout=8000)
            h1_text = await page.locator("h1").first.text_content()
            ok = h1_text is not None and "rchivad" in h1_text.lower()
            record(
                "V33",
                "Admin: /convocatorias/archivadas accesible",
                ok,
                f"h1='{(h1_text or '').strip()}'",
            )
            await page.screenshot(
                path=str(SCREENSHOTS_LANDING_DIR / "33_archivadas.png"),
                full_page=False,
            )
        except Exception as e:
            record(
                "V33",
                "Admin: /convocatorias/archivadas accesible",
                False,
                str(e)[:80],
            )

        # ============================================
        # ESCENARIO 10 — Flujo estudiante: postular + cancelar (P03)
        # ============================================
        print("\n  Escenario 10 — Flujo estudiante (postular + cancelar)")
        await logout(page)
        await login(page, *USERS["estudiante"])

        try:
            await page.goto(f"{BASE_URL}/mis-postulaciones")
            await page.wait_for_load_state("domcontentloaded")
            await page.wait_for_selector("h1", timeout=8000)
            ids_a_cancelar = []
            filas = await page.locator(
                "tr[data-postulacion-id][data-postulacion-estado='ENVIADA'], "
                "tr[data-postulacion-id][data-postulacion-estado='EN_REVISION']"
            ).all()
            for fila in filas:
                pid = await fila.get_attribute("data-postulacion-id")
                if pid:
                    ids_a_cancelar.append(pid)
            for pid in ids_a_cancelar:
                await page.request.post(
                    f"{BASE_URL}/postulaciones/{pid}/cancelar"
                )
        except Exception as e:
            print(f"    (cleanup falló sin bloquear) {str(e)[:80]}")

        href_conv_v34 = None
        try:
            await page.goto(f"{BASE_URL}/convocatorias")
            await page.wait_for_load_state("domcontentloaded")
            primera = page.locator(
                "tr[data-conv-id] a[href^='/convocatorias/']:not([href*='editar']):not([href*='archiv'])"
            ).first
            href_conv_v34 = await primera.get_attribute("href")
            await primera.click()
            await page.wait_for_load_state("domcontentloaded")
            await page.wait_for_selector("h1", timeout=8000)
            boton_postular = await page.locator(
                "button[data-accion='postular']"
            ).count()
            record(
                "V34",
                "Estudiante: detalle convocatoria PUBLICADA con botón Postularme",
                boton_postular >= 1,
                f"href={href_conv_v34} botones_postular={boton_postular}",
            )
            await page.screenshot(
                path=str(SCREENSHOTS_LANDING_DIR / "34_estudiante_detalle.png"),
                full_page=False,
            )
        except Exception as e:
            record(
                "V34",
                "Estudiante: detalle convocatoria PUBLICADA con botón Postularme",
                False,
                str(e)[:80],
            )

        try:
            boton = page.locator("button[data-accion='postular']").first
            await boton.click()
            await page.wait_for_load_state("domcontentloaded")
            ok_url = "mis-postulaciones" in page.url
            filas_envidas = await page.locator(
                "tr[data-postulacion-estado='ENVIADA']"
            ).count()
            record(
                "V35",
                "Estudiante: tras postular aparece en mis-postulaciones",
                ok_url and filas_envidas >= 1,
                f"url={page.url} filas_enviadas={filas_envidas}",
            )
            await page.screenshot(
                path=str(SCREENSHOTS_LANDING_DIR / "35_mis_postulaciones.png"),
                full_page=True,
            )
        except Exception as e:
            record(
                "V35",
                "Estudiante: tras postular aparece en mis-postulaciones",
                False,
                str(e)[:80],
            )

        try:
            if href_conv_v34:
                await page.goto(f"{BASE_URL}{href_conv_v34}")
                await page.wait_for_load_state("domcontentloaded")
                boton_dup = await page.locator(
                    "button[data-accion='postular']"
                ).count()
                indicador = await page.locator(
                    ".mi-postulacion[data-postulacion-estado]"
                ).count()
                record(
                    "V36",
                    "Estudiante: misma convocatoria sin botón duplicado + indicador estado",
                    boton_dup == 0 and indicador >= 1,
                    f"botones={boton_dup} indicador={indicador}",
                )
            else:
                record(
                    "V36",
                    "Estudiante: misma convocatoria sin botón duplicado + indicador estado",
                    False,
                    "V34 no obtuvo href_conv",
                )
        except Exception as e:
            record(
                "V36",
                "Estudiante: misma convocatoria sin botón duplicado + indicador estado",
                False,
                str(e)[:80],
            )

        try:
            await page.goto(f"{BASE_URL}/mis-postulaciones")
            await page.wait_for_load_state("domcontentloaded")
            btn_cancelar = page.locator(
                "form[action$='/cancelar'] button[type='submit']"
            ).first
            await btn_cancelar.click()
            await page.wait_for_load_state("domcontentloaded")
            await page.wait_for_selector("h1", timeout=8000)
            canceladas = await page.locator(
                "tr[data-postulacion-estado='CANCELADA']"
            ).count()
            record(
                "V37",
                "Estudiante: cancelar postulación cambia el estado a CANCELADA",
                canceladas >= 1,
                f"filas_canceladas={canceladas}",
            )
            await page.screenshot(
                path=str(SCREENSHOTS_LANDING_DIR / "37_postulacion_cancelada.png"),
                full_page=False,
            )
        except Exception as e:
            record(
                "V37",
                "Estudiante: cancelar postulación cambia el estado a CANCELADA",
                False,
                str(e)[:80],
            )

        # ============================================
        # ESCENARIO 11 — Bandeja del coordinador (P04)
        # ============================================
        print("\n  Escenario 11 — Bandeja coordinador + transición EN_REVISION + nota")
        await logout(page)
        await login(page, *USERS["coord"])
        try:
            await page.goto(f"{BASE_URL}/bandeja")
            await page.wait_for_load_state("domcontentloaded")
            await page.wait_for_selector("h1", timeout=8000)
            h1_text = await page.locator("h1").first.text_content() or ""
            filas_bandeja = await page.locator("tr[data-postulacion-id]").count()
            ok = "andeja" in h1_text.lower() and filas_bandeja >= 1
            record(
                "V38",
                "Coordinador: ve /bandeja con postulaciones de sus convocatorias",
                ok,
                f"h1='{h1_text.strip()}' filas={filas_bandeja}",
            )
            await page.screenshot(
                path=str(SCREENSHOTS_LANDING_DIR / "38_bandeja_coord.png"),
                full_page=False,
            )
        except Exception as e:
            record(
                "V38",
                "Coordinador: ve /bandeja con postulaciones de sus convocatorias",
                False,
                str(e)[:80],
            )

        try:
            await logout(page)
            await login(page, *USERS["estudiante"])
            await page.goto(f"{BASE_URL}/bandeja")
            await page.wait_for_load_state("domcontentloaded")
            cuerpo = await page.text_content("body") or ""
            tabla_postulaciones = await page.locator(
                "tr[data-postulacion-id]"
            ).count()
            es_bloqueo = (
                "403" in cuerpo
                or "denegado" in cuerpo.lower()
                or "permisos" in cuerpo.lower()
                or tabla_postulaciones == 0
            )
            record(
                "V39",
                "Estudiante: /bandeja bloqueada (403 o sin tabla)",
                es_bloqueo,
                f"tabla_postulaciones={tabla_postulaciones}",
            )
        except Exception as e:
            record(
                "V39",
                "Estudiante: /bandeja bloqueada (403 o sin tabla)",
                False,
                str(e)[:80],
            )

        # V40 setup: estudiante1 crea una postulación fresca a una PUBLICADA
        # (sus postulaciones anteriores quedaron CANCELADA tras V37/V41 previos)
        try:
            await logout(page)
            await login(page, *USERS["estudiante"])
            await page.goto(f"{BASE_URL}/convocatorias")
            await page.wait_for_load_state("domcontentloaded")
            conv_id_setup = None
            filas_conv = await page.locator("tr[data-conv-id]").all()
            for fila in filas_conv:
                conv_id_setup = await fila.get_attribute("data-conv-id")
                if conv_id_setup:
                    break
            if conv_id_setup:
                await page.request.post(
                    f"{BASE_URL}/convocatorias/{conv_id_setup}/postular",
                    form={"motivacion": "V40 setup - postulación fresca para revisión"},
                )
        except Exception as e:
            print(f"    (V40 setup falló sin bloquear) {str(e)[:80]}")

        href_post_v40 = None
        try:
            await logout(page)
            await login(page, *USERS["admin"])
            await page.goto(f"{BASE_URL}/bandeja?estado=enviada")
            await page.wait_for_load_state("domcontentloaded")
            await page.wait_for_selector("tr[data-postulacion-id]", timeout=8000)
            primera_post = page.locator(
                "tr[data-postulacion-id][data-postulacion-estado='ENVIADA'] "
                "a[href^='/postulaciones/']"
            ).first
            href_post_v40 = await primera_post.get_attribute("href")
            await primera_post.click()
            await page.wait_for_load_state("domcontentloaded")
            await page.wait_for_selector("h1", timeout=8000)
            boton_revisar = page.locator(
                "button[data-accion='iniciar-revision']"
            ).first
            await boton_revisar.click()
            await page.wait_for_load_state("domcontentloaded")
            badge_revision = await page.locator(
                "[data-postulacion-estado='EN_REVISION']"
            ).count()
            record(
                "V40",
                "Admin: transición ENVIADA → EN_REVISION funciona",
                badge_revision >= 1,
                f"href={href_post_v40} badges_revision={badge_revision}",
            )
            await page.screenshot(
                path=str(SCREENSHOTS_LANDING_DIR / "40_postulacion_en_revision.png"),
                full_page=False,
            )
        except Exception as e:
            record(
                "V40",
                "Admin: transición ENVIADA → EN_REVISION funciona",
                False,
                str(e)[:80],
            )

        try:
            textarea = page.locator("textarea[name='nota']").first
            if await textarea.count() == 0:
                raise RuntimeError("textarea[name=nota] no presente")
            nota_texto = "Validación manual: revisar promedio en sistema académico"
            await textarea.fill(nota_texto)
            await page.locator(
                "button[data-accion='guardar-nota']"
            ).first.click()
            await page.wait_for_load_state("domcontentloaded")
            cuerpo = await page.text_content("body") or ""
            ok = "Validación manual" in cuerpo
            record(
                "V41",
                "Coord/Admin: nota privada queda en historial",
                ok,
                f"nota_en_dom={'Validación manual' in cuerpo}",
            )
            await page.screenshot(
                path=str(SCREENSHOTS_LANDING_DIR / "41_nota_coord.png"),
                full_page=False,
            )
        except Exception as e:
            record(
                "V41",
                "Coord/Admin: nota privada queda en historial",
                False,
                str(e)[:80],
            )

        # ============================================
        # ESCENARIO 12 — Evaluación IA híbrida (P05)
        # ============================================
        print("\n  Escenario 12 — Evaluación IA (reglas + Haiku + fallback)")
        try:
            cards_ia = await page.locator(".card-evaluacion-ia").count()
            decisiones = await page.locator(
                ".card-evaluacion-ia[data-decision]"
            ).count()
            disclaimer = await page.locator(
                "text=La decisión final corresponde al coordinador"
            ).count()
            ok = cards_ia >= 1 and decisiones >= 1 and disclaimer >= 1
            record(
                "V42",
                "Detalle postulación: card IA con decisión sugerida + disclaimer",
                ok,
                f"cards={cards_ia} decisiones={decisiones} disclaimer={disclaimer}",
            )
            await page.screenshot(
                path=str(SCREENSHOTS_LANDING_DIR / "42_evaluacion_ia.png"),
                full_page=False,
            )
        except Exception as e:
            record(
                "V42",
                "Detalle postulación: card IA con decisión sugerida + disclaimer",
                False,
                str(e)[:80],
            )

        try:
            await page.goto(f"{BASE_URL}/bandeja")
            await page.wait_for_load_state("domcontentloaded")
            await page.wait_for_selector("h1", timeout=8000)
            cabeceras_ia = await page.locator(
                "thead th:text-is('IA')"
            ).count()
            badges_ia = await page.locator(
                "tr[data-postulacion-id] [data-decision]"
            ).count()
            ok = cabeceras_ia >= 1 and badges_ia >= 1
            record(
                "V43",
                "Bandeja: columna IA + al menos 1 badge de decisión",
                ok,
                f"th_ia={cabeceras_ia} badges={badges_ia}",
            )
            await page.screenshot(
                path=str(SCREENSHOTS_LANDING_DIR / "43_bandeja_con_ia.png"),
                full_page=False,
            )
        except Exception as e:
            record(
                "V43",
                "Bandeja: columna IA + al menos 1 badge de decisión",
                False,
                str(e)[:80],
            )

        try:
            await page.goto(f"{BASE_URL}/bandeja?ia=revisar&estado=todas")
            await page.wait_for_load_state("domcontentloaded")
            filas_total = await page.locator("tr[data-postulacion-id]").count()
            filas_revisar = await page.locator(
                "tr[data-postulacion-id] [data-decision='REVISAR_MANUAL']"
            ).count()
            ok = filas_total >= 1 and filas_revisar == filas_total
            record(
                "V44",
                "Bandeja filtro ?ia=revisar muestra solo REVISAR_MANUAL",
                ok,
                f"total={filas_total} revisar={filas_revisar}",
            )
        except Exception as e:
            record(
                "V44",
                "Bandeja filtro ?ia=revisar muestra solo REVISAR_MANUAL",
                False,
                str(e)[:80],
            )

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
