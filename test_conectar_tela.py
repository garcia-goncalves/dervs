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
const $ = (s) => {
  if (!REG[s]) { REG[s] = new No("reg"); if (s[0] === "#") REG[s].id = s.slice(1); }
  return REG[s];
};
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


# ===================================== E3-2: este computador e autorizar
def fontes(*nomes: str, consts: tuple[str, ...] = ()) -> list[str]:
    return [constante(c) for c in consts] + [funcao(n) for n in nomes]


PRELUDIO_DE_TEMPO = r"""
const agora = () => Date.now();
const ha = (s) => new Date(Date.now() - s * 1000).toISOString();
globalThis.setInterval = (f) => 77;
globalThis.clearInterval = () => {};
"""


class ARotaLeOsParametros(unittest.TestCase):
    def rota(self, hash_):
        return roda(self, fontes("rota"), "globalThis.location = { hash: %s };\n"
                    "console.log(JSON.stringify(rota()));" % json.dumps(hash_))

    def test_conectar_com_autorizar(self):
        r = self.rota("#/conectar?autorizar=K7M4-2QXP")
        self.assertEqual(r["tela"], "conectar")
        self.assertEqual(r["autorizar"], "K7M4-2QXP")

    def test_o_resto_da_rota_segue_igual(self):
        self.assertEqual(self.rota("#/projeto/clinica-agenda"),
                         {"tela": "projeto", "alvo": "clinica-agenda", "autorizar": ""})
        self.assertEqual(self.rota("")["tela"], "painel")
        self.assertEqual(self.rota("#/conta/entrada")["alvo"], "entrada")

    def test_o_parametro_nao_vaza_para_o_nome_da_tela_nem_para_o_alvo(self):
        r = self.rota("#/projeto/x?autorizar=K7M4-2QXP")
        self.assertEqual((r["tela"], r["alvo"]), ("projeto", "x"))

    def test_conectar_sem_parametro(self):
        self.assertEqual(self.rota("#/conectar")["autorizar"], "")


class OCodigoDeAutorizarSoAceitaOFormatoExato(unittest.TestCase):
    def codigos(self, entradas):
        return roda(self, fontes("codigoDeAutorizar"),
                    "console.log(JSON.stringify(%s.map(codigoDeAutorizar)));"
                    % json.dumps(entradas))

    def test_normaliza_caixa_espaco_e_hifen(self):
        self.assertEqual(self.codigos(["K7M4-2QXP", "k7m4 2qxp", "k7m42qxp"]),
                         ["K7M4-2QXP"] * 3)

    def test_recusa_o_que_o_servidor_recusaria(self):
        ruins = ["K7M0-2QXP", "K7MI-2QXP", "K7ML-2QXP", "K7M1-2QXP", "K7M4-2QX",
                 "K7M4-2QXPP", "", "<img src=x>", "javascript:alert(1)", "K7M4-2QX_"]
        self.assertEqual(self.codigos(ruins), [""] * len(ruins))

    def test_vazio_e_nulo_nao_estouram(self):
        r = roda(self, fontes("codigoDeAutorizar"),
                 "console.log(JSON.stringify([codigoDeAutorizar(null), "
                 "codigoDeAutorizar(undefined)]));")
        self.assertEqual(r, ["", ""])

    def test_a_cortina_usa_o_mesmo_alfabeto_do_painel(self):
        padrao = r"[2-9A-HJKMNP-Z]{8}"
        self.assertIn(padrao, funcao("codigoDeAutorizar"))
        self.assertIn(padrao, CORTINA)


def fontes_do_autorizar() -> list[str]:
    return ["const AUTORIZAR = { codigo: '', dados: null, fase: '', prazo: null, "
            "fim: 0, botao: null, focou: false };\n", "let PAGINA_VELHA = false;\n"] + [
        funcao(n) for n in ("criar", "botaoEmAcoes", "prazoEmPalavras",
                            "codigoDeAutorizar", "pintarAutorizar", "olharOPedido",
                            "autorizarPedido", "fecharAutorizar",
                            "abrirOuFecharAutorizar", "recolherAutorizar",
                            "andarOPrazoDoPedido")]


PRELUDIO_DO_AUTORIZAR = PRELUDIO_DA_REDE + r"""
globalThis.esperas = [];
function esperarMaquinaNova(onde, min, modo) { esperas.push([onde && onde.id, min, modo]); }
globalThis.history = { trocas: [], replaceState(a, b, c) { this.trocas.push(c); } };
const escrever = async (url, corpo) => { escritas.push([url, corpo]); return RESPOSTAS.shift(); };
globalThis.escritas = [];
const _fetch = globalThis.fetch;
globalThis.fetch = async (url) => { buscas.push(url); return RESPOSTAS.shift(); };
globalThis.buscas = [];
const bloco = () => $("#conectar-autorizar");
const textoDoBloco = () => bloco().textContent;
"""


