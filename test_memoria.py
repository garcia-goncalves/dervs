# -*- coding: utf-8 -*-
"""Testes da memoria do tempo: idade da pendencia, tendencia e briefing.

O painel so pode dizer "voce fechou 6 coisas esta semana" se alguem guardar
quando cada pendencia nasceu e quando sumiu. Isso e regra de negocio — tem
contrato, entao tem teste, e o teste veio antes.

    python test_memoria.py
"""
from __future__ import annotations

import sqlite3
import unittest
from datetime import datetime, timedelta, timezone

import memoria
import regras


def iso(dt) -> str:
    return dt.isoformat(timespec="seconds")


AGORA = datetime(2026, 8, 25, 14, 0, 0, tzinfo=timezone.utc)


def atras(**kw) -> str:
    return iso(AGORA - timedelta(**kw))


def pend(regra="grafo_velho", projeto="exemplo", gravidade="media", texto="t"):
    return {"id": "%s:%s" % (regra, projeto), "regra": regra, "projeto": projeto,
            "gravidade": gravidade, "texto": texto, "detalhe": "",
            "acao": {"tipo": "copiar", "rotulo": "Copiar", "texto": "x"}}


def banco_de_teste() -> sqlite3.Connection:
    """Um banco na memoria, com o mesmo esquema do de verdade."""
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    import banco
    con.executescript(banco.ESQUEMA)
    return con


