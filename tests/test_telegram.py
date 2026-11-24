"""Notificador de Telegram. No se conecta nunca de verdad: requests.post se sustituye."""

import logging
import threading
import time

import pytest
import requests

import config
from datos.db import BaseDatos
from estado import Estado
from hardware import hilos, sensores
from main import procesar_resultado
from notificador import telegram
from notificador.telegram import NotificadorTelegram, aviso_alerta, resumen_benchmark

TOKEN = "123456:TOKEN-DE-PRUEBA"


class RespuestaFalsa:
    def __init__(self, codigo=200, texto='{"ok": true}'):
        self.status_code = codigo
        self.ok = codigo == 200
        self.text = texto


@pytest.fixture
def envios(monkeypatch):
    """Sustituye requests.post: guarda lo que se habría enviado."""
    lista = []

    def post_falso(url, data, timeout):
        lista.append({"url": url, "data": data, "timeout": timeout})
        return RespuestaFalsa()

    monkeypatch.setattr(telegram.requests, "post", post_falso)
    return lista


# --- Sin token ---

def test_sin_token_queda_desactivado(envios):
    for token, chat in (("", "42"), (TOKEN, ""), ("", "")):
        notificador = NotificadorTelegram(token, chat)
        assert not notificador.activo
        notificador.enviar("hola")  # no hace nada y no falla
        assert notificador.cola.empty()
    assert envios == []


# --- Envío ---

def test_mandar(envios):
    notificador = NotificadorTelegram(TOKEN, "42")
    assert notificador.mandar("hola")
    [envio] = envios
    assert envio["url"] == f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    assert envio["data"] == {"chat_id": "42", "text": "hola"}
    assert envio["timeout"] == config.TIMEOUT_TELEGRAM_S


def test_enviar_no_espera_y_el_hilo_lo_manda(envios):
    notificador = NotificadorTelegram(TOKEN, "42")
    notificador.enviar("uno")
    notificador.enviar("dos")
    assert envios == []  # enviar solo lo deja en la cola

    parar = threading.Event()
    hilo = threading.Thread(target=notificador.hilo, args=(parar,))
    hilo.start()
    fin = time.time() + 2
    while len(envios) < 2 and time.time() < fin:
        time.sleep(0.02)
    parar.set()
    hilo.join(timeout=2)
    assert [e["data"]["text"] for e in envios] == ["uno", "dos"]
    assert not hilo.is_alive()


def test_cola_llena_descarta_sin_bloquear():
    notificador = NotificadorTelegram(TOKEN, "42")
    for i in range(config.MAX_MENSAJES_PENDIENTES + 5):
        notificador.enviar(f"mensaje {i}")  # no se queda esperando
    assert notificador.cola.qsize() == config.MAX_MENSAJES_PENDIENTES


# --- Sin Internet o con errores: no falla y el token no sale en el log ---

def test_sin_internet(monkeypatch, caplog):
    def sin_red(url, data, timeout):
        raise requests.ConnectionError(f"Max retries exceeded with url: /bot{TOKEN}/sendMessage")

    monkeypatch.setattr(telegram.requests, "post", sin_red)
    notificador = NotificadorTelegram(TOKEN, "42")
    with caplog.at_level(logging.WARNING):
        assert notificador.mandar("hola") is False
    assert "no se pudo enviar" in caplog.text
    assert TOKEN not in caplog.text


def test_timeout(monkeypatch, caplog):
    def lento(url, data, timeout):
        raise requests.Timeout("Read timed out")

    monkeypatch.setattr(telegram.requests, "post", lento)
    assert NotificadorTelegram(TOKEN, "42").mandar("hola") is False


def test_error_de_telegram(monkeypatch, caplog):
    monkeypatch.setattr(telegram.requests, "post",
                        lambda url, data, timeout: RespuestaFalsa(401, "Unauthorized"))
    with caplog.at_level(logging.WARNING):
        assert NotificadorTelegram(TOKEN, "42").mandar("hola") is False
    assert "401" in caplog.text
    assert TOKEN not in caplog.text


# --- Textos ---

def ejecucion(version, n, tiempo, speedup, temp_max, ambiente=24.9, throttling=False):
    return {"version": version, "n_trabajadores": n, "tiempo_s": tiempo, "speedup": speedup,
            "temp_cpu_max": temp_max, "temp_ambiente": ambiente, "throttling": throttling}


def test_resumen_benchmark():
    texto = resumen_benchmark(12, [
        ejecucion("secuencial", 1, 7.6, 1.0, 63.35),
        ejecucion("hilos", 4, 7.567, 1.0, 66.1),
        ejecucion("procesos", 4, 1.979, 3.84, 71.6),
    ], correcto=True, paleta="Fuego")
    assert "benchmark nº 12" in texto
    assert "Secuencial: 7.60 s" in texto
    assert "Procesos (4): 1.98 s · speedup 3.84" in texto
    assert "CPU máx: 71.6 °C · ambiente 24.9 °C" in texto
    assert "paleta Fuego" in texto
    assert "throttling" not in texto and "ATENCIÓN" not in texto


def test_resumen_con_problemas():
    texto = resumen_benchmark(1, [ejecucion("procesos", 4, 2.5, 3.0, 86.0, None, True)],
                              correcto=False)
    assert "throttling" in texto
    assert "ATENCIÓN" in texto
    assert "ambiente" not in texto


# --- Integración con el controlador ---

class NotificadorFalso:
    def __init__(self):
        self.mensajes = []

    def enviar(self, texto):
        self.mensajes.append(texto)


def test_al_terminar_el_benchmark_se_manda_el_resumen(tmp_path):
    db = BaseDatos(tmp_path / "t.db")
    db.inicializar()
    estado, notificador = Estado(), NotificadorFalso()
    procesar_resultado(estado, {"tipo": "inicio", "orden": "lanzar", "n_procesos": 2,
                                "id_benchmark": 5}, db, notificador)
    for version, n in (("secuencial", 1), ("procesos", 2)):
        procesar_resultado(estado, {"tipo": "ejecucion", "id_benchmark": 5, "version": version,
                                    "fecha": "2026-11-24T12:00:00", "n_trabajadores": n,
                                    "tiempo_s": 7.5 / n, "speedup": float(n),
                                    "imagen_correcta": True}, db, notificador)
    assert notificador.mensajes == []  # todavía no: solo al terminar
    procesar_resultado(estado, {"tipo": "fin", "correcto": True, "imagen": "x.png",
                                "paleta": "Bosque"}, db, notificador)
    [mensaje] = notificador.mensajes
    assert "benchmark nº 5" in mensaje and "Procesos (2)" in mensaje and "Bosque" in mensaje


def test_alerta_de_temperatura_avisa_una_vez(tmp_path, monkeypatch):
    db = BaseDatos(tmp_path / "t.db")
    db.inicializar()
    monkeypatch.setattr(sensores, "temp_cpu", lambda: config.UMBRAL_TEMP_CPU + 5)
    monkeypatch.setattr(config, "INTERVALO_MONITOR_S", 0.05)
    estado, notificador = Estado(), NotificadorFalso()
    parar = threading.Event()
    hilo = threading.Thread(target=hilos.hilo_monitor, args=(estado, db, notificador, parar))
    hilo.start()
    time.sleep(0.5)  # varias lecturas por encima del umbral
    parar.set()
    hilo.join(timeout=3)
    assert notificador.mensajes == [aviso_alerta(config.UMBRAL_TEMP_CPU + 5)]
