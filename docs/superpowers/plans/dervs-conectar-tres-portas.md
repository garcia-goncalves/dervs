# Plano de execução — Conectar em três portas

Fase 4 da esteira, escrito em 29/08/2026. Contrato:
`docs/esteira/conectar-tres-portas/spec.md` e
`docs/esteira/conectar-tres-portas/briefing.md`, os dois aprovados. As oito
contradições já resolvidas na spec **não se reabrem aqui**. Direção visual:
`docs/esteira/dervs/design.md`, aprovada e não reaberta. Onde este plano diverge
do contrato, ou onde o contrato se contradiz, está escrito com todas as letras
na última seção.

Linha de base medida no HEAD `9f9bf8d`, branch `conectar-tres-portas`:
**1293 testes em 24 arquivos, todos verdes**. Toda etapa abaixo mantém esse
número subindo e nunca descendo.

**Já feito, não replanejar:** o buraco CGNAT da peneira anti-SSRF foi fechado em
`9f9bf8d` (`coletar_github.py:79-106` — `CGNAT`, `_ip_privado` e o desembrulho
de IPv4 mapeado, com três casos em `test_coletar.py`). Era o item 5 das
contradições resolvidas e o primeiro da execução; está fechado.

## Objetivo

A tela "Conectar projeto" deixa de avisar que falta um computador e passa a ter
três portas que conectam de verdade: **o seu computador**, **o seu servidor** e
**a sua conta do GitHub**. A porta 1 fecha a dor relatada — o primeiro minuto
numa máquina, onde `python -m agente.enviar` exige estar dentro da pasta do
repositório e o dono levou `No module named` seguido de agente três vezes. E
mata a causa mais funda: `coletar.py:47`,
`RAIZ = Path(r"C:\Users\Desktop\source\repos")` escrito no código-fonte, que faz
qualquer outra máquina medir quase nada e o painel mostrar isso como "nenhum
projeto pendente" em vez de "não olhei para lugar nenhum".

**As travas que não se tocam:**

- O servidor continua sem importar `execucao` e sem alcançar `subprocess` a
  pedido de requisição. `test_rotas.py` não é afrouxado em nenhum ponto — nada
  sai de `PROIBIDO`, `AMPUTADOS`, `EXECUTA` ou `VERBOS_PERMITIDOS`.
- O painel continua mandando o **nome** do projeto e nunca um caminho
  (`agente/enviar.py:281`, `caminho_do_projeto`). Nenhuma etapa aqui inverte
  isso.
- O agente continua sem escutar porta nenhuma.
- A peneira anti-SSRF é **reusada, não reescrita**.

## O que está FORA desta esteira

Do briefing e da spec, com destino nomeado: instalador `.exe` assinado ·
`irm | iex` como caminho recomendado · chave SSH para o servidor, agora e sempre
· descoberta de máquinas na rede · GitLab, Bitbucket e outras forjas · macOS e
Linux **verificados** no conectador (o `.py` roda nos três; só o Windows é
conferido agora) · a fusão das capacidades em Python (outra esteira).

Cortado pelo Diretor na spec, com substituto:

- **Navegar as pastas da máquina pela tela do painel.** O briefing prometeu;
  três lentes condenaram e a contradição 1 cortou. **Este plano não tem etapa
  para isso**, e é a única divergência entre briefing e spec que muda escopo —
  o critério de aceitação do briefing que fala em "o painel navega as pastas da
  máquina pelo canal de sondagem" está **revogado pela spec**, e com ele o
  risco 4 do briefing. Substituto: reabrir o conectador.
- **Vigiar duas raízes ao mesmo tempo pela interface.** A estrutura de lista
  fica (é ela que mata o caminho fixo); o que sai é a tela de gerenciar N
  pastas.
- Desconectar a conta do GitHub pela tela (desinstala-se em github.com).
- Múltiplos ambientes por projeto (staging + produção). Um endereço de produção,
  como `casos.json` já modela. Dívida nomeada, não esquecida.

Acrescentado por este plano, com motivo:

- **O conectador não vira instalador.** Ver a última seção: o agente importa
  `coletar`, que importa `banco`, que importa `tarefas` — cerca de 4.600 linhas.
  Distribuir isso pelo painel é outro produto.
- **Migrar o `hub.db` de produção reescrevendo linha.** As colunas e tabelas
  novas nascem com valor padrão; nenhuma linha existente é reescrita.

---

## Grafo de dependências

```
FATIA A — o seu computador (a dor relatada)
  A1 coletar.RAIZ vira lista, lida da configuracao      (coletar.py, test_coletar.py)
        |
  A2 conectador.py: um arquivo, biblioteca padrao       (conectador.py, test_conectador.py, ci.yml)
        |
  A3 a rota que serve o conectador                      (servir.py, Dockerfile, test_rotas, test_servir, test_imagem)
        |
  A4 a linha que roda de qualquer pasta                 (painel.js, test_conectar_ponta_a_ponta, docs/operacao)
        |
  A5 a tela das tres portas                             (index.html, painel.js, painel.css, test_design)
        |
  A6 confirmacao imediata de que a maquina apareceu     (index.html, painel.js, painel.css, test_design)
        |
  A7 verificacao da fatia A
        |
FATIA B — o seu servidor
  B1 banco: endereco de producao por projeto e por dono (banco.py, test_banco.py)
        |
  B2 a rota que aceita a URL, com a peneira reusada     (servir.py, coletar_github.py, test_servir, test_rotas)
        |
  B3 a porta 3 na tela                                  (index.html, painel.js, painel.css, test_design)
        |
  B4 verificacao da fatia B
        |
FATIA C — a sua conta do GitHub
  C1 banco: instalacao do GitHub POR USUARIO            (banco.py, test_banco.py)
        |
  C2 o fluxo de instalar, com state assinado e conferencia contra a API
                                                        (servir.py, github_app.py, coletar_github.py, testes)
        |
  C3 a porta 2 na tela                                  (index.html, painel.js, painel.css, test_design)
        |
  C4 verificacao da fatia C
```

**Os arquivos que serializam quase tudo, e é por isso que este plano tem tão
pouco paralelismo de verdade:**

- `servir.py` — A3, B2, C2.
- `assets/painel.js` + `index.html` — A4, A5, A6, B3, C3.
- `banco.py` — B1, C1.
- `.github/workflows/ci.yml` — A2, e só ela: é o único arquivo de teste novo do
  plano. Conflito de linhas adjacentes, resolve-se na mesclagem.

**Ordenação por risco:** A1 primeiro porque é ela que destrava tudo, e porque um
caminho fixo esquecido faz o painel mentir em toda máquina que não seja esta.
A3 antes de A4 porque a tela precisa da rota existir para o vigia
`ATelaSoChamaRotaQueExiste` não ficar vermelho. A fatia C por último porque mexe
em autenticação e segredo de terceiro, com a suíte já verde.

---

## A1. `coletar.RAIZ` deixa de ser esta máquina

- **objetivo** — em qualquer computador do mundo o agente medir a pasta que a
  pessoa escolheu e, quando não medir, **dizer que não mediu**. Hoje
  `coletar.py:47` traz `RAIZ = Path(r"C:\Users\Desktop\source\repos")` no
  código-fonte, consumido em `:73` (`pastas_de_projeto`) e `:904` (o aviso).
- **arquivos** — `coletar.py`, `test_coletar.py`.
- **depende_de** — nenhuma.
- **paralelizavel_com** — B1 (arquivos disjuntos), se alguém quiser adiantar a
  fatia B. **Não** com A2, que depende do contrato declarado aqui.
- **revisores** — python, security.
- **risco** — médio. `test_coletar.py` tem 165 casos e `RAIZ` é lida em três
  pontos.
