## pedido_original
"Quero poder conectar mais de um servidor... e fazer eles refletirem em cada projeto
(cada projeto mostra qual está no local, qual tem ou não github, qual projeto está em
qual servidor ou se não está em nenhum servidor, etc)... essas são apenas ideias. Vc
precisa melhorar minhas ideias." Em resposta a três perguntas de desenho, o dono pediu
adicionalmente varredura automática do servidor (SSH) e correção autônoma de problemas
no servidor pelo Claude Code dentro do DERVS. Essas duas partes foram recusadas nesta
entrevista — motivo em `fora_de_escopo` — e o dono aprovou a versão cortada com "Ok.
Faça tudo! Sem parar."

## entendimento
Hoje "O seu servidor" grava um endereço por projeto, solto, sem nome de servidor. O
DERVS passa a ter um cadastro de servidores nomeados (ex.: "OVH", "TineHost"), cada um
com endereço público apenas — nunca chave de acesso. Cada projeto mostra, num só lugar,
três selos independentes: computador local, GitHub, e em qual(is) servidor(es)
cadastrados ele responde (ou nenhum) — um projeto pode responder em mais de um servidor
ao mesmo tempo. Quando o dono cadastra um servidor com um padrão de subdomínio, o DERVS
tenta esse padrão contra os nomes de projeto já conhecidos antes de pedir endereço
manual.

## usuario_alvo
O dono e o André, os dois desenvolvedores donos das contas que usam o DERVS. Ambos
operam o próprio parque de projetos e conhecem os termos do painel (selo, sem dados,
etc.) — a lente DX se aplica.

## criterio_de_aceitacao
- [ ] Em "Conectar projeto", é possível cadastrar mais de um servidor (nome + endereço público), ver a lista dos já cadastrados e apagar um.
- [ ] Em cada servidor cadastrado, o dono pode gravar um endereço por projeto (como já existe hoje), e o mesmo projeto pode ter endereço gravado em mais de um servidor ao mesmo tempo.
- [ ] Cadastrar um servidor com um padrão de subdomínio (ex. `*.tinehost.com.br`) faz o DERVS testar esse padrão contra os nomes de projeto já conhecidos (do computador ou do GitHub) e preencher sozinho quando o endereço responder — sem exigir clique a mais do dono para esse caso.
- [ ] Projeto cujo domínio não segue nenhum padrão cadastrado continua aceitando endereço manual por servidor, exatamente como hoje.
- [ ] Na tela do projeto e no card do painel, os três selos aparecem separados e legíveis: computador local, GitHub, e a lista de servidores onde ele responde (ou "não está em nenhum servidor cadastrado", nunca um selo genérico fundindo os três).
- [ ] Nenhuma rota nova aceita, grava, loga ou pede senha, chave, token ou qualquer segredo de acesso a servidor — só endereço público. Teste automatizado cobre isso.
- [ ] Endereço de rede interna continua recusado nas rotas novas, do mesmo jeito que já é recusado hoje (reaproveitando `coletar_github.url_segura`/`enderecos_publicos`, nunca uma segunda peneira).
- [ ] Teste automatizado sobe dois servidores cadastrados, com o mesmo projeto respondendo nos dois, e confere que o selo lista os dois nomes.
- [ ] CI verde nos testes novos e nos já existentes, sem novo `requirements.txt` nem `pyproject.toml` (biblioteca padrão pura, como o resto do repositório).

## fora_de_escopo
- Varrer o servidor por SSH, API do provedor ou qualquer credencial para descobrir
  projetos sozinho — contraria a regra existente do produto ("nunca pedimos chave de
  acesso ao servidor, e não vamos pedir") e a recusa nunca é reversível por autorização
  do dono, porque também é regra do Claude Code em uso, não só do DERVS.
- Qualquer forma de correção automática ou acesso de escrita ao servidor (deploy,
  reiniciar processo, editar arquivo remoto) feita pelo DERVS ou pelo Claude Code que
  roda dentro dele — o caminho de correção continua sendo a fila de tarefas que já
  existe: o DERVS aponta, o dono aprova, a mudança sai por commit e publicação manual.
- Medir a saúde do servidor em si (CPU, disco, memória, containers) — só mede se o
  projeto responde no endereço público, como hoje. Fica registrado como ideia futura.
- Garantir "zero erros, zero pendência, tudo perfeito" em qualquer projeto — não é um
  comportamento verificável por teste ou tela, e por isso não entra como critério desta
  etapa.

## riscos
Migration: nova(s) tabela(s) no banco do DERVS para o cadastro de servidores e o vínculo
projeto↔servidor. Nenhum dado de paciente nem pagamento envolvido — o único dado novo é
nome de servidor e endereço público, a mesma classe de dado que já existe hoje em
"O seu servidor".

## plano_de_voo
Fases 1 a 7, com a fase 3 ligada (o painel muda: "Conectar projeto", card do projeto,
tela do projeto) mas leve — reaproveita a direção visual "Torre de Controle" já aprovada
em `docs/esteira/dervs/design.md`, sem reabrir escolha de direção.
Modo enxuto na descoberta: as quatro lentes (Analista, Arquiteto, Pesquisador, Diretor)
em um despacho só, porque o domínio é conhecido (extensão direta do mecanismo de
"O seu servidor" que já existe) e o escopo está bem cortado acima.
Modelos: Interrogador (eu, sem despacho); descoberta sonnet; design sonnet leve;
plano (neguin-planner) sonnet; execução (neguin-executor) sonnet em worktrees isoladas,
paralelas onde não conflitam no mesmo arquivo; revisão com database-reviewer,
python-reviewer, security-reviewer e design-reviewer em paralelo, verificador técnico
sonnet; cronista sonnet.
Despachos previstos: 2 (descoberta+sintetizador) + 1 (design leve) + 1 (plano) + ~4
(execução) + ~5 (revisão em paralelo) + 1 (cronista) = 14.
