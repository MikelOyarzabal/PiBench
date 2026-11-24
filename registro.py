"""Configuración de los logs, común a todos los procesos."""

import logging


def configurar_logging(nivel=logging.INFO):
    # processName/threadName: así se ve en cada línea qué proceso y qué hilo la escribe.
    logging.basicConfig(
        level=nivel,
        format="%(asctime)s [%(processName)s/%(threadName)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )
