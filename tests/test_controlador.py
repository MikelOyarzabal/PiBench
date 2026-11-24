"""Lógica del controlador: pulsadores, nº de procesos, LEDs y resultados."""

import queue
import threading
import time

import pytest
from gpiozero import Device
from gpiozero.pins.mock import MockFactory

from datos.db import BaseDatos
from estado import Estado
from hardware.gpio import Hardware, simular_pulsacion
from hardware.hilos import (cambiar_n_procesos, hilo_leds, hilo_monitor, hilo_pulsadores,
                            pedir_benchmark)
from main import procesar_resultado


@pytest.fixture
def hw():
    Device.pin_factory = MockFactory()
    hardware = Hardware()
    yield hardware
    hardware.cerrar()
    Device.pin_factory.reset()


def arrancar(funcion, *args):
    parar = threading.Event()
    hilo = threading.Thread(target=funcion, args=(*args, parar))
    hilo.start()
    return hilo, parar


def esperar(condicion, timeout=2.0):
    fin = time.time() + timeout
    while time.time() < fin:
        if condicion():
            return True
        time.sleep(0.02)
    return False


# --- Órdenes ---

def test_pedir_benchmark():
    estado, cola = Estado(), queue.Queue()
    estado.siguiente_id_benchmark = 7
    assert pedir_benchmark(estado, cola)
    assert cola.get_nowait() == {"tipo": "lanzar", "n_procesos": 4, "id_benchmark": 7}
    assert estado.benchmark_en_curso
    assert estado.siguiente_id_benchmark == 8


def test_cada_peticion_tiene_un_id_nuevo():
    estado, cola = Estado(), queue.Queue()
    ids = []
    for _ in range(3):
        pedir_benchmark(estado, cola)
        ids.append(cola.get_nowait()["id_benchmark"])
        estado.benchmark_en_curso = False  # como si hubiera terminado
    assert ids == [1, 2, 3]


def test_pulsacion_ignorada_si_hay_benchmark_en_curso():
    estado, cola, parpadeos = Estado(), queue.Queue(), queue.Queue()
    estado.benchmark_en_curso = True
    assert not pedir_benchmark(estado, cola)
    assert cambiar_n_procesos(estado, parpadeos) is None
    assert cola.empty() and parpadeos.empty()
    assert estado.n_procesos == 4


def test_n_procesos_da_la_vuelta():
    estado, parpadeos = Estado(), queue.Queue()
    estado.n_procesos = 1
    assert [cambiar_n_procesos(estado, parpadeos) for _ in range(5)] == [2, 3, 4, 1, 2]
    assert [parpadeos.get_nowait() for _ in range(5)] == [2, 3, 4, 1, 2]


# --- Hilos con pines simulados ---

def test_hilo_pulsadores(hw):
    estado, eventos, ordenes, parpadeos = Estado(), queue.Queue(), queue.Queue(), queue.Queue()
    hilo, parar = arrancar(hilo_pulsadores, hw, estado, eventos, ordenes, parpadeos)
    try:
        simular_pulsacion(hw.pulsador_procesos, duracion=0)  # 4 -> 1
        assert parpadeos.get(timeout=2) == 1
        simular_pulsacion(hw.pulsador_lanzar, duracion=0)
        assert ordenes.get(timeout=2) == {"tipo": "lanzar", "n_procesos": 1, "id_benchmark": 1}

        # La web mete sus eventos en la misma cola: mismo efecto que el pulsador.
        with estado.lock:
            estado.benchmark_en_curso = False
        eventos.put({"accion": "barrido", "origen": "web"})
        assert ordenes.get(timeout=2) == {"tipo": "barrido", "n_procesos": 1, "id_benchmark": 2}
    finally:
        parar.set()
        hilo.join(timeout=2)
    assert not hilo.is_alive()


def test_led_estado_parpadea_y_queda_fijo(hw):
    estado = Estado()
    estado.benchmark_en_curso = True
    hilo, parar = arrancar(hilo_leds, hw, estado, queue.Queue())
    try:
        # Parpadeando: se ve encendido y apagado en algún momento.
        assert esperar(lambda: hw.led_estado.is_lit)
        assert esperar(lambda: not hw.led_estado.is_lit)
        with estado.lock:
            estado.benchmark_en_curso = False
            estado.hay_resultado = True
        assert esperar(lambda: hw.led_estado.is_lit)
        time.sleep(0.6)  # más de un ciclo: sigue encendido (fijo)
        assert hw.led_estado.is_lit
    finally:
        parar.set()
        hilo.join(timeout=2)


# --- Mensajes del proceso benchmark ---

@pytest.fixture
def db(tmp_path):
    base = BaseDatos(tmp_path / "prueba.db")
    base.inicializar()
    return base


def mensaje_ejecucion(version, id_benchmark=1):
    return {"tipo": "ejecucion", "id_benchmark": id_benchmark, "fecha": "2026-11-23T12:00:00",
            "version": version, "n_trabajadores": 1, "tiempo_s": 7.5, "speedup": 1.0,
            "imagen_correcta": True}


def mensaje_inicio(id_benchmark=1):
    return {"tipo": "inicio", "orden": "lanzar", "n_procesos": 4, "id_benchmark": id_benchmark}


def test_procesar_resultados(db):
    estado = Estado()
    procesar_resultado(estado, mensaje_inicio(), db)
    assert estado.benchmark_en_curso
    assert estado.id_benchmark == 1

    procesar_resultado(estado, {"tipo": "version_inicio", "version": "secuencial",
                                "n_trabajadores": 1}, db)
    assert estado.medicion is not None
    estado.medicion["temp_cpu_max"] = 99.0  # como si el monitor hubiera visto 99 °C

    ejecucion = procesar_resultado(estado, mensaje_ejecucion("secuencial"), db)
    assert ejecucion["temp_cpu_max"] == 99.0
    assert "temp_cpu_inicio" in ejecucion and "throttling" in ejecucion
    assert estado.medicion is None

    procesar_resultado(estado, {"tipo": "fin", "correcto": True, "imagen": "x.png"}, db)
    assert not estado.benchmark_en_curso
    assert estado.hay_resultado

    # Se ha guardado en la base de datos, con su temperatura máxima.
    [fila] = db.ultimas_ejecuciones()
    assert (fila["id_benchmark"], fila["version"], fila["temp_cpu_max"]) == (1, "secuencial", 99.0)


def test_cada_benchmark_tiene_su_id(db):
    estado = Estado()
    for id_benchmark in (1, 2):
        procesar_resultado(estado, mensaje_inicio(id_benchmark), db)
        procesar_resultado(estado, mensaje_ejecucion("secuencial", id_benchmark), db)
        procesar_resultado(estado, {"tipo": "fin", "correcto": True, "imagen": "x.png"}, db)
    assert [e["id_benchmark"] for e in db.ultimas_ejecuciones()] == [2, 1]


def test_error_libera_el_benchmark(db):
    estado = Estado()
    estado.benchmark_en_curso = True
    procesar_resultado(estado, {"tipo": "error", "mensaje": "algo"}, db)
    assert not estado.benchmark_en_curso


def test_hilo_monitor_guarda_lecturas(db):
    estado = Estado()
    hilo, parar = arrancar(hilo_monitor, estado, db)
    try:
        assert esperar(lambda: db.ultima_lectura() is not None)
    finally:
        parar.set()
        hilo.join(timeout=3)
    lectura = db.ultima_lectura()
    assert lectura["temp_cpu"] == estado.temp_cpu
    assert isinstance(lectura["uso_cpu"], list)
