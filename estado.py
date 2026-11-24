"""Estado compartido entre los hilos del controlador.

Varios hilos leen y escriben estos datos a la vez, así que siempre se accede
a ellos con `with estado.lock:`.
"""

import threading

import config


class Estado:
    def __init__(self):
        self.lock = threading.Lock()

        # Benchmark
        self.benchmark_en_curso = False
        self.id_benchmark = None            # nº del benchmark en curso (agrupa sus ejecuciones)
        self.hay_resultado = False          # para dejar el LED de estado fijo al acabar
        self.n_procesos = config.N_PROCESOS_INICIAL

        # Últimas lecturas del hilo monitor
        self.temp_cpu = None
        self.uso_cpu = []
        self.throttling = None

        # Medidas de la versión que se está ejecutando ahora mismo:
        # {"temp_cpu_inicio": .., "temp_cpu_max": .., "throttling": ..} o None.
        self.medicion = None