- **fazer** —
  1. `RAIZES` (lista) no lugar de `RAIZ` (um `Path`). A ordem de decisão, do
     mais explícito para o último recurso:
     1. a variável de ambiente `DERVS_RAIZES`, separada por `os.pathsep`;
     2. a chave `raizes` do **arquivo de configuração do agente** — o mesmo que
        já guarda o token, apontado por `DERVS_AGENTE_ARQUIVO` ou, na falta
        dele, `~/.dervs/agente.json` (`agente/enviar.py:47`,
        `arquivo_do_token`);
     3. **último recurso:** `Path.home()` mais `source/repos`. Derivado de
        `Path.home()`, nunca escrito à mão.
  2. **`coletar.py` NÃO importa `agente`.** `agente/enviar.py:36` já faz
     `sys.path.insert(...)` e `import coletar`; importar de volta é ciclo. A
     leitura do arquivo de configuração é uma função pequena e própria aqui,
     tolerante a arquivo ausente, JSON torto e chave ausente — **cada um desses
     casos cai no próximo degrau, sem levantar**.
  3. `pastas_de_projeto()` passa a varrer **todas** as raízes, deduplicando por
     caminho em minúsculas. A dedup com `AVULSOS` já existe em `:73-77`:
     estenda, não reescreva.
  4. O aviso de `:904` passa a nomear **cada raiz que não existe**, uma por uma.
     A frase de hoje já está certa no espírito — ela diz que aquilo **não** é
     "nenhum projeto pendente" — e é a lei nº 2 em texto. Raiz que existe e está
     vazia continua sendo caso diferente de raiz que não existe.
  5. `escrever_raizes(raizes)` — a função que o conectador (A2) vai chamar para
     gravar a escolha. Ela **preserva as outras chaves do arquivo** (o token
     mora ali) e grava pelo mesmo padrão de `guardar_token`
     (`agente/enviar.py:72`): temporário com `O_EXCL` e `os.replace` por cima.
     **Não reescreva o padrão — copie-o, e diga no comentário de onde veio.**
- **como_provar** —
  - `python test_coletar.py` → `OK`, `Ran N` com N ≥ 168 (hoje 165).
  - Casos nominais: duas raízes de mentira em `tempfile`, com um projeto em cada
    → `pastas_de_projeto()` traz os dois · raiz repetida aparece **uma** vez ·
    `DERVS_RAIZES` vence o arquivo · arquivo sem a chave `raizes` cai no último
    recurso · arquivo com JSON torto cai no último recurso **sem levantar** ·
    raiz inexistente entra em `avisos` **com o nome dela**, e a medição não
    devolve "nenhum projeto pendente".
  - `escrever_raizes` não apaga o token que já estava no arquivo.
  - **A guarda contra caminho desta máquina, e ela precisa poder reprovar.** Um
    teste que lê `coletar.py` como texto e reprova casando
    `[A-Za-z]:[\/]{1,2}Users`, sem diferenciar maiúscula. **Sabote antes de
    aceitar:** aplique o mesmo padrão a uma string fabricada com o caminho
    antigo e exija que ela case. Sem isso o caso pode ser tautológico — foi o
    que aconteceu em 29/08/2026, quando dois de cinco casos novos não podiam
    reprovar.
- **armadilha** — trocar `RAIZ` por `RAIZES` e deixar `RAIZ` como apelido "para
  compatibilidade". Duas cópias divergem, e a que diverge é sempre a que ninguém
  lê. `test_coletar.py:94-96` já mexe em `coletar.RAIZ` — **esse teste tem de
  mudar junto**, e não ganhar um apelido que o mantenha verde.

## A2. `conectador.py` — um arquivo, dois cliques, e nada de lixo

- **objetivo** — o primeiro minuto sem terminal. Ele abre a janela nativa do
  sistema para escolher a pasta, pareia com o código que já veio dentro, grava a
  raiz e registra a tarefa agendada.
- **arquivos** — `conectador.py` (novo), `test_conectador.py` (novo),
  `.github/workflows/ci.yml` (passo novo).
- **depende_de** — A1 (o contrato de onde a raiz se grava).
- **paralelizavel_com** — B1.
- **revisores** — python, security.
- **risco** — alto. É um programa novo que roda **fora** do servidor, na máquina
  de quem baixa, e mexe com `subprocess` e com o agendador do Windows.
- **fazer** —
  1. **Um arquivo, biblioteca padrão pura.** Nenhum `import` fora da padrão, e
     nenhum `import` de módulo deste repositório — ele roda numa máquina onde o
     repositório pode não estar.
  2. A pasta: `tkinter.filedialog.askdirectory`, sugerindo
     `%USERPROFILE%\source\repos` **quando ela existe**.
  3. **`import tkinter` dentro de `try`.** Builds da Microsoft Store vêm sem
     Tcl/Tk, e `tkinter` **não é instalável por pip**. No `ImportError`, ele
     **pergunta a pasta por `input()` e segue** — nunca trava. É a contradição 8
     da spec, e é também o que faz o mesmo arquivo servir uma VPS por SSH, onde
     não há janela gráfica nenhuma.
  4. O pareamento reusa o que já funciona ponta a ponta: `POST /agente/parear`
     com `codigo` e `maquina`, e o token gravado em `~/.dervs/agente.json`
     **com o mesmo cuidado de `guardar_token`** (`agente/enviar.py:72`):
     temporário `O_EXCL` com modo 600 e `os.replace` atômico. O token **nunca**
     é impresso.
  5. A tarefa agendada: `subprocess.run` com **lista de argumentos**, nunca
     `shell=True` e nunca string única — no molde de
     `["schtasks", "/Create", "/TN", "DERVS - reportar", "/TR", COMANDO, "/SC", "ONLOGON", "/F"]`.
     O valor de `/TR` carrega caminho com espaço e tem regra de aspas própria;
     ver a doc da Microsoft citada na spec. **Monte-o e teste-o como dado, não
     como texto solto.**
  6. **Fechar a janela sem escolher = não pareia e não deixa lixo.** Nem token,
     nem tarefa agendada, nem arquivo de configuração tocado. Falha fechada: sai
     dizendo o motivo, em português, com código de saída diferente de zero.
  7. **O console não fecha antes de a pessoa ler**, nem no sucesso nem no erro.
     **E aqui mora a armadilha que morde primeiro:** a mesma pausa, dentro de
     uma tarefa agendada, pendura o processo para sempre e ninguém vê. A pausa
     só acontece quando há alguém para ler — entrada e saída presentes e
     interativas — e nunca no modo que o agendador usa.
  8. **Nenhum caractere fora de ASCII no que ele imprime.** O console do Windows
     não mostra, e `test_conectar_ponta_a_ponta.py:266` já cobra isso do agente
     pelo mesmo motivo.
- **como_provar** —
  - `python test_conectador.py` → `OK`. Cobre, nominalmente:
    - **um arquivo só, biblioteca padrão só:** `ast.parse` do próprio fonte,
      reprovando todo `import` que não esteja em `sys.stdlib_module_names` e
      todo import de módulo deste repositório;
    - **os dois caminhos da pasta:** com `tkinter` disponível a janela é
      chamada; com `sys.modules["tkinter"] = None` forçando `ImportError` ele
      **cai no `input()` e termina o pareamento**, sem levantar;
    - **fechar sem escolher não deixa lixo:** com a janela devolvendo vazio,
      dublês de rede, de escrita e de `subprocess` que **estouram se forem
      chamados**, e o arquivo de configuração conferido byte a byte, igual ao
      que era antes;
    - **o comando da tarefa agendada, montado:** o argv é uma **lista**, `shell`
      não aparece nos parâmetros (ou é `False`), o primeiro elemento é
      `schtasks`, e o valor de `/TR` sobrevive a um caminho com espaço, do tipo
      `C:\Program Files`;
    - **a pausa não pendura o agendador:** com entrada não interativa, o
      programa termina sozinho.
  - `grep -c "python test_conectador.py" .github/workflows/ci.yml` → `1`. **Há
    um passo na CI que cobra essa lista** (`.github/workflows/ci.yml:70`):
    arquivo de teste novo fora dela deixa a verificação vermelha.
  - `if __name__ == "__main__":` **no fim do arquivo**, sempre. Já houve teste
    neste repositório que nunca rodou porque essa linha estava no meio.
