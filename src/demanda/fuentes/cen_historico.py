"""Histórico oficial de generación bruta horaria del Coordinador (2000 en adelante).

Archivo público, sin key:
    https://www.coordinador.cl/wp-content/uploads/2026/05/CEN-hist_gen_de_energia_por_hora_26.xlsx
(publicado en "Reportes y Estadísticas"; la URL cambia cuando sale una versión nueva,
por eso está en settings.yaml).

Se usa la generación bruta del SEN como proxy de la demanda: la diferencia son
pérdidas de transmisión y consumos propios, del orden de pocos puntos porcentuales,
y su patrón horario es el mismo.

Formato observado en el archivo (verificado en octubre de 2026):
- Una hoja por año ("2000"... "2025") y una hoja "Notas".
- Fila 1: título; fila 2: encabezados.
- Hasta 2016: columnas fecha, dia, hora, SIC, SING (sistemas separados).
- 2017-2024: fecha, dia, hora, SEN.  2025: fecha, hora, SEN (sin "dia").
- Hora local 1..24; el día del cambio a horario de invierno trae una hora 25.
- En 2025 la hora 24 viene codificada como 0.
- Según el año, el día del cambio a horario de verano trae 23 o 24 filas; cuando trae 24,
  la hora inexistente viene en 0 y se descarta.

Por esas inconsistencias NO se interpreta la etiqueta de hora: dentro de cada fecha
se usa el orden de las filas. La fila k de un día empieza k horas después de la
medianoche local de ese día (convertida a UTC), lo que resuelve solo los días de
23 y 25 horas. `reporte_calidad` avisa cuando un día no trae las horas esperadas.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from demanda.config import settings
from demanda.normalizar import esquema_comun

ZONA = "America/Santiago"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (proyecto pronostico-demanda-chile)",
    "Referer": "https://www.coordinador.cl/reportes-y-estadisticas/",
}


def ruta_local() -> Path:
    return settings()["rutas"]["raw"] / "cen" / Path(settings()["cen_historico"]["url"]).name


def descargar(forzar: bool = False, max_dias: int = 30) -> Path:
    """Descarga el archivo si no existe o si la copia local tiene más de `max_dias`."""
    import requests

    destino = ruta_local()
    destino.parent.mkdir(parents=True, exist_ok=True)
    if destino.exists() and not forzar:
        edad = datetime.now(timezone.utc).timestamp() - destino.stat().st_mtime
        if edad < max_dias * 86400:
            return destino
    r = requests.get(settings()["cen_historico"]["url"], headers=HEADERS, timeout=180)
    r.raise_for_status()
    destino.write_bytes(r.content)
    return destino


def _a_fecha(col: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(col):  # número de serie de Excel
        return pd.to_datetime(col, unit="D", origin="1899-12-30")
    return pd.to_datetime(col, errors="coerce", dayfirst=True)


def _leer_hoja(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [str(c).strip().upper() for c in df.columns]
    if "SEN" in df:
        valor = pd.to_numeric(df["SEN"], errors="coerce")
    elif {"SIC", "SING"} <= set(df.columns):
        valor = pd.to_numeric(df["SIC"], errors="coerce").fillna(0) + pd.to_numeric(
            df["SING"], errors="coerce").fillna(0)
    else:
        raise ValueError(f"Columnas inesperadas: {list(df.columns)}")
    out = pd.DataFrame({"fecha": _a_fecha(df["FECHA"]).dt.normalize(), "demanda_mwh": valor})
    # El día del cambio a horario de verano algunos años traen 24 filas con un 0 en la hora
    # que no existe: se descarta antes de ordenar (un SEN en 0 MWh no es un dato real).
    out = out.dropna(subset=["fecha", "demanda_mwh"])
    out = out[out["demanda_mwh"] > 0].reset_index(drop=True)
    out["pos"] = out.groupby("fecha").cumcount()  # orden de las filas dentro del día
    return out


def leer(ruta: str | Path | None = None, desde_anio: int | None = None) -> pd.DataFrame:
    ruta = Path(ruta or ruta_local())
    desde_anio = desde_anio or settings()["cen_historico"]["desde_anio"]
    libro = pd.ExcelFile(ruta)
    anios = [h for h in libro.sheet_names if str(h).strip().isdigit() and int(h) >= desde_anio]
    partes = [_leer_hoja(libro.parse(h, header=1)) for h in anios]
    if not partes:
        raise ValueError(f"No hay hojas de año >= {desde_anio} en {ruta}")
    datos = pd.concat(partes, ignore_index=True)

    inicio_dia_utc = (
        datos["fecha"].dt.tz_localize(ZONA, ambiguous=False, nonexistent="shift_forward")
        .dt.tz_convert("UTC")
    )
    datos["fecha_hora_utc"] = inicio_dia_utc + pd.to_timedelta(datos["pos"], unit="h")
    out = esquema_comun(datos, "cen_gen")
    out.attrs["filas_por_dia"] = datos.groupby("fecha").size()
    return out


def horas_esperadas(fechas: pd.Series) -> pd.Series:
    """23, 24 o 25 según el cambio de horario de cada día."""
    f = pd.to_datetime(pd.Series(fechas)).dt.normalize()
    ini = f.dt.tz_localize(ZONA, ambiguous=False, nonexistent="shift_forward")
    fin = (f + pd.Timedelta(days=1)).dt.tz_localize(ZONA, ambiguous=False, nonexistent="shift_forward")
    return ((fin - ini).dt.total_seconds() / 3600).round().astype(int).to_numpy()


def reporte_calidad(df_leido: pd.DataFrame) -> pd.DataFrame:
    """Días cuyo número de filas no coincide con las horas reales de ese día."""
    filas = df_leido.attrs.get("filas_por_dia")
    if filas is None:
        return pd.DataFrame(columns=["fecha", "filas", "esperadas"])
    rep = filas.rename("filas").reset_index()
    rep["esperadas"] = horas_esperadas(rep["fecha"])
    return rep[rep["filas"] != rep["esperadas"]].reset_index(drop=True)
