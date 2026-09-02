# -*- coding: utf-8 -*-
"""Faz o pytest ignorar as copias isoladas em `.claude/worktrees/`.

Este repositorio NAO roda por pytest: a CI chama `python test_X.py`, um passo
por arquivo, listado a mao em `.github/workflows/ci.yml`. Este arquivo existe
so para uma ferramenta de fora — o verificador automatico do harness, que
chama pytest sobre "os testes vizinhos do que foi editado".

O PROBLEMA QUE ELE RESOLVE, medido em 02/09/2026:

Quando varias etapas de um plano rodam em paralelo, cada executor trabalha
numa copia isolada do repositorio (git worktree) dentro de
`.claude/worktrees/agent-<id>/`. Com cinco copias vivas, existem seis
`test_servir.py` no disco — o da pasta principal e um por copia. O pytest
importa cada arquivo de teste como um MODULO pelo nome-base; seis arquivos
`test_servir.py` viram seis tentativas de importar o modulo `test_servir`, e
da segunda em diante ele para com:

    import file mismatch: imported module 'test_servir' has this __file__ ...

Isso e um erro DE COLETA, nao um teste vermelho. Aconteceu duas vezes numa
sessao so, e nas duas a suite de verdade estava inteira verde — o que e
exatamente o pior tipo de alarme: o que treina quem le a ignorar alarme.

Nao da para resolver com `norecursedirs`: o verificador passa os caminhos
EXPLICITAMENTE na linha de comando, e caminho explicito ignora aquela opcao.
`pytest_ignore_collect` e consultado tambem para os caminhos passados a mao,
e por isso e este o gancho usado aqui.

As copias sao descartaveis por construcao: o que vale delas ja foi mesclado
no ramo, e e nele que a suite roda.
"""
from __future__ import annotations

import os

PASTA_DAS_COPIAS = os.path.join(".claude", "worktrees")


def _e_copia_isolada(caminho: str) -> bool:
    """Verdadeiro para qualquer coisa dentro de `.claude/worktrees/`.

    Normaliza a barra porque esta maquina e Windows e o pytest entrega ora
    `\\`, ora `/`, dependendo de como o caminho chegou na linha de comando.
    """
    normal = str(caminho).replace("\\", "/")
    return "/.claude/worktrees/" in normal or normal.startswith(".claude/worktrees/")


def pytest_ignore_collect(collection_path, config):  # noqa: ARG001
    """Gancho do pytest 7+. Devolver True poda o caminho inteiro.

    Devolver None (e nao False) para o resto e de proposito: False FORCARIA a
    coleta e atropelaria a decisao de outros ganchos. None quer dizer "nao
    tenho opiniao sobre este caminho", que e a verdade.
    """
    if _e_copia_isolada(collection_path):
        return True
    return None
