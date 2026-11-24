"""Proceso principal (controlador) de PiBench.

Arranca los procesos benchmark y web y los hilos del controlador, y se encarga
del cierre limpio con Ctrl+C.

    Procesos:  controlador (este)  +  benchmark (benchmark_worker.py, con su Pool)
               +  web (web/app.py, Flask)
    Hilos del controlador:  pulsadores, LEDs, monitor, resultados y telegram

Uso:
    python main.py                       # en la Raspberry Pi
    PIBENCH_SIMULADO=1 python main.py    # en el portátil: la web y el teclado hacen de pulsadores
"""

import logging
import multiprocessing as mp
import os
import queue
import socket
import sys
import threading
import time

import config
from benchmark.benchmark_worker import proceso_benchmark
from datos.db import BaseDatos
from estado import Estado
from hardware import sensores
from hardware.gpio import Hardware, simular_pulsacion
from hardware.hilos import hilo_leds, hilo_monitor, hilo_pulsadores
from notificador.telegram import NotificadorTelegram, resumen_benchmark
from registro import configurar_logging
from web.app import proceso_web

log = logging.getLogger("controlador")


# --- Hilo resultados ---

def procesar_resultado(estado, mensaje, db, notificador=None):
    """Trata un mensaje que llega del proceso benchmark."""
    tipo = mensaje["tipo"]

    if tipo == "inicio":
        with estado.lock:
            estado.benchmark_en_curso = True
            estado.id_benchmark = mensaje["id_benchmark"]
            estado.ejecuciones_benchmark = []

    elif tipo == "version_inicio":
        # Empieza una versión: apuntamos la temperatura inicial; el hilo monitor irá
        # actualizando la máxima mientras dure.
        temp = sensores.temp_cpu()
        with estado.lock:
            estado.medicion = {"temp_cpu_inicio": temp, "temp_cpu_max": temp,
                               "throttling": bool(sensores.throttling()),
                               "temp_ambiente": estado.temp_ambiente}  # última del monitor

    elif tipo == "ejecucion":
        with estado.lock:
            medicion = estado.medicion or {}
            estado.medicion = None
            ejecucion = {**mensaje, **medicion}
            estado.ejecuciones_benchmark.append(ejecucion)
        log.info("Resultado: %s n=%d  %.3f s  speedup %.2f  temp máx %s °C",
                 ejecucion["version"], ejecucion["n_trabajadores"], ejecucion["tiempo_s"],
                 ejecucion["speedup"], ejecucion.get("temp_cpu_max"))
        db.guardar_ejecucion(ejecucion)
        return ejecucion

    elif tipo == "fin":
        with estado.lock:
            estado.benchmark_en_curso = False
            estado.hay_resultado = True
            id_benchmark = estado.id_benchmark
            ejecuciones = list(estado.ejecuciones_benchmark)
        if mensaje["correcto"]:
            log.info("Benchmark terminado; las imágenes coinciden. Imagen (paleta %s) en %s",
                     mensaje.get("paleta"), mensaje["imagen"])
        else:
            log.error("Benchmark terminado, pero alguna versión dio una imagen DISTINTA")
        if notificador is not None:
            notificador.enviar(resumen_benchmark(id_benchmark, ejecuciones, mensaje["correcto"],
                                                 mensaje.get("paleta")))

    elif tipo in ("cancelado", "error"):
        with estado.lock:
            estado.benchmark_en_curso = False
            estado.medicion = None
        if tipo == "error":
            log.error("Error en el benchmark: %s", mensaje["mensaje"])

    return None


def hilo_resultados(estado, cola_resultados, db, notificador, parar):
    """Recibe los resultados del proceso benchmark, los guarda y avisa por Telegram."""
    while not parar.is_set():
        try:
            mensaje = cola_resultados.get(timeout=0.5)
        except queue.Empty:
            continue
        try:
            procesar_resultado(estado, mensaje, db, notificador)
        except Exception:
            # Un fallo (por ejemplo, de la base de datos) no debe parar este hilo.
            log.exception("Error al procesar el mensaje %s", mensaje.get("tipo"))


# --- Solo en modo simulado: el teclado hace de pulsadores ---

def leer_tecla():
    """Devuelve la tecla pulsada, o None si no hay ninguna. No se queda bloqueada.

    No usamos input(): en Windows, un hilo bloqueado leyendo la entrada impide
    crear procesos nuevos (el Pool del benchmark se quedaría esperando).
    """
    if os.name == "nt":
        import msvcrt
        return msvcrt.getwch() if msvcrt.kbhit() else None
    import select
    listo, _, _ = select.select([sys.stdin], [], [], 0)
    return sys.stdin.readline().strip()[:1] if listo else None


def hilo_teclado(hw, parar):
    print("Modo simulado. Teclas: [l] lanzar benchmark, [p] cambiar nº de procesos, [q] salir"
          " (en Linux, pulsa Enter después de la tecla)")
    while not parar.is_set():
        tecla = (leer_tecla() or "").lower()
        if not tecla:
            parar.wait(0.1)
        elif tecla == "l":
            simular_pulsacion(hw.pulsador_lanzar)
        elif tecla == "p":
            simular_pulsacion(hw.pulsador_procesos)
        elif tecla == "q":
            parar.set()


