# PiBench

Proyecto de prácticas de **Arquitectura de Computadores** (curso 2026-2027), grupo 10.

Aplicación en Python para una **Raspberry Pi 5** que mide cuánto se gana al paralelizar un cálculo
(fractal de Mandelbrot): versión **secuencial**, con **hilos** y con **procesos** (1 a 4). Los
resultados se ven en LEDs, en una web en tiempo real y por Telegram.

Resultado típico en la Pi 5 (800×600, 500 iteraciones):

| Versión | Tiempo | Speedup |
|---|---|---|
| Secuencial | 7,6 s | 1,00 |
| Hilos (4) | 7,6 s | 1,00 (el GIL no deja calcular en paralelo) |
| Procesos (2) | 3,8 s | 2,0 |
| Procesos (4) | 2,0 s | 3,85 |

El plan completo y las decisiones de diseño están en [PLAN.md](PLAN.md).

## Arquitectura

```
 Pulsadores ─┐                         ┌──────────────────────┐
 Web ────────┴─► cola_eventos ─► hilo  │ Proceso BENCHMARK    │
                                 puls. ├► cola_ordenes ──────►│  Pool de N procesos  │
                                       │                      └──────────┬───────────┘
 ┌──────────── Proceso CONTROLADOR (main.py) ──────────┐                 │ cola_resultados
 │ hilos: pulsadores · LEDs · monitor · resultados ·   │◄────────────────┘
 │        telegram                                     │
 └──────────┬──────────────────────────┬───────────────┘
            │ SQLite (modo WAL)        │ memoria compartida (en curso, nº procesos)
            ▼                          ▼
 ┌──────────── Proceso WEB (Flask) ────────────────────┐
 │ dashboard, API, gráficas, imagen del fractal        │
 └─────────────────────────────────────────────────────┘
```

- **3 procesos** (controlador, benchmark, web) + el **Pool** de 1–4 trabajadores durante el cálculo.
- **5 hilos** propios en el controlador (+ uno más de teclado en modo simulado).
- **3 formas de comunicación entre procesos:** colas (`multiprocessing.Queue`), memoria compartida
  (`multiprocessing.Value`) y SQLite.

## Hardware

- Raspberry Pi 5 (4 GB) con fuente oficial de 27 W.
- 2 × Grove "Red LED Button v1.0": hilo **amarillo = LED**, **blanco = pulsador** (activo a nivel
  bajo), rojo = VCC, negro = GND.
- Grove "Temperature & Humidity Sensor v1.2" (**DHT11**: pines GND, VCC, NC, SIG).

> ⚠️ Todo a **3,3 V**, nunca a 5 V (pines 2 y 4): los GPIO de la Pi solo admiten 3,3 V.

### Conexiones

El **pin 1** está en la fila interior, en el extremo más alejado de los puertos USB y Ethernet
(por debajo, su soldadura es cuadrada). Fila interior = impares, fila del borde = pares.

```
                         (impares)  (pares)
 3,3 V  ◄ Módulo 1 VCC      [ 1]    [ 2]   5 V  ✗ nada
                            [ 3]    [ 4]   5 V  ✗ nada
                            [ 5]    [ 6]   GND    ◄ Módulo 1 GND
 GPIO4  ◄ Sensor SIG        [ 7]    [ 8]
 GND    ◄ Módulo 2 GND      [ 9]    [10]
 GPIO17 ◄ Módulo 1 LED      [11]    [12]
 GPIO27 ◄ Módulo 1 pulsador [13]    [14]   GND    ◄ Sensor GND
 GPIO22 ◄ Módulo 2 LED      [15]    [16]   GPIO23 ◄ Módulo 2 pulsador
 3,3 V  ◄ Módulo 2 VCC      [17]    [18]
            ...
 GPIO5  ◄ Sensor VCC        [29]    [30]
```

