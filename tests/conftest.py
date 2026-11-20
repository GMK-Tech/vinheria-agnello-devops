"""Carrega os dois app.py com nomes distintos e variáveis de ambiente de teste."""
import importlib.util
import os
import pathlib

import pytest

os.environ.update({
    "SERVICE_JWT_SECRET": "segredo-de-servico-para-testes-0123456789",
    "USER_JWT_SECRET": "segredo-de-usuario-para-testes-0123456789",
    "SENHA_DEMO": "senha-de-teste",
    "TLS": "off",
})
RAIZ = pathlib.Path(__file__).resolve().parents[1] / "services"


def _carregar(nome):
    spec = importlib.util.spec_from_file_location(nome.replace("-", "_"), RAIZ / nome / "app.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


@pytest.fixture
def rastreamento():
    return _carregar("ms-rastreamento")


@pytest.fixture
def pedidos():
    return _carregar("ms-pedidos")
