"""Las tres versiones del benchmark: secuencial, con hilos y con procesos.

Las tres calculan exactamente la misma imagen y devuelven la misma lista de
iteraciones; solo cambia cómo se reparte el trabajo.
"""

import time
from concurrent.futures import ThreadPoolExecutor
from multiprocessing import Pool

import config
from benchmark.mandelbrot import calcular_filas


def dividir_en_bloques(alto, n_bloques):
    """Divide las filas 0..alto en `n_bloques` bloques consecutivos [inicio, fin).

    Si las filas no se dividen exactamente, los primeros bloques llevan una fila más.
    """
    n_bloques = max(1, min(n_bloques, alto))
    base, sobrantes = divmod(alto, n_bloques)
    bloques = []
    inicio = 0
    for i in range(n_bloques):
        fin = inicio + base + (1 if i < sobrantes else 0)
        bloques.append((inicio, fin))
        inicio = fin
    return bloques


def _tareas(ancho, alto, max_iter, n_trabajadores):
    """Lista de argumentos de `calcular_filas`, una por bloque de filas."""
    bloques = dividir_en_bloques(alto, n_trabajadores * config.BLOQUES_POR_TRABAJADOR)
    return [(inicio, fin, ancho, alto, max_iter) for inicio, fin in bloques]


def _unir(partes):
    """Junta los resultados de cada bloque (ya vienen en orden) en una sola lista."""
    imagen = []
    for parte in partes:
        imagen.extend(parte)
    return imagen


def secuencial(ancho, alto, max_iter):
    """Todo el cálculo en un único hilo."""
    return calcular_filas(0, alto, ancho, alto, max_iter)


def con_hilos(ancho, alto, max_iter, n_hilos=config.HILOS):
    """Reparte los bloques entre varios hilos.

    Por el GIL de Python, solo un hilo ejecuta código Python a la vez, así que
    para un cálculo puro como este apenas mejora (o incluso empeora).
    """
    tareas = _tareas(ancho, alto, max_iter, n_hilos)
    with ThreadPoolExecutor(max_workers=n_hilos) as ejecutor:
        partes = ejecutor.map(lambda args: calcular_filas(*args), tareas)
        return _unir(partes)


def con_procesos(ancho, alto, max_iter, n_procesos):
    """Reparte los bloques entre varios procesos.

    Cada proceso tiene su propio intérprete (y su propio GIL), así que sí
    calculan a la vez en núcleos distintos. El tiempo incluye crear el Pool,
    que es un coste real del paralelismo con procesos.
    """
    tareas = _tareas(ancho, alto, max_iter, n_procesos)
    with Pool(processes=n_procesos) as pool:
        partes = pool.starmap(calcular_filas, tareas)  # starmap mantiene el orden
    return _unir(partes)


def medir(funcion, *args):
    """Ejecuta `funcion(*args)` y devuelve (resultado, segundos)."""
    inicio = time.perf_counter()
    resultado = funcion(*args)
    return resultado, time.perf_counter() - inicio