class OBlocoDeAutorizar(unittest.TestCase):
    def rode(self, respostas, script):
        # `escrever` e `fetch` de mentira: o que importa e o que o bloco faz.
        return roda(self, [PRELUDIO_DO_AUTORIZAR] + fontes_do_autorizar(),
                    "RESPOSTAS = " + respostas + ";\n" + script)

    def test_pedido_valido_mostra_nome_codigo_prazo_e_o_botao(self):
        r = self.rode("[]", r"""
pintarAutorizar({ codigo: "K7M4-2QXP", maquina: "PC-ESCRITORIO", minutos: 8, estado: "esperando" });
const b = bloco();
const botao = acha(b, n => n.tag === "button");
const cod = acha(b, n => n.className === "numerao");
const titulo = acha(b, n => n.id === "autorizar-titulo");
console.log(JSON.stringify({
  oculto: b.hidden, texto: textoDoBloco(), botao: botao.textContent,
  codigo: cod.textContent, leitura: cod.attrs["aria-label"],
  foco_no_titulo: FOCO.atual === titulo, tabindex: titulo.attrs.tabindex,
  busy: b.attrs["aria-busy"] }));
""")
        self.assertFalse(r["oculto"])
        self.assertIn("O computador PC-ESCRITORIO pediu para se ligar ao seu painel", r["texto"])
        self.assertIn("Vale por mais 8 minutos.", r["texto"])
        self.assertIn("Não reconhece este computador? Não clique em nada", r["texto"])
        self.assertEqual(r["botao"], "Autorizar este computador")
        self.assertEqual(r["codigo"], "K7M4-2QXP")
        self.assertEqual(r["leitura"], "Código: K, 7, M, 4, 2, Q, X, P")
        self.assertTrue(r["foco_no_titulo"])
        self.assertEqual(r["tabindex"], "-1")
        self.assertEqual(r["busy"], "false")

    def test_o_nome_do_computador_entra_como_texto(self):
        r = self.rode("[]", r"""
pintarAutorizar({ codigo: "K7M4-2QXP", maquina: "<img src=x onerror=alert(1)>", minutos: 3, estado: "esperando" });
console.log(JSON.stringify({ texto: textoDoBloco(),
  imgs: achaTodos(bloco(), n => n.tag === "img").length }));
""")
        self.assertIn("<img src=x onerror=alert(1)>", r["texto"])
        self.assertEqual(r["imgs"], 0)

    def test_carregando_nao_tem_botao_de_autorizar(self):
        r = self.rode("[]", r"""
pintarAutorizar({ estado: "carregando" });
console.log(JSON.stringify({ texto: textoDoBloco(), busy: bloco().attrs["aria-busy"],
  botoes: achaTodos(bloco(), n => n.tag === "button").length }));
""")
        self.assertIn("Conferindo o pedido…", r["texto"])
        self.assertEqual((r["busy"], r["botoes"]), ("true", 0))

    def test_nao_existe_diz_que_venceu_e_volta_para_conectar(self):
        r = self.rode("[]", r"""
pintarAutorizar({ estado: "nao_existe" });
const botao = acha(bloco(), n => n.tag === "button");
AUTORIZAR.codigo = "K7M4-2QXP";
await botao.clicar();
console.log(JSON.stringify({ texto: textoDoBloco(), botao: botao.textContent,
  oculto: bloco().hidden, trocas: history.trocas, foco: FOCO.atual === $("#pc-titulo") }));
""")
        self.assertIn("Este pedido venceu ou não existe. Baixe o arquivo de novo e abra.", r["texto"])
        self.assertEqual(r["botao"], "Voltar para Conectar")
        self.assertTrue(r["oculto"])
        self.assertEqual(r["trocas"], ["#/conectar"])
        self.assertTrue(r["foco"])

    def test_ja_autorizado_ou_conectado_nao_tem_botao(self):
        for estado in ("autorizado", "conectado"):
            with self.subTest(estado=estado):
                r = self.rode("[]", """
pintarAutorizar({ codigo: "K7M4-2QXP", maquina: "PC", minutos: 3, estado: "%s" });
console.log(JSON.stringify({ texto: textoDoBloco(),
  botoes: achaTodos(bloco(), n => n.tag === "button").length }));
""" % estado)
                self.assertIn("Este computador já foi autorizado. Veja abaixo se ele apareceu.", r["texto"])
                self.assertEqual(r["botoes"], 0)

    def test_erro_de_rede_nao_diz_que_venceu(self):
        r = self.rode("[]", r"""
pintarAutorizar({ estado: "erro_rede" });
console.log(JSON.stringify({ texto: textoDoBloco(),
  botao: acha(bloco(), n => n.tag === "button").textContent }));
""")
        self.assertIn("Isso não quer dizer que o pedido venceu — quer dizer que não olhei.", r["texto"])
        self.assertNotIn("Este pedido venceu", r["texto"])
        self.assertEqual(r["botao"], "Tentar de novo")

    def test_olhar_o_pedido_busca_pelo_codigo_e_pinta_os_dados(self):
        r = self.rode('[resposta(200, {codigo: "K7M4-2QXP", maquina: "PC", minutos: 9, '
                      'expira_em: "x", estado: "esperando"})]', r"""
AUTORIZAR.codigo = "K7M4-2QXP";
await olharOPedido("K7M4-2QXP", false);
console.log(JSON.stringify({ buscas, botoes: achaTodos(bloco(), n => n.tag === "button").length,
  texto: textoDoBloco() }));
""")
        self.assertEqual(r["buscas"], ["/api/pedido?codigo=K7M4-2QXP"])
        self.assertEqual(r["botoes"], 1)
        self.assertIn("Vale por mais 9 minutos.", r["texto"])

    def test_404_e_400_viram_nao_existe_e_falha_de_rede_vira_erro_de_rede(self):
        for resp, esperado in (("resposta(404, {})", "venceu ou não existe"),
                               ("resposta(400, {})", "venceu ou não existe"),
                               ("resposta(500, {})", "quer dizer que não olhei")):
            with self.subTest(resp=resp):
                r = self.rode("[%s]" % resp, r"""
AUTORIZAR.codigo = "K7M4-2QXP";
await olharOPedido("K7M4-2QXP", false);
console.log(JSON.stringify({ texto: textoDoBloco() }));
""")
                self.assertIn(esperado, r["texto"])

    def test_clicar_em_autorizar_manda_so_o_codigo_e_comeca_a_espera(self):
        r = self.rode("[resposta(200, {ok: true, maquina: 'PC', ja_estava: false})]", r"""
AUTORIZAR.codigo = "K7M4-2QXP";
AUTORIZAR.dados = { codigo: "K7M4-2QXP", maquina: "PC", minutos: 5, estado: "esperando" };
pintarAutorizar(AUTORIZAR.dados);
await acha(bloco(), n => n.tag === "button").clicar();
console.log(JSON.stringify({ escritas, esperas, texto: textoDoBloco(),
  botoes: achaTodos(bloco(), n => n.tag === "button").length }));
""")
        self.assertEqual(r["escritas"], [["/api/pedido/autorizar", {"codigo": "K7M4-2QXP"}]])
        self.assertEqual(r["esperas"], [["espera-maquina", 10, None]])
        self.assertIn("Autorizado. Volte à janela preta do computador: ela termina sozinha.",
                      r["texto"])
        self.assertEqual(r["botoes"], 0)

    def test_autorizar_com_falha_devolve_o_botao_e_foca_nele(self):
        r = self.rode("[resposta(500, {})]", r"""
AUTORIZAR.codigo = "K7M4-2QXP";
AUTORIZAR.dados = { codigo: "K7M4-2QXP", maquina: "PC", minutos: 5, estado: "esperando" };
pintarAutorizar(AUTORIZAR.dados);
await acha(bloco(), n => n.tag === "button").clicar();
const b = acha(bloco(), n => n.tag === "button");
console.log(JSON.stringify({ texto: textoDoBloco(), ativo: !b.disabled,
  foco: FOCO.atual === b, esperas }));
""")
        self.assertIn("quer dizer que não olhei", r["texto"])
        self.assertTrue(r["ativo"])
        self.assertTrue(r["foco"])
        self.assertEqual(r["esperas"], [])

    def test_autorizar_404_vira_nao_existe(self):
        r = self.rode("[resposta(404, {})]", r"""
AUTORIZAR.codigo = "K7M4-2QXP";
AUTORIZAR.dados = { codigo: "K7M4-2QXP", maquina: "PC", minutos: 5, estado: "esperando" };
pintarAutorizar(AUTORIZAR.dados);
await acha(bloco(), n => n.tag === "button").clicar();
console.log(JSON.stringify({ texto: textoDoBloco() }));
""")
        self.assertIn("Este pedido venceu ou não existe", r["texto"])

    def test_pagina_velha_no_autorizar_nao_repete_o_erro(self):
        r = self.rode("[{status: 403, ok: false}]", r"""
PAGINA_VELHA = true;
AUTORIZAR.codigo = "K7M4-2QXP";
AUTORIZAR.dados = { codigo: "K7M4-2QXP", maquina: "PC", minutos: 5, estado: "esperando" };
pintarAutorizar(AUTORIZAR.dados);
await acha(bloco(), n => n.tag === "button").clicar();
console.log(JSON.stringify({ texto: textoDoBloco(),
  botoes: achaTodos(bloco(), n => n.tag === "button").length }));
""")
        self.assertNotIn("quer dizer que não olhei", r["texto"])
        self.assertEqual(r["botoes"], 1)

    def test_a_pagina_aberta_sem_parametro_esconde_o_bloco(self):
        r = self.rode("[]", r"""
pintarAutorizar({ estado: "carregando" });
abrirOuFecharAutorizar("");
console.log(JSON.stringify({ oculto: bloco().hidden }));
""")
        self.assertTrue(r["oculto"])

    def test_codigo_torto_no_endereco_vira_nao_existe_sem_ir_ao_servidor(self):
        r = self.rode("[]", r"""
abrirOuFecharAutorizar("<script>");
console.log(JSON.stringify({ texto: textoDoBloco(), buscas }));
""")
        self.assertIn("venceu ou não existe", r["texto"])
        self.assertEqual(r["buscas"], [])

    def test_recolher_so_depois_de_autorizado(self):
        r = self.rode("[]", r"""
pintarAutorizar({ codigo: "K7M4-2QXP", maquina: "PC", minutos: 5, estado: "esperando" });
recolherAutorizar();
const antes = bloco().hidden;
pintarAutorizar({ estado: "sucesso" });
recolherAutorizar();
console.log(JSON.stringify({ antes, depois: bloco().hidden, foco: FOCO.atual === $("#pc-titulo") }));
""")
        self.assertFalse(r["antes"])
        self.assertTrue(r["depois"])
        self.assertTrue(r["foco"])

    def test_o_repintar_do_minuto_nao_vai_a_rede_e_so_anda_o_prazo(self):
        """GET /api/pedido tem balcao de 20 por origem em 15 minutos: uma
        leitura por pagina, nunca sondagem."""
        r = self.rode('[resposta(200, {codigo: "K7M4-2QXP", maquina: "PC", minutos: 5, estado: "esperando"})]', r"""
abrirOuFecharAutorizar("K7M4-2QXP");
await new Promise(f => setImmediate(f));
const botao = acha(bloco(), n => n.tag === "button");
for (let i = 0; i < 5; i++) abrirOuFecharAutorizar("k7m4-2qxp");
const _agora = Date.now; Date.now = () => _agora() + 2 * 60000 + 500;
abrirOuFecharAutorizar("K7M4-2QXP");
console.log(JSON.stringify({ buscas: buscas.length, mesmo_botao: acha(bloco(), n => n.tag === "button") === botao,
  texto: textoDoBloco() }));
""")
        self.assertEqual(r["buscas"], 1)
        self.assertTrue(r["mesmo_botao"])
        self.assertIn("Vale por mais 2 minutos.", r["texto"])

    def test_um_minuto_e_menos_de_um_minuto(self):
        r = roda(self, fontes("prazoEmPalavras"),
                 "console.log(JSON.stringify([0,1,2,undefined].map(prazoEmPalavras)));")
        self.assertEqual(r, ["menos de um minuto", "mais 1 minuto", "mais 2 minutos",
                             "menos de um minuto"])


