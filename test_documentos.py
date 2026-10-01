# -*- coding: utf-8 -*-
"""O leitor de documentacao e a conta do progresso (`documentos.py`).

MOTIVO: o DERVS passa a dizer "quanto o projeto esta desenvolvido" lendo os
`docs/esteira/<slug>/briefing.md`. Um numero de progresso e exatamente o tipo
de dado que a Lei 2 proibe de mentir, e ha quatro jeitos de ele mentir:

  - contar como cumprido o que ninguem provou (`[x]` escrito a mao nao e prova);
  - mostrar 0% ou 100% quando nao ha documentacao nenhuma;
  - aceitar como "prova" um texto que, rodado, executaria qualquer coisa;
  - estourar o limite do relatorio e fazer o servidor descartar o projeto
    INTEIRO (banco.MAX_BYTES_POR_PROJETO), em silencio.

Cada caso abaixo foi sabotado de proposito (ver o relatorio da etapa).

    python test_documentos.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import documentos

AQUI = Path(__file__).resolve().parent

VALIDO = """# Briefing - exemplo

Aprovado em: 2026-09-30

## pedido_original

texto livre, sem criterio nenhum aqui.

## criterio_de_aceitacao

- [ ] O formato esta escrito em um so lugar
Prova: python test_documentos.py
- [x] O leitor recusa comando hostil
- [ ] A tela mostra a barra

## fora_de_escopo

