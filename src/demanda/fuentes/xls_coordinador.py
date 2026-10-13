"""Lector de los archivos XLS/XLSX descargados del sitio del Coordinador.

Soporta dos formatos (configurable en settings.yaml):
- "ancho": una fila por día y una columna por hora (1..24).
- "largo": una fila por hora, con columnas de fecha, hora y demanda.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from demanda.config import settings
from demanda.normalizar import a_numero, construir_fecha_hora, esquema_comun


def _columnas_hora(columnas) -> list:
    horas = []
    for col in columnas:
        texto = str(col).strip().lower().replace("hora", "").replace("h", "").strip()
        if texto.isdigit() and 0 <= int(texto) <= 25:
            horas.append(col)
    return horas


def leer(ruta: str | Path) -> pd.DataFrame:
    c = settings()["xls"]
    zona = settings()["zona_horaria"]
    df = pd.read_excel(ruta, sheet_name=c["hoja"], header=c["fila_encabezado"])
    df.columns = [str(x).strip() for x in df.columns]
    # celdas combinadas: la fecha solo aparece en la primera fila del bloque
    df[c["columna_fecha"]] = df[c["columna_fecha"]].ffill()

    if c["formato"] == "ancho":
        horas = _columnas_hora(df.columns)
        if not horas:
            raise ValueError(f"No encontré columnas de hora en {ruta}: {list(df.columns)}")
        largo = df.melt(
            id_vars=[c["columna_fecha"]], value_vars=horas, var_name="hora", value_name="demanda"
        )
        largo["hora"] = largo["hora"].astype(str).str.extract(r"(\d+)")[0]
        fecha_col, hora_col, dem_col = c["columna_fecha"], "hora", "demanda"
    else:
        largo = df
        fecha_col, hora_col, dem_col = c["columna_fecha"], c["columna_hora"], c["columna_demanda"]

    # el orden cronológico es necesario para resolver la hora repetida del cambio de horario
    largo = largo.assign(
        _f=pd.to_datetime(largo[fecha_col], dayfirst=True, errors="coerce"),
        _h=pd.to_numeric(largo[hora_col], errors="coerce"),
    ).sort_values(["_f", "_h"])
    largo["fecha_hora_utc"] = construir_fecha_hora(
        largo[fecha_col], largo[hora_col], c["convencion_hora"], zona
    )
    largo["demanda_mwh"] = a_numero(largo[dem_col], c["decimal"])
    return esquema_comun(largo, "xls")


def leer_carpeta(carpeta: str | Path | None = None) -> pd.DataFrame:
    carpeta = Path(carpeta or settings()["rutas"]["xls_entrada"])
    archivos = sorted(list(carpeta.glob("*.xls")) + list(carpeta.glob("*.xlsx")))
    if not archivos:
        return esquema_comun(pd.DataFrame(columns=["fecha_hora_utc", "demanda_mwh"]), "xls")
    partes = [leer(a) for a in archivos]
    return esquema_comun(pd.concat(partes), "xls")