# --- Arranque y cierre ---

def main():
    configurar_logging()

    # 0) Base de datos: crea las tablas si hace falta y borra lecturas viejas.
    db = BaseDatos(config.RUTA_DB)
    borradas = db.inicializar()
    log.info("Base de datos %s lista (%d lecturas antiguas borradas)", config.RUTA_DB, borradas)

    # 1) Procesos benchmark y web. Se crean antes que los hilos para que los
    #    procesos nuevos no hereden hilos a medias.
    estado = Estado()             # incluye la memoria compartida con la web
    estado.siguiente_id_benchmark = db.siguiente_id_benchmark()  # sigue la numeración guardada
    cola_eventos = mp.Queue()     # pulsadores y web -> hilo pulsadores
    cola_ordenes = mp.Queue()     # controlador -> benchmark
    cola_resultados = mp.Queue()  # benchmark -> controlador
    parar_proceso = mp.Event()

    proceso = mp.Process(target=proceso_benchmark, name="benchmark",
                         args=(cola_ordenes, cola_resultados, parar_proceso))
    proceso.start()
    proceso_web_ = mp.Process(target=proceso_web, name="web",
                              args=(cola_eventos, estado.en_curso_compartido,
                                    estado.n_procesos_compartido))
    proceso_web_.start()

    # 2) Hardware e hilos.
    hw = Hardware()
    parar = threading.Event()
    cola_parpadeos = queue.Queue()
    notificador = NotificadorTelegram(config.TELEGRAM_TOKEN, config.TELEGRAM_CHAT_ID)
    hilos = [
        threading.Thread(target=hilo_pulsadores, name="pulsadores",
                         args=(hw, estado, cola_eventos, cola_ordenes, cola_parpadeos, parar)),
        threading.Thread(target=hilo_leds, name="leds", args=(hw, estado, cola_parpadeos, parar)),
        threading.Thread(target=hilo_monitor, name="monitor", args=(estado, db, notificador, parar)),
        threading.Thread(target=hilo_resultados, name="resultados",
                         args=(estado, cola_resultados, db, notificador, parar)),
    ]
    if notificador.activo:
        hilos.append(threading.Thread(target=notificador.hilo, name="telegram", args=(parar,)))
        notificador.enviar("PiBench en marcha. Te avisaré al terminar cada benchmark.")
    else:
        log.warning("Telegram desactivado: falta TELEGRAM_TOKEN o TELEGRAM_CHAT_ID en .env")
    for hilo in hilos:
        hilo.start()
    if config.SIMULADO:
        teclado = threading.Thread(target=hilo_teclado, name="teclado", args=(hw, parar))
        teclado.start()
        hilos.append(teclado)

    log.info("PiBench en marcha (%d procesos). Web: http://%s:%d  Ctrl+C para salir.",
             estado.n_procesos, "localhost" if config.SIMULADO else socket.gethostname() + ".local",
             config.PUERTO_WEB)

    # 3) El hilo principal solo espera: a Ctrl+C, a la tecla q o a que muera el benchmark.
    #    Si se cae la web, se avisa pero se sigue: el hardware y el benchmark no la necesitan.
    aviso_web = False
    try:
        while not parar.is_set():
            if not proceso.is_alive():
                log.error("El proceso benchmark ha terminado de forma inesperada")
                break
            if not proceso_web_.is_alive() and not aviso_web:
                log.error("El proceso web ha terminado; el resto sigue funcionando")
                aviso_web = True
            time.sleep(0.5)
    except KeyboardInterrupt:
        log.info("Ctrl+C recibido")
    finally:
        cerrar(hw, hilos, parar, proceso, parar_proceso, cola_ordenes, cola_eventos, proceso_web_)


def cerrar(hw, hilos, parar, proceso, parar_proceso, cola_ordenes, cola_eventos, proceso_web_):
    """Cierre limpio: web, hilos, proceso benchmark y LEDs, en ese orden."""
    log.info("Cerrando...")

    # La web no guarda nada propio (todo está en SQLite), así que se puede terminar directamente.
    proceso_web_.terminate()
    proceso_web_.join(timeout=5)

    parar.set()
    for hilo in hilos:
        # Margen para que el hilo telegram termine un envío a medias (timeout de requests).
        hilo.join(timeout=config.TIMEOUT_TELEGRAM_S + 1)
        if hilo.is_alive():
            log.warning("El hilo %s no ha terminado a tiempo", hilo.name)

    # Avisamos al proceso benchmark de dos formas: el Event (por si está calculando,
    # para que no empiece la siguiente versión) y la orden "salir" (por si está esperando).
    parar_proceso.set()
    cola_ordenes.put({"tipo": "salir"})
    proceso.join(timeout=config.TIMEOUT_CIERRE_S)
    if proceso.is_alive():
        log.warning("El proceso benchmark no responde: se fuerza su cierre")
        proceso.terminate()  # último recurso
        proceso.join(timeout=2)
    cola_ordenes.cancel_join_thread()  # no esperar a vaciar las colas al salir
    cola_eventos.cancel_join_thread()

    hw.cerrar()
    log.info("Todo cerrado. Hasta luego.")


if __name__ == "__main__":
    main()
