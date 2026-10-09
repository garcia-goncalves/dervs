# Ligar um servidor ao DERVS

*Escrito em 09/10/2026, na entrega B do "Conectar simples".*

O DERVS já sabia dos projetos do seu computador. Ligando um **servidor**, ele
passa a mostrar também **o que está rodando lá dentro** (quais sistemas, desde
quando, se reiniciaram) e **qual versão de cada projeto está no ar**, comparada
com o GitHub. Quem faz isso é um programa pequeno, o *ajudante*, que você
instala uma vez.

## O que o ajudante faz — e não faz

- **Só olha.** A cada 30 segundos ele conta ao DERVS: a lista de sistemas do
  Docker (nome, estado, desde quando, quantas vezes reiniciou), a carga, a
  memória, o disco e a última publicação bem-sucedida de cada projeto.
- **Não lê** senhas, arquivos de configuração, variáveis dos sistemas nem os
  registros de funcionamento deles. Não guarda **quem** publicou: esse dado é
  descartado na leitura.
- **Não recebe ordens** do DERVS e **não se atualiza sozinho**.
- **Roda separado**, num usuário só dele (`dervs-ajudante`), sem terminal de
  entrada. Atenção: para ver o Docker, esse usuário entra no grupo `docker`, que
  na prática equivale a administrador. Ou seja, "só olhar" é garantia do
  **código** do ajudante, não do sistema. Por isso confira o arquivo (o passo
  de conferência da linha faz isso) e só ligue servidores seus.

## Antes de começar

O servidor precisa ter: Linux com `systemd`, `python3` (3.8 ou mais novo),
Docker e acesso à internet. Você precisa poder usar `sudo` nele.

## Passo a passo

1. No painel do DERVS, abra **Conectar** e, no cartão **Seus servidores**,
   clique em **Ligar um servidor**. Aparece uma linha comprida; clique em
   **Copiar**.
2. Abra o terminal do servidor (o PuTTY ou o terminal do DERVS-VOZ) e entre
   como de costume.
3. **Cole a linha e aperte Enter.** Ela pode pedir a sua senha do servidor
   (é o `sudo`). A linha baixa o ajudante, **confere a soma de verificação**
   (SHA-256) e só então o roda.
4. Aparece no terminal um **código de 8 letras e números** (por exemplo
   `K7M4-2QXP`) e um endereço. Abra esse endereço **no seu computador**, onde
   você já entrou no DERVS. A tela mostra o nome do servidor e o código.
   **Confira que os dois são os do terminal**, clique em **Autorizar** e, se
   a tela pedir, digite o código. Se você não reconhece o pedido, **não
   clique**: ele vence sozinho em alguns minutos.
5. O terminal diz "Autorizado" e "Ligado". **Em até um minuto** o servidor
   aparece em **Seus servidores**, e os projetos que o DERVS reconhece ali
   ganham a linha "No ar em …".

## O que aparece se der certo

No terminal: "Autorizado.", "Ligado: a cada 30 segundos este servidor conta ao
painel o que roda nele." e a frase de como tirar. No painel: o nome do
servidor, "medido há N s" e a lista dos sistemas ("de pé", "parado",
"reiniciando", "com problema").

## Se der errado

| O que aparece | O que significa | O que fazer |
|---|---|---|
| `python3: command not found` | O servidor não tem Python. | Cole `sudo apt install -y python3` e rode a linha de novo. |
| `FAILED` ou `soma de verificação` | O arquivo chegou diferente do esperado. | **Não rode nada.** Recarregue a página do DERVS e copie a linha de novo. |
| "Preciso de poder de administrador" | Faltou o `sudo`. | Rode de novo com `sudo` na frente. |
| "Este servidor não usa o gerenciador de serviços…" | Não é um Linux com `systemd` (ou é um contêiner). | O ajudante não serve nessa máquina; nada foi alterado. |
| "Nao achei o Docker neste servidor" | O Docker não está instalado ou não está no caminho do `sudo`. | Instale o Docker e rode de novo. |
| "Nao consegui falar com o painel" | O servidor não alcança o DERVS. | Confira a internet do servidor e rode de novo. |
| "O painel nao liberou este servidor" | O pedido venceu ou foi recusado. | Rode a linha de novo e autorize dentro de alguns minutos. |
| O servidor aparece com **"Sem dados há N min — o servidor parou de contar."** | O ajudante parou ou perdeu a internet. | No servidor: `systemctl status dervs-ajudante.timer`. Se estiver parado, rode a linha de novo (ela não pede novo código). |
| "Não consegui ver os sistemas deste servidor." | O ajudante está vivo mas o Docker não respondeu a ele. | Confira `docker ps` no servidor e o grupo `docker` do usuário `dervs-ajudante`. |

Rodar a linha de novo é seguro: se o servidor já foi autorizado para o mesmo
endereço, ela não pede outro código.

## A versão "no ar"

O ajudante lê o histórico de publicações do kit de publicação
(`/var/log/deploy/historico.log`) e usa a última publicação **bem-sucedida** de
cada projeto. Se a última tentativa falhou **e voltou** para a versão
anterior, a versão no ar continua sendo a anterior. Se falhou **e não
conseguiu voltar**, o DERVS diz "não sei qual versão está no ar" — de
propósito: um palpite com cara de certeza seria pior. A pasta do histórico
costuma ser só do administrador; a instalação dá ao usuário do ajudante apenas
**leitura** dela (por `setfacl`), se o programa existir no servidor.

## Como tirar

No servidor, cole:

```
sudo python3 /opt/dervs-ajudante/dervs-ajudante.py remover
```

Isso desliga o temporizador, apaga os arquivos do ajudante, tira a permissão
de leitura do histórico e remove o usuário `dervs-ajudante`. **No DERVS o
servidor continua na lista, mostrando "Sem dados"** — ainda não há botão de
tirá-lo da tela. Isso é uma dívida conhecida.

## Onde as coisas ficam no servidor

| O quê | Onde |
|---|---|
| O programa | `/opt/dervs-ajudante/dervs-ajudante.py` |
| O acesso guardado (só o usuário do ajudante lê) | `/var/lib/dervs-ajudante/agente.json` |
| O serviço e o temporizador | `/etc/systemd/system/dervs-ajudante.service` e `.timer` |

## O que os testes automáticos não provam

Os testes usam um Docker e um `systemd` de mentira. **Só uma máquina de verdade
confirma**: a saída real do `docker inspect` quando um rótulo falta; se o
`ProtectSystem=strict` deixa o ajudante falar com o Docker; o Docker sem
variável `HOME` (se falhar, a correção prevista é `Environment=DOCKER_CONFIG=/var/lib/dervs-ajudante/docker`
na unidade); a hora do histórico, que é a hora **local** do servidor — fuso
diferente do esperado erra a hora, não o commit. A conferência numa máquina
virtual, depois no servidor real, é a etapa F-2 do plano
`docs/superpowers/plans/dervs-conectar-servidor-b.md`.
