"""
ms-pedidos — Gestão de Pedidos (Vinheria Agnello)

- Usuários fazem login e recebem um JWT de USUÁRIO.
- Para confirmar um pedido, o ms-pedidos reserva garrafas no ms-rastreamento
  usando um JWT de SERVIÇO próprio. O token do usuário NUNCA é repassado.
- Saga simplificada: se o pagamento falhar, a reserva é desfeita (compensação).
"""
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from functools import wraps

import jwt
import requests
from flask import Flask, g, jsonify, request
from werkzeug.security import check_password_hash, generate_password_hash

# ------------------------------------------------------------------ config
NOME_SERVICO = "ms-pedidos"
SEGREDO_USUARIO = os.environ.get("USER_JWT_SECRET", "")      # assina tokens de usuário
SEGREDO_SERVICO = os.environ.get("SERVICE_JWT_SECRET", "")   # assina tokens entre serviços
PORTA = int(os.environ.get("PORTA", "5001"))
TLS = os.environ.get("TLS", "off").lower() == "on"
CERT_DIR = os.environ.get("CERT_DIR", "/certs")

# Endereço do outro serviço: um NOME, resolvido pelo DNS (dnsmasq).
RASTREAMENTO_HOST = os.environ.get("RASTREAMENTO_HOST", "ms-rastreamento.vinheria.local")
RASTREAMENTO_PORTA = int(os.environ.get("RASTREAMENTO_PORTA", "5002"))
ESQUEMA = "https" if TLS else "http"
VERIFICAR_CERT = f"{CERT_DIR}/ca.crt" if TLS else True

logging.basicConfig(level=logging.INFO, format="%(asctime)s [ms-pedidos] %(message)s")
log = logging.getLogger(__name__)
app = Flask(__name__)

# Usuários de demonstração. Só o HASH da senha fica em memória.
SENHA_DEMO = os.environ.get("SENHA_DEMO", "")
USUARIOS = {
    "comercial": {"hash": generate_password_hash(SENHA_DEMO), "papel": "comercial"},
    "auditor":   {"hash": generate_password_hash(SENHA_DEMO), "papel": "auditor"},
}
PEDIDOS = {}


def agora():
    return datetime.now(timezone.utc)


# ------------------------------------------------------------ segurança
def exige_usuario(*papeis):
    """Valida o JWT de usuário e o papel (autorização)."""
    def decorador(funcao):
        @wraps(funcao)
        def interno(*args, **kwargs):
            cabecalho = request.headers.get("Authorization", "")
            if not cabecalho.startswith("Bearer "):
                return jsonify(erro="token ausente"), 401
            try:
                claims = jwt.decode(cabecalho[len("Bearer "):], SEGREDO_USUARIO,
                                    algorithms=["HS256"], audience=NOME_SERVICO)
            except jwt.ExpiredSignatureError:
                return jsonify(erro="token expirado"), 401
            except jwt.InvalidTokenError as exc:
                return jsonify(erro=f"token inválido: {exc}"), 401
            if claims.get("papel") not in papeis:
                return jsonify(erro="sem permissão para esta operação"), 403
            g.usuario = claims["sub"]
            return funcao(*args, **kwargs)
        return interno
    return decorador


def token_de_servico():
    """JWT curto (60 s) que identifica o ms-pedidos perante o ms-rastreamento."""
    momento = agora()
    return jwt.encode({
        "iss": NOME_SERVICO,
        "sub": NOME_SERVICO,
        "aud": "ms-rastreamento",
        "scope": "lotes:read reservas:write",
        "iat": momento,
        "exp": momento + timedelta(seconds=60),
        "jti": uuid.uuid4().hex,
    }, SEGREDO_SERVICO, algorithm="HS256")


def chamar_rastreamento(metodo, caminho, **kwargs):
    url = f"{ESQUEMA}://{RASTREAMENTO_HOST}:{RASTREAMENTO_PORTA}{caminho}"
    log.info("-> %s %s", metodo.upper(), url)
    return requests.request(
        metodo, url,
        headers={"Authorization": f"Bearer {token_de_servico()}"},
        timeout=5,
        verify=VERIFICAR_CERT,
        **kwargs,
    )


