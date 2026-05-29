# Recursos gráficos institucionales

## logosimbolo-udem-placeholder.svg

Marca-texto temporal que respeta la estructura del logosímbolo oficial
(escudo a la izquierda con UdeM en oro sobre fondo rojo institucional,
denominación completa "Universidad de Medellín" y lema "Ciencia y Libertad"
al costado).

**Por qué es placeholder.** El manual de identidad gráfica de la Universidad
de Medellín prohíbe que externos alteren o reproduzcan el escudo oficial.
Mientras se gestiona el archivo oficial vía la **Oficina de Información y
Medios de la UdeM**, este SVG simula la composición sin reproducir el
escudo bordado.

## Cómo reemplazarlo por el oficial

1. Solicitar el SVG oficial a la Oficina de Información y Medios:
   `informacion@udem.edu.co` (canal institucional).
2. Guardar el archivo recibido como `logosimbolo-udem.svg` en este mismo
   directorio (`app/static/images/`).
3. Reemplazar las referencias en los templates:
   - `app/templates/base.html` → el bloque `.escudo` del navbar.
   - `app/templates/login.html` → el bloque `.escudo-grande` del login card.
   Usar `<img src="{{ url_for('static', path='images/logosimbolo-udem.svg') }}" alt="Universidad de Medellín">`
   en lugar del bloque CSS-only actual.
4. Borrar este archivo `logosimbolo-udem-placeholder.svg` y actualizar este
   README aclarando que el archivo oficial ya está vigente.

## Reglas de uso del logosímbolo oficial

- **Nunca** rotar, deformar, recolorear ni añadir efectos al escudo.
- Respetar el área de reserva (mínimo igual a la altura del escudo).
- Tamaño mínimo: 32 px de alto en pantalla, 12 mm en impreso.
- Sobre fondos oscuros usar la versión inversa, no la roja.
