# -*- coding: utf-8 -*-
"""A tela "Vigilia e cerebros" (ponte com o DERVS-VOZ) -- so a casca da tela.

MOTIVO: a secao mostra ao dono se o VOZ esta vigiando e quais cerebros ele tem.
Tres mentiras possiveis, e nenhuma delas e vista por teste "a secao existe":

  - `sem_dados` com cara de "Vigiando" (verde sem dado);
  - cerebro "disponivel" sem informacao fresca do VOZ;
  - o aviso "so acontece depois do seu clique no VOZ" sumir do formulario.

E uma ameacca: o nome do computador, o motivo e o resumo vem do OUTRO computador
-- dado hostil. So `textContent`, nunca `innerHTML`, no trecho inteiro.

A funcao que monta o cartao e EXECUTADA (node, com um DOM de mentira minimo);
sem node os casos de comportamento sao pulados e os de texto continuam. Todos
foram sabotados de proposito (ver o relatorio da etapa).

    python test_voz_tela.py
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

INI = JS.index("/* ============================================ Vigília e cérebros")
FIM = JS.index("/* ========================================== Formas de entrar")
TRECHO = JS[INI:FIM]


def html_da_secao() -> str:
    i = HTML.index('id="voz"')
    return HTML[i:HTML.index("</section>", i)]


class ASecaoExisteDentroDeConectar(unittest.TestCase):
    def test_extracoes_acharam_algo(self):
        self.assertGreater(len(TRECHO), 2000)
        self.assertGreater(len(html_da_secao()), 1000)

    def test_titulo_e_formulario(self):
        h = html_da_secao()
        self.assertIn("Vigília e cérebros", h)
        self.assertIn("Mandar um recado ao DERVS-VOZ", h)
        for campo in ("voz-maquina", "voz-tipo", "voz-alvo", "voz-texto",
                      "voz-nivel", "voz-cerebro"):
            with self.subTest(campo=campo):
                self.assertRegex(h, r'<label for="%s">' % campo)
        self.assertIn('maxlength="500"', h)

    def test_mora_dentro_da_tela_dos_computadores_que_abre_com_conectar(self):
        ini = HTML.index('<section id="tela-computadores"')
        fim = HTML.index("</section>", HTML.index('id="voz"'))
        self.assertLess(ini, HTML.index('id="voz"'))
        # nenhum </section> entre a abertura da tela e a secao
        self.assertNotIn("</section>", HTML[ini:HTML.index('id="voz"')])
        self.assertGreater(fim, ini)

    def test_os_recados_ficam_num_details_fechado_no_fim_de_conectar(self):
        """Tela F do design: o VOZ saiu do meio da tela. Um `<details>` nativo
        (abre com Enter/Espaco), FECHADO, com o resumo escrito."""
        ini = HTML.index('<section id="tela-computadores"')
        tela = HTML[ini:HTML.index("</section>", ini)]
        m = re.search(r"<details\b([^>]*)>\s*<summary>([^<]*)</summary>", tela)
        self.assertIsNotNone(m, "o VOZ nao esta dentro de um <details> com <summary>")
        self.assertEqual(m.group(2).strip(), "Recados do DERVS-VOZ")
        self.assertNotRegex(m.group(1), r"\bopen\b", "o details tem de nascer fechado")
        self.assertLess(tela.index("<details"), tela.index('id="voz"'))
        self.assertLess(tela.index('id="voz"'), tela.index("</details>"))

    def test_conectar_carrega_a_vigilia(self):
        corpo = re.search(r'case "conectar":(.*?)break;', JS, re.S)
        self.assertIsNotNone(corpo)
        self.assertIn("carregarVoz()", corpo.group(1))

    def test_o_menu_segue_com_quatro(self):
        itens = re.findall(r'<a href="(#/[^"]+)" data-tela="([^"]+)"', HTML)
        self.assertEqual(len(itens), 4, itens)


class OPedidoQueATelaMontaESatisfazOServidor(unittest.TestCase):
    """O <select> entrega TEXTO e o servidor exige NUMERO em `maquina_id`.

    A suite do servidor monta o corpo a mao, com inteiro, e ficou verde com a
    tela mandando `"7"` (400 em todo recado). Este guarda le o que a tela monta.
    """

    def test_o_maquina_id_que_a_tela_manda_e_numero(self):
        m = re.search(r"maquina_id:\s*([^,\n]+),", TRECHO)
        self.assertIsNotNone(m, "a tela nao monta maquina_id")
        self.assertTrue(m.group(1).strip().startswith("+$("), m.group(1))

    def test_o_seletor_compara_texto_com_texto(self):
        # `m.maquina_id === antes` compara numero com texto e nunca casa: a
        # escolha do dono voltava para o primeiro computador a cada repintura.
        self.assertNotRegex(TRECHO, r"m\.maquina_id\s*===\s*antes")
        self.assertIn("String(m.maquina_id) === antes", TRECHO)

    def test_o_servidor_segue_exigindo_inteiro(self):
        """Se o servidor passar a aceitar texto, o guarda de cima perde o motivo."""
        fonte = (AQUI / "servir.py").read_text(encoding="utf-8")
        self.assertRegex(fonte, r"isinstance\(mid, int\)")


class OAvisoDoCliqueNaoSome(unittest.TestCase):
    FRASE = ("O que muda alguma coisa só acontece depois do seu clique no\n"
             "          DERVS-VOZ. Aprovar aqui não basta.")

    def test_o_aviso_fixo_esta_no_formulario(self):
        h = html_da_secao()
        self.assertIn('id="voz-aviso"', h)
        self.assertIn("só acontece depois do seu clique no", h)
        self.assertIn("Aprovar aqui não basta.", h)

    def test_o_aviso_nao_esta_escondido(self):
        tag = re.search(r'<p[^>]*id="voz-aviso"[^>]*>', html_da_secao()).group(0)
        self.assertNotIn("hidden", tag)

    def test_muda_estado_poe_em_destaque(self):
        self.assertRegex(TRECHO, r'"muda_estado"\s*\?\s*"sim"')
        css = (AQUI / "assets" / "painel.css").read_text(encoding="utf-8")
        self.assertIn('.voz__aviso[data-forte="sim"]', css)


class DadoDoServidorNaoEntraPorInnerHtml(unittest.TestCase):
    def test_nada_de_innerhtml_no_trecho(self):
        # sem os comentarios: eles PODEM citar a palavra, o codigo nao.
        codigo = re.sub(r"/\*.*?\*/", "", TRECHO, flags=re.S)
        codigo = re.sub(r"(?m)//[^\n]*$", "", codigo)
        self.assertGreater(len(codigo), 2000)
        for proibido in ("innerHTML", "outerHTML", "insertAdjacentHTML",
                         "document.write"):
            with self.subTest(proibido=proibido):
                self.assertNotIn(proibido, codigo)

    def test_o_helper_usa_textcontent(self):
        self.assertIn("e.textContent = texto", TRECHO)
        self.assertIn("erro.textContent = d.erro", TRECHO)

    def test_a_chamada_de_escrita_leva_o_token(self):
        # `escrever` e quem poe o X-Token; fetch cru aqui seria CSRF aberto.
        self.assertIn('escrever("/api/voz/recado"', TRECHO)
        self.assertNotRegex(TRECHO, r'fetch\("/api/voz/recado"')


class NaoHaTerminalNemExecucaoNaTela(unittest.TestCase):
    def test_a_secao_so_manda_recado(self):
        tudo = (TRECHO + html_da_secao()).lower()
        for palavra in ("ssh", "terminal", "xterm", "websocket", "eval(",
                        "new function"):
            with self.subTest(palavra=palavra):
                self.assertNotIn(palavra, tudo)


def _roda_cartao(maquina: dict):
    """Monta o cartao com um DOM de mentira e devolve o que foi escrito."""
    node = shutil.which("node")
    if not node:
        return None
    ini = JS.index("function haQuanto(")
    fim_ha = JS.index("function hora(", ini)
    ini_voz = JS.index("const VOZ_CEREBROS")
    fim_voz = JS.index("function vozRecado(")
    prog = r"""