- **armadilha** — chamar o `schtasks` ou a rede de verdade no teste. A CI roda
  em máquina sem Windows, sem agendador e sem painel: o teste ficaria vermelho
  por motivo errado. Tudo por dublê.

## A3. A rota que serve o conectador — e ela **entra** na imagem

- **objetivo** — a pessoa baixar o conectador pela tela, com o código de
  pareamento já dentro dele.
- **arquivos** — `servir.py`, `Dockerfile`, `test_rotas.py` (só acréscimo),
  `test_servir.py`, `test_imagem.py`.
- **depende_de** — A2.
- **paralelizavel_com** — B1. **Não** com B2 e C2: os três disputam `servir.py`.
- **revisores** — python, security.
- **risco** — alto. É o arquivo mais vigiado do repositório, e a rota entrega um
  arquivo que carrega um código de pareamento.
- **fazer** —
  1. **O conectador NÃO vai para `assets/`.** `ESTATICOS_OK`
     (`servir.py:126-135`) nasce de um `rglob` na subida **filtrado por
     extensão**, e `.py` está fora — o comentário ao lado já diz por quê: um
     `.py` que caísse ali por engano viraria código-fonte público. E tudo em
     `assets/` **exceto** `painel.js` e `painel.css` é servido antes da cortina
     (`ESTATICOS_COM_SESSAO`, `servir.py:2006`).
  2. Rota nomeada própria na tabela `ROTAS` (`servir.py:1939`), com handler
     próprio — **não** `Hub._estatico`, que é `super().do_GET()` e só serve o
     que está em `ESTATICOS_OK`. **Classe de acesso: `dado`**, decidida
     explicitamente, porque o arquivo carrega um código de pareamento e portanto
     exige sessão. `_despachar` (`servir.py:547`) nega por padrão, e
     `TodaRotaDeclaraAcesso` reprova rota sem classificação.
  3. **Decisão a tomar dentro desta etapa — leia antes de escrever.** Um `GET`
     que **cria estado** (o código de pareamento nasce aqui, como em
     `_maquina_parear`, `servir.py:1216`) é acionável de outro site com o cookie
     da sessão junto. O atacante não lê a resposta, mas queima códigos.
     **Recomendado: `POST`**, com a guarda comum das escritas (`Origin` em
     `ORIGENS_OK` mais o cabeçalho `X-Token` anti-CSRF, exatamente como
     `_maquina_parear`), e a tela transformando a resposta em arquivo por `Blob`
     mais `<a download>`. **Alternativa:** `GET` simples, mais fácil de baixar e
     sem proteção de CSRF; se o executor escolher esse caminho, a dívida fica
     escrita no código. **O `POST` mais `Blob` obriga a conferir a CSP de
     produção**, que é `default-src` restrito à própria origem: cinco defeitos da
     primeira publicação só existiam fora do localhost
     (`docs/esteira/dervs/verificacao.md`). A conferência é na etapa A7, contra
     `dervs.com.br`.
  4. O código de pareamento é gerado **do mesmo jeito** que `_maquina_parear`:
     `banco.novo_codigo(6)` mais `banco.abrir_pareamento(...)` dentro do laço de
     cinco tentativas que trata `sqlite3.IntegrityError` — colisão silenciada
     põe a máquina de um dentro da conta do outro.
  5. O handler **lê `conectador.py` do disco** e injeta o código e o endereço.
     `servir.py` **não importa** `conectador`: importar arrastaria `tkinter`
     para dentro do servidor e para dentro de
     `test_imagem.modulos_de_runtime()`.
  6. **`COPY conectador.py /app/` no `Dockerfile`, e o nome acrescentado à lista
     de `test_imagem.test_as_paginas_e_os_assets_entram`
     (`test_imagem.py:132`).** Isto **corrige uma premissa errada do enunciado
     desta esteira**: como o servidor **lê o arquivo** em vez de importá-lo, ele
     é invisível para `test_todo_modulo_importado_entra_na_imagem` — e uma rota
     que responde 200 aqui e quebra em produção é exatamente o modo de falha da
     etapa 16 da Fatia 1. O que **não** pode acontecer é o servidor **importar**
     o conectador; isso sim continua proibido.
- **como_provar** —
  - `python test_rotas.py` → `OK`, `Ran N` com N ≥ 25. **Nada removido** de
    `PROIBIDO`, `AMPUTADOS`, `EXECUTA` ou `VERBOS_PERMITIDOS`. Acréscimo
    nominal: a rota nova é `dado`. E `/assets/painel.js` e `/assets/painel.css`
    continuam existindo com esses nomes exatos — a trava casa por caminho
    exato, e renomear um deles a desliga em silêncio.
  - `python test_servir.py` → `OK`, no servidor de verdade
    (`test_servir.ServidorDeVerdade`, `:127`): sem sessão → `401` · com sessão →
    `200`, e o corpo traz um código de seis dígitos e o endereço do painel · o
    `Content-Type` **não** é `text/html`, para o navegador não renderizar · o
    código foi aberto para o `usuario_id` da sessão, e não para outro.
  - **O teste declara a chave do cofre ANTES de importar `banco`.** Se este
    arquivo subir servidor, ele começa declarando `DERVS_AMBIENTE` como `local`
    e `DERVS_COFRE` como a chave de teste — que não é segredo, é dado de teste —
    **antes do `import banco`**. Sem isso ele passa aqui e fica vermelho só na
    CI, porque `chave_do_cofre()` recusa inventar chave fora do ambiente local e
    o `cofre.chave` existe nesta máquina e não no runner. Custou o commit
    `45963da`. **O molde exato está em `test_conectar_ponta_a_ponta.py:44-58`;
    copie de lá.**
  - `python test_imagem.py` → `OK`, e nominalmente: `conectador.py` **está** na
    lista copiada, e `conectador` **não** está em `modulos_de_runtime()`.
  - Um teste que prova que `servir` não ganhou atributo `conectador`.
- **armadilha** — nomear a rota ou a função com algo que case
  `acao|execucao|exec|terminal|pty|shell|comando|grafo` (`test_rotas.py:41`). O
  padrão casa contra o **caminho** e contra o **nome da função**: `_conectador`
  passa, `_baixar_comando` não.

## A4. A linha que roda de qualquer pasta

- **objetivo** — matar o erro que o dono levou três vezes, colando de
  `C:\WINDOWS\system32`. É o único erro do roteiro que não vem em português,
  porque quem responde é o Python antes de o programa começar.
- **arquivos** — `assets/painel.js`, `test_conectar_ponta_a_ponta.py`,
  `docs/operacao/conectar-uma-maquina.md`.
- **depende_de** — A3.
- **paralelizavel_com** — B1.
- **revisores** — python, conteudo.
- **risco** — médio. Dois vigias amarram esta linha, e os dois vão reprovar de
  propósito antes de passar.
