"""Proceso benchmark: espera órdenes y ejecuta el benchmark.

Va en un proceso aparte porque pone la CPU al 100 %: si estuviera en el mismo
proceso que los pulsadores o la web, los bloquearía.

Comunicación (colas de multiprocessing):
  cola_ordenes   (entrada):  {"tipo": "lanzar", "n_procesos": N, "id_benchmark": id}
                             {"tipo": "barrido", "id_benchmark": id}  -> procesos con N = 1..4
                             {"tipo": "salir"}
  cola_resultados (salida):  {"tipo": "inicio", ...}
                             {"tipo": "version_inicio", ...}  antes de cada versión
                             {"tipo": "ejecucion", ...}       al acabar cada versión
                             {"tipo": "fin", ...} | {"tipo": "cancelado"} | {"tipo": "error", ...}

Este proceso solo calcula: las temperaturas las mide el controlador.
"""

import logging
import queue
import signal
import sys
from datetime import datetime

import config
from benchmark.mandelbrot import guardar_png, paleta_para
from benchmark.versiones import con_hilos, con_procesos, medir, secuencial
from registro import configurar_logging

log = logging.getLogger(__name__)


def _ejecutar_version(version, n, ancho, alto, max_iter):
    if version == "secuencial":
        return secuencial(ancho, alto, max_iter)
    if version == "hilos":
        return con_hilos(ancho, alto, max_iter, n)
    return con_procesos(ancho, alto, max_iter, n)


def ejecutar_orden(orden, enviar, parar):
    """Ejecuta una orden "lanzar" o "barrido" y manda los mensajes con `enviar`.

    `ancho`, `alto`, `max_iter` y `ruta_imagen` son opcionales en la orden
    (por defecto, los de config.py); los tests los usan para ir rápido.
    """
    ancho = orden.get("ancho", config.ANCHO)
    alto = orden.get("alto", config.ALTO)
    max_iter = orden.get("max_iter", config.MAX_ITER)
    ruta_imagen = orden.get("ruta_imagen", config.RUTA_IMAGEN)
    n_procesos = orden.get("n_procesos", config.MAX_PROCESOS)
    id_benchmark = orden.get("id_benchmark", 1)  # lo asigna el controlador al pedir el benchmark
    paleta = paleta_para(id_benchmark)

    # Siempre secuencial (la referencia del speedup) y con hilos; luego, procesos.
    pruebas = [("secuencial", 1), ("hilos", config.HILOS)]
    if orden["tipo"] == "barrido":
        pruebas += [("procesos", n) for n in range(1, config.MAX_PROCESOS + 1)]
    elif orden["tipo"] == "lanzar":
        pruebas.append(("procesos", n_procesos))
    else:
        raise ValueError(f"Orden desconocida: {orden['tipo']}")

    log.info("Empieza el benchmark nº %d (%s, %d procesos)", id_benchmark, orden["tipo"], n_procesos)
    enviar({"tipo": "inicio", "orden": orden["tipo"], "n_procesos": n_procesos,
            "id_benchmark": id_benchmark})

    referencia = None
    t_secuencial = None
    correcto = True
    for version, n in pruebas:
        if parar.is_set():
            log.info("Benchmark cancelado")
            enviar({"tipo": "cancelado"})
            return

        enviar({"tipo": "version_inicio", "version": version, "n_trabajadores": n})
        imagen, t = medir(_ejecutar_version, version, n, ancho, alto, max_iter)

        if referencia is None:  # la primera es la secuencial
            referencia, t_secuencial = imagen, t
        # Se comparan las listas de iteraciones (el resultado del cálculo), no los
        # colores: el color se pone después y no depende de la versión.
        igual = imagen == referencia
        correcto = correcto and igual

        log.info("%-10s n=%d  %.3f s  speedup %.2f", version, n, t, t_secuencial / t)
        enviar({
            "tipo": "ejecucion",
            "id_benchmark": id_benchmark,
            "fecha": datetime.now().isoformat(timespec="seconds"),
            "version": version,
            "n_trabajadores": n,
            "tiempo_s": round(t, 4),
            "speedup": round(t_secuencial / t, 3),
            "imagen_correcta": igual,
        })

    guardar_png(referencia, ancho, alto, max_iter, ruta_imagen, paleta, id_benchmark)
    enviar({"tipo": "fin", "correcto": correcto, "imagen": ruta_imagen, "paleta": paleta})


def _terminar_por_sigterm(signum, frame):
    # Convierte SIGTERM en una salida normal: así el "with Pool" cierra los trabajadores.
    sys.exit(0)


def proceso_benchmark(cola_ordenes, cola_resultados, parar):
    """Función principal del proceso benchmark."""
    configurar_logging()
    signal.signal(signal.SIGINT, signal.SIG_IGN)  # Ctrl+C lo gestiona el controlador
    signal.signal(signal.SIGTERM, _terminar_por_sigterm)
    log.info("Proceso benchmark listo")

    while not parar.is_set():
        try:
            orden = cola_ordenes.get(timeout=0.5)
        except queue.Empty:
            continue
        if orden["tipo"] == "salir":
            break
        try:
            ejecutar_orden(orden, cola_resultados.put, parar)
        except Exception as e:
            log.exception("Error en el benchmark")
            cola_resultados.put({"tipo": "error", "mensaje": str(e)})

    log.info("Proceso benchmark terminado")