class OLinkDeBaixarEOCartaoDoComputador(unittest.TestCase):
    """O botao e um LINK (GET), nao um botao que chama `escrever`."""

    def fontes(self):
        return ["let COMPUTADORES = null, COMPUTADORES_LIDO_EM = null, "
                "COMPUTADORES_FALHOU = false;\n"] + fontes(
            "haQuanto", "criar", "marcaDaPorta", "linkDeBaixar", "estadoDosComputadores",
            "situacaoDoComputador", "pintarEsteComputador", "linhaDeComputador",
            consts=("ESTADO_DA_PORTA", "COMPUTADOR_CALADO_APOS_MS"))

    PRELUDIO = PRELUDIO_DE_TEMPO + r"""
const esperas = [], carregou = [], confirmou = [];
function esperarMaquinaNova(onde, min, modo) { esperas.push([onde && onde.id, min]); }
function confirmar(o, f) { confirmou.push(o); }
function carregarComputadores() { carregou.push(1); }
function autorizarComputador() {} function removerComputador() {}
const card = () => $("#cartao-computador");
function acoes() { return $("#pc-acoes").filhos; }
"""

    def rode(self, script):
        return roda(self, [self.PRELUDIO] + self.fontes(), script)

    def test_o_link_aponta_para_o_arquivo_e_se_chama_conectar_dervs_cmd(self):
        r = self.rode(r"""
const a = linkDeBaixar("Conectar este computador", false);
console.log(JSON.stringify({ tag: a.tag, href: a.href, download: a.download,
  classe: a.className, texto: a.textContent }));
""")
        self.assertEqual(r["tag"], "a")
        self.assertEqual(r["href"], "/api/conectar.cmd")
        self.assertEqual(r["download"], "conectar-dervs.cmd")
        self.assertEqual(r["classe"], "botao")
        self.assertEqual(r["texto"], "Conectar este computador")

    def test_o_clique_no_link_comeca_a_espera_sem_cancelar_o_download(self):
        r = self.rode(r"""
const a = linkDeBaixar("x", false);
let cancelou = false;
await a.disparar("click", { preventDefault() { cancelou = true; } });
console.log(JSON.stringify({ esperas, cancelou }));
""")
        self.assertEqual(r["esperas"], [["espera-maquina", 10]])
        self.assertFalse(r["cancelou"])

    def test_antes_da_leitura_diz_olhando_e_o_botao_ja_funciona(self):
        r = self.rode(r"""
pintarEsteComputador();
console.log(JSON.stringify({ resumo: $("#pc-resumo").textContent, busy: card().attrs["aria-busy"],
  marca: $("#pc-marca").textContent, botoes: acoes().map(b => b.textContent) }));
""")
        self.assertEqual(r["resumo"], "Olhando os computadores desta conta…")
        self.assertEqual(r["busy"], "true")
        self.assertIn("não deu para conferir", r["marca"])
        self.assertEqual(r["botoes"], ["Conectar este computador"])

    def test_leitura_que_falhou_nao_diz_nenhum_computador(self):
        r = self.rode(r"""
COMPUTADORES_FALHOU = true;
pintarEsteComputador();
const antes = { resumo: $("#pc-resumo").textContent,
                botoes: acoes().map(b => b.textContent) };
await acoes()[1].clicar();
console.log(JSON.stringify({ antes, carregou, falhou: COMPUTADORES_FALHOU }));
""")
        self.assertIn("Isso não quer dizer que nenhum esteja ligado — quer dizer que não olhei.",
                      r["antes"]["resumo"])
        self.assertNotIn("Nenhum computador está ligado", r["antes"]["resumo"])
        self.assertEqual(r["antes"]["botoes"], ["Conectar este computador", "Tentar de novo"])
        self.assertEqual(r["carregou"], [1])
        self.assertFalse(r["falhou"])

    def test_lista_vazia_e_nao_conectado(self):
        r = self.rode(r"""
COMPUTADORES = []; COMPUTADORES_LIDO_EM = ha(1);
pintarEsteComputador();
console.log(JSON.stringify({ resumo: $("#pc-resumo").textContent, marca: $("#pc-marca").textContent,
  lista_oculta: $("#pc-lista").hidden, busy: card().attrs["aria-busy"] }));
""")
        self.assertIn("Nenhum computador está ligado ao DERVS ainda.", r["resumo"])
        self.assertIn("não conectado", r["marca"])
        self.assertTrue(r["lista_oculta"])
        self.assertEqual(r["busy"], "false")

    def test_conectado_com_projetos_diz_quantos_e_quando(self):
        r = self.rode(r"""
COMPUTADORES = [{ id: 1, nome: "PC-ESCRITORIO", visto_em: ha(12), relatado_em: ha(12),
  projetos: 7, executa: false, so_mede: true, projetos_vistos: [] }];
COMPUTADORES_LIDO_EM = ha(1);
pintarEsteComputador();
console.log(JSON.stringify({ marca: $("#pc-marca").textContent, carimbo: $("#pc-carimbo").textContent,
  botoes: acoes().map(b => [b.textContent, b.className]), lista_oculta: $("#pc-lista").hidden }));
""")
        self.assertIn("Conectado — achei 7 projetos", r["marca"])
        self.assertEqual(r["carimbo"], "PC-ESCRITORIO deu notícia há 12 segundos.")
        self.assertEqual(r["botoes"], [["Conectar outro computador", "botao botao--secundario"]])
        self.assertFalse(r["lista_oculta"])

    def test_um_projeto_so_fica_no_singular(self):
        r = self.rode(r"""
COMPUTADORES = [{ id: 1, nome: "PC", visto_em: ha(5), relatado_em: ha(5), projetos: 1, so_mede: true }];
COMPUTADORES_LIDO_EM = ha(1);
pintarEsteComputador();
console.log(JSON.stringify({ marca: $("#pc-marca").textContent }));
""")
        self.assertIn("achei 1 projeto", r["marca"])
        self.assertNotIn("projetos", r["marca"])

    def test_apareceu_e_ainda_nao_mediu_nunca_escreve_zero(self):
        r = self.rode(r"""
COMPUTADORES = [{ id: 1, nome: "PC", visto_em: ha(5), relatado_em: null, projetos: 0, so_mede: true }];
COMPUTADORES_LIDO_EM = ha(1);
pintarEsteComputador();
console.log(JSON.stringify({ resumo: $("#pc-resumo").textContent, marca: $("#pc-marca").textContent,
  linha: $("#lista-computadores").textContent }));
""")
        self.assertIn("O computador apareceu e ainda não mandou a primeira medição.", r["resumo"])
        self.assertIn("Isso leva menos de um minuto.", r["resumo"])
        self.assertNotRegex(r["marca"] + r["resumo"] + r["linha"], r"\b0 projeto")
        self.assertIn("ainda não mandou a primeira medição", r["linha"])

    def test_mediu_e_nao_achou_nada_oferece_baixar_de_novo(self):
        r = self.rode(r"""
COMPUTADORES = [{ id: 1, nome: "PC", visto_em: ha(5), relatado_em: ha(5), projetos: 0, so_mede: true }];
COMPUTADORES_LIDO_EM = ha(1);
pintarEsteComputador();
console.log(JSON.stringify({ resumo: $("#pc-resumo").textContent, botoes: acoes().map(b => b.textContent) }));
""")
        self.assertIn("Olhei a pasta que você escolheu e não achei nenhum projeto com histórico de versões.",
                      r["resumo"])
        self.assertNotIn("C:\\", r["resumo"])    # o servidor nao sabe a pasta
        self.assertEqual(r["botoes"], ["Baixar de novo"])

    def test_computador_mudo_nao_e_conectado_e_nada_e_apagado(self):
        r = self.rode(r"""
COMPUTADORES = [{ id: 1, nome: "PC-ESCRITORIO", visto_em: ha(3 * 3600), relatado_em: ha(3 * 3600),
  projetos: 7, so_mede: true }];
COMPUTADORES_LIDO_EM = ha(1);
pintarEsteComputador();
console.log(JSON.stringify({ resumo: $("#pc-resumo").textContent, marca: $("#pc-marca").textContent,
  linhas: $("#lista-computadores").filhos.length }));
""")
        self.assertIn("O PC-ESCRITORIO não dá notícia há 3 horas.", r["resumo"])
        self.assertIn("Os projetos dele continuam no painel, parados no último carimbo.", r["resumo"])
        self.assertIn("não deu para conferir", r["marca"])
        self.assertEqual(r["linhas"], 1)

    def test_mudo_ha_semanas_diz_desde_a_data(self):
        r = self.rode(r"""
COMPUTADORES = [{ id: 1, nome: "PC", visto_em: ha(40 * 86400), relatado_em: null, projetos: 0 }];
COMPUTADORES_LIDO_EM = ha(1);
pintarEsteComputador();
console.log(JSON.stringify({ resumo: $("#pc-resumo").textContent }));
""")
        self.assertRegex(r["resumo"], r"não dá notícia desde \d\d/\d\d/\d{4}\.")

    def test_a_linha_so_mede_nao_tem_deixar_consertar_aqui(self):
        r = self.rode(r"""
const li = linhaDeComputador({ id: 3, nome: "PC-ESCRITORIO", visto_em: ha(12), relatado_em: ha(12),
  projetos: 2, executa: false, so_mede: true, projetos_vistos: [] });
const botoes = achaTodos(li, n => n.tag === "button").map(b => b.textContent);
console.log(JSON.stringify({ botoes, texto: li.textContent }));
""")
        self.assertNotIn("Deixar consertar aqui", r["botoes"])
        self.assertIn("Remover", r["botoes"])
        self.assertIn("Este computador só acompanha os projetos. Ele não faz alterações.", r["texto"])
        self.assertIn("Só mede", r["texto"])

    def test_computador_pareado_por_comando_mantem_os_dois_botoes(self):
        r = self.rode(r"""
const li = linhaDeComputador({ id: 3, nome: "SERVIDOR", visto_em: ha(12), relatado_em: ha(12),
  projetos: 2, executa: false, so_mede: false });
console.log(JSON.stringify({ botoes: achaTodos(li, n => n.tag === "button").map(b => b.textContent) }));
""")
        self.assertEqual(r["botoes"], ["Deixar consertar aqui", "Remover"])

    def test_remover_confirma_com_o_texto_do_design(self):
        r = self.rode(r"""
const li = linhaDeComputador({ id: 3, nome: "PC-ESCRITORIO", visto_em: ha(12), relatado_em: ha(12),
  projetos: 2, so_mede: true });
await achaTodos(li, n => n.tag === "button").find(b => b.textContent === "Remover").clicar();
console.log(JSON.stringify(confirmou[0]));
""")
        self.assertEqual(r["titulo"], "Desconectar “PC-ESCRITORIO”?")
        self.assertIn("só volta se você baixar o arquivo de novo e abrir", r["texto"])
        self.assertEqual((r["sim"], r["nao"]), ("Desconectar", "Manter conectado"))

    def test_nome_de_outro_computador_entra_como_texto(self):
        r = self.rode(r"""
const li = linhaDeComputador({ id: 3, nome: "<b onmouseover=x>", visto_em: ha(1), relatado_em: ha(1),
  projetos: 1, so_mede: true });
console.log(JSON.stringify({ texto: li.textContent, bs: achaTodos(li, n => n.tag === "b").length }));
""")
        self.assertIn("<b onmouseover=x>", r["texto"])
        self.assertEqual(r["bs"], 0)


