import pandas as pd

from demanda.normalizar import a_numero, construir_fecha_hora
from demanda.validar import comparar, detectar_desfase


def test_coma_decimal_chilena():
    s = pd.Series(["8.512,3", "9.001,0"])
    assert a_numero(s, ",").tolist() == [8512.3, 9001.0]


def test_convencion_1_24_equivale_a_0_23_menos_uno():
    f = pd.Series(["15-01-2026"] * 2)
    a = construir_fecha_hora(f, pd.Series([1, 24]), "1-24")
    b = construir_fecha_hora(f, pd.Series([0, 23]), "0-23")
    assert (a == b).all()


def test_enero_esta_en_utc_menos_3():
    t = construir_fecha_hora(pd.Series(["15-01-2026"]), pd.Series([0]), "0-23")
    assert t.iloc[0].hour == 3  # 00:00 local (verano, UTC-3) = 03:00 UTC


def _serie(valores, inicio="2026-01-01"):
    t = pd.date_range(inicio, periods=len(valores), freq="h", tz="UTC")
    return pd.DataFrame({"fecha_hora_utc": t, "demanda_mwh": valores})


def test_validacion_detecta_alerta_y_faltante():
    a = _serie([100.0, 200, 300, 400])
    b = _serie([100.0, 210, 300])  # hora 2 difiere 5 %, hora 4 falta
    r = comparar(a, b, tolerancia_pct=0.5)
    assert r.resumen["alertas"] == 1
    assert r.resumen["faltantes"] == 1
    assert not r.ok


def test_detecta_desfase_de_una_hora():
    valores = [float(v) for v in range(100, 148)]
    a = _serie(valores)
    b = _serie(valores, inicio="2025-12-31 23:00")  # misma serie, una hora antes
    assert detectar_desfase(a, b) == 1
