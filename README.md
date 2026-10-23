# 🔥 Incendios Forestales · Colombia — Visor HTML (pro)

Visor **100 % estático en HTML/JS** de incendios forestales en Colombia, con datos de
**OroraTech WildFire Solution (WFS)**. Es la versión sin **Streamlit** del dashboard
[`incendios-colombia-wfs`](https://github.com/jorgealpala/incendios-colombia-wfs):
misma información y análisis, pero servida como sitio estático (GitHub Pages) para
**eliminar los límites de consultas** del Community Cloud.

Todo el procesamiento ocurre **en el navegador**: no hay backend ni base de datos.

---

## Qué incluye (espejo del dashboard Streamlit)

- **Tres niveles de vista**: Nacional, Departamental, Municipal (con drill-down al hacer clic en el mapa).
- **Mapa nacional coroplético** con 3 métodos de clasificación: *Cortes naturales (Jenks)*,
  *Rangos técnicos (alerta)* —5 niveles fijos con el superior abierto, Crítico ≥ 4000— y *Cuantiles*.
- **Mapa de calor** (nivel departamental) y **puntos por confianza** (nivel municipal:
  agrupados / sueltos / mapa de calor).
- **KPIs**: eventos, área total, área promedio, % confianza alta.
- **Gráficas**: distribución por confianza, eventos por mes (comparativo por año + promedio),
  serie diaria con media móvil de 7 días, comparativo anual (donas + barras con variación %),
  y tops por departamento/municipio.
- **Análisis para gestión del riesgo**: recurrencia estacional, mapa de calor de estacionalidad
  (municipio × mes), municipios reincidentes y distribución histórica por mes.
- **Filtros**: rango de fechas, año, nivel de confianza (chips).
- **Reporte PDF** institucional estructurado (según el nivel y filtros en pantalla) y **descarga CSV** de la tabla.

---

## Estructura

```
incendios-colombia-wfs-pro/
├── index.html         # El visor completo (autocontenido: HTML + CSS + JS)
├── generar_datos.py   # Build: genera data/wfs/ desde el proyecto Streamlit original
├── .nojekyll          # GitHub Pages: servir los archivos tal cual
├── logo/
│   └── ungrd-horizontal.png
└── data/
    └── wfs/
        ├── incendios_web.parquet            # tabla ligera (hyparquet, 8 columnas)
        ├── departamentos_simplificado.geojson
        └── municipios_simplificado.geojson
```

### Tecnologías (CDN, sin build de JS)
Leaflet 1.9 (+heat, +markercluster) · Chart.js 4 · **hyparquet** (lee Parquet en el navegador) ·
jsPDF + html2canvas (PDF) · tiles base **Esri World Light Gray** / OpenStreetMap.

---

## Datos

El visor lee **un parquet ligero** (`data/wfs/incendios_web.parquet`, ~11 MB, 674k filas,
8 columnas con tipos compactos) que hyparquet descarga una vez y convierte a *TypedArrays*;
todo el filtrado (fecha, confianza, nivel geográfico) se hace en memoria con máscaras. No hay
límite de consultas: GitHub Pages solo sirve archivos estáticos.

Columnas del parquet ligero (`incendios_web.parquet`):

| Col | Tipo | Significado |
|-----|------|-------------|
| `f` | int32 | fecha local (Colombia, −5) como `AAAAMMDD` |
| `cd` | int32 | código de departamento (DIVIPOLA; `11001` = Bogotá) |
| `cm` | int32 | código de municipio (DIVIPOLA, 5 díg.; `0` = sin clasificar) |
| `lon`,`lat` | float32 | centroide del evento |
| `conf` | uint8 | confianza ×10 en 6 niveles (0,2,4,6,8,10) |
| `area` | float32 | área del evento (ha) |
| `nf` | uint16 | número de focos |

### Cómo funciona por dentro

1. **Carga única**: `fetch` del parquet + los 2 GeoJSON → `hyparquet` lee las 8 columnas →
   `compactar()` las vuelca a *TypedArrays* paralelos (incluye día-índice, año y mes precalculados).
2. **Filtros por máscara**: cada cambio de control recalcula una `Uint8Array` (fecha + confianza)
   y un predicado geográfico según el nivel; KPIs, mapa y gráficas iteran los arrays aplicando la máscara.
3. **Mapa (Leaflet)**: coropleta (`L.geoJSON` + clasificación), `L.heatLayer` o `L.circleMarker`/
   `markerCluster` según el nivel; tiles Esri Light Gray.
4. **Gráficas (Chart.js)**: se reconstruyen con los agregados en cada actualización.
5. **Reporte PDF** (`generarPDF()`): reporte institucional **A4 vertical, estructurado y nativo**,
   con el mismo estilo del informe del proyecto Streamlit (`reporte.py`):
   - Encabezado (logo UNGRD + título), bloque de metadatos (Ámbito / Periodo / Generado) y
     **tabla de KPIs**, dibujados como **texto y tablas nativas** (jsPDF + `jspdf-autotable`) → nítidos.
   - Secciones con títulos: **Mapa**, **Análisis**, **Comparativo por año**, **Tops**,
     **Gestión del riesgo**, **Principales eventos** y **Términos de uso**.
   - Las **gráficas** se insertan como imagen desde el propio Chart.js (compuestas sobre blanco);
     el **mapa** y el **heatmap** vía `html2canvas`. La tabla de eventos se limita a 20 filas.
   - Antes de capturar se fuerza el dibujado síncrono de las gráficas (`chart.draw()`) para que
     ninguna salga en blanco aunque la pestaña no esté activa.

### Regenerar los datos

El build toma los datos procesados del **proyecto Streamlit original**
(`../incendios-colombia-wfs/data/processed/`), que se sigue actualizando con su propio
`actualizar_2026.py` / `preprocesar.py`. Para refrescar la versión web:

```bash
# 1) En el proyecto original: actualizar los datos (p. ej. nuevo mes)
#    python actualizar_2026.py
# 2) Aquí: regenerar el parquet web + copiar los límites
python generar_datos.py
# 3) Publicar
git add data/ && git commit -m "datos: actualizacion" && git push
```

---

## Uso local

Por CORS, no se puede abrir con doble clic (`file://`). Hay que servirlo:

```bash
python -m http.server 8000
# abrir http://localhost:8000
```

## Publicar (GitHub Pages)

1. Subir el repositorio a GitHub.
2. *Settings → Pages →* servir desde la rama `main` (raíz `/`).
3. La app queda en `https://<usuario>.github.io/<repo>/`.

> El `.nojekyll` evita que GitHub Pages procese el sitio con Jekyll.

---

## Notas

- **Bogotá** se trata como unidad propia (igual que OroraTech).
- La confianza intermedia 0.5 se normaliza a 0.4 (6 niveles estándar).
- La vista municipal no incluye la gráfica "por satélite" del dashboard original
  (el dato de satélite no se incluye en el parquet ligero).

**Realizado por:** Jorge Alpala (jorge.alpala@gestiondelriesgo.gov.co) · UNGRD – SCR.
**Fuentes:** OroraTech WildFire Solution (WFS) · Límites: DIVIPOLA – DANE.
