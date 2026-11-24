"""Sensor de ambiente (DHT11) y alerta de temperatura."""

import os
import queue
import threading
import time

import pytest
from gpiozero import Device
from gpiozero.pins.mock import MockFactory

import config
from estado import Estado
from hardware import sensores
from hardware.gpio import Hardware
from hardware.hilos import actualizar_alerta, hilo_leds


# --- DHT11: se simula la carpeta que crea el controlador del sistema ---

@pytest.fixture
def carpeta_iio(tmp_path, monkeypatch):
    """Crea .../iio_device0/ con los mismos archivos que el controlador dht11."""
    monkeypatch.setattr(sensores, "CARPETA_IIO", str(tmp_path))
    otro = tmp_path / "iio_device1"  # otro dispositivo que no es el nuestro
    otro.mkdir()
    (otro / "name").write_text("otro_sensor\n")
    dht = tmp_path / "iio_device0"
    dht.mkdir()
    (dht / "name").write_text("dht11@4\n")
    return dht


def escribir(carpeta, temp, humedad):
    (carpeta / "in_temp_input").write_text(f"{temp}\n")
    (carpeta / "in_humidityrelative_input").write_text(f"{humedad}\n")


def test_encuentra_el_sensor(carpeta_iio):
    assert sensores.buscar_dht11() == str(carpeta_iio)


def test_lee_temperatura_y_humedad(carpeta_iio):
    escribir(carpeta_iio, 24900, 33000)
    sensor = sensores.SensorAmbiente()
    assert sensor.disponible
    assert sensor.leer() == (24.9, 33.0)


def test_si_falla_usa_la_ultima_lectura_reciente(carpeta_iio):
    escribir(carpeta_iio, 24900, 33000)
    sensor = sensores.SensorAmbiente()
    sensor.leer()
    os.remove(carpeta_iio / "in_temp_input")  # como un "Connection timed out"
    assert sensor.leer() == (24.9, 33.0)


def test_si_falla_mucho_tiempo_devuelve_none(carpeta_iio, monkeypatch):
    escribir(carpeta_iio, 24900, 33000)
    sensor = sensores.SensorAmbiente()
    sensor.leer()
    os.remove(carpeta_iio / "in_temp_input")
    sensor.hora_ultima -= config.VALIDEZ_DHT_S + 1  # la última lectura ya es vieja
    assert sensor.leer() == (None, None)


def test_sin_sensor(tmp_path, monkeypatch):
    monkeypatch.setattr(sensores, "CARPETA_IIO", str(tmp_path))
    sensor = sensores.SensorAmbiente()
    assert not sensor.disponible
    assert sensor.leer() == (None, None)


# --- Alerta con histéresis ---

def test_alerta_con_histeresis():
    u, h = config.UMBRAL_TEMP_CPU, config.HISTERESIS_TEMP
    assert not actualizar_alerta(False, u - 0.1)
    assert actualizar_alerta(False, u)                # llega al umbral: se enciende
    assert actualizar_alerta(True, u - h + 0.1)       # baja un poco: sigue encendida
    assert not actualizar_alerta(True, u - h - 0.1)   # baja lo suficiente: se apaga
    assert actualizar_alerta(True, None)              # sin dato: no cambia


# --- LED de alerta ---

@pytest.fixture
def hw():
    Device.pin_factory = MockFactory()
    hardware = Hardware()
    yield hardware
    hardware.cerrar()
    Device.pin_factory.reset()


def esperar(condicion, timeout=2.0):
    fin = time.time() + timeout
    while time.time() < fin:
        if condicion():
            return True
        time.sleep(0.02)
    return False


def test_alimentacion_del_sensor_encendida(hw):
    assert hw.alimentacion_sensor.is_active


def test_led_alerta_sigue_a_la_alerta(hw):
    estado = Estado()
    parar = threading.Event()
    hilo = threading.Thread(target=hilo_leds, args=(hw, estado, queue.Queue(), parar))
    hilo.start()
    try:
        assert esperar(lambda: not hw.led_alerta.is_lit)
        with estado.lock:
            estado.alerta_temp = True
        assert esperar(lambda: hw.led_alerta.is_lit)
        with estado.lock:
            estado.alerta_temp = False
        assert esperar(lambda: not hw.led_alerta.is_lit)
    finally:
        parar.set()
        hilo.join(timeout=2)


def test_parpadeo_de_n_procesos_no_se_corta_por_la_alerta(hw, monkeypatch):
    monkeypatch.setattr(config, "PARPADEO_N_PROCESOS_S", 0.2)
    estado = Estado()
    parpadeos = queue.Queue()
    parar = threading.Event()
    hilo = threading.Thread(target=hilo_leds, args=(hw, estado, parpadeos, parar))
    hilo.start()
    try:
        parpadeos.put(3)  # 3 parpadeos = 1,2 s
        # Durante el parpadeo, el LED se apaga en algún momento aunque no haya alerta
        # ni deje de haberla: lo controla el parpadeo, no la alerta.
        with estado.lock:
            estado.alerta_temp = True
        assert esperar(lambda: not hw.led_alerta.is_lit, timeout=1.0)
        # Al terminar, se queda encendido (hay alerta).
        time.sleep(1.4)
        assert esperar(lambda: hw.led_alerta.is_lit)
    finally:
        parar.set()
        hilo.join(timeout=2)