| Componente | Señal | GPIO | Pin físico |
|---|---|---|---|
| Módulo 1 | LED de estado | GPIO17 | 11 |
| Módulo 1 | Pulsador "lanzar" | GPIO27 | 13 |
| Módulo 1 | VCC / GND | 3,3 V / GND | 1 / 6 |
| Módulo 2 | LED de alerta | GPIO22 | 15 |
| Módulo 2 | Pulsador "nº de procesos" | GPIO23 | 16 |
| Módulo 2 | VCC / GND | 3,3 V / GND | 17 / 9 |
| Sensor | SIG (datos) | GPIO4 | 7 |
| Sensor | VCC / GND | GPIO5 a nivel alto / GND | 29 / 14 |

El sensor se alimenta desde GPIO5 (el programa lo pone a 3,3 V al arrancar) porque los dos pines de
3,3 V ya los usan los módulos; consume menos de 2,5 mA. Su hilo blanco (NC) no se conecta.
**Ojo:** los cables dupont de los adaptadores no tienen por qué coincidir en color con los del Grove;
seguir cada hilo a través del conector. Los pines se cambian en `config.py`.

## Preparar la Raspberry Pi

1. Instalar **Raspberry Pi OS** (64 bits) con Raspberry Pi Imager. En los ajustes del Imager,
   activar **SSH** y configurar usuario, contraseña y Wi-Fi.
2. Actualizar el sistema: `sudo apt update && sudo apt full-upgrade -y`.
3. Activar el controlador del sensor DHT11 y reiniciar:

   ```bash
   echo "dtoverlay=dht11,gpiopin=4" | sudo tee -a /boot/firmware/config.txt
   sudo reboot
   ```

## Instalación

### En la Raspberry Pi

```bash
git clone https://github.com/MikelOyarzabal/PiBench.git
cd PiBench
python3 -m venv --system-site-packages venv   # para usar gpiozero y lgpio del sistema
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                           # y rellenar el token de Telegram en .env
```

> 🔒 **El token de Telegram va solo en `.env`, nunca en `.env.example`.**
> `.env` está en `.gitignore` y no se sube a GitHub; `.env.example` sí se sube y debe quedarse
> con los valores vacíos (solo sirve de plantilla). Si un token llega a subirse, aunque luego se
> borre sigue en el historial de git: hay que **revocarlo** en @BotFather (`/revoke`) y crear otro.

Comprobar el hardware:

```bash
python -m hardware.prueba_gpio   # cada pulsador enciende su LED (Ctrl+C para salir)
python -m hardware.sensores      # 10 lecturas del sensor de ambiente
```

### En el portátil (sin hardware)

```bash
python -m venv venv
source venv/bin/activate          # en Windows: venv\Scripts\activate
pip install -r requirements.txt gpiozero
```

Con la variable `PIBENCH_SIMULADO=1` se simulan LEDs, pulsadores y sensores
(en PowerShell: `$env:PIBENCH_SIMULADO = "1"`).

## Uso

```bash
python main.py                       # en la Raspberry Pi
PIBENCH_SIMULADO=1 python main.py    # en el portátil: teclas l (lanzar), p (nº procesos), q (salir)
```

> ⚠️ **Si está instalado el servicio systemd, páralo antes de ejecutar `main.py` a mano:**
> `sudo systemctl stop pibench`. Si no, habría dos PiBench a la vez peleándose por los pines
> GPIO y por el puerto 5000. Al acabar, se vuelve a arrancar con `sudo systemctl start pibench`.

- **Pulsador 1:** lanza el benchmark (secuencial, hilos y procesos con el N elegido).
  El LED 1 parpadea durante el cálculo y se queda fijo al acabar.
- **Pulsador 2:** cambia el nº de procesos (1 → 2 → 3 → 4 → 1); el LED 2 parpadea N veces.
- **LED 2 fijo:** alerta, la CPU ha llegado a 75 °C (se apaga al bajar de 72 °C; ajustable en `config.py`).
  Por Telegram se avisa como mucho una vez cada 10 minutos (`INTERVALO_AVISOS_ALERTA_S`).
- Mientras hay un benchmark en curso, las pulsaciones se ignoran.
- **Ctrl+C** (o `kill`, o `systemctl stop`) cierra todo de forma ordenada: hilos, procesos y LEDs.

### Web

En el puerto 5000: desde el portátil, `http://grupo10.local:5000` (o con la IP de la Pi);
en modo simulado, `http://localhost:5000`.

