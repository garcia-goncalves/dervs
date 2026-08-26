# -*- coding: utf-8 -*-
"""Testes do motor de pendencias.

Regra de pendencia e contrato: entra um retrato do projeto, sai zero ou uma
pendencia, com gravidade e UMA acao. Por isso tem teste — e por isso o teste
veio antes do motor.

    python test_regras.py
"""
from __future__ import annotations

import unittest

import regras


def projeto(**mudancas):
    """Um projeto perfeitamente saudavel. Cada teste estraga um campo so."""
    base = {
        "nome": "exemplo",
        "caminho": r"C:\Users\Desktop\source\repos\exemplo",
        "titulo": "Exemplo",
        "resumo": "um resumo escrito a mao",
        "git": {
            "versionado": True, "branch": "main", "sujos": 0, "sujos_dias": None,
            "ahead": 0, "behind": 0, "dias_parado": 2,
            "tem_remoto": True, "remoto_slug": "thi-garcia/exemplo",
        },
        "grafo": {"indexado": True, "dias": 1},
        "memoria_crlf": [],
        "env_drift": {"faltando": [], "sobrando": []},
        "compose": True,
        "containers": [{"nome": "exemplo-db", "saudavel": True, "reiniciando": False}],
        "containers_esperados": ["exemplo"],
        "aberto_no_editor": True,
        "caso_vazio": False,
        "github": {"ci": {"conclusao": "success", "url": "u", "quando": "hoje"},
                   "prs": [], "vulns": {"total": 0, "url": "v"}},
        "pesado": {"deps_inseguras": []},
    }
    base.update(mudancas)
    return base


def so(pendencias, regra):
    return [p for p in pendencias if p["regra"] == regra]


class ProjetoSaudavel(unittest.TestCase):
    def test_nao_produz_pendencia_nenhuma(self):
        self.assertEqual(regras.avaliar([projeto()], quota=None), [])


class RegrasAltas(unittest.TestCase):
    def test_1_ci_vermelha(self):
        p = projeto(github={"ci": {"conclusao": "failure", "url": "https://run/9",
                                   "quando": "há 1 h"},
                            "prs": [], "vulns": {"total": 0, "url": "v"}})
        (item,) = so(regras.avaliar([p], quota=None), "ci_vermelha")
        self.assertEqual(item["gravidade"], "alta")
        self.assertEqual(item["acao"]["tipo"], "abrir_url")
        self.assertEqual(item["acao"]["url"], "https://run/9")

    def test_2_container_esperado_caiu(self):
        p = projeto(containers=[])
        (item,) = so(regras.avaliar([p], quota=None), "container_caido")
        self.assertEqual(item["gravidade"], "alta")
        self.assertEqual(item["acao"]["comando"], "docker_up")

    def test_2_container_reiniciando_tambem_conta(self):
        p = projeto(containers=[{"nome": "x", "saudavel": False, "reiniciando": True}])
        self.assertEqual(len(so(regras.avaliar([p], quota=None), "container_caido")), 1)

    def test_2_sem_container_esperado_nao_reclama(self):
        p = projeto(containers=[], containers_esperados=[])
        self.assertEqual(so(regras.avaliar([p], quota=None), "container_caido"), [])

    def test_2_projeto_fechado_no_editor_nao_reclama(self):
        """Container de projeto fechado nao e pendencia: e o comportamento certo."""
        p = projeto(containers=[], aberto_no_editor=False)
        self.assertEqual(so(regras.avaliar([p], quota=None), "container_caido"), [])

    def test_2_sem_saber_do_editor_fica_calado(self):
        p = projeto(containers=[], aberto_no_editor=None)
        self.assertEqual(so(regras.avaliar([p], quota=None), "container_caido"), [])

    def test_3_vulnerabilidade(self):
        p = projeto(github={"ci": {"conclusao": "success", "url": "u", "quando": ""},
                            "prs": [], "vulns": {"total": 3, "url": "https://alerts"}})
        (item,) = so(regras.avaliar([p], quota=None), "vulnerabilidade")
        self.assertEqual(item["gravidade"], "alta")
        self.assertIn("3", item["texto"])

    def test_4_nao_commitado_ha_mais_de_um_dia(self):
        p = projeto(git=dict(projeto()["git"], sujos=4, sujos_dias=3))
        (item,) = so(regras.avaliar([p], quota=None), "nao_commitado")
        self.assertEqual(item["gravidade"], "alta")
        self.assertEqual(item["acao"]["tipo"], "vscode")

    def test_4_sujo_de_hoje_nao_e_pendencia(self):
        p = projeto(git=dict(projeto()["git"], sujos=4, sujos_dias=0))
        self.assertEqual(so(regras.avaliar([p], quota=None), "nao_commitado"), [])

    def test_5_commit_nao_enviado(self):
        p = projeto(git=dict(projeto()["git"], ahead=2))
        (item,) = so(regras.avaliar([p], quota=None), "nao_enviado")
        self.assertEqual(item["gravidade"], "alta")
        self.assertEqual(item["acao"]["comando"], "git_push")

    def test_6_memoria_em_crlf(self):
        p = projeto(memoria_crlf=["a.md", "b.md"])
        (item,) = so(regras.avaliar([p], quota=None), "memoria_crlf")
        self.assertEqual(item["gravidade"], "alta")
        self.assertEqual(item["acao"]["comando"], "crlf_para_lf")
        self.assertIn("nunca carrega", item["texto"])

    def test_7_cota_de_actions_estourando(self):
        pend = regras.avaliar([projeto()], quota={"pct": 92, "minutos": 1840,
                                                  "cota": 2000, "url": "https://billing"})
        (item,) = so(pend, "cota_actions")
        self.assertEqual(item["gravidade"], "alta")
        self.assertEqual(item["projeto"], "")

    def test_7_cota_folgada_nao_reclama(self):
        pend = regras.avaliar([projeto()], quota={"pct": 40, "minutos": 800,
                                                  "cota": 2000, "url": "u"})
        self.assertEqual(so(pend, "cota_actions"), [])