- **fazer** —
  1. `assets/painel.js:895-896` monta hoje a linha com `python -m`, o nome do
     módulo, `location.origin` e `d.codigo`. Ela passa a ser uma invocação **por
     caminho de arquivo**, que o Python resolve de qualquer pasta, no formato
     `python "<CAMINHO DO DERVS>\agente\enviar.py" --alvo <origem> --codigo <numero>`.
     Rodar o arquivo direto funciona porque `agente/enviar.py:36` já faz
     `sys.path.insert(0, parent.parent)` antes de `import coletar` — o pacote se
     acha sozinho, venha de onde vier.
  2. **`<CAMINHO DO DERVS>` é um espaço reservado, e é o único pedaço a trocar.**
     A tela o destaca como tal, em português, dizendo em uma frase o que é. Ver
     a última seção: não há como o painel adivinhar onde o repositório está na
     máquina de quem lê, e fingir que há seria o painel mentindo. Quem não quer
     trocar nada usa o conectador, que é o outro caminho da mesma porta.
  3. `docs/operacao/conectar-uma-maquina.md` muda **no mesmo commit**: o passo 2
     deixa de mandar abrir o terminal na pasta do DERVS, e a primeira linha da
     tabela de erros comuns — a que explica o erro em inglês do Python — sai,
     porque ele deixa de acontecer. O roteiro ganha o conectador como o caminho
     que não pede terminal nenhum.
- **como_provar** —
  - `python test_conectar_ponta_a_ponta.py` → `OK`. **Dois casos existentes
    mudam de sinal, e essa inversão é a prova:**
    - `test_rodar_de_fora_da_pasta_e_o_erro_do_python_e_nao_do_numero` (`:270`)
      hoje **exige** a mensagem de módulo não encontrado, rodando com
      `cwd=self.casa.name`. Ele passa a exigir `returncode == 0` e a frase
      `pareado com` na saída, **rodando da mesma pasta de fora**. Renomeie-o
      para o que ele passou a provar.
    - `test_a_linha_do_painel_e_a_que_o_agente_aceita` (`:184`) hoje afirma que
      os três primeiros elementos do argv são `python`, `-m` e o nome do módulo.
      Passa a afirmar a forma nova.
  - `comando_do_painel()` (`:71`) **lê a linha do `painel.js` por expressão
    regular** e levanta `AssertionError` se não achar. **Esse padrão vai deixar
    de casar** — ele muda junto, e passa a substituir o espaço reservado pelo
    caminho real do repositório (`AQUI`). **Não escreva a linha dentro do
    teste:** copiá-la cria a segunda versão do comando, que é o modo de falha
    que o `contraste.py` deste repositório já teve uma vez.
  - Um caso novo rodando de uma pasta que não é a do repositório, provando que o
    código de saída é 0 **e** que a máquina apareceu em `/api/maquinas`. Código
    de saída sozinho não basta: um programa que erra e devolve 0 passaria.
- **armadilha** — mudar a linha no `painel.js` e deixar o roteiro de
  `docs/operacao/` descrevendo a linha de ontem. Documentação que descreve o
  software de ontem mente com autoridade, e este roteiro é lido justamente por
  quem já está travado.

## A5. A tela: as três portas, e a porta 1 com os dois caminhos

- **objetivo** — a tela Conectar projeto parar de mandar o usuário para outra
  tela. Hoje `assets/painel.js:774-780` escreve na cara de quem lê que conectar
  a conta do GitHub e conectar o servidor ficaram para a fatia 2.
- **arquivos** — `index.html`, `assets/painel.js`, `assets/painel.css`,
  `test_design.py`.
- **depende_de** — A3, A4.
- **paralelizavel_com** — B1.
- **revisores** — design, conteudo.
- **risco** — médio no produto, baixo no código.
- **fazer** —
  1. `pintarConectar()` (`assets/painel.js:717`) passa a desenhar **três
     portas**. A direção visual é a Torre de Controle, já aprovada em
     `docs/esteira/dervs/design.md` — **aplicar, não escolher**. Não há portão
     visual nesta esteira.
  2. **A porta 1 mostra os DOIS caminhos, lado a lado e como iguais** — não como
     principal e plano B. É a contradição 4 da spec: o conectador serve a
     máquina de trabalho, a linha serve o servidor sem tela e quem prefere
     terminal.
  3. **A Mark-of-the-Web, dita sem dramatizar.** O SmartScreen vigia por
     extensão e `.py` **não** está na lista — a tela de proteção do Windows
     **não** aparece, e é justamente por isso que o conectador é `.py`
     (contradição 3). O que sobra é a Mark-of-the-Web e o comportamento do
     programa associado ao `.py`. A tela diz isso em texto claro, sem fingir que
     nada aparece e sem transformar em alarme.
  4. Cada porta mostra **conectado**, **não conectado** ou **não deu para
     conferir** — nunca um zero inventado. O selo tem quatro estados e o quarto é
     *sem dados*; zerar o que não deu para reler apaga um problema real.
  5. Todo número na tela leva carimbo, como o `haQuanto(COMPUTADORES_LIDO_EM)`
     que já existe em `:745`.
  6. **Nenhum arquivo novo em `assets/`.** A lista de estáticos nasce de uma
     leitura da pasta **na subida** (`servir.py:132`): arquivo novo só passa a
     ser servido depois de reiniciar `servir.py`, e um `.js` novo do painel
     precisaria entrar em `ESTATICOS_COM_SESSAO` por caminho exato e nos testes
     que cobram os nomes. Acrescente ao `painel.js` e ao `painel.css`.
- **como_provar** —
  - `python test_design.py` → `OK`, `Ran N` com N ≥ 23. O vigia de vocabulário
    já lê o `painel.js` (`test_design.py:337`): nada de deploy, task, issue,
    worker ou loading no texto novo.
  - `python test_servir.py` → `OK`: `ATelaSoChamaRotaQueExiste` acha a rota do
    conectador. Ela extrai o primeiro argumento de cada `fetch` de
    `assets/painel.js`, então uma rota escrita com erro de digitação reprova
    aqui em vez de falhar calada na cara do dono.
  - `python test_rotas.py` → `OK`.
  - **Conferido clicando, em 360x640**, e descrito na A7: as três portas cabem
    sem rolagem lateral, com alvo de toque de 44px. O botão vai dentro de
    `.acoes`, que é onde mora o `min-height: 44px` — solto no cartão ele fica
    com cerca de 36px, e isso já foi corrigido uma vez em `:751`.
- **armadilha** — escrever conectado para a porta 2 ou 3 antes de as fatias B e
  C existirem. Enquanto não existem, elas dizem o que são: **não conectado**,
  com o caminho para conectar desabilitado e o motivo escrito. Promessa na tela
  é a mentira que este produto existe para não contar.

## A6. A confirmação imediata de que a máquina apareceu

- **objetivo** — o terceiro dos três acertos que o Tailscale, o runner do GitHub
  Actions e o Netdata têm e o DERVS não tem: **confirmação imediata de que o
  aparelho apareceu** (contradição 6 da spec). Os outros dois — um passo só, sem
  mandar editar arquivo de configuração, e token de curta duração gerado pelo
  painel — já estão de pé.
- **arquivos** — `index.html`, `assets/painel.js`, `assets/painel.css`,
  `test_design.py`.
- **depende_de** — A5.
- **paralelizavel_com** — B1.
- **revisores** — design, conteudo, python.
- **risco** — baixo.
- **fazer** —
  1. Enquanto o código de pareamento estiver vivo e a tela aberta, o painel
     pergunta `GET /api/maquinas` de tempos em tempos e mostra, sem recarregar,
     que o computador apareceu e com quantos projetos.
  2. **Nenhuma rota nova.** `/api/maquinas` já existe, já é `dado`, e
     `carregarComputadores()` (`assets/painel.js:793`) já a consome. Reusar
     mantém `servir.py` fora desta etapa — que é o que permite a A6 rodar sem
     esperar a B2 e a C2.
  3. **Três estados, e o terceiro é de primeira classe:** apareceu · ainda não
     apareceu, com o relógio do código correndo · **não deu para conferir**,
     quando a consulta falhou. O terceiro nunca se pinta como o segundo.
  4. A sondagem **para** quando o código expira ou quando a tela sai. Não fica um
     relógio girando para sempre numa aba esquecida.
