# Verificação final da fatia 1

Etapa 17 do plano `docs/superpowers/plans/dervs-fatia-1.md`. Os oito comandos do
`como_provar`, com a saída colada. **Rodado em 28/08/2026**, contra
`https://dervs.com.br` no ar e a árvore em `main`.

Este arquivo existe para que daqui a um mês ninguém precise acreditar em
ninguém. Onde a saída diverge do esperado, ela está aqui do mesmo jeito, com a
explicação junto — a armadilha nomeada na própria etapa é escrever "tudo
verificado" com a saída de meia dúzia dos oito.

---

## O que a verificação encontrou antes de poder rodar

A etapa 17 não pôde começar pelo item 1. As três primeiras tentativas de
completar a prova 7 esbarraram em defeitos que **nenhuma verificação existente
podia enxergar**, e os três têm a mesma forma: cada elo individualmente correto,
e a cadeia quebrada no meio.

1. **`test_design.py` reprovava e devolvia sucesso.** Terminava em
   `unittest.main(exit=False)` sem repassar o resultado: imprimia
   `FAILED (failures=4)` e saía com código 0. O passo da CI decide pelo código
   de saída. A publicação `33190128169`, de 28/08 16h28, tem as quatro linhas de
   FAIL no registro e o job marcado `success` — o site foi ao ar com teste
   vermelho dentro. As quatro falhas eram reais: a correção da CSP (`496f710`)
   tirou o `<style>` e o `<script>` do `index.html`, e os leitores do teste
   continuaram apontados para o HTML.
2. **O site estava no ar sem entrada nenhuma.** Em produção `/entrar/local` não
   entra na tabela de rotas, então `/entrar/github` é a única porta — e ela
   responde 404 sem `DERVS_GITHUB_ID` e `DERVS_GITHUB_SECRET`, que moravam no
   repositório desde 27/08 e nunca chegavam ao `/opt/dervs/.env`. O roteiro de
   operação chamava esse passo de *opcional*, com a frase "o site sobe igual, só
   sem o botão".
3. **Perder a combinação da cortina era perder o site.** Ela nasce sorteada na
   primeira subida e é impressa uma vez, no registro daquele container; cada
   publicação recria o container. `cortina.trocar()` existia desde a etapa 9 e
   **nada no produto o chamava**.
4. **A porta abria para uma casa sem morador.** `autenticacao.convidar()` é a
   única forma de criar conta e roda só na linha de comando da máquina. Nada a
   rodava no servidor: não havia conta nenhuma. O sintoma não ajuda quem procura
   — o retorno do GitHub responde igual no sucesso e no fracasso, de propósito.

Os quatro estão corrigidos nos commits `a942b03`, `f2adc52` e `feed0e0`, e a
cadeia inteira passou a ser cobrada por `test_publicar.py`, registrado na CI.

---

## 1. A API recusa quem não tem sessão

```
$ curl -si https://dervs.com.br/api/dados | head -1
HTTP/1.1 401 Unauthorized
```

Esperado `401` ou `302`. ✅

## 2. Autenticação

```
$ python test_autenticacao.py
Ran 26 tests in 0.816s

OK
```
✅

## 3. Rotas

```
$ python test_rotas.py
Ran 22 tests in 0.005s

OK
```
✅

## 4. Nenhum shell exposto

```
$ grep -rn "dangerously-skip-permissions" $(git ls-files | grep -v '^vivo/') | wc -l
8
```

**Oito, não zero — e as oito são texto, não código.** Duas estão no próprio
passo do `publicar.yml` que faz a busca dentro da imagem; as outras seis são o
plano, o briefing, a spec e o handoff descrevendo esta mesma regra. Nenhuma liga
o atalho em lugar nenhum.

A busca que decide é a de dentro da imagem publicada, e quem a faz é o job
`imagem` do workflow, que **falha** se achar. Na publicação `33194924874`:

```
$ gh run view 33194924874 --repo garcia-goncalves/dervs --json jobs
success  conferir
success  imagem
success  publicar
success  etiquetar
```
✅ (com a ressalva acima escrita, não escondida)

## 5. A suíte inteira, duas corridas seguidas

```
$ for i in 1 2; do for t in test_*.py; do python $t || exit 1; done; done; echo DUAS-CORRIDAS-OK
DUAS-CORRIDAS-OK
```

