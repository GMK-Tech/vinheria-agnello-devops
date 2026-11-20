# Vinheria Agnello — Infraestrutura, Deploy e Comunicação Segura

**Turma:** 3ESOA · **Grupo:** GMKE Tech
**Serviços escolhidos (da fase anterior):** `ms-pedidos` e `ms-rastreamento`

---

## 0. O que vocês vão montar

```
                       rede vinheria-net  172.28.0.0/24
  ┌──────────────────────────────────────────────────────────────────┐
  │  dns-dhcp .2        ms-pedidos .11  ──REST+JWT──►  ms-rastreamento .12
  │  (dnsmasq)               ▲                                        │
  │  DNS: *.vinheria.local   │ login + pedido         jenkins .20     │
  │  DHCP: .150 – .200       │                        └─► /publicacao  │
  │                     cliente (demo)       caixa-loja-01 .150 (DHCP)│
  └──────────────────────────────────────────────────────────────────┘
```

| Requisito do enunciado | Onde está atendido |
|---|---|
| 2 microsserviços | `services/ms-pedidos` e `services/ms-rastreamento` (Python + Flask) |
| Rede e serviços em containers | `docker-compose.yml`, rede própria com IPs fixos |
| DHCP e DNS, serviços registrados | Container `dns-dhcp` (dnsmasq): zona `vinheria.local`, escopo DHCP e reserva |
| Serviços se comunicando | `ms-pedidos` chama `ms-rastreamento` **pelo nome DNS** |
| Repositório Git | Esta pasta, publicada no GitHub |
| Pipeline Jenkins com build e deploy | `Jenkinsfile`: Checkout → Build → Testes → DevSecOps → Deploy |
| Pasta de publicação | `publicacao/` (simula o `wwwroot` do IIS) |
| Autenticação | Login com JWT de usuário + JWT de serviço entre os microsserviços |
| Wireshark: sem e com criptografia | Captura com `TLS=off` e com `TLS=on`, comparando as duas |

---

## 1. Pré-requisitos

- **Docker Desktop** (no Windows, com backend WSL 2) — https://www.docker.com/products/docker-desktop
- **Git** — https://git-scm.com
- **Conta no GitHub**
- **Wireshark** — https://www.wireshark.org
- Portas **5001**, **5002** e **8080** livres na máquina
- Cerca de **4 GB de RAM livres** (o Jenkins é o mais pesado)

> **Windows:** rodem os comandos no **PowerShell**. Onde aparecer `curl.exe`, escrevam
> exatamente assim — no PowerShell, `curl` sozinho é outro comando.

---

## 2. Etapa 1 — Repositório Git

1. No GitHub, criem um repositório **público** chamado `vinheria-agnello-devops`
   (público dispensa configurar credencial no Jenkins).
2. Extraiam o zip e, dentro da pasta:

```powershell
# só na primeira vez que usam o Git nesta máquina:
git config --global user.name "Seu Nome"
git config --global user.email "seu@email.com"

git init -b main
git add .
git commit -m "Vinheria Agnello: ms-pedidos e ms-rastreamento"
git remote add origin https://github.com/<usuario>/vinheria-agnello-devops.git
git push -u origin main
```

O `.gitignore` já impede que segredos (`.env`), certificados e capturas subam para o
GitHub. Isso é prática de segurança e vale citar no PDF.

📸 **P01** — repositório no GitHub mostrando os arquivos.

---

## 3. Etapa 2 — Subir a infraestrutura

```powershell
copy .env.example .env
notepad .env
```

No `.env`, troquem os dois segredos por textos longos e diferentes entre si. Deixem
**`TLS=off`** por enquanto — a primeira demonstração de segurança é justamente sem
criptografia.

```powershell
docker compose up -d --build
docker compose ps
```

A primeira vez demora alguns minutos (download das imagens). O container `certs` roda,
gera os certificados TLS e termina — é normal ele aparecer como `exited (0)`.

Conferindo que os serviços estão de pé:

