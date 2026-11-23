"""Configuración de PiBench. Todos los valores ajustables están aquí."""

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
