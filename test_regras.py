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


if __name__ == "__main__":
    unittest.main(verbosity=2)