```powershell
curl.exe http://localhost:5001/health
curl.exe http://localhost:5002/health
```

📸 **P02** — saída do `docker compose ps` com todos os containers `running`.
📸 **P03** — Docker Desktop mostrando o grupo `vinheria`.
📸 **P04** — a rede: `docker network inspect vinheria_vinheria-net` (trecho com sub-rede e IPs).

---

## 4. Etapa 3 — DNS e DHCP

O container `dns-dhcp` faz o papel das roles **DNS Server** e **DHCP Server** do Windows
Server. A configuração inteira está em `infra/dnsmasq/dnsmasq.conf`, comentada.

| Conceito no Windows Server | Equivalente aqui |
|---|---|
| Zona de pesquisa direta `vinheria.local` | `domain=vinheria.local` + `local=/vinheria.local/` |
| Registros A | `host-record=ms-pedidos.vinheria.local,172.28.0.11` (e os demais) |
| Zona reversa (PTR) | Criada automaticamente pelo `host-record` |
| Registro CNAME | `cname=api.vinheria.local,ms-pedidos.vinheria.local` |
| Encaminhadores | `server=127.0.0.11` (nomes externos vão para o DNS da máquina) |
| Escopo DHCP | `dhcp-range=172.28.0.150,172.28.0.200,...,12h` |
| Opções 003 / 006 / 015 | `dhcp-option=router`, `dns-server`, `domain-name` |
| Reserva | `dhcp-host=02:42:ac:1c:00:96,caixa-loja-01,172.28.0.150` |

### 4.1 DNS

```powershell
docker exec dns-dhcp nslookup ms-rastreamento.vinheria.local 172.28.0.2
docker exec dns-dhcp nslookup api.vinheria.local 172.28.0.2
docker exec dns-dhcp nslookup 172.28.0.12 172.28.0.2
```

Resultados esperados: `172.28.0.12`, o CNAME apontando para `ms-pedidos`, e a consulta
reversa devolvendo `ms-rastreamento.vinheria.local`.

### 4.2 DHCP

Este container simula um **caixa da loja** ligando na rede e pedindo um IP:

```powershell
docker compose --profile dhcp run --rm cliente-dhcp
```

Saída esperada:

```
udhcpc: broadcasting discover
udhcpc: broadcasting select for 172.28.0.150, server 172.28.0.2
udhcpc: lease of 172.28.0.150 obtained from 172.28.0.2, lease time 43200
```

Ele recebeu o `.150` porque o MAC dele está **reservado**. E, como informou o nome
`caixa-loja-01`, o dnsmasq **registrou esse nome no DNS automaticamente**:

```powershell
docker exec dns-dhcp nslookup caixa-loja-01.vinheria.local 172.28.0.2
docker logs dns-dhcp
```

No log aparecem as quatro fases do DHCP — **DISCOVER → OFFER → REQUEST → ACK** — e cada
consulta DNS feita na rede.

📸 **P05** — trecho do `dnsmasq.conf` (zona + registros).
📸 **P06** — trecho do `dnsmasq.conf` (escopo DHCP + reserva).
📸 **P07** — os três `nslookup` da 4.1.
📸 **P08** — saída do `cliente-dhcp` recebendo o IP.
📸 **P09** — `docker logs dns-dhcp` com DISCOVER/OFFER/REQUEST/ACK.
📸 **P10** — `nslookup caixa-loja-01.vinheria.local` (nome registrado via DHCP).

---

## 5. Etapa 4 — Os serviços conversando

```powershell
docker compose --profile demo run --rm cliente
```

O cliente executa cinco cenários e imprime o resultado de cada um:

| # | Cenário | Resultado esperado |
|---|---|---|
| 1 | Acesso sem token | `401` — recusado |
| 2 | Login do usuário `comercial` | `200` + `access_token` |
| 3 | Pedido de 12 garrafas | `201 CONFIRMADO` — o `ms-pedidos` reservou no `ms-rastreamento` |
| 4 | Pedido acima do estoque | `409 REJEITADO` |
| 5 | Pagamento recusado | `402 CANCELADO` — a Saga desfez a reserva |