const SELOS = [];
function selo(estado, opc) { SELOS.push({estado, texto: opc.texto}); return mkel("selo"); }
function mkel(tag) {
  return { tag, className: "", textContent: "", dataset: {}, filhos: [],
           append(...x) { this.filhos.push(...x); } };
}
const document = { createElement: mkel };
""" + JS[ini:fim_ha] + JS[ini_voz:fim_voz] + r"""
function achata(n) {
  return [n.textContent].concat((n.filhos || []).flatMap(achata)).join(" | ");
}
const cartao = vozCartao(%s);
console.log(JSON.stringify({ selos: SELOS, texto: achata(cartao) }));
""" % json.dumps(maquina)
    r = subprocess.run([node, "-"], input=prog, capture_output=True,
                       text=True, timeout=30, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


AGORA_ISO = "2026-09-30T12:00:00Z"
CEREBROS_OK = {"claude_code": {"disponivel": True, "motivo": ""},
               "hermes": {"disponivel": False, "motivo": "não instalado"},
               "jev": {"disponivel": False, "motivo": "sem chave"}}


class AVigiliaNaoMenteNemOsCerebros(unittest.TestCase):
    def _cartao(self, **m):
        base = {"maquina_id": "m1", "nome": "Notebook", "visto_em": AGORA_ISO,
                "atraso_s": 10, "vigilia": "viva",
                "estado": {"cerebro_ativo": "claude_code", "fresco": True,
                           "cerebros": CEREBROS_OK, "gasto_dia_usd": 0.5}}
        base.update(m)
        r = _roda_cartao(base)
        if r is None:
            self.skipTest("sem node")
        return r

    def test_viva_e_vigiando(self):
        r = self._cartao()
        self.assertEqual(r["selos"], [{"estado": "saudavel", "texto": "Vigiando"}])

    def test_sem_dados_nao_e_verde(self):
        r = self._cartao(vigilia="sem_dados", atraso_s=5000)
        self.assertEqual(r["selos"], [{"estado": "sem_dados", "texto": "Sem dados"}])
        self.assertIn("últimos 20 minutos", r["texto"])

    def test_valor_desconhecido_de_vigilia_falha_fechado(self):
        r = self._cartao(vigilia="talvez")
        self.assertEqual(r["selos"][0]["estado"], "sem_dados")

    def test_nunca_mediu(self):
        r = self._cartao(visto_em=None, vigilia="sem_dados", estado=None)
        self.assertEqual(r["selos"], [{"estado": "sem_dados", "texto": "Ainda não mediu"}])

    def test_visto_em_nulo_nunca_e_vigiando_nem_que_o_servidor_diga_viva(self):
        r = self._cartao(visto_em=None, vigilia="viva")
        self.assertEqual(r["selos"][0]["estado"], "sem_dados")

    def test_cerebro_disponivel_com_motivo_dos_outros(self):
        r = self._cartao()
        self.assertIn("— disponível (em uso)", r["texto"])
        self.assertIn("indisponível: não instalado", r["texto"])
        self.assertIn("indisponível: sem chave", r["texto"])
        self.assertIn("triagem rápida: decide se algo é urgente; não conversa", r["texto"])

    def test_sem_estado_nao_mostra_cerebro_como_disponivel(self):
        r = self._cartao(estado=None)
        self.assertNotIn("disponível", r["texto"].replace("indisponível", ""))
        self.assertEqual(r["texto"].count("sem informação do VOZ"), 3)

    def test_estado_velho_nao_mostra_cerebro_como_disponivel(self):
        r = self._cartao(estado={"fresco": False, "cerebros": CEREBROS_OK,
                                 "cerebro_ativo": "claude_code"})
        self.assertNotIn("— disponível", r["texto"])
        self.assertEqual(r["texto"].count("sem informação do VOZ"), 3)

    def test_nome_hostil_vai_como_texto(self):
        r = self._cartao(nome="<img src=x onerror=alert(1)>")
        self.assertIn("<img src=x onerror=alert(1)>", r["texto"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
