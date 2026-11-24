# PiBench: plan del proyecto

Proyecto de prácticas de **Arquitectura de Computadores** (curso 2026-2027), grupo 10.
Aplicación en Python para una **Raspberry Pi 5** que mide cuánto se gana al paralelizar un cálculo
(secuencial frente a hilos frente a procesos) y lo muestra con LEDs, una web y un bot de Telegram.

> **Instrucciones para Claude Code**
> - Trabaja **fase a fase**, en orden. No empieces una fase sin terminar y probar la anterior.
> - Al terminar cada fase: marca sus casillas en este archivo, ejecuta las pruebas y haz un commit
>   con un mensaje claro (por ejemplo `fase 2: control de LEDs y pulsadores`).
> - El código debe poder **ejecutarse en un portátil sin Raspberry** (modo simulado, ver "Desarrollo sin hardware").
> - Si algo del hardware no está claro (pines, modelo del sensor), **pregunta** en lugar de suponer.
> - Comentarios y textos de la web en **castellano**. Código claro y sencillo: lo tiene que entender
>   y defender un grupo de estudiantes.

---

## 1. Requisitos de la asignatura

**Mínimo obligatorio (enunciado):**
- Al menos **2 procesos**, con sentido en el proyecto.
- Al menos **2 hilos**.
- **1 LED y 1 pulsador.**
- Servidor web básico (Flask) o interfaz gráfica local.

**Para subir nota (lo incluimos todo):**
- Más procesos e hilos que aporten valor.
- Funcionamiento sólido, sin errores (cierre limpio, sin procesos colgados).
- Web con **base de datos** y visualización **en tiempo real**.
- Sensores y actuadores adicionales (segundo LED-pulsador y sensor de temperatura y humedad).
- Demo funcional el día de la presentación.
- Uso de **GitHub**.
- Elemento extra: **bot de Telegram**.

**Evaluación:** CE3 paralelismo (1,5 puntos) + CE4 proyecto y defensa (2,5 puntos) = 4 puntos de la asignatura.

---

## 2. Hardware

| Elemento | Uso | Conexión |
|---|---|---|
| Raspberry Pi 5 (4 GB) + fuente oficial de 27 W | Ejecuta todo | — |
| Grove LED-pulsador 1 | LED de **estado** del benchmark + pulsador para **lanzar** el benchmark | Cable Grove a dupont, directo a GPIO |
| Grove LED-pulsador 2 | LED de **alerta** de temperatura + pulsador para **elegir nº de procesos** (1→2→3→4) | Cable Grove a dupont, directo a GPIO |
| Grove Temperature & Humidity Sensor V2.0 (**DHT20**, I2C, dirección `0x38`) | Temperatura y humedad del ambiente | Cable Grove a dupont, pines I2C: SDA = GPIO2 (pin 3), SCL = GPIO3 (pin 5) |
| Tarjeta microSD (≥ 16 GB) | Raspberry Pi OS | — |

**Pines GPIO propuestos** (todos configurables en `config.py`; comprobar en la wiki de Seeed qué hilo del
cable Grove es el LED y cuál el botón en el módulo LED-pulsador):

| Señal | GPIO |
|---|---|
| LED estado | GPIO17 |
| Pulsador lanzar | GPIO27 |
| LED alerta | GPIO22 |
| Pulsador nº procesos | GPIO23 |

**Avisos importantes de la Raspberry Pi 5:**
- **No usar `RPi.GPIO`** (no funciona en la Pi 5). Usar **`gpiozero`** (con `lgpio` por debajo),
  que viene con Raspberry Pi OS.
- Activar I2C: `sudo raspi-config` → Interface Options → I2C. Comprobar el sensor con `i2cdetect -y 1` (debe salir `38`).
- La Pi 5 **se calienta** con los 4 núcleos al 100 % y baja la frecuencia (*throttling*) hacia 85 °C.
  Lo medimos y lo usamos en la defensa (afecta al speedup).
- Si el DHT20 da problemas, el DHT20 es compatible con el AHT20: probar la librería `adafruit-circuitpython-ahtx0`
  o leerlo directamente con `smbus2`.

---

## 3. Arquitectura

### Procesos

