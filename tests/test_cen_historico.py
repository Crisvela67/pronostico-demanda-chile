"""Tests del lector del histórico CEN con un archivo que replica su formato real.

Formatos observados en el archivo oficial (octubre 2026):
- 2018: fecha, dia, hora (1..24, y 25 el día del cambio a invierno), SEN
- 2025: fecha, hora (1..23 y la hora 24 escrita como 0), SEN; día de 25 y de 23 filas
"""
import pandas as pd
import pytest

from demanda.fuentes import cen_historico


def _dia(fecha, horas, dia=None):
    filas = []
    for i, h in enumerate(horas):
        fila = {"fecha": pd.Timestamp(fecha), "hora": h, "SEN": 8000.0 + i}
        if dia is not None:
            fila = {"fecha": fila["fecha"], "dia": dia, "hora": h, "SEN": fila["SEN"]}
        filas.append(fila)
    return filas


@pytest.fixture
def archivo(tmp_path):
    h24 = list(range(1, 25))
    h2025 = list(range(1, 24)) + [0]
    y2018 = (_dia("2018-05-11", h24, 131) + _dia("2018-05-12", h24 + [25], 132)
             + _dia("2018-05-13", h24, 133))
    y2025 = (_dia("2025-04-04", h2025) + _dia("2025-04-05", h2025 + [0]) + _dia("2025-04-06", h2025)
             + _dia("2025-09-06", h2025) + _dia("2025-09-07", list(range(1, 23)) + [0])
             + _dia("2025-09-08", h2025))
    ruta = tmp_path / "CEN-hist_gen_de_energia_por_hora.xlsx"
    # título en la fila 1 y encabezados en la fila 2, como en el original
    with pd.ExcelWriter(ruta) as w:
        pd.DataFrame([["Notas"]]).to_excel(w, sheet_name="Notas", index=False, header=False)
        for nombre, filas in (("2018", y2018), ("2025", y2025)):
            df = pd.DataFrame(filas)
            pd.DataFrame([["Generación Horaria [MWh/h]"]]).to_excel(
                w, sheet_name=nombre, index=False, header=False, startrow=0)
            df.to_excel(w, sheet_name=nombre, index=False, startrow=1)
    return ruta


def test_serie_continua_sin_huecos_ni_duplicados(archivo):
    df = cen_historico.leer(archivo, desde_anio=2018)
    assert df["fecha_hora_utc"].is_unique
    for _, tramo in df.groupby(df["fecha_hora_utc"].dt.year):
        pasos = tramo["fecha_hora_utc"].diff().dropna()
        # dentro de cada bloque de días consecutivos las horas son contiguas
        assert (pasos[pasos < pd.Timedelta(days=1)] == pd.Timedelta(hours=1)).all()


def test_dia_de_25_horas_termina_en_medianoche_del_dia_siguiente(archivo):
    df = cen_historico.leer(archivo, desde_anio=2025)
    # 5-abr-2025: 00:00 UTC-3 = 03:00Z; 25 horas después = 04:00Z del 6-abr = 00:00 UTC-4
    dia5 = df[(df["fecha_hora_utc"] >= "2025-04-05 03:00Z") & (df["fecha_hora_utc"] < "2025-04-06 04:00Z")]
    assert len(dia5) == 25


def test_dia_de_23_horas(archivo):
    df = cen_historico.leer(archivo, desde_anio=2025)
    # 7-sep-2025 empieza 04:00Z (no existe 00:00 local) y termina 03:00Z del 8-sep
    dia7 = df[(df["fecha_hora_utc"] >= "2025-09-07 04:00Z") & (df["fecha_hora_utc"] < "2025-09-08 03:00Z")]
    assert len(dia7) == 23


def test_reporte_calidad_sin_alertas_cuando_el_formato_es_correcto(archivo):
    df = cen_historico.leer(archivo, desde_anio=2025)
    assert cen_historico.reporte_calidad(df).empty


def test_reporte_calidad_acepta_el_cambio_de_horario_de_2018(archivo):
    # 12-may-2018 fue el día del cambio a horario de invierno: 25 filas es correcto
    df = cen_historico.leer(archivo, desde_anio=2018)
    assert cen_historico.reporte_calidad(df).empty


def test_reporte_calidad_detecta_dia_con_filas_de_mas(tmp_path):
    # 11-may-2018 es un día normal; si trae 25 filas el reporte debe avisar
    filas = _dia("2018-05-11", list(range(1, 26)), 131)
    ruta = tmp_path / "malo.xlsx"
    with pd.ExcelWriter(ruta) as w:
        pd.DataFrame([["titulo"]]).to_excel(w, sheet_name="2018", index=False, header=False)
        pd.DataFrame(filas).to_excel(w, sheet_name="2018", index=False, startrow=1)
    rep = cen_historico.reporte_calidad(cen_historico.leer(ruta, desde_anio=2018))
    assert rep.iloc[0]["filas"] == 25 and rep.iloc[0]["esperadas"] == 24
