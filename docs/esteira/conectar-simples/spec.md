# Spec — Conectar simples, entrega A

Fase 2 da esteira, escrita em 09/10/2026 a partir de um despacho com quatro lentes
(analista, arquiteto, pesquisador, diretor) sobre o `briefing.md` aprovado. A seção
`decisoes_do_portao_1` do briefing continua vencendo este documento.

## problema

Ligar o DERVS a um computador, ao GitHub e a um site exige hoje entender peças que o dono
não opera: o computador só mede se o repositório do DERVS estiver clonado e a linha de
comando levar `<CAMINHO DO DERVS>` (`conectador.py:247`, `achar_o_agente`); o GitHub pede um
botão manual "Procurar minhas contas" (`assets/painel.js:1989`); o site pede um servidor
nomeado antes do endereço (`banco.py:403`, `servidor_id NOT NULL`) e grava antes de medir
(`servir.py:1717-1762`). A tela repete "Conectar um computador" (`index.html:236` e
`painel.js:1958`), mostra "agente" (`index.html:222`, `painel.js:1945`) e o histórico de
recados do DERVS-VOZ dentro de Conectar (`index.html:276-336`). E toda aba aberta antes
de um login novo recebe 403 "token vencido" num botão qualquer, e a tela diz só "não
consegui", porque `escrever()` (`painel.js:1263-1269`) não lê status nenhum.

## solucao

Seis peças, cada uma amarrada a um critério de aceitação do briefing:

1. **Página velha (critério 6).** O servidor acrescenta `"motivo": "pagina_velha"` ao JSON
   de todo 403 por token vencido, por um helper único que substitui os 14 pontos que hoje
   escrevem a frase à mão (`servir.py:1372, 1500, 1578, 1666, 2039`… e
   `_guarda_de_escrita`, `servir.py:3561-3582`). A frase atual fica (`test_servir.py:2015`
   a cobra). Na tela, `escrever()` lê `r.clone().json()` quando o status é 403 e, se o
   motivo for página velha, abre uma faixa fixa "Esta página ficou desatualizada" com o
   botão "Recarregar" — devolvendo `r` intacto a quem chamou. Uma correção cobre as 25
   chamadas de `escrever(` do painel.
2. **O ajudante em um arquivo (critérios 1 e 2).** O botão "Conectar este computador" baixa
   um `.cmd` pequeno e legível, por `<a href>` com GET (preserva o gesto do usuário, que é o
   que o Chrome usa para não avisar). O `.cmd`:
   - baixa com `curl.exe` o Python **embutível oficial** da python.org (12 MB, versão e
     SHA-256 fixados como constante no código, conferidos com `certutil -hashfile`;
     hash diferente = recusa e apaga), sem instalar e sem administrador;
   - pede ao DERVS um pedido de pareamento (`POST /agente/pedir`, modelo RFC 8628) e abre
     `https://dervs.com.br/#/conectar?autorizar=<código curto>`; mostra o mesmo código e o
     nome da máquina na janela, para o dono conferir;
   - abre a janela de escolher pasta pelo PowerShell 5.1 (`FolderBrowserDialog`), porque o
     Python embutível não traz tkinter;
   - pergunta a cada intervalo até o dono clicar "Autorizar este computador" na tela; recebe
     o token;
   - baixa o programa de medição de `GET /agente/pacote` (acesso `maquina`, lista fechada de
     arquivos lidos do disco do servidor, a mesma regra que já vale para `conectador.py`) e
     agenda com `pythonw.exe` (sem janela piscando), caindo no plano B de 10 em 10 minutos
     quando ONLOGON exigir administrador (`conectador.py:298-315`);
   - reaproveita `~/.dervs/agente.json` quando rodado de novo, para o PC não duplicar.
   Esse computador **só mede**: o pacote não leva `execucao` (`test_imagem.PROIBIDOS`), o
   relatório diz isso, e a tela não oferece o botão de autorizar tarefas a ele.
   Enquanto espera, a tela pergunta `/api/maquinas` a cada 5 s (já existe,
   `painel.js:1577-1632`), começando na página de autorizar, e mostra "Conectado — achei N
   projetos" com nome e pasta, reaproveitando `banco.projetos_da_maquina` (`banco.py:3665`).
   A linha de comando com `<CAMINHO DO DERVS>` continua existindo dentro de "Prefiro colar
   um comando" (fechado).
3. **Mostrar no painel (critério 3).** Tabela nova `projeto_oculto (usuario_id, projeto,
   PRIMARY KEY (usuario_id, projeto))`, com migração no molde das existentes. A poda é em
   `_dados` (`servir.py:806-816`), **depois** do motor — nunca em `montar_estado`. Rota
   `POST /api/projetos/mostrar` com balcão próprio. A mesma chave aparece no cartão do
   computador e na lista do GitHub.
