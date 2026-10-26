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
**mismos valores calculados arriba** (no recalcula nada) y refleja el nivel y los filtros
activos en pantalla. Las tablas y textos son **nativos** (nítidos y seleccionables); las
gráficas se insertan como **imagen**.

Estructura (según el ámbito):

| Sección | Fuente | §|
|---|---|---|
| Encabezado + KPIs | KPIs | 2 |
| Monitoreo reciente | alerta de anomalía + tendencia reciente (*sparkline*); *gauge* solo en Dep./Mun. | 7, 7.1, 6 |
| Mapa | coropleta del nivel activo | 3 |
| Afectación por territorio | treemap + registro de municipios | 5 |
| Análisis | confianza, mes comparativo, serie mensual continua, día | 8.1–8.3 |
| Comparativo por año | donas + barras con variación % | 8.4 |
| Calendario de actividad | heatmap anual (P98) | 9 |
| Tops | top departamentos/municipios | — |
| Gestión del riesgo | recurrencia, estacionalidad, reincidentes, distribución mensual, **índice de priorización** | 10, 11 |
| Tabla de eventos | hasta 20 filas | 1 |
| Términos de uso | — | — |

**Captura de imágenes**:
- Gráficas **Chart.js** → `chart.toBase64Image()` compuesto sobre blanco (evita fondo negro);
  se fuerza `chart.draw()` síncrono para que ninguna salga en blanco aunque la pestaña no esté activa.
- Vistas **ECharts** (treemap, *gauge*, calendario) → `getDataURL({pixelRatio:2, backgroundColor:'#fff'})`,
  exportación nativa (no `html2canvas`) → nítidas.
- **Mapa** y bloques HTML (alerta, panel de tendencia) → `html2canvas`.

---

## 13. Capa de puntos (nivel municipal), tooltip y descarga CSV

### 13.1 Puntos del mapa (incendios individuales)
En **nivel municipal**, cada evento filtrado (`maskBase ∧ geoOK`) se dibuja como un
`L.circleMarker` en `[lat, lon]`:

| Propiedad | Regla |
|---|---|
| Radio (px) | `r = 4 + √area / 4`, acotado a un **máximo de 18 px** (magnitud ∝ √área → el *área del círculo* es ∝ al área quemada) |
| Color | por nivel de confianza (`COLOR_CONF`: gris→verde→amarillo→naranja→rojo→rojo oscuro) |
| Opacidad | relleno 0.7 |

Tres visualizaciones: **agrupados** (markercluster), **sueltos** y **mapa de calor**.
El lienzo del mapa de calor se marca con `pointerEvents='none'` para que el clic
llegue siempre a los puntos (el mapa usa `preferCanvas:true`).

**Tooltip del punto** (al pasar/hacer clic), con este contenido exacto:

```
Fecha: AAAA-MM-DD · Confianza: c · Área: a ha · Focos: nf · Lat: yy.yyyyy, Lon: xx.xxxxx
```

- `Fecha` = fecha del evento en ISO (`AAAA-MM-DD`), misma que el CSV.
- `Confianza` = `conf/10` con 1 decimal (0.0–1.0).
- `Área` = hectáreas con 1 decimal · `Focos` = `num_fires`.
- `Lat`/`Lon` = coordenadas del centroide con **5 decimales** (≈ 1 m).

### 13.2 Descarga CSV
El botón *"Descargar tabla (CSV)"* exporta **todos** los eventos del ámbito actual
(`maskBase ∧ geoOK`, en **cualquier nivel**: Nacional, Departamental o Municipal),
ordenados por **área descendente**. Codificación UTF-8. Columnas:

```
departamento,municipio,lat,lon,area,confidence,num_fires,fecha
```

- `lat`,`lon` → 5 decimales · `area` → 2 decimales · `confidence` → 1 decimal · `fecha` → ISO.
- `departamento`/`municipio` se resuelven de los códigos DIVIPOLA a nombre; van entre comillas.

---

## 14. Contador de visitas (Firebase Firestore)

### 14.1 Por qué un servicio externo
GitHub Pages sirve **solo archivos estáticos**: no hay dónde guardar un número
**compartido** entre todos los visitantes. `localStorage` solo contaría las visitas de
*ese* navegador. Por eso el conteo se delega a **Cloud Firestore** (base NoSQL de
documentos, de Firebase), que persiste el total y lo incrementa de forma atómica en el
servidor. Es el **único** componente del visor con backend; no interviene en el análisis
de incendios.

### 14.2 Modelo de datos
Un único documento:

```
contadores/visitas  →  { total: <entero> }
```

`total` es el número acumulado de visitas. El documento se **crea en la primera visita**
(cuando aún no existe, se parte de 0 y se escribe 1).

