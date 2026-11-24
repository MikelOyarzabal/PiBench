"""Cálculo del fractal de Mandelbrot.

La función principal, `calcular_filas`, es una función pura: solo depende de
sus parámetros y no toca nada global. Por eso se puede ejecutar a la vez en
varios hilos o procesos sin ningún problema.
"""

import os

from PIL import Image
from PIL.PngImagePlugin import PngInfo

import config


def calcular_filas(fila_inicio, fila_fin, ancho, alto, max_iter):
    """Calcula las filas [fila_inicio, fila_fin) de la imagen.

    Devuelve una lista con el nº de iteraciones de cada píxel, fila a fila
    (de izquierda a derecha). Un píxel que llega a `max_iter` está dentro del
    conjunto de Mandelbrot.
    """
    paso_x = (config.X_MAX - config.X_MIN) / ancho
    paso_y = (config.Y_MAX - config.Y_MIN) / alto
    resultado = []

    for fila in range(fila_inicio, fila_fin):
        ci = config.Y_MIN + fila * paso_y
        for columna in range(ancho):
            cr = config.X_MIN + columna * paso_x
            # z = z² + c, empezando en z = 0, hasta que |z| > 2 o se acaben las iteraciones.
            zr = zi = 0.0
            n = 0
            while n < max_iter and zr * zr + zi * zi <= 4.0:
                zr, zi = zr * zr - zi * zi + cr, 2.0 * zr * zi + ci
                n += 1
            resultado.append(n)

    return resultado


# --- Colores ---
#
# El cálculo solo da el nº de iteraciones de cada píxel; el color se pone después,
# al guardar el PNG, fuera del tiempo medido. Por eso cambiar de paleta no afecta
# al benchmark: el trabajo (y la comprobación de que las versiones coinciden, que
# se hace con las iteraciones) es siempre el mismo.
#
# Cada paleta recibe t = iteraciones / max_iter (entre 0 y 1) y devuelve (r, g, b).
# Los puntos de dentro del conjunto siempre son negros.

def _limitar(x):
    return max(0, min(255, int(x)))


def _electrica(t):
    return (255 * t ** 0.3, 160 * t ** 0.5, 255 * (1 - t) ** 2)


def _fuego(t):
    s = 3 * 255 * t ** 0.35  # negro -> rojo -> amarillo -> blanco
    return (s, s - 255, s - 510)


def _oceano(t):
    s = t ** 0.35
    return (40 * s, 200 * s, 80 + 175 * s)


def _bosque(t):
    s = t ** 0.35
    return (60 * s, 60 + 195 * s, 40 * s)


def _grises(t):
    s = 255 * t ** 0.35
    return (s, s, s)


# El orden importa: los benchmarks van rotando por esta lista.
PALETAS = [
    ("Eléctrica", _electrica),
    ("Fuego", _fuego),
    ("Océano", _oceano),
    ("Bosque", _bosque),
    ("Grises", _grises),
]
NOMBRES_PALETAS = [nombre for nombre, _ in PALETAS]


def paleta_para(id_benchmark):
    """Nombre de la paleta del benchmark nº `id_benchmark` (1, 2, 3...).

    Van en orden y vuelven a empezar al acabar la lista, así que dos benchmarks
    seguidos nunca tienen la misma paleta.
    """
    return NOMBRES_PALETAS[(id_benchmark - 1) % len(PALETAS)]


def guardar_png(iteraciones, ancho, alto, max_iter, ruta, paleta=NOMBRES_PALETAS[0],
                id_benchmark=None):
    """Guarda la imagen en un PNG con la paleta indicada.

    El nombre de la paleta y el nº de benchmark se guardan dentro del propio PNG
    (metadatos de texto), así la web siempre muestra el nombre correcto de la imagen.
    """
    funcion = dict(PALETAS)[paleta]
    # Tabla con el color de cada nº de iteraciones: se calcula una vez, no por píxel.
    tabla = [tuple(_limitar(c) for c in funcion(n / max_iter)) for n in range(max_iter)]
    tabla.append((0, 0, 0))  # n == max_iter: dentro del conjunto
    pixeles = [tabla[n] for n in iteraciones]

    imagen = Image.new("RGB", (ancho, alto))
    imagen.putdata(pixeles)

    info = PngInfo()
    info.add_text("paleta", paleta)
    if id_benchmark is not None:
        info.add_text("id_benchmark", str(id_benchmark))

    os.makedirs(os.path.dirname(os.path.abspath(ruta)), exist_ok=True)
    imagen.save(ruta, pnginfo=info)


def leer_info_png(ruta):
    """Lee la paleta y el nº de benchmark guardados en el PNG, o None si no hay imagen."""
    try:
        with Image.open(ruta) as imagen:
            texto = dict(imagen.text)
    except (OSError, AttributeError):
        return None
    id_benchmark = texto.get("id_benchmark")
    return {"paleta": texto.get("paleta"),
            "id_benchmark": int(id_benchmark) if id_benchmark else None}
