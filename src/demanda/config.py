"""Carga de configuración (settings.yaml) y secretos (.env / variables de entorno)."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parents[2]


def _cargar_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(RAIZ / ".env")


@lru_cache
def settings() -> dict:
    _cargar_env()
    with open(RAIZ / "config" / "settings.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    for clave, rel in cfg["rutas"].items():
        ruta = RAIZ / rel
        ruta.mkdir(parents=True, exist_ok=True)
        cfg["rutas"][clave] = ruta
    return cfg


def secreto(nombre: str, obligatorio: bool = True) -> str | None:
    _cargar_env()
    valor = os.getenv(nombre)
    if obligatorio and not valor:
        raise RuntimeError(
            f"Falta la variable {nombre}. Defínela en .env (local) "
            "o como Secret en GitHub Actions."
        )
    return valor
