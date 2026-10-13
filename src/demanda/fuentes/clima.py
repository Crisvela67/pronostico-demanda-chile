"""Temperatura horaria ponderada por ciudades.

Usa el archivo histórico de Open-Meteo (gratuito, sin API key) para que el
proyecto funcione desde el primer día. Cuando tengas key de INIA o datos de
la DMC, puedes agregar otro extractor que devuelva las mismas columnas:
    fecha_hora_utc | temp_c
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import requests

from demanda.config import settings

URL_ARCHIVO = "https://archive-api.open-meteo.com/v1/archive"


def _ciudad(lat: float, lon: float, desde: date, hasta: date) -> pd.DataFrame:
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": desde.isoformat(),
        "end_date": hasta.isoformat(),
        "hourly": "temperature_2m",
        "timezone": "UTC",
    }
    r = requests.get(URL_ARCHIVO, params=params, timeout=60)
    r.raise_for_status()
    h = r.json()["hourly"]
    return pd.DataFrame(
        {"fecha_hora_utc": pd.to_datetime(h["time"], utc=True), "temp_c": h["temperature_2m"]}
    )


def descargar(desde: date, hasta: date) -> pd.DataFrame:
    ciudades = settings()["clima"]["ciudades"]
    total = None
    peso_total = sum(c["peso"] for c in ciudades.values())
    for nombre, c in ciudades.items():
        df = _ciudad(c["lat"], c["lon"], desde, hasta)
        df["temp_c"] *= c["peso"] / peso_total
        df = df.rename(columns={"temp_c": nombre})
        total = df if total is None else total.merge(df, on="fecha_hora_utc", how="outer")
    total["temp_c"] = total[list(ciudades)].sum(axis=1, min_count=len(ciudades))
    return total[["fecha_hora_utc", "temp_c"]]