4. **GitHub sem botão de procurar (critério 4).** `procurarContasDoGithub`
   (`painel.js:1732`) roda sozinha quando a página volta com `?github=` e uma vez por carga
   ao abrir Conectar; o botão some. O resto já existe: `installations/new` com selo, a volta
   que confere antes de gravar (`servir.py:2052`), o link de escolher repositórios
   (`servir.py:1948-1960`) e "mede N, mediu há…" (`painel.js:2021-2024`).
5. **Site em um campo (critério 5).** Rota nova `POST /api/enderecos/medir`, que **não
   grava**, com balcão próprio, reusando a peneira qualificada (`coletar_github.url_segura`,
   `host_publico`, `mede_site`). A tela mostra "respondeu" ou o motivo e então oferece
   "Guardar" (ou "Guardar mesmo assim"). Depois de colar, pergunta de qual projeto, com o
   mais parecido já escolhido; o servidor é escolhido sozinho quando só existe um, e é
   criado como "Meus sites" quando não existe nenhum. Servidor e padrão de subdomínio vão
   para "opções avançadas", fechado.
6. **Três cartões limpos (critério 7).** Este computador, GitHub e Seus sites, cada um com
   um botão principal. "agente", "token", "Git", "linha de comando" e "instalação" saem do
   texto ao dono. O histórico do DERVS-VOZ sai de Conectar para um `<details>` fechado
   (o menu continua com quatro itens).

Por que esta forma: cada peça reusa o que já está provado no repositório (peneira, balcões,
volta do GitHub, sondagem de 5 s, `projetos_da_maquina`) e acrescenta só o que falta. A
única peça de incerteza alta é o ajudante; ela vai primeiro para que o aviso do Chrome e o
do antivírus sejam medidos cedo, com um `.cmd` de verdade servido pelo dervs.com.br.

## o_que_ja_existe

- `servir.py:1570` — `POST /api/conectador`: lê `conectador.py` do disco e injeta
  `CODIGO`/`ALVO` (`servir.py:1609`).
- `conectador.py:108` — janela de pasta por tkinter; `:247` `achar_o_agente` exige o
  repositório clonado; `:298-315` plano B de agenda sem administrador.
- `servir.py:2188` — `/agente/parear` por código de 6 dígitos (`codigo_hash` global,
  `limpar_pareamentos_vencidos`, balcão `codigos`).
- `agente/enviar.py:37-38` — a medição depende de `coletar` + `tarefas`; `coletar.py:24-25`
  puxa `banco` e `documentos` (cerca de 311 KB ao todo). `enviar.py:307` importa
  `agente.executor` sob demanda, que puxa `execucao` (proibido na imagem,
  `test_imagem.py:43`).
- `Dockerfile:63-129` — lista de cópia; `conectador.py` entra como arquivo lido
  (`Dockerfile:123`, cobrado em `test_imagem.py:133-159`).
- `assets/painel.js:1577-1632` — `esperarMaquinaNova`/`sondarMaquinaNova`, a cada 5 s.
- `banco.py:3210-3227` — `/api/maquinas` devolve só a contagem; `banco.py:3665`
  `projetos_da_maquina` tem nome e pasta.
- `banco.py:371`, `:3619-3621`, `:3656` — `projeto_conectado.arquivado_em` é zerado a cada
  relatório e não serve para "esconder".
- `servir.py:806-816` — `_dados`, onde as podas acontecem depois do motor.
- `servir.py:2031`, `:2052`, `:1948-1960`, `:1962` — instalar o GitHub App, a volta,
  o link de configurar e `TETO_DE_PROCURAS`.
- `assets/painel.js:1732`, `:1989`, `:2021-2024` — procura de contas, o botão manual e a
  linha de medição por conta.
- `servir.py:1717-1762` — `_endereco_guardar`; `coletar_github.py:122/175/306` — a peneira.
- `assets/painel.js:1263-1269` — `escrever()`; `servir.py:3561-3582` — `_guarda_de_escrita`.
- Guardas que a mudança toca: `test_conectador.py` (ASCII em `:64`, fechar sem escolher em
  `:180`, `AcharOAgente` em `:418`), `test_conectar_ponta_a_ponta.py` (`:328` reaproveita
  `agente.json`; o espaço reservado `<CAMINHO DO DERVS>`), `test_imagem.py`,
  `test_rotas.py:42` (`PROIBIDO` casa `acao`), `test_menu.py:135`,
  `test_design.py` (`>Computadores<` ~713; `texto_visivel` ~330-353), `test_voz_tela.py:59`,
  `test_github_tela.py:100-117`, `test_servir.py:2015/2219/2875`, `.github/workflows/ci.yml`.
- Documentação que passa a mentir se não mudar junto: `docs/A-APLICACAO.md:150-157` e `:650`.

## fontes_externas

Consultadas em 09/10/2026:

