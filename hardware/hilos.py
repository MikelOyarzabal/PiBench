"""Hilos del controlador que tratan con el hardware: pulsadores, LEDs y monitor.

Todos reciben un `threading.Event` llamado `parar`: cuando se activa, terminan
su bucle y acaban. Así el cierre es limpio.
"""

import logging
import queue
import sqlite3
import time

import config
from hardware import sensores
from notificador.telegram import aviso_alerta

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
    LED 2 (alerta): encendido si la CPU está demasiado caliente. Al elegir el nº de
    procesos parpadea N veces, y después vuelve a mostrar la alerta.
    """
    fin_parpadeo = 0.0  # hasta cuándo el LED 2 está ocupado parpadeando
    while not parar.is_set():
        with estado.lock:
            en_curso = estado.benchmark_en_curso
            hay_resultado = estado.hay_resultado
            alerta = estado.alerta_temp

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
            fin_parpadeo = time.monotonic() + n * 2 * config.PARPADEO_N_PROCESOS_S
        except queue.Empty:
            if time.monotonic() >= fin_parpadeo:  # no cortar un parpadeo a medias
                hw.led_alerta.value = alerta

        parar.wait(config.PARPADEO_S)


def actualizar_alerta(activa, temp):
    """Decide si la alerta de temperatura debe estar activa, con histéresis.

    Se activa al llegar al umbral y no se desactiva hasta bajar HISTERESIS grados
    por debajo. Sin histéresis, con la temperatura rondando el umbral, el LED
    se encendería y apagaría continuamente.
    """
    if temp is None:
        return activa
    if not activa and temp >= config.UMBRAL_TEMP_CPU:
        return True
    if activa and temp < config.UMBRAL_TEMP_CPU - config.HISTERESIS_TEMP:
        return False
    return activa


def hilo_monitor(estado, db, notificador, parar):
    """Cada pocos segundos lee la temperatura de la CPU, el uso de cada núcleo, el
    throttling y la temperatura y humedad ambiente; lo guarda en la base de datos y
    decide si hay que activar la alerta de temperatura (y avisar por Telegram).
    """
    sensor_ambiente = sensores.SensorAmbiente()
    if not sensor_ambiente.disponible:
        log.warning("Sensor de ambiente (DHT11) no encontrado: se sigue sin él")
    ultimo_aviso = None  # cuándo se avisó por Telegram de la última alerta

    while not parar.is_set():
        temp = sensores.temp_cpu()
        uso = sensores.uso_cpu()
        throttling = sensores.throttling()
        temp_ambiente, humedad = sensor_ambiente.leer()

        try:
            db.guardar_lectura(temp, uso, temp_ambiente, humedad)
        except sqlite3.Error as e:
            log.warning("No se pudo guardar la lectura: %s", e)  # seguimos sin ella

        with estado.lock:
            estado.temp_cpu = temp
            estado.uso_cpu = uso
            estado.throttling = throttling
            estado.temp_ambiente = temp_ambiente
            estado.humedad = humedad
            alerta_antes = estado.alerta_temp
            alerta = actualizar_alerta(alerta_antes, temp)
            estado.alerta_temp = alerta
            # Si hay una versión del benchmark en marcha, guardamos su temperatura máxima.
            if estado.medicion is not None:
                estado.medicion["temp_cpu_max"] = max(estado.medicion["temp_cpu_max"], temp)
                if throttling:
                    estado.medicion["throttling"] = True
            en_curso = estado.benchmark_en_curso

        if alerta != alerta_antes:
            if alerta:
                log.warning("¡Alerta! CPU a %.1f °C (umbral %.0f °C)", temp, config.UMBRAL_TEMP_CPU)
                ahora = time.monotonic()
                if ultimo_aviso is None or ahora - ultimo_aviso >= config.INTERVALO_AVISOS_ALERTA_S:
                    if notificador is not None:
                        notificador.enviar(aviso_alerta(temp))
                    ultimo_aviso = ahora
                else:
                    log.info("Aviso por Telegram omitido: ya se avisó hace %.0f s",
                             ahora - ultimo_aviso)
            else:
                log.info("Fin de la alerta: CPU a %.1f °C", temp)

        log.debug("CPU %.1f °C, uso %s, throttling %s, ambiente %s °C, humedad %s %%",
                  temp, uso, throttling, temp_ambiente, humedad)
        parar.wait(config.INTERVALO_MONITOR_BENCHMARK_S if en_curso else config.INTERVALO_MONITOR_S)
