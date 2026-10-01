# -*- coding: utf-8 -*-
"""O FIO INTEIRO do progresso: do arquivo no disco ate o campo que a tela le.

MOTIVO: as 26 suites ja ficaram verdes com a Auditoria inteira morta, e o
`progresso` tem o mesmo desenho (agente le o disco, servidor conta, tela
desenha). Cada metade foi provada contra duble: `test_documentos` (o leitor),
`test_desenvolver` (o servidor, com a documentacao montada a mao) e
`test_progresso_tela` (a tela, com a resposta montada a mao). Ninguem provava
que o que o servidor ENTREGA e o que a tela LE sao a mesma coisa. Se um lado
renomeia um campo, os tres continuam verdes e a tela mostra "undefined" — ou
pior, cai na face "sem dados" e esconde o numero.

Aqui nada e montado a mao do lado do servidor: o briefing e escrito numa pasta
temporaria, `documentos.ler_projeto` produz a chave `documentacao`, ela sobe
pelo `POST /agente/relatorio` de uma maquina pareada, e o que volta de
`GET /api/dados` e `GET /api/progresso` e comparado com os campos que
`assets/painel.js` le (extraidos do proprio arquivo por regex).

    python test_progresso_fio.py
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("DERVS_AMBIENTE", "local")
os.environ.setdefault("DERVS_COFRE",
                      "chave-de-teste-que-nao-e-segredo-nenhum-0123456789")

import banco         # noqa: E402
import documentos    # noqa: E402
from agente import enviar, executor  # noqa: E402
from test_servir import BaseServidorDeVerdade  # noqa: E402

AQUI = Path(__file__).resolve().parent
JS = (AQUI / "assets" / "painel.js").read_text(encoding="utf-8")

BRIEFING = """# Briefing - exemplo do fio

Aprovado em: 2026-09-30

## criterio_de_aceitacao

- [ ] A tela mostra a barra de progresso
Prova: python test_progresso_tela.py
- [x] O leitor recusa comando hostil
Prova: python test_documentos.py; rm -rf /
- [ ] A conta nasce no servidor
1. item numerado nao conta

## fora_de_escopo

