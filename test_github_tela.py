# -*- coding: utf-8 -*-
"""A tela "A sua conta do GitHub" com varias contas conectadas (06/10/2026).

O que a tela nao pode fazer, e nenhum teste de "o botao existe" pega:

  - mostrar o NUMERO da instalacao no lugar do nome da conta;
  - montar link para fora do github.com (o endereco vem do servidor, e o nome
    da conta vem do GitHub: dado de fora, so `textContent` e link filtrado);
  - esconder as contas de quem tem mais de uma.

A funcao `porta()` e EXECUTADA em node com um DOM de mentira; sem node os casos
de comportamento sao pulados e os de texto continuam.

    python test_github_tela.py
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
JS = (RAIZ / "assets" / "painel.js").read_text(encoding="utf-8")


def _roda_porta(lista):
    node = shutil.which("node")
    if not node:
        return None
    ini = JS.index("function porta(")
    fim = JS.index("\n}\n", ini) + 3
    prog = r"""
function marcaDaPorta() { return mkel("marca"); }
function mkel(tag) {
  return { tag, className: "", textContent: "", href: "", dataset: {}, filhos: [],
           append(...x) { this.filhos.push(...x); },
           setAttribute() {}, addEventListener() {} };
}
const document = { createElement: mkel };
""" + JS[ini:fim] + r"""
function achata(n) {
  if (typeof n === "string") return [{ tag: "#texto", textContent: n, filhos: [] }];
  return [n].concat((n.filhos || []).flatMap(achata));
}
const cartao = porta({ titulo: "t", estado: "conectado", resumo: "r",
                       lista: %s });
const todos = achata(cartao);
console.log(JSON.stringify({
  textos: todos.map((n) => n.textContent).filter(Boolean),
  links: todos.filter((n) => n.tag === "a").map((n) => n.href) }));
""" % json.dumps(lista)
    r = subprocess.run([node, "-"], input=prog, capture_output=True, text=True,
                       timeout=30, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


class AListaDeContasMostraNomeELinkSeguro(unittest.TestCase):
    def setUp(self):
        if not shutil.which("node"):
            self.skipTest("sem node")

    def test_mostra_o_nome_e_o_detalhe_de_cada_conta(self):
        r = _roda_porta([
            {"texto": "thi-garcia (pessoal)", "detalhe": "mediu 6 repositórios",
             "link": {"rotulo": "escolher", "url":
                      "https://github.com/settings/installations/1"}},
            {"texto": "garcia-goncalves (organização)", "detalhe": "",
             "link": None}])
        juntos = " | ".join(r["textos"])
        self.assertIn("thi-garcia (pessoal)", juntos)
        self.assertIn("garcia-goncalves (organização)", juntos)
        self.assertIn("mediu 6 repositórios", juntos)
        self.assertEqual(["https://github.com/settings/installations/1"],
                         r["links"])

    def test_link_fora_do_github_nao_e_montado(self):
        for ruim in ("javascript:alert(1)", "http://github.com/x",
                     "https://github.com.evil.com/x", "//github.com/x",
                     "https://evil.com/https://github.com/"):
            r = _roda_porta([{"texto": "x", "link":
                              {"rotulo": "ir", "url": ruim}}])
            self.assertEqual([], r["links"], ruim)

    def test_sem_lista_nao_desenha_lista(self):
        self.assertEqual([], _roda_porta([])["links"])


class OTextoDaPortaDoGithub(unittest.TestCase):
    def trecho(self):
        ini = JS.index("PORTA 2 — a conta do GitHub")
        return JS[ini:JS.index("PORTA 3", ini)]

    def test_o_botao_diz_conectar_outra_conta_e_ha_o_de_procurar(self):
        t = self.trecho()
        self.assertIn("Conectar outra conta do GitHub", t)
        self.assertIn("Procurar minhas contas", t)
        self.assertIn("procurarContasDoGithub", t)

    def test_a_tela_le_a_lista_do_servidor_e_nao_so_um_numero(self):
        t = self.trecho()
        self.assertIn("GITHUB.instalacoes", t)
        self.assertIn("conta_login", t)
        self.assertIn("gerenciar_url", t)

    def test_nada_de_innerhtml_no_trecho_nem_na_funcao_porta(self):
        ini = JS.index("function porta(")
        self.assertNotIn("innerHTML", self.trecho())
        self.assertNotIn("innerHTML", JS[ini:JS.index("\n}\n", ini)])

    def test_a_chamada_de_procurar_vai_pela_funcao_que_leva_o_token(self):
        i = JS.index("async function procurarContasDoGithub")
        corpo = JS[i:JS.index("\n}\n", i)]
        self.assertIn('escrever("/api/github/procurar")', corpo)

    def test_sem_conversao_de_numero_proibida(self):
        self.assertIsNone(re.search(r"Number\(|parseInt\(", self.trecho()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
