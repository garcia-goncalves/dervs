# -*- coding: utf-8 -*-
"""Testes da camada pesada — a auditoria de dependencia.

Este arquivo nasceu de um defeito de 26/08/2026: `subprocess.run(["npm",
"audit", "--json"], shell=True)`. No Windows funciona por acidente; em Linux o
shell recebe SO o primeiro item da lista e joga o resto fora — roda `npm` puro,
que imprime a ajuda, que nao e JSON, que cai no `except`, que devolve lista
vazia. "Nenhuma dependencia insegura", com cara de auditoria feita.

    python test_coletar_pesado.py
"""
from __future__ import annotations

import ast
import json
import unittest

import coletar_pesado


class ArgvDoNpm(unittest.TestCase):
    """Os argumentos precisam CHEGAR ao npm nos dois sistemas."""

    def test_em_linux_e_a_lista_crua(self):
        self.assertEqual(coletar_pesado.argv_npm(windows=False),
                         ["npm", "audit", "--json"])

    def test_no_windows_passa_pelo_cmd_porque_npm_e_um_cmd(self):
        # Mesmo desenho do acao_vscode() em servir.py: o cmd resolve o .cmd, e
        # cada argumento continua sendo argumento — nunca texto de comando.
        self.assertEqual(coletar_pesado.argv_npm(windows=True),
                         ["cmd", "/c", "npm", "audit", "--json"])

    def test_os_dois_terminam_pedindo_json(self):
        for windows in (True, False):
            with self.subTest(windows=windows):
                self.assertEqual(coletar_pesado.argv_npm(windows=windows)[-1], "--json")


class InterpretaAudit(unittest.TestCase):
    """Ler a saida do npm audit. None e vazio dizem coisas opostas."""

    def _saida(self, vulns):
        return json.dumps({"vulnerabilities": vulns})

    def test_pega_o_grave_que_tem_conserto(self):
        texto = self._saida({"lodash": {"severity": "high", "fixAvailable": True}})
        self.assertEqual(coletar_pesado.interpreta_audit(texto), ["lodash"])

    def test_ignora_o_que_nao_e_grave(self):
        texto = self._saida({"lodash": {"severity": "low", "fixAvailable": True}})
        self.assertEqual(coletar_pesado.interpreta_audit(texto), [])

    def test_ignora_grave_sem_conserto_disponivel(self):
        # Pendencia sem conserto e estatistica, nao tarefa.
        texto = self._saida({"lodash": {"severity": "critical", "fixAvailable": False}})
        self.assertEqual(coletar_pesado.interpreta_audit(texto), [])

    def test_auditoria_limpa_e_lista_vazia_NAO_e_None(self):
        # Este e o caso honesto de "medi e nao achei nada".
        self.assertEqual(coletar_pesado.interpreta_audit(self._saida({})), [])

    def test_saida_que_nao_e_json_e_None_e_nao_lista_vazia(self):
        # Era exatamente isto que acontecia em Linux: a ajuda do npm.
        ajuda = "npm <command>\n\nUsage:\n\nnpm install\n"
        self.assertIsNone(coletar_pesado.interpreta_audit(ajuda))

    def test_saida_vazia_e_None(self):
        self.assertIsNone(coletar_pesado.interpreta_audit(""))

    def test_json_sem_a_chave_de_vulnerabilidade_e_None(self):
        # npm respondeu, mas nao com um relatorio de auditoria. Nao medimos.
        self.assertIsNone(coletar_pesado.interpreta_audit('{"erro": "sem rede"}'))

    def test_nao_confunde_medido_vazio_com_nao_medido(self):
        medido = coletar_pesado.interpreta_audit(self._saida({}))
        nao_medido = coletar_pesado.interpreta_audit("lixo")
        self.assertIsNotNone(medido)
        self.assertIsNone(nao_medido)
        self.assertNotEqual(medido, nao_medido)


class NadaDeShellTrue(unittest.TestCase):
    """A trava contra o defeito voltar."""

    def test_o_arquivo_nao_usa_shell_True(self):
        # Le a arvore do codigo, nao o texto: assim o comentario que EXPLICA o
        # defeito nao dispara o alarme, e nenhuma chamada real escapa.
        with open(coletar_pesado.__file__, encoding="utf-8") as f:
            arvore = ast.parse(f.read())
        culpadas = [n.lineno for n in ast.walk(arvore)
                    if isinstance(n, ast.Call)
                    for k in n.keywords
                    if k.arg == "shell" and getattr(k.value, "value", None) is True]
        self.assertEqual(culpadas, [],
                         "shell=True descarta os argumentos em Linux")


if __name__ == "__main__":
    unittest.main(verbosity=2)