# ------------------------------------------------------------------ registrar
class Registrar(unittest.TestCase):
    def setUp(self):
        self.con = banco_de_teste()

    def tearDown(self):
        self.con.close()

    def test_pendencia_nova_ganha_data_de_nascimento(self):
        memoria.registrar([pend()], self.con, iso(AGORA))
        v = memoria.vidas(self.con)
        self.assertIn("grafo_velho:exemplo", v)
        self.assertEqual(v["grafo_velho:exemplo"]["visto_em"], iso(AGORA))
        self.assertIsNone(v["grafo_velho:exemplo"]["fechada_em"])

    def test_pendencia_que_continua_nao_rejuvenesce(self):
        """O ponto inteiro da tabela: a segunda coleta nao pode zerar a idade."""
        memoria.registrar([pend()], self.con, atras(days=10))
        memoria.registrar([pend()], self.con, iso(AGORA))
        v = memoria.vidas(self.con)["grafo_velho:exemplo"]
        self.assertEqual(v["visto_em"], atras(days=10))
        self.assertEqual(v["ultimo_em"], iso(AGORA))
        self.assertIsNone(v["fechada_em"])

    def test_pendencia_que_sumiu_e_marcada_como_fechada(self):
        memoria.registrar([pend()], self.con, atras(days=2))
        memoria.registrar([], self.con, iso(AGORA))
        v = memoria.vidas(self.con, so_abertas=False)["grafo_velho:exemplo"]
        self.assertEqual(v["fechada_em"], iso(AGORA))

    def test_a_leitura_do_painel_nao_arrasta_as_fechadas(self):
        """Custo: vidas() roda a cada 15 s por aba, e a tabela nunca e podada."""
        memoria.registrar([pend(projeto="a"), pend(projeto="b")],
                          self.con, atras(days=2))
        memoria.registrar([pend(projeto="a")], self.con, iso(AGORA))
        self.assertEqual(sorted(memoria.vidas(self.con)), ["grafo_velho:a"])
        self.assertEqual(len(memoria.vidas(self.con, so_abertas=False)), 2)

    def test_pendencia_que_volta_reabre_com_data_nova(self):
        """Voltou depois de fechada e uma pendencia NOVA, nao a velha de antes."""
        memoria.registrar([pend()], self.con, atras(days=30))
        memoria.registrar([], self.con, atras(days=20))
        memoria.registrar([pend()], self.con, iso(AGORA))
        v = memoria.vidas(self.con)["grafo_velho:exemplo"]
        self.assertEqual(v["visto_em"], iso(AGORA))
        self.assertIsNone(v["fechada_em"])

    def test_registrar_grava_o_retrato_no_historico(self):
        memoria.registrar([pend(gravidade="alta"), pend(projeto="outro")],
                          self.con, iso(AGORA))
        linhas = dict((l["chave"], l["valor"]) for l in
                      self.con.execute("SELECT chave, valor FROM historico"))
        self.assertEqual(linhas["abertas_total"], 2)
        self.assertEqual(linhas["abertas_alta"], 1)
        self.assertEqual(linhas["abertas_media"], 1)
        self.assertEqual(linhas["abertas_baixa"], 0)

    def test_registrar_nao_estoura_com_lista_vazia(self):
        memoria.registrar([], self.con, iso(AGORA))
        self.assertEqual(memoria.vidas(self.con), {})

    def test_medicao_invalida_nao_fecha_nada(self):
        """Coleta que nao viu projeto nenhum NAO e 'o dono resolveu tudo'.

        Sem esta guarda, uma pasta de repositorios indisponivel por um instante
        fecharia as 27 pendencias de uma vez — incluindo as de seguranca — e no
        minuto seguinte o briefing se gabaria de ter fechado 27. Achado da
        revisao de seguranca de 25/08/2026.
        """
        memoria.registrar([pend(projeto="a"), pend(projeto="b")],
                          self.con, atras(days=1))
        r = memoria.registrar([], self.con, iso(AGORA), medicao_valida=False)
        self.assertTrue(r.get("ignorado"))
        self.assertEqual(len(memoria.vidas(self.con)), 2)      # continuam ABERTAS
        self.assertEqual(memoria.tendencia(self.con, iso(AGORA))["resolvidas_7d"], 0)

    def test_retrato_repetido_nao_vira_linha_nova(self):
        """4 linhas por minuto para sempre sao 2 milhoes por ano, quase todas
        iguais — e grafico feito de 10 mil pontos identicos nao mostra forma."""
        memoria.registrar([pend()], self.con, atras(minutes=30))
        n1 = self.con.execute("SELECT COUNT(*) FROM historico").fetchone()[0]
        r = memoria.registrar([pend()], self.con, atras(minutes=29))
        n2 = self.con.execute("SELECT COUNT(*) FROM historico").fetchone()[0]
        self.assertEqual(n1, n2)
        self.assertFalse(r["retrato"])

    def test_numero_que_muda_grava_na_hora(self):
        memoria.registrar([pend()], self.con, atras(minutes=30))
        n1 = self.con.execute("SELECT COUNT(*) FROM historico").fetchone()[0]
        r = memoria.registrar([pend(), pend(projeto="b")], self.con, atras(minutes=29))
        n2 = self.con.execute("SELECT COUNT(*) FROM historico").fetchone()[0]
        self.assertGreater(n2, n1)
        self.assertTrue(r["retrato"])

    def test_uma_hora_parada_ainda_deixa_batimento(self):
        """Sem isto, um dia inteiro sem novidade viraria um ponto so e o
        sparkline sumiria — 'nada mudou' tambem e informacao a desenhar."""
        memoria.registrar([pend()], self.con, atras(hours=3))
        r = memoria.registrar([pend()], self.con, atras(hours=1))
        self.assertTrue(r["retrato"])

    def test_medicao_invalida_nao_grava_retrato_falso_no_historico(self):
        memoria.registrar([pend(projeto="a")], self.con, atras(days=1))
        antes = self.con.execute("SELECT COUNT(*) FROM historico").fetchone()[0]
        memoria.registrar([], self.con, iso(AGORA), medicao_valida=False)
        depois = self.con.execute("SELECT COUNT(*) FROM historico").fetchone()[0]
        self.assertEqual(antes, depois)