class ASituacaoDoComputadorEPura(unittest.TestCase):
    def situacao(self, lista):
        return roda(self, fontes("situacaoDoComputador", "estadoDosComputadores",
                                 consts=("COMPUTADOR_CALADO_APOS_MS",)),
                    PRELUDIO_DE_TEMPO + "console.log(JSON.stringify(situacaoDoComputador(%s, Date.now())));"
                    % lista)

    def test_cada_tipo(self):
        casos = [
            ("[]", "vazio", "desconectado"),
            ('[{nome:"a", visto_em: ha(5), relatado_em: null, projetos: 0}]', "pendente", "conectado"),
            ('[{nome:"a", visto_em: ha(5), relatado_em: ha(5), projetos: 0}]', "zero", "conectado"),
            ('[{nome:"a", visto_em: ha(5), relatado_em: ha(5), projetos: 3}]', "com_projetos", "conectado"),
            ('[{nome:"a", visto_em: ha(99999), relatado_em: ha(99999), projetos: 3}]', "mudo", "sem_dados"),
        ]
        for lista, tipo, estado in casos:
            with self.subTest(tipo=tipo):
                r = self.situacao(lista)
                self.assertEqual((r["tipo"], r["estado"]), (tipo, estado))

    def test_soma_os_projetos_so_de_quem_ja_mediu(self):
        r = self.situacao('[{nome:"a", visto_em: ha(5), relatado_em: ha(5), projetos: 3},'
                          '{nome:"b", visto_em: ha(5), relatado_em: null, projetos: 0},'
                          '{nome:"c", visto_em: ha(5), relatado_em: ha(5), projetos: 4}]')
        self.assertEqual((r["tipo"], r["projetos"]), ("com_projetos", 7))

    def test_o_mais_recente_e_quem_da_o_nome(self):
        r = self.situacao('[{nome:"velho", visto_em: ha(500), relatado_em: ha(500), projetos: 1},'
                          '{nome:"novo", visto_em: ha(5), relatado_em: ha(5), projetos: 1}]')
        self.assertEqual(r["nome"], "novo")