class RegrasMedias(unittest.TestCase):
    def test_8_grafo_ausente(self):
        p = projeto(grafo={"indexado": False, "dias": None})
        (item,) = so(regras.avaliar([p], quota=None), "grafo_velho")
        self.assertEqual(item["gravidade"], "media")

    def test_8_grafo_velho(self):
        p = projeto(grafo={"indexado": True, "dias": 22})
        (item,) = so(regras.avaliar([p], quota=None), "grafo_velho")
        self.assertIn("22", item["texto"])

    def test_8_grafo_fresco_nao_reclama(self):
        self.assertEqual(so(regras.avaliar([projeto()], quota=None), "grafo_velho"), [])

    def test_9_pr_parado(self):
        p = projeto(github={"ci": {"conclusao": "success", "url": "u", "quando": ""},
                            "prs": [{"numero": 7, "titulo": "t", "url": "https://pr/7",
                                     "dias": 9}],
                            "vulns": {"total": 0, "url": "v"}})
        (item,) = so(regras.avaliar([p], quota=None), "pr_parado")
        self.assertEqual(item["gravidade"], "media")
        self.assertEqual(item["acao"]["url"], "https://pr/7")

    def test_9_pr_de_ontem_nao_e_pendencia(self):
        p = projeto(github={"ci": {"conclusao": "success", "url": "u", "quando": ""},
                            "prs": [{"numero": 7, "titulo": "t", "url": "u", "dias": 1}],
                            "vulns": {"total": 0, "url": "v"}})
        self.assertEqual(so(regras.avaliar([p], quota=None), "pr_parado"), [])

    def test_10_dependencia_insegura(self):
        p = projeto(pesado={"deps_inseguras": ["lodash", "axios"]})
        (item,) = so(regras.avaliar([p], quota=None), "dependencia_insegura")
        self.assertEqual(item["gravidade"], "media")

    def test_11_env_divergente(self):
        p = projeto(env_drift={"faltando": ["STRIPE_KEY"], "sobrando": []})
        (item,) = so(regras.avaliar([p], quota=None), "env_drift")
        self.assertEqual(item["gravidade"], "media")
        self.assertIn("STRIPE_KEY", item["acao"]["texto"])


class RegrasBaixas(unittest.TestCase):
    def test_12_parado_ha_mais_de_30_dias(self):
        p = projeto(git=dict(projeto()["git"], dias_parado=45))
        (item,) = so(regras.avaliar([p], quota=None), "abandonado")
        self.assertEqual(item["gravidade"], "baixa")

    def test_13_sem_remoto(self):
        p = projeto(git=dict(projeto()["git"], tem_remoto=False, remoto_slug=None))
        (item,) = so(regras.avaliar([p], quota=None), "sem_remoto")
        self.assertEqual(item["acao"]["tipo"], "copiar")
        self.assertIn("gh repo create", item["acao"]["texto"])

    def test_14_caso_vazio(self):
        (item,) = so(regras.avaliar([projeto(caso_vazio=True)], quota=None), "caso_vazio")
        self.assertEqual(item["gravidade"], "baixa")


