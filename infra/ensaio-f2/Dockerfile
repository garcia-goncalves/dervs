# Ensaio da F-2: um "servidor" Ubuntu com systemd, sudo, visudo e Docker de verdade.
FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
      systemd systemd-sysv dbus sudo python3 curl ca-certificates acl socat \
      rsync jq docker.io docker-compose-v2 iproute2 \
 && rm -rf /var/lib/apt/lists/* \
 && useradd -m -s /bin/bash tiba && usermod -aG sudo tiba \
 && echo 'tiba ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/tiba && chmod 440 /etc/sudoers.d/tiba
# O kit de publicacao, como o INSTALAR.md manda: /usr/local/bin/deploy, root, 755.
COPY kit/deploy /usr/local/bin/deploy
RUN sed -i 's/\r$//' /usr/local/bin/deploy && chmod 755 /usr/local/bin/deploy && chown root:root /usr/local/bin/deploy
# "localhost:4790" dentro do servidor chega ao DERVS local (o Host continua o permitido).
COPY ponte-4790.service /etc/systemd/system/ponte-4790.service
RUN sed -i 's/\r$//' /etc/systemd/system/ponte-4790.service && systemctl enable ponte-4790.service docker.service
STOPSIGNAL SIGRTMIN+3
CMD ["/sbin/init"]
