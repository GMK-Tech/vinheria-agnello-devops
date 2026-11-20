"""
ms-rastreamento — Rastreamento de Vinhos (Vinheria Agnello)

Mantém os lotes de vinho e as reservas de garrafas feitas pelos pedidos.
Só aceita chamadas de OUTROS MICROSSERVIÇOS, autenticadas com um JWT de
serviço enviado no cabeçalho:  Authorization: Bearer <token>
"""
import logging
import os
import uuid
from datetime import datetime, timezone
from functools import wraps

import jwt
from flask import Flask, g, jsonify, request

# ------------------------------------------------------------------ config
NOME_SERVICO = "ms-rastreamento"
SEGREDO_SERVICO = os.environ.get("SERVICE_JWT_SECRET", "")   # vem do .env, nunca do código
PORTA = int(os.environ.get("PORTA", "5002"))
TLS = os.environ.get("TLS", "off").lower() == "on"
CERT_DIR = os.environ.get("CERT_DIR", "/certs")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [ms-rastreamento] %(message)s")
log = logging.getLogger(__name__)
app = Flask(__name__)

# "Banco de dados" em memória: suficiente para a simulação.
LOTES = {
    "LT-2026-0147": {"vinho": "Agnello Reserva Tinto 2024", "disponivel": 3000},
    "LT-2025-0098": {"vinho": "Agnello Chardonnay 2025", "disponivel": 120},
}
RESERVAS = {}


# ------------------------------------------------------------ segurança
def exige_token_servico(escopo):
    """Valida o JWT de serviço: assinatura, expiração, destinatário e escopo."""
    def decorador(funcao):
        @wraps(funcao)
        def interno(*args, **kwargs):
            cabecalho = request.headers.get("Authorization", "")
            if not cabecalho.startswith("Bearer "):
                return jsonify(erro="token ausente"), 401
            try:
                claims = jwt.decode(
                    cabecalho[len("Bearer "):],
                    SEGREDO_SERVICO,
                    algorithms=["HS256"],          # fixo: bloqueia o ataque "alg: none"
                    audience=NOME_SERVICO,         # token emitido para OUTRO serviço é recusado
                    options={"require": ["exp", "iat", "sub", "aud"]},
                )
            except jwt.ExpiredSignatureError:
                return jsonify(erro="token expirado"), 401
            except jwt.InvalidTokenError as exc:
                return jsonify(erro=f"token inválido: {exc}"), 401

            if escopo not in claims.get("scope", "").split():
                return jsonify(erro=f"escopo '{escopo}' necessário"), 403

            g.chamador = claims["sub"]
            return funcao(*args, **kwargs)
        return interno
    return decorador


# ------------------------------------------------------------ endpoints
@app.get("/health")
def health():
    return jsonify(servico=NOME_SERVICO, status="ok", tls=TLS)


@app.get("/lotes/<codigo>")
@exige_token_servico("lotes:read")
def consultar_lote(codigo):
    lote = LOTES.get(codigo)
    if lote is None:
        return jsonify(erro="lote não encontrado"), 404
    return jsonify(codigo=codigo, **lote)


@app.post("/lotes/<codigo>/reservas")
@exige_token_servico("reservas:write")
def reservar(codigo):
    lote = LOTES.get(codigo)
    if lote is None:
        return jsonify(erro="lote não encontrado"), 404

    dados = request.get_json(silent=True) or {}
    quantidade = dados.get("quantidade")
    if not isinstance(quantidade, int) or quantidade <= 0:
        return jsonify(erro="quantidade deve ser um inteiro positivo"), 400
    if quantidade > lote["disponivel"]:
        return jsonify(erro="estoque insuficiente no lote", disponivel=lote["disponivel"]), 409

    lote["disponivel"] -= quantidade
    reserva_id = "RES-" + uuid.uuid4().hex[:8].upper()
    RESERVAS[reserva_id] = {
        "lote": codigo,
        "quantidade": quantidade,
        "pedido_id": dados.get("pedido_id"),
        "criada_em": datetime.now(timezone.utc).isoformat(),
    }
    log.info("reserva %s: %s garrafas do lote %s (chamador=%s)", reserva_id, quantidade, codigo, g.chamador)
    return jsonify(reserva_id=reserva_id, lote=codigo, quantidade=quantidade,
                   disponivel_restante=lote["disponivel"]), 201


@app.delete("/lotes/<codigo>/reservas/<reserva_id>")
@exige_token_servico("reservas:write")
def liberar_reserva(codigo, reserva_id):
    """Compensação da Saga: devolve as garrafas ao lote."""
    reserva = RESERVAS.pop(reserva_id, None)
    if reserva is None or reserva["lote"] != codigo:
        return jsonify(erro="reserva não encontrada"), 404
    LOTES[codigo]["disponivel"] += reserva["quantidade"]
    log.info("reserva %s liberada (compensação) por %s", reserva_id, g.chamador)
    return jsonify(reserva_id=reserva_id, status="liberada",
                   disponivel=LOTES[codigo]["disponivel"])


# ---------------------------------------------------------------- start
if __name__ == "__main__":
    if not SEGREDO_SERVICO:
        raise SystemExit("Defina a variável SERVICE_JWT_SECRET")
    ssl = (f"{CERT_DIR}/{NOME_SERVICO}.crt", f"{CERT_DIR}/{NOME_SERVICO}.key") if TLS else None
    log.info("subindo na porta %s | TLS=%s", PORTA, "ligado" if TLS else "DESLIGADO")
    # Dentro do container o serviço precisa escutar em todas as interfaces.
    app.run(host="0.0.0.0", port=PORTA, ssl_context=ssl)  # nosec B104