### 14.3 SDK y carga
Se usa el **SDK modular de Firebase v10.14.1**, cargado por **CDN** con `import()`
dinámico (sin `npm`, sin paso de build):

```
https://www.gstatic.com/firebasejs/10.14.1/firebase-app.js        → initializeApp
https://www.gstatic.com/firebasejs/10.14.1/firebase-firestore.js  → getFirestore, doc, runTransaction
```

### 14.4 Flujo de conteo (en cada carga de la página)
```
1. Verificar guardas (14.6). Si no pasa → no cuenta.
2. db  = getFirestore(initializeApp(FIREBASE_CONFIG))
3. ref = doc(db, 'contadores', 'visitas')
4. total = runTransaction(db, tx => {
       snap = tx.get(ref)
       n    = (snap existe ? snap.total : 0) + 1
       tx.set(ref, { total: n }, { merge: true })
       return n
   })
5. Mostrar en el pie: "👁 Visitas totales: N"  (N con formato es-CO, miles con punto)
```

**¿Por qué una transacción?** `runTransaction` hace un **lee–modifica–escribe atómico**
con reintentos automáticos si dos visitas coinciden: así **no se pierden** incrementos y,
además, **devuelve el valor ya confirmado** para mostrarlo. (Una alternativa,
`increment(1)`, también es atómica pero obligaría a una segunda lectura para mostrar el
número y podría “saltarse” valores entre visitas simultáneas.)

### 14.5 Semántica del conteo
Es un **total de visitas**: suma **1 en cada carga** de la página. **No** hay
deduplicación por sesión ni por navegador, por lo que **recargas y rastreadores también
suman**. No se guarda ningún dato personal, solo un entero.

### 14.6 Guardas (cuándo NO cuenta)
El módulo se auto-desactiva, sin error, en dos casos:

| Guarda | Condición | Motivo |
|---|---|---|
| `ES_LOCAL` | `hostname ∈ {localhost, 127.0.0.1, ''}` o `protocol = file:` | no inflar el contador en desarrollo |
| `CONFIGURADO` | algún valor de `FIREBASE_CONFIG` empieza por `"TU_"` | aún sin configurar → la página funciona igual |

### 14.7 Aislamiento y robustez
El contador vive en su **propio `<script type="module">`**, separado del visor. Todo va
dentro de `try/catch`: si el CDN de Firebase o la red fallan, solo se registra un
`console.warn` y **el visor no se ve afectado**. La línea del pie permanece oculta
(`display:none`) hasta que llega un valor.

### 14.8 Modelo de seguridad
- La `firebaseConfig` (incl. `apiKey`) es **pública por diseño**: identifica el proyecto,
  **no es un secreto** ni credencial. Es correcto publicarla en el repositorio.
- La seguridad real la dan las **reglas de Firestore**, que restringen el documento a:
  - **lectura** pública;
  - **create** solo si el documento es exactamente `{ total: 1 }`;
  - **update** solo si `total` nuevo = `total` anterior **+ 1** y el único campo es `total`
    (`hasOnly(['total'])`).
  ```
  rules_version = '2';
  service cloud.firestore {
    match /databases/{database}/documents {
      match /contadores/visitas {
        allow read: if true;
        allow create: if request.resource.data.keys().hasOnly(['total'])
                      && request.resource.data.total == 1;
        allow update: if request.resource.data.keys().hasOnly(['total'])
                      && request.resource.data.total == resource.data.total + 1;
      }
    }
  }
  ```
- Así **nadie** puede fijar un valor arbitrario, borrar el documento ni añadir campos; a lo
  sumo, sumar 1 por escritura.
- **Limitación residual**: un cliente podría hacer *scripting* de muchos `+1` para inflar el
  número (inherente a cualquier contador de navegador sin autenticación). Es aceptable para
  un contador de visitas.
- **Reiniciar**: solo manualmente en la consola de Firebase (las reglas impiden fijar el
  valor desde la web). *Firestore Database → Datos → `contadores/visitas` → editar `total`.*

### 14.9 Configuración y costo
- La `FIREBASE_CONFIG` se edita en el bloque *"CONTADOR DE VISITAS"* al final de
  `index.html` (campos `apiKey`, `authDomain`, `projectId`, `appId`).
- Proyecto en **plan Spark (gratuito)**; la cuota libre de Firestore (lecturas/escrituras
  por día) es amplia para este tráfico. No requiere copias de seguridad (solo plan Blaze).

---

*Cualquier cambio de pesos, umbrales o ventanas se hace en `index.html`
(`PESOS_PRIOR`, `RANGOS_TECNICOS`, ventanas de medias móviles, `FIREBASE_CONFIG`, etc.) o en
`generar_datos.py` (áreas, normalización de confianza).*
