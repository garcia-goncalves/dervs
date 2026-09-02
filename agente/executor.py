# -*- coding: utf-8 -*-
"""A tomada onde um braco e ligado.

O DERVS vai ter dois bracos. Hoje so um esta ligado — o Claude Code, que ja
existia e estava desligado (`execucao.py`, 1215 linhas, 91 testes). O Codex
entra na Fatia 3, e a unica coisa que este arquivo precisa garantir e que
ligar o segundo seja ACRESCENTAR uma implementacao, nao refazer nada.

Por isso `ExecutorCodex` ja existe aqui, com `disponivel()` devolvendo `False`.
Uma tomada vazia que ninguem consegue testar nao e uma tomada: e uma promessa.

**`execucao.py` nao e reescrito.** Ele tem 91 testes e a medicao de campo
colada no topo — quanto custa ligar uma sessao, e o quanto o `--max-budget-usd`
estourou. Este arquivo o EMBRULHA: `iniciar`, `estado`, `parar` e
`esperar_terminar` continuam sendo dele.

**A segunda camada do teto.** `Executor.rodar` chama `tarefas.pode_rodar` ANTES
de montar qualquer comando. O servidor ja recusou entregar a tarefa que nao
cabe; aqui ele recusa de novo. Duas camadas para a mesma regra e de proposito:
a de fora depende de o painel estar certo, e esta nao depende de nada.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

AQUI = Path(__file__).resolve().parent
if str(AQUI.parent) not in sys.path:
    sys.path.insert(0, str(AQUI.parent))

import auditoria  # noqa: E402
import execucao   # noqa: E402
import tarefas    # noqa: E402


class Executor:
    """O contrato. Tres coisas, e so tres.

    `rodar` devolve um dicionario no formato do DESFECHO descrito em
    `tarefas.py` — o mesmo que sobe por `POST /agente/resultado`. Quem escreve
    um braco novo nao precisa ler o servidor: le o contrato.
    """

    nome = "abstrato"

    def disponivel(self) -> bool:
        """Esta maquina consegue rodar este braco AGORA?"""
        raise NotImplementedError

    def rodar(self, tarefa: dict, teto_usd=None, ao_progredir=None,
              gasto_usd=0.0, repinturas=None, maquina=None) -> dict:
        raise NotImplementedError

    # A guarda comum, e ela mora na base para nao existir em duas versoes.
    def _recusar_se_nao_pode(self, tarefa, gasto_usd, repinturas, maquina):
        """`None` se pode rodar; o desfecho de recusa se nao pode."""
        pode, motivo = tarefas.pode_rodar(tarefa, gasto_usd, "", repinturas,
                                          maquina)
        if pode:
            return None
        return {
            "tipo": "desfecho",
            "id": (tarefa or {}).get("id") or "",
            "estado": "falha",
            "ramo": "", "resumo": "", "diff": "", "pr_url": "",
            "rodadas": 0, "custo_usd": 0.0,
            "erro": motivo,
            "recusada": True,
        }


class ExecutorClaude(Executor):
    """O braco que ja existia, agora alcancavel.

    Nada aqui monta comando, peneira ambiente ou clona repositorio: tudo isso
    e `execucao.py`, e ele ja e testado.
    """

    nome = "claude"

    # De quanto em quanto tempo o laco olha a sessao. Mais curto que o
    # intervalo com que o agente FALA com o painel
    # (`tarefas.SEGUNDOS_ENTRE_PROGRESSOS`), para nunca ser ele o gargalo.
    SEGUNDOS_ENTRE_OLHADAS = 1.0
    # Teto duro da sessao inteira. `--max-budget-usd` foi medido estourando
    # 4,5x; o relogio nao estoura.
    SEGUNDOS_DE_SESSAO = 1800

    def disponivel(self) -> bool:
        """Ha um binario do Claude Code nesta maquina?

        Nao roda nada para descobrir: montar o comando ja diz. Perguntar
        `claude --version` custaria uma subida de processo a cada volta do
        laco do agente.
        """
        try:
            return bool(execucao.montar_comando())
        except Exception:                      # noqa: BLE001 — falha fechada
            return False

    def rodar(self, tarefa: dict, teto_usd=None, ao_progredir=None,
              gasto_usd=0.0, repinturas=None, maquina=None) -> dict:
        recusa = self._recusar_se_nao_pode(tarefa, gasto_usd, repinturas,
                                           maquina)
        if recusa is not None:
            return recusa

        pendencia = {
            "id": tarefa.get("id") or "",
            "projeto": tarefa.get("projeto") or "",
            "regra": tarefa.get("regra") or "",
            "detalhe": tarefa.get("detalhe") or "",
            "gravidade": tarefa.get("gravidade") or "media",
        }
        caminho = tarefa.get("caminho") or tarefa.get("projeto_caminho") or ""
        teto = tarefa.get("teto_usd") if teto_usd is None else teto_usd

        # `contabilizar=False`: o custo desta sessao vai para a linha da `fila`
        # pelo desfecho. Deixar `True` contaria o mesmo gasto duas vezes.
        decisao = execucao.iniciar(pendencia, caminho, teto_usd=teto,
                                   contabilizar=False)
        if decisao != "iniciar":
            return {
                "tipo": "desfecho", "id": pendencia["id"], "estado": "falha",
                "ramo": "", "resumo": "", "diff": "", "pr_url": "",
                "rodadas": 0, "custo_usd": 0.0,
                "erro": ("ja ha uma sessao rodando nesta maquina"
                         if decisao == "mesma"
                         else "esta maquina recusou comecar a sessao"),
                "recusada": True,
            }

        return self._acompanhar(pendencia["id"], ao_progredir)

    def _acompanhar(self, tarefa_id: str, ao_progredir) -> dict:
        """Le a sessao enquanto ela roda e empurra o que aparece.

        `ao_progredir(retrato)` pode devolver `True` para dizer "pare". E por
        ai que o botao Parar do painel chega ate aqui: o agente pergunta ao
        painel de cinco em cinco segundos, e a resposta volta por este retorno.
        """
        entregues = 0
        fim = time.time() + self.SEGUNDOS_DE_SESSAO
        while time.time() < fim:
            retrato = execucao.estado(entregues)
            entregues = retrato.get("total_de_linhas", entregues)
            if ao_progredir is not None:
                try:
                    if ao_progredir(retrato):
                        execucao.parar()
                        break
                except Exception:              # noqa: BLE001
                    # Falha ao FALAR com o painel nao pode matar a sessao. O
                    # trabalho ja esta feito pela metade; perde-lo por causa de
                    # um cabo de rede seria o pior dos dois mundos.
                    pass
            if retrato.get("estado") in execucao.ESTADOS_TERMINAIS:
                break
            time.sleep(self.SEGUNDOS_ENTRE_OLHADAS)
        else:
            execucao.parar()

        final = execucao.estado(entregues)
        terminou_bem = final.get("estado") == "ok"
        return {
            "tipo": "desfecho",
            "id": tarefa_id,
            "estado": "ok" if terminou_bem else "falha",
            "ramo": final.get("ramo") or "",
            "resumo": final.get("resumo") or final.get("manchete") or "",
            "diff": final.get("diff") or "",
            "pr_url": final.get("pr_url") or "",
            "rodadas": int(final.get("rodadas") or 0),
            "custo_usd": float(final.get("custo_usd") or 0.0),
            "erro": "" if terminou_bem else (final.get("corpo") or
                                             final.get("manchete") or
                                             "a sessao nao terminou bem"),
        }


class ExecutorAuditor(Executor):
    """O braco SO-LEITURA (Auditoria Profunda, 02/09/2026): le um repositorio
    e devolve achados, nunca abre pull request.

    Nada aqui monta comando nem clona repositorio: tudo isso e
    `execucao.auditar`, a irma so-leitura de `execucao.iniciar`. O desfecho
    sobe pelo MESMO contrato de `tarefas.CAMPOS_DO_DESFECHO` — o campo
    `resumo` carrega o JSON cru que o agente respondeu (o esquema pedido por
    `--json-schema`), e quem valida aquele JSON e `auditoria.validar`, do
    lado do servidor, nunca este arquivo.
    """

    nome = auditoria.EXECUTOR

    SEGUNDOS_ENTRE_OLHADAS = 1.0
    SEGUNDOS_DE_SESSAO = 1800

    def disponivel(self) -> bool:
        try:
            return bool(execucao.montar_comando_de_auditoria())
        except Exception:                      # noqa: BLE001 — falha fechada
            return False

    def rodar(self, tarefa: dict, teto_usd=None, ao_progredir=None,
              gasto_usd=0.0, repinturas=None, maquina=None) -> dict:
        recusa = self._recusar_se_nao_pode(tarefa, gasto_usd, repinturas,
                                           maquina)
        if recusa is not None:
            return recusa

        projeto = tarefa.get("projeto") or ""
        caminho = tarefa.get("caminho") or tarefa.get("projeto_caminho") or ""
        teto = tarefa.get("teto_usd") if teto_usd is None else teto_usd

        decisao = execucao.auditar(projeto, caminho, teto_usd=teto)
        if decisao != "iniciar":
            return {
                "tipo": "desfecho", "id": tarefa.get("id") or "",
                "estado": "falha", "ramo": "", "resumo": "", "diff": "",
                "pr_url": "", "rodadas": 0, "custo_usd": 0.0,
                "erro": "ja ha uma sessao rodando nesta maquina",
                "recusada": True,
            }

        return self._acompanhar(tarefa.get("id") or "", ao_progredir)

    def _acompanhar(self, tarefa_id: str, ao_progredir) -> dict:
        """Igual a `ExecutorClaude._acompanhar`, sobre o estado da auditoria."""
        entregues = 0
        fim = time.time() + self.SEGUNDOS_DE_SESSAO
        while time.time() < fim:
            retrato = execucao.estado_auditoria(entregues)
            entregues = retrato.get("total_de_linhas", entregues)
            if ao_progredir is not None:
                try:
                    if ao_progredir(retrato):
                        execucao.parar_auditoria()
                        break
                except Exception:              # noqa: BLE001
                    pass
            if retrato.get("estado") in execucao.ESTADOS_TERMINAIS:
                break
            time.sleep(self.SEGUNDOS_ENTRE_OLHADAS)
        else:
            execucao.parar_auditoria()

        final = execucao.estado_auditoria(entregues)
        terminou_bem = final.get("estado") == "ok"
        return {
            "tipo": "desfecho",
            "id": tarefa_id,
            "estado": "ok" if terminou_bem else "falha",
            "ramo": "", "diff": "", "pr_url": "",
            "resumo": final.get("resumo") or "",
            "rodadas": int(final.get("rodadas") or 0),
            "custo_usd": float(final.get("custo_usd") or 0.0),
            "erro": "" if terminou_bem else (final.get("corpo") or
                                             final.get("manchete") or
                                             "a auditoria nao terminou bem"),
        }


class ExecutorCodex(Executor):
    """O segundo braco. Previsto, e desligado.

    Ele existe para que ligar o Codex seja escrever este corpo — e nao mexer
    no agente, no painel e no contrato ao mesmo tempo.
    """

    nome = "codex"

    def disponivel(self) -> bool:
        return False

    def rodar(self, tarefa: dict, teto_usd=None, ao_progredir=None,
              gasto_usd=0.0, repinturas=None, maquina=None) -> dict:
        raise NotImplementedError(
            "o segundo braco (Codex) e da Fatia 3. A tomada esta pronta; a "
            "implementacao, nao.")


# A lista dos bracos, por nome. O painel manda `executor` no corpo da tarefa, e
# e esta tabela que decide qual objeto responde. Nome desconhecido devolve
# `None`, e quem chama trata como recusa — nunca como "usa o padrao".
EXECUTORES = {
    ExecutorClaude.nome: ExecutorClaude,
    ExecutorAuditor.nome: ExecutorAuditor,
    ExecutorCodex.nome: ExecutorCodex,
}


def executor_de(nome: str):
    """A instancia do braco pedido, ou `None`. Falha fechada."""
    classe = EXECUTORES.get((nome or "").strip())
    return classe() if classe else None
