# Verificação — Conectar em três portas

*Escrita em 01/09/2026, ao fim das quinze etapas do plano
`docs/superpowers/plans/dervs-conectar-tres-portas.md`.*

**Como ler este arquivo.** Cada afirmação abaixo tem a saída do comando colada,
ou a descrição do que foi clicado. A seção que mais importa é a última — **o que
estes comandos NÃO provam** —, porque foi ela que salvou a etapa 17 da Fatia 1:
uma lista de dez verificados com dois calados se lê como doze verificados.

Linha de base, medida antes de começar, no `fd5ccc0`:
**1.294 testes em 24 arquivos, todos verdes.**

---

## O que existe agora, em uma frase por porta

- **Porta 1 — o seu computador.** Dois caminhos lado a lado e como iguais: o
  **conectador** (um arquivo, dois cliques, sem terminal) e a **linha de
  comando** (que agora roda de qualquer pasta). E o painel deixou de ter o
  caminho desta máquina escrito no código-fonte.
- **Porta 2 — a sua conta do GitHub.** Um botão leva à instalação do aplicativo
  e volta com a conta ligada, sem o dono ver, copiar ou colar segredo nenhum.
- **Porta 3 — o seu servidor.** Um campo de endereço por projeto, conferido pela
  peneira anti-SSRF, alimentando a coluna No ar com medição de verdade.

---

## 1. A suíte inteira, duas corridas seguidas

```
1a: TOTAL=1449 VERMELHOS=0
2a: TOTAL=1449 VERMELHOS=0
```

**1.294 → 1.449 testes; 24 → 25 arquivos.** Nenhum arquivo de teste a menos.
Duas corridas porque uma só não pega o teste que passa por sorte lendo banco
real.

Por arquivo, os que o plano nomeia:

```
test_coletar.py                  Ran 201 tests OK
test_conectador.py               Ran  29 tests OK
test_conectar_ponta_a_ponta.py   Ran   6 tests OK
test_rotas.py                    Ran  33 tests OK
test_servir.py                   Ran 177 tests OK
test_imagem.py                   Ran  13 tests OK
test_design.py                   Ran  29 tests OK
test_banco.py                    Ran 208 tests OK
test_github_app.py               Ran  29 tests OK
```

## 2. Nenhuma dependência externa

```
$ ls requirements*.txt pyproject.toml 2>/dev/null | wc -l
0
```

## 3. O arquivo de teste novo está na CI

```
$ grep -c "python test_conectador.py" .github/workflows/ci.yml
1
$ for t in test_*.py; do grep -q "python $t" ci.yml || echo FALTOU $t; done
faltou=0
```

---

## 4. As sabotagens — cada trava foi quebrada de propósito

Este projeto já aprendeu que **guarda de acoplamento se prova sabotando**: em
29/08/2026, dois de cinco casos novos eram incapazes de reprovar. Toda trava
abaixo foi quebrada, a suíte rodada, e o arquivo restaurado.

| O que foi sabotado | Resultado |
|---|---|
| `import requests` dentro do conectador | `FAILED (failures=1)` |
| Acento numa string que o conectador imprime | `FAILED (failures=1)` |
| `if __name__ == "__main__"` movido para o meio | `FAILED (failures=1)` |
| `shell=True` no `schtasks` | `FAILED (failures=1)` |
| Gravar o token **antes** de parear | `FAILED (failures=1)` |
| Rota do conectador sem o anti-CSRF | `FAILED (failures=1)` |
| Rota do conectador virando `GET` e `aberta` | `FAILED (failures=5, errors=2)` |
| `conectador.py` fora do `Dockerfile` | `FAILED (failures=2)` |
| `servir.py` **importando** o conectador | `FAILED (failures=1)` |
| A linha do painel voltando à forma de módulo | `FAILED (failures=6)` |
| O painel inventando um caminho no lugar do espaço reservado | `FAILED (failures=6)` |
| A query da volta do GitHub **depois** do `#` | `FAILED (failures=1)` |
| `mede_site` voltando a resolver pelo nome | `FAILED (failures=1)` |
| Aceitar o nome se **algum** IP for público | `FAILED (failures=1)` |
| Conferência do certificado desligada | `FAILED (failures=1)` |
| Resolução de nome sem prazo | `FAILED (failures=1)` |
| A leitura do endereço no banco desligada | `FAILED (failures=2)` |
| O endereço da tela não entrando no `caso` | `FAILED (failures=2)` |
| Arquivo vencendo o banco (ordem invertida) | `FAILED (failures=1)` |
| A conferência de posse da instalação desligada | `FAILED (failures=3, errors=1)` |
| O teto de criação de códigos desligado | `FAILED (failures=1, errors=2)` |
| A limpeza dos códigos vencidos desligada | `FAILED (failures=1, errors=1)` |
| O `UNIQUE (installation_id)` removido | `FAILED (errors=1)` |

**Uma sabotagem passou verde e virou trabalho.** Desligar a linha que junta o
endereço gravado ao `caso` (`if False and enderecos_gravados...`) deixava a
suíte verde: os dois guardas da B2 casavam **texto com texto**, e o texto
continuava no arquivo depois da sabotagem. Foram trocados por casos que rodam
`coletar.medir()` e `coletar_github.main()` de verdade. A sabotagem foi refeita
e agora acusa.

