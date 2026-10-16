#!/bin/bash
# Monta o projeto "ensaio" no servidor de ensaio e publica duas versoes pelo kit.
set -e
mkdir -p /etc/deploy /srv/ensaio
cat > /etc/deploy/ensaio.conf <<'X'
DIR=/srv/ensaio
COMPOSE="-p ensaio -f docker-compose.yml"
URL_SAUDE=http://127.0.0.1:8088/
ESPERA_SAUDE=60
PRESERVAR=".env*"
DONO=root
AVISAR=nao
ATIVO=sim
X
versao() {  # versao <texto>
  local d; d=$(mktemp -d)
  cat > "$d/Dockerfile" <<'X'
FROM busybox:1.36
COPY index.html /www/index.html
CMD ["httpd", "-f", "-p", "8080", "-h", "/www"]
X
  cat > "$d/docker-compose.yml" <<'X'
services:
  web:
    build: .
    image: ensaio-web
    ports: ["127.0.0.1:8088:8080"]
    restart: unless-stopped
X
  echo "$1" > "$d/index.html"
  mkdir -p /home/tiba/.deploy-envios
  tar -czf "/home/tiba/.deploy-envios/$1.tgz" -C "$d" .
  chown -R tiba:tiba /home/tiba/.deploy-envios
  sudo -u tiba sudo deploy ensaio "/home/tiba/.deploy-envios/$1.tgz" "$1"
}
versao v1
versao v2
sudo deploy --lista
cat /var/log/deploy/historico.log
curl -s http://127.0.0.1:8088/