# -------------------------------------------------------------------- decorar
class Decorar(unittest.TestCase):
    def test_pendencia_de_hoje_e_nova(self):
        v = {"grafo_velho:exemplo": {"visto_em": atras(hours=3), "fechada_em": None}}
        d = memoria.decorar([pend()], v, iso(AGORA))[0]
        self.assertTrue(d["nova"])
        self.assertEqual(d["dias"], 0)

    def test_pendencia_velha_traz_a_idade_em_dias(self):
        v = {"grafo_velho:exemplo": {"visto_em": atras(days=23), "fechada_em": None}}
        d = memoria.decorar([pend()], v, iso(AGORA))[0]
        self.assertFalse(d["nova"])
        self.assertEqual(d["dias"], 23)

    def test_pendencia_sem_vida_conhecida_nao_mente_idade(self):
        """Sem registro, a idade e desconhecida — nao e zero, e nao e 'nova'.

        Zero seria pior que nada: marcaria de 'nova' toda pendencia antiga na
        primeira coleta depois desta mudanca, bem no dia em que a tela estreia.
        """
        d = memoria.decorar([pend()], {}, iso(AGORA))[0]
        self.assertIsNone(d["dias"])
        self.assertFalse(d["nova"])

    def test_decorar_nao_altera_a_lista_original(self):
        p = pend()
        memoria.decorar([p], {}, iso(AGORA))
        self.assertNotIn("dias", p)

    def test_quem_ja_estava_ali_quando_a_memoria_comecou_nao_e_nova(self):
        """A armadilha da estreia, e o motivo de `desde` existir.

        Na PRIMEIRA coleta depois desta mudanca, todas as 27 pendencias abertas
        ganham `visto_em` = agora — inclusive o grafo velho ha 23 dias. Sem esta
        trava a tela estrearia dizendo "nova" para 27 coisas antigas, e o dono
        aprenderia na primeira olhada que o selo mente. Idade desconhecida se
        diz calando, nao chutando zero.
        """
        inicio = atras(hours=1)
        v = {"grafo_velho:exemplo": {"visto_em": inicio, "fechada_em": None}}
        d = memoria.decorar([pend()], v, iso(AGORA), desde=inicio)[0]
        self.assertFalse(d["nova"])
        self.assertIsNone(d["dias"])
        self.assertTrue(d["desde_o_inicio"])

    def test_idade_desconhecida_vira_um_piso_honesto(self):
        """Nao saber a idade exata nao e o mesmo que nao saber nada.

        A memoria sabe ha quanto tempo ELA existe. Se a pendencia ja estava aqui
        quando ela comecou, a idade e no MINIMO essa — e "aberta ha mais de 9
        dias" e informacao util, enquanto "ha mais tempo do que eu lembro" e
        uma frase comprida que nao ajuda ninguem a priorizar.
        """
        inicio = atras(days=9)
        v = {"grafo_velho:exemplo": {"visto_em": inicio, "fechada_em": None}}
        d = memoria.decorar([pend()], v, iso(AGORA), desde=inicio)[0]
        self.assertEqual(d["dias_min"], 9)
        self.assertIsNone(d["dias"])

    def test_memoria_com_menos_de_um_dia_nao_da_piso_nenhum(self):
        inicio = atras(hours=3)
        v = {"grafo_velho:exemplo": {"visto_em": inicio, "fechada_em": None}}
        d = memoria.decorar([pend()], v, iso(AGORA), desde=inicio)[0]
        self.assertEqual(d["dias_min"], 0)

    def test_quem_nasceu_depois_do_inicio_da_memoria_e_nova_de_verdade(self):
        v = {"grafo_velho:exemplo": {"visto_em": atras(hours=2), "fechada_em": None}}
        d = memoria.decorar([pend()], v, iso(AGORA), desde=atras(days=9))[0]
        self.assertTrue(d["nova"])
        self.assertEqual(d["dias"], 0)
        self.assertFalse(d["desde_o_inicio"])