class AEsperaSabeQuandoOComputadorMediu(unittest.TestCase):
    def situacao(self, lista, antes_ids, relato_antes):
        return roda(self, fontes("situacaoDaEspera", "maiorRelato"),
                    PRELUDIO_DE_TEMPO + "console.log(JSON.stringify(situacaoDaEspera(%s, new Set(%s), %s)));"
                    % (lista, antes_ids, relato_antes))

    def test_nada_mudou_continua_esperando(self):
        self.assertEqual(self.situacao('[{id: 1, visto_em: ha(9), relatado_em: ha(9)}]',
                                       "[1]", "maiorRelato([{relatado_em: ha(9)}])"), "esperando")

    def test_maquina_nova_sem_relato_apareceu_mas_nao_mediu(self):
        self.assertEqual(self.situacao('[{id: 1, visto_em: ha(9), relatado_em: ha(9)}, '
                                       '{id: 2, visto_em: ha(1), relatado_em: null}]',
                                       "[1]", "maiorRelato([{relatado_em: ha(9)}])"), "apareceu")

    def test_relato_mais_novo_que_o_do_inicio_da_espera_e_sucesso(self):
        self.assertEqual(self.situacao('[{id: 1, visto_em: ha(1), relatado_em: ha(1)}]',
                                       "[1]", "maiorRelato([{relatado_em: ha(600)}])"), "medido")

    def test_maquina_nova_que_ja_mediu_e_sucesso(self):
        self.assertEqual(self.situacao('[{id: 2, visto_em: ha(1), relatado_em: ha(1)}]',
                                       "[]", "0"), "medido")

    def test_relatado_em_ausente_ou_torto_nunca_e_sucesso(self):
        self.assertEqual(self.situacao('[{id: 1, visto_em: ha(9)}, {id: 2, visto_em: ha(9), relatado_em: "lixo"}]',
                                       "[1, 2]", "0"), "esperando")


