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