# ------------------------------------------------------------------ tendencia
class Tendencia(unittest.TestCase):
    def setUp(self):
        self.con = banco_de_teste()

    def tearDown(self):
        self.con.close()

    def test_conta_as_que_nasceram_nas_ultimas_24h(self):
        memoria.registrar([pend(projeto="velho")], self.con, atras(days=5))
        memoria.registrar([pend(projeto="velho"), pend(projeto="novo")],
                          self.con, atras(hours=2))
        t = memoria.tendencia(self.con, iso(AGORA))
        self.assertEqual(t["novas_24h"], 1)

    def test_conta_as_fechadas_na_semana(self):
        memoria.registrar([pend(projeto="a"), pend(projeto="b"), pend(projeto="c")],
                          self.con, atras(days=6))
        memoria.registrar([pend(projeto="c")], self.con, atras(days=3))
        t = memoria.tendencia(self.con, iso(AGORA))
        self.assertEqual(t["resolvidas_7d"], 2)

    def test_fechada_ha_muito_tempo_nao_conta_na_semana(self):
        memoria.registrar([pend(projeto="a")], self.con, atras(days=40))
        memoria.registrar([], self.con, atras(days=30))
        t = memoria.tendencia(self.con, iso(AGORA))
        self.assertEqual(t["resolvidas_7d"], 0)

    def test_abertas_por_gravidade(self):
        memoria.registrar([pend(gravidade="alta"), pend(projeto="b", gravidade="alta"),
                           pend(projeto="c", gravidade="baixa")], self.con, iso(AGORA))
        t = memoria.tendencia(self.con, iso(AGORA))
        self.assertEqual(t["abertas"]["alta"], 2)
        self.assertEqual(t["abertas"]["baixa"], 1)
        self.assertEqual(t["abertas"]["total"], 3)

    def test_direcao_piorando_quando_nascem_mais_do_que_fecham(self):
        memoria.registrar([pend(projeto="a")], self.con, atras(days=3))
        memoria.registrar([pend(projeto="a"), pend(projeto="b"), pend(projeto="c")],
                          self.con, atras(hours=1))
        self.assertEqual(memoria.tendencia(self.con, iso(AGORA))["direcao"], "piorando")

    def test_direcao_melhorando_quando_fecham_mais_do_que_nascem(self):
        memoria.registrar([pend(projeto="a"), pend(projeto="b"), pend(projeto="c")],
                          self.con, atras(days=3))
        memoria.registrar([pend(projeto="a")], self.con, atras(hours=1))
        self.assertEqual(memoria.tendencia(self.con, iso(AGORA))["direcao"], "melhorando")

    def test_a_primeira_coleta_nao_inventa_27_novidades(self):
        """A armadilha da estreia, do lado da tendencia.

        Na estreia, TODAS as pendencias abertas ganham visto_em=agora. Sem esta
        trava o briefing anunciaria "27 apareceram nas ultimas 24 h" no primeiro
        minuto de vida da memoria — e nenhuma delas era nova. Uma frase dessas
        no topo da tela, no dia da estreia, ensina que o topo da tela mente.
        """
        memoria.registrar([pend(projeto="p%d" % i) for i in range(27)],
                          self.con, iso(AGORA))
        t = memoria.tendencia(self.con, iso(AGORA))
        self.assertEqual(t["novas_24h"], 0)
        self.assertEqual(t["direcao"], "estavel")
        self.assertEqual(t["abertas"]["total"], 27)   # abertas SIM, novas NAO

    def test_depois_da_estreia_a_novidade_conta_de_verdade(self):
        memoria.registrar([pend(projeto="velho")], self.con, atras(days=3))
        memoria.registrar([pend(projeto="velho"), pend(projeto="novo")],
                          self.con, atras(hours=1))
        self.assertEqual(memoria.tendencia(self.con, iso(AGORA))["novas_24h"], 1)

    def test_banco_vazio_devolve_tendencia_zerada_sem_estourar(self):
        t = memoria.tendencia(self.con, iso(AGORA))
        self.assertEqual(t["novas_24h"], 0)
        self.assertEqual(t["resolvidas_7d"], 0)
        self.assertEqual(t["abertas"]["total"], 0)
        self.assertEqual(t["direcao"], "estavel")


# ------------------------------------------------------------------- briefing
def tend(novas=0, resolvidas=0, direcao="estavel", alta=0, media=0, baixa=0):
    return {"novas_24h": novas, "resolvidas_7d": resolvidas, "direcao": direcao,
            "abertas": {"alta": alta, "media": media, "baixa": baixa,
                        "total": alta + media + baixa},
            "serie": []}


