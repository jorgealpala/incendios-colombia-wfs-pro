# 📐 Metodología — Visor de Incendios Forestales (pro)

Documento de referencia de **todas las fórmulas y métodos de cálculo** usados en el
visor (`index.html`). Los datos provienen de **OroraTech WildFire Solution (WFS)**;
los límites y áreas, de **DIVIPOLA–DANE**.

Convenciones:
- `evento` = una detección/incendio (una fila del dataset).
- `área` = área del evento en hectáreas (`area`, ha).
- `confianza` = `confidence` ∈ {0.0, 0.2, 0.4, 0.6, 0.8, 1.0} (el 0.5 original se normaliza a 0.4).
- `fecha` = `oldest_acquisition` (primera detección satelital), en hora local de Colombia (−5).

---

## 1. Datos y filtros

El visor lee un parquet ligero (`data/wfs/incendios_web.parquet`) que se vuelca a
*TypedArrays* y se filtra en memoria con **máscaras**. Tres filtros se combinan:

- **Rango de fechas** `[fIni, fFin]` sobre la fecha del evento.
- **Confianza**: subconjunto de niveles activos (por defecto 0.6, 0.8, 1.0). El 0.0
  (“datos insuficientes”) solo entra si se marca la casilla correspondiente.
- **Nivel geográfico**: Nacional (todo), Departamental (un depto) o Municipal (un municipio).

**Máscara base** (un evento `i` pasa si):

```
maskBase[i] = (fIni ≤ fecha[i] ≤ fFin) ∧ (confianza[i] ∈ confianzasActivas)
```

El predicado geográfico `geoOK(i)` añade, según el nivel:
`Nacional → true`; `Departamental → cod_depto[i] = deptoSel`; `Municipal → cod_depto = deptoSel ∧ cod_muni = muniSel`.

> El conjunto `datos` (lo que ven KPIs y la mayoría de gráficas) = eventos con `maskBase ∧ geoOK`.

---

## 2. KPIs

Sobre `datos` (n = nº de eventos):

| KPI | Fórmula |
|---|---|
| Eventos | `n = |datos|` |
| Área total (ha) | `Σ area[i]` |
| Área promedio (ha) | `(Σ area[i]) / n` (0 si n = 0) |
| % confianza alta (≥0.6) | `100 · |{i : confianza[i] ∈ {0.6,0.8,1.0}}| / n` |

---

## 3. Mapa nacional — clasificación coroplética

Se cuenta `eventos por departamento` sobre los eventos filtrados por fecha+confianza
(`dff`). El color de cada departamento sale de clasificar esos conteos en clases. Tres métodos:

### 3.1 Cortes naturales (Jenks)
Algoritmo de **Fisher–Jenks** (NumPy puro) que busca los cortes que **minimizan la
varianza intra-clase** y maximizan la inter-clase, con 5 clases. Ideal para explorar.

### 3.2 Rangos técnicos (alerta)
Umbrales **fijos** (comparables en el tiempo): bordes inferiores `[0, 100, 500, 1500, 4000]`
con el nivel superior **abierto** (Crítico ≥ 4000). Niveles: **Bajo, Moderado, Alto,
Muy alto, Crítico**. El borde superior se estira hasta el máximo real del periodo, así
nunca se crea una clase sin etiqueta.

### 3.3 Cuantiles
Cortes en los cuantiles `{0, .2, .4, .6, .8, 1.0}` de los conteos: reparte los
departamentos en 5 grupos de igual tamaño.

---

## 4. Área del municipio/departamento (base de densidad y %)

Calculada en el build (`generar_datos.py`) desde los GeoJSON, con **área geodésica
esférica** (sin dependencias). Para un anillo de vértices `(λ, φ)` en radianes y radio
terrestre `R`:

```
A_anillo = | (R² / 2) · Σ_k (λ_{k+1} − λ_k) · (2 + sen φ_k + sen φ_{k+1}) |   [m²]
```

Área del polígono = anillo exterior − huecos; MultiPolygon = suma de polígonos.
`área (ha) = A / 10 000`. Se guarda en `data/wfs/areas.json` (clave = código DIVIPOLA
como entero). Error típico < 0.5 % frente al dato oficial (p. ej. Montería 315 378 ha
vs 313 735 ha oficial).

---

## 5. Métricas por municipio (treemap y registro)

Para cada municipio del ámbito (respetando fecha+confianza y, si aplica, el depto):

| Métrica | Fórmula |
|---|---|
| Eventos | `ev = nº de eventos del municipio` |
| Área quemada (ha) | `Σ area` |
| **Densidad** | `ev / (áreaMunicipio_ha / 1000)` → eventos por cada **1.000 ha** |
| **% de área** | `100 · (Σ area) / áreaMunicipio_ha` *(acumulado; puede superar 100 % al sumar varios años)* |
| % confianza alta | `100 · nº eventos ≥0.6 / ev` |

- **Treemap**: tamaño del rectángulo ∝ métrica (Área quemada o N° eventos), agrupado por
  departamento; color por intensidad relativa (valor / máximo).
- **Registro de municipios**: tabla ordenable/buscable con las métricas anteriores y barras.

---

## 6. Panel “Territorio seleccionado” (gauge)

Para el depto/municipio activo (con los filtros actuales):

```
% área del territorio con incendios = 100 · (Σ area eventos) / áreaTerritorio_ha
```

El gauge muestra ese porcentaje (acotado a 100 para la aguja); se acompaña de eventos,
área quemada, área del territorio y % confianza alta.

---

## 7. Alerta de anomalía

Compara el **último mes del rango** con el **promedio histórico de ese mismo mes**
(años anteriores disponibles), en el ámbito actual y respetando la confianza:

