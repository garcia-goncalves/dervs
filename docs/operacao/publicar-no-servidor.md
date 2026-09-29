# Colocar o DERVS no ar em dervs.com.br

*Escrito em 28/08/2026, na etapa 16 da fatia 1. Publicação refeita em
25/09/2026: agora sai do VS Code, e o GitHub não publica mais nada.*

Este é o roteiro completo, e ele tem duas partes bem diferentes:

- **A parte de uma vez só** (passos 1 a 6). Preparar o servidor e guardar os
  segredos. Isso exige a sua mão, porque envolve senha, chave e uma decisão de
  produto. Leva uns 30 minutos, e depois nunca mais.
- **A parte de sempre** (passo 7). Publicar. Commit + push, e a tarefa
  **"Deploy para a VPS"** no VS Code.

Ao longo do texto, sempre que houver um comando para você, ele vem com: **onde
colar**, **o que aparece se der certo** e **o que fazer se der errado**.

> **Um jeito mais fácil de rodar qualquer comando daqui:** cole na conversa do
> Claude Code com um `!` na frente — assim: `! docker ps`. A saída cai direto na
> conversa e eu leio junto com você.

---

## Antes de começar: o que este desenho faz e não faz

**O que vai para o ar:** um container com o painel, escutando numa porta que
**só o próprio servidor enxerga**. Quem fala com a internet é o nginx que já está
naquela máquina, com o certificado do domínio.

**O que nunca vai:** a pasta `vivo/` — o código antigo do dervs, que abre um
terminal sem senha nenhuma. O `.dockerignore` e a cópia arquivo por arquivo do
`Dockerfile` o seguram fora da imagem (a terceira trava, a busca dentro da
imagem, era do `publicar.yml` e saiu com ele em 25/09/2026).

**A publicação não é automática.** Nenhum commit vai para o ar sozinho. Você
roda a tarefa do VS Code quando quer. Isso é decisão, não limitação: publicar a
cada commit é mandar todo rascunho para a gráfica.

**Um cuidado que vale repetir:** aquela VPS **não é terreno limpo**. São 26
containers servindo 8 sistemas, incluindo o Ajudei. Por isso o passo 2 confere a
porta antes de escolher, e por isso nenhum script deste projeto escreve na
configuração do nginx — quem faz isso é você, uma vez, olhando.

---

## Passo 1 — Entrar no servidor

**Onde:** no terminal do seu computador (PowerShell), ou colando na conversa com
`!` na frente.

```
ssh -p 3119 tiba@57.129.81.137
```

Os valores estão aí porque foram medidos, não supostos: a VPS é
`57.129.81.137`, o SSH atende na porta **3119** (a 22 está fechada) e o usuário
de publicação é `tiba`. O usuário `andre`, que aparece nos documentos do Ajudei,
é outro acesso da mesma máquina.

**Se der certo:** o texto muda e passa a começar com algo como
`root@vps-alguma-coisa:~#`. Daí em diante, tudo o que você digitar acontece **no
servidor**, não no seu computador.

**Se der errado:**
- `Permission denied` → a chave de acesso não está no lugar. É o mesmo `ssh` que
  você já usa para o Ajudei; se aquele funciona, este funciona.
- `Connection timed out` → o endereço está errado, ou a VPS está fora do ar.

---

## Passo 2 — Escolher uma porta livre (o passo que evita derrubar outro sistema)

**Onde:** dentro do servidor, na janela que você abriu no passo 1.

```
ss -ltnp | awk '{print $4}' | grep -oE '[0-9]+$' | sort -n | uniq | tr '\n' ' '
```

Isso lista todos os números de porta já ocupados naquela máquina.

**O que fazer com a resposta:** procure o número **4877** na lista.

- **Se 4877 NÃO aparecer** → ótimo, é a porta do DERVS. Siga.
- **Se 4877 aparecer** → escolha outro número entre 4800 e 4999 que também não
  esteja na lista, e **anote**. Ele vai aparecer em dois lugares mais adiante
  (passo 4 e passo 5), e os dois têm de ter o mesmo número.

**Por que isso importa:** subir na porta de outro sistema não dá erro bonito. O
outro sistema simplesmente para de responder, e ninguém liga uma coisa à outra.

---

## Passo 3 — Criar a pasta do projeto no servidor

**Onde:** ainda dentro do servidor.

