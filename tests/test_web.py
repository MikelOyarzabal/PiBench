"""Web: API y página, con el cliente de pruebas de Flask (sin arrancar el servidor)."""

import queue

import pytest

import config
from datos.db import BaseDatos
from estado import Estado
from web.app import crear_app


@pytest.fixture
def entorno(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RUTA_IMAGEN", str(tmp_path / "mandelbrot.png"))
    db = BaseDatos(tmp_path / "web.db")
    db.inicializar()
    estado = Estado()  # sus Value son los mismos objetos que recibe la web de verdad
    eventos = queue.Queue()
    app = crear_app(db, eventos, estado.en_curso_compartido, estado.n_procesos_compartido)
    return app.test_client(), db, estado, eventos


def ejecucion(id_benchmark, version, n, tiempo, speedup):
    return {"id_benchmark": id_benchmark, "fecha": "2026-11-24T10:00:00", "version": version,
            "n_trabajadores": n, "tiempo_s": tiempo, "speedup": speedup,
            "temp_cpu_inicio": 50.0, "temp_cpu_max": 60.0, "throttling": False}


def test_pagina_principal(entorno):
    cliente, *_ = entorno
    respuesta = cliente.get("/")
    assert respuesta.status_code == 200
    html = respuesta.get_data(as_text=True)
    assert "PiBench" in html and "Lanzar benchmark" in html


def test_estado_vacio(entorno):
    cliente, *_ = entorno
    datos = cliente.get("/api/estado").get_json()
    assert datos["benchmark_en_curso"] is False
    assert datos["n_procesos"] == config.N_PROCESOS_INICIAL
    assert datos["lectura"] is None
    assert datos["ultimo_benchmark"] is None


def test_estado_refleja_memoria_compartida_y_lecturas(entorno):
    cliente, db, estado, _ = entorno
    estado.benchmark_en_curso = True
    estado.n_procesos = 2
    db.guardar_lectura(61.5, [100.0, 99.0, 98.0, 97.0])
    db.guardar_ejecucion(ejecucion(3, "secuencial", 1, 7.5, 1.0))

    datos = cliente.get("/api/estado").get_json()
    assert datos["benchmark_en_curso"] is True
    assert datos["n_procesos"] == 2
    assert datos["lectura"]["temp_cpu"] == 61.5
    assert datos["lectura"]["uso_cpu"] == [100.0, 99.0, 98.0, 97.0]
    assert datos["ultimo_benchmark"] == 3


def test_lanzar_manda_evento(entorno):
    cliente, _, _, eventos = entorno
    respuesta = cliente.post("/api/lanzar")
    assert respuesta.status_code == 202
    assert respuesta.get_json()["ok"]
    assert eventos.get_nowait() == {"accion": "lanzar", "origen": "web"}


@pytest.mark.parametrize("ruta, accion", [("/api/barrido", "barrido"), ("/api/procesos", "procesos")])
def test_otras_ordenes(entorno, ruta, accion):
    cliente, _, _, eventos = entorno
    assert cliente.post(ruta).status_code == 202
    assert eventos.get_nowait()["accion"] == accion


def test_no_se_lanza_si_hay_benchmark_en_curso(entorno):
    cliente, _, estado, eventos = entorno
    estado.benchmark_en_curso = True
    respuesta = cliente.post("/api/lanzar")
    assert respuesta.status_code == 409
    assert not respuesta.get_json()["ok"]
    assert eventos.empty()


def test_lanzar_solo_por_post(entorno):
    cliente, *_ = entorno
    assert cliente.get("/api/lanzar").status_code == 405


def test_ejecuciones(entorno):
    cliente, db, *_ = entorno
    db.guardar_ejecucion(ejecucion(1, "secuencial", 1, 7.5, 1.0))
    db.guardar_ejecucion(ejecucion(1, "procesos", 4, 1.97, 3.81))
    datos = cliente.get("/api/ejecuciones?limite=1").get_json()
    assert len(datos) == 1
    assert datos[0]["version"] == "procesos"  # la más reciente primero


def test_lecturas(entorno):
    cliente, db, *_ = entorno
    db.guardar_lectura(50.0, [1.0])
    db.guardar_lectura(51.0, [2.0])
    datos = cliente.get("/api/lecturas?minutos=5").get_json()
    assert [l["temp_cpu"] for l in datos] == [50.0, 51.0]


def test_imagen_y_su_paleta(entorno):
    cliente, *_ = entorno
    assert cliente.get("/imagen").status_code == 404
    assert cliente.get("/api/estado").get_json()["imagen"] is None

    from benchmark.mandelbrot import calcular_filas, guardar_png
    guardar_png(calcular_filas(0, 6, 8, 6, 20), 8, 6, 20, config.RUTA_IMAGEN, "Océano", 3)
    respuesta = cliente.get("/imagen")
    assert respuesta.status_code == 200
    assert respuesta.mimetype == "image/png"
    assert cliente.get("/api/estado").get_json()["imagen"] == {"paleta": "Océano", "id_benchmark": 3}
