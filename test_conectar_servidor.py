# -*- coding: utf-8 -*-
"""Conectar simples, entrega A: o lado do SERVIDOR.

    python test_conectar_servidor.py

Contratos C1 a C14 de `docs/superpowers/plans/dervs-conectar-simples-a.md`.
"""
from __future__ import annotations

import inspect
import json
import os
import unittest

os.environ.setdefault("DERVS_AMBIENTE", "local")
os.environ.setdefault("DERVS_COFRE",
                      "chave-de-teste-que-nao-e-segredo-nenhum-0123456789")

import banco     # noqa: E402
import servir    # noqa: E402
from test_servir import BaseServidorDeVerdade  # noqa: E402

FRASE = "recarregue a pagina (token vencido)"


class APaginaVelhaTemMotivo(BaseServidorDeVerdade):
    """C1: todo 403 de anti-CSRF vencido carrega `motivo: pagina_velha`."""

    def test_toda_rota_de_escrita_do_dono_devolve_o_motivo(self):
        cookies, _csrf = self.sessao_e_token()
        vistas = []
        for caminho, rota in servir.ROTAS.items():
            if rota.metodo != "POST" or rota.acesso != "dado":
                continue
            r = self.pedir(caminho, "POST", {}, cookies=cookies,
                           cabecalhos={"X-Token": "token-errado"})
            vistas.append(caminho)
            self.assertEqual(403, r.status, caminho)
            corpo = json.loads(r.corpo)
            self.assertEqual("pagina_velha", corpo.get("motivo"), caminho)
            self.assertEqual(FRASE, corpo.get("erro"), caminho)
        self.assertGreater(len(vistas), 10)

    def test_os_outros_403_nao_ganham_motivo(self):
        cookies, csrf = self.sessao_e_token()
        r = self.pedir("/api/silenciar", "POST", {}, cookies=cookies,
                       com_origem=False, cabecalhos={"X-Token": csrf})
        self.assertEqual(403, r.status)
        self.assertNotIn("motivo", json.loads(r.corpo))

    def test_a_frase_mora_num_lugar_so(self):
        self.assertEqual(1, inspect.getsource(servir).count("token vencido"))


if __name__ == "__main__":
    unittest.main()