class Comportamento(unittest.TestCase):
    def test_projeto_sem_git_nao_gera_avalanche(self):
        """Sem git nao da para saber nada de git: uma pendencia so, nao cinco."""
        p = projeto(git={"versionado": False})
        nomes = {i["regra"] for i in regras.avaliar([p], quota=None)}
        self.assertEqual(nomes & {"nao_commitado", "nao_enviado", "abandonado"}, set())

    def test_sem_camada_github_nao_inventa_pendencia(self):
        """GitHub fora do ar nao pode virar 'CI vermelha'. Ausencia != falha."""
        p = projeto(github=None)
        nomes = {i["regra"] for i in regras.avaliar([p], quota=None)}
        self.assertEqual(nomes & {"ci_vermelha", "pr_parado", "vulnerabilidade"}, set())

    def test_ordena_alta_antes_de_media_antes_de_baixa(self):
        p = projeto(git=dict(projeto()["git"], ahead=1, dias_parado=45),
                    grafo={"indexado": False, "dias": None})
        g = [i["gravidade"] for i in regras.avaliar([p], quota=None)]
        self.assertEqual(g, sorted(g, key=lambda x: ["alta", "media", "baixa"].index(x)))

    def test_id_e_estavel_entre_coletas(self):
        a = regras.avaliar([projeto(git=dict(projeto()["git"], ahead=1))], quota=None)
        b = regras.avaliar([projeto(git=dict(projeto()["git"], ahead=9))], quota=None)
        self.assertEqual([i["id"] for i in a], [i["id"] for i in b])

    def test_silenciada_nao_aparece(self):
        p = projeto(git=dict(projeto()["git"], ahead=1))
        (item,) = so(regras.avaliar([p], quota=None), "nao_enviado")
        self.assertEqual(regras.avaliar([p], quota=None, silenciadas={item["id"]: "9999"}), [])

class SiteDeProducao(unittest.TestCase):
    """Regra 15 — a unica pendencia desta lista que o CLIENTE percebe primeiro."""

    def gh(self, **site):
        base = dict(projeto()["github"])
        base["site"] = dict({"url": "https://exemplo.com.br"}, **site)
        return base

    def test_site_no_ar_nao_produz_pendencia(self):
        p = projeto(github=self.gh(ok=True, codigo=200))
        self.assertEqual(so(regras.avaliar([p]), "site_fora"), [])

    def test_site_que_nao_responde_e_pendencia_alta(self):
        p = projeto(github=self.gh(ok=False, codigo=0, erro="timeout"))
        pend = so(regras.avaliar([p]), "site_fora")
        self.assertEqual(len(pend), 1)
        self.assertEqual(pend[0]["gravidade"], "alta")
        self.assertEqual(pend[0]["acao"]["tipo"], "abrir_url")
        self.assertEqual(pend[0]["acao"]["url"], "https://exemplo.com.br")

    def test_erro_do_servidor_conta_como_fora_do_ar(self):
        p = projeto(github=self.gh(ok=False, codigo=503))
        self.assertEqual(len(so(regras.avaliar([p]), "site_fora")), 1)

    def test_projeto_sem_endereco_de_producao_fica_calado(self):
        """Invariante 2: camada nao medida nao vira alarme."""
        p = projeto()                       # o github base nao tem 'site'
        self.assertEqual(so(regras.avaliar([p]), "site_fora"), [])

    def test_camada_github_ausente_fica_calada(self):
        p = projeto(github=None)
        self.assertEqual(so(regras.avaliar([p]), "site_fora"), [])

    def test_o_texto_nao_repete_a_url_crua_do_arquivo_do_dono(self):
        """A URL vai na ACAO, que o navegador trata; o texto e escrito por nos.

        Mesmo vindo de arquivo que so o dono escreve, texto de fora nao entra
        cru numa string que pode acabar num prompt. Foi assim que o titulo de PR
        de um estranho quase virou comando, em 25/08/2026."""
        p = projeto(github=self.gh(ok=False, codigo=500))
        t = so(regras.avaliar([p]), "site_fora")[0]["texto"]
        self.assertIn("exemplo", t)         # o NOME do projeto, nao a url
        self.assertNotIn("https://", t)


