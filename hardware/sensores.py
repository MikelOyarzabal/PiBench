"""Lectura de sensores: temperatura de la CPU, uso de cada núcleo, throttling y
temperatura y humedad ambiente (sensor DHT11).

Si no estamos en una Raspberry (o con PIBENCH_SIMULADO=1), los valores se
simulan, para que todo funcione en un portátil.

Prueba del sensor de ambiente en la Pi:
    python -m hardware.sensores
"""

import glob
import os
import random
import subprocess
import time

import psutil

import config

RUTA_TEMP_CPU = "/sys/class/thermal/thermal_zone0/temp"


def temp_cpu():
    """Temperatura de la CPU en °C."""
    if config.SIMULADO or not os.path.exists(RUTA_TEMP_CPU):
        # Simulada: unos 40 °C en reposo y hasta 80 °C con la CPU al 100 %.
        return round(40 + 0.4 * psutil.cpu_percent() + random.uniform(-0.5, 0.5), 1)
    with open(RUTA_TEMP_CPU) as f:
        return int(f.read()) / 1000  # el archivo da milésimas de grado


def uso_cpu():
    """Lista con el % de uso de cada núcleo desde la última llamada."""
    return psutil.cpu_percent(percpu=True)


def throttling():
    """True si la Pi está bajando la frecuencia ahora mismo; None si no se puede saber.

    `vcgencmd get_throttled` devuelve algo como "throttled=0x0". Los bits que miramos:
      bit 1 (0x2): frecuencia limitada
      bit 2 (0x4): throttling activo
      bit 3 (0x8): límite suave de temperatura alcanzado
    """
    if config.SIMULADO:
        return False
    try:
        salida = subprocess.run(["vcgencmd", "get_throttled"],
                                capture_output=True, text=True, timeout=2).stdout
        valor = int(salida.strip().split("=")[1], 16)
    except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
        return None
    return bool(valor & 0xE)


# --- Temperatura y humedad ambiente (DHT11) ---

CARPETA_IIO = "/sys/bus/iio/devices"


def buscar_dht11():
    """Carpeta del sensor en /sys/bus/iio/devices, o None si el sistema no lo ve."""
    for archivo_nombre in glob.glob(os.path.join(CARPETA_IIO, "*", "name")):
        with open(archivo_nombre) as f:
            if f.read().startswith("dht11"):
                return os.path.dirname(archivo_nombre)
    return None


def _leer_milesimas(ruta):
    with open(ruta) as f:
        return int(f.read()) / 1000  # el sistema da milésimas (24900 -> 24.9)


class SensorAmbiente:
    """Lee temperatura y humedad del DHT11, a través del controlador dht11 del sistema.

    El DHT11 falla de vez en cuando (sobre todo con la CPU muy cargada, porque
    su protocolo depende de tiempos muy precisos). Si una lectura falla, se
    devuelve la última buena durante `VALIDEZ_DHT_S` segundos; después, None.
    Si no hay sensor, siempre devuelve (None, None): el programa sigue sin él.
    """

    def __init__(self):
        self.carpeta = None if config.SIMULADO else buscar_dht11()
        self.ultima = (None, None)
        self.hora_ultima = None

    @property
    def disponible(self):
        return config.SIMULADO or self.carpeta is not None

    def leer(self):
        """Devuelve (temperatura °C, humedad %)."""
        if config.SIMULADO:
            return (round(22 + random.uniform(-0.3, 0.3), 1), round(40 + random.uniform(-1, 1)))
        if self.carpeta is None:
            return (None, None)
        try:
            temp = _leer_milesimas(os.path.join(self.carpeta, "in_temp_input"))
            humedad = _leer_milesimas(os.path.join(self.carpeta, "in_humidityrelative_input"))
        except (OSError, ValueError):
            # Lectura fallida: vale la anterior si es reciente.
            if self.hora_ultima and time.monotonic() - self.hora_ultima < config.VALIDEZ_DHT_S:
                return self.ultima
            return (None, None)
        self.ultima = (temp, humedad)
        self.hora_ultima = time.monotonic()
        return self.ultima


if __name__ == "__main__":
    # Prueba: enciende la alimentación del sensor y lee 10 veces.
    from hardware.gpio import Hardware
    hw = Hardware()
    sensor = SensorAmbiente()
    print(f"Sensor encontrado en: {sensor.carpeta}" if sensor.disponible
          else "No se encuentra el sensor (¿falta el dtoverlay en config.txt?)")
    try:
        time.sleep(1)  # que el sensor arranque
        for _ in range(10):
            temp, humedad = sensor.leer()
            print(f"Ambiente: {temp} °C   Humedad: {humedad} %   CPU: {temp_cpu()} °C")
            time.sleep(2)
    finally:
        hw.cerrar()
