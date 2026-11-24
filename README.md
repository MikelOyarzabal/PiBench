# PiBench

Proyecto de prácticas de **Arquitectura de Computadores** (curso 2026-2027), grupo 10.

Aplicación en Python para una **Raspberry Pi 5** que mide cuánto se gana al paralelizar un cálculo
(fractal de Mandelbrot): versión **secuencial**, con **hilos** y con **procesos**. Los resultados se
muestran con LEDs, una web en tiempo real (Flask) y un bot de Telegram.

> Proyecto en desarrollo. El plan completo está en [PLAN.md](PLAN.md).

## Hardware

- Raspberry Pi 5 (4 GB) con fuente oficial de 27 W.
- 2 × Grove LED-pulsador.
- Grove Temperature & Humidity Sensor V2.0 (DHT20, I2C, dirección `0x38`).

Módulos Grove "Red LED Button v1.0": hilo **amarillo = LED**, **blanco = pulsador**
(activo a nivel bajo), rojo = VCC, negro = GND.

> ⚠️ Alimentar los módulos a **3,3 V** (pines 1 o 17), nunca a 5 V: los GPIO de la Pi solo admiten 3,3 V.

| Módulo | Señal | GPIO | Pin físico |
|---|---|---|---|
| 1 | LED estado | GPIO17 | 11 |
| 1 | Pulsador lanzar | GPIO27 | 13 |
| 1 | VCC / GND | 3,3 V / GND | 1 / 6 |
| 2 | LED alerta | GPIO22 | 15 |
| 2 | Pulsador nº procesos | GPIO23 | 16 |
| 2 | VCC / GND | 3,3 V / GND | 17 / 9 |
| DHT20 | SDA / SCL | GPIO2 / GPIO3 | 3 / 5 |

Los pines se cambian en `config.py`.

## Preparar la Raspberry Pi

1. Instalar **Raspberry Pi OS** (64 bits) con Raspberry Pi Imager. En los ajustes del Imager,
   activar **SSH** y configurar usuario, contraseña y Wi-Fi.
2. Activar **I2C**: `sudo raspi-config` → *Interface Options* → *I2C* → *Yes*.
3. Comprobar el sensor (cuando esté conectado):

   ```bash
   sudo apt install -y i2c-tools
   i2cdetect -y 1        # debe aparecer 38
   ```

## Instalación

### En la Raspberry Pi

```bash
git clone https://github.com/MikelOyarzabal/PiBench.git
cd PiBench
python3 -m venv --system-site-packages venv   # para usar gpiozero y lgpio del sistema
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                           # y rellenar el token de Telegram
```

### En el portátil (sin hardware)

```bash
python -m venv venv
source venv/bin/activate          # en Windows: venv\Scripts\activate
pip install -r requirements.txt gpiozero
```

Ejecutar con la variable `PIBENCH_SIMULADO=1` para simular LEDs, pulsadores y sensores.

## Ejecución

Prueba del benchmark (secuencial, hilos y procesos, con tiempos y speedup):

```bash
python -m benchmark.prueba              # 4 procesos
python -m benchmark.prueba --barrido    # procesos con N = 1, 2, 3 y 4
```

El tamaño del fractal se ajusta en `config.py`. La imagen se guarda en `resultados/mandelbrot.png`.

Prueba de LEDs y pulsadores (cada pulsador enciende su LED; Ctrl+C para salir):

```bash
python -m hardware.prueba_gpio                     # en la Raspberry Pi
PIBENCH_SIMULADO=1 python -m hardware.prueba_gpio  # en el portátil (simulado)
```

En PowerShell, el modo simulado se activa con `$env:PIBENCH_SIMULADO = "1"`.

### Aplicación (controlador + proceso benchmark)

```bash
python main.py                       # en la Raspberry Pi
PIBENCH_SIMULADO=1 python main.py    # en el portátil: teclas l (lanzar), p (nº procesos), q (salir)
```

- **Pulsador 1:** lanza el benchmark (secuencial, hilos y procesos con el N elegido).
  El LED 1 parpadea durante el cálculo y se queda fijo al acabar.
- **Pulsador 2:** cambia el nº de procesos (1 → 2 → 3 → 4 → 1); el LED 2 parpadea N veces.
- Mientras hay un benchmark en curso, las pulsaciones se ignoran.
- **Ctrl+C** cierra todo de forma ordenada: hilos, proceso benchmark y LEDs.

Los resultados y las lecturas de los sensores se guardan en `pibench.db` (SQLite). Para verlos:

```bash
python -m datos.db
```

### Web

`main.py` también arranca la web (proceso aparte, Flask) en el puerto 5000:

- En la Pi: desde el portátil, `http://grupo10.local:5000` (o con la IP de la Pi).
- En modo simulado: `http://localhost:5000`.

Muestra el estado y los sensores en tiempo real, botones para lanzar el benchmark, el barrido
1–4 y cambiar el nº de procesos, gráficas (temperatura, tiempos, speedup), el histórico y el fractal.

Chart.js se carga desde `web/static/vendor/chart.umd.min.js` si existe (funciona sin Internet)
y, si no, desde el CDN. Para tener la copia local (una vez, y subirla al repositorio):

```powershell
New-Item -ItemType Directory -Force web\static\vendor
Invoke-WebRequest https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js -OutFile web\static\vendor\chart.umd.min.js
```

_El bot de Telegram llegará en la fase 7._

## Tests

```bash
pytest
```
