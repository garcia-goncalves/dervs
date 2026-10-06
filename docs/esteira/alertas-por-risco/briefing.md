# Briefing â€” alertas por risco, não por contagem

Aprovado em: 2026-10-06

> Fase 1 da esteira `alertas-por-risco`. Escrito em 25/08/2026 sobre os 203
> alertas baixados um a um com `gh api dependabot/alerts`, não sobre suposição.

## pedido_original

"Aja como o cérebro! Seja ultra inteligente e autônomo. Faça tudo na melhor ordem
e seguindo as melhores práticas. Quero tudo integrado e sem bugs."

Recebido logo após o handoff apontar os 203 alertas de segurança abertos como "o
achado de maior valor da análise", deliberadamente fora do escopo anterior.

## entendimento

O painel mostra uma linha por projeto: *"93 alerta(s) de segurança aberto(s) em
medconsultoria."* O número é verdadeiro e mesmo assim engana, de quatro formas
medidas nesta data:

1. **Contagem não é tamanho do trabalho.** Os 203 alertas dos quatro projetos vêm
   de **32 pacotes distintos**. A tela sugere 203 problemas independentes.
2. **A gravidade some.** `workspace-medconsultoria` tem **6 críticos** e aparece
   como o menor problema (19) ao lado de `medconsultoria` (93, dos quais 11 são
   baixos). Ordenar por contagem inverte a ordem do risco.
3. **O mesmo defeito é contado várias vezes.** Os 6 críticos de
   `workspace-medconsultoria` são **2 CVEs de `vitest`** (CVE-2025-24964 e
   CVE-2026-47429) repetidos por 3 manifestos.
4. **Não se sabe o que roda em produção.** 202 dos 203 são npm; alguns são
   ferramenta de teste, outros são o framework (`next`, 26 alertas).

Isto é a quinta forma de o painel mentir, na mesma família das quatro já
registradas na memória do projeto: número certo, leitura errada.

## usuario_alvo

**O dono, desenvolvedor único.** Momento de uso: ele bate o olho no painel e
decide em que projeto mexe hoje. Se a lista ordena por contagem, ele vai começar
pelo `medconsultoria` (93, quase tudo transitivo) e deixar para depois os 6
críticos do `workspace-medconsultoria`. O defeito custa a ordem do dia dele.

## criterio_de_aceitacao

- [ ] A coleta grava, por projeto, a contagem por severidade (`critical` / `high` / `moderate` / `low`) na **mesma consulta GraphQL de hoje**, sem chamada de rede adicional. Verificável: `traduz()` de um nó com 6 CRITICAL devolve `vulns["sev"]["critical"] == 6`.
- [ ] A coleta grava **pacotes distintos** e **defeitos distintos** (par pacote+aviso), além do total bruto.
- [ ] A frase da pendência diz severidade e tamanho real. Verificável: um projeto com 19 alertas e 6 críticos produz frase contendo `6 crítico`.
- [ ] Gravidade `alta` só quando há crítico ou alto; projeto só com moderado/baixo vira `media`. Verificável em `regras.avaliar()`.
- [ ] Rodada que **não conseguiu** ler severidade não apaga nem inventa a anterior — a mesma proteção que hoje já existe para o total.
- [ ] Projeto sem alerta nenhum continua sem pendência.
- [ ] As 5 suítes verdes; suíte nova nomeada no `ci.yml` **e** no `py_compile`.

## fora_de_escopo

**Corrigir as dependências dos quatro projetos.** Cada um é a janela do próprio
repositório (Regra zero do CLAUDE.md). Este trabalho é fazer o painel dizer a
verdade sobre eles; o conserto vem depois, provavelmente pelo botão "Resolver".

Também fora: mudar o botão "Resolver", mexer no briefing matinal, e publicar
qualquer coisa em servidor.

## riscos

**O risco principal, e a razão de este briefing existir.** O GitHub expõe
`dependencyScope` (`RUNTIME` / `DEVELOPMENT`) e a tentação óbvia é rebaixar tudo
que é `DEVELOPMENT` â€” "vitest é ferramenta de teste, não vai para produção".
**Medido: não dá.** No mesmo repositório o mesmo `vitest` volta como
`DEVELOPMENT` em um manifesto e **`RUNTIME` em outro**, porque num `package.json`
ele está declarado fora de `devDependencies`. Rebaixar por escopo esconderia um
crítico real de produção â€” exatamente o tipo de mentira que este projeto existe
para não cometer.

Decisão: o escopo é **exibido como fato**, nunca usado sozinho para rebaixar.

Risco secundário: `vulnerabilityAlerts` exige permissão de administração e já
falha às vezes; pedir `nodes` além de `totalCount` aumenta a chance de a consulta
inteira ser recusada. Mitigação: a consulta continua tendo as duas versões, e o
degrau novo (severidade) cai sozinho sem derrubar o total.

Risco de forma: este repositório é versionado em CRLF e não tem `.gitattributes`;
`write_text()` e `sed -i` produzem diff fantasma. Mitigação: gravar em bytes com
`\r\n` ou usar a ferramenta Edit, e ler `git diff --stat` antes de todo commit.

## plano_de_voo

1. **Fase 2 enxuta, um despacho.** Domínio conhecido e escopo pequeno: não abro
   quatro lentes. O que falta descobrir já foi medido acima com `gh api`.
2. **Fase 3 (design):** não roda. A mudança é de texto de uma linha já existente
   na tela, não de tela nova.
3. **Fase 4/5:** TDD direto â€” teste primeiro em `test_coletar.py` e
   `test_regras.py`, depois `coletar_github.py` e `regras.py`.
4. **Fase 6:** revisores `python` e `security` em paralelo sobre o diff.
5. **Fase 7:** README, memória, CI verde, PR.

Portões previstos: **nenhum além deste briefing**. Não há decisão de produto em
aberto (a de escopo está resolvida acima, com medição), não há escolha visual, e
não há risco de paciente, pagamento, migration nem deploy â€” o trabalho é
somente-leitura sobre a API do GitHub.
