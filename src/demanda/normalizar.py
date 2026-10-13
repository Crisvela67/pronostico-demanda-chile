"""Esquema común para todas las fuentes de demanda.

Toda fuente debe terminar como un DataFrame con columnas:
    fecha_hora_utc (datetime64[ns, UTC]) | demanda_mwh (float) | fuente (str)

Convenciones:
- "1-24": la hora indica el FIN del intervalo (hora 1 = 00:00-01:00).
- "0-23": la hora indica el INICIO del intervalo.
Internamente se guarda el INICIO del intervalo, en UTC.
"""
from __future__ import annotations

import pandas as pd

COLUMNAS = ["fecha_hora_utc", "demanda_mwh", "fuente"]


def a_numero(serie: pd.Series, decimal: str = ".") -> pd.Series:
    """Convierte textos tipo '8.512,3' o '8512.3' a float."""
    if pd.api.types.is_numeric_dtype(serie):
        return serie.astype(float)
    s = serie.astype(str).str.strip().str.replace(" ", "", regex=False)
    if decimal == ",":
        s = s.str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
    return pd.to_numeric(s, errors="coerce")


def construir_fecha_hora(
    fecha: pd.Series,
    hora: pd.Series,
    convencion: str,
    zona: str = "America/Santiago",
) -> pd.Series:
    """Combina fecha local + número de hora en un timestamp UTC (inicio del intervalo)."""
    hora = pd.to_numeric(hora, errors="coerce").astype("Int64")
    if convencion == "1-24":
        hora = hora - 1
    elif convencion != "0-23":
        raise ValueError(f"Convención de hora desconocida: {convencion}")

    fecha = pd.to_datetime(fecha, dayfirst=True, errors="coerce").dt.normalize()
    local = fecha + pd.to_timedelta(hora.astype(float), unit="h")
    # ambiguous="infer" resuelve la hora repetida al pasar a horario de invierno;
    # nonexistent="shift_forward" la hora que no existe al pasar a verano.
    try:
        local = local.dt.tz_localize(zona, ambiguous="infer", nonexistent="shift_forward")
    except Exception:
        local = local.dt.tz_localize(zona, ambiguous="NaT", nonexistent="shift_forward")
    return local.dt.tz_convert("UTC")


def esquema_comun(df: pd.DataFrame, fuente: str) -> pd.DataFrame:
    out = df[["fecha_hora_utc", "demanda_mwh"]].copy()
    out["fuente"] = fuente
    out = out.dropna(subset=["fecha_hora_utc", "demanda_mwh"])
    out = out.sort_values("fecha_hora_utc").drop_duplicates("fecha_hora_utc", keep="last")
    return out[COLUMNAS].reset_index(drop=True)


def guardar(df: pd.DataFrame, ruta) -> None:
    """Agrega datos nuevos a un Parquet existente sin duplicar horas."""
    from pathlib import Path

    ruta = Path(ruta)
    if ruta.exists():
        previo = pd.read_parquet(ruta)
        df = pd.concat([previo, df]).drop_duplicates("fecha_hora_utc", keep="last")
    df.sort_values("fecha_hora_utc").to_parquet(ruta, index=False)
