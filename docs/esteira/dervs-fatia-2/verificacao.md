# Verificação da Fatia 2 — o painel ganha braços

Rodada em **29/08/2026**, no ramo `fatia-2`, a partir de `c9e424c`.
Linha de base do plano: **1095 testes em 19 arquivos** (HEAD `4988e21`).
**Agora: 1276 testes em 22 arquivos, todos verdes.**

> **Leia primeiro o que isto NÃO prova**, na última seção. Foi o que salvou a
> etapa 17 da Fatia 1: escrever "tudo verificado" com a saída de metade é o
> jeito mais fácil de um documento mentir com autoridade.

---

## Os dez critérios do briefing, na ordem, com a saída colada

### Critério 1 — o braço roda uma sessão e devolve ramo, resumo e diff

```
$ python test_executor.py
Ran 14 tests in 7.815s

OK
```

O binário `claude` **nunca é chamado** neste arquivo: um script Python de
mentira cospe o mesmo `stream-json`, linha a linha. Chamar o de verdade
gastaria cota da assinatura a cada corrida da CI, e a CI roda numa máquina sem
login nenhum — o teste ficaria vermelho pelo motivo errado.

O repositório de trabalho é de **verdade** (`git init` numa pasta temporária),
porque `execucao.criar_copia` roda `git` de verdade. O desfecho traz um ramo
começando em `hub/`.

### Critério 2 — nenhuma dependência externa

```
$ ls requirements*.txt pyproject.toml 2>/dev/null | wc -l
0
```

### Critério 3 — o semáforo existe num lugar só, e a guarda é cobrada no fonte

```
$ python test_tarefas.py
Ran 42 tests in 0.087s

OK
```

A guarda-da-guarda tem nome: `GuardaDaGuarda.test_pode_rodar_confere_aprovado_em_no_fonte`
lê `inspect.getsource(tarefas.pode_rodar)` e cobra que `aprovado_em` e
`cor_da_regra` apareçam ali. Apagar a guarda deixa o **arquivo** vermelho, e
não só uma asserção — asserção vermelha se "conserta" mudando a asserção.

E o isolamento, provado num processo novo:
`Isolamento.test_importar_tarefas_nao_arrasta_execucao_nem_fila`.

### Critério 4 — nenhuma tarefa, de nenhuma cor, publica

```
$ python test_tarefas_nao_publicam.py
Ran 18 tests in 0.005s

OK
```

Cinco cercas independentes, todas lidas das estruturas de verdade.
**Este vigia achou um buraco real no primeiro minuto de vida**, e o achado
está no §"o que este trabalho encontrou", abaixo.

### Critério 5 — com o teto estourado, o argv NUNCA é montado

```
$ python -m unittest test_executor.OTetoRecusaAntesDeComecar -v
test_com_o_teto_do_dia_consumido_o_argv_NUNCA_E_MONTADO ... ok
test_tarefa_vermelha_tambem_nao_monta_argv ... ok
test_maquina_sem_autorizacao_tambem_nao_monta_argv ... ok

Ran 3 tests in 0.605s

OK
```

Os três usam um dublê que **estoura se for chamado**. Se `pode_rodar` fosse
conferido depois de montar o comando, os três ficariam vermelhos — e é
exatamente esse o erro que eles existem para pegar.

### Critério 6 — a caixa efêmera na VPS

**NÃO FEITO.** É a etapa 15 do plano, e ela tem portão próprio: depende de um
sim ou não do dono, que ainda não foi dado. Ver a última seção.

### Critério 7 — a imagem continua sem o executor

```
$ python test_imagem.py
Ran 12 tests in 0.085s

OK
```

Nominalmente: `execucao.py`, `fila.py` e `barreira.py` continuam **fora** da
imagem, e `tarefas.py` entrou nela (o teste pegou isso sozinho, porque
`banco.py` passou a importá-lo).

### Critério 8 — o dono vê o trabalho acontecendo