- [ ] isto esta fora da secao e nao conta
"""


def doc(criterios, slug="exemplo", aprovado_em="2026-09-30", erros=None,
        cortado=False):
    """Um documento no formato que o agente sobe. `criterios`: (texto, marcado, prova)."""
    return {
        "slug": slug, "arquivo": "docs/esteira/%s/briefing.md" % slug,
        "aprovado_em": aprovado_em, "erros": list(erros or []),
        "cortado": cortado,
        "criterios": [{"n": i + 1, "texto": t, "marcado": m, "prova": p}
                      for i, (t, m, p) in enumerate(criterios)],
    }


def documentacao(*docs):
    return {"versao": 1, "documentos": list(docs)}


def id_de(projeto, d, i):
    c = d["criterios"][i]
    return documentos.id_do_criterio(projeto, d["slug"], c["n"], c["texto"])


class OParserLeOFormato(unittest.TestCase):
    def test_exemplo_valido(self):
        d = documentos.ler_briefing(VALIDO, "exemplo")
        self.assertEqual(d["slug"], "exemplo")
        self.assertEqual(d["arquivo"], "docs/esteira/exemplo/briefing.md")
        self.assertEqual(d["aprovado_em"], "2026-09-30")
        self.assertEqual(d["erros"], [])
        self.assertIs(d["cortado"], False)
        self.assertEqual(
            [(c["n"], c["marcado"], c["prova"]) for c in d["criterios"]],
            [(1, False, "python test_documentos.py"),
             (2, True, ""),
             (3, False, "")])
        self.assertEqual(d["criterios"][1]["texto"],
                         "O leitor recusa comando hostil")

    def test_so_conta_dentro_da_secao(self):
        d = documentos.ler_briefing(VALIDO, "exemplo")
        textos = " ".join(c["texto"] for c in d["criterios"])
        self.assertNotIn("fora da secao", textos)
        self.assertEqual(len(d["criterios"]), 3)

    def test_fim_de_linha_do_windows(self):
        d = documentos.ler_briefing(VALIDO.replace("\n", "\r\n"), "exemplo")
        self.assertEqual(len(d["criterios"]), 3)
        self.assertEqual(d["aprovado_em"], "2026-09-30")
        self.assertEqual(d["criterios"][0]["prova"], "python test_documentos.py")
        self.assertEqual(d["erros"], [])

    def test_x_maiusculo_tambem_marca(self):
        d = documentos.ler_briefing(
            "## criterio_de_aceitacao\n- [X] feito\n", "a")
        self.assertIs(d["criterios"][0]["marcado"], True)

    def test_sem_secao_nao_e_erro_e_nao_tem_criterio(self):
        # Briefing antigo: aparece "sem documentacao", nao "quebrado".
        d = documentos.ler_briefing("# Briefing\n\n## pedido_original\n\nx\n", "a")
        self.assertEqual(d["criterios"], [])
        self.assertEqual(d["erros"], [])

    def test_criterio_numerado_e_erro_e_nao_conta(self):
        d = documentos.ler_briefing(
            "## criterio_de_aceitacao\n\n1. um criterio numerado\n"
            "- [ ] este conta\n", "a")
        self.assertEqual(len(d["criterios"]), 1)
        self.assertEqual(d["erros"],
                         ["critério numerado não conta: use - [ ]"])

    def test_prova_solta_e_erro(self):
        d = documentos.ler_briefing(
            "## criterio_de_aceitacao\n\nProva: python test_a.py\n"
            "- [ ] critério\n\nProva: python test_b.py\n", "a")
        self.assertEqual(len(d["criterios"]), 1)
        self.assertEqual(d["criterios"][0]["prova"], "",
                         "a prova so vale LOGO ABAIXO do criterio")
        self.assertEqual(len(d["erros"]), 2)
        for e in d["erros"]:
            self.assertIn("prova solta", e)

    def test_segunda_prova_seguida_e_solta(self):
        d = documentos.ler_briefing(
            "## criterio_de_aceitacao\n- [ ] c\nProva: npm test\n"
            "Prova: python test_a.py\n", "a")
        self.assertEqual(d["criterios"][0]["prova"], "npm test")
        self.assertEqual(len(d["erros"]), 1)

    def test_linha_de_criterio_mal_formada_e_erro(self):
        # Sem isto, `-[ ] x` some em silencio e o total fica menor que o real.
        d = documentos.ler_briefing(
            "## criterio_de_aceitacao\n-[ ] sem espaco\n- [ ]sem texto\n"
            "- [ ] ok\n", "a")
        self.assertEqual(len(d["criterios"]), 1)
        self.assertEqual(len(d["erros"]), 2)

    def test_aprovacao_so_fora_da_secao(self):
        d = documentos.ler_briefing(
            "## criterio_de_aceitacao\nAprovado em: 2026-01-01\n- [ ] c\n", "a")
        self.assertEqual(d["aprovado_em"], "")

    def test_aprovacao_ausente_ou_invalida(self):
        sem = documentos.ler_briefing("## criterio_de_aceitacao\n- [ ] c\n", "a")
        self.assertEqual(sem["aprovado_em"], "")
        ruim = documentos.ler_briefing(
            "Aprovado em: 2026-13-45\n## criterio_de_aceitacao\n- [ ] c\n", "a")
        self.assertEqual(ruim["aprovado_em"], "")
        self.assertEqual(len(ruim["erros"]), 1)

    def test_teto_de_criterios_corta_e_marca(self):
        texto = "## criterio_de_aceitacao\n" + "".join(
            "- [ ] c%d\n" % i for i in range(documentos.MAX_CRITERIOS + 5))
        d = documentos.ler_briefing(texto, "a")
        self.assertEqual(len(d["criterios"]), documentos.MAX_CRITERIOS)
        self.assertIs(d["cortado"], True)

    def test_teto_de_texto_corta_e_marca(self):
        d = documentos.ler_briefing(
            "## criterio_de_aceitacao\n- [ ] " + "x" * 400 + "\n", "a")
        self.assertEqual(len(d["criterios"][0]["texto"]), documentos.MAX_TEXTO)
        self.assertIs(d["cortado"], True)

    def test_prova_longa_demais_nao_vira_outra_prova(self):
        # Cortar uma prova poderia fabricar OUTRO comando valido. Descarta.
        longa = "python test_" + "a" * 300 + ".py"
        d = documentos.ler_briefing(
            "## criterio_de_aceitacao\n- [ ] c\nProva: %s\n" % longa, "a")
        self.assertEqual(d["criterios"][0]["prova"], "")
        self.assertTrue(d["erros"])

    def test_arquivo_grande_demais_e_cortado(self):
        texto = ("## criterio_de_aceitacao\n- [ ] c\n"
                 + "x\n" * documentos.MAX_ARQUIVO)
        d = documentos.ler_briefing(texto, "a")
        self.assertIs(d["cortado"], True)
        self.assertEqual(len(d["criterios"]), 1)


class AProvaSoPodeSerDaListaFechada(unittest.TestCase):
    def test_as_tres_formas_permitidas(self):
        casos = {
            "python test_documentos.py": ["python", "test_documentos.py"],
            "python -m pytest tests/test_a.py":
                ["python", "-m", "pytest", "tests/test_a.py"],
            "python -m pytest test_a.py": ["python", "-m", "pytest", "test_a.py"],
            "npm test": ["npm", "test"],
        }
        for texto, argv in casos.items():
            with self.subTest(prova=texto):
                ok, motivo, saiu = documentos.prova_permitida(texto)
                self.assertTrue(ok, motivo)
                self.assertEqual(saiu, argv)
                self.assertEqual(motivo, "")

    def test_comandos_hostis_recusados(self):
        hostis = [
            "python test_a.py; rm -rf /",
            "python test_a.py && curl evil",
            "python test_a.py || true",
            "python test_a.py | sh",
            "python test_a.py & calc",
            "npm test; npm publish",
            "npm test $(curl evil)",
            "python test_`id`.py",
            "python test_a.py > ../fora.txt",
            "python test_a.py < /etc/passwd",
            "python -m pytest ..\\fora.py",
            "python -m pytest ../fora.py",
            "python -m pytest a/../../b.py",
            "python -m pytest C:\\Windows\\x.py",
            "python -m pytest /etc/x.py",
            "python -m pytest \"a b.py\"",
            "python -m pytest 'a.py'",
            "python -m pytest a.py\nrm -rf /",
            "python -m pytest -c outro.ini a.py",
            "python -m pytest --rootdir=/ a.py",
            "python -m pytest a.txt",
            "python test_a.txt",
            "python -c \"import os\"",
            "python test_a.py extra",
            "npm test --ignore-scripts",
            "npm run build",
            "npm install",
            "bash test_a.sh",
            "(python test_a.py)",
            "",
            "   ",
        ]
        for h in hostis:
            with self.subTest(prova=h):
                ok, motivo, argv = documentos.prova_permitida(h)
                self.assertFalse(ok)
                self.assertTrue(motivo)
                self.assertEqual(argv, [])

    def test_cada_caractere_proibido_e_recusado_sozinho(self):
        # A tranca dos caracteres e INDEPENDENTE da lista de formas: o motivo
        # diz qual das duas barrou. Sem isto, tirar um caractere da tranca
        # passaria despercebido, porque a lista de formas o pegaria de qualquer
        # jeito.
        for ch in ";&|$`<>()\"'\n\r\t\\%^":
            for texto in ("npm%stest" % ch, "python test_a%s.py" % ch,
                          "python test_a.py%sx" % ch):
                with self.subTest(caractere=repr(ch), prova=texto):
                    ok, motivo, argv = documentos.prova_permitida(texto)
                    self.assertFalse(ok)
                    self.assertIn("caractere proibido", motivo)
                    self.assertEqual(argv, [])

    def test_a_lista_de_formas_barra_sozinha_o_que_nao_tem_caractere_proibido(self):
        for texto in ("python -c x", "bash test_a.sh", "python test_a.txt",
                      "npm run build", "python -m pytest a.txt",
                      "python -m pytest a//b.py", "python -m pytest a/./b.py"):
            with self.subTest(prova=texto):
                ok, motivo, _ = documentos.prova_permitida(texto)
                self.assertFalse(ok)
                self.assertNotIn("caractere proibido", motivo)

    def test_nao_e_texto_nao_e_prova(self):
        for lixo in (None, 7, ["npm test"], b"npm test"):
            with self.subTest(lixo=lixo):
                self.assertFalse(documentos.prova_permitida(lixo)[0])


class OIdDoCriterioEEstavel(unittest.TestCase):
    def test_formato_e_estabilidade(self):
        a = documentos.id_do_criterio("p", "s", 1, "texto")
        self.assertRegex(a, r"^c[0-9a-f]{20}$")
        self.assertEqual(a, documentos.id_do_criterio("p", "s", 1, "texto"))

    def test_cada_campo_muda_o_id(self):
        base = documentos.id_do_criterio("p", "s", 1, "texto")
        for outro in (documentos.id_do_criterio("q", "s", 1, "texto"),
                      documentos.id_do_criterio("p", "t", 1, "texto"),
                      documentos.id_do_criterio("p", "s", 2, "texto"),
                      documentos.id_do_criterio("p", "s", 1, "outro")):
            self.assertNotEqual(base, outro)

    def test_separador_nao_deixa_dois_campos_colidirem(self):
        self.assertNotEqual(documentos.id_do_criterio("a", "bc", 1, "t"),
                            documentos.id_do_criterio("ab", "c", 1, "t"))


class OCriterioSensivelFicaDeFora(unittest.TestCase):
    def test_palavras_da_lista(self):
        for palavra in ("senha", "token", "segredo", "chave", "pagamento",
                        "paciente", "prontuario", "autentica", "login",
                        "migration", "deploy", "producao"):
            with self.subTest(palavra=palavra):
                self.assertTrue(documentos.criterio_sensivel(
                    "Trocar a %s do sistema" % palavra))

    def test_acento_e_caixa_nao_escapam(self):
        self.assertTrue(documentos.criterio_sensivel("Publicar em PRODUÇÃO"))
        self.assertTrue(documentos.criterio_sensivel("Nova autenticação"))
        self.assertTrue(documentos.criterio_sensivel("Dados do Prontuário"))

    def test_texto_comum_passa(self):
        self.assertFalse(documentos.criterio_sensivel("A tela mostra a barra"))


class AContaDoProgresso(unittest.TestCase):
    P = "dervs"

    def conta(self, *docs, provas=None, medido_em="2026-09-30T10:00:00+00:00"):
        return documentos.progresso(documentacao(*docs), self.P, medido_em,
                                    provas=provas)

    def test_os_quatro_estados(self):
        d = doc([("a", False, ""), ("b", True, "")])
        self.assertEqual(documentos.progresso(None, self.P, None)["estado"],
                         "sem_dados")
        self.assertEqual(self.conta()["estado"], "sem_documentacao")
        self.assertEqual(self.conta(d)["estado"], "nao_verificado")
        ids = {id_de(self.P, d, 0): True}
        self.assertEqual(self.conta(d, provas=ids)["estado"], "medido")

    def test_campos_do_contrato(self):
        r = self.conta(doc([("a", False, "")]))
        self.assertEqual(set(r), {
            "estado", "percentual", "total", "comprovados", "falhos",
            "nao_verificados", "faltam", "declarados", "medido_em",
            "documentos_n", "erros_n"})

    def test_nao_verificado_nunca_entra_no_percentual(self):
        # Quatro marcados [x] a mao, sem prova rodada: a conta NAO pode ler isto
        # como "100% feito". Sabotagem: somar `declarados` em `comprovados`.
        d = doc([("a", True, ""), ("b", True, ""), ("c", True, ""),
                 ("d", True, "python test_a.py")])
        r = self.conta(d)
        self.assertEqual(r["estado"], "nao_verificado")
        self.assertIsNone(r["percentual"])
        self.assertEqual(r["comprovados"], 0)
        self.assertEqual(r["declarados"], 4)
        self.assertEqual(r["total"], 4)

    def test_declarado_ao_lado_de_comprovado_nao_infla_a_conta(self):
        d = doc([("a", True, ""), ("b", False, "python test_a.py"),
                 ("c", False, ""), ("d", True, "")])
        r = self.conta(d, provas={id_de(self.P, d, 1): True})
        self.assertEqual(r["estado"], "medido")
        self.assertEqual(r["comprovados"], 1)
        self.assertEqual(r["declarados"], 2)
        self.assertEqual(r["percentual"], 25)

    def test_sem_documentacao_nunca_e_zero_nem_cem(self):
        r = self.conta()
        self.assertEqual(r["estado"], "sem_documentacao")
        self.assertIsNone(r["percentual"])
        self.assertEqual((r["total"], r["comprovados"]), (0, 0))
        # documento que existe mas nao tem critero algum tambem e "sem documentacao"
        r2 = self.conta(doc([], erros=["critério numerado não conta: use - [ ]"]))
        self.assertEqual(r2["estado"], "sem_documentacao")
        self.assertIsNone(r2["percentual"])
        self.assertEqual(r2["erros_n"], 1)
        self.assertEqual(r2["documentos_n"], 1)

    def test_sem_dados_nao_inventa_numero(self):
        r = documentos.progresso(None, self.P, "2026-09-30T10:00:00+00:00")
        self.assertIsNone(r["percentual"])
        self.assertIsNone(r["medido_em"])
        self.assertEqual((r["total"], r["documentos_n"], r["erros_n"]),
                         (0, 0, 0))

    def test_cem_so_quando_todos_comprovados(self):
        d = doc([("a", False, ""), ("b", False, "")])
        a, b = id_de(self.P, d, 0), id_de(self.P, d, 1)
        self.assertEqual(self.conta(d, provas={a: True})["percentual"], 50)
        self.assertEqual(self.conta(d, provas={a: True, b: True})["percentual"],
                         100)
        d3 = doc([("a", False, ""), ("b", False, ""), ("c", False, "")])
        ids = {id_de(self.P, d3, i): True for i in (0, 1)}
        self.assertEqual(self.conta(d3, provas=ids)["percentual"], 66,
                         "66,6% nao pode arredondar para 67 nem para 100")
        ids[id_de(self.P, d3, 2)] = True
        self.assertEqual(self.conta(d3, provas=ids)["percentual"], 100)

    def test_prova_que_falhou_conta_como_falho_e_nao_como_feito(self):
        d = doc([("a", True, "python test_a.py"), ("b", False, "")])
        r = self.conta(d, provas={id_de(self.P, d, 0): False})
        self.assertEqual(r["estado"], "medido")
        self.assertEqual((r["comprovados"], r["falhos"]), (0, 1))
        self.assertEqual(r["percentual"], 0)

    def test_as_parcelas_fecham_no_total(self):
        d = doc([("a", True, ""), ("b", False, ""), ("c", False, "npm test"),
                 ("d", False, ""), ("e", True, "")])
        ids = {id_de(self.P, d, 3): True, id_de(self.P, d, 4): False}
        r = self.conta(d, provas=ids)
        self.assertEqual(r["total"], 5)
        self.assertEqual(r["comprovados"] + r["falhos"] + r["nao_verificados"]
                         + r["faltam"], r["total"])
        self.assertLessEqual(r["declarados"], r["nao_verificados"])

    def test_resultado_que_nao_e_booleano_nao_conta(self):
        d = doc([("a", False, "")])
        for lixo in ("passou", 1, "true", None):
            with self.subTest(lixo=lixo):
                r = self.conta(d, provas={id_de(self.P, d, 0): lixo})
                self.assertEqual(r["comprovados"], 0)
                self.assertEqual(r["estado"], "nao_verificado")

    def test_percentual_do_agente_e_ignorado(self):
        d = doc([("a", False, "")])
        d["percentual"] = 100
        bruto = documentacao(d)
        bruto["percentual"] = 100
        r = documentos.progresso(bruto, self.P, None)
        self.assertIsNone(r["percentual"])
        self.assertEqual(r["comprovados"], 0)

    def test_documentacao_malformada_nao_levanta(self):
        for lixo in ("texto", 7, [], {"documentos": "x"}, {"documentos": None},
                     {"documentos": [1, None, "x"]},
                     {"documentos": [{"slug": 7}]},
                     {"documentos": [{"slug": "a", "criterios": "x"}]},
                     {"documentos": [{"slug": "a", "criterios": [
                         {"n": "1", "texto": 5, "marcado": "sim"}]}]}):
            with self.subTest(lixo=lixo):
                r = documentos.progresso(lixo, self.P, None)
                self.assertIn(r["estado"], ("sem_dados", "sem_documentacao"))
                self.assertIsNone(r["percentual"])

    def test_servidor_reaplica_o_teto_de_criterios(self):
        d = doc([("c%d" % i, False, "") for i in range(documentos.MAX_CRITERIOS + 9)])
        self.assertEqual(self.conta(d)["total"], documentos.MAX_CRITERIOS)

    def test_erros_e_documentos_sao_contados(self):
        a = doc([("a", False, "")], slug="a", erros=["x", "y"])
        b = doc([("b", False, "")], slug="b")
        r = self.conta(a, b)
        self.assertEqual((r["documentos_n"], r["erros_n"]), (2, 2))


class ODetalheDeCadaCriterio(unittest.TestCase):
    P = "dervs"

    def detalhe(self, d, bloqueio="", provas=None):
        return documentos.detalhar(documentacao(d), self.P, provas=provas,
                                   bloqueio=bloqueio)[0]["criterios"]

    def test_campos_do_contrato(self):
        d = doc([("a", False, "npm test")])
        r = documentos.detalhar(documentacao(d), self.P)
        self.assertEqual(set(r[0]), {"slug", "arquivo", "aprovado_em", "erros",
                                     "criterios"})
        self.assertEqual(set(r[0]["criterios"][0]), {
            "id", "n", "texto", "marcado", "prova", "prova_aceita",
            "situacao", "desenvolvivel", "motivo"})

    def test_situacao_de_cada_um(self):
        d = doc([("feito a mao", True, ""), ("a fazer", False, ""),
                 ("com prova", False, "npm test"), ("passou", False, ""),
                 ("falhou", False, "")])
        ids = {id_de(self.P, d, 3): True, id_de(self.P, d, 4): False}
        r = self.detalhe(d, provas=ids)
        self.assertEqual([c["situacao"] for c in r], [
            "nao_verificado", "falta", "nao_verificado", "comprovado",
            "prova_falhou"])
        self.assertEqual([c["prova_aceita"] for c in r],
                         [False, False, True, False, False])

    def test_so_o_critico_aprovado_nao_marcado_e_desenvolvivel(self):
        d = doc([("a fazer", False, ""), ("ja marcado", True, "")])
        r = self.detalhe(d)
        self.assertEqual((r[0]["desenvolvivel"], r[0]["motivo"]), (True, ""))
        self.assertEqual((r[1]["desenvolvivel"], r[1]["motivo"]),
                         (False, "criterio ja marcado"))

    def test_documento_sem_aprovacao_nao_desenvolve(self):
        r = self.detalhe(doc([("a", False, "")], aprovado_em=""))
        self.assertEqual(r[0]["motivo"], "documento nao aprovado")
        self.assertIs(r[0]["desenvolvivel"], False)

    def test_projeto_bloqueado_e_sensivel(self):
        r = self.detalhe(doc([("a", False, "")]), bloqueio="projeto bloqueado")
        self.assertEqual(r[0]["motivo"], "projeto bloqueado")
        r = self.detalhe(doc([("trocar a senha", False, "")]))
        self.assertEqual(r[0]["motivo"], "criterio sensivel")

    def test_a_ordem_das_recusas_e_a_do_contrato(self):
        c = documentos.recusa_de_desenvolvimento
        self.assertEqual(c("", True, "senha", "projeto bloqueado"),
                         "documento nao aprovado")
        self.assertEqual(c("2026-09-30", True, "senha", "projeto bloqueado"),
                         "projeto bloqueado")
        self.assertEqual(c("2026-09-30", True, "senha", ""), "criterio sensivel")
        self.assertEqual(c("2026-09-30", True, "a tela", ""),
                         "criterio ja marcado")
        self.assertEqual(c("2026-09-30", False, "a tela", ""), "")

    def test_criterio_comprovado_nao_se_desenvolve(self):
        d = doc([("a", False, "")])
        r = self.detalhe(d, provas={id_de(self.P, d, 0): True})
        self.assertIs(r[0]["desenvolvivel"], False)

    def test_os_ids_batem_com_id_do_criterio(self):
        d = doc([("a", False, ""), ("b", False, "")])
        r = self.detalhe(d)
        self.assertEqual([c["id"] for c in r],
                         [id_de(self.P, d, 0), id_de(self.P, d, 1)])


class OLeitorDoProjeto(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.raiz = Path(self.tmp.name)

    def escrever(self, slug, texto):
        pasta = self.raiz / "docs" / "esteira" / slug
        pasta.mkdir(parents=True, exist_ok=True)
        (pasta / "briefing.md").write_bytes(texto.encode("utf-8"))

    def test_sem_pasta_e_documentacao_vazia_e_nao_erro(self):
        self.assertEqual(documentos.ler_projeto(self.raiz),
                         {"versao": 1, "documentos": []})

    def test_le_os_documentos_em_ordem_de_slug(self):
        self.escrever("b-segundo", VALIDO)
        self.escrever("a-primeiro", VALIDO)
        r = documentos.ler_projeto(self.raiz)
        self.assertEqual([d["slug"] for d in r["documentos"]],
                         ["a-primeiro", "b-segundo"])
        self.assertEqual(len(r["documentos"][0]["criterios"]), 3)

    def test_briefing_antigo_sem_criterio_nao_entra(self):
        self.escrever("antigo", "# Briefing\n\n## pedido_original\n\nx\n")
        self.assertEqual(documentos.ler_projeto(self.raiz)["documentos"], [])

    def test_briefing_quebrado_entra_para_o_erro_aparecer(self):
        self.escrever("quebrado",
                      "## criterio_de_aceitacao\n1. numerado\n")
        docs = documentos.ler_projeto(self.raiz)["documentos"]
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0]["criterios"], [])
        self.assertTrue(docs[0]["erros"])

    def test_slug_fora_do_padrao_e_ignorado(self):
        self.escrever("Maiuscula", VALIDO)
        self.escrever("com espaco", VALIDO)
        self.escrever("ok", VALIDO)
        self.assertEqual([d["slug"] for d in
                          documentos.ler_projeto(self.raiz)["documentos"]],
                         ["ok"])

    def test_arquivo_ilegivel_nao_derruba_o_resto(self):
        self.escrever("bom", VALIDO)
        (self.raiz / "docs" / "esteira" / "ruim").mkdir()
        (self.raiz / "docs" / "esteira" / "ruim" / "briefing.md").mkdir()
        docs = documentos.ler_projeto(self.raiz)["documentos"]
        self.assertEqual([d["slug"] for d in docs], ["bom"])

    def test_teto_de_documentos(self):
        for i in range(documentos.MAX_DOCUMENTOS + 4):
            self.escrever("d%03d" % i, "## criterio_de_aceitacao\n- [ ] c\n")
        r = documentos.ler_projeto(self.raiz)
        self.assertEqual(len(r["documentos"]), documentos.MAX_DOCUMENTOS)
        self.assertTrue(any(d["erros"] or d["cortado"] for d in r["documentos"]),
                        "cortou documentos sem dizer")

    def test_tamanho_cabe_no_relatorio(self):
        """50 documentos x 100 criterios estourariam os 64 KiB por projeto e o
        servidor descartaria o projeto INTEIRO. O teto e o do JSON da chave."""
        linha = "- [ ] " + "critério longo demais para caber " * 8 + "\n"
        corpo = "## criterio_de_aceitacao\n" + linha * 100
        for i in range(50):
            self.escrever("doc-%02d" % i, corpo)
        r = documentos.ler_projeto(self.raiz)
        tamanho = len(json.dumps(r, ensure_ascii=False).encode("utf-8"))
        self.assertLessEqual(tamanho, documentos.MAX_JSON)
        self.assertLessEqual(documentos.MAX_JSON, 32 * 1024)
        self.assertTrue(r["documentos"], "cortou tudo, nao sobrou nada")
        self.assertTrue(any(d["cortado"] for d in r["documentos"]))
        # e o que sobrou e lido pelo servidor sem reclamar
        self.assertEqual(documentos.progresso(r, "p", None)["estado"],
                         "nao_verificado")


class OLeitorParaDeAbrirArquivoAoChegarNoTeto(unittest.TestCase):
    """Achado de revisao: o leitor abria TODOS os briefings e so depois cortava
    em 30. Um repositorio com 5.000 pastas de slug valido faria o agente ler
    5.000 arquivos por coleta."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.raiz = Path(self.tmp.name)

    def pastas(self, n, texto):
        base = self.raiz / "docs" / "esteira"
        for i in range(n):
            pasta = base / ("p%04d" % i)
            pasta.mkdir(parents=True)
            (pasta / "briefing.md").write_bytes(texto.encode("utf-8"))

    def contar_aberturas(self):
        abertos = []
        original = Path.open

        def espia(self, *a, **k):
            if self.name == "briefing.md":
                abertos.append(self)
            return original(self, *a, **k)

        Path.open = espia
        try:
            r = documentos.ler_projeto(self.raiz)
        finally:
            Path.open = original
        return r, len(abertos)

    def test_500_pastas_com_criterio_abrem_no_maximo_31(self):
        self.pastas(500, "## criterio_de_aceitacao\n- [ ] c\n")
        r, abertos = self.contar_aberturas()
        self.assertLessEqual(abertos, documentos.MAX_DOCUMENTOS + 1)
        self.assertEqual(len(r["documentos"]), documentos.MAX_DOCUMENTOS)
        self.assertTrue(r["documentos"][-1]["cortado"])

    def test_500_pastas_sem_criterio_tambem_tem_teto_de_abertura(self):
        """Briefing antigo nao entra na lista, mas abrir custa igual."""
        self.pastas(500, "# Briefing antigo\n\nsem secao nenhuma\n")
        r, abertos = self.contar_aberturas()
        self.assertLessEqual(abertos, documentos.MAX_VARRIDOS)
        # O corte NAO pode ser mudo (Lei 2): sem erro visivel o painel diria
        # "sem documentacao" para um projeto que so tem briefing demais.
        self.assertEqual(len(r["documentos"]), 1)
        self.assertTrue(any("limite" in e for e in r["documentos"][0]["erros"]))

    def test_diretorio_gigante_nao_e_listado_inteiro(self):
        """`sorted(iterdir())` lia a pasta toda antes de qualquer teto."""
        self.pastas(documentos.MAX_PASTAS + 50, "# antigo\n")
        r, abertos = self.contar_aberturas()
        self.assertLessEqual(abertos, documentos.MAX_VARRIDOS)
        self.assertTrue(any("limite" in e
                            for d in r["documentos"] for e in d["erros"]))