Agora vejam o lado de dentro:

```powershell
docker logs ms-pedidos
docker logs ms-rastreamento
docker logs dns-dhcp --tail 20
```

- No `ms-pedidos`: `-> POST http://ms-rastreamento.vinheria.local:5002/...` — a chamada é
  feita **pelo nome**, não pelo IP.
- No `dns-dhcp`: `query[A] ms-rastreamento.vinheria.local from 172.28.0.11` — a prova de
  que quem resolveu o nome foi o nosso DNS.
- No `ms-rastreamento`: `chamador=ms-pedidos` — ele sabe quem chamou, porque leu o JWT
  de serviço.

📸 **P11** — saída completa do cliente.
📸 **P12** — log do `ms-pedidos` com a chamada pelo nome DNS.
📸 **P13** — log do `dns-dhcp` com a consulta vinda do `172.28.0.11`.

---

## 6. Etapa 5 — Pipeline no Jenkins

### 6.1 Primeiro acesso

1. Abram **http://localhost:8080**.
2. Senha inicial:
   ```powershell
   docker exec jenkins cat /var/jenkins_home/secrets/initialAdminPassword
   ```
3. **Install suggested plugins** → criem o usuário administrador → **Save and Finish**.

### 6.2 Criar o job

1. **Nova tarefa** → nome `vinheria-deploy` → **Pipeline** → OK.
2. Em **Pipeline**:
   - Definition: **Pipeline script from SCM**
   - SCM: **Git**
   - Repository URL: a URL do repositório de vocês
   - Branch: `*/main`
   - Script Path: `Jenkinsfile`
3. **Salvar** → **Construir agora**.

### 6.3 O que o pipeline faz

| Estágio | O que acontece |
|---|---|
| **Checkout** | Baixa o código do GitHub |
| **Build** | `echo 'Deploy da Vinheria'`, instala as dependências e compila os dois serviços |
| **Testes** | Roda os 18 testes automatizados (autenticação, estoque, Saga) |
| **DevSecOps** | `bandit` procura falhas de segurança no código — o build **falha** se encontrar algo médio ou grave |
| **Deploy** | Copia os serviços para `publicacao/releases/build-N` e atualiza `publicacao/atual` |

A pasta `publicacao/` está montada dentro do Jenkins: abram-na no Explorer depois do
build. Cada execução gera uma pasta nova em `releases/` (o histórico, que permite voltar
uma versão) e substitui `atual/` (o que está "no ar", como a pasta do site no IIS). O
arquivo `atual/VERSAO.txt` mostra build, commit e data.

### 6.4 Provando que o DevSecOps funciona (recomendado)

1. Em `services/ms-pedidos/app.py`, última linha, acrescentem `debug=True` dentro do
   `app.run(...)`.
2. `git commit` + `git push` → **Construir agora**.
3. O estágio **DevSecOps falha** com `B201: flask_debug_true` — modo debug do Flask
   permite executar código remotamente. **Nada é publicado.**
4. Desfaçam a mudança, `push` de novo → build verde.

Esse "vermelho → verde" é a melhor evidência de DevSecOps que vocês podem mostrar.

### 6.5 Deploy automático (opcional)

Na configuração do job, marquem **Consultar periodicamente o SCM** com `H/2 * * * *`. O
Jenkins verifica o GitHub a cada 2 minutos e dispara sozinho quando houver commit novo.

📸 **P14** — configuração do job (seção Pipeline).
📸 **P15** — **Stage View** com os 5 estágios verdes.
📸 **P16** — **Console Output** mostrando `Deploy da Vinheria` e os testes passando.
📸 **P17** — pasta `publicacao/` no Explorer + conteúdo do `VERSAO.txt`.
📸 **P18** — build vermelho no estágio DevSecOps (item 6.4).

---

## 7. Etapa 6 — Comunicação segura e Wireshark

