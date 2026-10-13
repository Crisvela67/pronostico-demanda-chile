"""Extractor de la API pública SIP del Coordinador Eléctrico Nacional.

La API pagina con un campo "next"; aquí se recorren todas las páginas.
Los nombres de parámetros y campos están en config/settings.yaml porque
deben verificarse contra la documentación vigente cuando tengas tu user_key.
"""
from __future__ import annotations

import json
from datetime import date

import pandas as pd
import requests

from demanda.config import secreto, settings
from demanda.normalizar import a_numero, construir_fecha_hora, esquema_comun


def _pedir_paginas(url: str, params: dict, timeout: int) -> list[dict]:
    filas: list[dict] = []
    sesion = requests.Session()
    while url:
        r = sesion.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        cuerpo = r.json()
        filas.extend(cuerpo.get("data") or cuerpo.get("results") or [])
        url = cuerpo.get("next")
        params = None  # la URL "next" ya trae los parámetros
    return filas


def descargar(desde: date, hasta: date, guardar_raw: bool = True) -> pd.DataFrame:
    cfg = settings()
    c = cfg["api_sip"]
    params = {
        "user_key": secreto("SIP_USER_KEY"),
        c["param_fecha_inicio"]: desde.isoformat(),
        c["param_fecha_fin"]: hasta.isoformat(),
    }
    url = f"{c['base_url']}/{c['endpoint_demanda']}/"
    filas = _pedir_paginas(url, params, c["timeout_s"])

    if guardar_raw:
        destino = cfg["rutas"]["raw"] / "api" / f"demanda_{desde}_{hasta}.json"
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(json.dumps(filas, ensure_ascii=False), encoding="utf-8")

    return desde_registros(filas)


def desde_registros(filas: list[dict]) -> pd.DataFrame:
    """Convierte la respuesta JSON al esquema común (separado para poder testearlo)."""
    c = settings()["api_sip"]
    df = pd.DataFrame(filas)
    if df.empty:
        return esquema_comun(pd.DataFrame(columns=["fecha_hora_utc", "demanda_mwh"]), "api")
    df["fecha_hora_utc"] = construir_fecha_hora(
        df[c["campo_fecha"]], df[c["campo_hora"]], c["convencion_hora"], settings()["zona_horaria"]
    )
    df["demanda_mwh"] = a_numero(df[c["campo_demanda"]])
    return esquema_comun(df, "api")
