# -*- coding: utf-8 -*-
"""A seção "Quanto já foi desenvolvido" da tela Projeto -- só a casca da tela.

MOTIVO: o painel mostra, por projeto, quanto da documentação já está cumprido.
Quatro mentiras possíveis, e nenhuma é vista por um teste "a seção existe":

  - um percentual (0% ou 100%) onde não há número nenhum (sem documentação,
    sem prova rodada, agente antigo);
  - o texto de um critério -- que vem de um arquivo de OUTRO repositório --
    entrar como HTML;
  - o botão "Desenvolver isto" aparecer para critério que o servidor recusaria;
  - o progresso mexer no selo de saúde do projeto.

O contrato com o servidor (GET /api/dados -> `progresso`, GET /api/progresso,
POST /api/desenvolver) está em docs/superpowers/plans/dervs-progresso-por-
documentacao.md. As funções de montagem são EXECUTADAS (node, DOM de mentira,
como test_voz_tela.py); sem node os casos de comportamento são pulados e os de
texto continuam. Todos foram sabotados de propósito (ver o relatório da etapa).

    python test_progresso_tela.py
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

INI = JS.index("/* ================================ Progresso pela documentação")
FIM = JS.index("/* ============================ fim: Progresso pela documentação")
TRECHO = JS[INI:FIM]


def sem_comentarios(js: str) -> str:
    js = re.sub(r"/\*.*?\*/", "", js, flags=re.S)
    return re.sub(r"(?m)//[^\n]*$", "", js)


CODIGO = sem_comentarios(TRECHO)


def funcao(nome: str) -> str:
    """O corpo de uma função de primeiro nível do painel.js (até o `}` na coluna 0)."""
    m = re.search(r"(?:async )?function %s\(.*?\n}\n" % re.escape(nome), JS, re.S)
    assert m, "funcao %s nao encontrada" % nome
    return m.group(0)


def secao_html() -> str:
    i = HTML.index('id="projeto-progresso"')
    return HTML[i:HTML.index("</section>", i)]


class ASecaoExisteDentroDaTelaProjeto(unittest.TestCase):
    def test_extracoes_acharam_algo(self):
        self.assertGreater(len(CODIGO), 3000)
        self.assertGreater(len(secao_html()), 300)

    def test_e_uma_secao_dentro_da_tela_projeto(self):
        ini = HTML.index('<section id="tela-projeto"')
        pos = HTML.index('id="projeto-progresso"')
        self.assertLess(ini, pos)
        # nenhuma outra tela abre entre a abertura de tela-projeto e a secao
        self.assertNotIn('<section id="tela-', HTML[ini + 10:pos])
        self.assertIn('<section id="projeto-progresso"', HTML)

    def test_o_menu_segue_com_quatro(self):
        itens = re.findall(r'<a href="(#/[^"]+)" data-tela="([^"]+)"', HTML)
        self.assertEqual(len(itens), 4, itens)

    def test_pintarProjeto_pinta_o_progresso(self):
        self.assertIn("pintarProgresso(p);", funcao("pintarProjeto"))

    def test_projeto_ausente_esconde_a_secao(self):
        self.assertIn('$("#projeto-progresso").hidden = true', funcao("pintarProjeto"))

    def test_css_nao_inventa_cor(self):
        i = CSS.rindex("/*", 0, CSS.index("Progresso pela documentação"))
        bloco = sem_comentarios(CSS[i:])
        self.assertIn(".progresso__barra", bloco)
        self.assertNotRegex(bloco, r"#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(")
        self.assertNotIn("--estado-", bloco)  # progresso nao e o selo de saude
        self.assertIn("focus-visible", bloco)


class DadoDeForaNaoEntraPorInnerHtml(unittest.TestCase):
    def test_nada_de_html_no_trecho_inteiro(self):
        for proibido in ("innerHTML", "outerHTML", "insertAdjacentHTML",
                         "document.write"):
            with self.subTest(proibido=proibido):
                self.assertNotIn(proibido, CODIGO)

    def test_nem_em_pintarProgresso_nem_em_linhaDeCriterio(self):
        for nome in ("pintarProgresso", "linhaDeCriterio", "pintarCriterios"):
            with self.subTest(nome=nome):
                corpo = sem_comentarios(funcao(nome))
                self.assertGreater(len(corpo), 200)
                self.assertNotIn("innerHTML", corpo)

    def test_texto_do_criterio_e_so_textcontent(self):
        corpo = funcao("linhaDeCriterio")
        self.assertIn("texto.textContent = c.texto", corpo)
        self.assertIn("cmd.textContent = c.prova", corpo)

    def test_sem_Number_nem_parseInt(self):
        # test_design toma os dois por "numero na tela sem carimbo"
        self.assertNotRegex(CODIGO, r"Number\(|parseInt\(")


class OBotaoSoExisteAtrasDeDesenvolvivel(unittest.TestCase):
    def test_o_if_do_desenvolvivel_guarda_o_botao(self):
        corpo = funcao("linhaDeCriterio")
        i = corpo.index("c.desenvolvivel === true")
        # o botao e montado DENTRO do bloco do if, e em nenhum outro lugar
        self.assertEqual(corpo.count('createElement("button")'), 1)
        self.assertLess(i, corpo.index('createElement("button")'))
        self.assertLess(corpo.index('createElement("button")'),
                        corpo.index("} else if (typeof c.motivo"))

    def test_o_corpo_do_pedido_e_so_o_id_do_criterio(self):
        corpo = funcao("desenvolverCriterio")
        self.assertIn('escrever("/api/desenvolver", { criterio: c.id })', corpo)
        # `escrever` e quem poe o X-Token; fetch cru seria CSRF aberto
        self.assertNotIn("fetch(", corpo)

    def test_o_botao_chama_desenvolverCriterio(self):
        self.assertIn("desenvolverCriterio(c, b)", funcao("linhaDeCriterio"))


class OProgressoNaoMexeNoSelo(unittest.TestCase):
    def test_nenhuma_chamada_de_selo_no_trecho(self):
        self.assertNotRegex(CODIGO, r"\bselo\(")

    def test_pintarProjeto_nao_passa_progresso_ao_selo(self):
        for m in re.finditer(r"\bselo\([^;]*;", funcao("pintarProjeto")):
            self.assertNotIn("progresso", m.group(0).lower())

    def test_o_selo_do_projeto_continua_vindo_do_selo_do_projeto(self):
        self.assertIn("selo(p.selo, { como: \"span\" })", funcao("pintarProjeto"))


class AsQuatroFacesEstaoMapeadas(unittest.TestCase):
    def test_os_quatro_estados_sao_tratados(self):
        corpo = funcao("pintarProgresso")
        for estado in ("medido", "nao_verificado", "sem_documentacao", "sem_dados"):
            with self.subTest(estado=estado):
                self.assertIn('"%s"' % estado, corpo)

    def test_frases_fixas(self):
        corpo = funcao("pintarProgresso")
        self.assertIn("Nenhuma prova rodou ainda.", corpo)
        self.assertIn("marcados no documento, sem prova", corpo)
        self.assertIn("haQuanto(pr.medido_em)", corpo)

    def test_percentual_so_na_face_medido(self):
        corpo = sem_comentarios(funcao("pintarProgresso"))
        # todo "%" escrito na tela fica depois de `if (lido === "medido")`
        i = corpo.index('if (lido === "medido")')
        self.assertNotIn('"%"', corpo[:i])
        self.assertNotIn("%", re.sub(r'"%"', "", corpo[:i]))


# ----------------------------------------------------------- comportamento
AGORA = "2026-09-30T12:00:00Z"

PRELUDIO = r"""
class El {
  constructor(tag) { this.tag = tag; this.className = ""; this._t = ""; this.dataset = {};
    this.filhos = []; this.attrs = {}; this.hidden = false; this.ouvintes = {}; this.disabled = false; }
  get textContent() { return this._t; }
  set textContent(v) { this._t = v; this.filhos = []; }
  append(...x) { for (const i of x) this.filhos.push(typeof i === "string" ? Object.assign(new El("#texto"), {_t: i}) : i); }
  setAttribute(k, v) { this.attrs[k] = v; }
  addEventListener(t, f) { this.ouvintes[t] = f; }
}
const ELS = {};
const $ = s => (ELS[s] = ELS[s] || new El(s));
const document = { createElement: t => new El(t) };
function achata(n) { return [n._t].concat(n.filhos.map(achata)).join(" "); }
function acha(n, tag) { return (n.tag === tag ? [n] : []).concat(...n.filhos.map(f => acha(f, tag))); }
const CHAMADAS = [];
let RESPOSTA = { ok: true, status: 200, corpo: { documentos: [] } };
async function fetch(url) { CHAMADAS.push({ get: url }); return { ok: RESPOSTA.ok, status: RESPOSTA.status, json: async () => RESPOSTA.corpo }; }
async function escrever(url, corpo) { CHAMADAS.push({ url, corpo }); return { ok: RESPOSTA.ok, status: RESPOSTA.status, json: async () => RESPOSTA.corpo }; }
async function carregarTarefas() { CHAMADAS.push({ tarefas: true }); }
"""


def _roda(corpo_js: str):
    node = shutil.which("node")
    if not node:
        return None
    a = JS.index("function haQuanto(")
    b = JS.index("function hora(", a)
    m = re.search(r"function nada\(.*?\n}\n", JS, re.S)
    prog = (PRELUDIO + JS[a:b] + m.group(0) + TRECHO
            + "\n(async () => {\n" + corpo_js + "\n})();\n")
    r = subprocess.run([node, "-"], input=prog, capture_output=True, text=True,
                       timeout=30, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def _pinta(pr, nome="meu proj", corpo=None, resposta=None):
    """Pinta o resumo para um `progresso` e devolve o que apareceu na tela."""
    js = """
    %s
    pintarProgresso({ nome: %s, progresso: %s });
    await new Promise(r => setTimeout(r, 20));
    console.log(JSON.stringify({
      resumo: achata($("#progresso-resumo")),
      lista: achata($("#progresso-lista")),
      barras: acha($("#progresso-resumo"), "progress").length,
      estado: $("#projeto-progresso").dataset.estado,
      escondida: $("#projeto-progresso").hidden,
      chamadas: CHAMADAS }));
    """ % ("RESPOSTA = %s;" % json.dumps(resposta) if resposta else "",
           json.dumps(nome), json.dumps(pr))
    r = _roda(js)
    if r is None:
        raise unittest.SkipTest("sem node")
    return r


def pr(estado, **k):
    base = {"estado": estado, "percentual": None, "total": 0, "comprovados": 0,
            "falhos": 0, "nao_verificados": 0, "faltam": 0, "declarados": 0,
            "medido_em": AGORA, "documentos_n": 0, "erros_n": 0}
    base.update(k)
    return base


class OResumoNaoMente(unittest.TestCase):
    def test_medido_mostra_o_numero_a_barra_e_o_carimbo(self):
        r = _pinta(pr("medido", percentual=40, total=5, comprovados=2, falhos=1,
                      nao_verificados=1, faltam=1, declarados=0, documentos_n=1))
        self.assertIn("40%", r["resumo"])
        self.assertEqual(r["barras"], 1)
        self.assertIn("2 de 5 critérios comprovados", r["resumo"])
        self.assertRegex(r["resumo"], r"medido (há|agora|em|sem carimbo)")

    def test_nao_verificado_nao_tem_percentual_nem_barra(self):
        r = _pinta(pr("nao_verificado", total=4, declarados=3, documentos_n=1))
        self.assertIn("Nenhuma prova rodou ainda", r["resumo"])
        self.assertIn("3 marcados no documento, sem prova", r["resumo"])
        self.assertNotIn("%", r["resumo"])
        self.assertEqual(r["barras"], 0)

    def test_nao_verificado_ignora_percentual_que_o_servidor_mande(self):
        """Servidor defeituoso mandando 100 nao vira 100% na tela."""
        r = _pinta(pr("nao_verificado", percentual=100, total=4, comprovados=4))
        self.assertNotIn("%", r["resumo"])
        self.assertNotIn("100", r["resumo"])
        self.assertEqual(r["barras"], 0)

    def test_sem_documentacao_nunca_escreve_percentual_nem_zero(self):
        r = _pinta(pr("sem_documentacao", percentual=0))
        self.assertIn("Sem documentação", r["resumo"])
        self.assertNotIn("%", r["resumo"])
        self.assertNotIn("0", r["resumo"])
        self.assertEqual(r["barras"], 0)
        self.assertEqual(r["chamadas"], [])  # nada a buscar

    def test_sem_dados_e_agente_antigo_nao_escrevem_numero(self):
        for p in (pr("sem_dados"), None, {}, pr("inventado", percentual=50)):
            with self.subTest(p=p):
                r = _pinta(p)
                self.assertIn("Não consegui medir", r["resumo"])
                self.assertNotIn("%", r["resumo"])
                self.assertEqual(r["barras"], 0)
                self.assertEqual(r["estado"], "sem_dados")

    def test_medido_sem_percentual_legivel_falha_fechado(self):
        r = _pinta(pr("medido", percentual=None, total=3))
        self.assertNotIn("%", r["resumo"])
        self.assertEqual(r["barras"], 0)

    def test_percentual_hostil_nao_passa_de_cem(self):
        r = _pinta(pr("medido", percentual=10 ** 9, total=1, comprovados=1))
        self.assertIn("100%", r["resumo"])
        self.assertNotIn("1000000000", r["resumo"])


class AListaDeCriteriosChegaDoServidor(unittest.TestCase):
    CORPO = {"projeto": "meu proj", "documentos": [{
        "slug": "coisa", "arquivo": "docs/esteira/coisa/briefing.md",
        "aprovado_em": "2026-09-30", "erros": ["linha 7: critério numerado não conta"],
        "criterios": [
            {"id": "c1", "n": 1, "texto": "<img src=x onerror=alert(1)>", "marcado": False,
             "prova": "python test_x.py", "prova_aceita": True,
             "situacao": "nao_verificado", "desenvolvivel": True, "motivo": ""},
            {"id": "c2", "n": 2, "texto": "outro", "marcado": True, "prova": "",
             "prova_aceita": False, "situacao": "falta", "desenvolvivel": False,
             "motivo": "documento não aprovado"}]}]}

    def test_busca_pelo_nome_escapado_e_pinta_os_criterios(self):
        r = _pinta(pr("medido", percentual=0, total=2, documentos_n=1),
                   resposta={"ok": True, "status": 200, "corpo": self.CORPO})
        self.assertEqual(r["chamadas"], [{"get": "/api/progresso?projeto=meu%20proj"}])
        self.assertIn("<img src=x onerror=alert(1)>", r["lista"])
        self.assertIn("Aprovado em 30/09/2026", r["lista"])
        self.assertIn("Erro de formato: linha 7", r["lista"])
        self.assertIn("documento não aprovado", r["lista"])

    def test_erro_do_servidor_mostra_frase_e_tentar_de_novo(self):
        r = _pinta(pr("medido", percentual=0, total=2),
                   resposta={"ok": False, "status": 500, "corpo": {}})
        self.assertIn("erro 500", r["lista"])
        self.assertIn("Tentar de novo", r["lista"])

    def test_404_nao_vira_lista_vazia(self):
        r = _pinta(pr("nao_verificado", total=2),
                   resposta={"ok": False, "status": 404, "corpo": {"erro": "projeto nao encontrado"}})
        self.assertIn("não está mais na lista", r["lista"])

    def test_corpo_sem_documentos_e_erro_nao_vazio(self):
        r = _pinta(pr("medido", percentual=0, total=2),
                   resposta={"ok": True, "status": 200, "corpo": {"projeto": "x"}})
        self.assertIn("não entendi", r["lista"])

    def test_carregando_aparece_antes_da_resposta(self):
        js = """
        pintarProgresso({ nome: "x", progresso: %s });
        console.log(JSON.stringify({ lista: achata($("#progresso-lista")) }));
        """ % json.dumps(pr("medido", percentual=10, total=2))
        r = _roda(js)
        if r is None:
            self.skipTest("sem node")
        self.assertIn("Carregando os critérios", r["lista"])


class OBotaoEOPedidoPorDentro(unittest.TestCase):
    def _linha(self, **c):
        base = {"id": "cabc", "n": 1, "texto": "t", "marcado": False, "prova": "",
                "prova_aceita": False, "situacao": "falta", "desenvolvivel": False,
                "motivo": ""}
        base.update(c)
        r = _roda("""
        const li = linhaDeCriterio(%s);
        console.log(JSON.stringify({ botoes: acha(li, "button").map(b => b._t),
                                     texto: achata(li) }));
        """ % json.dumps(base))
        if r is None:
            self.skipTest("sem node")
        return r

    def test_so_true_de_verdade_mostra_o_botao(self):
        self.assertEqual(self._linha(desenvolvivel=True)["botoes"], ["Desenvolver isto"])
        for v in (False, None, "true", 1, "sim", [], {}):
            with self.subTest(v=v):
                self.assertEqual(self._linha(desenvolvivel=v)["botoes"], [])

    def test_sem_botao_o_motivo_aparece(self):
        self.assertIn("documento não aprovado", self._linha(motivo="documento não aprovado")["texto"])

    def test_situacao_desconhecida_nunca_vira_comprovado(self):
        r = self._linha(situacao="verde_de_mentira")
        self.assertIn("Não verificado", r["texto"])
        self.assertNotIn("Comprovado", r["texto"])

    def test_prova_fora_da_lista_diz_que_nunca_roda(self):
        r = self._linha(prova="rm -rf /", prova_aceita=False)
        self.assertIn("nunca roda", r["texto"])

    def _clica(self, resposta):
        r = _roda("""
        RESPOSTA = %s;
        const b = new El("button");
        await desenvolverCriterio({ id: "cabc", texto: "t", desenvolvivel: true, regra: "intruso" }, b);
        console.log(JSON.stringify({ chamadas: CHAMADAS, desabilitado: b.disabled,
                                     texto: $("#progresso-recado-texto")._t,
                                     aviso: $("#progresso-recado-aviso")._t }));
        """ % json.dumps(resposta))
        if r is None:
            self.skipTest("sem node")
        return r

    def test_o_corpo_do_post_e_so_o_id(self):
        r = self._clica({"ok": True, "status": 200,
                         "corpo": {"ok": True, "pedido": True, "aviso": "nenhum computador ligado"}})
        self.assertEqual(r["chamadas"][0], {"url": "/api/desenvolver", "corpo": {"criterio": "cabc"}})
        self.assertIn("Na fila", r["texto"])
        self.assertEqual(r["aviso"], "nenhum computador ligado")
        self.assertTrue(r["desabilitado"])

    def test_cada_403_tem_a_sua_frase(self):
        frases = set()
        for erro in ("documento nao aprovado", "projeto bloqueado",
                     "criterio sensivel", "criterio ja marcado"):
            r = self._clica({"ok": False, "status": 403, "corpo": {"erro": erro}})
            self.assertFalse(r["desabilitado"], erro)  # pode tentar de novo
            self.assertGreater(len(r["texto"]), 30, erro)
            frases.add(r["texto"])
        self.assertEqual(len(frases), 4, frases)
        # e as palavras do servidor nunca vazam cruas para a tela
        for f in frases:
            self.assertNotRegex(f, r"nao aprovado|criterio sensivel|ja marcado")

    def test_outros_status_tem_frase_propria(self):
        for status in (400, 401, 404, 429, 500):
            r = self._clica({"ok": False, "status": status, "corpo": {}})
            with self.subTest(status=status):
                self.assertGreater(len(r["texto"]), 30)


class ODetalheApareceAoLadoDoPodeFazer(unittest.TestCase):
    """Em Consertar o dono clica em "Pode fazer" e precisa ler O QUE foi
    pedido. O texto vem de um documento de outro repositorio: so textContent."""

    def _linha(self, **t):
        node = shutil.which("node")
        if not node:
            self.skipTest("sem node")
        base = {"id": "desenvolver:1:c1", "projeto": "dervs",
                "regra": "desenvolver", "estado": "esperando", "cor": "vermelho",
                "aprovado_em": None, "criado_em": AGORA}
        base.update(t)
        a = JS.index("function haQuanto(")
        b = JS.index("function hora(", a)
        prog = (PRELUDIO + JS[a:b] + funcao("linhaDeTarefa") + funcao("marcaDeCor")
                + """
        const ANDAMENTO = {}; const CORES = { vermelho: { glifo: "x", rotulo: "Vermelho" } };
        function irPara() {} function aprovarTarefa() {}
        const li = linhaDeTarefa(%s);
        console.log(JSON.stringify({ botoes: acha(li, "button").map(b => b._t),
                                     texto: achata(li) }));
        """ % json.dumps(base))
        r = subprocess.run([node, "-"], input=prog, capture_output=True,
                           text=True, timeout=30, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def test_o_pedido_aparece_com_o_rotulo_ao_lado_do_botao(self):
        r = self._linha(detalhe="Critério 1 de docs/x: mostrar a barra")
        self.assertIn("O que foi pedido:", r["texto"])
        self.assertIn("mostrar a barra", r["texto"])
        self.assertIn("Pode fazer", r["botoes"])

    def test_html_no_pedido_fica_como_texto(self):
        r = self._linha(detalhe="<img src=x onerror=alert(1)>")
        self.assertIn("<img src=x onerror=alert(1)>", r["texto"])

    def test_sem_detalhe_nao_escreve_rotulo_vazio(self):
        for v in (None, "", 7, {}):
            with self.subTest(v=v):
                self.assertNotIn("O que foi pedido", self._linha(detalhe=v)["texto"])

    def test_no_codigo_so_textcontent_e_sem_Number(self):
        corpo = sem_comentarios(funcao("linhaDeTarefa"))
        self.assertIn("O que foi pedido:", corpo)
        self.assertNotIn("innerHTML", corpo)
        self.assertNotRegex(corpo, r"Number\(|parseInt\(")


if __name__ == "__main__":
    unittest.main(verbosity=2)