**E uma sabotagem falhou em ser aplicada, o que também custou tempo.** A
primeira tentativa de reverter a linha do `painel.js` foi escrita num heredoc do
Bash, que **troca as barras invertidas nesta máquina** — a armadilha que o
`CLAUDE.md` deste repositório já registra. O teste ficou verde porque o arquivo
não tinha mudado. Refeita por um script gravado em disco, ela reprovou.

---

## 5. Clicando — o que só se prova assim

### Porta 1, o conectador

Baixado pela tela, aberto como processo novo, apontado para uma pasta que **não
é** `source\repos`:

```
Passo 1 de 3 - escolha a pasta onde ficam os seus projetos.
Pasta escolhida: ...\dervs-prova-cgl3a89x\meus-projetos

Passo 2 de 3 - conectando com o painel...
Conectado. Este computador ja aparece no painel.

Passo 3 de 3 - manter o relato ligado sozinho.
Nao achei o DERVS nesta maquina, entao NAO agendei nada.
O pareamento acima valeu; o que falta e o relato continuo, que
precisa dos arquivos do DERVS aqui.

codigo de saida: 0
raizes: ['...\\dervs-prova-cgl3a89x\\meus-projetos']
o token aparece na saida do programa? False
```

E os projetos daquela pasta chegaram ao painel:

```
enviado: 3 projetos -> http://localhost:4777
```

O caminho da janela gráfica foi desligado de propósito (um `tkinter` de mentira
no caminho de busca), para exercitar **o galho do teclado** — o mesmo que serve
uma VPS por SSH e os Pythons da Microsoft Store, que vêm sem Tcl/Tk.

### Porta 1, a confirmação imediata (A6)

Número gerado na tela, pareado de fora, **sem recarregar a página**:

> `[OK] conectado` — “computador-da-prova-A6” apareceu, com 3 projeto(s).
> `deu notícia agora`

### Porta 3, o servidor

Pelo formulário da própria tela, um a um:

| Endereço digitado | O que a tela respondeu |
|---|---|
| `http://192.168.0.10/` | *esse endereco aponta para dentro de uma rede privada…* |
| `http://100.64.5.5/` | a mesma frase (faixa CGNAT) |
| `http://169.254.169.254/` | a mesma frase (o metadado da nuvem) |
| `https://dervs.com.br` | **endereço guardado** → `[OK] conectado · respondeu 200 · medido agora` |

E o `casos.json` do `dervs` **não tem** `url_prod`:

```
$ python -c "import json; ..."
dervs tem url_prod no casos.json? False None
$ ... banco.enderecos_de_producao(1)
{'dervs': 'https://dervs.com.br'}
```

### Porta 2, a conta do GitHub

A ida devolve o endereço com o selo assinado:

```
{"url": "https://github.com/apps/<app>/installations/new?state=1.1788305592.3e36a8…",
 "minutos": 30}
```

A volta com um selo forjado (`state=forjado.123.abc`) redireciona para
`/?github=nao-deu#/conectar`, **não grava nada**, e a tela mostra:

> `[···] não deu para conferir` — Não deu para confirmar a instalação. Se você
> fechou a página do GitHub no meio, é isso mesmo e não é erro: é só tentar de
> novo. O DERVS só liga a conta depois que o GitHub confirma.

Sem erro vermelho, e com o caminho de tentar de novo — que é o que a etapa pedia.

### Em 360×640

Medido no navegador, com o viewport de verdade:

```
{"viewport": 345, "rolagem_horizontal": false, "estouram": [],
 "alvos_abaixo_de_44px": []}
```

As três portas cabem, nada estoura a largura, e os quatro botões mais os dois
campos têm 44px de altura.

---

## 6. As duas revisões, e o que elas acharam

Um revisor de segurança e um de Python, em paralelo, contra `main...HEAD`.
Os dois terminaram com **“corrija antes de mergear”**, e os cinco achados foram
corrigidos neste mesmo trabalho:

1. **Bloqueante — a peneira media um endereço e conectava em outro.** Três
   resoluções de DNS, e só a última decidia o destino. Corrigido fixando o IP.
2. **Provar que a instalação existe não é provar que ela é sua.** Corrigido com
   a conferência do `account.id` e o `UNIQUE (installation_id)`.
3. **O espaço dos códigos de seis dígitos nunca era limpo**, e a rota do
   conectador não tinha teto.
4. **O teto entrava depois da resolução de DNS**, que é justamente o que
   bloqueia a thread.
5. **Dois testes-guarda não podiam reprovar.**

Mais três menores: o conectador travava numa VPS com `tkinter` instalado e sem
tela; o `--alvo` da tarefa agendada ia sem aspas; e `achar_o_agente` procurava
na pasta de Downloads antes da raiz escolhida.

---

## 7. O QUE ESTES COMANDOS **NÃO** PROVAM

Esta seção é a razão de o arquivo existir.

