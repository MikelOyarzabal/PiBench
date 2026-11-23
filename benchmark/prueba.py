"""Script de prueba: ejecuta las tres versiones e imprime tiempos y speedup.

Uso (desde la carpeta del proyecto):
    python -m benchmark.prueba                     # tamaño de config.py, 4 procesos
    python -m benchmark.prueba --procesos 2
    python -m benchmark.prueba --barrido           # procesos con N = 1, 2, 3 y 4
    python -m benchmark.prueba --ancho 400 --alto 300 --iter 500
"""

import argparse
import os

import config
from benchmark.mandelbrot import guardar_png
from benchmark.versiones import con_hilos, con_procesos, medir, secuencial

CARPETA_RESULTADOS = "resultados"


def main():
    parser = argparse.ArgumentParser(description="Prueba del benchmark de Mandelbrot")
    parser.add_argument("--ancho", type=int, default=config.ANCHO)
    parser.add_argument("--alto", type=int, default=config.ALTO)
    parser.add_argument("--iter", type=int, default=config.MAX_ITER, help="iteraciones máximas")
    parser.add_argument("--procesos", type=int, default=4, help="nº de procesos (1-4)")
    parser.add_argument("--barrido", action="store_true", help="probar procesos con N = 1, 2, 3 y 4")
    args = parser.parse_args()

    tam = (args.ancho, args.alto, args.iter)
    print(f"Imagen {args.ancho}x{args.alto}, {args.iter} iteraciones máx., "
          f"{os.cpu_count()} núcleos lógicos\n")

    filas = []  # (versión, nº trabajadores, segundos, imagen)

    print("Calculando versión secuencial...")
    imagen_ref, t_sec = medir(secuencial, *tam)
    filas.append(("secuencial", 1, t_sec, imagen_ref))

    print(f"Calculando versión con hilos ({config.HILOS})...")
    imagen, t = medir(con_hilos, *tam, config.HILOS)
    filas.append(("hilos", config.HILOS, t, imagen))

    lista_procesos = [1, 2, 3, 4] if args.barrido else [args.procesos]
    for n in lista_procesos:
        print(f"Calculando versión con procesos ({n})...")
        imagen, t = medir(con_procesos, *tam, n)
        filas.append(("procesos", n, t, imagen))

    print(f"\n{'Versión':<12}{'Trab.':>6}{'Tiempo (s)':>12}{'Speedup':>10}  Imagen")
    print("-" * 50)
    for version, n, t, imagen in filas:
        igual = "OK" if imagen == imagen_ref else "DISTINTA"
        print(f"{version:<12}{n:>6}{t:>12.3f}{t_sec / t:>10.2f}  {igual}")

    os.makedirs(CARPETA_RESULTADOS, exist_ok=True)
    ruta = os.path.join(CARPETA_RESULTADOS, "mandelbrot.png")
    guardar_png(imagen_ref, *tam, ruta)
    print(f"\nImagen guardada en {ruta}")


if __name__ == "__main__":
    main()
