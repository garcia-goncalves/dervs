# Briefing — DERVS e DERVS-VOZ como um sistema só

## pedido_original

"Continue de onde você parou e faça tudo. Preciso da aplicação 100% funcionando e sem erros. Preciso que o DERVS-VOZ esteja conectado e integrado a aplicação web DERVS (você). O Dervs-Voz já está aberto em outro terminal/VSCODE. Vocês podem interagir... e quero que vcs mesmo façam tudo o que for necessário para funcionar. Preciso que a aplicação DERVS analise todos os projetos e monitore eles 24h por dia. Faça manutenção e ajustes em tudo. Desenvolva e programe/crie. Preciso que o DERVS-VOZ possa utilizar tanto o Claude Code como modelo de IA, mas tbm quero que tenha opção de usar o HERMES AGENT e o JEV. Quero que tenhamos nosso proprio terminal SSH para comandos e desenvolvimento. Precisa ser tudo bem inteligente e integrado. Quero suas melhores ideias..."

## entendimento

O DERVS web (painel, na VPS) e o DERVS-VOZ (programa de voz no computador do dono) passam a conversar por uma ponte autenticada: o VOZ mede e vigia todos os projetos sem parar, o painel mostra e enfileira os consertos, e o VOZ executa. O VOZ ganha um seletor de cérebro (Claude Code, Hermes Agent e JEV, cada um no papel que faz bem) e um terminal SSH próprio, que mora no computador do dono e nunca no painel exposto à internet.

## usuario_alvo

Dono e desenvolvedores (Thiago e André) que não operam terminal: falam com o VOZ, olham o painel de manhã, aprovam com um clique. É desenvolvedor: a lente DX vale.

## criterio_de_aceitacao

Fatia A — lado do DERVS web (esta janela):
- [ ] O painel mostra o estado da "vigília": quando cada computador pareado mediu pela última vez e se está atrasado. Um computador calado há mais que o dobro do intervalo aparece como *sem dados*, nunca como verde. Prova: teste de `regras.py` e clique no painel local.
- [ ] O painel mostra o seletor de cérebro de cada computador e o registro de qual cérebro fez cada tarefa. Prova: teste de servidor e tela.
- [ ] Uma rota nova de "recado para o VOZ" aceita só sessão do dono, enfileira no mesmo balcão próprio e nunca executa nada no servidor. Prova: teste cruzando duas contas e teste de balcão.
- [ ] Nenhuma rota nova abre terminal, shell ou SSH no servidor. Prova: `test_rotas` e `test_tarefas_nao_publicam` continuam verdes, com caso novo que procura por essas palavras.
- [ ] As suítes existentes ficam verdes e todo `test_*.py` novo entra no `ci.yml`. Prova: rodar todas.

Fatia B — lado do DERVS-VOZ (a outra janela, por recado na caixa):
- [ ] O VOZ tem um seletor de cérebro com três encaixes: `claude_code` (já existe), `hermes` e `jev`. Trocar de cérebro não muda as travas de segurança do VOZ: aprovação só por clique, caminhos protegidos, Fachada sem Motor. Prova: testes do VOZ.
- [ ] O JEV entra como **triagem rápida**, não como conversa: classifica ("é urgente?", "qual cérebro resolve?") pela API `POST https://api.typesafe.ai/v1/systemone`, com a chave em `TYPESAFE_API_KEY` fora do repositório. Sem chave, o encaixe fica desligado. Prova: teste com servidor de mentira.
- [ ] O Hermes Agent entra como cérebro alternativo atrás do mesmo contrato do Claude Code, desligado até alguém instalá-lo, e com o motivo escrito. Prova: teste do contrato com dublê.
- [ ] O terminal SSH do VOZ abre só a partir do computador do dono, usa a chave do próprio usuário (nunca guarda senha), lista o que foi digitado no registro de ações e recusa o que as travas recusam. Prova: teste do porteiro e uma sessão real num servidor de teste.
- [ ] O VOZ e o painel trocam uma mensagem de ponta a ponta: um alerta aprovado no painel chega ao VOZ, que o executa e devolve o resultado. Prova: um teste que sobe os dois lados de verdade, não dublê.

## fora_de_escopo

- Terminal, shell ou SSH dentro do painel web ou da VPS (o terminal sem senha de `vivo/` foi removido de propósito).
- Tornar o JEV um cérebro conversacional: ele só devolve valores tipados.
- Instalar o Hermes Agent no computador sem o dono ver o que ele instala e com que permissão.
- Publicar no servidor sem o "PUBLICAR" do dono, e mexer em `publicar.yml`, `Dockerfile` ou cobrança do GitHub.
- Consertar por IA alertas de segurança ou dependência insegura.
- Tocar nos projetos do André (`Nexa`, `aninha-site`) e nos cinco da TineHost.

## riscos

Produção e dinheiro: o VOZ executa comandos no computador e pode gastar o teto diário. SSH é a superfície mais sensível do sistema: precisa de aprovação por clique, registro encadeado e chave do próprio usuário. JEV e Hermes mandam dados a terceiros: nada de dado de paciente, de chave ou de caminho protegido vai para eles. Nenhuma migration prevista; se aparecer, volta ao portão de risco.

## plano_de_voo

Modo enxuto. Fase 2: um Explore lê o DERVS-VOZ (`dervs_brain.py`, `dervs_claude_code.py`, `dervs_ponte_electron.py`, `dervs_porteiro.py`) e o agente do DERVS (`agente/`). Fase 3 (design): só a tela de vigília e de cérebros, reaproveitando os tokens. Fase 4: plano por mim. Fase 5: 2 executores em worktrees para a Fatia A; a Fatia B vira recado gravado na caixa da janela do VOZ, que o executa lá. Fase 6: revisores python e security, mais clique real. Despachos previstos: cerca de 8.
