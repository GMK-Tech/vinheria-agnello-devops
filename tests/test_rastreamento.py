"""O ms-rastreamento só pode aceitar chamadas com JWT de serviço válido."""
from datetime import datetime, timedelta, timezone

import jwt

SEGREDO = "segredo-de-servico-para-testes-0123456789"


def token(**sobrescrever):
    agora = datetime.now(timezone.utc)
    claims = {"sub": "ms-pedidos", "aud": "ms-rastreamento", "scope": "lotes:read reservas:write",
              "iat": agora, "exp": agora + timedelta(seconds=60)}
    claims.update(sobrescrever)
    return jwt.encode(claims, SEGREDO, algorithm="HS256")


def reservar(cliente, tk, quantidade=10, lote="LT-2026-0147"):
    cab = {"Authorization": f"Bearer {tk}"} if tk else {}
    return cliente.post(f"/lotes/{lote}/reservas", json={"quantidade": quantidade}, headers=cab)


def test_health(rastreamento):
    assert rastreamento.app.test_client().get("/health").status_code == 200


def test_sem_token_401(rastreamento):
    assert reservar(rastreamento.app.test_client(), None).status_code == 401


def test_assinatura_errada_401(rastreamento):
    falso = jwt.encode({"sub": "invasor", "aud": "ms-rastreamento", "scope": "reservas:write",
                        "iat": datetime.now(timezone.utc),
                        "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
                       "outro-segredo-qualquer-0123456789abcdef", algorithm="HS256")
    assert reservar(rastreamento.app.test_client(), falso).status_code == 401


def test_token_expirado_401(rastreamento):
    vencido = token(exp=datetime.now(timezone.utc) - timedelta(seconds=1))
    resp = reservar(rastreamento.app.test_client(), vencido)
    assert resp.status_code == 401 and "expirado" in resp.get_json()["erro"]


def test_token_para_outro_servico_401(rastreamento):
    assert reservar(rastreamento.app.test_client(), token(aud="ms-qualidade")).status_code == 401


def test_alg_none_401(rastreamento):
    sem_assinatura = jwt.encode({"sub": "invasor", "aud": "ms-rastreamento", "scope": "reservas:write"},
                                None, algorithm="none")
    assert reservar(rastreamento.app.test_client(), sem_assinatura).status_code == 401


def test_sem_escopo_403(rastreamento):
    assert reservar(rastreamento.app.test_client(), token(scope="lotes:read")).status_code == 403


def test_reserva_ok_e_baixa_estoque(rastreamento):
    cliente = rastreamento.app.test_client()
    resp = reservar(cliente, token(), quantidade=100)
    assert resp.status_code == 201
    assert resp.get_json()["disponivel_restante"] == 2900


def test_estoque_insuficiente_409(rastreamento):
    assert reservar(rastreamento.app.test_client(), token(), quantidade=999, lote="LT-2025-0098").status_code == 409


def test_lote_inexistente_404(rastreamento):
    assert reservar(rastreamento.app.test_client(), token(), lote="LT-0000").status_code == 404


def test_compensacao_devolve_garrafas(rastreamento):
    cliente = rastreamento.app.test_client()
    rid = reservar(cliente, token(), quantidade=20, lote="LT-2025-0098").get_json()["reserva_id"]
    resp = cliente.delete(f"/lotes/LT-2025-0098/reservas/{rid}", headers={"Authorization": f"Bearer {token()}"})
    assert resp.status_code == 200 and resp.get_json()["disponivel"] == 120