class Briefing(unittest.TestCase):
    def test_dia_limpo_reconhece_o_trabalho_feito(self):
        t = memoria.briefing([], tend(resolvidas=6), hora=9)
        self.assertIn("6", t)
        self.assertNotIn("pede", t.lower())

    def test_com_alta_nunca_diz_que_esta_tudo_certo(self):
        """A trava que separa briefing util de enfeite."""
        ps = memoria.decorar([pend(regra="ci_vermelha", projeto="dents",
                                   gravidade="alta", texto="A CI do dents falhou.")],
                             {"ci_vermelha:dents": {"visto_em": AGORA.isoformat(),
                                                    "fechada_em": None}},
                             iso(AGORA))
        t = memoria.briefing(ps, tend(alta=1), hora=9)
        for proibido in ("tudo certo", "tudo em dia", "nada pendente"):
            self.assertNotIn(proibido, t.lower())

    def test_cita_o_projeto_que_mais_doi(self):
        ps = memoria.decorar(
            [pend(regra="ci_vermelha", projeto="dents", gravidade="alta"),
             pend(regra="grafo_velho", projeto="ccvp", gravidade="media")],
            {"ci_vermelha:dents": {"visto_em": atras(days=4), "fechada_em": None},
             "grafo_velho:ccvp": {"visto_em": atras(days=30), "fechada_em": None}},
            iso(AGORA))
        t = memoria.briefing(ps, tend(alta=1, media=1), hora=9)
        self.assertIn("dents", t)          # a ALTA vence a mais velha de gravidade menor

    def test_tres_estados_produzem_tres_textos_diferentes(self):
        """Briefing que nao muda com o dado e enfeite, nao briefing."""
        limpo = memoria.briefing([], tend(resolvidas=3), hora=9)
        com_alta = memoria.briefing(
            memoria.decorar([pend(regra="ci_vermelha", projeto="dents", gravidade="alta")],
                            {}, iso(AGORA)), tend(alta=1), hora=9)
        piorando = memoria.briefing(
            memoria.decorar([pend(regra="ci_vermelha", projeto="dents", gravidade="alta"),
                             pend(regra="site_fora", projeto="ccvp", gravidade="alta")],
                            {}, iso(AGORA)),
            tend(alta=2, novas=2, direcao="piorando"), hora=9)
        self.assertEqual(len({limpo, com_alta, piorando}), 3)

    def test_saudacao_segue_a_hora(self):
        self.assertTrue(memoria.briefing([], tend(), hora=8).startswith("Bom dia"))
        self.assertTrue(memoria.briefing([], tend(), hora=15).startswith("Boa tarde"))
        self.assertTrue(memoria.briefing([], tend(), hora=22).startswith("Boa noite"))

    def test_nunca_devolve_vazio(self):
        for h in (0, 6, 12, 19, 23):
            self.assertTrue(memoria.briefing([], tend(), hora=h).strip())


