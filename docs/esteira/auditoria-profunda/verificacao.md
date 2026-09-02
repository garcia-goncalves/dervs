# Verificação — A Auditoria Profunda

> 02/09/2026, branch `auditoria-profunda`. **A segunda metade deste documento é a
> que importa:** o que os comandos abaixo NÃO provam.

## O que foi rodado, e a saída

### A suíte inteira — 26 de 26 arquivos, 1.635 casos

```
### SUITE COMPLETA ###
test_agente.py                     OK (skipped=1)
test_auditoria.py                  OK
test_autenticacao.py               OK
test_banco.py                      OK
test_barreira.py                   OK
test_coletar.py                    OK
test_coletar_pesado.py             OK
test_conectador.py                 OK
test_conectar_ponta_a_ponta.py     OK
test_cortina.py                    OK
test_design.py                     OK
test_execucao.py                   OK
test_executor.py                   OK
test_fila.py                       OK
test_github_app.py                 OK
test_imagem.py                     OK
test_memoria.py                    OK
test_p256.py                       OK
test_passkey.py                    OK
test_publicar.py                   OK
test_regras.py                     OK
test_rotas.py                      OK
test_servir.py                     OK
test_sse.py                        OK
test_tarefas.py                    OK
test_tarefas_nao_publicam.py       OK
### ARQUIVOS COM FALHA: 0 ###
TOTAL DE CASOS: 1635
```

**Rodar a suíte inteira não foi cerimônia.** Na primeira corrida completa,
`test_memoria.py` ficou **vermelho num arquivo que nenhuma etapa tinha tocado** —
o guarda "toda regra do motor tem rótulo em português" lê o *texto* de `regras.py`
atrás de nome escrito à mão, e as cinco regras novas são **derivadas** de
`auditoria.CATEGORIAS`. Cada executor tinha visto verde nos seus arquivos.

### O servidor de verdade, subindo

```
capa:                       200
api/dados sem sessao:       401
api/auditoria sem sessao:   401
assets/painel.js sem sessao: 401
```

O `401` do `painel.js` é o que prova que a trava por **caminho exato** continuou
de pé depois de tudo o que foi mexido em `servir.py`.

## As nove revisões, e o que elas acharam com a suíte verde

Duas revisões especialistas (segurança e Python) leram o diff inteiro **depois**
de a suíte estar verde. Acharam nove coisas. Isto é o argumento inteiro a favor
de revisar código que já passou nos testes.

| # | O que era | Onde |
|---|---|---|
| 1 | **A auditoria nunca gravava nada.** Nada no repositório produzia a chave `achados`; o bloco de gravação era inalcançável. Rodaria, gastaria o teto e não gravaria | `agente/executor.py`, `execucao.py` |
| 2 | **O achado trocava de dono entre contas.** Id determinístico sem o dono dentro; a segunda gravação transferia a linha e sumia o achado do painel do primeiro | `banco.py` |
| 3 | **Pedido de auditoria pulava a lista de projetos proibidos** — dava para pedir auditoria do repositório de prontuário excluído de propósito | `servir.py` |
| 4 | **Uma conta enfileirava trabalho na máquina da outra**, queimando o teto compartilhado de R$ 50 | `servir.py` |
| 5 | **Código-fonte privado descia para a máquina errada** — `LEFT JOIN` sem confrontar o dono | `banco.py` |
| 6 | O nome do projeto era interpolado **dentro do bloco de instrução** do prompt; a peneira era decorativa ali | `auditoria.py` |
| 7 | Número torto vindo de máquina pareada derrubava a rota em **500** em vez de recusar fechado | `servir.py` |
| 8 | O poll de 60 segundos de **toda aba** carregava a lista inteira de achados (até 1.200 caracteres cada) | `servir.py` |
| 9 | `RecursionError`, e caractere de controle aceito no caminho do arquivo | `auditoria.py` |

**Todos os nove estão corrigidos, com teste e sabotagem.**

**Uma correção proposta pela revisão foi RECUSADA, e conferida antes.** A revisão
de Python propôs resolver o nº 8 podando os achados em `banco.montar_estado`.
Isso **teria quebrado a entrega inteira**: é de `montar_estado` que
`regras.avaliar` lê os achados para virar pendência. A poda ficou **depois** do
motor, e existe um terceiro teste que lê `montar_estado` direto e exige os
achados lá — sem ele, alguém "consertaria" daquele jeito e os dois primeiros
testes ficariam verdes com o motor cego.

## Os guardas que não podiam reprovar — e foram pegos