- **como_provar** —
  - `python test_design.py` → `OK`, com o vocabulário cobrindo o texto novo e
    `NenhumNumeroSemCarimbo` satisfeito: a contagem de projetos é número, e
    número nesta tela leva carimbo.
  - `python test_servir.py` → `OK`: a rota que a tela busca existe.
  - **Conferido clicando, e é a única prova que vale aqui:** gerar o número,
    parear de verdade apontando para uma segunda pasta, e ver a tela mudar **sem
    recarregar**. Já aconteceu nesta casa afirmar que a fila funcionava tendo só
    visto a faixa aparecer, com o botão nunca disparando.
- **armadilha** — dar por confirmado porque a resposta chegou. A máquina só
  apareceu quando ela tem `visto_em`: parear sem relatório deixa a tela dizendo
  que ela nunca deu notícia, e `test_conectar_ponta_a_ponta.py:229` já cobra
  essa diferença do lado do agente.

## A7. Verificação da fatia A

- **objetivo** — rodar o critério de aceitação da porta 1 inteiro, de uma vez, e
  só então dizer pronto.
- **arquivos** — `docs/esteira/conectar-tres-portas/verificacao.md` (novo).
- **depende_de** — A6.
- **paralelizavel_com** — nenhuma.
- **revisores** — conteudo.
- **risco** — baixo.
- **como_provar** — com a saída **colada**:
  1. `python test_coletar.py` → `OK`, com o caso da guarda de caminho absoluto
     nomeado, junto com a sabotagem que provou que ele reprova.
  2. `python test_conectador.py` → `OK`, com os dois caminhos do `tkinter`
     nomeados.
  3. `python test_conectar_ponta_a_ponta.py` → `OK`, com o caso que roda **de
     fora da pasta** nomeado e a saída dele colada.
  4. `python test_rotas.py`, `python test_servir.py`, `python test_imagem.py` e
     `python test_design.py` → todos `OK`.
  5. A suíte inteira, **duas corridas seguidas**, ambas verdes. Duas corridas
     pegam o teste que passa por sorte lendo banco real.
  6. `ls requirements*.txt pyproject.toml 2>/dev/null | wc -l` → `0`.
  7. **Conferido clicando, com o que foi clicado descrito:** baixar o
     conectador, dar dois cliques, apontar para uma pasta que **não** é
     `source\repos`, e ver os projetos dela aparecerem no painel. É o critério
     que só se prova assim.
  8. **Contra `dervs.com.br`, não contra o localhost:** a rota do conectador
     responde com sessão, e o download acontece sob a CSP de produção. Cinco
     defeitos da primeira publicação só existiam fora do localhost.
  9. O varredor de segredo passa.
- **armadilha** — escrever que tudo foi verificado com a saída de metade. E
  escrever no arquivo **o que os comandos NÃO provam** — foi o que salvou a
  etapa 17 da Fatia 1.

---

## B1. O banco aprende o endereço de produção por projeto

- **objetivo** — a URL do servidor deixar de ser escrita à mão no `casos.json` e
  passar a ser um dado por projeto **e por dono**.
- **arquivos** — `banco.py`, `test_banco.py`.
- **depende_de** — nenhuma. (A B2 é que depende dela.)
- **paralelizavel_com** — toda a fatia A.
- **revisores** — python, security.
- **risco** — médio. Migração em banco que já roda em produção.
- **fazer** —
  1. Uma coluna ou tabela para o endereço de produção, **com dono**: quem lê o
     endereço de um projeto é a conta que o gravou. O IDOR já foi consertado
     duas vezes neste repositório (`servir.py`, método `_estado`, achados das
     revisões de segurança das etapas 8 e 11) e não se repete aqui.
  2. `_migrar_...(con)` no molde do que já existe — `banco.py:502`
     (`_migrar_fila_semaforo`), `:573`, `:663`, `:735`: `PRAGMA table_info`,
     depois `con.execute("BEGIN IMMEDIATE")`, depois **releitura dentro da
     transação**, e `_religar_fk(con)` no fim. Chamada a partir de `migrar()`
     (`banco.py:460`), **uma função por migração**.
  3. **Nunca `executescript` aqui.** Ele dá COMMIT implícito e desmonta o
     `BEGIN IMMEDIATE`, deixando duas subidas simultâneas migrarem juntas — o
     próprio `banco.py:510` já escreve isso.
  4. Funções de leitura e escrita, com `usuario_id` obrigatório.
- **como_provar** —
  - `python test_banco.py` → `OK`, `Ran N` com N ≥ 136 (hoje 133).
  - **Siga o precedente que já existe:** `MigracaoDoBancoVelho`
    (`test_banco.py:478`). Um `hub.db` no esquema **antigo**, uma linha gravada,
    `banco.migrar` rodado **duas vezes**, e as provas: a coluna existe, a linha
    antiga sobreviveu, e o valor dela é o padrão.
  - Um teste que prova que duas contas guardam endereços diferentes para o mesmo
    nome de projeto, e que **uma não lê o da outra**.
  - Um teste que prova que a fonte de `migrar()` não contém `executescript`.
- **armadilha** — apagar o `casos.json`. Ele **continua existindo** para os
  campos narrativos (`titulo`, `resumo`, `caso`, `portas`, `containers`), e o
  cabeçalho do próprio arquivo diz isso. Só o `url_prod` muda de dono.

## B2. A rota que aceita a URL, com a peneira **reusada**

- **objetivo** — o campo de endereço do servidor, conferido pela peneira
  anti-SSRF que já existe, alimentando a coluna No ar.
- **arquivos** — `servir.py`, `coletar_github.py`, `test_servir.py`,
  `test_rotas.py` (só acréscimo), `test_coletar.py`.
- **depende_de** — A3 (mesmo arquivo), B1.
- **paralelizavel_com** — nenhuma das que tocam `servir.py`.
- **revisores** — python, security.
- **risco** — **alto.** O painel passa a buscar uma URL que o usuário digitou —
  a superfície clássica de pedir ao servidor que bata em endereço interno.
- **fazer** —
  1. **Reusar, não reescrever.** `coletar_github.url_segura` (`:109`),
     `host_publico` (`:133`), `_ip_privado` (`:92`) e `_SemRedirecionar`
     (`:143`) são funções de módulo, sem estado, chamáveis de `servir.py`. Elas
     bloqueiam redirecionamento do jeito mais forte possível: **nunca seguindo
     nenhum**. Quando essa peneira foi escrita, reescrevê-la matou o drift em
     silêncio com 926 testes verdes.
  2. `servir.py` passa a importar `coletar_github`. **Confira antes de seguir:**
     `test_rotas.EXECUTA` (`:110`) contém a palavra `coletar`, e a checagem é
     **interseção de conjunto, não expressão regular** — `coletar_github` é
     outro nome e não casa. Mas `servir.coletar` **existe** como função de
     módulo: se algum caminho alcançável a partir de uma rota citar o nome
     `coletar`, a suíte reprova. Chame sempre qualificado, no formato
     `coletar_github.url_segura`, e **nunca** com `from coletar_github import`.
  3. `coletar_github.py` **já está na imagem** (bloco dos coletores no
     `Dockerfile`): nenhuma linha nova ali. Confirme com `test_imagem.py`.
  4. Rota nova, verbo `POST`, acesso `dado`, com a guarda comum das escritas:
     `Origin` em `ORIGENS_OK` mais o cabeçalho anti-CSRF, no molde de
     `_maquina_parear` (`servir.py:1216`).
  5. **A prova de que a URL responde**, que o critério de aceitação exige, reusa
     `coletar_github.mede_site` (`:172`) — que já faz `url_segura`,
     `host_publico`, duas tentativas, teto de 8 segundos e nenhum
     redirecionamento seguido. **Ela bloqueia a thread do pedido:** ponha teto de
     tentativas por origem, com balcão próprio em `cortina.registrar_tentativa`
     (`cortina.py:181`), e **não reuse o balcão de outra coisa** — misturar
     balcões tranca a máquina legítima, e isso já aconteceu aqui.
  6. `mede_site` devolve `ok` como `None` para não deu para medir, e isso **não
     é** fora do ar — a invariante está escrita no próprio docstring dela. A
     resposta da rota carrega os três estados separados.
  7. O endereço gravado passa a alimentar `coletar_github.py:883`, onde hoje o
     `url_prod` sai do dado local. `coletar.py:883` continua entregando
     `url_prod`; ele passa a sair do banco quando existir, e do `casos.json`
     quando não. E `coletar.py:533` — a regra de deploy, que cobra workflow de
     quem tem endereço declarado — passa a enxergar o endereço novo.