class OLeitorNaoSaiDoRepositorio(unittest.TestCase):
    """`docs` ou `docs/esteira` como link simbolico (ou junction no Windows)
    levariam o leitor a um diretorio de FORA, e o conteudo de la entraria no
    relatorio."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.raiz = base / "repo"
        self.fora = base / "fora"
        (self.fora / "x").mkdir(parents=True)
        (self.fora / "x" / "briefing.md").write_bytes(VALIDO.encode("utf-8"))
        self.raiz.mkdir()

    def recusou(self, r):
        self.assertEqual([c for d in r["documentos"] for c in d["criterios"]],
                         [], "leu briefing de fora do repositorio")
        self.assertEqual(len(r["documentos"]), 1)
        self.assertTrue(r["documentos"][0]["erros"], "recusou calado")

    def test_esteira_como_link_para_fora_e_recusada_com_erro(self):
        (self.raiz / "docs").mkdir()
        try:
            (self.raiz / "docs" / "esteira").symlink_to(
                self.fora, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("sem privilegio para criar link simbolico")
        self.recusou(documentos.ler_projeto(self.raiz))

    def test_docs_como_link_para_fora_e_recusada_com_erro(self):
        (self.fora / "esteira").mkdir()
        (self.fora / "esteira" / "x").mkdir()
        (self.fora / "esteira" / "x" / "briefing.md").write_bytes(
            VALIDO.encode("utf-8"))
        try:
            (self.raiz / "docs").symlink_to(self.fora,
                                            target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("sem privilegio para criar link simbolico")
        self.recusou(documentos.ler_projeto(self.raiz))

    def test_resolve_que_aponta_para_fora_e_recusado(self):
        """Nao depende de privilegio: o `resolve()` e que e simulado (e o que
        uma junction do Windows, ou um `..`, faria)."""
        (self.raiz / "docs" / "esteira" / "x").mkdir(parents=True)
        (self.raiz / "docs" / "esteira" / "x" / "briefing.md").write_bytes(
            VALIDO.encode("utf-8"))
        original = Path.resolve
        fora = self.fora

        def resolve_mentiroso(self, *a, **k):
            if self.name == "esteira":
                return original(fora, *a, **k)
            return original(self, *a, **k)

        Path.resolve = resolve_mentiroso
        try:
            r = documentos.ler_projeto(self.raiz)
        finally:
            Path.resolve = original
        self.recusou(r)

    def test_repositorio_normal_segue_lendo(self):
        (self.raiz / "docs" / "esteira" / "x").mkdir(parents=True)
        (self.raiz / "docs" / "esteira" / "x" / "briefing.md").write_bytes(
            VALIDO.encode("utf-8"))
        r = documentos.ler_projeto(self.raiz)
        self.assertEqual(len(r["documentos"][0]["criterios"]), 3)
        self.assertEqual(r["documentos"][0]["erros"], [])


class OModuloNaoImportaOQueNaoPode(unittest.TestCase):
    def test_importa_sem_banco_execucao_fila(self):
        """Em processo novo: `servir.py` e `coletar.py` importam este modulo, e
        a imagem so leva o que `servir.py` alcanca (`test_imagem.PROIBIDOS`)."""
        codigo = ("import sys, documentos;"
                  "ruins = {'banco','execucao','fila','barreira','tarefas',"
                  "'servir','coletar','subprocess'} & set(sys.modules);"
                  "print(sorted(ruins)); sys.exit(1 if ruins else 0)")
        r = subprocess.run([sys.executable, "-c", codigo], cwd=str(AQUI),
                           capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_nao_tem_eval_nem_subprocess_no_codigo(self):
        fonte = (AQUI / "documentos.py").read_text(encoding="utf-8")
        for proibido in ("subprocess", "eval(", "exec(", "os.system", "Popen"):
            self.assertNotIn(proibido, fonte)


if __name__ == "__main__":
    unittest.main(verbosity=2)
