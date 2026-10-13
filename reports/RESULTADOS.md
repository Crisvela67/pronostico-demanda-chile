# Resultados

> Generado automáticamente por `python -m demanda.pipeline reporte`. Fuente: Histórico oficial de generación bruta horaria, Coordinador Eléctrico Nacional.

## Resumen

| Indicador | Valor |
|---|---|
| Período analizado | 2018-01-01 a 2025-12-31 (70.123 horas) |
| Máximo horario | 13.093 MWh/h (2025-12-29 05:00) |
| Hora punta promedio | 12:00 · valle 04:00 |
| Fin de semana vs día hábil | -6,9 % |
| Peor semana de 2020 (pandemia) | -5,7 % vs 2018-2019 |
| Temperatura de menor consumo | ≈ 16 °C |
| **Error del modelo (MAPE)** | **9,30 %** |
| Baseline semana pasada | 8,88 % |
| Baseline ayer | 9,84 % |
| Error medio absoluto | 417 MWh/h |

## Mapa de calor anual

Cada fila es un año y cada columna un día. Lo oscuro es más consumo.

![Mapa de calor anual](figures/01_huella_calendario.png)

## Hora × día de la semana

El patrón semanal: valle de madrugada, meseta laboral y punta nocturna.

![Hora × día de la semana](figures/02_hora_vs_dia_semana.png)

## Hora × mes

Cómo se mueve la punta durante el año.

![Hora × mes](figures/03_hora_vs_mes.png)

## Tendencia y crecimiento



![Tendencia y crecimiento](figures/04_tendencia_mensual.png)

## Temperatura y consumo

El consumo sube cuando hace frío (calefacción) y cuando hace calor (refrigeración).

![Temperatura y consumo](figures/05_temperatura_vs_demanda.png)

## El efecto de la pandemia



![El efecto de la pandemia](figures/06_covid_2020.png)

## Desempeño del modelo

Pronóstico a 24 horas evaluado sobre datos que el modelo no vio.

![Desempeño del modelo](figures/00_metricas.png)

## Pronóstico vs realidad



![Pronóstico vs realidad](figures/07_pronostico_vs_real.png)

## Error por hora del día



![Error por hora del día](figures/08_error_por_hora.png)

## Sesgo del modelo por hora y mes



![Sesgo del modelo por hora y mes](figures/09_sesgo_hora_mes.png)

## Qué variables importan



![Qué variables importan](figures/10_importancia_variables.png)