1. **A porta 2 nunca falou com o GitHub de verdade.** Não há GitHub App
   registrado com a *setup URL* apontando para `/github/instalado`, e criá-lo
   **exige a mão do dono** em github.com. Tudo o que está provado aqui é a
   lógica, contra dublês: o selo, a recusa, a posse, o "não deu para conferir".
   **O caminho feliz ponta a ponta continua por provar**, e ele é o único que
   dirá se a *setup URL* e o `state` sobrevivem ao fluxo real. A própria spec
   registra que o `state` se perde em variações legítimas do fluxo, com duas
   discussões de comunidade citadas — como risco conhecido, e não como
   garantia.

2. **A tarefa agendada foi montada, não vista rodar.** `test_conectador.py`
   prova o argv, as aspas e o `shell=False`; a CI não tem Windows nem
   agendador. **Ninguém reiniciou o Windows para ver a máquina voltar a
   reportar.** Enquanto isso não for feito, "sempre atualizado e sincronizado"
   continua sendo promessa.

3. **macOS e Linux não foram verificados.** O `.py` roda nos três, mas
   `schtasks` é do Windows: nas outras duas plataformas o conectador pareia e
   grava a raiz, e **não agenda nada** — ele diz isso, e isso está testado; o
   que não foi testado é a plataforma.

4. **Nada disto foi publicado.** Tudo aqui foi conferido contra
   `http://localhost:4777`. **O que está no ar é mais velho que a `main`**, e a
   A7 do plano mandava conferir o download do conectador contra
   `dervs.com.br`, sob a CSP de produção — porque cinco defeitos da primeira
   publicação só existiam fora do localhost. **Isso não foi feito**, e depende
   do sinal do dono para publicar.

5. ~~**A verificação automática no GitHub ainda não rodou.**~~ **Rodou, e ficou
   VERMELHA — este item deixou de ser uma ressalva e virou um defeito
   consertado.** A linha que o painel entrega carregava `gente\enviar.py`,
   com a barra invertida do Windows; no Linux o Python responde
   `can't open file '.../dervsgente\enviar.py'`, e seis casos caíram. Foi o
   único defeito que 1.449 testes verdes nesta máquina não podiam pegar, e ele
   estava escrito nesta seção uma hora antes de acontecer.

   O conserto: **barra normal**, que o Python aceita nos três sistemas — o
   painel serve a máquina do dono (Windows) *e* o servidor (Linux), e uma linha
   que só roda num deles é uma linha errada para metade de quem lê. O teste
   ganhou a guarda (`assertNotIn("\\", argv[1])`) e passou a montar o caminho
   com `as_posix()`; `str(AQUI)` traria a barra do Windows de volta e
   reproduziria exatamente o mesmo modo de falha.

   Depois disso a suíte foi rodada **em Linux de verdade**, num
   `python:3.12-slim`: `TOTAL=1449 VERMELHOS=0`. E a verificação do GitHub
   passou (`testes  pass  49s`).

6. **Instalação de organização é recusada.** É decisão, não defeito, e está
   escrita no código: provar que alguém é membro de uma organização exige o
   fluxo de token do usuário, que é outra etapa. Quem instalar o App numa
   organização vai ver "não deu para conferir".

7. **Com várias contas, o coletor não sabe de quem é a instalação.** Ele roda
   num processo só e hoje lê a da conta local. Dívida nomeada no plano, e ela
   continua nomeada.

8. **A máquina sem o repositório clonado continua sem reportar.** É a
   contradição mais cara do plano, e nenhuma etapa a resolveu: o conectador é um
   arquivo de biblioteca padrão, e uma medição precisa de ~4.600 linhas do
   repositório na máquina. Ele pareia assim mesmo e **diz** isso — falha
   honesta, e não uma tarefa agendada que morre calada.

9. **A linha de comando não é copiar-e-colar sem editar.** Ela roda de qualquer
   pasta, que era o critério; mas carrega `<CAMINHO DO DERVS>`, porque o painel
   não pode saber onde o repositório está na máquina de quem lê. O caminho sem
   edição nenhuma é o conectador.

10. **Um teste é intermitente nesta máquina, e não é meu.**
    `test_servir.py` falha em cerca de uma corrida a cada cinco com
    `ConnectionAbortedError [WinError 10053]`, em testes diferentes a cada vez,
    inclusive em casos que existem desde antes desta esteira. É a pilha de
    soquetes do Windows abortando a conexão do próprio teste. Quatro corridas
    seguidas verdes depois de cada mudança; **mas isso é um sintoma para
    investigar, não um detalhe.**

11. **O rebinding está fechado para o caminho novo, e o dono do IP não é
    reconferido a cada tentativa.** `mede_site` resolve uma vez e reusa o IP nas
    duas tentativas — o que é o conserto. O que não existe é uma reconferência
    entre a primeira e a segunda batida; elas acontecem no mesmo segundo e usam
    o mesmo endereço já aprovado, então não há janela nova, mas está registrado.

12. **O critério do briefing sobre navegar as pastas da máquina pela tela não
    tem etapa correspondente.** Foi revogado pela contradição 1 da spec, e é de
    propósito. Quem conferir o briefing item a item vai achar um critério sem
    prova: é este.
