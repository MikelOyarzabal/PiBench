"""Las tres versiones del benchmark deben dar exactamente la misma imagen."""

import pytest
from PIL import Image

from benchmark.mandelbrot import (NOMBRES_PALETAS, calcular_filas, guardar_png, leer_info_png,
                                  paleta_para)
from benchmark.versiones import con_hilos, con_procesos, dividir_en_bloques, secuencial

# Imagen pequeña para que los tests vayan rápido.
ANCHO, ALTO, MAX_ITER = 80, 60, 200


@pytest.fixture(scope="module")
def imagen_secuencial():
    return secuencial(ANCHO, ALTO, MAX_ITER)


def test_tamano_y_valores(imagen_secuencial):
    assert len(imagen_secuencial) == ANCHO * ALTO
    assert all(1 <= n <= MAX_ITER for n in imagen_secuencial)
    # Hay píxeles dentro del conjunto y píxeles fuera.
    assert MAX_ITER in imagen_secuencial
    assert min(imagen_secuencial) < MAX_ITER


def test_punto_conocido():
    # El píxel cuya c está más cerca de 0 está dentro del conjunto (no escapa nunca).
    fila, columna = ALTO // 2, round(ANCHO * 2.5 / 3.5)
    datos = calcular_filas(fila, fila + 1, ANCHO, ALTO, MAX_ITER)
    assert datos[columna] == MAX_ITER


@pytest.mark.parametrize("n_bloques", [1, 2, 3, 4, 7, 16, 60, 100])
def test_bloques_cubren_todas_las_filas(n_bloques):
    bloques = dividir_en_bloques(ALTO, n_bloques)
    assert bloques[0][0] == 0
    assert bloques[-1][1] == ALTO
    for (_, fin), (inicio, _) in zip(bloques, bloques[1:]):
        assert fin == inicio  # sin huecos ni solapes
    assert all(fin > inicio for inicio, fin in bloques)  # ningún bloque vacío


@pytest.mark.parametrize("n_hilos", [1, 4])
def test_hilos_igual_que_secuencial(imagen_secuencial, n_hilos):
    assert con_hilos(ANCHO, ALTO, MAX_ITER, n_hilos) == imagen_secuencial


@pytest.mark.parametrize("n_procesos", [1, 2, 3, 4])
def test_procesos_igual_que_secuencial(imagen_secuencial, n_procesos):
    assert con_procesos(ANCHO, ALTO, MAX_ITER, n_procesos) == imagen_secuencial


# --- Paletas ---

def test_paletas_rotan_en_orden_sin_repetir_seguidas():
    n = len(NOMBRES_PALETAS)
    paletas = [paleta_para(i) for i in range(1, 2 * n + 2)]
    assert paletas[:n] == NOMBRES_PALETAS           # en el orden de la lista
    assert paletas[n:2 * n] == NOMBRES_PALETAS      # y vuelta a empezar
    assert all(a != b for a, b in zip(paletas, paletas[1:]))


def test_png_guarda_paleta_y_benchmark(imagen_secuencial, tmp_path):
    ruta = tmp_path / "img.png"
    guardar_png(imagen_secuencial, ANCHO, ALTO, MAX_ITER, ruta, "Fuego", id_benchmark=2)
    assert leer_info_png(ruta) == {"paleta": "Fuego", "id_benchmark": 2}


def test_sin_imagen():
    assert leer_info_png("no_existe.png") is None


def test_cada_paleta_colorea_distinto_las_mismas_iteraciones(imagen_secuencial, tmp_path):
    """El color cambia, pero el cálculo (las iteraciones) es el mismo."""
    imagenes = []
    for nombre in NOMBRES_PALETAS:
        ruta = tmp_path / f"{nombre}.png"
        guardar_png(imagen_secuencial, ANCHO, ALTO, MAX_ITER, ruta, nombre)
        with Image.open(ruta) as img:
            pixel = img.load()
            imagenes.append([pixel[x, y] for y in range(ALTO) for x in range(ANCHO)])
    # Todas distintas entre sí...
    assert len({tuple(p) for p in imagenes}) == len(NOMBRES_PALETAS)
    # ...pero con el negro (dentro del conjunto) en los mismos píxeles.
    dentro = [n == MAX_ITER for n in imagen_secuencial]
    for pixeles in imagenes:
        assert [p == (0, 0, 0) for p in pixeles] == dentro