- **como_provar** —
  - `python test_rotas.py` → `OK`. Acréscimo nominal: a rota nova é `dado`. Nada
    removido de `PROIBIDO`, `AMPUTADOS`, `EXECUTA` ou `VERBOS_PERMITIDOS`, e
    `NenhumaRotaAlcancaExecucao` continua verde **depois** do
    `import coletar_github`.
  - `python test_servir.py` → `OK`, no servidor de verdade, com a chave do cofre
    declarada antes de `import banco`. Cada faixa provada, uma por uma:
    `localhost` · `127.0.0.0/8` · `10/8` · `172.16/12` · `192.168/16` ·
    `169.254/16` · o endereço de loopback IPv6 · **e a faixa CGNAT
    `100.64.0.0/10`**, fechada em `9f9bf8d`. Mais: um IPv4 mapeado em IPv6 ·
    nome que resolve para endereço interno · **o redirecionamento que sai de um
    endereço público para um interno** · sem sessão → `401` · com sessão e sem
    anti-CSRF → `403` · endereço de outra conta não é legível.
  - `python test_coletar.py` → `OK`: o endereço do banco vence o do `casos.json`,
    e a ausência dos dois continua sendo silêncio, e não fora do ar.
  - `python test_imagem.py` → `OK`.
- **armadilha** — reescrever a peneira porque a do coletor tem coisa demais. Ela
  cobre **mais** do que o briefing pedia, e a parte a mais é justamente a que já
  pegou um SSRF real. Reusar é a ordem da spec.

## B3. A porta 3 na tela

- **objetivo** — o campo de endereço, com os três estados honestos.
- **arquivos** — `index.html`, `assets/painel.js`, `assets/painel.css`,
  `test_design.py`.
- **depende_de** — A6 (mesmos arquivos), B2.
- **paralelizavel_com** — nenhuma.
- **revisores** — design, conteudo.
- **risco** — baixo.
- **fazer** — a porta 3 sai de não conectado, é da fatia 2 para um campo de
  endereço por projeto, com a recusa **explicada em português** quando a peneira
  barra: endereço interno recusado é comportamento correto, e a tela diz por
  quê. Os três estados: no ar · fora do ar · **não deu para conferir**. Sem
  chave SSH em lugar nenhum, agora e sempre.
- **como_provar** —
  - `python test_design.py` → `OK`, com o vocabulário cobrindo o texto novo,
    todo número com carimbo, e o selo com os quatro sinais: cor, forma, glifo e
    rótulo escrito. Cor sozinha não é informação.
  - `python test_servir.py` → `OK`: `ATelaSoChamaRotaQueExiste` acha a rota da
    B2.
  - Clicando, em 360x640: sem rolagem lateral, alvo de toque de 44px.
- **armadilha** — pintar fora do ar quando a medição não aconteceu. O `None` é o
  quarto estado, e apagar um fora do ar real que já estava no banco é exatamente
  o cuidado que `coletar_github.py:886-893` já toma.

## B4. Verificação da fatia B

- **objetivo** — fechar a porta 3 sozinha.
- **arquivos** — `docs/esteira/conectar-tres-portas/verificacao.md`.
- **depende_de** — B3.
- **paralelizavel_com** — nenhuma.
- **revisores** — conteudo, security.
- **risco** — baixo.
- **como_provar** — com a saída colada: `python test_banco.py` ·
  `python test_servir.py`, com as faixas nomeadas uma a uma, incluindo a CGNAT e
  o redirecionamento · `python test_coletar.py` · `python test_rotas.py` ·
  `python test_design.py` · a suíte inteira duas vezes · e, **clicando**, um
  endereço real gravado para um projeto e a coluna No ar saindo dele, com o
  `casos.json` daquele projeto **sem** `url_prod`.
- **armadilha** — provar só com um endereço que funciona e concluir que está
  pronto. Prove também o caminho da recusa: um endereço interno, barrado, com a
  frase que a tela mostra.

---

## C1. O banco aprende a instalação do GitHub **por usuário**

- **objetivo** — a instalação do GitHub App deixar de ser uma configuração única
  do processo e passar a ser um dado de cada conta.
- **arquivos** — `banco.py`, `test_banco.py`.
- **depende_de** — B1 (mesmo arquivo).
- **paralelizavel_com** — toda a fatia A.
- **revisores** — python, security.
- **risco** — médio.
- **fazer** —
  1. **Tabela nova. E aqui há uma premissa do enunciado a corrigir antes de
     escrever qualquer linha:** a tabela `instalacao` de `banco.py:294` **não**
     guarda o `installation_id` do GitHub. Ela guarda a impressão digital da
     combinação da cortina, tem `CHECK (id = 1)` e não tem nada a ver com isto. O
     `installation_id` de hoje é a **variável de ambiente
     `DERVS_GITHUB_INSTALLATION_ID`** (`coletar_github.py:309`), global ao
     processo inteiro. O efeito descrito no enunciado está certo — hoje é uma
     instalação só para todo mundo —, mas o lugar não. **Não reaproveite a
     tabela `instalacao`;** crie outra, com
     `usuario_id INTEGER NOT NULL REFERENCES usuario(id) ON DELETE CASCADE` e a
     restrição de unicidade que impede uma conta ter duas.
  2. Migração no mesmo molde da B1: `PRAGMA table_info`, `BEGIN IMMEDIATE`,
     releitura dentro da transação, `_religar_fk`. **Nunca `executescript`.**
  3. Se algum valor guardado ali for segredo, ele passa por `banco.cifrar` e
     `banco.decifrar` (`:925` e `:946`) com contexto. **O `installation_id` em si
     não é segredo** — é um número público, e `docs/operacao/token-do-coletor.md`
     já o trata assim, inclusive citando um exemplo na URL de instalação.
- **como_provar** —
  - `python test_banco.py` → `OK`, `Ran N` maior que o da B1.
  - O critério do briefing ao pé da letra: **duas contas guardam instalações
    diferentes, e uma não lê a da outra.**
  - Desconectar apaga a instalação daquele usuário **e só a dele**.
  - O precedente `MigracaoDoBancoVelho` (`test_banco.py:478`) seguido: esquema
    antigo, `migrar` duas vezes, linha antiga intacta.
- **armadilha** — pôr o `installation_id` numa coluna sem dono porque hoje é um
  só. É exatamente o estado de hoje, e é o que esta fatia existe para desfazer.

## C2. O fluxo de instalar — `state` assinado **e** conferência contra a API

- **objetivo** — um botão levar à instalação do aplicativo e voltar com a conta
  ligada, sem o dono ver, copiar ou colar segredo nenhum.
- **arquivos** — `servir.py`, `github_app.py`, `coletar_github.py`,
  `test_servir.py`, `test_github_app.py`, `test_rotas.py` (só acréscimo),
  `test_coletar.py`.
