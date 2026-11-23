"""Las tres versiones del benchmark deben dar exactamente la misma imagen."""

import pytest

from benchmark.mandelbrot import calcular_filas
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
