# Vinheria Agnello — Infraestrutura, DevOps e DevSecOps

Simulação de parte da arquitetura de microsserviços da Vinheria Agnello
(Turma 3ESOA · Grupo GMKE Tech).

| Componente | Função |
|---|---|
| `services/ms-pedidos` | Pedidos — login (JWT de usuário) e criação de pedidos |
| `services/ms-rastreamento` | Lotes e reservas — aceita só chamadas com JWT de serviço |
| `infra/dnsmasq` | DNS (`vinheria.local`) + DHCP da rede |
| `infra/certs` | Gera a CA local e os certificados TLS |
| `infra/jenkins` | Jenkins com Python para o pipeline |
| `Jenkinsfile` | Checkout → Build → Testes → DevSecOps → Deploy |
| `tests/` | 18 testes automatizados |

Instruções completas: **[PASSO-A-PASSO.md](PASSO-A-PASSO.md)**

```bash
cp .env.example .env      # e editar os segredos
docker compose up -d --build
docker compose --profile demo run --rm cliente
```