Dezenove arquivos de teste, duas vezes. A segunda corrida existe para pegar o
teste que passa por sorte lendo banco real. ✅

## 6. A verificação automática está verde

```
$ gh run list --repo garcia-goncalves/dervs --limit 1 --json conclusion -q '.[0].conclusion'
success
```
✅

## 7. A máquina reporta, e o carimbo é recente

Esta é a prova que exigiu tudo o que está na seção de cima. Máquina pareada pelo
número gerado no painel:

```
$ python -m agente.enviar --alvo https://dervs.com.br --codigo 760091
pareado com https://dervs.com.br. O token ficou em C:\Users\Desktop\.dervs\agente.json
enviado: 17 projetos -> https://dervs.com.br
```

E a leitura, com sessão de verdade aberta no navegador:

```
GET https://dervs.com.br/api/maquinas
{"maquinas": [{"id": 1, "nome": "Thiago",
               "criado_em": "2026-08-28T17:44:53+00:00",
               "visto_em":  "2026-08-28T17:45:12+00:00",
               "projetos": 17}]}
```

Idade do carimbo no momento da leitura:

```
visto_em : 2026-08-28T17:45:12+00:00
agora    : 2026-08-28T17:46:16+00:00
idade    : 64 segundos (DENTRO de 120)
```
✅

## 8. Os oito itens do design

```
$ python test_design.py
Ran 21 tests in 0.022s

OK
```

Este é o arquivo que mentia. Depois da correção, o código de saída foi provado
**nos dois sentidos**: com uma falha plantada (`len(fs), 30` virou
`len(fs), 9999`) ele devolve `1`; sem ela, `0`.

Dois dos oito itens continuam **não automatizados**, e o próprio teste diz isso
na saída em vez de se calar — o item 5 (em 360×640 a linha mostra selo, nome,
motivo e carimbo juntos) e o clique da etapa 14. Os dois foram verificados à
mão nesta sessão; ver abaixo. ✅

---

## O que os oito comandos não provam, e foi conferido clicando

O plano é explícito: os `como_provar` provam que a leitura é confiável e que não
há shell exposto. Não provam que o produto é bom. Isto foi verificado no
navegador, em `https://dervs.com.br`, com sessão de verdade:

- **A cortina abre** com a combinação de seis dígitos, digitada botão a botão no
  teclado da tela.
- **"Entrar com GitHub" leva ao painel.** Antes desta sessão respondia 404.
- **O painel lê dado real:** *"1 projeto quebrado, 5 pedem atenção, 11 estão
  bem"* — 17 no total, batendo com o que o agente enviou. Os quatro selos
  aparecem, inclusive `0 sem dados`.
- **Cada linha traz selo, nome, motivo e carimbo** (*medido há 75 segundos*).
- **O botão "Ver o que gerou este alerta" leva à prova**, não a uma tela vazia:
  abre `#/alerta/memoria_crlf:ccvp` com os três arquivos nomeados um a um, mais
  *Adiar 24 horas* e *Isto está certo assim*.
- **A tela Computadores gera o número** e monta o comando de pareamento.

**Um defeito de texto foi achado assim e corrigido:** a tela *Formas de entrar*
dizia *"Hoje entra pela porta do ambiente local, que não existe no servidor"* —
falso em produção, onde a entrada foi pelo GitHub. Nenhum teste pegaria: é
frase, não contrato.

**Um falso alarme, registrado para não custar de novo:** dois cliques meus no
menu não registraram, e cheguei a chamar isso de defeito. Não era. A imagem que
a automação me devolve tem 1568 pontos de largura e a janela tem 1920 — as
coordenadas estavam deslocadas. O menu funciona; clicar pelo identificador do
elemento, e não por coordenada, é o que evita o engano.

---

## O que continua em aberto

Nada disto bloqueia a fatia, e nada disto está resolvido:

1. **Uma forma de entrar só.** Nenhuma chave de acesso cadastrada e nenhum
   código de papel gerado. Quem perder o GitHub não abre a conta — o próprio
   painel cobra isso em vermelho.
2. **`/assets/painel.js` é legível sem sessão.** Custo aceito no commit
   `496f710`.
3. **Não existe comando para apagar conta criada errada.** O e-mail é UNIQUE em
   `usuario`; errar custa mexer no banco do servidor à mão.
4. **`dervs.com.br` publica um MX nulo** — o domínio declara que não recebe
   e-mail. Os e-mails das contas são identificadores, não caixas.