- **depende_de** — B2 (mesmo arquivo), C1.
- **paralelizavel_com** — nenhuma.
- **revisores** — python, security.
- **risco** — **alto.** Caminho de autenticação e segredo de terceiro.
- **fazer** —
  1. Rota de ida e rota de volta, as duas na tabela `ROTAS`, as duas com classe
     de acesso declarada. A de ida exige sessão (`dado`); a de volta é o callback
     do GitHub e precisa aceitar quem chega de fora — declare `cortina` e
     **escreva a decisão no comentário**, no molde de `/entrar/github/retorno`
     (`servir.py:1945`), que já é `cortina` pelo mesmo motivo.
  2. **`state` assinado com o cofre.** `banco.chave_do_cofre()` (`:867`) mais
     `hmac`, carregando o `usuario_id` e um prazo curto. Na volta, confira com
     `hmac.compare_digest`.
  3. **O `installation_id` da URL NUNCA é aceito só por ter vindo na query
     string.** A própria documentação do GitHub avisa que qualquer um pode bater
     na setup URL com um `installation_id` forjado. Antes de gravar, **confira a
     instalação contra a API do GitHub** com o JWT do app: `montar_jwt`
     (`github_app.py:240`) e `chave_de_pem` (`:163`) já existem e estão
     conferidos byte a byte contra o OpenSSL. A peça nova é **uma chamada HTTP a
     mais**, reusando `_pedir_ao_github` (`:285`) e `_SemRedirecionar` (`:277`).
  4. **Nenhuma primitiva de criptografia nova.** Se em algum momento parecer que
     é preciso escrever uma, **pare**: a regra do vetor de fora manda que toda
     peça nova venha conferida contra uma testemunha externa — RFC 6979 A.2.5
     para o `p256.py`, OpenSSL byte a byte para o `github_app.py` — e isso é
     outra etapa, não um detalhe desta.
  5. **Lei nº 3, sem exceção:** toda porta deste caminho devolve `None` ou
     `False`, e nunca levanta para quem chamou tratar. É a doutrina escrita no
     topo do `github_app.py`, e um `except` esquecido em caminho de login vira
     porta aberta.
  6. **Quem cancela no meio nunca chega ao callback, e isso é NORMAL.** Não é
     erro e não é alarme: é não deu para conferir, o quarto estado. O `state`
     também se perde em variações legítimas do fluxo — a spec registra isso como
     risco conhecido, com duas discussões de comunidade citadas, e **não** como
     garantia.
  7. `coletar_github._app()` (`:333`) lê o `installation_id` do ambiente. Ele
     passa a poder vir do banco. **Mantenha a ordem de precedência que já está
     documentada no arquivo** (`:285-306`: token pronto no ambiente, depois o
     app, depois o `gh`) e escreva onde a fonte nova entra — quem definiu a
     variável de ambiente está depurando, e quer que ela valha.
  8. **Nenhum segredo em log, resposta HTTP ou mensagem de erro.** Toda mensagem
     que sai é escrita por nós, nunca repassada da exceção: `URLError` carrega a
     URL, e URL de API carrega o que o chamador pôs nela.
- **como_provar** —
  - `python test_rotas.py` → `OK`. As duas rotas novas com acesso declarado, e
    nada removido das quatro listas.
  - `python test_servir.py` → `OK`, com a chave do cofre declarada antes de
    `import banco`. Casos nominais:
    - `installation_id` na query **sem** `state` válido → **não grava nada**, e
      devolve o estado não deu para conferir;
    - `state` de outro usuário → não grava;
    - `state` vencido → não grava;
    - `state` válido **mas** a API do GitHub não confirma a instalação → **não
      grava**. Este é o caso de que a doc do GitHub avisa, e é o único que prova
      que o parâmetro da URL não é a prova;
    - `state` válido **e** API confirma → grava, e grava para **aquele** usuário;
    - a rota de ida sem sessão → `401`;
    - **falha de rede com o GitHub devolve `None`, e o processo não cai.**
  - `python test_github_app.py` → `OK`, `Ran N` ≥ 22, com a chamada nova coberta
    por dublê — **nunca** batendo no GitHub de verdade: a CI roda em máquina sem
    credencial nenhuma.
  - `python test_coletar.py` → `OK`: a ordem de precedência das fontes de token
    continua valendo.
  - O varredor de segredo passa. **Lembre da forma:** ele barra por **forma**,
    não por conteúdo — um bloco de chave privada literal e qualquer atribuição de
    token com 16 ou mais caracteres são bloqueados mesmo sendo dado de teste. Em
    `test_github_app.py` a chave de teste é guardada **sem a armadura** e
    remontada em tempo de execução, e os tokens de mentira têm menos de 16
    caracteres. **Siga esse padrão.** E o gancho de leitura barra pelo **texto do
    comando**: citar um arquivo de chave numa linha de comando é recusado mesmo
    que a leitura seja inofensiva — renomeie o temporário.
- **armadilha** — a que vai morder primeiro: gravar no callback e conferir
  depois, porque a conferência é lenta. Uma gravação que acontece antes da prova
  é a gravação de um dado forjado, e o desfazer nunca vem.

## C3. A porta 2 na tela

- **objetivo** — o botão que liga a conta, e o estado honesto de quando não deu.
- **arquivos** — `index.html`, `assets/painel.js`, `assets/painel.css`,
  `test_design.py`.
- **depende_de** — B3 (mesmos arquivos), C2.
- **paralelizavel_com** — nenhuma.
- **revisores** — design, conteudo.
- **risco** — baixo.
- **fazer** — a porta 2 sai de ficou para a fatia 2 e passa a levar à instalação
  e a voltar com a conta ligada. **Quem cancelou no meio vê não deu para
  conferir, com o caminho de tentar de novo — nunca um erro vermelho**, e nunca
  conectado. Desconectar acontece em github.com, e a tela **diz isso**, porque
  foi cortado de propósito e esconder o corte é mentir por omissão.
- **como_provar** —
  - `python test_design.py` → `OK`, com o vocabulário cobrindo o texto novo,
    número com carimbo e selo com os quatro sinais.
  - `python test_servir.py` → `OK`: a tela só chama rota que existe.
  - Clicando, em 360x640, sem rolagem lateral e com alvo de 44px.
- **armadilha** — mostrar o `installation_id` na tela como se fosse prova de
  alguma coisa. Ele é um número que qualquer um pode digitar; o que vale é o que
  a API confirmou, e é isso que a tela reflete.

## C4. Verificação da fatia C, e da esteira inteira

- **objetivo** — rodar o critério de aceitação das três portas de uma vez.
- **arquivos** — `docs/esteira/conectar-tres-portas/verificacao.md`,
  `docs/A-APLICACAO.md`, `CLAUDE.md`,
  `docs/operacao/conectar-uma-maquina.md`, `README.md`.
- **depende_de** — C3.
- **paralelizavel_com** — nenhuma.
- **revisores** — conteudo, security.
- **risco** — baixo.
- **fazer** — a documentação que **não** coube nas etapas anteriores fecha aqui:
  a fonte única (`docs/A-APLICACAO.md`, que vence os outros documentos em
  conflito), a seção de travas do `CLAUDE.md`, o `README.md`. O que mudou de
  porta, comando, variável, fluxo e tela.
