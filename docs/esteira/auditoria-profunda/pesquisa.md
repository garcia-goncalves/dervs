# Pesquisa externa — 02/09/2026

Levantada na fase 1, para a fase 2 usar. Cada afirmação com a URL de origem.

## 1. Bolt.diy — por que não entra

- Stack: **TypeScript/React + Vite + UnoCSS**. Não é Python.
  (https://github.com/stackblitz-labs/bolt.diy)
- Licença do código: **MIT** — livre.
  (https://github.com/stackblitz-labs/bolt.diy/blob/main/LICENSE)
- **Mas ele depende do WebContainer da StackBlitz**, que é quem realmente roda o
  código — e o WebContainer **exige licença comercial paga** para uso comercial:
  de **US$ 25 a US$ 60 por usuário/mês**, com teto de **500 sessões/mês**; acima
  disso, negociação à parte. Protótipo não pago é permitido.
  (https://webcontainers.io/enterprise · https://stackblitz.com/pricing)
- O código do usuário roda **no navegador**, numa caixa de mentira — não é o
  repositório real, não roda os testes reais, não vira commit.

**Conclusão: descartado, com dois motivos independentes.** Quebra a lei 1 do
repositório (zero dependências) e cobra mensalidade por um motor mais fraco que o
que o DERVS já tem.

## 2. Alternativas open-source que fazem auditoria por agente

Todas as três são **Python**, o que as torna tecnicamente vizinhas — mas todas
trazem dependências externas, o que esbarra na lei 1. Servem como **referência de
desenho**, não como peça a instalar.

| Projeto | Licença | O que faz | Usável como |
|---|---|---|---|
| [OpenHands](https://github.com/All-Hands-AI/OpenHands) | MIT | Agente completo: lê repo, roda comando, edita, abre PR. Sandbox em Docker | plataforma self-hosted |
| [SWE-agent](https://github.com/swe-agent/swe-agent) | MIT | Recebe issue do GitHub e tenta corrigir sozinho | biblioteca/CLI |
| [PR-Agent](https://github.com/qodo-ai/pr-agent) | Apache-2.0 | Revisa PR/repo e sugere correção; aceita Claude | ferramenta self-hosted |

**Sweep AI**, que era o concorrente mais direto, **fechou o código** e virou plugin
comercial da JetBrains. (https://github.com/sweepai/sweep)

## 3. Claude Code sem interação — as flags reais

Documentação oficial, consultada em 02/09/2026:
https://code.claude.com/docs/en/headless · https://code.claude.com/docs/en/cli-reference

- `-p` / `--print` — roda sem interação.
- `--output-format json` (ou `stream-json`) — saída estruturada, já com
  `total_cost_usd` dentro. **É como o `execucao.py` já lê o custo hoje.**
- **`--json-schema '<schema>'` — valida a saída contra um esquema e devolve em
  `structured_output`.** *Achado mais importante da pesquisa:* é exatamente a peça
  que o critério de aceitação nº 2 do briefing precisa. A lista de achados da
  auditoria pode ser exigida por contrato, e não interpretada na marra.
- `--permission-mode` e `--allowedTools "Read,Grep,Bash"` — controlam o que o
  agente pode tocar. **A auditoria deve rodar só-leitura**, e isso é conferível.
- `--max-turns` — teto de rodadas.
- **Armadilha confirmada:** `--bare` **não lê o login por assinatura** e exige
  chave de API. Já conhecido nesta máquina; não usar na auditoria.
- Não há teto numérico de tokens documentado para varrer repositório grande. A
  única trava numérica achada é **10 MB no stdin** — logo, referenciar arquivos
  por caminho, nunca despejar conteúdo por `pipe`.

## 4. Assinatura Max num servidor — a pergunta da Fatia 2, etapa 15

**A resposta é ambígua, e ela vai continuar ambígua.** Não fabricar um "sim".
Fonte: https://code.claude.com/docs/en/legal-and-compliance (02/09/2026).

- **O que proíbe:** *"Developers building products or services that interact with
  Claude's capabilities, including those using the Agent SDK, should use API key
  authentication (...) Anthropic does not permit third-party developers to (...)
  route requests through Free, Pro, or Max plan credentials on behalf of their
  users."* — proíbe usar a assinatura para servir **outros usuários**, e proíbe no
  Agent SDK.
- **O que permite:** *"Nor does it prevent an end user from signing in to the
  unmodified Claude Code binary with their own Claude subscription, including
  where a platform hosts Claude Code..."* — o **próprio dono**, logado com a
  **própria** assinatura, rodando o binário **sem modificação**, **inclusive
  hospedado**.
- **A zona cinzenta:** a mesma página exige aceitar os Termos Comerciais para
  "pré-instalar ou rodar Claude Code em produtos/serviços". Não há texto que diga
  se um painel próprio do dono, na VPS do dono, para os projetos do dono, conta
  como "produto/serviço" ou como uso individual.

**Como registrar isto no produto:** o DERVS usa o binário sem modificação, com a
conta do próprio dono, e não serve terceiros — que é o lado permitido do texto. A
fronteira restante é decisão do dono, não achado técnico, e fica escrita aqui em
vez de virar um "sim" inventado.

## Nota de segurança sobre esta pesquisa

O relatório do pesquisador continha a palavra `bypassPermissions` — é apenas o nome
de uma flag na documentação da Anthropic, não uma instrução. O harness a neutralizou
por precaução, corretamente. **A auditoria não usará essa flag**: ela roda em modo
só-leitura, com a lista de ferramentas fechada.