```
mkdir -p /opt/dervs && cd /opt/dervs && pwd
```

**Se der certo:** aparece `/opt/dervs`.

---

## Passo 4 — Gerar os segredos e gravá-los, dentro do servidor

Aqui está a regra que não tem exceção: **o segredo nasce dentro do servidor e
nunca sai de lá.** Não passa por conversa, por commit, por documentação nem por
mim. O que este arquivo registra é **onde** ele mora, nunca o valor.

**Onde:** dentro do servidor, na pasta `/opt/dervs`.

Cole isto **inteiro, de uma vez** (é um comando só, em várias linhas):

```
umask 077 && cat > /opt/dervs/.env <<'FIM'
DERVS_PORTA=4877
DERVS_DOMINIO=dervs.com.br
DERVS_COFRE=TROQUE-ESTA-LINHA
DERVS_GITHUB_ID=
DERVS_GITHUB_SECRET=
FIM
sed -i "s|^DERVS_COFRE=.*|DERVS_COFRE=$(openssl rand -hex 32)|" /opt/dervs/.env
chmod 600 /opt/dervs/.env
grep -c '^DERVS_' /opt/dervs/.env
```

**Se der certo:** aparece o número **5**. São as cinco linhas de configuração. O
`sed` da penúltima linha trocou o `TROQUE-ESTA-LINHA` por 64 caracteres
sorteados — **você nunca precisa ver esse valor, e é melhor assim**.

**Se você mudou a porta no passo 2:** troque o `4877` da primeira linha pelo
número que você anotou.

**Se der errado:**
- `openssl: command not found` → use no lugar:
  `sed -i "s|^DERVS_COFRE=.*|DERVS_COFRE=$(head -c 32 /dev/urandom | base64 | tr -d '=+/')|" /opt/dervs/.env`

> **O que é o "cofre":** é a chave que embaralha os dados sensíveis dentro do
> banco do painel. Se ela mudar depois, o que já foi guardado não abre mais.
> Por isso ela é gerada uma vez e fica quieta.

> **Uma sexta variável que você não precisa escrever.** O
> `DERVS_PROXIES_CONFIAVEIS` já vem com o valor certo no `docker-compose.yml`.
> Ela diz ao painel que o pedido veio do nginx e que o endereço de quem chegou
> está no cabeçalho, não na conexão. Sem ela, todo visitante do mundo dividiria
> **o mesmo** teto de cinco tentativas — e cinco chamadas de um estranho
> trancariam você para fora do próprio painel.

---

## Passo 4.5 — Um teste que vale a pena antes de continuar

Ainda dentro do servidor, confira que o Docker e o compose respondem:

```
docker compose version && docker ps --format '{{.Names}}' | wc -l
```

**Se der certo:** sai a versão do compose e o número de containers rodando na
máquina — deve ser algo perto de 26. Se sair `0`, algo está errado com o Docker
daquela VPS e **pare aqui**, porque publicar por cima disso vai dar confusão.

**As duas linhas vazias (`DERVS_GITHUB_ID` e `DERVS_GITHUB_SECRET`)** são a
entrada por GitHub. Enquanto estiverem vazias, aquele botão simplesmente não
existe no site — e o painel funciona pelas outras portas de entrada. O passo 6
preenche as duas.

---

## Passo 5 — Instalar o porteiro do site (nginx)

**Onde:** dentro do servidor.

Primeiro, o certificado do domínio. Confira se ele já existe:

```
ls /etc/letsencrypt/live/dervs.com.br/fullchain.pem
```

- **Se aparecer o caminho** → o certificado existe, siga.
- **Se aparecer `No such file or directory`** → falta emitir. Rode:
  `certbot certonly --webroot -w /var/www/html -d dervs.com.br -d www.dervs.com.br`
  e responda o que ele perguntar (e-mail e aceite dos termos). Isso só funciona
  se o domínio já apontar para esta VPS — e ele já aponta.

> **Atenção, e isto vai acontecer com você:** já existe um bloco respondendo
> por `dervs.com.br` — o arquivo `/etc/nginx/sites-available/dervs` (sem
> `.conf`), que serve a página provisória de `/var/www/dervs`. Conferido em
> 28/08/2026: `https://dervs.com.br` responde 200 com certificado válido. Esse
> bloco antigo **tem de sair do ar antes** do novo entrar, senão o nginx recusa
> os dois com `conflicting server name`. Desligar é apagar o link, não o
> arquivo:
> `sudo rm -f /etc/nginx/sites-enabled/dervs`

