"""Prueba de los LEDs y pulsadores: cada pulsador enciende su LED mientras está pulsado.

Uso (desde la carpeta del proyecto):
    python -m hardware.prueba_gpio                    # en la Raspberry Pi (Ctrl+C para salir)
    PIBENCH_SIMULADO=1 python -m hardware.prueba_gpio  # en el portátil, con pulsaciones simuladas
"""

import time

import config
from hardware.gpio import Hardware, simular_pulsacion


def conectar_pulsadores_a_leds(hw):
    """Pulsador lanzar -> LED estado; pulsador nº procesos -> LED alerta."""
    def al_pulsar_lanzar():
        print("Pulsador LANZAR")
        hw.led_estado.on()

    def al_pulsar_procesos():
        print("Pulsador Nº PROCESOS")
        hw.led_alerta.on()

    hw.pulsador_lanzar.when_pressed = al_pulsar_lanzar
    hw.pulsador_lanzar.when_released = hw.led_estado.off
    hw.pulsador_procesos.when_pressed = al_pulsar_procesos
    hw.pulsador_procesos.when_released = hw.led_alerta.off


def demo_simulada(hw):
    """En el portátil no hay botones: pulsamos por programa y mostramos los LEDs."""
    for nombre, pulsador in (("lanzar", hw.pulsador_lanzar), ("nº procesos", hw.pulsador_procesos)):
        pulsador.pin.drive_low()
        print(f"  [simulado] pulsado '{nombre}' -> LED estado={hw.led_estado.is_lit}, "
              f"LED alerta={hw.led_alerta.is_lit}")
        time.sleep(0.5)
        pulsador.pin.drive_high()
        print(f"  [simulado] suelto  '{nombre}' -> LED estado={hw.led_estado.is_lit}, "
              f"LED alerta={hw.led_alerta.is_lit}")
    simular_pulsacion(hw.pulsador_lanzar)  # pulsación corta, como haría la web


def main():
    hw = Hardware()
    conectar_pulsadores_a_leds(hw)
    try:
        if config.SIMULADO:
            print("Modo simulado")
            demo_simulada(hw)
        else:
            print("Pulsa los botones: cada uno enciende su LED. Ctrl+C para salir.")
            # gpiozero atiende los pulsadores en su propio hilo; aquí solo esperamos.
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        hw.cerrar()
        print("\nLEDs apagados, pines liberados.")


if __name__ == "__main__":
    main()
