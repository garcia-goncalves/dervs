# Verificação — esteira `alertas-por-risco`

Os sete critérios do `briefing.md`, cada um com o comando que o prova e a saída
que ele deu em 25/08/2026. Nada aqui é "deve funcionar": é o que apareceu.

---

## 1. Severidade na mesma consulta, sem ida a mais na rede

`CAMPO_VULNS` deixou de ser `first: 1 { totalCount }` e passou a pedir
`first: 100` com `dependencyScope`, `securityAdvisory.ghsaId` e
`securityVulnerability { severity, package }`. **É o mesmo campo da mesma query
GraphQL** — o número de requisições HTTP por rodada não mudou.

```
python coletar_github.py
→ ok: 15 repositorios do GitHub atualizados
```

Prova em teste: `test_coletar.AlertaTemSeveridadeNaoSoContagem.test_conta_por_severidade`.

## 2. Pacotes distintos e defeitos distintos

Gravado no banco pela coleta real:

```
investrix                  {"total": 20, "sev": {...}, "pacotes": 9,  "defeitos": 17}
medconsultoria             {"total": 93, "sev": {...}, "pacotes": 24, "defeitos": 85}
odontologia-pericia        {"total": 71, "sev": {...}, "pacotes": 13, "defeitos": 62}
workspace-medconsultoria   {"total": 19, "sev": {...}, "pacotes": 7,  "defeitos": 12}
```

**203 alertas, 53 pacotes-por-projeto, e no conjunto 32 pacotes distintos.**

Testes: `test_pacotes_distintos_e_o_tamanho_real_do_trabalho` (3 alertas do mesmo
pacote = 1 pacote, 1 defeito) e
`test_mesmo_pacote_com_avisos_diferentes_sao_defeitos_diferentes` (1 pacote, 2
defeitos).

## 3. A frase diz severidade e tamanho, não só o total

`GET /api/dados` no painel rodando, depois de reiniciado com o código novo:

```
[alta] 6 crítico(s) e 7 alto(s) entre 19 alerta(s) de segurança em workspace-medconsultoria, em 7 pacote(s).
       6 crítico · 7 alto · 3 moderado · 3 baixo · 12 defeito(s) distinto(s) · 6 em dependência de produção
[alta] 2 crítico(s) e 44 alto(s) entre 93 alerta(s) de segurança em medconsultoria, em 24 pacote(s).
[alta] 1 crítico(s) e 40 alto(s) entre 71 alerta(s) de segurança em odontologia-pericia, em 13 pacote(s).
[alta] 12 alto(s) entre 20 alerta(s) de segurança em investrix, em 9 pacote(s).
```

O critério pedia a frase do `workspace-medconsultoria` contendo `6 crítico`:
está na primeira linha. Teste:
`test_regras.AlertaOrdenadoPorRiscoNaoPorContagem.test_a_frase_diz_a_severidade_nao_so_o_total`.

**A tela não precisou mudar.** `index.html:958` já desenhava `p.detalhe`; a linha
de detalhe apareceu sozinha.

## 4. Alta só com crítico ou alto — e as duas exceções que sobem de volta

`gravidade_alerta()`:

- crítico ou alto > 0 → `alta`
- só moderado/baixo → `media` (`test_so_moderado_e_baixo_nao_e_alta`)
- **sem `sev` medido → `alta`** (`test_severidade_nao_medida_continua_alta`)
- **`amostra` → `alta`** (`test_amostra_parcial_nao_afirma_o_que_nao_mediu`)

As duas últimas são o critério 5 em forma de regra: não saber não é estar seguro.

## 5. Rodada sem severidade não apaga nem inventa

Três camadas, cada uma com teste:

| Situação | O que acontece | Teste |
|---|---|---|
| GraphQL recusa o campo inteiro | segunda consulta sem `vulns`; o valor anterior é recarregado do banco | já existia antes desta esteira |
| permissão dá `totalCount` e recusa `nodes` | devolve só `{"total": N}`, sem `sev` — a tela volta ao texto de antes | `test_sem_nodes_o_total_sobrevive_sozinho` |
| mais de 100 alertas | marca `amostra`, a frase diz *"pelo menos"*, a gravidade fica alta | `test_nodes_truncados_nao_mentem_sobre_o_total` |

Severidade que o GitHub não mandou fica **fora** da soma, nunca cai em
"moderate" por omissão: `test_severidade_desconhecida_nao_vira_baixa`.

## 6. Projeto sem alerta continua sem pendência

`test_zero_alerta_continua_sem_pendencia` — `{"total": 0}` não produz linha.
`ProjetoSaudavel.test_nao_produz_pendencia_nenhuma`, que já existia, continua
verde.

## 7. As cinco suítes verdes

