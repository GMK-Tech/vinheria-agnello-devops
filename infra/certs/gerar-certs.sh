#!/bin/sh
# ---------------------------------------------------------------------
# Gera uma Autoridade Certificadora (CA) local e um certificado TLS para
# cada microsserviço. Roda uma vez só: se os certificados já existem, sai.
# ---------------------------------------------------------------------
set -eu
DEST="${DEST:-/certs}"
DIAS=825
mkdir -p "$DEST"
cd "$DEST"

if [ -f ms-rastreamento.crt ]; then
  echo "[certs] certificados já existem em $DEST - nada a fazer"
  exit 0
fi

echo "[certs] criando a CA local da Vinheria..."
openssl req -x509 -newkey rsa:2048 -nodes -days "$DIAS" \
  -keyout ca.key -out ca.crt \
  -subj "/CN=Vinheria Agnello CA Local/O=GMKE Tech" \
  -addext "basicConstraints=critical,CA:TRUE" \
  -addext "keyUsage=critical,keyCertSign,cRLSign" 2>/dev/null

for svc in ms-pedidos ms-rastreamento; do
  echo "[certs] emitindo certificado para $svc.vinheria.local..."
  openssl req -newkey rsa:2048 -nodes -keyout "$svc.key" -out "$svc.csr" \
    -subj "/CN=$svc.vinheria.local/O=Vinheria Agnello" 2>/dev/null
  cat > "$svc.ext" <<EXT
basicConstraints=CA:FALSE
keyUsage=critical,digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
subjectAltName=DNS:$svc.vinheria.local,DNS:$svc,DNS:localhost,IP:127.0.0.1
subjectKeyIdentifier=hash
authorityKeyIdentifier=keyid,issuer
EXT
  openssl x509 -req -in "$svc.csr" -CA ca.crt -CAkey ca.key -CAcreateserial \
    -days "$DIAS" -out "$svc.crt" -extfile "$svc.ext" 2>/dev/null
  rm -f "$svc.csr" "$svc.ext"
done

# Ambiente de laboratório: os containers rodam com outro usuário e precisam ler.
chmod 644 ./*.crt ./*.key
echo "[certs] pronto:"
ls -1 "$DEST"