class ADocumentacaoNaoPodeMentir(unittest.TestCase):
    """A docstring dizia "as 14 regras" com 16 no arquivo, por meses.

    Documentacao que descreve o software de ontem mente com autoridade — e este
    projeto inteiro existe para acabar com numero errado com cara de certo.
    Contar na mao e o mesmo erro que o HUB corrige nos outros; entao conta o
    teste.
    """

    def _nomes(self):
        import re
        with open(regras.__file__, encoding="utf-8") as f:
            fonte = f.read()
        return sorted(set(re.findall(r'_p\(\s*\n?\s*"([a-z_]+)"', fonte)))

    def test_a_docstring_diz_o_numero_certo_de_regras(self):
        quantas = len(self._nomes())
        self.assertIn("as %d regras" % quantas, regras.__doc__,
                      "a docstring de regras.py esta desatualizada: sao %d" % quantas)

    def test_nenhuma_regra_repete_o_nome(self):
        import re
        with open(regras.__file__, encoding="utf-8") as f:
            fonte = f.read()
        todos = re.findall(r'_p\(\s*\n?\s*"([a-z_]+)"', fonte)
        # grafo_velho aparece duas vezes de proposito (ausente / velho): sao dois
        # textos para a mesma pendencia, e o id continua um so por projeto.
        repetidos = {n for n in todos if todos.count(n) > 1}
        self.assertEqual(repetidos, {"grafo_velho"})


class AuditoriaQueNaoRodou(unittest.TestCase):
    """Regra 17. A diferenca entre "auditei e esta limpo" e "nao auditei".

    Nasceu de um defeito real (26/08/2026): o `npm audit` era invocado de um
    jeito que, em Linux, nao rodava — e o motor, vendo lista vazia, ficava
    calado. Auditoria de seguranca que nunca aconteceu, com cara de auditoria
    limpa. Na VPS isso valeria para todos os projetos, todo dia.

    A regra tem de ficar em pe SEM atropelar o invariante 2: ausencia de camada
    continua sendo silencio. So falamos quando TENTAMOS e falhamos.
    """

    def test_auditoria_limpa_nao_produz_pendencia(self):
        p = projeto(pesado={"deps_inseguras": []})
        self.assertEqual(so(regras.avaliar([p]), "auditoria_nao_rodou"), [])

    def test_camada_pesada_ausente_fica_calada(self):
        """Invariante 2: nunca rodou != rodou e falhou."""
        for ausente in ({}, None):
            with self.subTest(pesado=ausente):
                p = projeto(pesado=ausente)
                self.assertEqual(so(regras.avaliar([p]), "auditoria_nao_rodou"), [])

    def test_tentou_e_falhou_produz_uma_pendencia(self):
        p = projeto(pesado={"deps_inseguras": None, "auditoria_falhou": True})
        achadas = so(regras.avaliar([p]), "auditoria_nao_rodou")
        self.assertEqual(len(achadas), 1)

    def test_a_pendencia_tem_acao_de_verdade(self):
        """Invariante 1: sem acao nao e pendencia, e estatistica."""
        p = projeto(pesado={"deps_inseguras": None, "auditoria_falhou": True})
        acao = so(regras.avaliar([p]), "auditoria_nao_rodou")[0]["acao"]
        self.assertIn(acao["tipo"], regras.ACOES)
        self.assertTrue(acao.get("texto") or acao.get("url"))

    def test_o_texto_diz_que_nao_sabemos_nao_que_esta_limpo(self):
        p = projeto(pesado={"deps_inseguras": None, "auditoria_falhou": True})
        t = so(regras.avaliar([p]), "auditoria_nao_rodou")[0]["texto"].lower()
        self.assertIn("exemplo", t)
        self.assertNotIn("limpo", t)
        self.assertNotIn("seguro", t)

    def test_id_estavel_para_poder_silenciar(self):
        """Invariante 3."""
        p = projeto(pesado={"deps_inseguras": None, "auditoria_falhou": True})
        self.assertEqual(so(regras.avaliar([p]), "auditoria_nao_rodou")[0]["id"],
                         "auditoria_nao_rodou:exemplo")

    def test_nao_se_dobra_com_a_regra_de_dependencia_insegura(self):
        """Falhou = nao ha lista. As duas juntas seriam contradicao na tela."""
        p = projeto(pesado={"deps_inseguras": None, "auditoria_falhou": True})
        pend = regras.avaliar([p])
        self.assertEqual(so(pend, "dependencia_insegura"), [])
        self.assertEqual(len(so(pend, "auditoria_nao_rodou")), 1)

    def test_falha_nao_ofusca_uma_pendencia_alta_do_mesmo_projeto(self):
        p = projeto(pesado={"deps_inseguras": None, "auditoria_falhou": True},
                    github={"ci": {"conclusao": "failure", "url": "u", "quando": "hoje"},
                            "prs": [], "vulns": {"total": 0, "url": "v"}})
        pend = regras.avaliar([p])
        self.assertEqual(pend[0]["gravidade"], "alta")
        self.assertTrue(so(pend, "auditoria_nao_rodou"))