Agora o arquivo do site. O conteúdo dele está no repositório, em
`infra/nginx-dervs.conf`. Traga-o e ligue:

```
curl -fsSL -H "Authorization: token SEU-TOKEN-DO-GITHUB" \
  https://raw.githubusercontent.com/garcia-goncalves/dervs/main/infra/nginx-dervs.conf \
  -o /etc/nginx/sites-available/dervs.conf
ln -sfn /etc/nginx/sites-available/dervs.conf /etc/nginx/sites-enabled/dervs.conf
nginx -t
```

**Se der certo:** as duas últimas linhas da resposta são
`syntax is ok` e `test is successful`.

**Se der errado:**
- `conflicting server name` → já existe outro arquivo respondendo por
  `dervs.com.br`. Ache com `grep -rl dervs.com.br /etc/nginx/sites-enabled/` e
  me mostre o resultado **antes de apagar nada** — pode ser de outro sistema.
- `cannot load certificate` → volte ao certificado, acima.

**Se você mudou a porta no passo 2:** antes do `nginx -t`, troque o número
dentro do arquivo:
`sed -i 's|127.0.0.1:4877|127.0.0.1:SUA-PORTA|' /etc/nginx/sites-available/dervs.conf`

> **Um cuidado, e ele é específico desta máquina:** nunca deixe uma segunda
> cópia do arquivo em `/etc/nginx/sites-enabled/` — nem com outro nome, nem
> como `dervs.conf.bak`, nem como `dervs.conf~`. O nginx do Debian inclui
> **tudo** o que está naquela pasta, sem olhar a extensão, e uma cópia
> esquecida faz ele recusar a configuração inteira. Se isso acontecer, o
> `nginx -t` acima fica vermelho e o `reload` não é aplicado — os outros 8
> sistemas continuam no ar, e é para isso que o teste vem antes. Para guardar
> uma cópia, guarde fora: `cp dervs.conf /root/dervs.conf.guardado`.

Só depois do `test is successful`, aplique:

```
systemctl reload nginx && systemctl is-active nginx
```

**Se der certo:** aparece `active`. O `reload` não derruba os outros 8 sistemas:
ele troca a configuração sem parar o nginx.

---

## Passo 6 — O que era do workflow e agora é à mão, com o administrador

Até 25/09/2026 o `publicar.yml` do GitHub gravava valores no `/opt/dervs/.env`
e rodava comandos dentro do container. Ele saiu (o runner do GitHub foi tirado
do servidor, e as chaves de robô apagadas). Estas tarefas agora são **manuais
no servidor**, feitas pelo administrador da VPS. Nada disso muda a cada
publicação: o `.env` e o banco (volume `dervs-dados`) ficam onde estão.

**6.1 — entrada por GitHub (OAuth App) e GitHub App.** NÃO é opcional: em
produção `/entrar/github` é a **única** porta de entrada, e sem
`DERVS_GITHUB_ID`/`DERVS_GITHUB_SECRET` ela responde 404 (foi o que aconteceu em
28/08/2026). No GitHub, o callback do App **DERVS** tem de ser
`https://dervs.com.br/entrar/github/retorno`. Os valores vão direto no
`/opt/dervs/.env` (`DERVS_GITHUB_ID`, `DERVS_GITHUB_SECRET`,
`DERVS_GITHUB_APP_SLUG`, `DERVS_GITHUB_APP_ID`, `DERVS_GITHUB_APP_KEY`), e depois
uma publicação (ou `docker compose up -d` na pasta) recria o container.

> A chave do GitHub App vai **em uma linha**, sem as linhas `-----BEGIN`/
> `-----END`: `grep -v -- ----- chave.pem | tr -d '\n'`. Colar o arquivo
> inteiro achatado produz uma linha começando com `-----`, que o painel descarta
> — a chave sairia vazia. Chave cifrada (`ENCRYPTED`) não serve. Para conferir:
> `docker exec dervs python -c 'import os, github_app; print(bool(github_app.chave_de_pem(os.environ.get("DERVS_GITHUB_APP_KEY") or "")))'`
> tem de dizer `True`.