```
test_coletar     Ran 81 tests   OK
test_regras      Ran 57 tests   OK
test_memoria     Ran 46 tests   OK
test_execucao    Ran 78 tests   OK
test_servir      Ran 43 tests   OK
                 -------------
                 305 testes (eram 281 antes desta esteira)
```

**Nenhuma suíte nova foi criada** — as 24 provas entraram nas suítes existentes,
como classes novas. Por isso `ci.yml` e a lista do `py_compile` **não mudam**:
os dois já nomeiam `test_coletar`, `test_regras` e `test_memoria`. Foi conferido,
não suposto.

---

## O que quebrou no caminho, e como foi consertado

Três coisas, todas encontradas rodando, nenhuma pega pelos testes que já existiam.

### O agrupador desfazia o conserto um andar acima

Com quatro projetos em alerta, `regras.agrupar()` dobrava tudo em *"4 projetos
com alertas de segurança abertos"* — **apagando na visão padrão da tela toda a
severidade recém-adicionada**. O mesmo defeito, um nível acima.

Conserto: `NAO_AGRUPAR = {"vulnerabilidade"}`. Custo medido: a tela passa de 11
para **14 linhas** com os dados reais de hoje. Testes:
`AlertaDeSegurancaNaoSeDobra` (3 provas, incluindo uma que garante que as outras
regras continuam agrupando).

Consequência: `test_memoria.test_grupo_vem_antes_de_item_menos_grave` usava
`vulnerabilidade` só como exemplo de "regra que agrupa". O que ele mede não
mudou; o fixture passou a usar `ci_vermelha`, com comentário dizendo por quê.

### A ordem da lista continuava mandando para o lugar errado

Com a frase já correta, as quatro linhas saíam `investrix` (12 altos, zero
crítico) **antes** de `workspace-medconsultoria` (6 críticos), porque o desempate
dentro da gravidade era alfabético.

Conserto: `risco_alerta()` (100 por crítico, 1 por alto, zero para
moderado/baixo) e um campo `risco` em `_p()`, usado como terceiro critério de
ordenação — **depois** da gravidade, nunca atravessando ela. Ordem antes e depois,
medida no painel:

```
antes:  investrix(12 altos) · medconsultoria · odontologia-pericia · workspace(6 críticos)
depois: workspace r=607 · medconsultoria r=244 · odontologia-pericia r=140 · investrix r=12
```

7 provas em `OMaisPerigosoVemPrimeiro`, incluindo
`test_risco_nao_atropela_a_gravidade`.

### Os acentos viraram lixo, e isso era ferramenta minha

Escrever arquivo por `heredoc do bash → sys.stdin.read()` **corrompe acento no
Windows**: o bash entrega bytes UTF-8 e o Python decodifica com a página de
código do console (cp1252). "crítico" virou `c3 83 c2 ad`, e o teste falhou com
uma mensagem que parecia de encoding do arquivo — não era, o arquivo estava certo.

Atingiu `test_regras.py` (2 linhas) e `briefing.md` (55). Reparado por
`scratchpad/repara.py`, que só mexe no trecho que volta limpo na ida e volta
cp1252→UTF-8. **A regra que fica:** conteúdo com acento vai para arquivo com a
ferramenta Write e é lido em bytes — nunca por stdin do Python.

Isso também corrigiu uma suposição do handoff anterior: **este repositório não é
todo CRLF, é misto.** `coletar_github.py`, `regras.py`, `index.html` e
`test_memoria.py` são LF; `test_coletar.py`, `test_regras.py` e `README.md` são
CRLF. A regra certa é preservar o de cada arquivo, e é o que
`scratchpad/edita.py` faz. Prova: `git diff --stat` fechou em **550 inserções e
13 remoções** em 6 arquivos, sem nenhuma linha fantasma.

---

## O que NÃO foi feito, e por quê

**As 203 dependências continuam vulneráveis.** Esta esteira fez o painel dizer a
verdade sobre elas; não corrigiu nenhuma. Cada projeto é a janela do seu próprio
repositório (Regra zero), e o conserto é trabalho de lá — provavelmente pelo
botão "Resolver". A ordem que a tela agora dá é o roteiro:

1. `workspace-medconsultoria` — 6 críticos, 7 pacotes. O menor trabalho e o maior risco.
2. `medconsultoria` — 2 críticos, 44 altos, 24 pacotes.
3. `odontologia-pericia` — 1 crítico, 40 altos, 13 pacotes, **43 em produção**.
4. `investrix` — 12 altos, nenhum crítico.

**Revisão por agente especialista não rodou.** As instruções desta sessão proibiam
despachar subagentes, então a revisão de Python e de segurança foi minha. O
`CLAUDE.md` pede revisor independente antes de mesclar; isto é uma lacuna
conhecida deste PR, não um esquecimento.
