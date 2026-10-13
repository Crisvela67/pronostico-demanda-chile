"""Construcción de variables para el modelo.

Regla clave para no hacer trampa (data leakage): con horizonte de 24 h,
solo se pueden usar rezagos de 24 h o más.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from demanda.fuentes import calendario

REZAGOS_H = [24, 48, 168]


def construir(
    demanda: pd.DataFrame,
    clima: pd.DataFrame | None = None,
    base_cal: float = 18.0,
    base_enf: float = 24.0,
) -> pd.DataFrame:
    df = demanda[["fecha_hora_utc", "demanda_mwh"]].sort_values("fecha_hora_utc").copy()
    # rejilla horaria completa para que los rezagos por posición sean correctos
    rejilla = pd.date_range(df["fecha_hora_utc"].min(), df["fecha_hora_utc"].max(), freq="h")
    df = df.set_index("fecha_hora_utc").reindex(rejilla).rename_axis("fecha_hora_utc").reset_index()

    df = calendario.agregar(df)
    df["hora_sin"] = np.sin(2 * np.pi * df["hora_local"] / 24)
    df["hora_cos"] = np.cos(2 * np.pi * df["hora_local"] / 24)

    for h in REZAGOS_H:
        df[f"lag_{h}h"] = df["demanda_mwh"].shift(h)
    df["media_7d_lag24"] = df["demanda_mwh"].shift(24).rolling(168, min_periods=24).mean()

    if clima is not None and not clima.empty:
        df = df.merge(clima, on="fecha_hora_utc", how="left")
        df["grados_calefaccion"] = (base_cal - df["temp_c"]).clip(lower=0)
        df["grados_enfriamiento"] = (df["temp_c"] - base_enf).clip(lower=0)
    return df


def columnas_modelo(df: pd.DataFrame) -> list[str]:
    excluir = {"fecha_hora_utc", "demanda_mwh", "fuente"}
    return [c for c in df.columns if c not in excluir]
