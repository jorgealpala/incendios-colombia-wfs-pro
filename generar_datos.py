"""
============================================================================
GENERAR DATOS DEL PORTAL HTML (incendios-colombia-wfs-pro)
============================================================================
Produce los archivos ligeros que lee el visor estático (index.html):

  data/wfs/incendios_web.parquet          <- tabla ligera (hyparquet, navegador)
  data/wfs/departamentos_simplificado.geojson
  data/wfs/municipios_simplificado.geojson

FUENTE: el parquet procesado del proyecto Streamlit original
  (../incendios-colombia-wfs/data/processed/). Ese proyecto se sigue
  actualizando con `actualizar_2026.py` / `preprocesar.py`; este script solo
  deriva la versión web ligera.

El parquet web guarda SOLO lo que el visor necesita, con tipos compactos:
  f     int32   fecha local (Colombia, -5) como entero AAAAMMDD
  cd    int32   codigo de departamento (DIVIPOLA; 2 digitos, o 11001 = Bogotá)
  cm    int32   codigo de municipio (DIVIPOLA, 5 digitos; 0 = sin clasificar)
  lon   float32 longitud del centroide
  lat   float32 latitud del centroide
  conf  uint8   confianza * 10, en 6 niveles estandar (0,2,4,6,8,10)
                (el 0.5 original -> 0.4, para no inflar "confianza alta")
  area  float32 area del evento (ha)
  nf    uint16  numero de focos (num_fires)

USO:
  python generar_datos.py
============================================================================
"""

import shutil
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parent
# Proyecto Streamlit original (fuente de datos procesados)
ORIGEN = RAIZ.parent / "incendios-colombia-wfs" / "data" / "processed"
F_PARQUET_SRC = ORIGEN / "incendios.parquet"
F_CSV_SRC = ORIGEN / "incendios.csv"
F_DEPTOS_SRC = ORIGEN / "departamentos_simplificado.geojson"
F_MUNIS_SRC = ORIGEN / "municipios_simplificado.geojson"

DIR_OUT = RAIZ / "data" / "wfs"


def _cod_int(serie, ndig):
    """Convierte un codigo DIVIPOLA textual (con posibles '.0' y nulos) a int."""
    s = serie.astype(str).str.replace(r"\.0$", "", regex=True)
    s = s.where(~serie.isna(), None)
    out = pd.to_numeric(s, errors="coerce")
    return out


def main():
    print("=" * 60)
    print("GENERAR DATOS WEB - incendios-colombia-wfs-pro")
    print("=" * 60)

    if not F_PARQUET_SRC.exists() and not F_CSV_SRC.exists():
        print(f"[ERROR] No existe la fuente: {F_PARQUET_SRC}")
        print("        Genera primero data/processed/ en el proyecto original.")
        return

    print(f">> Leyendo fuente: {F_PARQUET_SRC.name}")
    src = F_PARQUET_SRC if F_PARQUET_SRC.exists() else F_CSV_SRC
    df = pd.read_parquet(src) if src.suffix == ".parquet" else pd.read_csv(src)
    print(f"   filas origen: {len(df):,}")

    # --- Fecha local (Colombia -5) a entero AAAAMMDD ---
    fecha = pd.to_datetime(df["oldest_acquisition"], errors="coerce", utc=True)
    fecha_local = fecha.dt.tz_convert("America/Bogota")
    f_int = (fecha_local.dt.year * 10000
             + fecha_local.dt.month * 100
             + fecha_local.dt.day)

    out = pd.DataFrame({
        "f": f_int,
        "cd": _cod_int(df["cod_depto"], 2),
        "cm": _cod_int(df["cod_muni"], 5),
        "lon": pd.to_numeric(df["lon"], errors="coerce"),
        "lat": pd.to_numeric(df["lat"], errors="coerce"),
        "conf": (pd.to_numeric(df["confidence"], errors="coerce") * 10).round(),
        "area": pd.to_numeric(df["area"], errors="coerce"),
        "nf": pd.to_numeric(df.get("num_fires"), errors="coerce"),
    })

    # Descartar filas sin fecha o sin coordenadas (inservibles para el visor)
    antes = len(out)
    out = out[out["f"].notna() & out["lon"].notna() & out["lat"].notna()].copy()
    if len(out) != antes:
        print(f"   descartadas sin fecha/coords: {antes - len(out):,}")

    # --- Tipos compactos ---
    out["f"] = out["f"].astype("int32")
    # cd en int32: Bogotá usa 11001 (no cabe en uint8)
    out["cd"] = out["cd"].fillna(0).astype("int32")
    out["cm"] = out["cm"].fillna(0).astype("int32")
    out["lon"] = out["lon"].astype("float32")
    out["lat"] = out["lat"].astype("float32")
    out["conf"] = out["conf"].fillna(0).clip(0, 10)
    # Normalizar el nivel intermedio 0.5 (conf==5) a 0.4: deja 6 niveles
    # estandar y evita inflar el % de confianza alta (>=0.6).
    out.loc[out["conf"] == 5, "conf"] = 4
    out["conf"] = out["conf"].astype("uint8")
    out["area"] = out["area"].fillna(0).astype("float32")
    out["nf"] = out["nf"].fillna(1).clip(0, 65535).astype("uint16")

    DIR_OUT.mkdir(parents=True, exist_ok=True)
    f_out = DIR_OUT / "incendios_web.parquet"
    # Snappy: compresion soportada nativamente por hyparquet en el navegador.
    out.to_parquet(f_out, index=False, compression="snappy")
    mb = f_out.stat().st_size / 1e6
    print(f">> {f_out.name}: {len(out):,} filas · {mb:.1f} MB")
    print(f"   años: {sorted((out['f'] // 10000).unique().tolist())}")

    # --- Copiar límites simplificados (se reusan tal cual) ---
    for src_gj in (F_DEPTOS_SRC, F_MUNIS_SRC):
        if src_gj.exists():
            dst = DIR_OUT / src_gj.name
            shutil.copy2(src_gj, dst)
            print(f">> copiado {dst.name}: {dst.stat().st_size/1e6:.1f} MB")
        else:
            print(f"[aviso] no existe {src_gj}")

    print(f"\n>> Listo. Salida en: {DIR_OUT}")


if __name__ == "__main__":
    main()
