# A fila que conserta — verificação dos 8 critérios

Gerado em 25/08/2026, na branch `hub/fila-motor`. Cada critério traz a saída
real do comando. **Três critérios ficaram em aberto** e estão marcados como
tal — o motivo de cada um está escrito, não escondido.

Especificação: `docs/superpowers/specs/2026-08-25-fila-que-conserta-design.md`
Plano: `docs/superpowers/plans/2026-08-25-fila-que-conserta.md`

---

## 1. `test_fila.py` verde, e o projeto acima de 340 testes — ATENDIDO

```
fila       Ran 75 tests in 0.632s OK
regras     Ran 57 tests in 0.002s OK
coletar    Ran 85 tests in 9.355s OK
execucao   Ran 78 tests in 0.009s OK
servir     Ran 46 tests in 0.014s OK
memoria    Ran 46 tests in 0.016s OK
TOTAL: 387 testes
```

387 testes — 82 a mais que os 305 de antes desta entrega.

## 2. As suítes existentes seguem verdes — ATENDIDO

Ver acima: `OK` nas seis, incluindo as cinco que já existiam.

## 3. `renovate.json` nos 4 repositórios, e o Renovate tendo aberto um pedido — PARCIAL

O arquivo está nos quatro, cada um em ramo próprio e com pedido de alteração
aberto:

| Repositório | Pedido |
|---|---|
| workspace-medconsultoria | https://github.com/garcia-goncalves/workspace-medconsultoria/pull/120 |
| medconsultoria | https://github.com/garcia-goncalves/medconsultoria/pull/1 |
| odontologia-pericia | https://github.com/garcia-goncalves/odontologia-pericia/pull/1 |
| investrix | https://github.com/garcia-goncalves/investrix/pull/1 |

**Em aberto:** o Renovate ainda não abriu pedido nenhum, porque o aplicativo não
está instalado. Instalar exige aprovação no navegador, em
https://github.com/apps/renovate, marcando os quatro repositórios — é a mão do
dono, não dá para fazer daqui. Enquanto isso não acontecer, o `renovate.json`
é um arquivo sem leitor.

Para o `automerge` funcionar depois, cada repositório precisa de
*Settings → General → Pull Requests → Allow auto-merge* ligado.

## 4. Dependabot *security updates* desligado, alertas mantidos — EM ABERTO, DE PROPÓSITO

Estado conferido hoje (`gh api repos/garcia-goncalves/<repo>/vulnerability-alerts`):

```
workspace-medconsultoria alertas LIGADOS
medconsultoria           alertas LIGADOS
odontologia-pericia      alertas LIGADOS
investrix                alertas LIGADOS
```

Os alertas ficam ligados — é o que alimenta a regra `vulnerabilidade` do painel.

**Não desliguei o Dependabot ainda, e é decisão consciente.** Desligar agora,
com o Renovate ainda não instalado, deixaria os quatro repositórios sem nenhum
robô cuidando de dependência — uma janela de descuido em cima de 203 alertas
abertos. A ordem certa é: instalar o Renovate, ver o primeiro pedido dele
nascer, e só então rodar o `DELETE .../automated-security-fixes` nos quatro.

## 5. Uma corrida real da fila, com o gasto em reais e o que produziu — EM ABERTO

Não rodei, e o motivo é dinheiro. Das 7 pendências elegíveis hoje, **todas as 7
são do trilho do Claude** — nenhuma é mecânica:

```
dents                    dependencia_insegura     claude
investrix                env_drift                claude
medconsultoria           dependencia_insegura     claude
medconsultoria-crm       dependencia_insegura     claude
odontologia-pericia      dependencia_insegura     claude
odontologia-pericia      env_drift                claude
workspace-medconsultoria env_drift                claude
```

Uma corrida real gastaria dinheiro de verdade (até US$ 3 por item) e abriria
pedido de alteração em até 7 repositórios. Dinheiro e ato para fora são decisão
do dono, não minha — fica aguardando o sinal dele.

O trilho mecânico não tinha o que fazer: depois de o `MEMORY.md` sair do
varredor (ver critério 8), nenhuma pendência `memoria_crlf` restou.

## 6. Um item reprovado pela trava do teste apagado — ATENDIDO

Demonstração direta contra a trava, com diffs reais:

