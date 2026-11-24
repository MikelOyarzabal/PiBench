// Dashboard de PiBench: pide datos a la API cada poco tiempo y actualiza la página.

const $ = (id) => document.getElementById(id);
const color = (nombre) => getComputedStyle(document.documentElement).getPropertyValue(nombre).trim();

const NOMBRES = { secuencial: "Secuencial", hilos: "Hilos", procesos: "Procesos" };
const fmt = (x, decimales = 1) => (x === null || x === undefined ? "—" : Number(x).toFixed(decimales));

let graficas = {};          // se crean cuando Chart.js está cargado
let ultimoBenchmark = null; // para saber cuándo hay resultados nuevos
let enCursoAntes = false;
let imagenMostrada;         // nº de benchmark de la imagen que se está viendo

// ---------- Llamadas a la API ----------

async function pedir(url, opciones) {
  const respuesta = await fetch(url, opciones);
  return { codigo: respuesta.status, datos: await respuesta.json() };
}

async function enviarOrden(ruta) {
  try {
    const { datos } = await pedir(ruta, { method: "POST" });
    $("mensaje").textContent = datos.mensaje;
    pintarEstado(datos);
  } catch (e) {
    $("mensaje").textContent = "No se pudo contactar con la Pi.";
  }
}

$("boton-lanzar").onclick = () => enviarOrden("/api/lanzar");
$("boton-barrido").onclick = () => enviarOrden("/api/barrido");
$("boton-procesos").onclick = () => enviarOrden("/api/procesos");

// ---------- Estado y sensores (cada segundo) ----------

function pintarEstado(estado) {
  const enCurso = estado.benchmark_en_curso;
  const etiqueta = $("estado-benchmark");
  etiqueta.textContent = enCurso ? "Calculando…" : "En reposo";
  etiqueta.className = "etiqueta" + (enCurso ? " etiqueta-ocupado" : "");
  $("n-procesos").textContent = estado.n_procesos;
  for (const id of ["boton-lanzar", "boton-barrido", "boton-procesos"]) $(id).disabled = enCurso;
}

function pintarSensores(lectura) {
  if (!lectura) return;
  $("hora-lectura").textContent = "· " + lectura.fecha.slice(11);
  const temp = $("temp-cpu");
  temp.textContent = fmt(lectura.temp_cpu) + " °C";
  temp.classList.toggle("caliente", lectura.temp_cpu >= 75);
  $("temp-ambiente").textContent = lectura.temp_ambiente === null ? "sin sensor" : fmt(lectura.temp_ambiente) + " °C";
  $("humedad").textContent = lectura.humedad === null ? "sin sensor" : fmt(lectura.humedad, 0) + " %";

  // Una barra por núcleo
  const contenedor = $("nucleos");
  if (contenedor.children.length !== lectura.uso_cpu.length) {
    contenedor.innerHTML = lectura.uso_cpu.map((_, i) => `
      <div class="nucleo">
        <span>Núcleo ${i}</span>
        <div class="nucleo-barra"><div class="nucleo-relleno"></div></div>
        <span class="nucleo-valor"></span>
      </div>`).join("");
  }
  lectura.uso_cpu.forEach((uso, i) => {
    const fila = contenedor.children[i];
    fila.querySelector(".nucleo-relleno").style.width = uso + "%";
    fila.querySelector(".nucleo-valor").textContent = fmt(uso, 0) + " %";
  });
}

async function actualizarEstado() {
  try {
    const { datos } = await pedir("/api/estado");
    pintarEstado(datos);
    pintarSensores(datos.lectura);

    // Si hay un benchmark nuevo, o acaba de terminar uno, recargamos resultados.
    const termino = enCursoAntes && !datos.benchmark_en_curso;
    if (datos.ultimo_benchmark !== ultimoBenchmark || termino) {
      ultimoBenchmark = datos.ultimo_benchmark;
      actualizarEjecuciones();
    }
    enCursoAntes = datos.benchmark_en_curso;

    // La imagen se recarga solo cuando hay una nueva (cambia su nº de benchmark).
    const imagen = datos.imagen;
    const idImagen = imagen ? imagen.id_benchmark : null;
    if (idImagen !== imagenMostrada) {
      imagenMostrada = idImagen;
      if (imagen) actualizarImagen();
    }
    $("paleta").textContent = imagen && imagen.paleta
      ? `Paleta: ${imagen.paleta}` + (imagen.id_benchmark ? ` · benchmark nº ${imagen.id_benchmark}` : "")
      : "";
  } catch (e) {
    $("estado-benchmark").textContent = "Sin conexión";
    $("estado-benchmark").className = "etiqueta";
  }
}

// ---------- Gráficas (Chart.js) ----------

