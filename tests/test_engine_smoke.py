"""Smoke del motor: solo si MODEL=1 y hay pesos; si no, skip honesto."""
import os
import pytest


def test_engine_smoke():
    if os.environ.get("MODEL") != "1":
        pytest.skip("Sin MODEL=1: no se ejecuta inferencia real (honesto, no simulado)")
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine"))
    import kraken_adapter as ka
    if not ka.model_ready():
        pytest.skip("Modelo no descargado en MODEL_DIR: ejecutar ensure_model() primero")
    res = ka.smoke_test()
    assert res.get("ok") is True
