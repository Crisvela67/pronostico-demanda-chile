"""Entrenamiento, evaluación y pronóstico.

Compara siempre contra un baseline ingenuo (misma hora de la semana pasada):
si el modelo no le gana, no aporta.
"""
from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from demanda.features import columnas_modelo


def mape(real, pred) -> float:
    real, pred = np.asarray(real, float), np.asarray(pred, float)
    m = (real != 0) & ~np.isnan(real) & ~np.isnan(pred)
    return float(np.mean(np.abs((real[m] - pred[m]) / real[m])) * 100)


def mae(real, pred) -> float:
    real, pred = np.asarray(real, float), np.asarray(pred, float)
    m = ~np.isnan(real) & ~np.isnan(pred)
    return float(np.mean(np.abs(real[m] - pred[m])))


def separar(df: pd.DataFrame, dias_test: int):
    datos = df.dropna(subset=["demanda_mwh", "lag_168h"])
    corte = datos["fecha_hora_utc"].max() - pd.Timedelta(days=dias_test)
    return datos[datos["fecha_hora_utc"] <= corte], datos[datos["fecha_hora_utc"] > corte]


def entrenar(df: pd.DataFrame, params: dict, dias_test: int = 60, usar_mlflow: bool = True):
    from lightgbm import LGBMRegressor

    train, test = separar(df, dias_test)
    cols = columnas_modelo(df)
    modelo = LGBMRegressor(**params, verbose=-1)
    modelo.fit(train[cols], train["demanda_mwh"])

    pred = modelo.predict(test[cols])
    metricas = {
        "mape_modelo": mape(test["demanda_mwh"], pred),
        "mae_modelo": mae(test["demanda_mwh"], pred),
        "mape_baseline_semana": mape(test["demanda_mwh"], test["lag_168h"]),
        "mape_baseline_dia": mape(test["demanda_mwh"], test["lag_24h"]),
        "horas_train": int(len(train)),
        "horas_test": int(len(test)),
    }

    if usar_mlflow:
        try:
            import mlflow

            with mlflow.start_run(run_name="lightgbm"):
                mlflow.log_params(params)
                mlflow.log_metrics({k: v for k, v in metricas.items() if isinstance(v, float)})
        except Exception as e:  # MLflow es opcional
            print(f"MLflow no disponible ({e}); continúo sin registrar.")

    resultado_test = test[["fecha_hora_utc", "demanda_mwh", "lag_168h"]].assign(pronostico=pred)
    return modelo, cols, metricas, resultado_test


def guardar(modelo, cols, metricas, carpeta: Path) -> None:
    carpeta.mkdir(parents=True, exist_ok=True)
    joblib.dump({"modelo": modelo, "columnas": cols}, carpeta / "modelo.joblib")
    (carpeta / "metricas.json").write_text(json.dumps(metricas, indent=2), encoding="utf-8")


def pronosticar(df_features: pd.DataFrame, carpeta: Path, horizonte_h: int = 24) -> pd.DataFrame:
    """Pronostica las próximas `horizonte_h` horas usando los rezagos ya conocidos."""
    from demanda.features import construir

    paquete = joblib.load(carpeta / "modelo.joblib")
    ultimo = df_features["fecha_hora_utc"].max()
    futuro = pd.DataFrame(
        {"fecha_hora_utc": pd.date_range(ultimo + pd.Timedelta(hours=1), periods=horizonte_h, freq="h"),
         "demanda_mwh": np.nan}
    )
    base = pd.concat([df_features[["fecha_hora_utc", "demanda_mwh"]], futuro])
    clima = None
    if "temp_c" in df_features:
        # sin pronóstico meteorológico se usa la temperatura del mismo horario de ayer
        clima = df_features[["fecha_hora_utc", "temp_c"]].copy()
        clima_fut = futuro[["fecha_hora_utc"]].copy()
        clima_fut["temp_c"] = df_features["temp_c"].tail(horizonte_h).to_numpy()
        clima = pd.concat([clima, clima_fut])
    feats = construir(base, clima).tail(horizonte_h)
    for c in paquete["columnas"]:
        if c not in feats:
            feats[c] = np.nan
    feats["pronostico_mwh"] = paquete["modelo"].predict(feats[paquete["columnas"]])
    return feats[["fecha_hora_utc", "pronostico_mwh"]].reset_index(drop=True)
