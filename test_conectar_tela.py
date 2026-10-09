# -*- coding: utf-8 -*-
"""A tela Conectar (entrega A do "Conectar simples") -- so a casca da tela.

MOTIVO: o servidor e o computador estao provados por outros arquivos. O que
nenhum deles prova e o que o DONO ve. Mentiras possiveis desta tela, e nenhuma
e vista por um teste "o botao existe":

  - o 403 de pagina velha cair num "tente de novo" que falharia de novo;
  - "0 projetos" escrito para um computador que ainda nem mediu;
  - a chave "Mostrar no painel" mudar de posicao sem o servidor ter aceito;
  - um site "fora do ar" onde a medicao simplesmente nao aconteceu;
  - texto vindo de OUTRO computador, de OUTRO repositorio ou do GitHub entrar
    como HTML.

As funcoes de montagem sao EXECUTADAS (node, com um DOM de mentira), como em
`test_voz_tela.py`; sem node os casos de comportamento sao pulados e os de
texto continuam. Cada guarda foi sabotada de proposito.

    python test_conectar_tela.py
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

AQUI = Path(__file__).parent
HTML = (AQUI / "index.html").read_text(encoding="utf-8")
JS = (AQUI / "assets" / "painel.js").read_text(encoding="utf-8")
CSS = (AQUI / "assets" / "painel.css").read_text(encoding="utf-8")
CORTINA = (AQUI / "assets" / "cortina.js").read_text(encoding="utf-8")


def sem_comentarios(js: str) -> str:
    js = re.sub(r"/\*.*?\*/", "", js, flags=re.S)
    return re.sub(r"(?m)^\s*//[^\n]*$", "", js)


def funcao(nome: str) -> str:
    """O texto de uma funcao de primeiro nivel do painel.js (ate o `}` na coluna 0)."""
    m = re.search(r"^(?:async )?function %s\(.*?\n}\n" % re.escape(nome), JS,
                  re.S | re.M)
    assert m, "funcao %s nao encontrada em painel.js" % nome
    return m.group(0)


def constante(nome: str) -> str:
    """Uma `const NOME = ...;` de primeiro nivel (ate o `;` que fecha a linha)."""
    m = re.search(r"^const %s = .*?;\n" % re.escape(nome), JS, re.S | re.M)
    assert m, "constante %s nao encontrada em painel.js" % nome
    return m.group(0)


# --------------------------------------------------------------- o DOM de mentira
PRELUDIO = r"""
const FOCO = { atual: null };
const REG = {};
class No {
  constructor(tag) {
    this.tag = tag; this.className = ""; this._texto = ""; this.filhos = [];
    this.attrs = {}; this.dataset = {}; this.hidden = false; this.ouvintes = {};
    this.disabled = false; this.checked = false; this.value = ""; this.open = false;
    this.isConnected = true; this.href = ""; this.download = ""; this.rel = "";
    this.target = ""; this.type = ""; this.id = ""; this.name = "";
    const eu = this;
    this.classList = {
      add(c) { if (!eu.className.split(" ").includes(c)) eu.className = (eu.className + " " + c).trim(); },
      remove(c) { eu.className = eu.className.split(" ").filter(x => x && x !== c).join(" "); },
      contains(c) { return eu.className.split(" ").includes(c); }
    };
  }
  set textContent(v) { this._texto = String(v); this.filhos = []; }
  get textContent() {
    return this._texto + this.filhos.map(f => typeof f === "string" ? f : f.textContent).join("");
  }
  append(...x) { this.filhos.push(...x); }
  replaceChildren(...x) { this._texto = ""; this.filhos = x; }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; }
  removeAttribute(k) { delete this.attrs[k]; }
  addEventListener(t, f) { (this.ouvintes[t] = this.ouvintes[t] || []).push(f); }
  async disparar(t, ev) { for (const f of (this.ouvintes[t] || [])) await f(ev || { preventDefault() {} }); }
  async clicar() { await this.disparar("click"); }
  focus() { FOCO.atual = this; }
  remove() {}
}
const document = { createElement: (t) => new No(t), activeElement: null };
const $ = (s) => (REG[s] = REG[s] || new No("reg"));
function todos(n) {
  if (typeof n === "string") return [];
  return [n].concat((n.filhos || []).flatMap(todos));
}
function acha(n, f) { return todos(n).find(f) || null; }
function achaTodos(n, f) { return todos(n).filter(f); }
"""


def node_ou_pula(caso: unittest.TestCase) -> str:
    node = shutil.which("node")
    if not node:
        caso.skipTest("sem node")
    return node


def roda(caso: unittest.TestCase, fontes: list[str], script: str):
    """Roda `fontes` (trechos do painel.js) mais `script` com o DOM de mentira.

    O script imprime UM json no fim (`console.log(JSON.stringify(...))`)."""
    node = node_ou_pula(caso)
    prog = PRELUDIO + "\n".join(fontes) + "\n(async () => {\n" + script + "\n})();\n"
    r = subprocess.run([node, "-"], input=prog, capture_output=True, text=True,
                       timeout=30, encoding="utf-8")
    caso.assertEqual(r.returncode, 0, r.stderr)
    return json.loads(r.stdout.strip().splitlines()[-1])


# ============================================================ E3-1: a faixa
def fontes_da_faixa() -> list[str]:
    return ["let PAGINA_VELHA = false;\n", "const TOKEN = 't';\n",
            funcao("recado"), funcao("abrirFaixaPaginaVelha"), funcao("escrever")]


PRELUDIO_DA_REDE = r"""
let RESPOSTAS = [];
globalThis.fetch = async () => RESPOSTAS.shift();
globalThis.location = { reloaded: 0, reload() { this.reloaded++; } };
globalThis.setTimeout = (f) => 0;
globalThis.clearTimeout = () => {};
function resposta(status, corpo) {
  return {
    status, ok: status >= 200 && status < 300,
    json: async () => { if (corpo === undefined) throw new Error("sem json"); return corpo; },
    clone() { return resposta(status, corpo); }
  };
}
"""


class AFaixaDePaginaVelha(unittest.TestCase):
    def rode(self, respostas, script):
        return roda(self, fontes_da_faixa(),
                    PRELUDIO_DA_REDE + "RESPOSTAS = " + respostas + ";\n" + script)

    def test_403_com_o_motivo_abre_a_faixa_com_alerta_e_foco(self):
        r = self.rode('[resposta(403, {erro: "x", motivo: "pagina_velha"})]', r"""
