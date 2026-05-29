"""
Genera docs/entrega/entrega_release1.pdf desde el markdown del mismo
nombre. Usa Playwright Chromium headless para renderizar HTML con
Mermaid embebido vía CDN y exportar a PDF.

Uso:
    uv run python scripts/generate_release_pdf.py
"""
import asyncio
import re
import sys
from pathlib import Path

import markdown
from playwright.async_api import async_playwright

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
MD_PATH = ROOT / "docs" / "entrega" / "entrega_release1.md"
HTML_PATH = ROOT / "docs" / "entrega" / "entrega_release1.html"
PDF_PATH = ROOT / "docs" / "entrega" / "entrega_release1.pdf"


_HTML_TEMPLATE = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>Proyecto PÚRPURA — Release 1</title>
<link href="https://fonts.googleapis.com/css2?family=Open+Sans:wght@400;600;700;800&family=Roboto:wght@300;400;500;700&family=JetBrains+Mono&display=swap" rel="stylesheet">
<style>
  :root {
    --udem-rojo: #C8202D;
    --udem-rojo-oscuro: #8B141E;
    --udem-azul: #2B5278;
    --udem-teal: #5BB0A8;
    --udem-negro: #1A1A1A;
    --udem-crema: #F7F5F0;
    --udem-borde: #E5E3DD;
    --udem-gris-texto: #5F5E5A;
    --udem-gris-claro: #B4B2A9;
  }
  * { box-sizing: border-box; }
  body {
    font-family: 'Roboto', sans-serif;
    color: var(--udem-gris-texto);
    line-height: 1.6;
    margin: 0;
    padding: 0;
    font-size: 11pt;
  }
  h1, h2, h3, h4 {
    font-family: 'Open Sans', sans-serif;
    color: var(--udem-negro);
    font-weight: 800;
  }
  h1 { font-size: 28pt; color: var(--udem-rojo); page-break-before: always; margin-top: 0; }
  h1:first-of-type { page-break-before: avoid; }
  h2 { font-size: 18pt; border-bottom: 2px solid var(--udem-rojo); padding-bottom: 6px; margin-top: 32px; }
  h3 { font-size: 14pt; color: var(--udem-azul); margin-top: 24px; }
  h4 { font-size: 12pt; }
  p { margin: 10px 0; }
  a { color: var(--udem-rojo); text-decoration: none; }
  code {
    font-family: 'JetBrains Mono', 'Courier New', monospace;
    font-size: 9.5pt;
    background: var(--udem-crema);
    padding: 1px 5px;
    border-radius: 3px;
    color: var(--udem-rojo-oscuro);
  }
  pre {
    background: var(--udem-crema);
    border-left: 3px solid var(--udem-rojo);
    padding: 12px 16px;
    overflow-x: auto;
    font-size: 9pt;
    page-break-inside: avoid;
  }
  pre code { background: transparent; padding: 0; color: var(--udem-negro); }
  table {
    width: 100%;
    border-collapse: collapse;
    margin: 16px 0;
    font-size: 10pt;
    page-break-inside: avoid;
  }
  th {
    background: var(--udem-azul);
    color: white;
    padding: 8px 10px;
    text-align: left;
    font-weight: 700;
    font-size: 9pt;
    text-transform: uppercase;
    letter-spacing: 0.03em;
  }
  td {
    padding: 6px 10px;
    border-bottom: 1px solid var(--udem-borde);
  }
  tr:nth-child(even) td { background: var(--udem-crema); }
  ul, ol { padding-left: 24px; }
  li { margin: 4px 0; }
  blockquote {
    border-left: 4px solid var(--udem-rojo);
    margin: 16px 0;
    padding: 8px 16px;
    background: var(--udem-crema);
    font-style: italic;
  }
  hr {
    border: none;
    border-top: 1px solid var(--udem-borde);
    margin: 24px 0;
  }
  .mermaid {
    background: white;
    padding: 12px;
    border: 1px solid var(--udem-borde);
    border-radius: 4px;
    text-align: center;
    margin: 16px 0;
    page-break-inside: avoid;
  }
  /* Encabezado de portada */
  .portada {
    text-align: center;
    padding: 80px 0 40px;
    border-bottom: 4px solid var(--udem-rojo);
    margin-bottom: 40px;
  }
  @page {
    size: A4;
    margin: 18mm 16mm 20mm 16mm;
    @bottom-center { content: "PÚRPURA · UdeMedellín · Release 1 · página " counter(page); font-size: 9pt; color: #999; }
  }
</style>
</head>
<body>
__CONTENT__
<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
<script>
  mermaid.initialize({ startOnLoad: false, theme: 'default', themeVariables: { primaryColor: '#C8202D', primaryTextColor: '#1A1A1A', primaryBorderColor: '#8B141E', lineColor: '#5F5E5A' }});
  mermaid.run({ querySelector: '.mermaid' }).then(function() { window.__mermaidReady = true; }).catch(function() { window.__mermaidReady = true; });
</script>
</body>
</html>
"""


def _convert_mermaid_blocks(html: str) -> str:
    """Cambia <pre><code class="language-mermaid">...</code></pre>
    a <div class="mermaid">...</div> para que mermaid.js lo renderice.
    """
    pattern = re.compile(
        r'<pre><code class="language-mermaid">(.*?)</code></pre>',
        re.DOTALL,
    )

    def replace(match):
        contenido = match.group(1)
        # Decodificar HTML entities básicas
        contenido = (
            contenido
            .replace("&lt;", "<")
            .replace("&gt;", ">")
            .replace("&amp;", "&")
            .replace("&quot;", '"')
        )
        return f'<div class="mermaid">{contenido}</div>'

    return pattern.sub(replace, html)


async def main():
    if not MD_PATH.exists():
        print(f"[ERROR] no existe {MD_PATH}", file=sys.stderr)
        return 1

    md_text = MD_PATH.read_text(encoding="utf-8")
    md = markdown.Markdown(
        extensions=["tables", "fenced_code", "toc", "sane_lists"]
    )
    html_body = md.convert(md_text)
    html_body = _convert_mermaid_blocks(html_body)
    html = _HTML_TEMPLATE.replace("__CONTENT__", html_body)
    HTML_PATH.write_text(html, encoding="utf-8")
    print(f"[ok] HTML intermedio: {HTML_PATH}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context()
        page = await ctx.new_page()
        await page.goto(f"file:///{HTML_PATH.as_posix()}")
        # esperar a que Mermaid termine
        try:
            await page.wait_for_function(
                "() => window.__mermaidReady === true",
                timeout=20000,
            )
        except Exception as exc:
            print(f"[warn] Mermaid no terminó en 20s: {exc}")
        await page.pdf(
            path=str(PDF_PATH),
            format="A4",
            print_background=True,
            margin={"top": "18mm", "right": "16mm", "bottom": "20mm", "left": "16mm"},
        )
        await browser.close()

    size_kb = PDF_PATH.stat().st_size // 1024
    print(f"[ok] PDF: {PDF_PATH} ({size_kb} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
