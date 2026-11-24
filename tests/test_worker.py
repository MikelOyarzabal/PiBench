"""Proceso benchmark: órdenes, mensajes que devuelve y cierre."""

import multiprocessing as mp
import threading

from benchmark.benchmark_worker import ejecutar_orden, proceso_benchmark

PEQUENO = {"ancho": 40, "alto": 30, "max_iter": 50}


def ejecutar(orden, tmp_path, parar=None):
    mensajes = []
    orden = {**PEQUENO, "ruta_imagen": str(tmp_path / "img.png"), **orden}
    ejecutar_orden(orden, mensajes.append, parar or threading.Event())
    return mensajes


def test_lanzar(tmp_path):
    mensajes = ejecutar({"tipo": "lanzar", "n_procesos": 2}, tmp_path)
    tipos = [m["tipo"] for m in mensajes]
    assert tipos == ["inicio"] + ["version_inicio", "ejecucion"] * 3 + ["fin"]

    ejecuciones = [m for m in mensajes if m["tipo"] == "ejecucion"]
    assert [(e["version"], e["n_trabajadores"]) for e in ejecuciones] == [
        ("secuencial", 1), ("hilos", 4), ("procesos", 2)]
    assert ejecuciones[0]["speedup"] == 1.0
    assert all(e["imagen_correcta"] and e["tiempo_s"] > 0 for e in ejecuciones)

    assert mensajes[-1]["correcto"]
    assert (tmp_path / "img.png").exists()


def test_barrido(tmp_path):
    mensajes = ejecutar({"tipo": "barrido"}, tmp_path)
    procesos = [m["n_trabajadores"] for m in mensajes
                if m["tipo"] == "ejecucion" and m["version"] == "procesos"]
    assert procesos == [1, 2, 3, 4]


def test_cancelar(tmp_path):
    parar = threading.Event()
    parar.set()
    mensajes = ejecutar({"tipo": "lanzar"}, tmp_path, parar)
    assert [m["tipo"] for m in mensajes] == ["inicio", "cancelado"]


def test_proceso_real_y_cierre(tmp_path):
    """El proceso de verdad: recibe una orden, devuelve resultados y se cierra al pedirlo."""
    cola_ordenes, cola_resultados, parar = mp.Queue(), mp.Queue(), mp.Event()
    proceso = mp.Process(target=proceso_benchmark, args=(cola_ordenes, cola_resultados, parar))
    proceso.start()
    try:
        cola_ordenes.put({**PEQUENO, "tipo": "lanzar", "n_procesos": 2,
                          "ruta_imagen": str(tmp_path / "img.png")})
        tipos = []
        while not tipos or tipos[-1] not in ("fin", "error"):
            tipos.append(cola_resultados.get(timeout=30)["tipo"])
        assert tipos[-1] == "fin"

        cola_ordenes.put({"tipo": "salir"})
        proceso.join(timeout=10)
        assert not proceso.is_alive()
        assert proceso.exitcode == 0
    finally:
        if proceso.is_alive():
            proceso.terminate()


def test_orden_desconocida_no_mata_el_proceso(tmp_path):
    cola_ordenes, cola_resultados, parar = mp.Queue(), mp.Queue(), mp.Event()
    proceso = mp.Process(target=proceso_benchmark, args=(cola_ordenes, cola_resultados, parar))
    proceso.start()
    try:
        cola_ordenes.put({"tipo": "bailar"})
        assert cola_resultados.get(timeout=30)["tipo"] == "error"
        assert proceso.is_alive()
        parar.set()  # también se puede cerrar con el Event
        proceso.join(timeout=10)
        assert not proceso.is_alive()
    finally:
        if proceso.is_alive():
            proceso.terminate()
