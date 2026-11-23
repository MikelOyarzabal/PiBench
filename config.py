"""Configuración de PiBench. Todos los valores ajustables están aquí."""

import os

# --- Modo simulado ---
# Con PIBENCH_SIMULADO=1 todo funciona sin Raspberry (LEDs y pulsadores de mentira).
SIMULADO = os.environ.get("PIBENCH_SIMULADO") == "1"

# --- GPIO (numeración BCM) ---
# Módulos Grove "Red LED Button v1.0": hilo amarillo = LED, hilo blanco = pulsador.
# Los pulsadores son activos a nivel bajo (al pulsar, el pin pasa a 0 V).
PIN_LED_ESTADO = 17         # pin físico 11 - módulo 1
PIN_PULSADOR_LANZAR = 27    # pin físico 13 - módulo 1
PIN_LED_ALERTA = 22         # pin físico 15 - módulo 2
PIN_PULSADOR_PROCESOS = 23  # pin físico 16 - módulo 2

# Tiempo antirrebote de los pulsadores (segundos).
ANTIRREBOTE_S = 0.05

# --- Benchmark (fractal de Mandelbrot) ---
# Tamaño de la imagen y nº máximo de iteraciones por píxel.
# Ajustar en la Pi para que la versión secuencial tarde unos 5-10 s.
# Medido en la Pi 5: 800x600 con 1000 iteraciones -> 14,9 s (demasiado).
ANCHO = 800
ALTO = 600
MAX_ITER = 500

# Zona del plano complejo que se dibuja (proporción 4:3, como la imagen).
X_MIN, X_MAX = -2.5, 1.0
Y_MIN, Y_MAX = -1.3125, 1.3125

# Nº de trabajadores para la versión con hilos.
HILOS = 4

# Cada trabajador recibe varios bloques de filas pequeños en lugar de uno grande.
# Así el reparto es más equilibrado: las filas del centro del fractal cuestan
# mucho más que las de los bordes.
BLOQUES_POR_TRABAJADOR = 4
