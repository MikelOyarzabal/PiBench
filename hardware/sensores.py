"""Lectura de sensores: temperatura de la CPU, uso de cada núcleo y throttling.

Si no estamos en una Raspberry (o con PIBENCH_SIMULADO=1), la temperatura se
simula a partir del uso de la CPU, para que todo funcione en un portátil.
El sensor DHT20 se añadirá en la fase 6.
"""

import os
import random
import subprocess

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
