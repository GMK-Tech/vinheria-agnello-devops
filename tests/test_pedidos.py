"""Login, autorização por papel e chamada ao ms-rastreamento com token DE SERVIÇO."""
import jwt
import requests


class RespostaFalsa:
    def __init__(self, status, corpo):
        self.status_code, self._corpo = status, corpo

    def json(self):
        return self._corpo


def login(cliente, usuario="comercial", senha="senha-de-teste"):
    return cliente.post("/login", json={"usuario": usuario, "senha": senha})


def cab(cliente, usuario="comercial"):
    return {"Authorization": "Bearer " + login(cliente, usuario).get_json()["access_token"]}


def test_login_senha_errada_401(pedidos):
    assert login(pedidos.app.test_client(), senha="errada").status_code == 401


def test_login_ok(pedidos):
    resp = login(pedidos.app.test_client())
    assert resp.status_code == 200 and resp.get_json()["token_type"] == "Bearer"


def test_pedido_sem_token_401(pedidos):
    assert pedidos.app.test_client().post("/pedidos", json={}).status_code == 401


def test_auditor_nao_cria_pedido_403(pedidos):
    cliente = pedidos.app.test_client()
    resp = cliente.post("/pedidos", json={"lote": "LT-2026-0147", "quantidade": 1}, headers=cab(cliente, "auditor"))
    assert resp.status_code == 403


def test_pedido_confirmado_usa_token_de_servico(pedidos, monkeypatch):
    enviado = {}

    def falso(metodo, url, headers, **kw):
        enviado.update(url=url, auth=headers["Authorization"])
        return RespostaFalsa(201, {"reserva_id": "RES-TESTE"})

    monkeypatch.setattr(pedidos.requests, "request", falso)
    cliente = pedidos.app.test_client()
    cabecalho_usuario = cab(cliente)
    resp = cliente.post("/pedidos", json={"lote": "LT-2026-0147", "quantidade": 6}, headers=cabecalho_usuario)

    assert resp.status_code == 201 and resp.get_json()["status"] == "CONFIRMADO"
    assert "ms-rastreamento.vinheria.local" in enviado["url"]           # usa o nome DNS
    assert enviado["auth"] != cabecalho_usuario["Authorization"]        # token do usuário NÃO é repassado
    claims = jwt.decode(enviado["auth"][7:], options={"verify_signature": False})
    assert claims["sub"] == "ms-pedidos" and claims["aud"] == "ms-rastreamento"


def test_rastreamento_fora_do_ar_503(pedidos, monkeypatch):
    def cai(*a, **kw):
        raise requests.ConnectionError("sem rota")

    monkeypatch.setattr(pedidos.requests, "request", cai)
    cliente = pedidos.app.test_client()
    resp = cliente.post("/pedidos", json={"lote": "LT-2026-0147", "quantidade": 1}, headers=cab(cliente))
    assert resp.status_code == 503 and resp.get_json()["status"] == "REJEITADO"


def test_falha_pagamento_compensa_reserva(pedidos, monkeypatch):
    chamadas = []

    def falso(metodo, url, **kw):
        chamadas.append(metodo)
        return RespostaFalsa(201, {"reserva_id": "RES-X"}) if metodo == "post" else RespostaFalsa(200, {})

    monkeypatch.setattr(pedidos.requests, "request", falso)
    cliente = pedidos.app.test_client()
    resp = cliente.post("/pedidos", json={"lote": "LT-2026-0147", "quantidade": 3,
                                          "simular_falha_pagamento": True}, headers=cab(cliente))
    assert resp.status_code == 402 and resp.get_json()["status"] == "CANCELADO"
    assert chamadas == ["post", "delete"]
