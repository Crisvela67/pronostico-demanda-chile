"""Reporte visual: mapas de calor, tendencias y desempeño del modelo.

Genera PNG en reports/figures/, un reports/RESULTADOS.md con todos los gráficos
y actualiza la sección de resultados del README (entre marcadores).

    python -m demanda.pipeline reporte
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm  # noqa: E402

from demanda.config import RAIZ  # noqa: E402

ZONA = "America/Santiago"
REPORTS = RAIZ / "reports"
FIG = REPORTS / "figures"

# Paleta de referencia validada (guía dataviz): superficie, tintas y series
SUP, INK, INK2, MUTED, GRID, BASE = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
AZUL, NARANJA, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
RAMPA_AZUL = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
SEQ = LinearSegmentedColormap.from_list("azul", RAMPA_AZUL)
DIV = LinearSegmentedColormap.from_list("div", ["#184f95", "#6da7ec", "#f0efec", "#ec8a89", "#b52f2f"])
DIAS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]

plt.rcParams.update({
    "figure.facecolor": SUP, "axes.facecolor": SUP, "savefig.facecolor": SUP,
    "font.family": "DejaVu Sans", "font.size": 10.5,
    "text.color": INK, "axes.labelcolor": INK2, "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.edgecolor": BASE, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": False, "grid.color": GRID, "grid.linewidth": 0.6,
    "axes.titlesize": 13, "axes.titleweight": "bold", "axes.titlelocation": "left",
    "axes.titlepad": 14, "legend.frameon": False, "lines.linewidth": 2,
})


def _titulo(ax, titulo: str, sub: str | None = None) -> None:
    ax.set_title(titulo, color=INK, pad=30 if sub else 14)
    if sub:
        ax.annotate(sub, xy=(0, 1), xycoords="axes fraction", xytext=(0, 9),
                    textcoords="offset points", color=INK2, fontsize=9.5, va="bottom")


def _guardar(fig, nombre: str) -> str:
    FIG.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG / nombre, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return f"figures/{nombre}"


def _barra_color(fig, im, ax, etiqueta):
    cb = fig.colorbar(im, ax=ax, fraction=0.025, pad=0.015)
    cb.outline.set_visible(False)
    cb.ax.tick_params(colors=MUTED, length=0)
    cb.set_label(etiqueta, color=INK2)
    return cb


def _local(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["t"] = out["fecha_hora_utc"].dt.tz_convert(ZONA)
    out["anio"], out["mes"], out["hora"] = out["t"].dt.year, out["t"].dt.month, out["t"].dt.hour
    out["dow"], out["doy"], out["fecha"] = out["t"].dt.dayofweek, out["t"].dt.dayofyear, out["t"].dt.date
    return out


# ---------- Exploración ----------

def fig_huella(d: pd.DataFrame) -> str:
    diario = d.groupby(["anio", "doy"])["demanda_mwh"].mean().unstack()
    fig, ax = plt.subplots(figsize=(13, 0.5 * len(diario) + 1.8))
    im = ax.imshow(diario.values, aspect="auto", cmap=SEQ, interpolation="nearest")
    ax.set_yticks(range(len(diario)), diario.index)
    inicios = pd.date_range("2021-01-01", periods=12, freq="MS").dayofyear - 1
    ax.set_xticks(inicios, MESES)
    ax.tick_params(length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    _barra_color(fig, im, ax, "MWh/h promedio del día")
    _titulo(ax, "La huella del sistema eléctrico: cada día, cada año",
            "Generación bruta promedio diaria del SEN. Se ven los inviernos, los fines de semana y la caída de 2020.")
    return _guardar(fig, "01_huella_calendario.png")


def _heatmap(m: pd.DataFrame, yt, titulo, sub, nombre, etiqueta="MWh/h promedio") -> str:
    fig, ax = plt.subplots(figsize=(12, 0.42 * len(m) + 1.6))
    im = ax.imshow(m.values, aspect="auto", cmap=SEQ, interpolation="nearest")
    ax.set_yticks(range(len(m)), yt)
    ax.set_xticks(range(0, 24, 2), [f"{h:02d}" for h in range(0, 24, 2)])
    ax.set_xlabel("Hora local")
    ax.tick_params(length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    # anotar el máximo de cada fila
    for i, fila in enumerate(m.values):
        j = int(np.nanargmax(fila))
        ax.text(j, i, "▲", ha="center", va="center", color="white", fontsize=7)
    _barra_color(fig, im, ax, etiqueta)
    _titulo(ax, titulo, sub)
    return _guardar(fig, nombre)


def fig_hora_dia(d):
    m = d.pivot_table(index="dow", columns="hora", values="demanda_mwh", aggfunc="mean")
    return _heatmap(m, DIAS, "¿Cuándo consume más Chile? Hora × día de la semana",
                    "▲ marca la hora de mayor demanda de cada día.", "02_hora_vs_dia_semana.png")


def fig_hora_mes(d):
    m = d.pivot_table(index="mes", columns="hora", values="demanda_mwh", aggfunc="mean")
    return _heatmap(m, [MESES[i - 1] for i in m.index], "El ritmo del año: hora × mes",
                    "▲ marca la hora punta de cada mes; en invierno la punta se corre a la tarde-noche.",
                    "03_hora_vs_mes.png")


def fig_tendencia(d) -> tuple[str, dict]:
    # en Chile la medianoche no existe el día que se adelanta el reloj: se agrupa en hora local "ingenua"
    mensual = d.set_index(d["t"].dt.tz_localize(None))["demanda_mwh"].resample("MS").mean()
    anual = d.groupby("anio")["demanda_mwh"].agg(["mean", "count"])
    anual = anual[anual["count"] > 24 * 300]
    twh = anual["mean"] * 8760 / 1e6
    crec = twh.pct_change() * 100

    fig, ax = plt.subplots(figsize=(12, 4.6))
    ax.plot(mensual.index, mensual.values, color=AZUL)
    ax.grid(axis="y")
    ax.set_ylabel("MWh/h promedio mensual")
    ax.set_ylim(mensual.min() * 0.92, mensual.max() * 1.12)
    for anio, v in twh.items():
        x = pd.Timestamp(f"{anio}-07-01")
        txt = f"{v:,.1f} TWh".replace(",", "X").replace(".", ",").replace("X", ".")
        if anio in crec and not np.isnan(crec[anio]):
            txt += f"\n{crec[anio]:+.1f} %".replace(".", ",")
        ax.text(x, mensual.max() * 1.02, txt, ha="center", va="bottom", fontsize=8.5, color=INK2)
    _titulo(ax, "Tendencia: energía anual y crecimiento",
            "Línea: promedio mensual. Arriba: energía anual estimada y variación respecto del año anterior.")
    info = {"twh_por_anio": {int(k): round(float(v), 2) for k, v in twh.items()},
            "crecimiento_pct": {int(k): round(float(v), 2) for k, v in crec.dropna().items()}}
    return _guardar(fig, "04_tendencia_mensual.png"), info


def fig_temperatura(d, clima) -> tuple[str | None, dict]:
    if clima is None or clima.empty:
        return None, {}
    x = d.merge(clima, on="fecha_hora_utc", how="inner")
    dia = x[x["dow"] < 5].groupby("fecha").agg(temp=("temp_c", "mean"), dem=("demanda_mwh", "mean"))
    if len(dia) < 50:
        return None, {}
    fig, ax = plt.subplots(figsize=(8.5, 5.6))
    hb = ax.hexbin(dia["temp"], dia["dem"], gridsize=38, cmap=SEQ, mincnt=1, linewidths=0.2,
                   edgecolors=SUP)
    coef = np.polyfit(dia["temp"], dia["dem"], 2)
    xs = np.linspace(dia["temp"].min(), dia["temp"].max(), 100)
    ax.plot(xs, np.polyval(coef, xs), color=NARANJA, lw=2)
    t_min = -coef[1] / (2 * coef[0]) if coef[0] > 0 else np.nan
    if dia["temp"].min() < t_min < dia["temp"].max():
        ax.axvline(t_min, color=MUTED, lw=1, ls=":")
        ax.text(t_min, dia["dem"].max(), f"  mínimo ≈ {t_min:.0f} °C", color=INK2, fontsize=9, va="top")
    ax.set_xlabel("Temperatura media del día (°C, ponderada Santiago/Antofagasta/Concepción)")
    ax.set_ylabel("MWh/h promedio del día")
    _barra_color(fig, hb, ax, "días")
    _titulo(ax, "Frío y calor: la curva en U del consumo",
            "Días hábiles. La línea naranja es un ajuste cuadrático.")
    corr = float(np.corrcoef(dia["temp"], dia["dem"])[0, 1])
    return _guardar(fig, "05_temperatura_vs_demanda.png"), {
        "temp_min_consumo_c": None if np.isnan(t_min) else round(float(t_min), 1), "corr_lineal": round(corr, 3)}


def fig_covid(d) -> tuple[str | None, dict]:
    if not {2019, 2020}.issubset(set(d["anio"])):
        return None, {}
    sem = d.assign(sem=d["t"].dt.isocalendar().week.astype(int)).query("sem <= 52")
    s = sem.pivot_table(index="sem", columns="anio", values="demanda_mwh", aggfunc="mean")
    base = s[[c for c in (2018, 2019) if c in s]].mean(axis=1)
    var = (s[2020] / base - 1) * 100
    fig, ax = plt.subplots(figsize=(12, 4.4))
    colores = [AZUL if v >= 0 else "#d03b3b" for v in var.values]
    ax.bar(var.index, var.values, color=colores, width=0.8)
    ax.axhline(0, color=BASE, lw=1)
    ax.grid(axis="y")
    ax.set_xlabel("Semana del año")
    ax.set_ylabel("% vs promedio 2018-2019")
    peor = var.idxmin()
    ax.annotate(f"semana {peor}: {var.min():.1f} %".replace(".", ","), (peor, var.min()),
                xytext=(peor + 4, var.min()), color=INK2, fontsize=9,
                arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.8))
    _titulo(ax, "2020: el año en que la pandemia apagó parte del país",
            "Demanda semanal de 2020 comparada con el promedio de 2018-2019 (rojo: menos consumo).")
    return _guardar(fig, "06_covid_2020.png"), {"covid_peor_semana": int(peor),
                                                 "covid_peor_caida_pct": round(float(var.min()), 1)}


# ---------- Modelo ----------

def _mape(r, p):
    r, p = np.asarray(r, float), np.asarray(p, float)
    return float(np.mean(np.abs((r - p) / r)) * 100)


def fig_pronostico(test) -> str:
    t = test.copy()
    t["t"] = t["fecha_hora_utc"].dt.tz_convert(ZONA)
    # dos semanas de invierno si existen, si no las últimas dos
    inv = t[t["t"].dt.month == 7]
    tramo = (inv if len(inv) >= 24 * 14 else t).iloc[: 24 * 14]
    fig, ax = plt.subplots(figsize=(13, 4.8))
    ax.plot(tramo["t"], tramo["demanda_mwh"], color=INK, lw=2, label="Real")
    ax.plot(tramo["t"], tramo["pronostico"], color=AZUL, lw=2, label="Modelo (LightGBM)")
    ax.plot(tramo["t"], tramo["lag_168h"], color=NARANJA, lw=1.4, ls="--", label="Baseline: semana pasada")
    ax.grid(axis="y")
    ax.set_ylabel("MWh/h")
    ax.legend(loc="upper center", ncols=3, bbox_to_anchor=(0.5, -0.1))
    ax.margins(x=0)
    import matplotlib.dates as mdates
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d-%m", tz=tramo["t"].dt.tz))
    _titulo(ax, "Pronóstico vs realidad: dos semanas del período de prueba",
            f"Período fuera de muestra (el modelo nunca vio estos datos al entrenar).")
    return _guardar(fig, "07_pronostico_vs_real.png")


def fig_error_hora(test) -> str:
    t = test.assign(hora=test["fecha_hora_utc"].dt.tz_convert(ZONA).dt.hour)
    m = t.groupby("hora").apply(lambda g: pd.Series({
        "Modelo": _mape(g["demanda_mwh"], g["pronostico"]),
        "Semana pasada": _mape(g["demanda_mwh"], g["lag_168h"])}), include_groups=False)
    fig, ax = plt.subplots(figsize=(12, 4.4))
    x = np.arange(24)
    ax.bar(x - 0.21, m["Semana pasada"], width=0.4, color=NARANJA, label="Baseline: semana pasada")
    ax.bar(x + 0.21, m["Modelo"], width=0.4, color=AZUL, label="Modelo")
    ax.set_xticks(x, [f"{h:02d}" for h in x])
    ax.set_xlabel("Hora local")
    ax.set_ylabel("Error MAPE (%)")
    ax.grid(axis="y")
    ax.legend(loc="upper center", ncols=2, bbox_to_anchor=(0.5, -0.16))
    _titulo(ax, "¿A qué hora se equivoca más?", "Error porcentual medio por hora del día, período de prueba.")
    return _guardar(fig, "08_error_por_hora.png")


def fig_error_heatmap(test) -> str:
    t = test.copy()
    tl = t["fecha_hora_utc"].dt.tz_convert(ZONA)
    t["hora"], t["mes"] = tl.dt.hour, tl.dt.month
    t["sesgo"] = (t["pronostico"] - t["demanda_mwh"]) / t["demanda_mwh"] * 100
    m = t.pivot_table(index="mes", columns="hora", values="sesgo", aggfunc="mean")
    lim = max(1.0, float(np.nanpercentile(np.abs(m.values), 98)))
    fig, ax = plt.subplots(figsize=(12, 0.42 * len(m) + 1.6))
    im = ax.imshow(m.values, aspect="auto", cmap=DIV, norm=TwoSlopeNorm(0, -lim, lim),
                   interpolation="nearest")
    ax.set_yticks(range(len(m)), [MESES[i - 1] for i in m.index])
    ax.set_xticks(range(0, 24, 2), [f"{h:02d}" for h in range(0, 24, 2)])
    ax.set_xlabel("Hora local")
    ax.tick_params(length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    _barra_color(fig, im, ax, "sesgo % (rojo: sobreestima)")
    _titulo(ax, "Dónde se sesga el modelo: hora × mes",
            "Azul: pronostica menos que lo real. Rojo: pronostica más. Gris: sin sesgo.")
    return _guardar(fig, "09_sesgo_hora_mes.png")


NOMBRES = {
    "lag_24h": "Demanda hace 24 h", "lag_48h": "Demanda hace 48 h", "lag_168h": "Demanda hace 1 semana",
    "media_7d_lag24": "Promedio últimos 7 días", "hora_local": "Hora del día", "hora_sin": "Hora (seno)",
    "hora_cos": "Hora (coseno)", "dia_semana": "Día de la semana", "mes": "Mes", "es_feriado": "Feriado",
    "es_fin_semana": "Fin de semana", "es_puente": "Día puente", "offset_utc_h": "Horario verano/invierno",
    "temp_c": "Temperatura", "grados_calefaccion": "Grados-día calefacción",
    "grados_enfriamiento": "Grados-día enfriamiento",
}


def fig_importancia(paquete) -> str:
    m, cols = paquete["modelo"], paquete["columnas"]
    imp = pd.Series(m.booster_.feature_importance("gain"), index=cols)
    imp = (imp / imp.sum() * 100).sort_values().tail(12)
    fig, ax = plt.subplots(figsize=(9, 5.2))
    ax.barh([NOMBRES.get(c, c) for c in imp.index], imp.values, color=AZUL, height=0.6)
    for y, v in enumerate(imp.values):
        ax.text(v + 0.4, y, f"{v:.1f} %".replace(".", ","), va="center", fontsize=9, color=INK2)
    ax.set_xlabel("Importancia (% de la ganancia total)")
    ax.tick_params(axis="y", length=0, colors=INK)
    ax.spines["left"].set_visible(False)
    _titulo(ax, "¿Qué mira el modelo para predecir?", "Importancia de cada variable en LightGBM.")
    return _guardar(fig, "10_importancia_variables.png")


def fig_metricas(met) -> str:
    nombres = ["Ayer, misma hora", "Semana pasada, misma hora", "Modelo LightGBM"]
    vals = [met["mape_baseline_dia"], met["mape_baseline_semana"], met["mape_modelo"]]
    fig, ax = plt.subplots(figsize=(8, 3.2))
    ax.barh(nombres, vals, color=[BASE, NARANJA, AZUL], height=0.55)
    for y, v in enumerate(vals):
        ax.text(v + max(vals) * 0.01, y, f"{v:.2f} %".replace(".", ","), va="center", color=INK, fontsize=10)
    ax.set_xlabel("Error MAPE en el período de prueba (menor es mejor)")
    ax.tick_params(axis="y", length=0, colors=INK)
    ax.spines["left"].set_visible(False)
    mejora = (1 - met["mape_modelo"] / met["mape_baseline_semana"]) * 100
    _titulo(ax, f"El modelo reduce el error {mejora:.0f} % frente al mejor baseline".replace(".", ","))
    return _guardar(fig, "00_metricas.png")


# ---------- Documento ----------

def _fmt(x, dec=1):
    return f"{x:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def generar(demanda: pd.DataFrame, clima: pd.DataFrame | None, test: pd.DataFrame | None,
            metricas: dict | None, paquete: dict | None, fuente: str) -> dict:
    d = _local(demanda.dropna(subset=["demanda_mwh"]))
    figs, info = {}, {}
    figs["huella"] = fig_huella(d)
    figs["hora_dia"] = fig_hora_dia(d)
    figs["hora_mes"] = fig_hora_mes(d)
    figs["tendencia"], i = fig_tendencia(d); info.update(i)
    f, i = fig_temperatura(d, clima); info.update(i)
    if f: figs["temperatura"] = f
    f, i = fig_covid(d); info.update(i)
    if f: figs["covid"] = f
    if test is not None and metricas:
        figs["metricas"] = fig_metricas(metricas)
        figs["pronostico"] = fig_pronostico(test)
        figs["error_hora"] = fig_error_hora(test)
        figs["sesgo"] = fig_error_heatmap(test)
    if paquete is not None:
        figs["importancia"] = fig_importancia(paquete)

    pico = d.loc[d["demanda_mwh"].idxmax()]
    hp = d.groupby("hora")["demanda_mwh"].mean()
    info.update({
        "fuente": fuente,
        "desde": str(d["t"].min().date()), "hasta": str(d["t"].max().date()), "horas": int(len(d)),
        "maximo_mwh": round(float(pico["demanda_mwh"]), 1), "maximo_fecha": str(pico["t"]),
        "hora_punta_promedio": int(hp.idxmax()), "hora_valle_promedio": int(hp.idxmin()),
        "finde_vs_habil_pct": round(float(d[d["dow"] >= 5]["demanda_mwh"].mean()
                                          / d[d["dow"] < 5]["demanda_mwh"].mean() * 100 - 100), 1),
    })
    if metricas:
        info["metricas"] = metricas
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / "resumen.json").write_text(json.dumps(info, indent=2, ensure_ascii=False), encoding="utf-8")
    _escribir_md(figs, info)
    _actualizar_readme(figs, info)
    return info


def _kpis(info) -> str:
    filas = [
        ("Período analizado", f"{info['desde']} a {info['hasta']} ({_fmt(info['horas'], 0)} horas)"),
        ("Máximo horario", f"{_fmt(info['maximo_mwh'], 0)} MWh/h ({info['maximo_fecha'][:16]})"),
        ("Hora punta promedio", f"{info['hora_punta_promedio']:02d}:00 · valle {info['hora_valle_promedio']:02d}:00"),
        ("Fin de semana vs día hábil", f"{_fmt(info['finde_vs_habil_pct'])} %"),
    ]
    if "covid_peor_caida_pct" in info:
        filas.append(("Peor semana de 2020 (pandemia)", f"{_fmt(info['covid_peor_caida_pct'])} % vs 2018-2019"))
    if info.get("temp_min_consumo_c") is not None:
        filas.append(("Temperatura de menor consumo", f"≈ {_fmt(info['temp_min_consumo_c'], 0)} °C"))
    m = info.get("metricas")
    if m:
        filas += [
            ("**Error del modelo (MAPE)**", f"**{_fmt(m['mape_modelo'], 2)} %**"),
            ("Baseline semana pasada", f"{_fmt(m['mape_baseline_semana'], 2)} %"),
            ("Baseline ayer", f"{_fmt(m['mape_baseline_dia'], 2)} %"),
            ("Error medio absoluto", f"{_fmt(m['mae_modelo'], 0)} MWh/h"),
        ]
    return "| Indicador | Valor |\n|---|---|\n" + "\n".join(f"| {a} | {b} |" for a, b in filas)


def _escribir_md(figs, info):
    secciones = [
        ("huella", "Mapa de calor anual", "Cada fila es un año y cada columna un día. Lo oscuro es más consumo."),
        ("hora_dia", "Hora × día de la semana", "El patrón semanal: valle de madrugada, meseta laboral y punta nocturna."),
        ("hora_mes", "Hora × mes", "Cómo se mueve la punta durante el año."),
        ("tendencia", "Tendencia y crecimiento", ""),
        ("temperatura", "Temperatura y consumo", "El consumo sube cuando hace frío (calefacción) y cuando hace calor (refrigeración)."),
        ("covid", "El efecto de la pandemia", ""),
        ("metricas", "Desempeño del modelo", "Pronóstico a 24 horas evaluado sobre datos que el modelo no vio."),
        ("pronostico", "Pronóstico vs realidad", ""),
        ("error_hora", "Error por hora del día", ""),
        ("sesgo", "Sesgo del modelo por hora y mes", ""),
        ("importancia", "Qué variables importan", ""),
    ]
    partes = [f"# Resultados\n\n> Generado automáticamente por `python -m demanda.pipeline reporte`. "
              f"Fuente: {info['fuente']}.\n\n## Resumen\n\n{_kpis(info)}\n"]
    for clave, titulo, texto in secciones:
        if clave in figs:
            partes.append(f"## {titulo}\n\n{texto}\n\n![{titulo}]({figs[clave]})\n")
    (REPORTS / "RESULTADOS.md").write_text("\n".join(partes), encoding="utf-8")


INI, FIN = "<!-- RESULTADOS:INICIO -->", "<!-- RESULTADOS:FIN -->"


def _actualizar_readme(figs, info):
    readme = RAIZ / "README.md"
    if not readme.exists():
        return
    txt = readme.read_text(encoding="utf-8")
    if INI not in txt or FIN not in txt:
        return
    imgs = [k for k in ("metricas", "huella", "hora_dia", "pronostico") if k in figs]
    cuerpo = (f"\n_Actualizado automáticamente. Fuente: {info['fuente']}._\n\n{_kpis(info)}\n\n"
              + "\n\n".join(f"![{k}](reports/{figs[k]})" for k in imgs)
              + "\n\n**[Ver el reporte completo con todos los gráficos →](reports/RESULTADOS.md)**\n")
    a, b = txt.index(INI) + len(INI), txt.index(FIN)
    readme.write_text(txt[:a] + cuerpo + txt[b:], encoding="utf-8")
