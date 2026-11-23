"""LEDs y pulsadores con pines simulados (MockFactory): no hace falta la Raspberry."""

import pytest
from gpiozero import Device
from gpiozero.pins.mock import MockFactory

import config
from hardware.gpio import Hardware, simular_pulsacion
from hardware.prueba_gpio import conectar_pulsadores_a_leds


@pytest.fixture
def hw():
    Device.pin_factory = MockFactory()
    hardware = Hardware()
    yield hardware
    hardware.cerrar()
    Device.pin_factory.reset()


def estado_pin(numero):
    return Device.pin_factory.pin(numero).state


def test_leds_empiezan_apagados(hw):
    assert not estado_pin(config.PIN_LED_ESTADO)
    assert not estado_pin(config.PIN_LED_ALERTA)


def test_encender_y_apagar_leds(hw):
    hw.led_estado.on()
    assert estado_pin(config.PIN_LED_ESTADO)
    assert not estado_pin(config.PIN_LED_ALERTA)  # el otro no se toca

    hw.led_alerta.on()
    hw.apagar_leds()
    assert not estado_pin(config.PIN_LED_ESTADO)
    assert not estado_pin(config.PIN_LED_ALERTA)


def test_pulsadores_sin_pulsar(hw):
    # Con pull-up, sin pulsar el pin está a nivel alto y el botón no cuenta como pulsado.
    assert not hw.pulsador_lanzar.is_pressed
    assert not hw.pulsador_procesos.is_pressed


def test_pulsar_es_nivel_bajo(hw):
    hw.pulsador_lanzar.pin.drive_low()
    assert hw.pulsador_lanzar.is_pressed
    assert not hw.pulsador_procesos.is_pressed
    hw.pulsador_lanzar.pin.drive_high()
    assert not hw.pulsador_lanzar.is_pressed


def test_cada_pulsador_llama_a_su_funcion(hw):
    pulsaciones = []
    hw.pulsador_lanzar.when_pressed = lambda: pulsaciones.append("lanzar")
    hw.pulsador_procesos.when_pressed = lambda: pulsaciones.append("procesos")

    simular_pulsacion(hw.pulsador_lanzar, duracion=0)
    simular_pulsacion(hw.pulsador_procesos, duracion=0)

    assert pulsaciones == ["lanzar", "procesos"]


def test_cada_pulsador_enciende_su_led(hw):
    # Lo mismo que hace la prueba real en la Pi.
    conectar_pulsadores_a_leds(hw)

    hw.pulsador_procesos.pin.drive_low()
    assert hw.led_alerta.is_lit
    assert not hw.led_estado.is_lit
    hw.pulsador_procesos.pin.drive_high()
    assert not hw.led_alerta.is_lit


def test_cerrar_apaga_los_leds():
    Device.pin_factory = MockFactory()
    hardware = Hardware()
    hardware.led_estado.on()
    hardware.led_alerta.on()
    hardware.cerrar()
    assert not estado_pin(config.PIN_LED_ESTADO)
    assert not estado_pin(config.PIN_LED_ALERTA)
    Device.pin_factory.reset()