- https://docs.python.org/3/using/windows.html — o pacote embutível não traz Tcl/tk (sem
  tkinter) nem pip; o `._pth` ignora variáveis de ambiente e registro.
- https://www.python.org/downloads/release/python-3148/ — 3.14.8 embutível de 64 bits,
  12.0 MB, SHA-256 `a93abe456ab01bd96d7a085b3cdb6566b3063f4241360d114142fbdb07f0a310`.
  Endereço estável `https://www.python.org/ftp/python/{v}/python-{v}-embed-amd64.zip`.
- https://www.thomasmaurer.ch/2017/12/tar-and-curl-on-windows-10/ — `curl.exe` e `tar.exe`
  vêm no Windows 10 desde a build 17063.
- https://chromium.googlesource.com/chromium/src/+/main/components/safe_browsing/content/resources/download_file_types.asciipb
  e o README da mesma pasta — `.cmd` é `ALLOW_ON_USER_GESTURE`; o Chrome não avisa com gesto
  do usuário e visita anterior ao site. Ambíguo com Safe Browsing ligado: medir no ar.
- https://datatracker.ietf.org/doc/html/rfc8628 — fluxo de autorizar dispositivo:
  `authorization_pending`, `slow_down`, `expired_token`; limitar tentativas do código curto;
  confirmar que o dispositivo está com o usuário (phishing remoto, §5.4).
- https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/about-the-setup-url
  — o `installation_id` da volta não deve ser confiado; "Redirect on update" leva à volta
  quando a instalação muda.
- https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/registering-a-github-app
  — com "Request user authorization during installation" ligado, o Setup URL some: não ligar.

## fora_de_escopo

Além do que o briefing já tira:

- Avisar a tela pelo fluxo de eventos (`/api/eventos`) quando uma máquina pareia: a
  sondagem de 5 s já cumpre os 15 s do critério 2.
- Atualização automática do ajudante no computador (seria código do servidor rodando
  sozinho em todo PC — a chave mestra que a decisão 2 recusou).
- `.cmd` para ARM64, e qualquer coisa para macOS ou Linux.
- Executar tarefas num computador ligado pelo `.cmd`: ele só mede nesta entrega.
- Repositório que só existe no GitHub virar projeto no painel (exige mexer em
  `montar_estado` e no selo).
- Fica para o fim da entrega, cortável se apertar: a sugestão de endereço vinda do
  `homepageUrl` do repositório, o "o que isso faz?" com imagem por passo e o aviso de
  "ajudante desatualizado" pela versão no relatório.

## contradicoes_resolvidas

1. **"Sem exigir Python" (decisão 3) contra "programa sem Python fica fora" (fora de
   escopo).** Venceu a leitura que concilia as duas: não exigir Python **instalado**; o
   `.cmd` baixa o interpretador oficial embutível e confere o hash. Motivo: nada é
   empacotado nem assinado por nós, e o dono não instala nada. Consequência aceita: a janela
   de pasta sai do tkinter e vai para o PowerShell.
2. **Critério 1 ("sem a linha com `<CAMINHO DO DERVS>`") contra o CLAUDE.md e
   `test_conectar_ponta_a_ponta`.** A linha continua existindo, só que dentro de "Prefiro
   colar um comando", fechada. O critério 7 já permite exatamente isso.
3. **"Programa que mede" contra o braço executor.** O pacote não leva `execucao`. O
   computador ligado pelo `.cmd` mede e não executa, e a tela diz isso em vez de oferecer um
   botão que o servidor recusaria (Lei 2).
4. **Medir antes de gravar (critério 5) contra `test_servir.py:2219`** ("não medir não
   desfaz a gravação"). Rota de medir separada, que não grava; a rota atual e o teste dela
   continuam valendo.
5. **"Acompanhar" por repositório (decisão 5) contra "mostrar" por projeto (critério 3).**
   Decidido: **uma** chave só, "mostrar no painel", por projeto, que aparece igual no cartão
   do computador e na lista do GitHub. Motivo: as duas falam da mesma coisa para o dono ("isto
   aparece no meu painel?"); duas chaves exigiriam transformar repositório só do GitHub em
   projeto, o que muda o selo e é outra entrega.
6. **"Servidor em um campo" contra `servidor_id NOT NULL`.** Decidido: cola o endereço,
   mede, pergunta o projeto; o servidor é escolhido sozinho (um só) ou criado como "Meus
   sites" (nenhum); trocar servidor fica em opções avançadas. Motivo: é a leitura literal do
   critério 5, e a entrega B vai redefinir "servidor" como "onde roda o ajudante" — não vale
   amarrar a tela ao nome do provedor agora.

## duvidas_para_o_dono

nenhuma. As duas que a descoberta levantou (itens 5 e 6 acima) foram decididas pelo que o
briefing aprovado já diz; o dono pode inverter qualquer uma no próximo recado sem custo de
código jogado fora, porque o plano as isola em etapas próprias.