```
$ python test_sse.py
Ran 16 tests in 7.9s

OK
```

**E conferido CLICANDO, num navegador de verdade**, com o servidor local de pé
em `http://localhost:4777`:

- gravei uma linha nova direto no banco enquanto a tela estava aberta;
- ela **apareceu na tela sem eu recarregar nada**, e a frase da barra do freio
  mudou junto;
- o log lido da tela depois disso:
  `["abrindo a copia isolada", "rodando os testes", "editando .env.example", "ESTA LINHA CHEGOU AO VIVO"]`.

Os cabeçalhos, pedidos com sessão de verdade:

```
$ curl -D - -o /dev/null --max-time 4 -H "Cookie: sessao=..." http://localhost:4777/api/eventos
HTTP/1.0 200 OK
Content-Type: text/event-stream; charset=utf-8
Cache-Control: no-cache
X-Accel-Buffering: no
Connection: close
```

Sem sessão:

```
$ curl -o /dev/null -w "%{http_code}" http://localhost:4777/api/eventos
401
```

**O botão Parar foi disparado de verdade**, e não só olhado — a lição já paga
nesta casa foi afirmar que a fila funcionava tendo só visto a faixa aparecer.
Depois do clique:

- `parada_pedida_em` gravado no banco: `2026-08-29T00:19:39+00:00`;
- a frase da barra virou *"Pedido de parada enviado. Esperando o computador
  confirmar — isso leva alguns segundos."*;
- o botão ficou desabilitado;
- **em nenhum momento a tela disse "parado"**.

### Critério 9 — o diff em português, e o ramo

Conferido clicando, na tarefa terminada:

- frase em português: `1 linha trocada em \`MEMORY.md\``;
- o ramo: *"As mudanças estão no ramo `hub/memoria-crlf-2`, e não no seu código
  principal."*;
- o diff cru abriu dentro do `<details>`, com o conteúdo certo.

A tradução é **função pura e determinística** (`tarefas.frases_do_diff`), sem
modelo de linguagem nenhum no caminho, e tem oito testes próprios em
`test_tarefas.DiffEmPortugues` — incluindo arquivo criado, apagado, renomeado e
diff vazio.

### Critério 10 — todo texto de tela em português

```
$ python test_design.py
Ran 24 tests in 0.037s
OK
```

**E agora o vigia enxerga o `painel.js`**, o que não acontecia até esta fatia:
desde 28/08 ele lia um `<script>` inline que a CSP tinha expulsado, e vinha
verde por estar olhando para o vazio. Medido: com o `painel.js`, 103 pedaços de
texto e 2990 caracteres; sem ele, 61 e 1991. O piso do teste ficou entre os
dois de propósito.

---

## Além dos dez

**Duas corridas seguidas da suíte inteira, ambas verdes.** (Duas corridas pegam
o teste que passa por sorte lendo banco real.)

```
corrida 1: 1276 verdes | falhou: nenhum
corrida 2: 1276 verdes | falhou: nenhum
```

**Em 360×640, nenhuma tela rola na horizontal.** Medido dentro de um quadro de
360 px, lendo `document.documentElement.scrollWidth`:

| Tela | Antes | Depois |
|---|---|---|
| Painel | — | 345 px |
| Trabalho | 392 px | 345 px |
| Consumo | — | 345 px |
| Detalhe da tarefa | — | 345 px |

Os 392 px eram um defeito real, achado nesta verificação: a marca de cor com
`white-space: nowrap` empurrava o conteúdo, e a página inteira passava a rolar.

---

## O que este trabalho ENCONTROU

Cinco defeitos, todos achados pelos próprios testes ou clicando, e todos
corrigidos antes de fechar:

1. **O buraco do `NUNCA_VERDE`, e é o mais grave.** `tarefas.pode_rodar`
   conferia a lista dentro do `if` da aprovação. Uma tarefa da regra
   `publicar` que tivesse `aprovado_em` **passava** — o clique do dono
   aprovando uma tarefa aprovava a **publicação**. Achado pelo vigia irmão
   (`test_tarefas_nao_publicam.py`) no primeiro minuto em que ele existiu. A
   checagem subiu para antes da aprovação.
