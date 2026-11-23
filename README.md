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

| Señal | GPIO |
|---|---|
| LED estado | GPIO17 |
| Pulsador lanzar | GPIO27 |
| LED alerta | GPIO22 |
| Pulsador nº procesos | GPIO23 |
| DHT20 SDA / SCL | GPIO2 (pin 3) / GPIO3 (pin 5) |

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

_La aplicación completa (LEDs, web, Telegram) llegará en las fases siguientes._

## Tests

```bash
pytest
```
