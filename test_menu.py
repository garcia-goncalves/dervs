# -*- coding: utf-8 -*-
"""O menu enxuto e o botao "Consertar com IA" -- a Fatia B (a tela).

MOTIVO: o menu de sete itens virou quatro lugares (Painel, Consertar, Conectar,
Conta), e as telas antigas viraram abas ou secoes dentro deles. Tres coisas
quebram em silencio quando alguem mexe nisso:

  - um quinto item nasce no menu e o "enxuto" deixa de ser;
  - um endereco antigo (`#/consumo`, `#/entrada`, `#/computadores`) deixa de
    abrir alguma coisa -- quem guardou o link cai numa tela em branco;
  - o botao "Consertar com IA" aparece num alerta que o servidor nao conserta,
    e o clique so devolve recusa.

Este teste le `index.html` e `assets/painel.js` como TEXTO: nao ha navegador
aqui. O que ele nao prova (o clique, o visual) foi conferido clicando, e o
relatorio da fatia diz isso.

Cada caso comeca provando que a extracao achou o que ia examinar -- busca que
nao acha nada passa vazia e verde. Todos foram sabotados de proposito.

    python test_menu.py
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

AQUI = Path(__file__).parent
HTML = (AQUI / "index.html").read_text(encoding="utf-8")
JS = (AQUI / "assets" / "painel.js").read_text(encoding="utf-8")

ITENS_DO_MENU = [
    ("#/painel", "painel", "Painel"),
    ("#/trabalho", "trabalho", "Consertar"),
    ("#/conectar", "conectar", "Conectar"),
    ("#/conta", "conta", "Conta"),
]

# Endereco antigo -> o que ele precisa abrir agora.
ANTIGOS = {
    "trabalho": None,          # continua sendo rota de verdade
    "auditoria": None,         # idem, vive como aba de Consertar
    "consumo": "#/conta",
    "entrada": "#/conta/entrada",
    "computadores": "#/conectar",
}


def corpo_da_funcao(nome: str) -> str:
    """O texto de `function nome(` / `async function nome(` ate o `}` que a
    fecha na coluna zero."""
    m = re.search(r"^(?:async )?function %s\(" % re.escape(nome), JS, re.M)
    assert m, "a funcao %s sumiu do painel.js" % nome
    fim = JS.index("\n}\n", m.start())
    return JS[m.start():fim]


class OMenuTemQuatroLugares(unittest.TestCase):
    def itens(self):
        nav = re.search(r'<nav class="mapa".*?</nav>', HTML, re.S)
        self.assertIsNotNone(nav, "o <nav class=\"mapa\"> sumiu do index.html")
        return re.findall(
            r'<a href="([^"]+)" data-tela="([^"]+)">([^<]+)</a>', nav.group(0))

    def test_exatamente_quatro_itens_com_os_nomes_certos(self):
        self.assertEqual(self.itens(), ITENS_DO_MENU)

    def test_nao_ha_link_no_menu_fora_da_lista(self):
        """`itens()` so enxerga o formato esperado; um link escrito diferente
        escaparia dele. Conta TODO `<a` dentro do nav."""
        nav = re.search(r'<nav class="mapa".*?</nav>', HTML, re.S).group(0)
        self.assertEqual(len(re.findall(r"<a\b", nav)), 4)

    def test_so_existe_um_nav_de_menu(self):
        """As abas de dentro da tela NAO podem ser `<nav class="mapa">`: o
        `mostrar()` marca o item do menu por esse seletor."""
        self.assertEqual(len(re.findall(r'<nav class="mapa"', HTML)), 1)

    def test_cada_item_do_menu_tem_uma_tela_no_roteador(self):
        for href, _, _ in ITENS_DO_MENU:
            tela = href[2:]
            if tela == "painel":
                continue  # e' o `default:` do switch
            with self.subTest(tela=tela):
                self.assertRegex(JS, r'case\s+"%s"\s*:' % tela)

    def test_o_item_marcado_de_cada_tela_e_um_item_que_existe(self):
        """`MENU_DE` liga cada tela ao item do menu que fica marcado. Um valor
        que nao e' `data-tela` de item nenhum deixa o menu sem marca."""
        m = re.search(r"const MENU_DE = \{(.*?)\};", JS, re.S)
        self.assertIsNotNone(m, "a tabela MENU_DE sumiu do painel.js")
        valores = set(re.findall(r':\s*"([a-z]+)"', m.group(1)))
        self.assertTrue(valores, "o teste parou de ler a tabela")
        existentes = {tela for _, tela, _ in ITENS_DO_MENU}
        self.assertTrue(valores <= existentes,
                        "MENU_DE aponta para %s; o menu so tem %s"
                        % (valores - existentes, existentes))


