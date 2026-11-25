"""Prueba de robustez: lanza N benchmarks seguidos y comprueba que todo va bien.

Con PiBench ya en marcha (python main.py), en otra terminal de la misma máquina:
    python -m herramientas.prueba_estres            # 20 benchmarks
    python -m herramientas.prueba_estres --n 5

Lanza cada benchmark por la API web (igual que el botón "Lanzar") y después comprueba:
  - que el benchmark termina (y en un tiempo razonable);
  - que se guardan sus 3 ejecuciones y que las 3 versiones dieron la misma imagen;
  - que se genera la imagen nueva;
  - que no se quedan procesos colgados (los del Pool deben desaparecer al acabar);
  - cuánta memoria usa PiBench (si crece sin parar, habría una fuga).
"""

import argparse
import sys
import time

import psutil
import requests

TIMEOUT_BENCHMARK_S = 120


def buscar_pibench():
    """El proceso principal de PiBench (el que ejecuta main.py)."""
    for proceso in psutil.process_iter(["cmdline"]):
        cmdline = proceso.info["cmdline"] or []
        if any(arg.endswith("main.py") for arg in cmdline) and "python" in cmdline[0].lower():
            return proceso
    return None


def procesos_y_memoria(principal):
    """Nº de procesos de PiBench (principal + hijos) y memoria total en MB."""
    try:
        todos = [principal] + principal.children(recursive=True)
        memoria = sum(p.memory_info().rss for p in todos if p.is_running())
    except psutil.NoSuchProcess:
        return 0, 0.0
    return len(todos), memoria / 1e6


def estado(url):
    return requests.get(f"{url}/api/estado", timeout=5).json()


def id_imagen(url):
    imagen = estado(url).get("imagen") or {}
    return imagen.get("id_benchmark") or 0


def esperar_reposo(url):
    """Espera a que no haya ningún benchmark en curso."""
    while estado(url)["benchmark_en_curso"]:
        time.sleep(0.5)


def un_benchmark(url):
    """Lanza un benchmark y espera a que termine. Devuelve (id, segundos)."""
    esperar_reposo(url)
    antes = id_imagen(url)
    inicio = time.monotonic()
    respuesta = requests.post(f"{url}/api/lanzar", timeout=5)
    if respuesta.status_code != 202:
        raise RuntimeError(f"/api/lanzar respondió {respuesta.status_code}: {respuesta.text}")

    # Termina cuando aparece la imagen nueva (se guarda al final) y ya no está en curso.
    while True:
        if time.monotonic() - inicio > TIMEOUT_BENCHMARK_S:
            raise RuntimeError("el benchmark no ha terminado a tiempo")
        datos = estado(url)
        imagen = (datos.get("imagen") or {}).get("id_benchmark") or 0
        if imagen > antes and not datos["benchmark_en_curso"]:
            return imagen, time.monotonic() - inicio
        time.sleep(0.5)


def comprobar_ejecuciones(url, id_benchmark):
    ejecuciones = [e for e in requests.get(f"{url}/api/ejecuciones?limite=20", timeout=5).json()
                   if e["id_benchmark"] == id_benchmark]
    versiones = sorted(e["version"] for e in ejecuciones)
    if versiones != ["hilos", "procesos", "secuencial"]:
        raise RuntimeError(f"ejecuciones guardadas inesperadas: {versiones}")
    return {e["version"]: e for e in ejecuciones}


def main():
    parser = argparse.ArgumentParser(description="Lanza N benchmarks seguidos y comprueba que todo va bien")
    parser.add_argument("--n", type=int, default=20)
    parser.add_argument("--url", default="http://localhost:5000")
    args = parser.parse_args()

    principal = buscar_pibench()
    if principal is None:
        sys.exit("No encuentro PiBench: arráncalo antes con `python main.py` en otra terminal.")
    try:
        esperar_reposo(args.url)
    except requests.RequestException:
        sys.exit(f"No responde la web en {args.url}")

    procesos_inicio, memoria_inicio = procesos_y_memoria(principal)
    print(f"PiBench (pid {principal.pid}): {procesos_inicio} procesos, {memoria_inicio:.0f} MB\n")
    print(f"{'#':>3} {'bench':>5} {'total':>7} {'secuencial':>10} {'hilos':>7} {'procesos':>9} "
          f"{'speedup':>8} {'T máx':>6} {'procs':>6} {'MB':>6}")

    errores = 0
    speedups = []
    for i in range(1, args.n + 1):
        try:
            id_benchmark, duracion = un_benchmark(args.url)
            e = comprobar_ejecuciones(args.url, id_benchmark)
            n_procesos, memoria = procesos_y_memoria(principal)
            speedups.append(e["procesos"]["speedup"])
            print(f"{i:>3} {id_benchmark:>5} {duracion:>6.1f}s {e['secuencial']['tiempo_s']:>9.2f}s "
                  f"{e['hilos']['tiempo_s']:>6.2f}s {e['procesos']['tiempo_s']:>8.2f}s "
                  f"{e['procesos']['speedup']:>8.2f} {e['procesos']['temp_cpu_max'] or 0:>6.1f} "
                  f"{n_procesos:>6} {memoria:>6.0f}")
            if n_procesos != procesos_inicio:
                print(f"    ¡Ojo! Había {procesos_inicio} procesos y ahora hay {n_procesos}")
                errores += 1
        except (RuntimeError, requests.RequestException) as error:
            print(f"{i:>3}  ERROR: {error}")
            errores += 1
            if not principal.is_running():
                print("PiBench ha terminado: se para la prueba.")
                break

    procesos_fin, memoria_fin = procesos_y_memoria(principal)
    print(f"\nBenchmarks: {len(speedups)}/{args.n} correctos, {errores} problemas")
    if speedups:
        print(f"Speedup con procesos: medio {sum(speedups) / len(speedups):.2f}, "
              f"mínimo {min(speedups):.2f}, máximo {max(speedups):.2f}")
    print(f"Procesos: {procesos_inicio} al empezar, {procesos_fin} al acabar")
    print(f"Memoria:  {memoria_inicio:.0f} MB al empezar, {memoria_fin:.0f} MB al acabar")
    print("\nRESULTADO:", "OK" if errores == 0 and len(speedups) == args.n else "HAY PROBLEMAS")
    sys.exit(0 if errores == 0 else 1)


if __name__ == "__main__":
    main()
