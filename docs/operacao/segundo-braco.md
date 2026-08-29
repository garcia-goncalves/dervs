# Deixar o DERVS consertar sozinho

> Para quem não opera terminal. Cada passo diz **o comando exato**, **onde
> colar**, **o que aparece se der certo** e **o que fazer se der errado**.

Até aqui o DERVS só **media**: ele olhava seus projetos e dizia o que estava
quebrado. Agora ele pode **consertar** — abrir uma cópia isolada do projeto,
trabalhar nela, e devolver um ramo com as mudanças para você aprovar.

**O que ele nunca faz, nem com você autorizando:** publicar no servidor. Essa
porta é vermelha para sempre e não tem interruptor.

---

## Antes de tudo: as três coisas que já precisam existir

1. **O painel no ar**, em <https://dervs.com.br>, e você conseguindo entrar.
2. **Um computador conectado** — se ainda não conectou, o roteiro é
   [`conectar-uma-maquina.md`](conectar-uma-maquina.md).
3. **O Claude Code instalado nesse computador**, com você já tendo entrado
   nele alguma vez. O DERVS usa a mesma assinatura que você usa no dia a dia;
   ele não tem conta própria.

Para conferir a terceira, **eu rodo** o comando abaixo e te digo o resultado —
você não precisa fazer nada:

```
claude --version
```

**Se der certo**, aparece uma linha com um número de versão, algo como
`2.0.14 (Claude Code)`.

**Se der errado**, aparece `'claude' não é reconhecido...`. Aí o Claude Code
não está instalado nessa máquina, e o DERVS vai continuar só medindo — sem
quebrar nada, e dizendo na tela que aquele computador não tem o braço.

---

## Passo 1 — autorizar o computador (é seu, e só seu)

Conectar um computador **nunca** deu a ele o direito de rodar código. É preciso
um segundo sim, e ele é dado assim:

1. Abra <https://dervs.com.br>.
2. Clique em **Computadores**, no menu de cima.
3. Ache o computador na lista. Embaixo do nome dele há uma etiqueta em letras
   maiúsculas com contorno: ela diz **SÓ MEDE** enquanto ele não pode rodar
   nada.
4. Clique em **Deixar consertar aqui**.
5. Vai aparecer uma janela explicando o que ele passa a poder fazer. Leia, e
   clique em **Pode consertar**.

**O que aparece se der certo:** a etiqueta muda para **PODE CONSERTAR AQUI**,
com o contorno mais forte e o texto mais escuro, e o botão passa a dizer
**Deixar só medindo**. As duas etiquetas se distinguem por contorno e peso, e
não por cor — quem não separa cores enxerga a diferença igual.

**Se der errado:** aparece um aviso vermelho dizendo *"não deu para mudar esse
computador"*. Isso quase sempre é a sessão vencida — recarregue a página, entre
de novo e repita.

**Para desfazer, a qualquer momento:** o mesmo botão, agora escrito **Deixar só
medindo**. Um clique, e o computador volta a só olhar.

---

## Passo 2 — decidir o que anda sozinho

Toda regra nasce **vermelha**: ela para e espera você clicar. Você decide,
regra por regra, quais podem andar sozinhas.

1. Clique em **Trabalho**, no menu de cima.
2. Role até **O que pode andar sozinho**.
3. Cada regra tem uma marca ao lado — *espera o clique* (vermelho) ou *anda
   sozinho* (verde) — e um botão para trocar.

**A sugestão honesta:** deixe tudo vermelho na primeira semana. Você aprova
tarefa por tarefa, vê o que o DERVS faz, e só então libera as regras em que
confiar. É mais trabalho no começo, e é o único jeito de a confiança ser
baseada em algo.

**A regra `publicar` não tem botão.** Ao lado dela está escrito *"nunca anda
sozinha, e isso não se muda"*. Não é um limite de configuração: são quatro
travas independentes no código, e a única forma de removê-las seria reescrever
o programa.

---

## Passo 3 — o que você vai ver quando ele trabalhar

Na tela **Trabalho**:

- **Uma faixa no topo de TODAS as telas** enquanto houver algo acontecendo, com
  a frase do que está sendo feito e um botão **Parar**.
- Clicando na tarefa, **o que ele está fazendo aparece linha por linha, ao
  vivo**, sem você recarregar nada.
- Quando termina, **O que mudou**: uma frase em português por arquivo
  (*"3 linhas trocadas em `banco.py`"*), o nome do ramo, e — se você quiser a
  prova — o código linha a linha, fechado embaixo.

**As mudanças nunca vão para o seu código principal.** Elas ficam num ramo
separado, com nome começando em `hub/`. Nada é enviado ao GitHub pela sessão: a
cópia em que ela trabalha nem sabe o endereço do seu repositório.

---

## O botão Parar — e a verdade sobre ele

Ele **não é instantâneo**, e a tela diz isso.

Quando você clica, o painel escreve o pedido. O computador que está trabalhando
só descobre no próximo aviso que ele manda — **até 5 segundos** —, e depois
ainda leva alguns segundos para encerrar os programas. **No pior caso, uns 10
segundos.**

Por isso a frase na faixa muda em duas etapas:

1. *"Pedido de parada enviado. Esperando o computador confirmar."*
2. Só quando ele confirma é que a tarefa aparece como encerrada.

Se aparecesse "parado" logo no clique, você acharia que acabou enquanto a
sessão ainda estava rodando — e essa é exatamente a mentira que este painel não
conta.

---

## Passo 4 — olhar o consumo, e por quê

O DERVS usa a **mesma assinatura** que você usa. O que acaba não é dinheiro: é
**cota**. O jeito de isso dar errado não é uma fatura alta — é o Claude parar
para vocês dois no meio de uma terça-feira.

**Você decidiu, em 28/08/2026, não ter freio de horário e observar sete dias.**
A tela **Consumo** é o que torna essa decisão possível de cumprir:

1. Clique em **Consumo**, no menu de cima.
2. Veja quantas **sessões** e **rodadas** foram gastas na semana, por dia, por
   projeto e por regra.

O valor em reais aparece ali, mas **rotulado como referência**. O número que
manda é sessões e rodadas.

**Marque no calendário: no sétimo dia, olhe essa tela.** Se o consumo estiver
alto, o conserto é fechar regras (voltar para vermelho) — não é mexer no
código.

---

## Se alguma coisa der errado

| O que você vê | O que é | O que fazer |
|---|---|---|
| *"esta máquina não tem o braço 'claude' instalado"* | O Claude Code não está naquele computador | Me avise; eu confiro a instalação |
| A tarefa fica *"trabalhando agora"* e nunca acaba | O computador parou de dar notícia | Espere 15 minutos: o painel marca sozinho como falha e diz *"o computador parou de dar notícia"* |
| *"esta tarefa está vermelha e espera o seu clique"* | Funcionou como devia | Clique em **Pode fazer** na tarefa |
| *"o teto de R$ 50,00 do dia já foi alcançado"* | O freio de gasto disparou | Nada a fazer hoje; ele zera na virada do dia, no seu fuso |
| A faixa do ao vivo diz que a ligação caiu | A conexão de tempo real caiu | Nada. A tela continua atualizando a cada minuto sozinha |

**Nada aqui exige terminal.** Se algum passo parecer exigir, me chame — o
comando é meu, a decisão é sua.
