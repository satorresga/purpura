"""
Genera variantes del logosímbolo UdeM a partir del SVG oficial.

Variantes (según manual de identidad gráfica UdeM):
  - logosimbolo-udem-color.png       policromía sobre transparente
  - logosimbolo-udem-blanco.png      blanco/negativo para fondos oscuros
  - logosimbolo-udem-sobre-rojo.png  blanco compuesto sobre rojo #C8202D

Uso: uv run python scripts/generate_logo_variants.py
"""
import base64
import re
import sys
from io import BytesIO
from pathlib import Path

try:
    import numpy as np
    from PIL import Image
except ImportError:
    print("Falta Pillow o numpy. uv add --dev Pillow numpy", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "app" / "static" / "images" / "logosimbolo-udem.svg"
OUT = ROOT / "app" / "static" / "images"
UDEM_RED = (200, 32, 45, 255)  # #C8202D


def main():
    if not SRC.exists():
        print(f"ERROR: no existe {SRC}", file=sys.stderr)
        return 1
    svg = SRC.read_text(encoding="utf-8")
    m = re.search(r'data:image/png;base64,([A-Za-z0-9+/=]+)', svg)
    if not m:
        print("ERROR: no se encontro PNG base64 en el SVG", file=sys.stderr)
        return 1
    png_bytes = base64.b64decode(m.group(1))
    img = Image.open(BytesIO(png_bytes)).convert("RGBA")
    print(f"[ok] PNG extraido: {img.size[0]}x{img.size[1]}, {len(png_bytes):,} bytes")

    arr = np.array(img)
    rgb = arr[:, :, :3]
    original_alpha = arr[:, :, 3]
    whiteness = rgb.min(axis=2)
    ink_alpha = (255 - whiteness).astype(np.uint8)
    combined_alpha = np.minimum(ink_alpha, original_alpha).astype(np.uint8)

    color_arr = arr.copy()
    color_arr[:, :, 3] = combined_alpha
    img_color = Image.fromarray(color_arr, "RGBA")
    p1 = OUT / "logosimbolo-udem-color.png"
    img_color.save(p1, "PNG", optimize=True)
    print(f"[ok] {p1.name}")

    white = np.zeros_like(arr)
    white[:, :, 0:3] = 255
    white[:, :, 3] = combined_alpha
    img_white = Image.fromarray(white, "RGBA")
    p2 = OUT / "logosimbolo-udem-blanco.png"
    img_white.save(p2, "PNG", optimize=True)
    print(f"[ok] {p2.name}")

    canvas = Image.new("RGBA", img.size, UDEM_RED)
    canvas.paste(img_white, (0, 0), img_white)
    p3 = OUT / "logosimbolo-udem-sobre-rojo.png"
    canvas.save(p3, "PNG", optimize=True)
    print(f"[ok] {p3.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
