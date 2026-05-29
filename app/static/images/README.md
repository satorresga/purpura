# Logosímbolo Universidad de Medellín

## Archivos disponibles

| Archivo | Uso | Fondo |
|---------|-----|-------|
| `logosimbolo-udem.svg` | Fuente de verdad oficial (Figma) | n/a |
| `logosimbolo-udem-color.png` | Navbar, login, cards | Fondo blanco |
| `logosimbolo-udem-blanco.png` | Footer institucional | Fondo oscuro |
| `logosimbolo-udem-sobre-rojo.png` | Banner hero, CTAs | Fondo rojo |
| `_legacy_placeholder.svg` | Placeholder textual del P01, sin uso activo | trazabilidad |

## Regenerar variantes

Si se actualiza `logosimbolo-udem.svg` (nueva versión del manual UdeM):

```bash
uv run python scripts/generate_logo_variants.py
```

El script extrae el PNG embebido del SVG y produce las 3 variantes:
- **color**: tal cual el PNG pero con alpha derivado de la "no-blancura"
  de cada píxel (los blancos del PNG original se vuelven transparentes).
- **blanco**: pinta el contenido visible de blanco usando el mismo alpha mask.
- **sobre-rojo**: composite del blanco transparente sobre canvas rojo `#C8202D`.

## Manual de identidad

El uso se rige por el Manual de Identidad Gráfica UdeM:
- Versión color sobre fondos blancos únicamente.
- Versión negativa blanca sobre fondos sólidos oscuros.
- Versión policromía blanca sobre rojo institucional `#C8202D`.
- Nunca rotar, deformar ni recolorear.
- Todas las páginas portan "Vigilada MinEducación" en el footer.