function crearGraficas() {
  if (!window.Chart || graficas.temp) return;
  Chart.defaults.color = color("--texto-2");
  Chart.defaults.borderColor = color("--rejilla");
  Chart.defaults.font.family = 'system-ui, -apple-system, "Segoe UI", sans-serif';
  const sinAnimacion = { animation: false, maintainAspectRatio: false, responsive: true };

  graficas.temp = new Chart($("grafica-temp"), {
    type: "line",
    data: { labels: [], datasets: [{ label: "CPU (°C)", data: [], borderColor: color("--serie-1"),
                                     borderWidth: 2, pointRadius: 0, tension: 0.2 }] },
    options: { ...sinAnimacion, interaction: { mode: "index", intersect: false },
               plugins: { legend: { display: false } },
               scales: { x: { ticks: { maxTicksLimit: 8 } }, y: { title: { display: true, text: "°C" } } } },
  });

  graficas.tiempos = new Chart($("grafica-tiempos"), {
    type: "bar",
    data: { labels: [], datasets: [{ label: "Tiempo (s)", data: [], backgroundColor: color("--serie-1"),
                                     borderRadius: 4, maxBarThickness: 48 }] },
    options: { ...sinAnimacion, plugins: { legend: { display: false },
               tooltip: { callbacks: { afterLabel: (c) => "Speedup: " + fmt(c.dataset.speedups[c.dataIndex], 2) } } },
               scales: { y: { beginAtZero: true, title: { display: true, text: "segundos" } } } },
  });

  graficas.speedup = new Chart($("grafica-speedup"), {
    type: "line",
    data: { labels: ["1", "2", "3", "4"], datasets: [
      { label: "Medido (media)", data: [], borderColor: color("--serie-1"), backgroundColor: color("--serie-1"),
        borderWidth: 2, pointRadius: 5 },
      { label: "Ideal (speedup = nº procesos)", data: [1, 2, 3, 4], borderColor: color("--ideal"),
        borderWidth: 2, borderDash: [6, 4], pointRadius: 0 },
    ] },
    options: { ...sinAnimacion, interaction: { mode: "index", intersect: false },
               scales: { x: { title: { display: true, text: "nº de procesos" } },
                         y: { beginAtZero: true, title: { display: true, text: "speedup" } } } },
  });
}

async function actualizarLecturas() {
  crearGraficas();
  if (!graficas.temp) return;
  try {
    const { datos } = await pedir("/api/lecturas?minutos=10");
    graficas.temp.data.labels = datos.map((l) => l.fecha.slice(11));
    graficas.temp.data.datasets[0].data = datos.map((l) => l.temp_cpu);
    graficas.temp.update();
  } catch (e) { /* se reintenta en el siguiente ciclo */ }
}

// ---------- Ejecuciones: tabla y gráficas de tiempos y speedup ----------

function pintarTabla(ejecuciones) {
  if (!ejecuciones.length) return;
  $("tabla-ejecuciones").innerHTML = ejecuciones.slice(0, 40).map((e, i, lista) => {
    const nuevoBench = i > 0 && e.id_benchmark !== lista[i - 1].id_benchmark;
    const thr = e.throttling === null ? "—" : e.throttling ? "Sí" : "No";
    return `<tr class="${nuevoBench ? "inicio-bench" : ""}">
      <td>${e.id_benchmark}</td><td>${e.fecha.replace("T", " ")}</td><td>${NOMBRES[e.version]}</td>
      <td class="num">${e.n_trabajadores}</td><td class="num">${fmt(e.tiempo_s, 3)}</td>
      <td class="num">${fmt(e.speedup, 2)}</td><td class="num">${fmt(e.temp_cpu_inicio)} °C</td>
      <td class="num">${fmt(e.temp_cpu_max)} °C</td><td>${thr}</td></tr>`;
  }).join("");
}

function pintarGraficasEjecuciones(ejecuciones) {
  crearGraficas();
  if (!graficas.tiempos || !ejecuciones.length) return;

  // Tiempos del último benchmark (vienen ordenadas de más reciente a más antigua).
  const ultimo = ejecuciones[0].id_benchmark;
  const delUltimo = ejecuciones.filter((e) => e.id_benchmark === ultimo).reverse();
  $("id-ultimo").textContent = "· nº " + ultimo;
  graficas.tiempos.data.labels = delUltimo.map((e) =>
    e.version === "secuencial" ? "Secuencial" : `${NOMBRES[e.version]} (${e.n_trabajadores})`);
  graficas.tiempos.data.datasets[0].data = delUltimo.map((e) => e.tiempo_s);
  graficas.tiempos.data.datasets[0].speedups = delUltimo.map((e) => e.speedup);
  graficas.tiempos.update();

  // Speedup medio por nº de procesos, con todas las ejecuciones con procesos.
  const medias = [1, 2, 3, 4].map((n) => {
    const valores = ejecuciones.filter((e) => e.version === "procesos" && e.n_trabajadores === n)
                               .map((e) => e.speedup);
    return valores.length ? valores.reduce((a, b) => a + b, 0) / valores.length : null;
  });
  graficas.speedup.data.datasets[0].data = medias;
  graficas.speedup.update();
}

async function actualizarEjecuciones() {
  try {
    const { datos } = await pedir("/api/ejecuciones?limite=500");
    pintarTabla(datos);
    pintarGraficasEjecuciones(datos);
  } catch (e) { /* se reintenta más tarde */ }
}

function actualizarImagen() {
  const img = $("imagen-fractal");
  img.onload = () => { img.hidden = false; $("sin-imagen").hidden = true; };
  img.onerror = () => { img.hidden = true; $("sin-imagen").hidden = false; };
  img.src = "/imagen?t=" + Date.now(); // parámetro distinto: que no use una copia vieja
}

// ---------- Arranque ----------

actualizarEstado();
actualizarLecturas();
actualizarEjecuciones();
setInterval(actualizarEstado, 1000);
setInterval(actualizarLecturas, 3000);
setInterval(actualizarEjecuciones, 10000);