Quatro, nesta entrega:

1. **`assertIn("auditoria", html)`** — não podia reprovar, porque `id="tela-auditoria"`
   já contém a palavra. Reescrito casando **três** ocorrências que têm de bater entre si.
2. **A sabotagem 3b, do jeito óbvio** — o caso certo é *"a auditoria rodou e achou
   zero"*, não *"a camada não foi coletada"*: com a camada ausente o defeito plantado
   nunca era executado.
3. **A identidade do nome do executor** — por interning de string no CPython, escrever
   o nome à mão sozinho **não** fazia o `assertIs` reprovar. Documentado no teste.
4. **`test_achados_acima_do_teto_proprio_sao_recusados_inteiros`** — reprovava pelo
   motivo errado (o texto usado nem era JSON válido), então não provava a trava de
   tamanho. Um segundo caso, com JSON válido e enchimento, foi escrito.

E uma sabotagem que **deixou de poder acusar depois do conserto certo**: com a
chave primária composta, a linha `usuario_id = excluded.usuario_id` virou **código
morto**, e teste de comportamento não acusa código que não roda. Foi trocada por
um guarda que lê o código-fonte.

---

# O QUE ISTO NÃO PROVA

**1. Nenhuma auditoria de verdade jamais rodou.** Nem uma. Todo o fio é provado
com script de mentira cuspindo `stream-json`, porque nenhum teste pode chamar o
binário `claude` (a CI não tem login, e cada corrida gastaria a assinatura do
dono). O que está provado é que **o fio conduz**; o que não está é que o Claude
Code, apontado para um repositório de verdade, devolve achados úteis dentro do
esquema.

**2. `--json-schema` é promessa do fornecedor, não fato medido.** Se a versão
instalada do binário não tiver essa opção, ou não a respeitar, os testes continuam
verdes — eles leem o comando montado, não a resposta. `auditoria.validar` recusaria
a corrida inteira e o projeto ficaria em **sem dados**, que é o desfecho correto,
mas o defeito só apareceria na primeira auditoria real.

**3. Ninguém viu a tela de Auditoria desenhada.** O painel local sobe (`200`), a
rota exige sessão (`401`), e `test_design.py` confere a estrutura. Mas entrar no
painel exige o PIN do Windows, que é a mão do dono. **Os quatro estados da tela
— nunca auditado, carregando, falhou, e "auditado, nada encontrado" — nunca foram
vistos por olho humano.**

**4. O custo real de uma auditoria é palpite.** `TETO_AUDITORIA_USD = 1,50` foi
escolhido pela conta de quantas cabem nos R$ 50 do dia, não por medição.
`MAX_TURNOS_AUDITORIA = 60` é palpite declarado do plano. **A primeira auditoria
real é que vira medição.**

**5. Nada disto está no ar.** O site publicado é de 29/08 e **não tem nada desta
entrega**. Nem a Auditoria, nem as correções de segurança. Publicar exige a mão do
dono.

**6. A migração da chave primária de `achado` nunca rodou sobre dado de verdade.**
Ela é provada contra um banco de teste montado no formato antigo. O `hub.db` desta
máquina é descartável; o do servidor não existe ainda com essas tabelas.

**7. O interruptor "este projeto quer ser auditado" (`auditoria_ligada`) não tem
tela.** Ele foi decidido pelo executor da etapa 3, existe no motor de regras, e
**nada no painel o liga ou desliga**. Hoje o seletor da tela lista todos os
projetos.

**8. O botão "Ver auditoria" na tela de Projeto não foi feito.** Estava no desenho
aprovado; não estava no "Fazer" da etapa 6. O executor disse que deixou de fora.

**9. O agendamento noturno não existe.** A auditoria é disparada por botão e pela
regra `auditoria_vencida`. O "audita tudo de madrugada e de manhã você vê o
resultado" **não foi construído** — está nomeado como fora de escopo no briefing,
depois da primeira auditoria real.

**10. As cinco regras de achado não viram conserto automático.** Elas ficam fora
de `fila.REGRAS_MECANICAS`, de propósito, porque "fora" é o estado seguro. Ligar
isso é decisão do dono, não conserto de executor.

**11. Duas contas nunca auditaram o mesmo repositório ao mesmo tempo de verdade.**
A colisão de dono é provada por teste com dois `usuario_id` no mesmo banco de
teste — não por duas máquinas reais em concorrência.

**12. O DERVS nunca auditou a si mesmo.** Seria o primeiro teste honesto do
produto, e ele depende do item 1.