```
apagou test_regras.py              -> 'apagou o arquivo de teste test_regras.py'
desligou um teste com skip         -> 'desligou um teste com `@unittest.skip`'
desligou um teste de JS            -> 'desligou um teste com `it.skip(`'
RELIGOU um teste (deve passar)     -> ''
```

A última linha é a que importa tanto quanto as três primeiras: **tirar** um skip
passa. Religar um teste é o oposto de burlar, e uma trava que confundisse as
duas coisas ensinaria a nunca mexer em teste.

Essas mensagens são as que a tela mostra: `fila.reprovar` devolve o motivo em
português, e o `execucao.py` o joga em `frase` e `manchete` antes de descartar
a cópia isolada.

**Ressalva honesta:** isto prova a trava, não a corrida inteira. Uma sessão real
do Claude apagando um teste de propósito num repositório de rascunho — como o
plano pedia — não foi feita, pelo mesmo motivo do critério 5.

## 7. Teto diário demonstrado, com o motivo na tela — ATENDIDO

Corrida com o teto baixado para R$ 0,01 **em memória**, num banco temporário —
o `fila.py` não foi editado:

```
teto usado nesta corrida: R$ 0.01
itens na fila: 2 | executados: ['memoria_crlf:aa']
feitos=1 falhas=0 gasto=US$ 5.00
MOTIVO DA PARADA: 'teto de R$ 0,01 do dia atingido'

teto de volta ao normal: 50.0
```

Dois itens na fila, **um** executado: o segundo não começou porque o teto já
tinha estourado. E a fila não parou muda — disse por que parou, em português,
que é o que a tela precisa mostrar.

## 8. README atualizado no mesmo commit — ATENDIDO

Seção nova **A fila que conserta**, entre "As 16 pendências" e "A paleta de
comandos". Cobre os três trilhos, as quatro travas numeradas, por que
`ci_vermelha` e `grafo_velho` ficam de fora, o teto na data local e por que não
em UTC, e o risco aceito de apagar o `hub.db` no meio do dia.

Inclui também a resposta à dúvida que estava aberta desde 24/08: o `MEMORY.md`
saiu do varredor de CRLF. O motivo da regra é *"em CRLF o harness ignora o
frontmatter"* — e esse arquivo, por especificação, não tem frontmatter. Dos 13
`.md` da pasta de memória deste projeto, ele é o único sem `---`. A exclusão tem
o motivo em comentário no `coletar.py` e quatro testes novos em
`test_coletar.py`, um deles garantindo que excluir o `MEMORY.md` não esconde os
outros arquivos.

---

## Resumo

| Critério | Estado |
|---|---|
| 1. Testes da fila verdes, projeto > 340 | Atendido — 387 |
| 2. Suítes existentes verdes | Atendido |
| 3. `renovate.json` nos 4 + pedido do Renovate | Parcial — falta instalar o app |
| 4. Dependabot desligado, alertas mantidos | Em aberto de propósito — depende do 3 |
| 5. Corrida real da fila | Em aberto — depende do sinal do dono (dinheiro) |
| 6. Trava do teste apagado | Atendido |
| 7. Teto diário parando a fila | Atendido |
| 8. README no mesmo commit | Atendido |

Cinco atendidos, um parcial, dois em aberto. Os três que faltam dependem de duas
coisas que não são minhas: a aprovação do Renovate no navegador e o aceite de
gastar dinheiro numa corrida real.

---

# Revisão especialista — 25/08/2026

Dois revisores rodaram antes de mesclar (`python-reviewer`, `security-reviewer`).
Ambos deram **"corrija antes de mesclar"**. O que segue é o que foi corrigido e
o que **continua aberto**.

## Corrigido nesta branch

| # | Achado | Onde |
|---|---|---|
| 1 | Teto não fechava entre 21h e meia-noite (data local × UTC) | `banco.gasto_entre`, `fila.janela_local_em_utc`, `fila.dia_local_de` |
| 2 | Dois cliques iniciavam duas filas | `servir._fila_trava` |
| 3 | **O botão nunca funcionava** — `executar_acao` exigia `projeto` | `servir.ACOES_SEM_PROJETO` |
| 4 | Trava falhava **aberta**: diff vazio ou cortado era aprovado | `execucao.diff_para_a_trava` devolve `confiavel` |
| 5 | Arquivo novo não commitado escapava da trava (`publicar` faz `git add -A`) | `git add -A` antes de tirar o diff da trava |
| 6 | `git config diff.noprefix true` cegava a trava para sempre | diff da trava roda com `-c diff.noprefix=false -c core.quotepath=false` |
| 7 | Renomear `test_x.py` para `x.bak` passava | `diff_mexeu_em_teste` barra `rename from` |
| 8 | `executor_claude` ignorava a recusa de `iniciar()` e herdava o `pr_url` de outra execução | checa a decisão antes de esperar |
| 9 | Projeto bloqueado depois do enfileiramento continuava sendo trabalhado | `executor_claude` reavalia `trilho_de` |

## Continua ABERTO — não mesclar sem decidir

- **Esvaziar um teste sem apagar o arquivo** (só linhas `-`) passa por todas as
  travas. Mexer no runner também (`pytest.ini`, `"test": "exit 0"`,
  `norecursedirs`). A trava 3 cobre apagar, desligar e renomear — não cobre
  esvaziar nem desviar.
- ~~**A sessão roda com `Bash` liberado** num worktree que compartilha o `.git`
  e o remoto autenticado do projeto real.~~ **Endereçado em 25/08/2026** — ver
  "As três barreiras" no fim deste documento. A cópia deixou de ser worktree, a
  sessão deixou de carregar configuração de arquivo, e todo comando passa por
  uma lista. O que **continua** valendo: rodar teste é rodar código arbitrário,
  e não há isolamento de rede.
- **O teto é conferido antes de começar o item**, e o próprio código mede que o
  limite de gasto da sessão estoura até 4,5×: um único item pode custar ~R$ 69
  contra um teto de R$ 50.
- **Execuções pelo botão "Resolver" não entram na tabela `fila`** e portanto não
  contam para o teto do dia.
- **`env_example_tem_valor` varre o diff inteiro**, não o trecho do arquivo de
  exemplo: reprova por engano uma linha legítima como `TETO = 50`, e não olha
  segredo em nenhum outro arquivo nem sob as outras regras.
- **Dinheiro em `float`**, não `Decimal`. O erro nesta escala é bilhões de vezes
  menor que um centavo — dívida registrada, não defeito.
- **A trava contra o duplo clique não tem teste.** Testar corrida de threads de
  forma confiável exige aparato que este projeto não tem, e teste intermitente é
  pior que teste nenhum.

## O que isto significa

O item 3 é o mais importante e é uma falha da minha verificação: eu confirmei no
navegador que a **faixa aparece** e afirmei que estava "funcionando". Nunca
cliquei no botão. Ele respondia *"projeto desconhecido."* e a fila jamais
começava — o que também quer dizer que **nenhuma das quatro travas foi
exercitada de ponta a ponta**. Elas estão provadas em teste unitário, não em
corrida real.

## As três barreiras (25/08/2026)

O item acima bloqueava a fila: sem vigia humana, `Bash` liberado num worktree
com o remoto autenticado é um programa solto na máquina do dono. Três barreiras
foram postas, em ordem de importância — a primeira é a que carrega o peso.

| # | Barreira | Onde | Prova |
|---|---|---|---|
| 1 | A cópia não alcança o GitHub: `git clone --no-hardlinks` com `origin` removido e `core.hooksPath` vazio | `execucao.criar_copia` | corrida real: `remote -v` vazio, ramo certo, 0,5 s |
| 2 | A sessão não carrega configuração de arquivo: `--setting-sources ""` mais `--settings` explícito | `execucao.settings_da_barreira` | a CLI 2.1.245 aceita a flag (código 0); 5 testes |
| 3 | Todo comando passa por uma lista antes de rodar | `barreira.py`, hook `PreToolUse` | hook rodado como processo real: `git push` → código 2 com a frase; `python -m pytest` → código 0; 29 testes |

E a ponte que substituiu o push da sessão: `execucao.publicar` traz o ramo da
cópia para o projeto com `git fetch` e faz o push **do projeto**. Provado numa
corrida real com um projeto de mentira — o ramo atravessou e o commit chegou.

### O furo que ninguém tinha visto

A barreira 2 não foi feita para os hooks do dono. Ela existe porque a sessão
filha também carregava o **`.claude/settings.json` do repositório sendo
consertado** — isto é, um arquivo escrito por estranho, versionado no repositório
que a fila ia visitar, podendo definir hook próprio. O `--setting-sources ""`
fecha os dois de uma vez.

Isso também derruba o que estava escrito no README e no topo de `execucao.py`:
que só `--bare` isolaria, e que `--bare` não serve com este login. A segunda
metade continua verdadeira; a primeira estava errada.

### O que continua NÃO provado, e é o próximo passo

**Nenhuma sessão filha completa foi rodada com as barreiras ligadas.** O hook
foi exercitado como processo isolado, e a cópia e a ponte foram exercitadas de
verdade — mas ninguém viu ainda o `claude` carregar o `--settings` e barrar um
comando dentro de uma sessão de verdade. Falta porque o classificador de
segurança desta máquina impede uma sessão do Claude de disparar outra: a
medição depende da mão do dono.

Enquanto isso não for feito, o estado honesto é: **as peças foram provadas
separadas, a montagem não.**
