# -*- coding: utf-8 -*-
"""Testes do servidor do HUB.

Este arquivo era, até a etapa 7 do DERVS, quase todo sobre o proxy do grafo de
código: 40 testes de tradução de caminho, reescrita de corpo, compressão e
cabeçalho. O proxy foi removido junto com as rotas que executavam comando, e
os testes dele saíram no mesmo commit — teste de código que não existe mais é
peso morto que dá a falsa impressão de cobertura.

O que ficou aqui são os dois amarres que o servidor ainda precisa:

  - importar `servir.py` não pode quebrar por causa da linha de comando;
  - a tela não pode chamar rota que o servidor não tem.

A pergunta "este servidor executa comando?" mora em `test_rotas.py`, e lá ela é
respondida pela estrutura em memória, não por este arquivo.

    python test_servir.py
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

import servir


class PortaDaLinhaDeComando(unittest.TestCase):
    """Importar servir.py nao pode quebrar so porque ha argumento na linha.

    `python -m pytest test_servir.py` explodia com ValueError antes de rodar um
    unico teste: o argumento era o nome do arquivo.
    """

    def test_argumento_que_nao_e_numero_e_ignorado(self):
        self.assertEqual(servir.porta_de(["servir.py"], 4777), 4777)
        self.assertEqual(servir.porta_de(["servir.py", "-v"], 4777), 4777)
        self.assertEqual(servir.porta_de(["x", "test_servir.py"], 4777), 4777)

    def test_numero_valido_vale(self):
        self.assertEqual(servir.porta_de(["servir.py", "4780"], 4777), 4780)

    def test_numero_fora_da_faixa_e_ignorado(self):
        self.assertEqual(servir.porta_de(["servir.py", "0"], 4777), 4777)
        self.assertEqual(servir.porta_de(["servir.py", "99999"], 4777), 4777)


class ATelaSoChamaRotaQueExiste(unittest.TestCase):
    """O sucessor de `PaletaNaoInventaComando`, e pelo mesmo motivo.

    Aquele teste lia os `comando: "..."` do index.html e exigia que cada um
    existisse na lista branca do servidor. A lista branca acabou junto com
    `/api/acao`; o risco que ele cobria, nao. Uma rota escrita com erro de
    digitacao no `fetch()` falha calada na cara do dono: o botao roda, o
    servidor responde 404, e a tela nao mostra nada.

    Agora o amarre e direto — os caminhos que o index.html busca contra
    `servir.ROTAS`.
    """

    def _rotas_do_html(self):
        html = (Path(__file__).parent / "index.html").read_text(encoding="utf-8")
        # Pega o primeiro argumento de fetch(), que e sempre um literal aqui.
        # Query e concatenacao ficam de fora: a tabela casa so o caminho.
        cruas = re.findall(r'fetch\(\s*"(/[^"?]*)', html)
        return {c for c in cruas}

    def test_todo_fetch_da_tela_tem_rota_no_servidor(self):
        for caminho in self._rotas_do_html():
            self.assertIn(caminho, servir.ROTAS,
                          "a tela busca %r, que o servidor nao serve" % caminho)

    def test_a_extracao_realmente_acha_alguma_coisa(self):
        """Se a extracao parar de achar nada, o teste acima passa vazio e mente."""
        achadas = self._rotas_do_html()
        self.assertTrue(achadas)
        self.assertIn("/api/dados", achadas)

    def test_a_tela_nao_chama_mais_as_rotas_amputadas(self):
        html = (Path(__file__).parent / "index.html").read_text(encoding="utf-8")
        # `fetch(` e `src=` sao os dois jeitos pelos quais a tela alcancava o
        # que foi removido — o segundo era o quadro do grafo.
        for morta in ("/api/acao", "/api/execucao", "/api/grafo", "/grafo/"):
            with self.subTest(rota=morta):
                self.assertNotIn('fetch("%s' % morta, html)
                self.assertNotIn('src = "%s"' % morta, html)


if __name__ == "__main__":
    unittest.main(verbosity=0)