- **como_provar** — com a saída colada:
  1. A suíte inteira, **duas corridas seguidas**, ambas verdes, com o total maior
     ou igual ao de partida (1293) e **nenhum arquivo de teste a menos**.
  2. `python test_banco.py`, `python test_servir.py`, `python test_rotas.py`,
     `python test_github_app.py`, `python test_design.py` e
     `python test_imagem.py` → todos `OK`.
  3. A última corrida da verificação automática no GitHub com conclusão
     `success`. **Verde nesta máquina não basta.**
  4. `ls requirements*.txt pyproject.toml 2>/dev/null | wc -l` → `0`.
  5. O varredor de segredo passa.
  6. **Clicando, e descrito:** as três portas, cada uma conectada de verdade uma
     vez, e cada uma mostrando também o estado de não deu para conferir.
  7. A tela em 360x640 sem rolagem lateral.
  8. **O que os comandos NÃO provam**, escrito no arquivo. É o que salvou a
     etapa 17 da Fatia 1.
- **armadilha** — publicar junto. **O deploy roda no GitHub, nunca daqui**, só
  por `workflow_dispatch` com a palavra PUBLICAR digitada, e o sinal é do dono.
  Lembre também que **o que está no ar é mais velho que a `main`**: antes de
  dizer que a tela mudou, confira se a etiqueta `publicado-*` mais nova cobre o
  commit em questão.

---

## Paralelização, dito de uma vez

**Rodam juntas, sem cruzar arquivo:** `A1` e `B1` — e só elas. Depois de A1,
`A2` entra em paralelo com `B1`. Depois de B1, `C1` toma o lugar dela na trilha
do banco. **Este plano tem pouco paralelismo de verdade, e isso é um fato do
código, não uma escolha:** três arquivos concentram quase toda a mudança.

**Sequencial obrigatório, e por quê:**

- `A1 → A2`: contrato. A A2 grava no formato que a A1 define.
- `A3 → B2 → C2`: os três editam `servir.py`.
- `A4 → A5 → A6 → B3 → C3`: os cinco editam `index.html` e `assets/painel.js`.
  **É o caminho crítico do plano.**
- `B1 → C1`: os dois editam `banco.py`.
- `A2 → A3`: a rota serve o arquivo que a A2 cria.
- `A3 → A4`: a tela precisa da rota existir, senão
  `ATelaSoChamaRotaQueExiste` fica vermelho.
- `B1 → B2 → B3 → B4` e `C1 → C2 → C3 → C4`: cada fatia fecha sozinha, como o
  briefing exige.

**O atrito conhecido:** `.github/workflows/ci.yml` é editado **só pela A2** — é
o único arquivo de teste novo deste plano (`test_conectador.py`). Há um passo na
CI que cobra a lista (`.github/workflows/ci.yml:70`), e arquivo de teste
esquecido **não fica vermelho, fica mudo**. Não resolva isso criando uma etapa
de CI no fim.

**Caminho crítico, em fila:** `A1 → A2 → A3 → A4 → A5 → A6 → A7 → B2 → B3 → B4
→ C2 → C3 → C4`. Treze etapas. As duas que dá para adiantar em paralelo são
`B1` e `C1`.

---

## O QUE ESTE PLANO NÃO RESOLVE

- **A máquina sem o repositório clonado continua sem reportar, e nenhuma etapa
  aqui muda isso.** É a contradição que o briefing e a spec não resolveram, e a
  mais cara do plano. O briefing nomeia o usuário-alvo como o primeiro minuto,
  numa máquina onde o DERVS ainda não existe, **sem o repositório clonado**; e a
  spec promete que o conectador registra a tarefa agendada **para continuar
  reportando**. As duas coisas não cabem juntas: `agente/enviar.py:36-39` faz
  `sys.path.insert(...)` e `import coletar`; `coletar.py:24` importa `banco`;
  `banco.py:29` importa `tarefas`. São cerca de **4.600 linhas** que precisam
  estar na máquina para que uma medição aconteça. O conectador é **um arquivo,
  biblioteca padrão pura**: ele pareia (é só HTTP), escolhe a pasta e agenda a
  tarefa — mas **o que a tarefa agendada roda tem de existir ali**.
  **Duas leituras, e elas geram planos diferentes:**
  - **Leitura 1 — recomendada, e é a que este plano executa.** O conectador e a
    linha servem a máquina que **já tem o repositório**. O conectador descobre
    ou pergunta onde ele está, grava esse caminho junto com a raiz, e a tarefa
    agendada aponta para o agente por **caminho absoluto** — que roda de
    qualquer pasta. Quando não achar o repositório, ele **pareia assim mesmo e
    diz, em português, que o relato contínuo precisa dele** — falha honesta, e
    não uma tarefa agendada que morre calada. Recomendo esta porque não inventa
    um distribuidor de código-fonte, e porque é o caso real do dono e o de uma
    VPS, onde se clona antes de rodar qualquer coisa.
  - **Leitura 2.** O conectador vira instalador: baixa `coletar.py`, `banco.py`,
    `tarefas.py` e a pasta do agente, do painel para `%USERPROFILE%\.dervs\`.
    Fecha o caso do briefing ao pé da letra, mas cria um distribuidor de código
    pelo painel, um problema de atualização que hoje não existe, e contraria o
    **arquivo ÚNICO** do critério de aceitação. **Se o dono quiser esta, a fatia
    A muda: a A2 cresce muito e nasce uma etapa nova só para servir os módulos.**
- **A linha de comando não é copiar-e-colar sem editar.** Ela roda de qualquer
  pasta — que é o critério escrito — mas carrega `<CAMINHO DO DERVS>`, porque o
  painel **não pode saber** onde o repositório está na máquina de quem lê, e
  inventar seria o painel mentindo. O caminho sem edição nenhuma é o conectador.
  Se o dono quiser a linha também sem edição, isso depende da Leitura 2.
- **A escolha entre `POST` com `Blob` e `GET` para baixar o conectador (A3) não
  está fechada.** Recomendo `POST`, porque um `GET` que cria estado é acionável
  de outro site com o cookie junto. O custo é depender de `Blob` sob a CSP de
  produção, que **este plano manda conferir contra `dervs.com.br` na A7, e não
  no localhost** — cinco defeitos da primeira publicação só existiam fora dele.
  Se a CSP recusar, o executor cai no `GET` e escreve a dívida no código.
- **O `installation_id` por usuário e o coletor não se encontram sozinhos.**
  `coletar_github._app()` roda **num processo separado**, disparado por caminho
  (a tabela `COLETORES` de `servir.py`), e hoje lê o ambiente. A C2 manda ele
  poder ler o banco, mas **com várias contas, qual instalação o coletor usa numa
  rodada?** Este plano não responde: mantém a precedência atual, em que o
  ambiente vence, e deixa a escolha por conta como dívida nomeada. Com duas
  pessoas de público isso não dói; com dez, dói.
- **`test_conectador.py` prova o comando da tarefa agendada montado, não a
  tarefa rodando.** A CI não tem Windows nem agendador. A conferência no
  relógio — a máquina voltar a reportar depois de reiniciar o Windows — é do
  roteiro de verificação, feita à mão, e o próprio briefing já a coloca ali.
  **Enquanto ninguém a fizer, sempre atualizados e sincronizados continua sendo
  promessa.**
- **macOS e Linux não são verificados.** O `.py` roda nos três, mas `schtasks` é
  do Windows: nas outras duas plataformas o conectador pareia e grava a raiz, e
  **não agenda nada**. Ele tem de dizer isso em vez de fingir que agendou.
- **O briefing e a spec discordam sobre o navegador de pastas, e este plano
  segue a spec.** O critério de aceitação do briefing que promete o painel
  navegando as pastas da máquina está **revogado** pela contradição 1, e o risco
  4 do briefing cai junto. Quem for conferir o briefing item a item na
  verificação vai achar um critério sem etapa correspondente: **é este, e é de
  propósito.**
- **A estimativa de esforço não existe.** Nenhuma etapa tem prazo, e três (A2,
  B2, C2) são visivelmente maiores que as outras. Se alguma precisar quebrar em
  duas durante a execução, o grafo aguenta — as trilhas são disjuntas por
  arquivo, e é por isso que estão desenhadas assim.
