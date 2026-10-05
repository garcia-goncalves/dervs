# Briefing — O bloco "No GitHub" medindo no servidor

> Fase 1 da esteira. Escrito em 05/10/2026. Aguarda o portão 1 (aprovação do dono).

## pedido_original

> a) Bloco "No GitHub": causa achada. Conserto = coleta por conta com token de
> instalação: ENTRA PELA ESTEIRA (briefing primeiro) + security-reviewer.
> Remendo mínimo: avisar "não medi" em vez de exit 0 calado.

(Recado de handoff do dono, 04/10/2026. O remendo já está na `main`, PR #33. Este briefing é o
conserto de verdade. O dono mandou começar o briefing em 05/10/2026: "agora o briefing da
esteira para o 'No GitHub'".)

## entendimento

Em produção todo projeto mostra "No GitHub: nunca foi medido", porque o coletor
(`coletar_github.main`) só lê a conta de teste (`banco.conta_local()`), que no servidor não
tem projeto nenhum; os projetos reais estão na conta do dono. Vamos fazer o coletor medir
**cada conta que tem projetos e o GitHub App instalado**, usando o token de instalação **daquela**
conta, e gravar o resultado no estado dela. Uma conta que não deu para medir passa a dizer
"sem dados" no painel (Lei 2), nunca "nada a mostrar".

## usuario_alvo

**É desenvolvedor, e é o dono hoje.** Ele abre o painel em https://dervs.com.br para ver CI,
pedidos de alteração (PR), alertas de segurança e publicação dos próprios repositórios.
Hoje esse bloco está vazio em todos os projetos, e o vazio parece "tudo certo". A lente DX está
ligada: o motivo de uma conta não ser medida tem de aparecer em português na tela, sem ele
abrir log do servidor. Com mais contas no futuro, cada uma só pode ver o que é dela.

## criterio_de_aceitacao

1. **Ponta a ponta no servidor:** depois da publicação e de uma rodada de coleta, abrir
   https://dervs.com.br/#/painel, entrar em um projeto com remoto no GitHub e ver o bloco "No
   GitHub" com CI, PR e alertas medidos (com carimbo "há X minutos"), no lugar de "nunca foi
   medido". Prova: olhada na tela, com o projeto de nome citado na verificação.
2. **Uma conta, uma instalação:** teste novo que cria duas contas, cada uma com instalação e
   projetos próprios, roda a coleta e prova que cada conta recebeu **só** os repositórios dela e
   que o token usado em cada uma foi o da instalação dela (dublê de rede registra o token
   por chamada). Comando: `python test_coletar_por_conta.py` sai com 0.
3. **Conta sem instalação ou com instalação quebrada não fica "vazia":** teste prova que o
   estado dela marca "sem dados" com motivo (`falhas_de_coleta` por conta), nunca zero
   repositórios; e que a rodada continua para as outras contas (uma falha não derruba as demais).
4. **Falha fechada de token:** teste prova que, se o token de instalação não puder ser obtido,
   a conta fica "sem dados" e **nenhuma** chamada cai no token de outra conta nem no token do
   ambiente.
5. **Segredo não vaza:** teste prova que nenhum token aparece em saída, log, mensagem de erro
   nem no estado gravado; o varredor `secret-scan.sh` passa sem exceção.
6. **Teto de custo:** teste prova que o número de chamadas ao GitHub por rodada tem teto
   declarado (`TETO_...`), com mais de uma conta, e que estourar o teto vira "sem dados" com
   motivo, nunca silêncio.
7. **Nada quebra:** as 37 suítes existentes continuam verdes, a CI do GitHub passa, e
   `test_imagem` aceita o Dockerfile (qualquer arquivo novo entra na cópia da imagem).
8. **Revisão:** `security-reviewer` e `python-reviewer` rodam antes de mesclar e os achados
   críticos estão fechados ou justificados por escrito no `verificacao.md`.

## fora_de_escopo

- Coletar repositórios que a conta não instalou: o GitHub App só enxerga o que o dono liberou.
- Mudar o desenho do bloco "No GitHub" na tela, além do estado "sem dados com motivo".
- Trocar o token do ambiente (`VAR_TOKEN_NO_AMBIENTE`) usado em depuração local.
- Publicar na VPS: continua sendo a tarefa "Deploy para a VPS" do dono no VS Code.
- Mexer no agente local, no DERVS-VOZ ou em `/agente/voz/*`.
- Escrever em repositório do GitHub: a coleta é só leitura.
- OAuth de usuário (porta 2 do login): a instalação do App já existe e é o que se usa.

## riscos

**Config de segredo e produção:**

- **Token de instalação (segredo, ~1 hora de validade).** Fica só em memória, como
  `github_app.Coletor` já faz. Nunca em disco, log, estado ou mensagem. Uma instância por
  conta, nunca uma compartilhada: usar a de outra conta lê repositório de outra pessoa.
- **Isolamento entre contas.** O erro clássico deste projeto (achados, fila, instalação) é a
  identidade sem o dono. Toda leitura e gravação leva `usuario_id`, e o teste do critério 2
  existe por isso.
- **Cota da API do GitHub.** Mais contas multiplicam as chamadas por rodada de 20 minutos.
  Sem teto, uma conta grande bloqueia as outras, como a cota de Actions já bloqueou o CI.
- **Produção:** o conserto só funciona depois da publicação (mão do dono). Nada de dado de
  paciente, pagamento ou migration de tabela existente previstos; se a spec achar que precisa
  de coluna nova para guardar o motivo por conta, volta ao portão 4 antes de mexer no banco.

## plano_de_voo

- **Modo:** enxuto (escopo de um módulo, domínio conhecido), com revisão de segurança.
- **Fase 2 (descoberta):** 1 despacho (`neguin-planner`, Sonnet) com quatro perguntas: o que
  já existe (`banco.instalacoes_do_github`, `github_app.Coletor`, `servir._anotar_a_vida`), como
  a rodada de 20 min chama o coletor, onde mora o estado por conta, o teto de chamadas.
- **Fase 3 (design):** pulada. O único texto novo é o motivo do "sem dados", feito pelo
  Cronista com o vocabulário que já existe na tela.
- **Fase 4 (plano):** 1 despacho (`neguin-planner`, Sonnet) em etapas verificáveis.
- **Fase 5 (execução):** 1 a 2 `neguin-executor` (Sonnet) em worktree isolada. As etapas tocam
  o mesmo arquivo (`coletar_github.py`), então vão em sequência.
- **Fase 6 (revisão):** `security-reviewer` (Opus, token e isolamento de conta) e
  `python-reviewer` (Sonnet), mais o verificador técnico.
- **Portões:** 1 (este briefing). O portão de risco só dispara se a spec pedir coluna nova.
- **Número de despachos previsto:** 6 a 7.
