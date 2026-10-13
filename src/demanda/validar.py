"""Validación cruzada hora a hora entre dos fuentes de demanda (API vs XLS)."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class ResultadoValidacion:
    detalle: pd.DataFrame
    resumen: dict

    @property
    def ok(self) -> bool:
        return self.resumen["alertas"] == 0 and self.resumen["faltantes"] == 0


def comparar(
    a: pd.DataFrame,
    b: pd.DataFrame,
    tolerancia_pct: float = 0.5,
    nombres: tuple[str, str] = ("api", "xls"),
) -> ResultadoValidacion:
    na, nb = nombres
    cruce = a[["fecha_hora_utc", "demanda_mwh"]].merge(
        b[["fecha_hora_utc", "demanda_mwh"]],
        on="fecha_hora_utc",
        how="outer",
        suffixes=(f"_{na}", f"_{nb}"),
        indicator=True,
    )
    va, vb = cruce[f"demanda_mwh_{na}"], cruce[f"demanda_mwh_{nb}"]
    cruce["dif_mwh"] = va - vb
    cruce["dif_pct"] = (cruce["dif_mwh"].abs() / vb.abs()) * 100

    cruce["estado"] = "ok"
    cruce.loc[cruce["dif_pct"] > tolerancia_pct, "estado"] = "alerta"
    cruce.loc[cruce["_merge"] == "left_only", "estado"] = f"solo_{na}"
    cruce.loc[cruce["_merge"] == "right_only", "estado"] = f"solo_{nb}"
    cruce = cruce.drop(columns="_merge").sort_values("fecha_hora_utc").reset_index(drop=True)

    comunes = cruce[cruce["estado"].isin(["ok", "alerta"])]
    resumen = {
        "horas_comparadas": int(len(comunes)),
        "ok": int((cruce["estado"] == "ok").sum()),
        "alertas": int((cruce["estado"] == "alerta").sum()),
        "faltantes": int(cruce["estado"].str.startswith("solo_").sum()),
        "dif_pct_max": float(comunes["dif_pct"].max()) if len(comunes) else 0.0,
        "dif_pct_media": float(comunes["dif_pct"].mean()) if len(comunes) else 0.0,
        "desfase_sospechoso_h": detectar_desfase(a, b),
    }
    return ResultadoValidacion(cruce, resumen)


def detectar_desfase(a: pd.DataFrame, b: pd.DataFrame, max_h: int = 2) -> int:
    """Devuelve el corrimiento (en horas) que mejor alinea ambas series.

    Si no es 0, casi siempre es un problema de convención de hora (1-24 vs 0-23)
    o de zona horaria, no un error real de datos.
    """
    sa = a.set_index("fecha_hora_utc")["demanda_mwh"]
    sb = b.set_index("fecha_hora_utc")["demanda_mwh"]
    mejor, error_min = 0, float("inf")
    for k in range(-max_h, max_h + 1):
        movida = sb.copy()
        movida.index = movida.index + pd.Timedelta(hours=k)
        dif = (sa - movida).abs().dropna()
        if len(dif) and dif.mean() < error_min:
            mejor, error_min = k, dif.mean()
    return mejor
