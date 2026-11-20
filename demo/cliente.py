"""
Cliente de demonstração: simula o portal da vinheria usando a API.
Roda DENTRO da rede Docker, então acessa os serviços pelo nome DNS.
"""
import json
import os
import sys

import requests

TLS = os.environ.get("TLS", "off").lower() == "on"
BASE = f"{'https' if TLS else 'http'}://ms-pedidos.vinheria.local:5001"
VERIFY = os.environ.get("CA_CERT", "/certs/ca.crt") if TLS else True
SENHA = os.environ.get("SENHA_DEMO", "")


def mostrar(titulo, resp):
    print(f"\n=== {titulo} ===")
    print(f"HTTP {resp.status_code}")
    try:
        print(json.dumps(resp.json(), indent=2, ensure_ascii=False))
    except ValueError:
        print(resp.text)


def main():
    print(f"Cliente da Vinheria -> {BASE}  (TLS {'LIGADO' if TLS else 'DESLIGADO'})")

    r = requests.get(f"{BASE}/pedidos/PED-QUALQUER", timeout=5, verify=VERIFY)
    mostrar("1. Tentativa SEM token (deve ser recusada)", r)

    r = requests.post(f"{BASE}/login", json={"usuario": "comercial", "senha": SENHA}, timeout=5, verify=VERIFY)
    mostrar("2. Login do usuário 'comercial'", r)
    if r.status_code != 200:
        sys.exit("login falhou - confira SENHA_DEMO no .env")
    cab = {"Authorization": "Bearer " + r.json()["access_token"]}

    r = requests.post(f"{BASE}/pedidos", json={"lote": "LT-2026-0147", "quantidade": 12},
                      headers=cab, timeout=10, verify=VERIFY)
    mostrar("3. Pedido de 12 garrafas (ms-pedidos chama o ms-rastreamento)", r)

    r = requests.post(f"{BASE}/pedidos", json={"lote": "LT-2025-0098", "quantidade": 500},
                      headers=cab, timeout=10, verify=VERIFY)
    mostrar("4. Pedido acima do estoque (deve ser rejeitado)", r)

    r = requests.post(f"{BASE}/pedidos", json={"lote": "LT-2026-0147", "quantidade": 6,
                                               "simular_falha_pagamento": True},
                      headers=cab, timeout=10, verify=VERIFY)
    mostrar("5. Pagamento recusado (Saga desfaz a reserva)", r)


if __name__ == "__main__":
    main()