# ------------------------------------------------------------ endpoints
@app.get("/health")
def health():
    return jsonify(servico=NOME_SERVICO, status="ok", tls=TLS)


@app.post("/login")
def login():
    dados = request.get_json(silent=True) or {}
    usuario = USUARIOS.get(dados.get("usuario", ""))
    if not SENHA_DEMO or usuario is None or not check_password_hash(usuario["hash"], dados.get("senha", "")):
        return jsonify(erro="usuário ou senha inválidos"), 401

    momento = agora()
    token = jwt.encode({
        "iss": NOME_SERVICO,
        "sub": dados["usuario"],
        "aud": NOME_SERVICO,
        "papel": usuario["papel"],
        "iat": momento,
        "exp": momento + timedelta(minutes=15),
    }, SEGREDO_USUARIO, algorithm="HS256")
    return jsonify(access_token=token, token_type="Bearer", expira_em_segundos=900)


@app.post("/pedidos")
@exige_usuario("comercial")
def criar_pedido():
    dados = request.get_json(silent=True) or {}
    lote, quantidade = dados.get("lote"), dados.get("quantidade")
    if not lote or not isinstance(quantidade, int) or quantidade <= 0:
        return jsonify(erro="informe 'lote' e 'quantidade' (inteiro positivo)"), 400

    pedido_id = "PED-" + uuid.uuid4().hex[:8].upper()
    pedido = {"id": pedido_id, "lote": lote, "quantidade": quantidade,
              "criado_por": g.usuario, "status": "PENDENTE"}
    PEDIDOS[pedido_id] = pedido

    # Passo 1 da Saga: reservar garrafas no ms-rastreamento (REST síncrono)
    try:
        resp = chamar_rastreamento("post", f"/lotes/{lote}/reservas",
                                   json={"pedido_id": pedido_id, "quantidade": quantidade})
    except requests.RequestException as exc:
        pedido.update(status="REJEITADO", motivo="ms-rastreamento indisponível")
        log.warning("falha ao chamar ms-rastreamento: %s", exc)
        return jsonify(pedido), 503

    if resp.status_code != 201:
        pedido.update(status="REJEITADO", motivo=resp.json().get("erro", "reserva recusada"))
        return jsonify(pedido), 409 if resp.status_code == 409 else 422

    pedido["reserva_id"] = resp.json()["reserva_id"]

    # Passo 2 da Saga: pagamento (simulado). Falhou? Compensa a reserva.
    if dados.get("simular_falha_pagamento"):
        chamar_rastreamento("delete", f"/lotes/{lote}/reservas/{pedido['reserva_id']}")
        pedido.update(status="CANCELADO", motivo="pagamento recusado — reserva desfeita")
        return jsonify(pedido), 402

    pedido["status"] = "CONFIRMADO"
    log.info("pedido %s CONFIRMADO por %s", pedido_id, g.usuario)
    return jsonify(pedido), 201


@app.get("/pedidos/<pedido_id>")
@exige_usuario("comercial", "auditor")
def consultar_pedido(pedido_id):
    pedido = PEDIDOS.get(pedido_id)
    return (jsonify(pedido), 200) if pedido else (jsonify(erro="pedido não encontrado"), 404)


# ---------------------------------------------------------------- start
if __name__ == "__main__":
    if not (SEGREDO_USUARIO and SEGREDO_SERVICO and SENHA_DEMO):
        raise SystemExit("Defina USER_JWT_SECRET, SERVICE_JWT_SECRET e SENHA_DEMO")
    ssl = (f"{CERT_DIR}/{NOME_SERVICO}.crt", f"{CERT_DIR}/{NOME_SERVICO}.key") if TLS else None
    log.info("subindo na porta %s | TLS=%s | rastreamento em %s://%s:%s",
             PORTA, "ligado" if TLS else "DESLIGADO", ESQUEMA, RASTREAMENTO_HOST, RASTREAMENTO_PORTA)
    # Dentro do container o serviço precisa escutar em todas as interfaces.
    app.run(host="0.0.0.0", port=PORTA, ssl_context=ssl)  # nosec B104