class ACortinaGuardaSoOFormatoExato(unittest.TestCase):
    def rode(self, hash_):
        node = node_ou_pula(self)
        prog = r"""
const guardado = {};
const el = () => ({ addEventListener() {}, setAttribute() {}, removeAttribute() {},
  hasAttribute() { return false; }, value: "", hidden: true, focus() {}, closest() { return null; } });
globalThis.location = { hash: %s };
globalThis.sessionStorage = { setItem(k, v) { guardado[k] = v; },
  getItem(k) { return guardado[k] || null; }, removeItem(k) { delete guardado[k]; } };
globalThis.document = { getElementById: el, querySelectorAll: () => [], querySelector: () => null };
""" % json.dumps(hash_) + CORTINA + "\nconsole.log(JSON.stringify(guardado));\n"
        r = subprocess.run([node, "-"], input=prog, capture_output=True, text=True,
                           timeout=30, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout.strip().splitlines()[-1])

    def test_codigo_valido_e_guardado_normalizado(self):
        self.assertEqual(self.rode("#/conectar?autorizar=k7m4-2qxp"),
                         {"dervs-autorizar": "K7M4-2QXP"})
        self.assertEqual(self.rode("#/conectar?autorizar=K7M42QXP"),
                         {"dervs-autorizar": "K7M4-2QXP"})

    def test_o_resto_nao_e_guardado(self):
        for h in ("", "#/painel", "#/conectar", "#/conectar?autorizar=",
                  "#/conectar?autorizar=<script>", "#/conectar?autorizar=K7M0-2QXP",
                  "#/projeto/x?autorizar=K7M4-2QXP", "#/conectar?outro=K7M4-2QXP"):
            with self.subTest(hash=h):
                self.assertEqual(self.rode(h), {})


