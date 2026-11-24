"""Base de datos SQLite: ejecuciones del benchmark y lecturas de los sensores.

Cada operación abre y cierra su propia conexión. Así se puede usar desde
varios hilos (monitor, resultados) y desde varios procesos (la web) sin
compartir conexiones, que en sqlite3 no es seguro.

El modo WAL permite que la web lea mientras el controlador escribe.

Uso para ver el contenido (desde la carpeta del proyecto):
    python -m datos.db
"""

import json
import sqlite3
from datetime import datetime, timedelta

import config

ESQUEMA = """
CREATE TABLE IF NOT EXISTS ejecuciones (
    id INTEGER PRIMARY KEY,
    id_benchmark INTEGER NOT NULL,  -- agrupa las versiones de una misma pulsación
    fecha TEXT NOT NULL,
    version TEXT NOT NULL,          -- 'secuencial' | 'hilos' | 'procesos'
    n_trabajadores INTEGER NOT NULL,
    tiempo_s REAL NOT NULL,
    speedup REAL,
    temp_cpu_inicio REAL,
    temp_cpu_max REAL,
    temp_ambiente REAL,
    throttling INTEGER              -- 0/1
);

CREATE TABLE IF NOT EXISTS lecturas (
    id INTEGER PRIMARY KEY,
    fecha TEXT NOT NULL,
    temp_cpu REAL,
    uso_cpu TEXT,                   -- JSON con el % de cada núcleo
    temp_ambiente REAL,
    humedad REAL
);

CREATE INDEX IF NOT EXISTS idx_lecturas_fecha ON lecturas(fecha);
"""

COLUMNAS_EJECUCION = ("id_benchmark", "fecha", "version", "n_trabajadores", "tiempo_s",
                      "speedup", "temp_cpu_inicio", "temp_cpu_max", "temp_ambiente", "throttling")


def ahora():
    """Fecha y hora actual en texto ISO (se ordena bien como texto)."""
    return datetime.now().isoformat(timespec="seconds")


class BaseDatos:
    def __init__(self, ruta=config.RUTA_DB):
        self.ruta = str(ruta)

    def conectar(self):
        # timeout: si otro hilo/proceso está escribiendo, espera hasta 5 s en lugar de fallar.
        conexion = sqlite3.connect(self.ruta, timeout=5)
        conexion.row_factory = sqlite3.Row  # filas accesibles por nombre de columna
        return conexion

    def _ejecutar(self, sql, parametros=()):
        """Ejecuta una sentencia que modifica datos y la confirma (commit)."""
        conexion = self.conectar()
        try:
            with conexion:  # commit al acabar (o rollback si hay error)
                return conexion.execute(sql, parametros)
        finally:
            conexion.close()

    def _consultar(self, sql, parametros=()):
        """Ejecuta una consulta y devuelve una lista de diccionarios."""
        conexion = self.conectar()
        try:
            return [dict(fila) for fila in conexion.execute(sql, parametros)]
        finally:
            conexion.close()

    # --- Arranque ---

    def inicializar(self):
        """Crea las tablas (si no existen), activa WAL y borra lecturas antiguas."""
        conexion = self.conectar()
        try:
            conexion.execute("PRAGMA journal_mode=WAL")  # se queda guardado en el archivo
            conexion.executescript(ESQUEMA)
        finally:
            conexion.close()
        return self.borrar_lecturas_antiguas()

    def borrar_lecturas_antiguas(self, horas=config.HORAS_LECTURAS):
        limite = (datetime.now() - timedelta(hours=horas)).isoformat(timespec="seconds")
        return self._ejecutar("DELETE FROM lecturas WHERE fecha < ?", (limite,)).rowcount

    # --- Ejecuciones ---

    def siguiente_id_benchmark(self):
        fila = self._consultar("SELECT COALESCE(MAX(id_benchmark), 0) + 1 AS siguiente "
                               "FROM ejecuciones")
        return fila[0]["siguiente"]

    def guardar_ejecucion(self, ejecucion):
        """Guarda una ejecución (un diccionario con las claves de COLUMNAS_EJECUCION)."""
        valores = [ejecucion.get(columna) for columna in COLUMNAS_EJECUCION]
        sql = (f"INSERT INTO ejecuciones ({', '.join(COLUMNAS_EJECUCION)}) "
               f"VALUES ({', '.join('?' * len(COLUMNAS_EJECUCION))})")
        return self._ejecutar(sql, valores).lastrowid

    def ultimas_ejecuciones(self, limite=50):
        """Las ejecuciones más recientes primero."""
        return self._consultar("SELECT * FROM ejecuciones ORDER BY id DESC LIMIT ?", (limite,))

    def ejecuciones_de(self, id_benchmark):
        return self._consultar("SELECT * FROM ejecuciones WHERE id_benchmark = ? ORDER BY id",
                               (id_benchmark,))

    # --- Lecturas ---

    def guardar_lectura(self, temp_cpu, uso_cpu, temp_ambiente=None, humedad=None, fecha=None):
        return self._ejecutar(
            "INSERT INTO lecturas (fecha, temp_cpu, uso_cpu, temp_ambiente, humedad) "
            "VALUES (?, ?, ?, ?, ?)",
            (fecha or ahora(), temp_cpu, json.dumps(uso_cpu), temp_ambiente, humedad),
        ).lastrowid

    def lecturas_desde(self, minutos=10):
        """Lecturas de los últimos `minutos`, de la más antigua a la más reciente."""
        limite = (datetime.now() - timedelta(minutes=minutos)).isoformat(timespec="seconds")
        lecturas = self._consultar("SELECT * FROM lecturas WHERE fecha >= ? ORDER BY id",
                                   (limite,))
        for lectura in lecturas:
            lectura["uso_cpu"] = json.loads(lectura["uso_cpu"]) if lectura["uso_cpu"] else []
        return lecturas

    def ultima_lectura(self):
        filas = self._consultar("SELECT * FROM lecturas ORDER BY id DESC LIMIT 1")
        if not filas:
            return None
        filas[0]["uso_cpu"] = json.loads(filas[0]["uso_cpu"]) if filas[0]["uso_cpu"] else []
        return filas[0]


if __name__ == "__main__":
    db = BaseDatos()
    print(f"Base de datos: {db.ruta}\n")
    print(f"{'id':>4} {'bench':>5}  {'fecha':<19}  {'versión':<10} {'n':>2} "
          f"{'tiempo':>8} {'speedup':>8} {'T máx':>6} {'thr':>4}")
    for e in reversed(db.ultimas_ejecuciones(15)):
        print(f"{e['id']:>4} {e['id_benchmark']:>5}  {e['fecha']:<19}  {e['version']:<10} "
              f"{e['n_trabajadores']:>2} {e['tiempo_s']:>8.3f} {e['speedup'] or 0:>8.2f} "
              f"{e['temp_cpu_max'] or 0:>6.1f} {e['throttling'] if e['throttling'] is not None else '-':>4}")
    ultima = db.ultima_lectura()
    print(f"\nLecturas de los últimos 10 min: {len(db.lecturas_desde(10))}")
    if ultima:
        print(f"Última lectura: {ultima['fecha']}  CPU {ultima['temp_cpu']} °C  uso {ultima['uso_cpu']}")
