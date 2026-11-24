"""Avisos por Telegram: un hilo que envía los mensajes de una cola.

Los demás hilos solo llaman a `notificador.enviar(texto)`, que mete el mensaje
en la cola y vuelve al momento. El envío (que puede tardar o fallar si no hay
Internet) lo hace el hilo "telegram", así nunca se bloquea al resto.

Si no hay token o chat_id en .env, el notificador queda desactivado y
`enviar` no hace nada. Si no hay Internet, se registra un aviso y se sigue.
"""

import logging
import queue

import requests

import config

log = logging.getLogger(__name__)

NOMBRES = {"secuencial": "Secuencial", "hilos": "Hilos", "procesos": "Procesos"}


class NotificadorTelegram:
    def __init__(self, token, chat_id):
        self.token = token
        self.chat_id = chat_id
        self.activo = bool(token and chat_id)
        self.cola = queue.Queue(maxsize=config.MAX_MENSAJES_PENDIENTES)

    def enviar(self, texto):
        """Deja un mensaje para enviar. No espera nunca."""
        if not self.activo:
            return
        try:
            self.cola.put_nowait(texto)
        except queue.Full:
            log.warning("Telegram: demasiados mensajes pendientes, se descarta uno")

    def hilo(self, parar):
        """Hilo "telegram": envía los mensajes de la cola hasta que se active `parar`."""
        while not parar.is_set():
            try:
                texto = self.cola.get(timeout=0.5)
            except queue.Empty:
                continue
            self.mandar(texto)

    def mandar(self, texto):
        """Envía un mensaje ahora mismo. Devuelve True si Telegram lo ha aceptado."""
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        try:
            respuesta = requests.post(url, data={"chat_id": self.chat_id, "text": texto},
                                      timeout=config.TIMEOUT_TELEGRAM_S)
        except requests.RequestException as e:
            # El mensaje de error de requests incluye la URL, y la URL lleva el token:
            # lo tapamos para que el token no acabe en el log.
            log.warning("Telegram: no se pudo enviar (¿sin Internet?): %s", self._ocultar(e))
            return False
        if not respuesta.ok:
            log.warning("Telegram: respuesta %d: %s", respuesta.status_code,
                        self._ocultar(respuesta.text[:200]))
            return False
        log.info("Telegram: mensaje enviado (%s)", texto.splitlines()[0])
        return True

    def _ocultar(self, texto):
        return str(texto).replace(self.token, "***") if self.token else str(texto)


# --- Textos de los mensajes ---

def resumen_benchmark(id_benchmark, ejecuciones, correcto, paleta=None):
    """Mensaje al terminar un benchmark, con una línea por versión."""
    lineas = [f"PiBench · benchmark nº {id_benchmark} terminado"]
    for e in ejecuciones:
        nombre = NOMBRES.get(e["version"], e["version"])
        if e["version"] != "secuencial":
            nombre += f" ({e['n_trabajadores']})"
        linea = f"{nombre}: {e['tiempo_s']:.2f} s"
        if e["version"] != "secuencial":
            linea += f" · speedup {e['speedup']:.2f}"
        lineas.append(linea)

    temps = [e["temp_cpu_max"] for e in ejecuciones if e.get("temp_cpu_max") is not None]
    if temps:
        linea = f"CPU máx: {max(temps):.1f} °C"
        ambiente = next((e["temp_ambiente"] for e in ejecuciones
                         if e.get("temp_ambiente") is not None), None)
        if ambiente is not None:
            linea += f" · ambiente {ambiente:.1f} °C"
        lineas.append(linea)
    if any(e.get("throttling") for e in ejecuciones):
        lineas.append("Hubo throttling (la CPU bajó la frecuencia por calor)")
    if not correcto:
        lineas.append("ATENCIÓN: alguna versión dio una imagen distinta")
    if paleta:
        lineas.append(f"Imagen: paleta {paleta}")
    return "\n".join(lineas)


def aviso_alerta(temp):
    return (f"PiBench · ¡alerta de temperatura! CPU a {temp:.1f} °C "
            f"(umbral {config.UMBRAL_TEMP_CPU:.0f} °C). LED de alerta encendido.")
