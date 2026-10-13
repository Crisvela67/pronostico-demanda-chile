# Pronóstico de demanda eléctrica — Chile

Pronóstico horario (24 h) de la demanda del **Sistema Eléctrico Nacional**, con datos públicos del Coordinador Eléctrico Nacional, clima y calendario chileno. El pipeline se actualiza solo todos los días con GitHub Actions e incluye una **validación cruzada entre dos fuentes** (API vs archivos descargados) antes de entrenar.

> Estado: funciona con el **histórico oficial de generación horaria del Coordinador (2018-2025)**, público y sin key. La API SIP queda lista para cuando haya `user_key`.

## Datos

| Fuente | Qué aporta | Acceso |
|---|---|---|
| [Histórico de generación horaria CEN](https://www.coordinador.cl/reportes-y-estadisticas/) | Generación bruta horaria del SEN desde 2000 (MWh/h) | XLSX público, se descarga solo |
| [Open-Meteo](https://open-meteo.com/en/docs/historical-weather-api) | Temperatura horaria de Santiago, Antofagasta y Concepción | API sin key |
| `holidays` | Feriados de Chile | Librería, sin red |
| API SIP del Coordinador | Demanda real horaria | Requiere `user_key` (pendiente) |

**Generación como proxy de demanda.** El archivo oficial público trae generación bruta, no demanda. La diferencia son pérdidas de transmisión y consumos propios (pocos puntos porcentuales) con el mismo patrón horario, por lo que sirve para modelar la forma y los niveles de la demanda. La demanda real oficial se publica mensualmente (alrededor del día 20 del mes siguiente) en el sitio del Coordinador.

**Cambio de horario.** El archivo marca el día del cambio a invierno con una hora 25, en 2025 escribe la hora 24 como 0 y no siempre es consistente con el día de 23 horas. Por eso el lector no confía en la etiqueta de hora: usa el orden de las filas desde la medianoche local de cada día y genera un reporte de los días que no traen las horas esperadas (`data/validation/calidad_cen_historico.csv`).

**Limitación actual:** el histórico llega hasta diciembre de 2025; 2026 se agregará con la demanda real mensual o con la API.

## Arquitectura

```
Fuentes (API SIP · XLS · clima · calendario)
        │
        ▼
Ingesta y normalización ── todo a UTC, MWh, esquema común
        │
        ▼
Validación cruzada ── API vs XLS hora a hora, detecta desfases
        │
        ▼
Almacenamiento (raw → processed, Parquet)
        │
        ▼
Features (rezagos 24h/48h/168h, grados-día, feriados) ──► LightGBM vs baseline
        │
        ▼
Salidas: pronóstico 24 h + dashboard Streamlit
```

## Inicio rápido

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m demanda.pipeline historico   # descarga el histórico oficial 2018-2025 y el clima
python -m demanda.pipeline entrenar
streamlit run app/dashboard.py

# sin internet o para probar rápido: datos sintéticos
python -m demanda.pipeline demo
```

Con Docker:

```bash
docker build -t demanda-chile .
docker run -p 8501:8501 demanda-chile   # abrir http://localhost:8501
```

## Con datos reales

1. Regístrate en el portal de API del Coordinador y copia tu `user_key`.
2. `cp .env.example .env` y pégala en `SIP_USER_KEY`.
3. Revisa en `config/settings.yaml` los nombres de parámetros y campos de la API (`api_sip`) contra la documentación vigente.
4. Descarga archivos de demanda real del sitio del Coordinador a `data/raw/xls/` y ajusta la sección `xls` (columna de fecha, formato ancho/largo, convención de hora).
5. `python -m demanda.pipeline diario --dias 30`

En GitHub, agrega `SIP_USER_KEY` en **Settings → Secrets and variables → Actions**.

## Comandos

| Comando | Qué hace |
|---|---|
| `historico [--forzar]` | Descarga y procesa el histórico oficial de generación horaria + clima |
| `demo` | Datos sintéticos con 3 errores inyectados, y el pipeline completo |
| `ingesta --dias N` | Descarga API, lee XLS y clima de los últimos N días |
| `validar` | Compara API vs XLS; falla si hay más alertas que `max_alertas` |
| `entrenar` | LightGBM, métricas contra baseline, guarda el modelo |
| `pronosticar` | Próximas 24 h |
| `diario` | Todo en orden (lo que corre GitHub Actions) |

## Validación cruzada

Para cada hora cubierta por ambas fuentes se calcula la diferencia absoluta y porcentual:

- **ok**: diferencia ≤ `tolerancia_pct` (0,5 % por defecto)
- **alerta**: diferencia mayor
- **solo_api / solo_xls**: la hora falta en una fuente

Además se detecta si las series calzan mejor **corridas N horas**, lo que casi siempre indica un problema de convención (hora 1–24 vs 0–23) o de zona horaria, no un error real. Solo se comparan días con más de `dias_rezago` de antigüedad, porque la demanda real se corrige después de publicada.

## Resultados de prueba (datos sintéticos, no reales)

| Modelo | MAPE |
|---|---|
| Baseline: mismo día de la semana pasada | 1,64 % |
| Baseline: ayer a la misma hora | 3,42 % |
| **LightGBM** | **1,42 %** |

Estos números solo prueban que el pipeline funciona. Se reemplazarán por los resultados sobre el histórico oficial.

## Decisiones de diseño

- **UTC interno.** Chile cambia de horario dos veces al año: un día tiene 23 horas y otro 25. Se guarda el inicio de cada intervalo en UTC y se convierte a hora local solo para mostrar.
- **Sin fuga de datos.** Con horizonte de 24 h solo se usan rezagos de 24 h o más.
- **raw inmutable.** Lo descargado nunca se edita; la limpieza vive en `processed`.
- **Clima sin key desde el día uno.** Se usa el histórico de Open-Meteo, ponderando Santiago, Antofagasta y Concepción; se puede reemplazar por INIA o la DMC.

## Estructura

```
config/settings.yaml          parámetros, rutas, tolerancias
src/demanda/fuentes/          extractores: api_sip, xls_coordinador, clima, calendario
src/demanda/normalizar.py     esquema común, UTC, coma decimal
src/demanda/validar.py        comparación API vs XLS
src/demanda/features.py       variables del modelo
src/demanda/modelo.py         entrenamiento, métricas, pronóstico
src/demanda/pipeline.py       orquestador (CLI)
app/dashboard.py              Streamlit
tests/                        pruebas de normalización y validación
.github/workflows/            pipeline diario
```

## Próximos pasos

- [ ] Conectar la API SIP con `user_key` y verificar campos
- [x] Lector del histórico oficial de generación horaria
- [ ] Correr el entrenamiento sobre 2018-2025 y publicar resultados
- [ ] Agregar 2026 con la demanda real mensual del Coordinador
- [ ] Comparar contra la previsión oficial de demanda del Coordinador
- [ ] Usar pronóstico meteorológico en vez de la temperatura de ayer
- [ ] SHAP para explicar qué variables mueven el pronóstico

## Autor

Cristopher Velásquez — [GitHub](https://github.com/Crisvela67)