class AsRotasAntigasContinuamAbrindo(unittest.TestCase):
    def tabela(self):
        m = re.search(r"const ROTAS_ANTIGAS = \{(.*?)\};", JS, re.S)
        self.assertIsNotNone(m, "a tabela ROTAS_ANTIGAS sumiu do painel.js")
        return dict(re.findall(r'(\w+):\s*"([^"]+)"', m.group(1)))

    def test_cada_alias_antigo_esta_no_roteador(self):
        tabela = self.tabela()
        self.assertTrue(tabela, "o teste parou de ler a tabela")
        for antigo, novo in ANTIGOS.items():
            with self.subTest(rota=antigo):
                if novo is None:
                    self.assertRegex(JS, r'case\s+"%s"\s*:' % antigo)
                else:
                    self.assertEqual(tabela.get(antigo), novo)

    def test_o_destino_de_cada_alias_tambem_abre_alguma_coisa(self):
        for antigo, destino in self.tabela().items():
            tela = destino[2:].split("/")[0]
            with self.subTest(alias=antigo, destino=destino):
                self.assertRegex(JS, r'case\s+"%s"\s*:' % tela)

    def test_a_conta_abre_as_duas_abas(self):
        corpo = re.search(r'case "conta":(.*?)break;', JS, re.S)
        self.assertIsNotNone(corpo)
        self.assertIn('alvo === "entrada"', corpo.group(1))
        self.assertIn("pintarConsumo()", corpo.group(1))
        self.assertIn("pdCarregar()", corpo.group(1))

    def test_conectar_traz_a_secao_de_computadores(self):
        corpo = re.search(r'case "conectar":(.*?)break;', JS, re.S)
        self.assertIsNotNone(corpo)
        self.assertIn('tambem: ["computadores"]', corpo.group(1))
        self.assertIn("carregarComputadores()", corpo.group(1))
        self.assertIn('id="tela-computadores"', HTML)

    def test_as_abas_apontam_para_enderecos_que_abrem(self):
        abas = re.findall(r'<a href="(#/[^"]+)" data-aba="([^"]+)"', HTML)
        self.assertGreaterEqual(len(abas), 6, abas)
        for href, aba in abas:
            tela = href[2:].split("/")[0]
            with self.subTest(aba=aba, href=href):
                self.assertRegex(JS, r'case\s+"%s"\s*:' % tela)

    def test_abas_sem_estilo_embutido(self):
        """A CSP descarta `style=`: a aba e' estilizada por classe."""
        for bloco in re.findall(r'<div class="abas".*?</div>', HTML, re.S):
            self.assertNotIn("style=", bloco)
        self.assertRegex(re.sub(r"/\*.*?\*/", "",
                                (AQUI / "assets" / "painel.css").read_text(
                                    encoding="utf-8"), flags=re.S),
                         r"\.abas\s+a\[aria-current=\"page\"\]")


class OBotaoConsertarSoExisteAtrasDeConsertavel(unittest.TestCase):
    ROTULO = "Consertar com IA"

    def test_o_rotulo_aparece_uma_vez_so_e_dentro_de_pintarAlerta(self):
        self.assertEqual(JS.count(self.ROTULO), 1,
                         "o rotulo ficou em mais de um lugar: cada um e' um "
                         "botao que pode escapar da guarda")
        self.assertIn(self.ROTULO, corpo_da_funcao("pintarAlerta"))
        self.assertNotIn(self.ROTULO, HTML,
                         "o botao nao pode nascer escrito no HTML: ele "
                         "existiria para todo alerta")

    def test_o_if_que_o_guarda_le_consertavel(self):
        corpo = corpo_da_funcao("pintarAlerta")
        i = corpo.index(self.ROTULO)
        # o `if (` mais proximo ANTES do rotulo e' quem o guarda.
        j = corpo.rindex("if (", 0, i)
        cabeca = corpo[j:corpo.index("\n", j)]
        self.assertIn("p.consertavel", cabeca,
                      "o botao esta guardado por %r, e nao por `p.consertavel`"
                      % cabeca)
        # O bloco tem de ABRIR na propria linha do `if`: `if (x) { }` seguido
        # de um bloco solto guardaria nada. (Sabotado: passava.)
        self.assertTrue(cabeca.rstrip().endswith("{"),
                        "o `if` nao abre o bloco do botao: %r" % cabeca)
        # ... e ninguem o fecha entre o `if` e o rotulo (o rotulo estaria FORA).
        entre = corpo[corpo.index("\n", j):i]
        self.assertNotIn("\n  }", entre,
                         "o bloco do `if` fecha antes do rotulo: o botao "
                         "escapou da guarda")

    def test_o_clique_chama_a_rota_do_servidor_com_o_id(self):
        corpo = corpo_da_funcao("consertarComIA")
        self.assertIn('"/api/consertar"', corpo)
        self.assertRegex(corpo, r"\{\s*id:\s*p\.id\s*\}")

    def test_o_clique_mostra_o_aviso_do_servidor_e_o_caminho_da_fila(self):
        corpo = corpo_da_funcao("consertarComIA")
        self.assertIn("Na fila. Aprove em Consertar.", corpo)
        self.assertIn("corpo.aviso", corpo)
        self.assertIn('href="#/trabalho" id="alerta-consertar-link"', HTML)

    def test_todo_erro_do_servidor_vira_frase_em_portugues(self):
        corpo = corpo_da_funcao("frasePorQueNaoConsertou")
        for status in ("401", "403", "404", "429"):
            with self.subTest(status=status):
                self.assertIn("status === " + status, corpo)
        # e a falha de rede e a resposta que nao e' JSON tem frase propria
        fun = corpo_da_funcao("consertarComIA")
        self.assertIn("catch", fun)
        self.assertIn("corpo.ok !== true", fun)