const resp = await escrever("/api/silenciar", { id: "a" });
const faixa = $("#faixa-pagina-velha");
const alerta = acha(faixa, n => n.attrs.role === "alert");
const botao = acha(faixa, n => n.tag === "button");
console.log(JSON.stringify({
  status: resp.status, tem_alerta: !!alerta, texto: faixa.textContent,
  botao: botao && botao.textContent, foco_no_botao: FOCO.atual === botao,
  corpo_ainda_legivel: (await resp.json()).motivo }));
""")
        self.assertEqual(r["status"], 403)
        self.assertTrue(r["tem_alerta"])
        self.assertIn("Esta página ficou desatualizada.", r["texto"])
        self.assertIn("O que você acabou de clicar não foi feito.", r["texto"])
        self.assertEqual(r["botao"], "Recarregar")
        self.assertTrue(r["foco_no_botao"])
        self.assertEqual(r["corpo_ainda_legivel"], "pagina_velha")

    def test_o_botao_recarrega_a_pagina(self):
        r = self.rode('[resposta(403, {motivo: "pagina_velha"})]', r"""
await escrever("/x");
await acha($("#faixa-pagina-velha"), n => n.tag === "button").clicar();
console.log(JSON.stringify({ recarregou: location.reloaded }));
""")
        self.assertEqual(r["recarregou"], 1)

    def test_a_segunda_recusa_nao_empilha_outra_faixa(self):
        r = self.rode('[resposta(403, {motivo: "pagina_velha"}), '
                      'resposta(403, {motivo: "pagina_velha"})]', r"""