class OPedidoGuardadoVoltaParaAutorizar(unittest.TestCase):
    def rode(self, guardado, hash_):
        return roda(self, fontes("voltarAoPedidoGuardado", "codigoDeAutorizar", "rota"), r"""
const trocas = [];
const arm = %s;
globalThis.sessionStorage = { getItem: (k) => arm[k] || null, removeItem: (k) => { delete arm[k]; } };
globalThis.location = { hash: %s };
globalThis.history = { replaceState(a, b, c) { trocas.push(c); location.hash = c; } };
voltarAoPedidoGuardado();
console.log(JSON.stringify({ trocas, sobrou: Object.keys(arm) }));
""" % (json.dumps(guardado), json.dumps(hash_)))

    def test_volta_para_o_pedido_e_apaga_a_chave(self):
        r = self.rode({"dervs-autorizar": "K7M4-2QXP"}, "")
        self.assertEqual(r, {"trocas": ["#/conectar?autorizar=K7M4-2QXP"], "sobrou": []})

    def test_valor_torto_no_armazenamento_e_ignorado_e_apagado(self):
        r = self.rode({"dervs-autorizar": "<img src=x>"}, "")
        self.assertEqual(r, {"trocas": [], "sobrou": []})

    def test_nao_atropela_um_endereco_que_ja_tem_pedido(self):
        r = self.rode({"dervs-autorizar": "K7M4-2QXP"}, "#/conectar?autorizar=ABCD-2345")
        self.assertEqual(r["trocas"], [])