Estado y sensores en tiempo real, botones (lanzar, barrido 1–4 procesos, cambiar nº de procesos),
gráficas de temperatura, tiempos y speedup, histórico de ejecuciones y el último fractal (cada
benchmark con una paleta de color distinta). Chart.js está copiado en `web/static/vendor/`, así que
funciona sin Internet.

### Telegram

Si `.env` tiene `TELEGRAM_TOKEN` y `TELEGRAM_CHAT_ID`, PiBench envía un mensaje al arrancar, un
resumen al terminar cada benchmark (tiempos, speedup, temperaturas) y un aviso cuando se enciende
el LED de alerta. Si falta el token o no hay Internet, el programa funciona igual: solo deja un
aviso en el log.

### Datos

Las ejecuciones y las lecturas de los sensores se guardan en `pibench.db` (SQLite). Para verlas:

```bash
python -m datos.db
```

### Benchmark solo, sin la aplicación

```bash
python -m benchmark.prueba              # 4 procesos
python -m benchmark.prueba --barrido    # procesos con N = 1, 2, 3 y 4
```

## Arranque automático (servicio systemd)

```bash
sudo cp deploy/pibench.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now pibench      # arranca ya y en cada encendido
journalctl -u pibench -f                 # ver el log (Ctrl+C para dejar de verlo)
sudo systemctl stop pibench              # parar (cierre limpio)
sudo systemctl disable pibench           # que no arranque al encender
```

Mientras el servicio está en marcha, no ejecutes `python main.py` a mano (los dos querrían los
mismos pines y el puerto 5000): páralo antes con `sudo systemctl stop pibench`.

## Pruebas

```bash
pytest                                   # tests (en el portátil o en la Pi)
python -m herramientas.prueba_estres     # con main.py en marcha: 20 benchmarks seguidos
```

La prueba de estrés lanza los benchmarks por la API web y comprueba que terminan, que se guardan sus
resultados, que no quedan procesos colgados y que la memoria no crece.

## Estructura

```
main.py                     controlador: arranca procesos e hilos, cierre limpio
config.py                   pines, tamaño del fractal, umbrales, rutas
estado.py                   estado compartido entre hilos (y memoria compartida con la web)
registro.py                 formato de los logs (proceso/hilo en cada línea)
benchmark/
  mandelbrot.py             cálculo de un bloque de filas y paletas de color
  versiones.py              secuencial, hilos, procesos
  benchmark_worker.py       proceso benchmark (órdenes y resultados por colas)
  prueba.py                 benchmark desde la terminal
hardware/
  gpio.py                   LEDs, pulsadores y alimentación del sensor (gpiozero)
  sensores.py               temperatura CPU, uso, throttling y DHT11
  hilos.py                  hilos de pulsadores, LEDs y monitor
  prueba_gpio.py            prueba de LEDs y pulsadores
datos/db.py                 SQLite: ejecuciones y lecturas
notificador/telegram.py     hilo + cola de mensajes de Telegram
web/                        Flask: app.py, plantilla, JS, CSS y Chart.js
herramientas/prueba_estres.py
deploy/pibench.service      servicio systemd
tests/                      pytest
```

## Problemas frecuentes

| Problema | Solución |
|---|---|
| `ssh pi@grupo10.local` no conecta | Probar con la IP (`192.168.137.31` con el cable al portátil). |
| La Pi no tiene Internet (cable al portátil) | En Windows: `ncpa.cpl` → Wi-Fi → Propiedades → Uso compartido → permitir y elegir el adaptador Ethernet (desmarcar y volver a marcar si ya estaba). |
| `apt` dice "Could not get lock" | Lo está usando PackageKit: esperar o `sudo systemctl stop packagekit`. |
| La web dice "sin sensor" | Falta el `dtoverlay` en `/boot/firmware/config.txt` o el cableado; probar `python -m hardware.sensores`. |
| No llegan mensajes de Telegram | Mirar el log: "Telegram desactivado" (falta `.env`) o "no se pudo enviar" (sin Internet). |
| `Address already in use` o pines ocupados | Ya hay otro PiBench en marcha (¿el servicio?): `sudo systemctl stop pibench`. |