```
actual  = eventos del mes m en el año de corte
prom    = promedio de eventos del mes m en los años anteriores
desv %  = 100 · (actual − prom) / prom
```

Semáforo: **↑ por encima** si `desv% > +10`; **↓ por debajo** si `desv% < −10`; **≈ en línea** en el resto.

---

## 7.1 Tendencia reciente (aceleración)

Compara la actividad **reciente** con el **periodo previo del mismo largo**, anclado al
**último día con datos** (`F_MAX`). Respeta nivel y confianza; es independiente del rango
de fechas. Para una ventana de `W` días (se usan `W = 7` y `W = 30`):

```
reciente = eventos en los últimos W días      = Σ eventos en [F_MAX−W+1 , F_MAX]
previo   = eventos en los W días anteriores   = Σ eventos en [F_MAX−2W+1 , F_MAX−W]
variación % (aceleración) = 100 · (reciente − previo) / previo
```

Lectura: **▲ al alza** (más incendios) si `var% > +10` (rojo); **▼ a la baja** si `var% < −10`
(verde); **▬ estable** en el resto. Se acompaña de una *sparkline* con los **últimos 90 días**.

---

## 8. Series de tiempo

### 8.1 Eventos por mes (comparativo por año)
Conteo por `(año, mes)`; una línea por año (12 meses) + **promedio mensual** = media de
cada mes a través de los años.

### 8.2 Eventos por mes (serie continua)
Conteo por mes calendario en todo el periodo (línea gris) + **media móvil de 6 meses**
(centrada, línea roja) como tendencia:

```
MA6[t] = promedio de eventos de los meses [t−3 .. t+2]
```

### 8.3 Eventos por día
Conteo por día (línea gris) + **media móvil de 7 días** (centrada, línea roja):

```
MA7[t] = promedio de eventos de los días [t−3 .. t+3]
```
Los días sin eventos se rellenan con 0 para una serie continua.

### 8.4 Análisis comparativo por año
- **Eventos/área por año** (tortas) con su porcentaje del total.
- **Variación % interanual**: `100 · (valor_año − valor_añoAnterior) / valor_añoAnterior`.
- El año de corte se marca **“parcial”** si el dataset no llega a diciembre.

---

## 9. Calendario de actividad (estacionalidad diaria)

Mapa de calor tipo calendario (ECharts): un **panel por año**; cada celda = un día,
coloreada por el **nº de eventos de ese día** (respeta fecha+confianza+nivel).

La escala de color se **acota al percentil 98** de los conteos diarios, para que un
único día pico no aplane visualmente el resto:

```
tope_escala = P98( {eventos por día} )
```

Rampa de color claro→intenso; los días por encima del tope toman el color máximo.

---

## 10. Análisis para gestión del riesgo

Sobre el ámbito (nacional o departamento), respetando fecha+confianza:

### 10.1 Recurrencia estacional
Agrupa por `(municipio, mes)` y cuenta **años distintos** con eventos. Se listan los
que tienen **≥ 2 años** en el mismo mes (patrón estacional predecible):
`años_recurrentes = |{años distintos con eventos en ese mes}|`.

### 10.2 Mapa de calor de estacionalidad (municipio × mes)
Para los 15 municipios con más eventos: matriz `municipio × mes` con el conteo de
eventos; color por intensidad. Revela las ventanas de riesgo de cada territorio.

### 10.3 Municipios reincidentes
Por municipio: `años_activos = |{años distintos con eventos}|`, ordenado desc. Más años
distintos = vigilancia prioritaria.

### 10.4 Distribución histórica por mes
Conteo de eventos por mes (sumando todos los años); se resalta el **mes pico**.

---

## 11. Índice de priorización para vigilancia

Puntaje **0–100** por municipio (usa **todo el histórico**; respeta nivel y confianza).
Para cada municipio del ámbito se calculan 4 insumos:

| Insumo | Definición |
|---|---|
| `recur` | nº de años distintos con eventos (recurrencia / cronicidad) |
| `reciente` | eventos de los **últimos 12 meses** (fecha > `F_MAX − 1 año`) |
| `area` | área quemada total (ha) — magnitud |
| `dens` | densidad = `ev / (áreaMunicipio_ha / 1000)` — intensidad |

Cada insumo se **normaliza 0–100** entre los municipios del ámbito (min–max):

```
norm(x) = 100 · (x − min) / (max − min)      (0 si max = min)
```

El **puntaje** es la suma ponderada:

```
Puntaje = 0.25·norm(recur) + 0.30·norm(reciente) + 0.25·norm(area) + 0.20·norm(dens)
```

Pesos por defecto (ajustables en la constante `PESOS_PRIOR` del código):

| Componente | Peso |
|---|---|
| Recurrencia | 25 % |
| Actividad reciente | 30 % |
| Magnitud (área) | 25 % |
| Intensidad (densidad) | 20 % |

Clasificación del puntaje: **Alta** (≥ 66), **Media** (33–65), **Baja** (< 33).
La tabla se ordena por puntaje descendente; clic en una fila navega al municipio.

---

## 12. Reporte PDF

Reporte institucional A4 vertical generado en el navegador (jsPDF + autotable): usa los
mismos valores calculados arriba (KPIs, mapa, gráficas, tablas de riesgo y tabla de
eventos). Las gráficas se insertan como imagen; las tablas y textos son nativos.

---

*Cualquier cambio de pesos, umbrales o ventanas se hace en `index.html`
(`PESOS_PRIOR`, `RANGOS_TECNICOS`, ventanas de medias móviles, etc.) o en
`generar_datos.py` (áreas, normalización de confianza).*