class OPassoAPassoAbreNaPrimeiraVisita(unittest.TestCase):
    def rode(self, storage_js):
        return roda(self, ["let PASSOS_JA_DECIDIDOS = false;\n",
                           funcao("abrirPassosNaPrimeiraVisita")], storage_js + r"""
abrirPassosNaPrimeiraVisita();
abrirPassosNaPrimeiraVisita();
console.log(JSON.stringify({ aberto: $("#o-que-vai-aparecer").open }));
""")

    def test_primeira_visita_abre(self):
        r = self.rode("const m = {}; globalThis.localStorage = { getItem: k => m[k] || null, setItem: (k, v) => { m[k] = v; } };")
        self.assertTrue(r["aberto"])

    def test_visita_seguinte_fica_fechada(self):
        r = self.rode('const m = {"dervs-conectar-visto": "1"}; globalThis.localStorage = { getItem: k => m[k] || null, setItem: (k, v) => { m[k] = v; } };')
        self.assertFalse(r["aberto"])

    def test_sem_armazenamento_a_tela_nasce_aberta(self):
        r = self.rode("globalThis.localStorage = { getItem() { throw new Error('bloqueado'); }, setItem() { throw new Error('x'); } };")
        self.assertTrue(r["aberto"])


class AMarcacaoDoCartaoEstaNoHtml(unittest.TestCase):
    def test_os_vaos_que_o_script_preenche_existem(self):
        for ident in ("conectar-autorizar", "cartao-computador", "pc-titulo", "pc-marca",
                      "pc-resumo", "pc-carimbo", "pc-acoes", "espera-maquina", "pc-lista",
                      "lista-computadores", "computadores-carimbo", "o-que-vai-aparecer",
                      "o-que-faz", "prefiro-comando", "btn-gerar-numero", "pareamento",
                      "numero-pareamento", "comando-pareamento", "btn-copiar-comando",
                      "espera-pareamento", "conectar-corpo"):
            with self.subTest(id=ident):
                self.assertIn('id="%s"' % ident, HTML)

    def test_cada_id_que_o_script_pede_existe_no_html(self):
        # Um `$("#x")` para um id que nao existe estoura em silencio no navegador.
        usados = set(re.findall(r'\$\("#(pc-[a-z]+|espera-[a-z]+|conectar-[a-z]+|'
                                r'o-que-[a-z-]+|lista-computadores|computadores-carimbo|'
                                r'cartao-computador)"\)', JS))
        self.assertGreater(len(usados), 8)
        for ident in usados:
            with self.subTest(id=ident):
                self.assertIn('id="%s"' % ident, HTML)

    def test_o_pc_titulo_recebe_foco_e_o_bloco_de_autorizar_comeca_escondido(self):
        self.assertRegex(HTML, r'<h2 id="pc-titulo" tabindex="-1">')
        self.assertRegex(HTML, r'<div class="cartao" id="conectar-autorizar"[^>]*\bhidden\b')

    def test_os_textos_do_design_estao_na_tela(self):
        for texto in ("Ligue o DERVS ao que você usa.",
                      "Este computador",
                      "O que vai aparecer?",
                      "O que vai aparecer quando você clicar",
                      "O fornecedor não pôde ser verificado",
                      "O que esse arquivo faz no meu computador?",
                      "Prefiro colar um comando",
                      "Funciona no Windows 10 (versão 1803 ou mais nova) e no Windows 11.",
                      "Precisa de internet, mas não precisa de administrador.",
                      "O Windows vai perguntar se você confia no arquivo. É normal"):
            with self.subTest(texto=texto):
                junto = re.sub(r"\s+", " ", HTML)
                self.assertIn(texto, junto)

    def test_o_passo_a_passo_tem_sete_passos_e_tres_desenhos_sem_estilo_embutido(self):
        i = HTML.index('id="o-que-vai-aparecer"')
        bloco = HTML[i:HTML.index("</details>", i)]
        self.assertEqual(len(re.findall(r"<li>", bloco)), 7)
        self.assertEqual(len(re.findall(r"<svg\b", bloco)), 3)
        self.assertNotIn("style=", bloco)
        self.assertNotRegex(bloco, r'(fill|stroke)="[^"]*"')
        self.assertEqual(bloco.count('aria-hidden="true"'), 3)

    def test_os_desenhos_so_usam_classes_que_o_css_define(self):
        i = HTML.index('id="o-que-vai-aparecer"')
        bloco = HTML[i:HTML.index("</details>", i)]
        classes = set(re.findall(r'class="(desenho[a-z_-]*)"', bloco))
        self.assertGreaterEqual(len(classes), 5)
        css = sem_comentarios(CSS)
        for c in classes:
            with self.subTest(classe=c):
                self.assertIn("." + c, css)

    def test_o_menu_segue_com_quatro_itens(self):
        itens = re.findall(r'<a href="(#/[^"]+)" data-tela="([^"]+)"', HTML)
        self.assertEqual(len(itens), 4, itens)

    def test_assets_nao_ganhou_arquivo(self):
        nomes = sorted(p.name for p in (AQUI / "assets").iterdir())
        for novo in nomes:
            self.assertNotRegex(novo, r"(?i)desenho|passo|conectar", novo)


if __name__ == "__main__":
    unittest.main(verbosity=2)
