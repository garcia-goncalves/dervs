# Colocar o DERVS no ar em dervs.com.br

*Escrito em 28/08/2026, na etapa 16 da fatia 1.*

Este é o roteiro completo, e ele tem duas partes bem diferentes:

- **A parte de uma vez só** (passos 1 a 6). Preparar o servidor e guardar os
  segredos. Isso exige a sua mão, porque envolve senha, chave e uma decisão de
  produto. Leva uns 30 minutos, e depois nunca mais.
- **A parte de sempre** (passo 7). Publicar. Um botão no GitHub, e pronto.

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
terminal sem senha nenhuma. Três travas independentes o seguram, e a publicação
para se qualquer uma cair.

**A publicação não é automática.** Nenhum commit vai para o ar sozinho. Você
aperta um botão e digita a palavra `PUBLICAR`. Isso é decisão, não limitação:
publicar a cada commit é mandar todo rascunho para a gráfica.

**Um cuidado que vale repetir:** aquela VPS **não é terreno limpo**. São 26
containers servindo 8 sistemas, incluindo o Ajudei. Por isso o passo 2 confere a
porta antes de escolher, e por isso nenhum script deste projeto escreve na
configuração do nginx — quem faz isso é você, uma vez, olhando.

---

## Passo 1 — Entrar no servidor

**Onde:** no terminal do seu computador (PowerShell), ou colando na conversa com
`!` na frente.

```
ssh root@SEU-SERVIDOR
```

Troque `SEU-SERVIDOR` pelo endereço da VPS da OVH.

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

Só depois do `test is successful`, aplique:

```
systemctl reload nginx && systemctl is-active nginx
```

**Se der certo:** aparece `active`. O `reload` não derruba os outros 8 sistemas:
ele troca a configuração sem parar o nginx.

---

## Passo 6 — Guardar no GitHub o que o robô da publicação precisa

Estes são os quatro valores que o GitHub usa para chegar ao servidor. Eles ficam
guardados **no GitHub**, cifrados, e nem eu nem você os lemos de volta depois.

**Onde:** no navegador, em
<https://github.com/garcia-goncalves/dervs/settings/secrets/actions>.

Clique em **New repository secret**, uma vez para cada linha da tabela:

| Nome (copie exatamente) | O que colar no valor |
|---|---|
| `VPS_HOST` | o endereço da VPS (o mesmo que você usou no `ssh` do passo 1) |
| `VPS_USUARIO` | `root` (ou o usuário que você usa no `ssh`) |
| `VPS_CHAVE_SSH` | a **chave privada** que abre o servidor — o arquivo inteiro, do `-----BEGIN` ao `-----END` |
| `VPS_IMPRESSAO_DIGITAL` | a linha que o passo 6.1 abaixo gera |

**6.1 — a impressão digital do servidor.** Ela é o que impede o deploy de ser
entregue a uma máquina que só *finge* ser a sua VPS. **Onde:** no seu
computador (não dentro do servidor):

```
ssh-keyscan -t ed25519 SEU-SERVIDOR
```

**Se der certo:** sai uma linha longa começando com o endereço e
`ssh-ed25519 AAAA...`. É essa linha inteira que vai no valor de
`VPS_IMPRESSAO_DIGITAL` (ignore as linhas que começam com `#`).

**6.2 — a entrada por GitHub (opcional, dá para deixar para depois).** O OAuth
App já existe (veja `docs/operacao/registrar-app-github.md`). Falta dizer a ele o
endereço novo:

1. Vá em <https://github.com/settings/developers> → o App do DERVS.
2. Em **Authorization callback URL**, coloque:
   `https://dervs.com.br/entrar/github/retorno`
3. Copie o **Client ID**, e gere um **Client Secret** novo.
4. De volta ao servidor, preencha as duas linhas vazias do passo 4:
   ```
   sed -i "s|^DERVS_GITHUB_ID=.*|DERVS_GITHUB_ID=COLE-O-CLIENT-ID|" /opt/dervs/.env
   ```
   e para o secret, o mesmo com `DERVS_GITHUB_SECRET`.

**Se você pular o 6.2:** o site sobe igual, só sem o botão "entrar com GitHub".

**6.3 — uma trava a mais, se você quiser (opcional).** O ambiente `producao` já
existe no repositório. Em
<https://github.com/garcia-goncalves/dervs/settings/environments> você pode
abrir `producao` e ligar **Required reviewers**, marcando você mesmo. A partir
daí toda publicação para e espera você aprovar no navegador — é um segundo
"sim", depois da palavra `PUBLICAR`. Útil no dia em que houver mais gente com
acesso ao repositório; hoje, com você sozinho, é cinto sobre suspensório.

---

## Passo 7 — Publicar (este é o passo de sempre)

**Onde:** no navegador, em
<https://github.com/garcia-goncalves/dervs/actions/workflows/publicar.yml>.

1. Clique em **Run workflow** (canto direito).
2. No campo que aparece, digite `PUBLICAR` — em maiúsculas, exatamente assim.
3. Clique no botão verde **Run workflow**.

**O que acontece, nesta ordem:** toda a suíte de testes roda duas vezes; a
imagem é montada; ela é **subida e testada** antes de sair do GitHub; só então o
servidor troca o container; o site é conferido pelo endereço de verdade; e uma
etiqueta é criada para marcar o que está no ar.

**Se der certo:** todos os passos ficam com visto verde, e
<https://dervs.com.br> abre a capa do painel.

**Se der errado:** clique no passo vermelho e leia a última linha. Os três erros
prováveis:

| O que aparece | O que aconteceu | O que fazer |
|---|---|---|
| `/opt/dervs/.env não existe` | o passo 4 não foi feito | refaça o passo 4 |
| `a imagem não ficou saudável` | o container não subiu | me chame; a causa está no código, não no servidor |
| `Permission denied (publickey)` | a chave do passo 6 está errada | refaça `VPS_CHAVE_SSH` — tem de ser a chave **privada**, o arquivo inteiro |

---

## Voltar atrás

Cada publicação cria uma etiqueta com a data e a hora. Para ver as últimas:

```
gh release list --repo garcia-goncalves/dervs --limit 5
```

Para voltar a versão anterior, **dentro do servidor**:

```
cd /opt/dervs && docker compose down && \
  sed -i "s|^DERVS_IMAGEM=.*|DERVS_IMAGEM=A-REFERENCIA-ANTERIOR|" .env && \
  docker compose up -d --wait
```

Onde `A-REFERENCIA-ANTERIOR` sai de `docker images | grep dervs`.

**O banco não é afetado por isso.** Ele mora num volume separado, fora da imagem
— é justamente para que voltar atrás no código não custe nenhuma conta, nenhum
computador pareado e nenhuma medição.

---

## Onde cada coisa mora, para consulta rápida

| Coisa | Onde |
|---|---|
| Os segredos do painel | `/opt/dervs/.env`, dentro do servidor, só leitura do dono |
| Os segredos do deploy | no GitHub, em Settings → Secrets → Actions |
| O banco | volume Docker `dervs-dados`, fora da imagem |
| A configuração do nginx | `/etc/nginx/sites-available/dervs.conf` |
| O certificado | `/etc/letsencrypt/live/dervs.com.br/` |
| O que está no ar agora | `grep DERVS_IMAGEM /opt/dervs/.env` |
