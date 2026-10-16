# Ensaio da F-2 num container

Um "servidor" Ubuntu 24.04 com **systemd, sudo, visudo e Docker de verdade**,
para provar o ajudante das entregas B e C antes de ligá-lo na VPS. Não é a VPS:
não prova nginx, o Docker da VPS, o fuso dela nem o Ajudei. Rodado e aprovado em
16/10/2026 (resultado em `docs/esteira/conectar-acoes/verificacao.md`).

Tudo roda no Git Bash desta máquina, com o DERVS local de pé na 4790
(`DERVS_AMBIENTE=local`). `MSYS_NO_PATHCONV=1` impede o Git Bash de trocar
`/run` por um caminho do Windows.

```bash
export MSYS_NO_PATHCONV=1
cd infra/ensaio-f2
mkdir -p kit && gh api repos/garcia-goncalves/deploy-padrao/contents/servidor/deploy \
  --jq .content | base64 -d > kit/deploy          # o kit de publicar DE VERDADE
docker build -t dervs-f2:ensaio .
docker run -d --name dervs-f2 --hostname servidor-ensaio --privileged \
  --cgroupns=private --tmpfs /run --tmpfs /run/lock \
  -v dervs-f2-docker:/var/lib/docker -v dervs-f2-containerd:/var/lib/containerd \
  dervs-f2:ensaio
docker cp projeto.sh dervs-f2:/root/ && docker exec dervs-f2 bash /root/projeto.sh
```

Os dois volumes são obrigatórios: sem o do `containerd`, o `docker build` lá
dentro falha com `mount source: "overlay" ... invalid argument`.

`projeto.sh` cria o projeto `ensaio` em `/etc/deploy` e publica v1 e v2 pelo
kit, como usuário `tiba`: assim existe histórico e versão anterior para voltar.

Depois, a linha do painel (Conectar → Ligar um servidor) é colada como `tiba`
**num terminal** (`docker exec -it -u tiba dervs-f2 bash`). Por arquivo, a saída
do Python fica presa no buffer e o código de autorizar não aparece.

`ponte-4790.service` faz `localhost:4790` de dentro do container chegar ao DERVS
do Windows (`host.docker.internal`): o `Host` continua `localhost:4790`, que é o
que `HOSTS_OK` aceita, e o `rp_id` dos pedidos fica `localhost`.

Para desmontar: `docker rm -f dervs-f2 && docker volume rm dervs-f2-docker dervs-f2-containerd`.
