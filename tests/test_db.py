"""Base de datos SQLite: tablas, inserciones y consultas."""

import sqlite3
import threading
from datetime import datetime, timedelta

import pytest

from datos.db import BaseDatos


@pytest.fixture
def db(tmp_path):
    base = BaseDatos(tmp_path / "prueba.db")
    base.inicializar()
    return base


def ejecucion(id_benchmark=1, version="secuencial", n=1, tiempo=7.5, speedup=1.0):
    return {"id_benchmark": id_benchmark, "fecha": "2026-11-24T10:00:00", "version": version,
            "n_trabajadores": n, "tiempo_s": tiempo, "speedup": speedup,
            "temp_cpu_inicio": 50.0, "temp_cpu_max": 60.5, "temp_ambiente": None,
            "throttling": False, "imagen_correcta": True, "tipo": "ejecucion"}


def hace(**kwargs):
    return (datetime.now() - timedelta(**kwargs)).isoformat(timespec="seconds")


def test_tablas_creadas_y_modo_wal(db):
    conexion = sqlite3.connect(db.ruta)
    tablas = {f[0] for f in conexion.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    modo = conexion.execute("PRAGMA journal_mode").fetchone()[0]
    conexion.close()
    assert {"ejecuciones", "lecturas"} <= tablas
    assert modo == "wal"


def test_inicializar_dos_veces_no_borra_datos(db):
    db.guardar_ejecucion(ejecucion())
    db.inicializar()
    assert len(db.ultimas_ejecuciones()) == 1


def test_guardar_y_leer_ejecucion(db):
    # Las claves que no son columnas (tipo, imagen_correcta) se ignoran.
    id_fila = db.guardar_ejecucion(ejecucion(version="procesos", n=4, tiempo=1.97, speedup=3.82))
    [fila] = db.ultimas_ejecuciones()
    assert fila["id"] == id_fila
    assert (fila["version"], fila["n_trabajadores"], fila["speedup"]) == ("procesos", 4, 3.82)
    assert fila["temp_cpu_max"] == 60.5
    assert fila["throttling"] == 0
    assert fila["temp_ambiente"] is None


def test_ultimas_ejecuciones_mas_recientes_primero(db):
    for i in range(5):
        db.guardar_ejecucion(ejecucion(tiempo=float(i + 1)))
    tiempos = [e["tiempo_s"] for e in db.ultimas_ejecuciones(limite=3)]
    assert tiempos == [5.0, 4.0, 3.0]


def test_id_benchmark_y_agrupar(db):
    assert db.siguiente_id_benchmark() == 1
    for version in ("secuencial", "hilos", "procesos"):
        db.guardar_ejecucion(ejecucion(id_benchmark=1, version=version))
    assert db.siguiente_id_benchmark() == 2
    db.guardar_ejecucion(ejecucion(id_benchmark=2))
    assert [e["version"] for e in db.ejecuciones_de(1)] == ["secuencial", "hilos", "procesos"]
    assert len(db.ejecuciones_de(2)) == 1


def test_lectura_guarda_uso_cpu_como_json(db):
    db.guardar_lectura(55.2, [10.0, 20.5, 30.0, 99.9])
    ultima = db.ultima_lectura()
    assert ultima["temp_cpu"] == 55.2
    assert ultima["uso_cpu"] == [10.0, 20.5, 30.0, 99.9]
    assert ultima["humedad"] is None


def test_lecturas_desde_filtra_por_tiempo(db):
    db.guardar_lectura(40.0, [1.0], fecha=hace(minutes=30))
    db.guardar_lectura(45.0, [2.0], fecha=hace(minutes=5))
    db.guardar_lectura(50.0, [3.0])
    assert [l["temp_cpu"] for l in db.lecturas_desde(minutos=10)] == [45.0, 50.0]
    assert len(db.lecturas_desde(minutos=60)) == 3


def test_borrar_lecturas_antiguas(db):
    db.guardar_lectura(40.0, [], fecha=hace(hours=30))
    db.guardar_lectura(41.0, [], fecha=hace(hours=25))
    db.guardar_lectura(42.0, [], fecha=hace(hours=1))
    assert db.inicializar() == 2  # al arrancar se borran las de más de 24 h
    assert [l["temp_cpu"] for l in db.lecturas_desde(minutos=24 * 60)] == [42.0]


def test_sin_lecturas(db):
    assert db.ultima_lectura() is None
    assert db.lecturas_desde() == []


def test_varios_hilos_escribiendo_a_la_vez(db):
    """Como el monitor y el hilo de resultados: cada uno con sus conexiones."""
    def escribir_lecturas():
        for _ in range(50):
            db.guardar_lectura(50.0, [1.0, 2.0])

    def escribir_ejecuciones():
        for _ in range(50):
            db.guardar_ejecucion(ejecucion())

    hilos = [threading.Thread(target=escribir_lecturas), threading.Thread(target=escribir_lecturas),
             threading.Thread(target=escribir_ejecuciones)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    assert len(db.lecturas_desde()) == 100
    assert len(db.ultimas_ejecuciones(limite=1000)) == 50