class TrabalhoNaoPublicado(unittest.TestCase):
    """Regra 16 — o que esta na main do GitHub e mais novo que o que esta no ar."""

    def gh(self, **deploy):
        base = dict(projeto()["github"])
        base["deploy"] = dict({"url": "https://github.com/x/y/actions"}, **deploy)
        return base

    def test_publicado_em_dia_nao_produz_pendencia(self):
        p = projeto(github=self.gh(atras=0, sha="abc1234"))
        self.assertEqual(so(regras.avaliar([p]), "nao_publicado"), [])

    def test_commits_alem_do_ultimo_deploy_viram_pendencia_media(self):
        p = projeto(github=self.gh(atras=7, sha="abc1234"))
        pend = so(regras.avaliar([p]), "nao_publicado")
        self.assertEqual(len(pend), 1)
        self.assertEqual(pend[0]["gravidade"], "media")
        self.assertIn("7", pend[0]["texto"])
        self.assertEqual(pend[0]["acao"]["tipo"], "abrir_url")

    def test_repositorio_sem_workflow_de_deploy_fica_calado(self):
        """Nao saber nao e o mesmo que estar atrasado."""
        p = projeto()                       # o github base nao tem 'deploy'
        self.assertEqual(so(regras.avaliar([p]), "nao_publicado"), [])

    def test_deploy_medido_mas_sem_numero_fica_calado(self):
        p = projeto(github=self.gh(atras=None, sha=""))
        self.assertEqual(so(regras.avaliar([p]), "nao_publicado"), [])


class MotorInteiro(unittest.TestCase):
    def test_toda_pendencia_tem_acao(self):
        """O principio que impede o painel de virar spam."""
        p = projeto(git={"versionado": False}, grafo={"indexado": False, "dias": None},
                    memoria_crlf=["a.md"], caso_vazio=True,
                    env_drift={"faltando": ["X"], "sobrando": []},
                    containers=[], aberto_no_editor=True,
                    pesado={"deps_inseguras": ["lodash"]},
                    github={"ci": {"conclusao": "failure", "url": "u", "quando": ""},
                            "prs": [{"numero": 1, "titulo": "t", "url": "u", "dias": 30}],
                            "vulns": {"total": 1, "url": "v"}})
        pend = regras.avaliar([p], quota={"pct": 99, "minutos": 1, "cota": 1, "url": "u"})
        self.assertTrue(pend)
        for i in pend:
            self.assertIn(i["acao"]["tipo"], regras.ACOES, i["regra"])
            self.assertTrue(i["acao"]["rotulo"], i["regra"])
            self.assertTrue(i["texto"], i["regra"])