### 7.1 Como os serviços se autenticam

| Trecho | Mecanismo |
|---|---|
| Usuário → `ms-pedidos` | `POST /login` com usuário e senha → recebe **JWT de usuário** (15 min), enviado depois em `Authorization: Bearer` |
| Autorização | O token carrega o **papel**: `comercial` cria pedidos, `auditor` só consulta |
| `ms-pedidos` → `ms-rastreamento` | **JWT de serviço** próprio (60 s), com destinatário (`aud`) e escopo (`reservas:write`). **O token do usuário nunca é repassado** |
| Validações no `ms-rastreamento` | Assinatura, expiração, destinatário, escopo e algoritmo fixo em `HS256` (bloqueia o ataque `alg: none`) |
| Transporte | `TLS=off` → HTTP puro · `TLS=on` → HTTPS com certificados de uma CA própria |

### 7.2 Captura SEM criptografia (`TLS=off`)

```powershell
docker compose --profile captura up -d sniffer
docker compose --profile demo run --rm cliente
docker compose --profile captura stop sniffer
```

Isso gera `capturas/trafego-tls-off.pcap`.

> **Por que um "sniffer" em container, e não o Wireshark direto na placa de rede?**
> No Windows, os containers rodam dentro de uma máquina virtual do Docker Desktop. O
> Wireshark da máquina não enxerga o tráfego entre eles. O `sniffer` grava a captura de
> dentro da rede, e o Wireshark só abre o arquivo.

No Wireshark:

1. **Arquivo → Abrir** → `capturas/trafego-tls-off.pcap`.
2. As portas 5001/5002 não são portas HTTP padrão. Ensinem isso ao Wireshark:
   **Analisar → Decodificar como…** → `+` → *TCP port* `5001` → **HTTP**; repitam para `5002`.
3. Filtro: `http.request.method == "POST"`.
4. Cliquem no `POST /login` → botão direito → **Seguir → Fluxo HTTP**.

Vão aparecer, **em texto puro**:

- `{"usuario": "comercial", "senha": "..."}` — a senha do usuário
- `Authorization: Bearer eyJ...` — os tokens, inclusive o de serviço na porta 5002
- Lotes, quantidades e IDs de pedido

**Demonstração extra — o JWT não é criptografado:** copiem um token capturado e colem em
https://jwt.io. O conteúdo (usuário, papel, escopo, expiração) aparece na hora, sem
precisar de segredo nenhum. A assinatura impede **alteração**, não **leitura**.

**Demonstração extra — roubo de sessão:** copiem o token de **usuário** (porta 5001) e
usem antes de ele expirar:

```powershell
curl.exe -X POST http://localhost:5001/pedidos -H "Content-Type: application/json" -H "Authorization: Bearer COLE_O_TOKEN_AQUI" -d "@demo/pedido.json"
```

O pedido é aceito. Quem escuta a rede vira o usuário.

### 7.3 Captura COM criptografia (`TLS=on`)

1. No `.env`, mudem para `TLS=on`.
2. Recriem os serviços e repitam a captura:

```powershell
docker compose up -d
docker compose --profile captura up -d --force-recreate sniffer
docker compose --profile demo run --rm cliente
docker compose --profile captura stop sniffer
```

Agora o arquivo é `capturas/trafego-tls-on.pcap`, e o log mostra `https://`. No Wireshark:

1. Abram o arquivo e usem o filtro `tls`.
2. Só aparecem **Client Hello**, **Server Hello** e **Application Data**.
3. **Seguir → Fluxo TCP** mostra apenas bytes ilegíveis. Senha, tokens e dados de pedido
   não aparecem mais.
4. Abram um **Client Hello** → *Extension: server_name*: o nome
   `ms-rastreamento.vinheria.local` continua visível. O TLS esconde o **conteúdo**, mas
   não **com quem** se fala — ponto bom para a reflexão.