class OsNomesDeVerDetalheForamUnificados(unittest.TestCase):
    def test_nenhum_rotulo_antigo_sobrou(self):
        for antigo in ("Ver o que gerou este selo", "Ver o que gerou este alerta"):
            with self.subTest(rotulo=antigo):
                self.assertNotIn(antigo, JS)
                self.assertNotIn(antigo, HTML)

    def test_o_novo_existe_nos_tres_lugares(self):
        self.assertIn(">\n          Ver detalhes", HTML)
        self.assertEqual(JS.count('"Ver detalhes"'), 2)


class ODetalheDaTarefaMostraOPedidoDeAlteracao(unittest.TestCase):
    def test_o_link_existe_e_so_abre_endereco_seguro(self):
        self.assertIn('id="tarefa-pr"', HTML)
        self.assertIn("Ver o pedido de alteração", HTML)
        corpo = corpo_da_funcao("recarregarTarefa")
        self.assertIn("t.pr_url", corpo)
        self.assertIn("enderecoSeguro(t.pr_url)", corpo)


class APortaDoComputadorNaoMenteQuandoEleCalou(unittest.TestCase):
    """Em 29/09/2026 a porta 1 mostrava "[OK] conectado" para dois computadores
    mudos havia 26 dias. Estado vem do `visto_em` mais recente, nao da contagem.

    A funcao e pura e sem DOM, entao ela e EXECUTADA (node), nao so lida. Sem
    node o caso de comportamento e pulado -- os de texto abaixo continuam.
    """

    @staticmethod
    def _roda(lista, agora_iso):
        import json, shutil, subprocess
        node = shutil.which("node")
        if not node:
            return None
        ini = JS.index("const COMPUTADOR_CALADO_APOS_MS")
        fim = JS.index("function pintarConectar()")
        prog = (JS[ini:fim] + "\nconsole.log(JSON.stringify("
                "estadoDosComputadores(%s, Date.parse(%s))));"
                % (json.dumps(lista), json.dumps(agora_iso)))
        r = subprocess.run([node, "-"], input=prog, capture_output=True,
                           text=True, timeout=30)
        assert r.returncode == 0, r.stderr
        return json.loads(r.stdout)

    AGORA = "2026-09-29T18:00:00Z"

    def test_calado_ha_semanas_nao_e_conectado(self):
        r = self._roda([{"visto_em": "2026-09-03T12:00:00+00:00"},
                        {"visto_em": "2026-08-28T12:00:00+00:00"}], self.AGORA)
        if r is None:
            self.skipTest("sem node")
        self.assertEqual(r["estado"], "desconectado")
        self.assertTrue(r["calado"])
        self.assertTrue(r["vistoEm"].startswith("2026-09-03"))

    def test_o_mais_recente_da_lista_e_quem_manda(self):
        r = self._roda([{"visto_em": "2026-08-28T12:00:00+00:00"},
                        {"visto_em": "2026-09-29T17:50:00+00:00"}], self.AGORA)
        if r is None:
            self.skipTest("sem node")
        self.assertEqual(r["estado"], "conectado")
        self.assertFalse(r["calado"])

    def test_sem_carimbo_nenhum_nao_e_conectado(self):
        r = self._roda([{"visto_em": None}], self.AGORA)
        if r is None:
            self.skipTest("sem node")
        self.assertEqual(r["estado"], "desconectado")
        self.assertTrue(r["calado"])

    def test_lista_vazia_continua_desconectado(self):
        r = self._roda([], self.AGORA)
        if r is None:
            self.skipTest("sem node")
        self.assertEqual(r["estado"], "desconectado")
        self.assertFalse(r["calado"])

    def test_a_tela_usa_a_funcao_e_nao_a_contagem(self):
        corpo = corpo_da_funcao("pintarConectar")
        self.assertIn("estadoDosComputadores(COMPUTADORES", corpo)
        self.assertIn("vida.estado", corpo)
        self.assertNotIn('ligados ? "conectado"', corpo)


if __name__ == "__main__":
    unittest.main(verbosity=2)