| Proceso | Qué hace | Por qué es un proceso aparte |
|---|---|---|
| **Principal / controlador** (`main.py`) | Arranca todo, gestiona el hardware con hilos y guarda en la base de datos | Coordina el resto y es el único que toca los GPIO |
| **Benchmark** (`benchmark_worker.py`) | Espera órdenes y ejecuta el benchmark; dentro usa un `multiprocessing.Pool` de N procesos | Pone la CPU al 100 %: si estuviera junto al resto, bloquearía la web y los pulsadores |
| **Web** (`web/app.py`, Flask) | Sirve el dashboard y la API | Independiente: si la web falla, el hardware y el benchmark siguen funcionando |

> En la propuesta entregada hablamos de 2 procesos (benchmark y web). Con el controlador son 3, más el
> *pool* de trabajadores. Es coherente con la propuesta y se explica bien en la defensa.

### Hilos (en el proceso controlador, con `threading`)

Hilos **propios**, no solo los internos de `gpiozero`, cada uno con una función clara:

1. **Hilo pulsadores:** detecta pulsaciones y manda órdenes al benchmark (lanzar, cambiar nº de procesos).
2. **Hilo LEDs:** parpadeo del LED de estado mientras hay benchmark; LED de alerta según la temperatura.
3. **Hilo monitor:** cada 2 s lee la temperatura de la CPU, el uso por núcleo, el *throttling* y el sensor DHT20, y lo guarda.
4. **Hilo resultados:** recibe los resultados del proceso benchmark, los guarda en SQLite y los pasa al notificador.
5. **Hilo Telegram:** envía los mensajes de una `queue.Queue` sin bloquear al resto (si no hay Internet, no pasa nada).

Sincronización: un `threading.Event` global `parar` para el cierre limpio, un `Lock` para el estado
compartido (por ejemplo `benchmark_en_curso`) y colas (`queue.Queue`) entre hilos.

### Comunicación

```
             cola_ordenes (mp.Queue)             cola_resultados (mp.Queue)
 Pulsadores ─┐                    ┌──────────────┐                     ┌─ Hilo resultados ─► SQLite
 Web ────────┴──────────────────► │  Benchmark   │ ──────────────────► │                  └─► Telegram
                                  │ (Pool N proc)│                     │
                                  └──────────────┘
 Hilo monitor ─► SQLite (tabla lecturas) ◄── Web lee y muestra en tiempo real
```

- **Web → benchmark:** la web pone un evento en `cola_eventos`, la misma cola que usan los pulsadores;
  el hilo pulsadores del controlador lo convierte en orden. Así la web y el pulsador siguen el mismo camino
  (y se ignoran igual si hay un benchmark en curso).
- **Estado del benchmark para la web:** `benchmark_en_curso` y `n_procesos` en memoria compartida
  (`multiprocessing.Value`): el controlador escribe y la web lee.
- **Estado en tiempo real:** el controlador escribe las lecturas en SQLite y la web las consulta cada segundo
  (`fetch` a `/api/estado`). Es sencillo y fácil de explicar.
- **SQLite** en modo WAL, para que la web pueda leer mientras el controlador escribe.

---

## 4. El benchmark

- **Cálculo:** fractal de Mandelbrot (por ejemplo 800 × 600 píxeles, 1.000 iteraciones máximo).
  Cada píxel es independiente, así que se reparte por **bloques de filas** entre los trabajadores.
- **Versiones:**
  1. **Secuencial:** un bucle normal.
  2. **Hilos:** `ThreadPoolExecutor(max_workers=4)`. Por el GIL apenas mejora (eso es lo que queremos demostrar).
  3. **Procesos:** `multiprocessing.Pool(N)` con N elegido con el pulsador 2 (1, 2, 3 o 4).
- **Barrido de speedup:** una opción que ejecuta procesos con N = 1, 2, 3 y 4 para dibujar la gráfica de speedup frente a núcleos.
- **Medidas por ejecución:** tiempo (`time.perf_counter`), speedup (`t_secuencial / t_version`),
  temperatura de la CPU al inicio y máxima, si hubo *throttling* (`vcgencmd get_throttled`) y temperatura ambiente.
- **Comprobación de corrección:** las tres versiones deben dar **la misma imagen** (comparar el resultado).
- Guardar la imagen generada como PNG (con Pillow) para enseñarla en la web.
- El tamaño debe ser configurable: en la Pi, que la versión secuencial tarde unos **5–10 s**.

---

## 5. Base de datos (SQLite)