**6.2 — a combinação da cortina (seis dígitos).** Nasce sorteada na primeira
subida e é impressa uma vez, no registro daquele container. Para trocar, dentro
do servidor (o número vai por STDIN, não aparece em `ps`):

```
read -rs CORTINA && printf '%s' "$CORTINA" | docker exec -i dervs python -c 'import sys, banco, cortina; con = banco.conectar(); cortina.trocar(sys.stdin.read().strip(), con); con.close(); print("combinacao da cortina trocada")'; unset CORTINA
```

**6.3 — a conta de um dono.** `autenticacao.convidar()` é a **única** forma de
criar conta, e não passa pela web de propósito. O e-mail é único e **não existe
comando para apagar conta criada errada** — confira antes. Dentro do servidor:

```
printf '%s\n' "login-do-github email@exemplo.com" | docker exec -i dervs python -c 'import sys, banco, autenticacao; con = banco.conectar(); ns = [l.split() for l in sys.stdin.read().splitlines() if l.split()]; [print(("ja existe: %s" % e) if con.execute("SELECT 1 FROM usuario WHERE email = ?", (e.strip().lower(),)).fetchone() else ("conta criada: %s (id %d)" % (e, autenticacao.convidar(g, e, con=con)))) for g, e in ns]; con.close()'
```

---

## Passo 7 — Publicar (este é o passo de sempre)

O padrão da VPS, e como configurar o seu computador uma vez, estão em
<https://github.com/garcia-goncalves/deploy-padrao>.

**O apelido SSH `vps-ovh` (uma vez, no seu computador).** O SSH desta VPS
escuta na porta **3119**, o usuário é `tiba`, e a porta 22 está fechada. Sem o
apelido, o deploy pára em `Could not resolve hostname` ou em `Connection timed
out`. Crie uma chave só para o deploy (`ssh-keygen -t ed25519 -f
"$HOME\.ssh\dervs_deploy"`), peça ao administrador para acrescentar a parte
**pública** (`.pub`) ao `authorized_keys` do `tiba` e cadastre no `~/.ssh/config`:

```
Host vps-ovh
    HostName 57.129.81.137
    Port 3119
    User tiba
    IdentityFile ~/.ssh/dervs_deploy
    IdentitiesOnly yes
```

Teste com `ssh vps-ovh "sudo deploy --lista"`: deve listar os projetos, com o
`dervs` como `sim`. A chave pede a frase dela a cada etapa do deploy. Quem
tiver o arquivo da chave privada entra como `tiba`: ele não sai do seu
computador, e revogar é apagar a linha no servidor.

1. Faça commit e **push** para a `main` (o servidor publica o que está no
   GitHub, não o que está só no seu disco).
2. No VS Code: **Terminal → Executar Tarefa → "Deploy para a VPS"**.

**O que acontece:** o servidor faz backup do volume `dervs-dados`, pega o
commit, **monta a imagem ali mesmo** (`build: .` no `docker-compose.yml`, imagem
`dervs:vps`) com a versão antiga no ar, troca o container e confere
`https://dervs.com.br/robots.txt`. Se o site não responder, ele **volta sozinho**
para a versão anterior. O `/opt/dervs/.env` nunca é tocado.

**Se der errado:** leia as últimas linhas da tarefa. Se a imagem não montar ou
o container não ficar saudável, a causa está no código — a versão anterior
continua no ar.

---

## Voltar atrás

No VS Code: **Terminal → Executar Tarefa → "Deploy: voltar para a versao
anterior"**.

**O banco não é afetado por isso.** Ele mora num volume separado, fora da imagem
— é justamente para que voltar atrás no código não custe nenhuma conta, nenhum
computador pareado e nenhuma medição.

---

## Onde cada coisa mora, para consulta rápida

| Coisa | Onde |
|---|---|
| Os segredos do painel | `/opt/dervs/.env`, dentro do servidor, só leitura do dono |
| A configuração da publicação | `/etc/deploy/dervs.conf` (servidor) e `.deploy-vps` (repositório) |
| O banco | volume Docker `dervs-dados`, fora da imagem (backup antes de cada publicação) |
| A configuração do nginx | `/etc/nginx/sites-available/dervs.conf` |
| O certificado | `/etc/letsencrypt/live/dervs.com.br/` |
| O que está no ar agora | `ssh vps-ovh sudo deploy --lista` |
