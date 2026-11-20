# Servidor DNS + DHCP da rede da Vinheria (equivalente às roles DNS e DHCP do Windows Server)
FROM alpine:3.20
RUN apk add --no-cache dnsmasq
EXPOSE 53/udp 53/tcp 67/udp
# -k: fica em primeiro plano (necessário em container)
ENTRYPOINT ["dnsmasq", "-k", "--conf-file=/etc/dnsmasq.conf"]
