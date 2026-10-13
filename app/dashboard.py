"""Dashboard Streamlit: pronóstico, desempeño del modelo y validación de fuentes.

    streamlit run app/dashboard.py
"""
import json

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from demanda.config import settings

st.set_page_config(page_title="Demanda eléctrica Chile", layout="wide")
r = settings()["rutas"]
proc, val, mod = r["processed"], r["validation"], r["modelos"]


def a_local(df, col="fecha_hora_utc"):
    df = df.copy()
    df[col] = pd.to_datetime(df[col], utc=True).dt.tz_convert("America/Santiago")
    return df


st.title("Pronóstico de demanda eléctrica — Sistema Eléctrico Nacional")

if not (mod / "metricas.json").exists():
    st.warning("Aún no hay modelo. Corre `python -m demanda.pipeline demo` o `diario`.")
    st.stop()

m = json.loads((mod / "metricas.json").read_text())
c1, c2, c3 = st.columns(3)
c1.metric("MAPE modelo", f"{m['mape_modelo']:.2f} %")
c2.metric("MAPE baseline (semana pasada)", f"{m['mape_baseline_semana']:.2f} %",
          delta=f"{m['mape_modelo'] - m['mape_baseline_semana']:.2f} pp", delta_color="inverse")
c3.metric("MAE modelo", f"{m['mae_modelo']:,.0f} MWh")

st.subheader("Próximas 24 horas")
if (proc / "pronostico.parquet").exists():
    pron = a_local(pd.read_parquet(proc / "pronostico.parquet"))
    hist = a_local(pd.read_parquet(proc / "demanda_api.parquet")).tail(72)
    fig = go.Figure()
    fig.add_scatter(x=hist["fecha_hora_utc"], y=hist["demanda_mwh"], name="Real")
    fig.add_scatter(x=pron["fecha_hora_utc"], y=pron["pronostico_mwh"], name="Pronóstico",
                    line={"dash": "dash"})
    fig.update_layout(yaxis_title="MWh", height=380, margin={"t": 10})
    st.plotly_chart(fig, use_container_width=True)

st.subheader("Desempeño en el período de prueba")
if (proc / "resultado_test.parquet").exists():
    t = a_local(pd.read_parquet(proc / "resultado_test.parquet")).tail(24 * 14)
    fig = go.Figure()
    fig.add_scatter(x=t["fecha_hora_utc"], y=t["demanda_mwh"], name="Real")
    fig.add_scatter(x=t["fecha_hora_utc"], y=t["pronostico"], name="Modelo")
    fig.add_scatter(x=t["fecha_hora_utc"], y=t["lag_168h"], name="Baseline", opacity=0.5)
    fig.update_layout(yaxis_title="MWh", height=380, margin={"t": 10})
    st.plotly_chart(fig, use_container_width=True)

st.subheader("Validación cruzada API vs XLS")
if (val / "ultimo_resumen.json").exists():
    res = json.loads((val / "ultimo_resumen.json").read_text())
    v1, v2, v3, v4 = st.columns(4)
    v1.metric("Horas comparadas", res["horas_comparadas"])
    v2.metric("Alertas", res["alertas"])
    v3.metric("Faltantes", res["faltantes"])
    v4.metric("Diferencia máx.", f"{res['dif_pct_max']:.2f} %")
    ultimos = sorted(val.glob("validacion_*.csv"))
    if ultimos:
        det = pd.read_csv(ultimos[-1])
        st.dataframe(det[det["estado"] != "ok"], use_container_width=True)
else:
    st.info("Sin validación todavía (se necesita API y XLS).")
