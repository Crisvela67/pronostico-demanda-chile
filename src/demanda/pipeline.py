"""Orquestador del pipeline. Lo usa GitHub Actions y también se corre a mano.

Uso:
    python -m demanda.pipeline demo                 # datos sintéticos, sin keys
    python -m demanda.pipeline historico            # histórico oficial CEN 2018-2025 + clima
    python -m demanda.pipeline ingesta --dias 7     # API + XLS + clima
    python -m demanda.pipeline validar
    python -m demanda.pipeline entrenar
    python -m demanda.pipeline pronosticar
    python -m demanda.pipeline reporte              # gráficos, mapas de calor y README
    python -m demanda.pipeline diario               # todo lo anterior en orden
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta

import numpy as np
import pandas as pd

from demanda import features, modelo, normalizar, validar
from demanda.config import RAIZ, settings


def _rutas():
    r = settings()["rutas"]
    return {
        "api": r["processed"] / "demanda_api.parquet",
        "xls": r["processed"] / "demanda_xls.parquet",
        "cen": r["processed"] / "demanda_cen_historico.parquet",
        "clima": r["processed"] / "clima.parquet",
        "validacion": r["validation"],
        "modelos": r["modelos"],
        "pronostico": r["processed"] / "pronostico.parquet",
        "test": r["processed"] / "resultado_test.parquet",
    }


def ingesta(dias: int) -> None:
    from demanda.fuentes import api_sip, clima, xls_coordinador

    p = _rutas()
    hasta = date.today() - timedelta(days=1)
    desde = hasta - timedelta(days=dias - 1)

    try:
        normalizar.guardar(api_sip.descargar(desde, hasta), p["api"])
        print(f"API SIP: {desde} a {hasta} OK")
    except RuntimeError as e:
        print(f"API SIP omitida: {e}")

    xls = xls_coordinador.leer_carpeta()
    if len(xls):
        normalizar.guardar(xls, p["xls"])
        print(f"XLS: {len(xls)} horas leídas")

    try:
        normalizar.guardar(clima.descargar(desde, hasta), p["clima"])
        print("Clima OK")
    except Exception as e:
        print(f"Clima omitido: {e}")


def historico(forzar: bool = False, con_clima: bool = True) -> None:
    """Descarga y procesa el histórico oficial de generación horaria del Coordinador."""
    from demanda.fuentes import cen_historico, clima

    p = _rutas()
    ruta = cen_historico.descargar(forzar=forzar)
    df = cen_historico.leer(ruta)
    rep = cen_historico.reporte_calidad(df)
    df.attrs = {}  # Parquet no admite metadatos que no sean JSON
    df.to_parquet(p["cen"], index=False)
    rep.to_csv(p["validacion"] / "calidad_cen_historico.csv", index=False)
    ini, fin = df["fecha_hora_utc"].min(), df["fecha_hora_utc"].max()
    print(f"Histórico CEN: {len(df)} horas, {ini:%Y-%m-%d} a {fin:%Y-%m-%d}")
    if len(rep):
        print(f"Ojo: {len(rep)} días con filas distintas a las esperadas "
              f"(ver data/validation/calidad_cen_historico.csv):")
        print(rep.head(10).to_string(index=False))

    if not con_clima:
        return
    previo = pd.read_parquet(p["clima"]) if p["clima"].exists() else None
    horas_por_anio = (previo["fecha_hora_utc"].dt.year.value_counts() if previo is not None
                      else pd.Series(dtype=int))
    faltantes = [a for a in range(ini.year, fin.year + 1) if horas_por_anio.get(a, 0) < 24 * 300]
    partes = []
    for anio in faltantes:
        desde = max(date(anio, 1, 1), ini.date())
        hasta = min(date(anio, 12, 31), fin.date())
        try:
            partes.append(clima.descargar(desde, hasta))
            print(f"Clima {anio} OK")
        except Exception as e:
            print(f"Clima {anio} omitido: {e}")
    if partes:
        nuevo = pd.concat(partes + ([previo] if previo is not None else []))
        nuevo.drop_duplicates("fecha_hora_utc").sort_values("fecha_hora_utc").to_parquet(
            p["clima"], index=False)


def paso_validar() -> bool:
    p, cfg = _rutas(), settings()["validacion"]
    if not (p["api"].exists() and p["xls"].exists()):
        print("Validación omitida: falta una de las dos fuentes.")
        return True
    api, xls = pd.read_parquet(p["api"]), pd.read_parquet(p["xls"])
    # solo días ya consolidados (la demanda real se corrige días después)
    limite = pd.Timestamp.now(tz="UTC").normalize() - pd.Timedelta(days=cfg["dias_rezago"])
    api, xls = api[api["fecha_hora_utc"] < limite], xls[xls["fecha_hora_utc"] < limite]
    # comparar solo el rango que cubren ambas
    ini = max(api["fecha_hora_utc"].min(), xls["fecha_hora_utc"].min())
    fin = min(api["fecha_hora_utc"].max(), xls["fecha_hora_utc"].max())
    api = api[api["fecha_hora_utc"].between(ini, fin)]
    xls = xls[xls["fecha_hora_utc"].between(ini, fin)]

    res = validar.comparar(api, xls, cfg["tolerancia_pct"])
    hoy = date.today().isoformat()
    res.detalle.to_csv(p["validacion"] / f"validacion_{hoy}.csv", index=False)
    (p["validacion"] / "ultimo_resumen.json").write_text(json.dumps(res.resumen, indent=2))
    print(json.dumps(res.resumen, indent=2))
    if res.resumen["desfase_sospechoso_h"]:
        print(f"Ojo: las series calzan mejor corridas {res.resumen['desfase_sospechoso_h']} h. "
              "Revisa convencion_hora en settings.yaml.")
    return res.resumen["alertas"] <= cfg["max_alertas"]


def _serie_demanda() -> pd.DataFrame:
    """Prioridad: API > XLS manual > histórico CEN (rellena lo que falte)."""
    p = _rutas()
    partes = [pd.read_parquet(p[k]) for k in ("api", "xls", "cen") if p[k].exists()]
    if not partes:
        raise SystemExit("No hay datos de demanda. Corre 'ingesta' o 'demo' primero.")
    return pd.concat(partes).drop_duplicates("fecha_hora_utc", keep="first")


def _clima():
    p = _rutas()
    return pd.read_parquet(p["clima"]) if p["clima"].exists() else None


def entrenar(dias_test: int | None = None) -> dict:
    cfg = settings()
    c = settings()["clima"]
    df = features.construir(_serie_demanda(), _clima(), c["base_calefaccion_c"], c["base_enfriamiento_c"])
    m, cols, metricas, test = modelo.entrenar(df, cfg["modelo"]["lightgbm"],
                                               dias_test or cfg["modelo"]["dias_test"])
    modelo.guardar(m, cols, metricas, _rutas()["modelos"])
    test.to_parquet(_rutas()["test"], index=False)
    print(json.dumps(metricas, indent=2))
    return metricas


def pronosticar() -> pd.DataFrame:
    c = settings()["clima"]
    df = features.construir(_serie_demanda(), _clima(), c["base_calefaccion_c"], c["base_enfriamiento_c"])
    pron = modelo.pronosticar(df, _rutas()["modelos"], settings()["modelo"]["horizonte_h"])
    pron.to_parquet(_rutas()["pronostico"], index=False)
    print(pron.head(24).to_string(index=False))
    return pron


def reporte() -> dict:
    import joblib

    from demanda import reporte as rep

    p = _rutas()
    fuente = ("Histórico oficial de generación bruta horaria, Coordinador Eléctrico Nacional"
              if p["cen"].exists() else "datos sintéticos de demostración (no reales)")
    demanda = _serie_demanda()
    test = pd.read_parquet(p["test"]) if p["test"].exists() else None
    met_path = p["modelos"] / "metricas.json"
    metricas = json.loads(met_path.read_text()) if met_path.exists() else None
    mod_path = p["modelos"] / "modelo.joblib"
    paquete = joblib.load(mod_path) if mod_path.exists() else None
    info = rep.generar(demanda, _clima(), test, metricas, paquete, fuente)
    print(f"Reporte generado: reports/RESULTADOS.md ({len(list(rep.FIG.glob('*.png')))} gráficos)")
    return info


def demo(dias: int = 400, semilla: int = 7) -> None:
    """Genera demanda y clima sintéticos realistas para probar todo sin keys.

    Las dos fuentes difieren levemente y se inyectan 3 errores para que la
    validación tenga algo que detectar.
    """
    rng = np.random.default_rng(semilla)
    fin = pd.Timestamp.now(tz="UTC").floor("h") - pd.Timedelta(days=1)
    t = pd.date_range(fin - pd.Timedelta(days=dias), fin, freq="h")
    local = t.tz_convert("America/Santiago")
    h, dow, doy = local.hour, local.dayofweek, local.dayofyear

    temp = 13 + 7 * np.cos(2 * np.pi * (doy - 15) / 365) + 5 * np.sin(2 * np.pi * (h - 9) / 24)
    temp = temp + rng.normal(0, 1.5, len(t))
    perfil = 8600 + 1300 * np.sin(2 * np.pi * (h - 7) / 24) + 500 * np.sin(2 * np.pi * (h - 17) / 12)
    finde = np.where(dow >= 5, -700, 0)
    calef = 45 * np.clip(18 - temp, 0, None)
    tendencia = np.linspace(0, 250, len(t))
    demanda = perfil + finde + calef + tendencia + rng.normal(0, 90, len(t))

    api = pd.DataFrame({"fecha_hora_utc": t, "demanda_mwh": demanda})
    xls = api.copy()
    xls["demanda_mwh"] = xls["demanda_mwh"] * (1 + rng.normal(0, 0.0005, len(t)))
    idx = rng.choice(len(xls) - 200, 3, replace=False)
    xls.loc[idx, "demanda_mwh"] *= 1.04  # errores inyectados

    p = _rutas()
    for k in ("api", "xls", "cen", "clima"):
        p[k].unlink(missing_ok=True)
    normalizar.guardar(normalizar.esquema_comun(api, "api"), p["api"])
    normalizar.guardar(normalizar.esquema_comun(xls, "xls"), p["xls"])
    pd.DataFrame({"fecha_hora_utc": t, "temp_c": temp}).to_parquet(p["clima"], index=False)
    print(f"Datos sintéticos: {len(t)} horas ({dias} días).")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paso", choices=["demo", "historico", "ingesta", "validar", "entrenar",
                                     "pronosticar", "reporte", "diario"])
    ap.add_argument("--dias", type=int, default=7, help="días hacia atrás para la ingesta")
    ap.add_argument("--forzar", action="store_true", help="vuelve a descargar el histórico")
    a = ap.parse_args(argv)

    if a.paso == "demo":
        demo()
        paso_validar()  # en demo las alertas son esperadas (errores inyectados)
        entrenar(dias_test=60)
        pronosticar()
        reporte()
        return 0
    if a.paso == "ingesta":
        ingesta(a.dias)
    elif a.paso == "validar":
        return 0 if paso_validar() else 1
    elif a.paso == "entrenar":
        entrenar()
    elif a.paso == "pronosticar":
        pronosticar()
    elif a.paso == "reporte":
        reporte()
    elif a.paso == "historico":
        historico(forzar=a.forzar)
    elif a.paso == "diario":
        try:
            historico()  # usa la copia local si tiene menos de 30 días
        except Exception as e:
            print(f"Histórico CEN omitido: {e}")
        ingesta(a.dias)
        p = _rutas()
        if not any(p[k].exists() for k in ("api", "xls", "cen")):
            print("Aún no hay datos de demanda (falta SIP_USER_KEY o archivos XLS). "
                  "Nada que entrenar; termino sin error.")
            return 0
        ok = paso_validar()
        entrenar()
        pronosticar()
        reporte()
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
