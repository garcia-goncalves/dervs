# Briefing — conectar o GitHub fácil, com quantas contas quiser

Aprovado em: 2026-10-06

> Fase 1 da esteira. Escrito em 06/10/2026. Portão 1 aprovado pelo dono em 06/10/2026.

## pedido_original

"Quero que a aplicação seja facilitada e todas as conexões e integrações também. Por exemplo: essa parte de conectar o github pra puxar os repositórios, quero que seja bem fácil. Quero que o usuário possa conectar mais de uma conta do github como por exemplo a conta pessoal e a conta da organização. Sem frescura. Nada engessado. A aplicação pode servir para qualquer usuário..."

## entendimento

Hoje o DERVS aceita **uma** instalação do GitHub por conta (`instalacao_github` tem `UNIQUE (usuario_id)`), e o App `dervs-coletor` é privado, só instalável na organização dona. Vai passar a aceitar **várias contas do GitHub** (pessoal e organizações) por usuário do DERVS, conectadas em um clique cada, e a coleta passa a medir os repositórios de todas elas. A tela mostra cada conta conectada, quantos repositórios cada uma libera, e o que fazer quando faltam.

## usuario_alvo

Qualquer pessoa que tenha projetos no GitHub, desenvolvedora ou não (hoje o dono, depois outros). Momento: primeiro acesso ao painel, ou quando cria um repositório novo e quer vê-lo medido. Quem usa não sabe o que é "instalação de App" nem "id".

## criterio_de_aceitacao

- [ ] O App `dervs-coletor` é público, para poder ser instalado na conta pessoal e em organizações de qualquer pessoa. Prova: olhada na tela de `github.com/apps/dervs-coletor`, sem estar logado como o dono.
- [ ] Um mesmo usuário do DERVS pode ter **várias** instalações do GitHub (pessoal e organizações). Prova: python test_banco.py
- [ ] A migração do banco existente preserva a instalação que já está gravada e não perde nenhuma linha. Prova: python test_banco.py
- [ ] A coleta mede os repositórios de **todas** as instalações do usuário, cada uma com a própria credencial, e uma instalação quebrada não impede as outras. Prova: python test_coletar_por_conta.py
- [ ] Instalação de organização continua exigindo que o usuário seja ADMIN dela, e nenhum usuário consegue amarrar a instalação de outro. Prova: python test_servir.py
- [ ] Na tela, o botão "Conectar outra conta do GitHub" abre a instalação, volta ao painel sozinho e mostra a nova conta na lista, e o botão "Procurar minhas contas" liga sozinho as instalações que já existem no GitHub e são da conta. Prova: olhada na tela, conectando a conta `thi-garcia`.
- [ ] A tela lista cada conta conectada com o nome (não o número), quantos repositórios ela libera e, quando faltam repositórios, um botão que leva à configuração dela no GitHub. Prova: python test_progresso_tela.py
- [ ] Cada conta tem um link para escolher os repositórios dela no GitHub, e uma instalação quebrada não impede as outras de medir (desconectar continua sendo no GitHub, por decisão antiga). Prova: python test_coletar_por_conta.py
- [ ] No ar: `thi-garcia` e `garcia-goncalves` conectadas e o painel mede os repositórios das duas, incluindo os 6 que hoje estão fora de alcance. Prova: olhada na tela do `https://dervs.com.br`, depois da publicação.
- [ ] Nada quebra: todas as suítes de `ci.yml` continuam verdes. Prova: python test_design.py

## fora_de_escopo

- Outros provedores (GitLab, Bitbucket). Esta entrega é só GitHub.
- Conectar servidores, VPS, SSH e outras integrações: cada uma terá a própria esteira, com o mesmo princípio de "um clique".
- Escrever no GitHub (abrir PR, comentar). O App continua só de leitura.
- Rodízio de ordem entre contas na coleta.

## riscos

- **Migration** no banco do servidor (troca de `UNIQUE (usuario_id)` por `UNIQUE (usuario_id, installation_id)`): dado em produção. Mitigação: backup do volume já feito pelo deploy, migração tudo-ou-nada, teste com banco antigo.
- **Config de deploy / produção:** tornar o App público é decisão do dono (conta dele no GitHub) e o deploy é pelo VS Code.
- **Segurança:** o App público passa a ser instalável por estranhos; o `installation_id` é público e sequencial. As travas de `account.id` e `UNIQUE (installation_id)` precisam continuar valendo por instalação, e `security-reviewer` roda antes de mesclar.
- Dado de paciente e pagamento: nenhum.

## plano_de_voo

Fases 1, 2 (enxuto: um despacho com as quatro perguntas), 4, 5, 6 e 7; sem fase 3 (tela já existe, só cresce uma lista). Modelos: sonnet no planejamento e na execução, opus só na revisão de segurança da migração. Despachos previstos: cerca de 7 (1 descoberta, 1 planejador, 2 executores, 2 revisores: security e python, 1 verificador de tela). Portão 4 (risco) uma pergunta de sim ou não antes de publicar a migração.