await escrever("/a"); await escrever("/b");
const faixa = $("#faixa-pagina-velha");
console.log(JSON.stringify({
  alertas: achaTodos(faixa, n => n.attrs.role === "alert").length,
  botoes: achaTodos(faixa, n => n.tag === "button").length }));
""")
        self.assertEqual(r, {"alertas": 1, "botoes": 1})

    def test_403_de_outro_motivo_nao_abre_faixa(self):
        for corpo in ('{erro: "entre de novo"}', '{erro: "origem nao permitida"}',
                      "undefined"):
            with self.subTest(corpo=corpo):
                r = self.rode("[resposta(403, %s)]" % corpo, r"""
const resp = await escrever("/a");
console.log(JSON.stringify({ filhos: $("#faixa-pagina-velha").filhos.length,
                             status: resp.status }));
""")
                self.assertEqual(r, {"filhos": 0, "status": 403})

    def test_resposta_que_nao_e_403_passa_intacta(self):
        r = self.rode('[resposta(200, {ok: true})]', r"""
const resp = await escrever("/a");
console.log(JSON.stringify({ ok: resp.ok, d: await resp.json(),
                             filhos: $("#faixa-pagina-velha").filhos.length }));
""")
        self.assertEqual(r, {"ok": True, "d": {"ok": True}, "filhos": 0})

    def test_com_a_faixa_aberta_o_recado_de_erro_nao_promete_tentar_de_novo(self):
        r = self.rode('[resposta(403, {motivo: "pagina_velha"})]', r"""
await escrever("/a");
recado("não conseguimos adiar. Tente de novo.", true);
const ruim = $("#recado").textContent;
recado("adiado por 24 horas.");
console.log(JSON.stringify({ ruim, bom: $("#recado").textContent }));
""")
        self.assertEqual(r["ruim"], "Não foi feito. Veja o aviso no alto da página.")
        # recado de SUCESSO nao e trocado: so o de erro mente com a faixa aberta.
        self.assertEqual(r["bom"], "adiado por 24 horas.")

    def test_sem_a_faixa_o_recado_de_erro_e_o_de_quem_chamou(self):
        r = self.rode("[]", r"""
recado("não conseguimos adiar. Tente de novo.", true);
console.log(JSON.stringify({ t: $("#recado").textContent }));
""")
        self.assertEqual(r["t"], "não conseguimos adiar. Tente de novo.")

    def test_o_literal_do_motivo_mora_dentro_de_escrever(self):
        """Vale tambem sem node: o servidor e a tela combinam este valor."""
        self.assertIn('motivo === "pagina_velha"', funcao("escrever"))
        self.assertIn("abrirFaixaPaginaVelha()", funcao("escrever"))

    def test_so_o_motivo_exato_abre_a_faixa_e_o_status_tambem_conta(self):
        corpo = funcao("escrever")
        self.assertIn("r.status === 403", corpo)

    def test_a_faixa_tem_lugar_no_html_sem_estilo_embutido(self):
        i = HTML.index('id="faixa-pagina-velha"')
        marca = HTML[HTML.rindex("<", 0, i):HTML.index(">", i) + 1]
        self.assertNotIn("style=", marca)
        self.assertLess(HTML.index("<main"), i, "a faixa tem de ficar dentro do <main>")

    def test_a_classe_da_faixa_existe_nos_dois_lados_e_nao_usa_cor_de_estado(self):
        self.assertIn("faixa--pagina-velha", JS)
        css = sem_comentarios(CSS)
        self.assertIn(".faixa--pagina-velha", css)
        ini = css.index("#faixa-pagina-velha")
        bloco = css[ini:css.index(".freio__texto", ini)]
        self.assertGreater(len(bloco), 200)
        self.assertNotIn("--estado-", bloco)
        self.assertIn("position: sticky", bloco)
        self.assertIn("z-index: 60", bloco)   # acima do .freio (50)

    def test_a_faixa_nao_tem_botao_de_fechar(self):
        self.assertNotRegex(sem_comentarios(funcao("abrirFaixaPaginaVelha")),
                            r'"(Fechar|Dispensar|OK)"')


if __name__ == "__main__":
    unittest.main(verbosity=2)