class AlertaOrdenadoPorRiscoNaoPorContagem(unittest.TestCase):
    """93 alertas baixos nao sao mais urgentes que 6 criticos.

    Ordenar por contagem manda o dono comecar pelo projeto errado.
    """

    @staticmethod
    def _com(vulns):
        return projeto(github={"ci": {"conclusao": "success", "url": "u", "quando": ""},
                               "prs": [], "vulns": dict(vulns, url="https://alerts")})

    def test_a_frase_diz_a_severidade_nao_so_o_total(self):
        """Caso real do workspace-medconsultoria em 25/08/2026."""
        p = self._com({"total": 19, "sev": {"critical": 6, "high": 7,
                                            "moderate": 3, "low": 3},
                       "pacotes": 12, "defeitos": 14})
        (item,) = so(regras.avaliar([p], quota=None), "vulnerabilidade")
        self.assertIn("6 crítico", item["texto"])
        self.assertEqual(item["gravidade"], "alta")

    def test_a_frase_diz_o_tamanho_real_do_trabalho(self):
        """Os 93 do medconsultoria eram 17 pacotes. A tela precisa dizer isso."""
        p = self._com({"total": 93, "sev": {"critical": 2, "high": 44,
                                            "moderate": 36, "low": 11},
                       "pacotes": 17, "defeitos": 30})
        (item,) = so(regras.avaliar([p], quota=None), "vulnerabilidade")
        self.assertIn("17 pacote", item["texto"])

    def test_so_moderado_e_baixo_nao_e_alta(self):
        p = self._com({"total": 8, "sev": {"critical": 0, "high": 0,
                                           "moderate": 5, "low": 3},
                       "pacotes": 4, "defeitos": 6})
        (item,) = so(regras.avaliar([p], quota=None), "vulnerabilidade")
        self.assertEqual(item["gravidade"], "media")
        self.assertNotIn("crítico", item["texto"])

    def test_um_critico_sozinho_ja_e_alta(self):
        p = self._com({"total": 1, "sev": {"critical": 1, "high": 0,
                                           "moderate": 0, "low": 0},
                       "pacotes": 1, "defeitos": 1})
        (item,) = so(regras.avaliar([p], quota=None), "vulnerabilidade")
        self.assertEqual(item["gravidade"], "alta")

    def test_severidade_nao_medida_continua_alta(self):
        """NAO SABER a severidade nao e o mesmo que ela ser baixa.

        Coleta antiga no banco, ou permissao que so deu totalCount, cai aqui.
        Rebaixar por falta de dado seria a quinta forma de o painel mentir.
        """
        p = self._com({"total": 3})
        (item,) = so(regras.avaliar([p], quota=None), "vulnerabilidade")
        self.assertEqual(item["gravidade"], "alta")
        self.assertIn("3", item["texto"])

    def test_amostra_parcial_nao_afirma_o_que_nao_mediu(self):
        """203 alertas nao cabem nos 100 nos do GraphQL.

        Com amostra, a frase nao pode dizer "6 criticos de 203" â€” ela so pode
        dizer "pelo menos 6". E a gravidade nao pode cair, porque o critico pode
        estar justamente na parte que nao veio.
        """
        p = self._com({"total": 203, "sev": {"critical": 0, "high": 0,
                                             "moderate": 2, "low": 1},
                       "pacotes": 3, "defeitos": 3, "amostra": True})
        (item,) = so(regras.avaliar([p], quota=None), "vulnerabilidade")
        self.assertEqual(item["gravidade"], "alta")
        self.assertIn("pelo menos", item["texto"])

    def test_zero_alerta_continua_sem_pendencia(self):
        p = self._com({"total": 0, "sev": {"critical": 0, "high": 0,
                                           "moderate": 0, "low": 0},
                       "pacotes": 0, "defeitos": 0})
        self.assertEqual(so(regras.avaliar([p], quota=None), "vulnerabilidade"), [])

class AlertaDeSegurancaNaoSeDobra(unittest.TestCase):
    """Agrupar mata ruido; alerta de seguranca NAO e ruido.

    Os quatro projetos com alerta em 25/08/2026 tinham gravidades muito
    diferentes: workspace-medconsultoria com 6 criticos e medconsultoria com 93
    alertas dos quais 11 baixos. Dobrar isso em "4 projetos com alertas de
    seguranca abertos" apaga exatamente o numero que diz por onde comecar — o
    mesmo defeito que a coleta por severidade acabou de consertar, reaparecendo
    um andar acima.
    """

    @staticmethod
    def _v(projeto, texto):
        return {"id": "vulnerabilidade:" + projeto, "regra": "vulnerabilidade",
                "gravidade": "alta", "projeto": projeto, "texto": texto,
                "detalhe": "", "acao": {}, "dias": 3}

    def test_quatro_projetos_com_alerta_continuam_quatro_linhas(self):
        ps = [self._v("p%d" % i, "%d crítico(s)" % i) for i in range(4)]
        saida = regras.agrupar(ps)
        self.assertEqual([x["tipo"] for x in saida], ["item"] * 4)

    def test_a_severidade_de_cada_projeto_sobrevive_na_tela(self):
        ps = [self._v("ws", "6 crítico(s) e 7 alto(s) entre 19"),
              self._v("med", "2 crítico(s) e 44 alto(s) entre 93"),
              self._v("inv", "12 alto(s) entre 20"),
              self._v("odo", "1 crítico(s) e 40 alto(s) entre 71")]
        textos = " | ".join(x["pendencia"]["texto"] for x in regras.agrupar(ps))
        self.assertIn("6 crítico", textos)
        self.assertIn("12 alto", textos)

    def test_as_outras_regras_continuam_agrupando(self):
        """A trava e so para seguranca; o fim do ruido nao pode ser desfeito."""
        ps = [{"id": "grafo_velho:p%d" % i, "regra": "grafo_velho",
               "gravidade": "media", "projeto": "p%d" % i, "texto": "t",
               "detalhe": "", "acao": {}, "dias": 2} for i in range(4)]
        (g,) = regras.agrupar(ps)
        self.assertEqual(g["tipo"], "grupo")
        self.assertEqual(g["n"], 4)

