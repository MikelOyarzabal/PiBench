"""Lógica del controlador: pulsadores, nº de procesos, LEDs y resultados."""

import queue
import threading
import time

import pytest
from gpiozero import Device
from gpiozero.pins.mock import MockFactory

from estado import Estado
from hardware.gpio import Hardware, simular_pulsacion
from hardware.hilos import cambiar_n_procesos, hilo_leds, hilo_pulsadores, pedir_benchmark
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
    assert pedir_benchmark(estado, cola)
    assert cola.get_nowait() == {"tipo": "lanzar", "n_procesos": 4}
    assert estado.benchmark_en_curso


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
    estado, ordenes, parpadeos = Estado(), queue.Queue(), queue.Queue()
    hilo, parar = arrancar(hilo_pulsadores, hw, estado, ordenes, parpadeos)
    try:
        simular_pulsacion(hw.pulsador_procesos, duracion=0)  # 4 -> 1
        assert parpadeos.get(timeout=2) == 1
        simular_pulsacion(hw.pulsador_lanzar, duracion=0)
        assert ordenes.get(timeout=2) == {"tipo": "lanzar", "n_procesos": 1}
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

def test_procesar_resultados():
    estado = Estado()
    procesar_resultado(estado, {"tipo": "inicio", "orden": "lanzar", "n_procesos": 4})
    assert estado.benchmark_en_curso

    procesar_resultado(estado, {"tipo": "version_inicio", "version": "secuencial",
                                "n_trabajadores": 1})
    assert estado.medicion is not None
    estado.medicion["temp_cpu_max"] = 99.0  # como si el monitor hubiera visto 99 °C

    ejecucion = procesar_resultado(estado, {
        "tipo": "ejecucion", "fecha": "2026-11-23T12:00:00", "version": "secuencial",
        "n_trabajadores": 1, "tiempo_s": 7.5, "speedup": 1.0, "imagen_correcta": True})
    assert ejecucion["temp_cpu_max"] == 99.0
    assert "temp_cpu_inicio" in ejecucion and "throttling" in ejecucion
    assert estado.medicion is None

    procesar_resultado(estado, {"tipo": "fin", "correcto": True, "imagen": "x.png"})
    assert not estado.benchmark_en_curso
    assert estado.hay_resultado


def test_error_libera_el_benchmark():
    estado = Estado()
    estado.benchmark_en_curso = True
    procesar_resultado(estado, {"tipo": "error", "mensaje": "algo"})
    assert not estado.benchmark_en_curso