2. **A vaga do fluxo ao vivo não voltava.** O laço só escrevia de 20 em 20
   segundos, e a vaga só era devolvida quando o servidor percebia que a aba
   tinha fechado. Com quatro vagas por sessão, **quatro recargas de página
   trancavam o dono fora do próprio painel por cinco minutos.** Consertado com
   uma sonda de três bytes por segundo.
3. **A tela dizia que uma tarefa em andamento tinha terminado.** O bloco "O que
   mudou" aparecia numa tarefa `rodando`, com a frase "nada mudou: a sessão
   terminou sem tocar em nenhum arquivo".
4. **O primeiro progresso era engolido**: toda sessão começava com cinco
   segundos de tela em branco, logo depois do clique — que é o intervalo em que
   uma pessoa clica de novo.
5. **A página rolava na horizontal em 360 px** (392 px de conteúdo).

Mais dois pegos por vigias que já existiam: um `color: #fff` literal no CSS, e
o `tarefas.py` faltando no `Dockerfile`.

E **uma afirmação minha que estava errada**: eu tinha escrito num comentário
que "o servidor não alcança `subprocess`". Falso — ele usa `subprocess` desde
sempre, para rodar os próprios coletores. A trava real nunca foi "não
importar": é que o argv nunca venha de um pedido. O teste agora cobra isso.

---

## O QUE ESTA VERIFICAÇÃO **NÃO** PROVA

- **Nada disto foi publicado.** `https://dervs.com.br` responde `200` na raiz e
  **`404` em `/api/eventos`** — ou seja, o servidor no ar ainda roda o código
  de antes desta fatia. Toda a prova acima é **local**, em
  `http://localhost:4777`. Cinco defeitos da primeira publicação só existiam
  fora do localhost; **o bloco do nginx foi conferido por LEITURA, e não por
  requisição contra o servidor de verdade.**
- **A caixa efêmera na VPS não existe** (critério 6). A etapa 15 não começou:
  ela depende de um sim ou não do dono, e vem junto com uma pergunta que
  **ninguém respondeu ainda** — se rodar o binário da assinatura Max dentro de
  um servidor é aceitável nos termos da Anthropic. A pesquisa achou a regra que
  proíbe assinatura **com o Agent SDK**, e o DERVS não usa o SDK; isso não é a
  mesma coisa que uma resposta.
- **Nenhuma sessão de verdade rodou de ponta a ponta.** O braço foi exercitado
  contra um dublê que imita o formato do `claude`. O caminho
  *painel → agente → binário real → ramo → diff na tela* nunca correu inteiro
  com o programa de verdade. É a próxima coisa a fazer, e ela precisa de um
  computador autorizado no painel.
- **O botão Parar foi provado no banco e na tela, e não contra um processo
  vivo.** Que `execucao.parar()` mate a árvore de processos é coberto pelos 91
  testes de `execucao.py`, que existiam antes desta fatia; o que esta fatia
  provou é que o pedido **viaja** do clique até o agente.
- **A troca de chave por token continua sem ter rodado contra o GitHub de
  verdade.** Dívida antiga, não tocada aqui.
- **`test_servir.py` tem uma intermitência** (`WinError 10053`, ~1 falha em 4
  corridas). **Reproduzida no commit anterior à etapa 6**, com o trabalho
  guardado: 1 falha em 4 corridas também lá. **Não é desta fatia**, e não foi
  investigada.
- **Nada aqui prova que o dono vai confiar no verde.** Se ele abrir a tela, vir
  uma tarefa verde que já rodou sozinha e sentir que perdeu o controle do
  próprio código, todos os testes acima continuam verdes e a fatia falhou
  assim mesmo. A revisão do sétimo dia é onde isso aparece — e ela não é uma
  etapa deste plano, é um compromisso de calendário.
