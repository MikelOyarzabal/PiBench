"""LEDs y pulsadores con gpiozero.

En la Raspberry Pi 5 gpiozero usa lgpio por debajo (RPi.GPIO no funciona en la Pi 5).
En modo simulado (PIBENCH_SIMULADO=1) se usan pines de mentira (MockFactory), así
que todo esto funciona también en un portátil.
"""

import time

from gpiozero import LED, Button, Device, DigitalOutputDevice
from gpiozero.pins.mock import MockFactory

import config


def activar_modo_simulado():
    """Hace que gpiozero use pines simulados en lugar de los de verdad."""
    if not isinstance(Device.pin_factory, MockFactory):
        Device.pin_factory = MockFactory()


class Hardware:
    """Los 2 LEDs, los 2 pulsadores y la alimentación del sensor de ambiente."""

    def __init__(self):
        if config.SIMULADO:
            activar_modo_simulado()

        # Alimentación del sensor DHT11 desde un GPIO a nivel alto (ver config.py).
        # Se enciende lo primero para que el sensor tenga tiempo de arrancar.
        self.alimentacion_sensor = None
        if config.PIN_ALIMENTACION_DHT is not None:
            self.alimentacion_sensor = DigitalOutputDevice(config.PIN_ALIMENTACION_DHT,
                                                           initial_value=True)

        self.led_estado = LED(config.PIN_LED_ESTADO)
        self.led_alerta = LED(config.PIN_LED_ALERTA)
        # pull_up=True: sin pulsar el pin está a 3,3 V y al pulsar baja a 0 V.
        self.pulsador_lanzar = Button(
            config.PIN_PULSADOR_LANZAR, pull_up=True, bounce_time=config.ANTIRREBOTE_S
        )
        self.pulsador_procesos = Button(
            config.PIN_PULSADOR_PROCESOS, pull_up=True, bounce_time=config.ANTIRREBOTE_S
        )

    def apagar_leds(self):
        self.led_estado.off()
        self.led_alerta.off()

    def cerrar(self):
        """Apaga los LEDs y libera los pines. Llamar siempre al terminar."""
        self.apagar_leds()
        for dispositivo in (self.led_estado, self.led_alerta,
                            self.pulsador_lanzar, self.pulsador_procesos,
                            self.alimentacion_sensor):
            if dispositivo is not None:
                dispositivo.close()


def simular_pulsacion(pulsador, duracion=0.1):
    """Simula que alguien pulsa y suelta un pulsador (solo en modo simulado).

    La usaremos desde la web para "pulsar" los botones en el portátil.
    """
    pulsador.pin.drive_low()   # pulsado: el pin baja a 0 V
    time.sleep(duracion)
    pulsador.pin.drive_high()  # suelto: vuelve a 3,3 V