# ------------------------------------------------------------------- agrupar
class Agrupar(unittest.TestCase):
    def test_regra_repetida_tres_vezes_ou_mais_vira_um_grupo(self):
        ps = [pend(projeto=n) for n in ("a", "b", "c")]
        g = regras.agrupar(ps)
        self.assertEqual(len(g), 1)
        self.assertEqual(g[0]["tipo"], "grupo")
        self.assertEqual(g[0]["n"], 3)
        self.assertEqual(len(g[0]["itens"]), 3)

    def test_regra_com_duas_ocorrencias_continua_solta(self):
        ps = [pend(projeto="a"), pend(projeto="b")]
        g = regras.agrupar(ps)
        self.assertEqual([x["tipo"] for x in g], ["item", "item"])

    def test_nenhuma_pendencia_se_perde_no_agrupamento(self):
        ps = ([pend(projeto=n) for n in "abcde"] +
              [pend(regra="vulnerabilidade", projeto="x", gravidade="alta")])
        g = regras.agrupar(ps)
        dentro = []
        for x in g:
            dentro.extend(x["itens"] if x["tipo"] == "grupo" else [x["pendencia"]])
        self.assertEqual(sorted(i["id"] for i in dentro), sorted(i["id"] for i in ps))

    def test_o_grupo_herda_a_pior_gravidade_dos_seus_itens(self):
        ps = [pend(projeto="a"), pend(projeto="b"), pend(projeto="c", gravidade="alta")]
        self.assertEqual(regras.agrupar(ps)[0]["gravidade"], "alta")

    def test_grupo_vem_antes_de_item_menos_grave(self):
        # `ci_vermelha`, e nao `vulnerabilidade`: alerta de seguranca entrou em
        # NAO_AGRUPAR e nunca mais vira grupo. O que este teste mede — grupo
        # grave na frente de item leve — nao mudou; so o exemplo mudou.
        ps = ([pend(regra="ci_vermelha", projeto=n, gravidade="alta")
               for n in "abc"] + [pend(regra="abandonado", projeto="z", gravidade="baixa")])
        g = regras.agrupar(ps)
        self.assertEqual(g[0]["tipo"], "grupo")
        self.assertEqual(g[0]["gravidade"], "alta")

    def test_o_grupo_diz_a_idade_da_mais_velha(self):
        ps = [dict(pend(projeto="a"), dias=2), dict(pend(projeto="b"), dias=23),
              dict(pend(projeto="c"), dias=None)]
        self.assertEqual(regras.agrupar(ps)[0]["dias"], 23)

    def test_o_grupo_tem_acao_e_texto(self):
        """Invariante 1 do motor, na versao de grupo: sem o que fazer, nao entra."""
        g = regras.agrupar([pend(projeto=n) for n in "abc"])[0]
        self.assertTrue(g["texto"])
        self.assertTrue(g["acao"]["rotulo"])
        self.assertEqual(g["acao"]["tipo"], "expandir")

    def test_lista_vazia_devolve_lista_vazia(self):
        self.assertEqual(regras.agrupar([]), [])

    def test_toda_regra_do_motor_tem_rotulo_em_portugues(self):
        """A trava que impede o grupo de cair no texto generico caladamente.

        Sem este teste, uma regra nova entrava no motor e o card do grupo dizia
        "3 projetos com a mesma pendencia" — sem erro, sem aviso, so pior. Ja
        aconteceu: `so_no_disco` e `sem_descricao` estavam no dicionario, mas os
        ids reais eram `nao_enviado` e `caso_vazio`.
        """
        import re
        fonte = open("regras.py", encoding="utf-8").read()
        ids = {m.group(1) for m in re.finditer(r'_p\(\s*\n?\s*"([a-z_]+)"', fonte)}
        self.assertTrue(ids, "nao achei regra nenhuma na fonte")
        self.assertEqual(ids - set(regras.ROTULO_REGRA), set(),
                         "regra sem rótulo: o grupo cairia no texto genérico")
        self.assertEqual(set(regras.ROTULO_REGRA) - ids, set(),
                         "rótulo órfão: aponta para uma regra que não existe")

    def test_o_texto_do_grupo_usa_o_rotulo_certo(self):
        g = regras.agrupar([pend(regra="nao_enviado", projeto=n, gravidade="alta")
                            for n in "abc"])[0]
        self.assertIn("GitHub", g["texto"])
        self.assertNotIn("mesma pendência", g["texto"])

    def test_a_contagem_visivel_cai_com_os_dados_de_hoje(self):
        """27 pendencias reais de 25/08: 10 grafo_velho + 4 vulnerabilidade + 13 soltas."""
        ps = ([pend(regra="grafo_velho", projeto="g%d" % i) for i in range(10)] +
              [pend(regra="vulnerabilidade", projeto="v%d" % i, gravidade="alta")
               for i in range(4)] +
              [pend(regra="r%d" % i, projeto="p%d" % i) for i in range(13)])
        self.assertEqual(len(ps), 27)
        self.assertLessEqual(len(regras.agrupar(ps)), 18)


if __name__ == "__main__":
    unittest.main(verbosity=2)