class OMaisPerigosoVemPrimeiro(unittest.TestCase):
    """Empate de gravidade nao pode ser desempatado pelo alfabeto.

    Medido no painel em 25/08/2026, ja com a severidade na frase: as quatro
    linhas de alerta sairam `investrix` (12 altos, zero critico) ANTES de
    `workspace-medconsultoria` (6 criticos), porque `i` vem antes de `w`. A
    frase dizia a verdade e a ordem ainda mandava o dono para o lugar errado.
    """

    @staticmethod
    def _v(projeto, critico, alto):
        return regras._p(
            "vulnerabilidade", "alta", projeto, "t",
            {"tipo": "abrir_url", "rotulo": "Ver os alertas", "url": "u"},
            risco=regras.risco_alerta({"sev": {"critical": critico, "high": alto}}))

    def test_seis_criticos_vem_antes_de_doze_altos(self):
        ps = [self._v("investrix", 0, 12), self._v("workspace", 6, 7)]
        ordem = [x["pendencia"]["projeto"] for x in regras.agrupar(ps)]
        self.assertEqual(ordem, ["workspace", "investrix"])

    def test_sem_critico_desempata_pelo_numero_de_altos(self):
        ps = [self._v("a", 0, 5), self._v("b", 0, 40)]
        ordem = [x["pendencia"]["projeto"] for x in regras.agrupar(ps)]
        self.assertEqual(ordem, ["b", "a"])

    def test_um_critico_ganha_de_qualquer_quantidade_de_altos(self):
        """Critico e alto nao sao a mesma moeda: 1 critico > 40 altos."""
        ps = [self._v("muitos_altos", 0, 40), self._v("um_critico", 1, 0)]
        ordem = [x["pendencia"]["projeto"] for x in regras.agrupar(ps)]
        self.assertEqual(ordem, ["um_critico", "muitos_altos"])

    def test_risco_nao_atropela_a_gravidade(self):
        """Uma media com 99 de risco continua depois de qualquer alta."""
        alta = regras._p("nao_enviado", "alta", "z", "t", {}, risco=0)
        media = regras._p("vulnerabilidade", "media", "a", "t", {}, risco=99)
        ordem = [x["pendencia"]["gravidade"] for x in regras.agrupar([media, alta])]
        self.assertEqual(ordem, ["alta", "media"])

    def test_pendencia_sem_risco_declarado_nao_quebra_a_ordem(self):
        """Toda regra que nao mede risco fica em zero e ordena como sempre."""
        ps = [regras._p("abandonado", "baixa", p, "t", {}) for p in ("b", "a")]
        ordem = [x["pendencia"]["projeto"] for x in regras.agrupar(ps)]
        self.assertEqual(ordem, ["a", "b"])

    def test_o_risco_ignora_moderado_e_baixo(self):
        """Sao 47 dos 203 alertas reais; se contassem, virariam o desempate."""
        self.assertEqual(
            regras.risco_alerta({"sev": {"critical": 0, "high": 0,
                                         "moderate": 99, "low": 99}}), 0)

    def test_sem_severidade_medida_o_risco_e_zero_e_nao_um_chute(self):
        self.assertEqual(regras.risco_alerta({"total": 93}), 0)

if __name__ == "__main__":
    unittest.main(verbosity=2)
