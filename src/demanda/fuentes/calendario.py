"""Variables de calendario: feriados de Chile, día de la semana, horario local."""
from __future__ import annotations

import pandas as pd

ZONA = "America/Santiago"


def feriados(anios: list[int]) -> set:
    """Feriados nacionales con la librería `holidays` (sin red)."""
    import holidays

    return set(holidays.Chile(years=anios).keys())


def agregar(df: pd.DataFrame, col_tiempo: str = "fecha_hora_utc") -> pd.DataFrame:
    out = df.copy()
    local = out[col_tiempo].dt.tz_convert(ZONA)
    fer = feriados(sorted(local.dt.year.unique().tolist()))
    fecha_local = local.dt.date

    out["hora_local"] = local.dt.hour
    out["dia_semana"] = local.dt.dayofweek
    out["mes"] = local.dt.month
    out["es_feriado"] = fecha_local.isin(fer).astype(int)
    out["es_fin_semana"] = (out["dia_semana"] >= 5).astype(int)
    # día hábil entre feriado y fin de semana ("sándwich")
    dia_antes = (local - pd.Timedelta(days=1)).dt.date.isin(fer)
    dia_despues = (local + pd.Timedelta(days=1)).dt.date.isin(fer)
    out["es_puente"] = (
        (out["es_feriado"] == 0) & (out["es_fin_semana"] == 0) & (dia_antes | dia_despues)
    ).astype(int)
    out["offset_utc_h"] = local.map(lambda t: t.utcoffset().total_seconds() / 3600)
    return out
