"""Hilos del controlador que tratan con el hardware: pulsadores, LEDs y monitor.

Todos reciben un `threading.Event` llamado `parar`: cuando se activa, terminan
su bucle y acaban. Así el cierre es limpio.
"""

import logging
import queue
import sqlite3

import config
from hardware import sensores

log = logging.getLogger(__name__)


# --- Acciones de los pulsadores (también se pueden llamar desde fuera) ---

def pedir_benchmark(estado, cola_ordenes, tipo="lanzar"):
    """Manda una orden al proceso benchmark, salvo que ya haya uno en curso."""
    with estado.lock:
        if estado.benchmark_en_curso:
            log.info("Pulsación ignorada: ya hay un benchmark en curso")
            return False
        estado.benchmark_en_curso = True
        n = estado.n_procesos
        # Cada benchmark lleva su nº: agrupa sus ejecuciones y decide la paleta de la imagen.
        id_benchmark = estado.siguiente_id_benchmark
        estado.siguiente_id_benchmark += 1
    log.info("Lanzando benchmark nº %d (%s) con %d procesos", id_benchmark, tipo, n)
    cola_ordenes.put({"tipo": tipo, "n_procesos": n, "id_benchmark": id_benchmark})
    return True


def cambiar_n_procesos(estado, cola_parpadeos):
    """Pasa al siguiente nº de procesos (1 -> 2 -> 3 -> 4 -> 1) y pide parpadear el LED."""
    with estado.lock:
        if estado.benchmark_en_curso:
            log.info("Pulsación ignorada: ya hay un benchmark en curso")
            return None
        estado.n_procesos = estado.n_procesos % config.MAX_PROCESOS + 1
        n = estado.n_procesos
    log.info("Nº de procesos: %d", n)
    cola_parpadeos.put(n)
    return n


# --- Hilos ---

def hilo_pulsadores(hw, estado, cola_eventos, cola_ordenes, cola_parpadeos, parar):
    """Recibe las pulsaciones (de los pulsadores y de la web) y las convierte en órdenes.

    Las funciones `when_pressed` de gpiozero se ejecutan en un hilo interno de
    gpiozero; solo meten el evento en `cola_eventos` para no bloquearlo. La web
    (otro proceso) mete sus eventos en la misma cola. Así, pulsar en la web hace
    exactamente lo mismo que pulsar el botón físico.

    Eventos: {"accion": "lanzar" | "barrido" | "procesos", "origen": "pulsador" | "web"}
    """
    hw.pulsador_lanzar.when_pressed = lambda: cola_eventos.put(
        {"accion": "lanzar", "origen": "pulsador"})
    hw.pulsador_procesos.when_pressed = lambda: cola_eventos.put(
        {"accion": "procesos", "origen": "pulsador"})

    while not parar.is_set():
        try:
            evento = cola_eventos.get(timeout=0.2)
        except queue.Empty:
            continue
        log.debug("Evento %s desde %s", evento["accion"], evento["origen"])
        if evento["accion"] in ("lanzar", "barrido"):
            pedir_benchmark(estado, cola_ordenes, evento["accion"])
        elif evento["accion"] == "procesos":
            cambiar_n_procesos(estado, cola_parpadeos)

    hw.pulsador_lanzar.when_pressed = None
    hw.pulsador_procesos.when_pressed = None


def hilo_leds(hw, estado, cola_parpadeos, parar):
    """LED de estado: parpadea durante el benchmark y se queda fijo al acabar.
    LED 2: parpadea tantas veces como el nº de procesos elegido.
    """
    while not parar.is_set():
        with estado.lock:
            en_curso = estado.benchmark_en_curso
            hay_resultado = estado.hay_resultado

        if en_curso:
            hw.led_estado.toggle()
        elif hay_resultado:
            hw.led_estado.on()
        else:
            hw.led_estado.off()

        try:
            n = cola_parpadeos.get_nowait()
            # background=True: gpiozero hace el parpadeo sin bloquear este hilo.
            hw.led_alerta.blink(on_time=config.PARPADEO_N_PROCESOS_S,
                                off_time=config.PARPADEO_N_PROCESOS_S, n=n, background=True)
        except queue.Empty:
            pass

        parar.wait(config.PARPADEO_S)


def hilo_monitor(estado, db, parar):
    """Lee la temperatura, el uso de cada núcleo y el throttling cada pocos segundos,
    y lo guarda en la base de datos.
    """
    while not parar.is_set():
        temp = sensores.temp_cpu()
        uso = sensores.uso_cpu()
        throttling = sensores.throttling()

        try:
            db.guardar_lectura(temp, uso)  # temp. ambiente y humedad: fase 6
        except sqlite3.Error as e:
            log.warning("No se pudo guardar la lectura: %s", e)  # seguimos sin ella

        with estado.lock:
            estado.temp_cpu = temp
            estado.uso_cpu = uso
            estado.throttling = throttling
            # Si hay una versión del benchmark en marcha, guardamos su temperatura máxima.
            if estado.medicion is not None:
                estado.medicion["temp_cpu_max"] = max(estado.medicion["temp_cpu_max"], temp)
                if throttling:
                    estado.medicion["throttling"] = True
            en_curso = estado.benchmark_en_curso

        log.debug("CPU %.1f °C, uso %s, throttling %s", temp, uso, throttling)
        parar.wait(config.INTERVALO_MONITOR_BENCHMARK_S if en_curso else config.INTERVALO_MONITOR_S)