📸 **P19** — Wireshark, `TLS=off`: fluxo HTTP do `/login` com a senha visível.
📸 **P20** — Wireshark, `TLS=off`: `Authorization: Bearer` na porta 5002 (serviço → serviço).
📸 **P21** — jwt.io decodificando o token capturado.
📸 **P22** — o `curl.exe` com token roubado sendo aceito.
📸 **P23** — Wireshark, `TLS=on`: lista com Client Hello / Application Data.
📸 **P24** — Wireshark, `TLS=on`: fluxo TCP ilegível.
📸 **P25** — `docker logs ms-pedidos` mostrando `TLS=ligado` e `https://`.

---

## 8. Roteiro do PDF

| Seção do PDF (exigida) | Conteúdo | Prints |
|---|---|---|
| **1. Serviços e infraestrutura** | Por que esses dois serviços (vem da fase anterior: o pedido precisa reservar lote, e é a chamada síncrona do sistema). Tabela de IPs da seção 0. Tabela "Windows Server × dnsmasq" da seção 4. | P02–P04 |
| **2. DHCP e DNS** | Zona, registros A/PTR/CNAME, escopo, reserva, registro dinâmico do `caixa-loja-01`. | P05–P10, P12–P13 |
| **3. Fluxo de deploy** | Tabela de estágios da 6.3. Caminho: `git push` → Jenkins → testes → bandit → pasta de publicação. Releases versionadas. | P01, P14–P18 |
| **4. Práticas de segurança** | Tabela da 7.1. Comparação HTTP × HTTPS. Mais: segredos fora do Git, containers sem root, análise estática no pipeline, token curto, token de serviço separado do de usuário. | P11, P19–P25 |
| **5. Reflexão final** | Ver abaixo. | — |

### Sobre a reflexão

Ela precisa vir da experiência real do grupo — anotem durante a montagem o que travou.
Perguntas para guiar:

- O que mais deu trabalho para funcionar, e como resolveram?
- O que mudou na percepção de vocês ao ver a senha em texto puro no Wireshark?
- Por que o JWT, sozinho, não basta? O que o TLS resolve que o JWT não resolve — e vice-versa?
- O que o TLS **não** esconde (o nome do servidor no Client Hello)?
- Qual a vantagem de o pipeline barrar código inseguro antes do deploy, e não depois?
- O que falta para isso ir para produção? (servidor de aplicação real no lugar do servidor
  de desenvolvimento do Flask; segredos em cofre e não em `.env`; banco de dados no lugar
  da memória; CA de verdade; um API Gateway na frente, como na arquitetura da fase anterior)

---

## 9. Solução de problemas

| Sintoma | Causa provável e solução |
|---|---|
| `certs` sai com erro `set: illegal option -` | O Git converteu os finais de linha para Windows. O `.gitattributes` evita isso em clones novos; se já aconteceu: `git rm --cached -r .` e `git reset --hard` |
| `ms-pedidos` não sobe: "defina ... no .env" | Faltou criar o `.env` a partir do `.env.example` |
| Jenkins não instala plugins ou não acessa o GitHub | O DNS da vinheria encaminha nomes externos para o DNS da máquina. Confiram `docker logs dns-dhcp`; em rede de faculdade com proxy, testem em outra rede |
| Estágio Deploy: `Permission denied` em `/publicacao` (Linux) | `sudo chown -R 1000:1000 publicacao` |
| Porta 8080 já em uso | Em `docker-compose.yml`, troquem `"8080:8080"` por `"8081:8080"` e acessem a 8081 |
| Wireshark não mostra nada com o filtro `http` | Falta o **Decodificar como…** das portas 5001/5002 (item 7.2) |
| Cliente com `TLS=on` dá erro de certificado | A pasta `infra/certs/out` foi apagada depois de os serviços subirem. `docker compose down`, apaguem a pasta e `docker compose up -d` de novo |

### Desligar tudo

```powershell
docker compose --profile demo --profile dhcp --profile captura down      # mantém os dados do Jenkins
docker compose --profile demo --profile dhcp --profile captura down -v   # apaga tudo, inclusive o Jenkins
```