```sql
CREATE TABLE ejecuciones (
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

CREATE TABLE lecturas (
    id INTEGER PRIMARY KEY,
    fecha TEXT NOT NULL,
    temp_cpu REAL,
    uso_cpu TEXT,                   -- JSON con el % de cada núcleo
    temp_ambiente REAL,
    humedad REAL
);
```

Borrar lecturas de más de 24 h al arrancar, para que la base de datos no crezca sin límite.

---

## 6. Web (Flask)

- **`/`**: dashboard con:
  - estado actual (benchmark en curso o no, nº de procesos elegido);
  - temperatura de la CPU, temperatura ambiente, humedad y uso de cada núcleo, **en tiempo real**;
  - botones "Lanzar benchmark" y "Barrido 1–4 procesos";
  - gráfica de tiempos por versión y gráfica de speedup frente a nº de procesos (**Chart.js**);
  - tabla con el histórico de ejecuciones;
  - la última imagen del fractal.
- **API JSON:** `GET /api/estado`, `GET /api/ejecuciones`, `GET /api/lecturas?minutos=10`, `POST /api/lanzar`, `POST /api/barrido`.
- Ejecutar con `debug=False` y sin el *reloader* (el *reloader* duplica procesos).

---

## 7. Bot de Telegram

- Crear el bot con **@BotFather** (`/newbot`) y obtener el **token**; obtener el **chat_id**.
- Token y chat_id en un archivo **`.env`** (cargado con `python-dotenv`), **nunca** en el repositorio.
- Mensaje al terminar cada benchmark: tiempos, speedup y temperatura máxima.
- Opcional: aviso cuando se enciende el LED de alerta.
- Envío con `requests.post(..., timeout=5)` dentro de `try/except`: sin Internet, se registra el error y el programa sigue.
- Si `.env` no tiene token, el notificador se desactiva solo.

---

## 8. Estructura del repositorio

```
pibench/
├── PLAN.md
├── README.md                 # cómo instalar, conectar y ejecutar
├── requirements.txt
├── .env.example              # TELEGRAM_TOKEN=, TELEGRAM_CHAT_ID=
├── .gitignore                # .env, *.db, __pycache__, venv/, resultados/
├── config.py                 # pines, tamaño del fractal, umbral de temperatura, intervalos
├── main.py                   # proceso controlador: arranca procesos e hilos, cierre limpio
├── benchmark/
│   ├── mandelbrot.py         # cálculo de un bloque de filas (función pura)
│   ├── versiones.py          # secuencial, hilos, procesos
│   └── benchmark_worker.py   # proceso que escucha cola_ordenes
├── hardware/
│   ├── gpio.py               # LEDs y pulsadores con gpiozero
│   ├── sensores.py           # temp CPU, uso CPU, throttling, DHT20 (con modo simulado)
│   └── hilos.py              # hilos de pulsadores, LEDs y monitor
├── datos/
│   └── db.py                 # SQLite: crear tablas, insertar, consultar
├── notificador/
│   └── telegram.py           # hilo + cola de mensajes
├── web/
│   ├── app.py
│   ├── templates/index.html
│   └── static/ (app.js, estilos.css)
└── tests/
    ├── test_mandelbrot.py    # las 3 versiones dan el mismo resultado
    ├── test_db.py
    └── test_gpio_mock.py     # LEDs y pulsadores con MockFactory
```

**Dependencias:** `flask`, `psutil`, `pillow`, `requests`, `python-dotenv`, `smbus2` (o `adafruit-circuitpython-ahtx0`), `pytest`.
En la Pi, crear el entorno virtual con `python3 -m venv --system-site-packages venv` para poder usar el `gpiozero` y el `lgpio` del sistema.

---

## 9. Desarrollo sin hardware

- Variable de entorno `PIBENCH_SIMULADO=1`:
  - `gpiozero` con `GPIOZERO_PIN_FACTORY=mock` (LEDs y pulsadores simulados);
  - el sensor DHT20 devuelve valores inventados;
  - la temperatura de la CPU se lee con `psutil` si existe, o se simula.
- En modo simulado, la web permite "pulsar" los botones, para probar todo en el portátil.

---

## 10. Fases

### Fase 0: Preparación
- [x] Repositorio en GitHub creado, con `.gitignore`, `README.md` y `requirements.txt`.
- [x] Raspberry Pi OS instalado en la Pi 5, SSH activado, I2C activado.
- [x] Entorno virtual creado (`--system-site-packages`) y dependencias instaladas.

