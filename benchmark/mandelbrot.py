"""Cálculo del fractal de Mandelbrot.

La función principal, `calcular_filas`, es una función pura: solo depende de
sus parámetros y no toca nada global. Por eso se puede ejecutar a la vez en
varios hilos o procesos sin ningún problema.
"""

import os

from PIL import Image

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


def guardar_png(iteraciones, ancho, alto, max_iter, ruta):
    """Guarda la imagen en un PNG (negro = dentro del conjunto)."""
    pixeles = []
    for n in iteraciones:
        if n == max_iter:
            pixeles.append((0, 0, 0))
        else:
            # Color según lo rápido que escapa el punto.
            t = n / max_iter
            pixeles.append((int(255 * t ** 0.3), int(160 * t ** 0.5), int(255 * (1 - t) ** 2)))

    imagen = Image.new("RGB", (ancho, alto))
    imagen.putdata(pixeles)
    os.makedirs(os.path.dirname(os.path.abspath(ruta)), exist_ok=True)
    imagen.save(ruta)