- [ ] isto esta fora da secao
"""


def funcao(nome: str) -> str:
    m = re.search(r"(?:async )?function %s\(.*?\n}\n" % re.escape(nome), JS, re.S)
    assert m, "funcao %s nao encontrada em painel.js" % nome
    return m.group(0)


def sem_comentarios(js: str) -> str:
    js = re.sub(r"/\*.*?\*/", "", js, flags=re.S)
    return re.sub(r"(?m)//[^\n]*$", "", js)


def campos(variavel: str, *nomes_de_funcao: str) -> set:
    """Os `variavel.campo` que essas funcoes do painel.js leem."""
    achados = set()
    for nome in nomes_de_funcao:
        achados |= set(re.findall(r"\b%s\.([A-Za-z_]\w*)" % variavel,
                                  sem_comentarios(funcao(nome))))
    return achados


# Metodos/propriedades de DOM que nao sao campo do servidor.
DOM = {"textContent", "className", "dataset", "append", "hidden", "disabled",
       "value", "max", "length", "type", "title"}


class OQueATelaLeOServidorEntrega(BaseServidorDeVerdade):
    PROJETO = "fio-proj"

    def setUp(self):
        super().setUp()
        self.addCleanup(self.limpar)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        pasta = Path(self.tmp.name) / "docs" / "esteira" / "exemplo"
        pasta.mkdir(parents=True)
        (pasta / "briefing.md").write_bytes(BRIEFING.encode("utf-8"))
        # O AGENTE: le o disco de verdade. Nada de dicionario escrito aqui.
        self.documentacao = documentos.ler_projeto(self.tmp.name)
        self.assertEqual(len(self.documentacao["documentos"]), 1)
        self.enviar_relatorio()

    def limpar(self):
        con = banco.conectar()
        try:
            con.execute("DELETE FROM maquina")
            con.execute("DELETE FROM medida")
            con.execute("DELETE FROM historico")
            con.commit()
        finally:
            con.close()

    def enviar_relatorio(self):
        token, _ = self.maquina_com_token()
        r = self.como_agente(token, "/agente/relatorio", {"projetos": [
            {"nome": self.PROJETO, "documentacao": self.documentacao}]})
        self.assertEqual(r.status, 200, r.corpo)

    def get(self, caminho):
        r = self.pedir(caminho, cookies=self.sessao_e_token()[0])
        self.assertEqual(r.status, 200, r.corpo)
        return json.loads(r.corpo)

    def projeto_dos_dados(self):
        return next(p for p in self.get("/api/dados")["projetos"]
                    if p["nome"] == self.PROJETO)

    # ------------------------------------------------------------ o fio
    def test_o_relatorio_real_vira_progresso_nos_dois_endpoints(self):
        p = self.projeto_dos_dados()
        self.assertNotIn("documentacao", p)
        pr = p["progresso"]
        self.assertEqual(pr["estado"], "nao_verificado")
        self.assertIsNone(pr["percentual"])
        self.assertEqual((pr["total"], pr["declarados"], pr["comprovados"]),
                         (3, 1, 0))
        self.assertEqual(pr["erros_n"], 1)        # o item numerado
        corpo = self.get("/api/progresso?projeto=" + self.PROJETO)
        self.assertEqual(corpo["progresso"], pr)
        self.assertEqual(len(corpo["documentos"]), 1)
        self.assertEqual(len(corpo["documentos"][0]["criterios"]), 3)

    def test_todo_campo_de_progresso_que_a_tela_le_existe_na_resposta(self):
        lidos = campos("pr", "pintarProgresso")
        lidos |= set(re.findall(r'\btem\("(\w+)"\)',
                                sem_comentarios(funcao("pintarProgresso"))))
        lidos -= DOM
        # a extracao achou o que tinha de achar (senao o teste e vazio)
        self.assertTrue({"estado", "percentual", "medido_em", "comprovados",
                         "total", "declarados", "erros_n",
                         "documentos_n"} <= lidos, lidos)
        dados = self.projeto_dos_dados()["progresso"]
        corpo = self.get("/api/progresso?projeto=" + self.PROJETO)["progresso"]
        for nome in sorted(lidos):
            with self.subTest(campo=nome):
                self.assertIn(nome, dados, "/api/dados nao entrega pr.%s" % nome)
                self.assertIn(nome, corpo,
                              "/api/progresso nao entrega pr.%s" % nome)

    def test_todo_campo_de_criterio_que_a_tela_le_existe_na_resposta(self):
        lidos = campos("c", "linhaDeCriterio", "desenvolverCriterio") - DOM
        self.assertTrue({"id", "texto", "prova", "prova_aceita", "situacao",
                         "desenvolvivel", "motivo"} <= lidos, lidos)
        corpo = self.get("/api/progresso?projeto=" + self.PROJETO)
        for c in corpo["documentos"][0]["criterios"]:
            for nome in sorted(lidos):
                with self.subTest(criterio=c["n"], campo=nome):
                    self.assertIn(nome, c, "criterio sem c.%s" % nome)

    def test_todo_campo_de_documento_que_a_tela_le_existe_na_resposta(self):
        lidos = campos("d", "pintarCriterios") - DOM
        self.assertTrue({"slug", "aprovado_em", "erros", "criterios"} <= lidos,
                        lidos)
        corpo = self.get("/api/progresso?projeto=" + self.PROJETO)
        self.assertIn("documentos", sem_comentarios(funcao("carregarProgresso")))
        for nome in sorted(lidos):
            with self.subTest(campo=nome):
                self.assertIn(nome, corpo["documentos"][0])

    def test_o_projeto_que_a_tela_passa_a_pintarProgresso_tem_nome_e_progresso(self):
        lidos = campos("p", "pintarProgresso") - DOM
        self.assertTrue({"progresso", "nome"} <= lidos, lidos)
        p = self.projeto_dos_dados()
        for nome in sorted(lidos):
            with self.subTest(campo=nome):
                self.assertIn(nome, p)

    def test_a_prova_hostil_nao_e_aceita_e_a_boa_e(self):
        """O que o agente leu com `;` chega ao servidor e ali e recusado de
        novo: a lista fechada vale nas duas pontas."""
        corpo = self.get("/api/progresso?projeto=" + self.PROJETO)
        c = corpo["documentos"][0]["criterios"]
        self.assertIs(c[0]["prova_aceita"], True)
        self.assertIs(c[1]["prova_aceita"], False)
        self.assertEqual(c[1]["situacao"], "nao_verificado")


# ----------------------------------------------- a conta dos documentos REAIS
def _criterios_por_extenso(raiz: Path):
    """Conta `- [ ]`/`- [x]` dentro de `## criterio_de_aceitacao`, com regex
    ESCRITA AQUI e sem chamar nada de `documentos`: a conta independente."""
    total = marcados = 0
    for arq in sorted((raiz / "docs" / "esteira").glob("*/briefing.md")):
        texto = arq.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
        for bloco in re.split(r"(?m)^## ", texto)[1:]:
            if not bloco.startswith("criterio_de_aceitacao"):
                continue
            linhas = re.findall(r"(?m)^- \[([ xX])\] \S", bloco)
            total += len(linhas)
            marcados += sum(1 for m in linhas if m in "xX")
    return total, marcados


class UmaProvaDeVerdadeVirapercentual(BaseServidorDeVerdade):
    """Do clique ao percentual, SEM nenhum dicionario montado a mao.

    Cada etapa da fase 2 foi provada contra duble (o executor contra uma
    tarefa escrita a mao, o servidor contra um resultado escrito a mao). Com
    `provas` fora do desfecho do executor, ou ignorado por `_resultado`, as
    duas metades continuam verdes e o painel nunca sai de "nao verificado".
    Aqui o repositorio e git de verdade, o relatorio sai de `ler_projeto`, a
    tarefa e a que o SERVIDOR entrega e o desfecho e o do `ExecutorProva` real.
    """
    PROJETO = "fio-prova"
    BOM = ("import unittest\n\n\nclass T(unittest.TestCase):\n"
           "    def test_a(self):\n        self.assertTrue(True)\n\n\n"
           "if __name__ == '__main__':\n    unittest.main()\n")
    RUIM = BOM.replace("assertTrue(True)", "assertTrue(False)")
    ESPERA = 120

    def setUp(self):
        super().setUp()
        self.addCleanup(self.limpar)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name) / "repo"
        pasta = self.repo / "docs" / "esteira" / "x"
        pasta.mkdir(parents=True)
        (self.repo / "test_bom.py").write_text(self.BOM, encoding="utf-8")
        (self.repo / "test_ruim.py").write_text(self.RUIM, encoding="utf-8")
        (pasta / "briefing.md").write_text(
            "# Briefing - x\n\nAprovado em: 2026-09-30\n\n"
            "## criterio_de_aceitacao\n\n"
            "- [ ] O primeiro passa\nProva: python test_bom.py\n"
            "- [ ] O segundo falha\nProva: python test_ruim.py\n",
            encoding="utf-8")
        for args in (("init", "-q"), ("add", "-A"), ("commit", "-q", "-m", "x")):
            subprocess.run(["git", "-c", "user.name=x", "-c", "user.email=x@x",
                            *args], cwd=str(self.repo), check=True,
                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=60)

    def limpar(self):
        self.limpar_fila()
        con = banco.conectar()
        try:
            con.execute("DELETE FROM maquina")
            con.execute("DELETE FROM prova_rodada")
            con.execute("DELETE FROM medida")
            con.execute("DELETE FROM historico")
            con.commit()
        finally:
            con.close()

    def test_o_clique_vira_percentual_pelo_fio_inteiro(self):
        documentacao = documentos.ler_projeto(str(self.repo))
        self.assertEqual(len(documentacao["documentos"][0]["criterios"]), 2)
        token, mid = self.maquina_com_token()
        r = self.como_agente(token, "/agente/relatorio", {"projetos": [
            {"nome": self.PROJETO, "documentacao": documentacao}]})
        self.assertEqual(r.status, 200, r.corpo)

        cookies, csrf = self.sessao_e_token()
        r = self.pedir("/api/provar", "POST", {"projeto": self.PROJETO},
                       cookies=cookies, cabecalhos={"X-Token": csrf})
        self.assertEqual(r.status, 200, r.corpo)
        tarefa_id = json.loads(r.corpo)["tarefa"]
        r = self.pedir("/api/tarefas/aprovar", "POST", {"id": tarefa_id},
                       cookies=cookies, cabecalhos={"X-Token": csrf})
        self.assertEqual(r.status, 200, r.corpo)

        # A tarefa vem do SERVIDOR, como o agente a recebe.
        r = self.como_agente(token, "/agente/relatorio", {"projetos": [
            {"nome": self.PROJETO, "documentacao": documentacao}]})
        entregue = json.loads(r.corpo)["tarefa"]
        self.assertIsNotNone(entregue, "o servidor nao entregou a prova")

        medicao = {"projetos": [{"nome": self.PROJETO,
                                 "caminho": str(self.repo)}]}
        with mock.patch.object(executor.ExecutorProva, "PRAZO_POR_PROVA", 60), \
                mock.patch.object(executor.ExecutorProva, "PRAZO_DA_TAREFA",
                                  self.ESPERA):
            desfecho = enviar.fazer_a_tarefa(
                "http://127.0.0.1:%d" % self.porta, token, entregue, medicao)
        self.assertEqual(desfecho["estado"], "ok", desfecho)

        r = self.pedir("/api/progresso?projeto=%s" % self.PROJETO,
                       cookies=cookies)
        self.assertEqual(r.status, 200, r.corpo)
        pr = json.loads(r.corpo)
        pr = pr.get("progresso", pr)
        self.assertEqual(pr["estado"], "medido", pr)
        self.assertEqual(pr["percentual"], 50, pr)
        self.assertEqual((pr["comprovados"], pr["falhos"]), (1, 1), pr)


class AContaDosDocumentosReaisDoDervs(unittest.TestCase):
    def test_a_conta_bate_com_a_contagem_por_extenso(self):
        total, marcados = _criterios_por_extenso(AQUI)
        doc = documentos.ler_projeto(AQUI)
        pr = documentos.progresso(doc, "dervs", "2026-09-30T12:00:00+00:00")
        self.assertEqual(pr["total"], total,
                         "o leitor e a contagem por extenso discordam")
        self.assertEqual(pr["declarados"], marcados)
        # nenhuma prova roda nesta entrega: nunca ha percentual nem comprovado
        self.assertIsNone(pr["percentual"])
        self.assertEqual(pr["comprovados"], 0)
        self.assertEqual(pr["falhos"], 0)
        self.assertEqual(pr["nao_verificados"] + pr["faltam"], total)
        self.assertEqual(pr["estado"],
                         "nao_verificado" if total else "sem_documentacao")

    def test_o_briefing_desta_entrega_e_lido_com_os_criterios_dele(self):
        """O DERVS usa a propria documentacao (criterio 6 do briefing): o
        briefing que descreve esta entrega tem de aparecer, com aprovacao."""
        doc = documentos.ler_projeto(AQUI)
        d = next(x for x in doc["documentos"]
                 if x["slug"] == "progresso-por-documentacao")
        self.assertGreaterEqual(len(d["criterios"]), 5)
        self.assertEqual(d["aprovado_em"], "2026-09-30")

    def test_briefing_antigo_sem_checklist_nao_inventa_criterio(self):
        """Os briefings antigos nao foram convertidos: ficam de fora (ou com
        erro), nunca com criterio fabricado."""
        doc = documentos.ler_projeto(AQUI)
        por_slug = {d["slug"]: d for d in doc["documentos"]}
        antigo = AQUI / "docs" / "esteira" / "dervs" / "briefing.md"
        if antigo.is_file() and not re.search(
                r"(?m)^- \[[ xX]\] ", antigo.read_text(encoding="utf-8-sig")):
            self.assertNotIn("dervs", por_slug)


if __name__ == "__main__":
    unittest.main(verbosity=2)
