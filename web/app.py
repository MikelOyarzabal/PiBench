"""Proceso web: dashboard y API con Flask.

Va en su propio proceso: si la web falla, el hardware y el benchmark siguen.

Cómo se comunica con el controlador:
  - Lee las lecturas y las ejecuciones de SQLite (modo WAL: lee mientras el controlador escribe).
  - Lee `benchmark_en_curso` y `n_procesos` de memoria compartida (multiprocessing.Value).
  - Manda las órdenes (lanzar, barrido, cambiar nº de procesos) por `cola_eventos`,
    la misma cola que usan los pulsadores físicos.

API:
  GET  /api/estado               estado actual, última lectura de sensores y paleta de la imagen
  GET  /api/ejecuciones?limite=N histórico de ejecuciones (más recientes primero)
  GET  /api/lecturas?minutos=N   lecturas de los últimos N minutos
  POST /api/lanzar               lanza el benchmark con el nº de procesos elegido
  POST /api/barrido              lanza el barrido con 1, 2, 3 y 4 procesos
  POST /api/procesos             cambia el nº de procesos (como el pulsador 2)
  GET  /imagen                   última imagen del fractal (PNG)
"""

import logging
import os
import signal

from flask import Flask, jsonify, render_template, request, send_file

import config
from benchmark.mandelbrot import leer_info_png
from datos.db import BaseDatos
from registro import configurar_logging

log = logging.getLogger(__name__)


def crear_app(db, cola_eventos, en_curso, n_procesos):
    """Crea la aplicación Flask.

    `en_curso` y `n_procesos` son los multiprocessing.Value del controlador
    (en los tests, cualquier objeto con un atributo `.value`).
    """
    app = Flask(__name__)

    def estado_actual():
        return {"benchmark_en_curso": bool(en_curso.value), "n_procesos": n_procesos.value}

    def enviar_evento(accion):
        """Manda una acción al controlador, como si se pulsara un botón."""
        if en_curso.value:
            return jsonify(ok=False, mensaje="Ya hay un benchmark en curso", **estado_actual()), 409
        cola_eventos.put({"accion": accion, "origen": "web"})
        log.info("Petición web: %s", accion)
        return jsonify(ok=True, mensaje="Orden enviada", **estado_actual()), 202

    @app.get("/")
    def inicio():
        return render_template("index.html", simulado=config.SIMULADO,
                               max_procesos=config.MAX_PROCESOS,
                               umbral=config.UMBRAL_TEMP_CPU)

    @app.get("/api/estado")
    def api_estado():
        ultimas = db.ultimas_ejecuciones(limite=1)
        return jsonify(
            **estado_actual(),
            simulado=config.SIMULADO,
            lectura=db.ultima_lectura(),
            ultimo_benchmark=ultimas[0]["id_benchmark"] if ultimas else None,
            imagen=leer_info_png(config.RUTA_IMAGEN),  # {"paleta", "id_benchmark"} o None
        )

    @app.get("/api/ejecuciones")
    def api_ejecuciones():
        limite = min(request.args.get("limite", 50, type=int), 1000)
        return jsonify(db.ultimas_ejecuciones(limite=limite))

    @app.get("/api/lecturas")
    def api_lecturas():
        minutos = min(request.args.get("minutos", 10, type=int), 24 * 60)
        return jsonify(db.lecturas_desde(minutos=minutos))

    @app.post("/api/lanzar")
    def api_lanzar():
        return enviar_evento("lanzar")

    @app.post("/api/barrido")
    def api_barrido():
        return enviar_evento("barrido")

    @app.post("/api/procesos")
    def api_procesos():
        return enviar_evento("procesos")

    @app.get("/imagen")
    def imagen():
        if not os.path.exists(config.RUTA_IMAGEN):
            return jsonify(mensaje="Todavía no hay imagen"), 404
        # max_age=0: que el navegador no guarde una imagen vieja.
        return send_file(config.RUTA_IMAGEN, mimetype="image/png", max_age=0)

    return app


def proceso_web(cola_eventos, en_curso, n_procesos):
    """Función principal del proceso web."""
    configurar_logging()
    signal.signal(signal.SIGINT, signal.SIG_IGN)  # Ctrl+C lo gestiona el controlador
    logging.getLogger("werkzeug").setLevel(logging.WARNING)  # sin una línea por cada petición

    app = crear_app(BaseDatos(config.RUTA_DB), cola_eventos, en_curso, n_procesos)
    log.info("Web en http://%s:%d", config.HOST_WEB, config.PUERTO_WEB)
    # debug=False y sin reloader: el reloader crearía un proceso más (duplicado).
    app.run(host=config.HOST_WEB, port=config.PUERTO_WEB, debug=False, use_reloader=False)