### Fase 1: Benchmark (en el portátil)
- [x] `mandelbrot.py`: función que calcula un bloque de filas.
- [x] Versiones secuencial, con hilos y con procesos (N configurable).
- [x] Test: las tres versiones dan exactamente la misma imagen.
- [x] Script de prueba que imprime tiempos y speedup.
- **Hecho cuando:** en el portátil, la versión con procesos es claramente más rápida y la de hilos no.

### Fase 2: GPIO
- [x] `gpio.py` con los 2 LEDs y los 2 pulsadores (`gpiozero`), pines desde `config.py`.
- [x] Prueba con `MockFactory` en el portátil.
- [x] Prueba real en la Pi: cada pulsador enciende su LED.

### Fase 3: Procesos e hilos
- [x] `benchmark_worker.py`: proceso que espera órdenes en `cola_ordenes` y devuelve resultados en `cola_resultados`.
- [x] Hilos de pulsadores, LEDs, monitor y resultados en el controlador.
- [x] Pulsador 1 lanza el benchmark; el LED de estado parpadea durante el cálculo y se queda fijo al acabar.
- [x] Pulsador 2 cambia el nº de procesos (1→4) y el LED parpadea tantas veces como el número elegido.
- [x] Ignorar pulsaciones mientras hay un benchmark en curso.
- [x] **Cierre limpio** con Ctrl+C: se paran hilos y procesos y se apagan los LEDs.

### Fase 4: Base de datos
- [x] `db.py` con las tablas de la sección 5 (modo WAL).
- [x] El controlador guarda ejecuciones y lecturas.
- [x] Tests de inserción y consulta.

### Fase 5: Web
- [x] Flask en su propio proceso, con la API de la sección 6.
- [x] Dashboard con estado en tiempo real, botones, gráficas (Chart.js), tabla e imagen del fractal.
- [x] Lanzar el benchmark desde la web funciona igual que desde el pulsador.

### Fase 6: Sensor DHT20
- [ ] Conectar por I2C y comprobar con `i2cdetect -y 1`.
- [ ] Leer temperatura y humedad en el hilo monitor; si el sensor falla, seguir funcionando sin él.
- [ ] Mostrar la temperatura ambiente junto a la de la CPU en la web.
- [ ] LED de alerta cuando la temperatura de la CPU pase del umbral (`config.py`, por ejemplo 75 °C).

### Fase 7: Bot de Telegram
- [ ] Crear el bot, guardar el token y el chat_id en `.env`.
- [ ] Hilo notificador con cola; mensaje al terminar cada benchmark.
- [ ] Probar sin Internet: el programa no se cuelga.
- [ ] Probar en la red de la universidad.

### Fase 8: Robustez y pulido
- [ ] Probar 20 benchmarks seguidos sin errores ni procesos colgados.
- [ ] Logs claros (módulo `logging`) en lugar de `print`.
- [ ] Servicio `systemd` opcional para arrancar al encender la Pi.
- [ ] README completo: conexiones (con foto o esquema), instalación y ejecución.

### Fase 9: Defensa
- [ ] Gráfica de speedup frente a nº de procesos (1–4) con datos reales de la Pi.
- [ ] Explicación del GIL: por qué los hilos no aceleran el cálculo pero sí sirven para la entrada/salida.
- [ ] Por qué no se llega a un speedup de 4 exacto: reparto del trabajo, coste de crear procesos y *throttling* térmico.
- [ ] Diagrama de procesos e hilos (el de la sección 3).
- [ ] Guion de la demo: pulsar → LED parpadea → web en tiempo real → mensaje de Telegram → resultados.
- [ ] Plan B si falla la red: la demo funciona igual sin Telegram.

---

## 11. Riesgos

| Riesgo | Solución |
|---|---|
| No hay Internet en clase (Telegram) | `try/except` y demo sin Telegram; la web va por red local o en la propia Pi |
| El sensor no funciona o no lo dan | El monitor sigue sin él; la web muestra "sin sensor" |
| *Throttling* por calor | Medirlo y explicarlo; si molesta, usar disipador o ventilador |
| `RPi.GPIO` no funciona en la Pi 5 | Usar `gpiozero` desde el principio |
| Procesos huérfanos al cerrar | Cierre con `Event`, `join` con *timeout* y `terminate` como último recurso |
