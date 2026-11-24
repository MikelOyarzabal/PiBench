"""Estado compartido entre los hilos del controlador (y, en parte, con la web).

Varios hilos leen y escriben estos datos a la vez, así que siempre se accede
a ellos con `with estado.lock:`.

`benchmark_en_curso` y `n_procesos` también los necesita la web, que es otro
proceso. Por eso se guardan en **memoria compartida** (`multiprocessing.Value`):
el controlador los escribe (siempre con el lock) y la web solo los lee.
"""

import multiprocessing as mp
import threading

import config


class Estado:
    def __init__(self):
        self.lock = threading.Lock()

        # Memoria compartida con el proceso web. lock=False porque ya protegemos
        # las escrituras con self.lock y la web solo lee un número.
        self.en_curso_compartido = mp.Value("b", 0, lock=False)
        self.n_procesos_compartido = mp.Value("i", config.N_PROCESOS_INICIAL, lock=False)

        # Benchmark
        self.id_benchmark = None            # nº del benchmark en curso (agrupa sus ejecuciones)
        self.siguiente_id_benchmark = 1     # el controlador lo pone al arrancar (desde SQLite)
        self.hay_resultado = False          # para dejar el LED de estado fijo al acabar

        # Últimas lecturas del hilo monitor
        self.temp_cpu = None
        self.uso_cpu = []
        self.throttling = None

        # Medidas de la versión que se está ejecutando ahora mismo:
        # {"temp_cpu_inicio": .., "temp_cpu_max": .., "throttling": ..} o None.
        self.medicion = None

    # Propiedades: el resto del código usa estado.benchmark_en_curso y
    # estado.n_procesos como si fueran atributos normales.

    @property
    def benchmark_en_curso(self):
        return bool(self.en_curso_compartido.value)

    @benchmark_en_curso.setter
    def benchmark_en_curso(self, valor):
        self.en_curso_compartido.value = 1 if valor else 0

    @property
    def n_procesos(self):
        return self.n_procesos_compartido.value

    @n_procesos.setter
    def n_procesos(self, valor):
        self.n_procesos_compartido.value = valor
