# -*- coding: utf-8 -*-
"""O fio das provas no servidor: pedir (`/api/provar`), receber o resultado
(`/agente/resultado`, chave `provas`) e alimentar a conta (`/api/progresso`,
`/api/dados`).

O que quebra em silencio se alguem mexer aqui:

  - o id da tarefa perde o dono, e duas contas com projeto de mesmo nome
    colidem na fila;
  - o pedido empresta o balcao de outra rota (esgotar um tranca o outro);
  - o resultado grava sem conferir a prova ATUAL do criterio (trocar a linha
    `Prova:` manteria o veredito antigo);
  - `/api/dados` deixa de passar as provas e a conta nunca sai de "nao
    verificado" — com todos os outros testes verdes;
  - as linhas do banco (`criterio_id`, `medido_em`) nao casam com as de
    `documentos.provas_validas` (`id`, `em`).

    python test_provar.py
"""
from __future__ import annotations

import json
import os
import unittest

os.environ.setdefault("DERVS_AMBIENTE", "local")
os.environ.setdefault("DERVS_COFRE",
                      "chave-de-teste-que-nao-e-segredo-nenhum-0123456789")

import banco         # noqa: E402
import documentos    # noqa: E402
import servir        # noqa: E402
import tarefas       # noqa: E402
from test_desenvolver import (criterio, documento, documentacao,  # noqa: E402
                              id_de)
from test_servir import BaseServidorDeVerdade  # noqa: E402

PROVA = "python test_alfa.py"
OUTRA_PROVA = "python test_beta.py"


class OAdaptadorDeLinhas(unittest.TestCase):
    def test_o_banco_fala_criterio_id_e_medido_em_e_documentos_fala_id_e_em(self):
        d = documento([criterio(1, prova=PROVA)])
        cid = id_de("p", "alfa", 1, "A tela mostra a barra de progresso")
        linhas = [{"criterio_id": cid, "prova": PROVA, "ok": True,
                   "medido_em": "2026-10-01T10:00:00+00:00", "motivo": "",
                   "sha": "", "tarefa_id": "t"}]
        # Sem o adaptador, `provas_validas` nao acha o id de ninguem.
        cru, _ = documentos.provas_validas(documentacao(d), "p", linhas)
        self.assertEqual(cru, {})
        veredito, em = documentos.provas_validas(
            documentacao(d), "p", servir._linhas_de_prova(linhas))
        self.assertEqual(veredito, {cid: True})
        self.assertEqual(em, "2026-10-01T10:00:00+00:00")

    def test_entrada_estranha_vira_lista_vazia(self):
        self.assertEqual(servir._linhas_de_prova(None), [])


class AsProvasNoServidorDeVerdade(BaseServidorDeVerdade):
    def setUp(self):
        super().setUp()
        self.addCleanup(self.limpar)

    def limpar(self):
        self.limpar_fila()
        con = banco.conectar()
        try:
            con.execute("DELETE FROM maquina")
            con.execute("DELETE FROM prova_rodada")
            con.commit()
        finally:
            con.close()

    # ------------------------------------------------------------ utilidades
    def com_projeto(self, nome, doc=None, usuario_id=None, **extra):
        dados = {"nome": nome}
        if doc is not None:
            dados["documentacao"] = doc
        dados.update(extra)
        con = banco.conectar()
        try:
            banco.gravar(nome, "local", dados, con=con,
                         usuario_id=usuario_id or self.uid)
            con.commit()
        finally:
            con.close()

    def outra_conta(self):
        AsProvasNoServidorDeVerdade._n = getattr(
            AsProvasNoServidorDeVerdade, "_n", 0) + 1
        con = banco.conectar()
        try:
            uid = banco.criar_usuario("prova%d@teste.local" % self._n, con=con)
            con.commit()
            cookie = banco.novo_token()
            banco.abrir_sessao(uid, cookie, banco.prazo(3600), con=con)
            final = banco.confirmar_segundo_fator(cookie, banco.novo_token(),
                                                  con=con)
            s = banco.sessao_valida(final, con=con)
        finally:
            con.close()
        return uid, ({"sessao": final}, servir.Hub._csrf_da_sessao(s))

    def projeto_com_provas(self, nome="pv-ok", usuario_id=None):
        """Dois criterios com a MESMA prova e um com outra."""
        d = documento([criterio(1, "Primeiro criterio", prova=PROVA),
                       criterio(2, "Segundo criterio", prova=PROVA),
                       criterio(3, "Terceiro criterio", prova=OUTRA_PROVA)])
        self.com_projeto(nome, documentacao(d), usuario_id=usuario_id)
        return [id_de(nome, "alfa", n, t) for n, t in
                ((1, "Primeiro criterio"), (2, "Segundo criterio"),
                 (3, "Terceiro criterio"))]

    def provar(self, projeto, sessao=None, extra=None):
        cookies, csrf = sessao or self.sessao_e_token()
        corpo = {"projeto": projeto}
        corpo.update(extra or {})
        return self.pedir("/api/provar", "POST", corpo, cookies=cookies,
                          cabecalhos={"X-Token": csrf})

    def progresso(self, nome, sessao=None):
        cookies = (sessao or self.sessao_e_token())[0]
        r = self.pedir("/api/progresso?projeto=%s" % nome, cookies=cookies)
        self.assertEqual(r.status, 200, r.corpo)
        return json.loads(r.corpo)

    def dados(self):
        cookies = self.sessao_e_token()[0]
        return json.loads(self.pedir("/api/dados", cookies=cookies).corpo)

    def linhas_da_fila(self):
        con = banco.conectar()
        try:
            return [dict(l) for l in con.execute("SELECT * FROM fila")]
        finally:
            con.close()

    def tarefa_rodando(self, projeto):
        """Pede a prova e poe a tarefa nas maos de uma maquina, como o agente."""
        j = json.loads(self.provar(projeto).corpo)
        self.assertIs(j["pedido"], True, j)
        token, mid = self.maquina_com_token()
        con = banco.conectar()
        try:
            con.execute("UPDATE fila SET maquina_id = ?, estado = 'rodando'"
                        " WHERE id = ?", (mid, j["tarefa"]))
            con.commit()
        finally:
            con.close()
        return j["tarefa"], token

    def resultado(self, token, tarefa, provas, **extra):
        corpo = {"tipo": "desfecho", "id": tarefa, "estado": "ok",
                 "provas": provas, "sha": "abc123"}
        corpo.update(extra)
        return self.como_agente(token, "/agente/resultado", corpo)

    # ---------------------------------------------------------------- pedir
    def test_pedido_enfileira_vermelha_com_dono_executor_e_comandos(self):
        self.projeto_com_provas("pv-pedido")
        r = self.provar("pv-pedido")
        self.assertEqual(r.status, 200, r.corpo)
        j = json.loads(r.corpo)
        self.assertIs(j["ok"], True)
        self.assertIs(j["pedido"], True)
        l = self.linhas_da_fila()[0]
        self.assertTrue(l["id"].startswith("provar:%d:" % self.uid), l["id"])
        self.assertEqual(l["id"], j["tarefa"])
        self.assertEqual(l["regra"], tarefas.PROVAR)
        self.assertEqual(l["executor"], tarefas.EXECUTOR_DA_PROVA)
        self.assertEqual(l["trilho"], "prova")
        self.assertEqual(l["usuario_id"], self.uid)
        self.assertEqual(l["projeto"], "pv-pedido")
        self.assertEqual(l["cor"], "vermelho")
        self.assertIsNone(l["aprovado_em"])
        self.assertIn(banco.MARCA_DA_PROVA + PROVA, l["detalhe"])
        self.assertIn(banco.MARCA_DA_PROVA + OUTRA_PROVA, l["detalhe"])

    def test_cliques_simultaneos_enfileiram_uma_prova_so(self):
        import threading
        self.projeto_com_provas("pv-corrida")
        sessao = self.sessao_e_token()
        respostas, trava = [], threading.Lock()

        def clicar():
            r = self.provar("pv-corrida", sessao=sessao)
            with trava:
                respostas.append(r)
        fios = [threading.Thread(target=clicar) for _ in range(8)]
        for f in fios:
            f.start()
        for f in fios:
            f.join(timeout=30)
        self.assertEqual(len(respostas), 8)
        status = [r.status for r in respostas]
        self.assertTrue(all(s in (200, 429) for s in status), status)
        self.assertEqual(len(self.linhas_da_fila()), 1)

    def test_a_decisao_de_enfileirar_prova_mora_sob_a_trava(self):
        # Guarda de codigo-fonte: o teste de corrida e probabilistico, este nao.
        import inspect
        fonte = inspect.getsource(servir.Hub._provar_pedir)
        corpo = fonte.split("with self._TRAVA_DE_PROVAS:", 1)
        self.assertEqual(len(corpo), 2, "a trava sumiu de _provar_pedir")
        self.assertIn("prova_aberta", corpo[1])
        self.assertIn("banco.enfileirar", corpo[1])

    def test_os_comandos_aparecem_na_coluna_prova_da_lista(self):
        self.projeto_com_provas("pv-lista")
        self.provar("pv-lista")
        r = self.pedir("/api/tarefas", cookies=self.sessao_e_token()[0])
        t = json.loads(r.corpo)["tarefas"][0]
        self.assertIn(PROVA, t["prova"])
        self.assertIn(OUTRA_PROVA, t["prova"])

    def test_o_dono_entra_no_id_duas_contas_com_projeto_igual_nao_colidem(self):
        self.projeto_com_provas("pv-igual")
        uid2, sessao2 = self.outra_conta()
        self.projeto_com_provas("pv-igual", usuario_id=uid2)
        a = json.loads(self.provar("pv-igual").corpo)
        b = json.loads(self.provar("pv-igual", sessao=sessao2).corpo)
        self.assertIs(a["pedido"], True)
        self.assertIs(b["pedido"], True)
        self.assertNotEqual(a["tarefa"], b["tarefa"])
        self.assertEqual(len(self.linhas_da_fila()), 2)

    def test_nao_existe_e_nao_e_seu_dao_o_mesmo_404(self):
        uid2, sessao2 = self.outra_conta()
        self.projeto_com_provas("pv-dela", usuario_id=uid2)
        alheio = self.provar("pv-dela")
        inexistente = self.provar("pv-que-nao-existe")
        self.assertEqual(alheio.status, 404)
        self.assertEqual(inexistente.status, 404)
        self.assertEqual(alheio.corpo, inexistente.corpo)
        self.assertEqual(json.loads(alheio.corpo)["erro"],
                         "projeto nao encontrado")
        self.assertEqual(self.linhas_da_fila(), [])

    def test_o_dono_e_o_projeto_do_corpo_que_nao_e_da_conta_sao_ignorados(self):
        self.projeto_com_provas("pv-meu")
        uid2, _ = self.outra_conta()
        self.projeto_com_provas("pv-dela2", usuario_id=uid2)
        r = self.provar("pv-meu", extra={"usuario_id": uid2,
                                         "comandos": ["rm -rf /"]})
        self.assertEqual(r.status, 200, r.corpo)
        l = self.linhas_da_fila()[0]
        self.assertEqual(l["usuario_id"], self.uid)
        self.assertNotIn("rm -rf", l["detalhe"])
        self.assertEqual(self.provar("pv-dela2").status, 404)

    def test_projeto_bloqueado_e_403(self):
        self.projeto_com_provas("Nexa-x")
        r = self.provar("Nexa-x")
        self.assertEqual(r.status, 403, r.corpo)
        self.assertEqual(json.loads(r.corpo)["erro"], "projeto bloqueado")
        self.assertEqual(self.linhas_da_fila(), [])

    def test_sem_prova_aceita_e_409(self):
        d = documento([criterio(1, prova="rm -rf /")])
        self.com_projeto("pv-sem", documentacao(d))
        r = self.provar("pv-sem")
        self.assertEqual(r.status, 409, r.corpo)
        self.assertEqual(json.loads(r.corpo)["erro"],
                         "nenhuma prova para rodar")

    def test_prova_ja_aberta_nao_enfileira_de_novo(self):
        self.projeto_com_provas("pv-aberta")
        self.assertIs(json.loads(self.provar("pv-aberta").corpo)["pedido"],
                      True)
        r = self.provar("pv-aberta")
        self.assertEqual(r.status, 200, r.corpo)
        self.assertIs(json.loads(r.corpo)["pedido"], False)
        self.assertEqual(len(self.linhas_da_fila()), 1)

    def test_o_balcao_e_proprio_esgotar_provar_nao_tranca_desenvolver(self):
        cid = self.projeto_com_provas("pv-balcao")[0]
        ultimo = None
        for _ in range(servir.Hub.TETO_DE_PROVAS + 1):
            ultimo = self.provar("pv-balcao")
        self.assertEqual(ultimo.status, 429)
        cookies, csrf = self.sessao_e_token()
        r = self.pedir("/api/desenvolver", "POST", {"criterio": cid},
                       cookies=cookies, cabecalhos={"X-Token": csrf})
        self.assertNotEqual(r.status, 429, r.corpo)

    def test_o_balcao_de_desenvolver_tambem_nao_tranca_provar(self):
        self.projeto_com_provas("pv-balcao2")
        cookies, csrf = self.sessao_e_token()
        for i in range(servir.Hub.TETO_DE_DESENVOLVIMENTOS + 1):
            self.pedir("/api/desenvolver", "POST", {"criterio": "x%d" % i},
                       cookies=cookies, cabecalhos={"X-Token": csrf})
        self.assertNotEqual(self.provar("pv-balcao2").status, 429)

    # ---------------------------------------------------- as regras da tarefa
    def test_provar_nunca_fica_verde_e_a_tela_a_lista_em_nunca_verde(self):
        self.assertFalse(tarefas.pode_repintar("provar", "verde"))
        self.assertTrue(tarefas.pode_repintar("provar", "vermelho"))
        self.assertEqual(tarefas.cor_da_regra("provar", {"provar": "verde"}),
                         tarefas.VERMELHO)
        j = json.loads(self.pedir("/api/tarefas",
                                  cookies=self.sessao_e_token()[0]).corpo)
        self.assertIn("provar", j["nunca_verde"])

    # ------------------------------------------------------------ o resultado
    def test_resultado_grava_e_a_conta_passa_a_medida(self):
        cids = self.projeto_com_provas("pv-res")
        antes = self.progresso("pv-res")["progresso"]
        self.assertEqual(antes["estado"], "nao_verificado")
        self.assertIsNone(antes["percentual"])
        tarefa, token = self.tarefa_rodando("pv-res")
        r = self.resultado(token, tarefa, [
            {"prova": PROVA, "ok": True, "criterios": cids[:2], "motivo": ""},
            {"prova": OUTRA_PROVA, "ok": False, "criterios": [cids[2]],
             "motivo": "falhou"}])
        self.assertEqual(r.status, 200, r.corpo)
        j = json.loads(r.corpo)
        self.assertEqual(j["provas_gravadas"], 3)
        self.assertEqual(j["provas_descartadas"], 0)
        pr = self.progresso("pv-res")["progresso"]
        self.assertEqual(pr["estado"], "medido")
        self.assertEqual((pr["comprovados"], pr["falhos"]), (2, 1))
        self.assertEqual(pr["percentual"], 66)
        self.assertIsNotNone(pr["provado_em"])
        # e /api/dados, que e o que a tela le a cada minuto
        p = [x for x in self.dados()["projetos"] if x["nome"] == "pv-res"][0]
        self.assertEqual(p["progresso"]["estado"], "medido")

    def test_estado_medido_so_depois_de_resultado_true_ou_false(self):
        cids = self.projeto_com_provas("pv-medido")
        tarefa, token = self.tarefa_rodando("pv-medido")
        # `ok: None` (a prova nao chegou a rodar) nao mede nada.
        self.resultado(token, tarefa, [
            {"prova": PROVA, "ok": None, "criterios": cids[:2],
             "motivo": "sem python"}])
        self.assertEqual(self.progresso("pv-medido")["progresso"]["estado"],
                         "nao_verificado")
        self.resultado(token, tarefa, [
            {"prova": PROVA, "ok": False, "criterios": cids[:1], "motivo": ""}])
        self.assertEqual(self.progresso("pv-medido")["progresso"]["estado"],
                         "medido")

    def test_ok_em_texto_nao_grava(self):
        cids = self.projeto_com_provas("pv-tipo")
        tarefa, token = self.tarefa_rodando("pv-tipo")
        for torto in ("true", 1, "True", [True], {}):
            r = self.resultado(token, tarefa, [
                {"prova": PROVA, "ok": torto, "criterios": cids[:2],
                 "motivo": ""}])
            self.assertEqual(r.status, 200, r.corpo)
            self.assertEqual(json.loads(r.corpo)["provas_gravadas"], 0, torto)
        self.assertEqual(banco.provas_da_conta(self.uid), {})
        self.assertEqual(self.progresso("pv-tipo")["progresso"]["estado"],
                         "nao_verificado")

    def test_resultado_de_outra_regra_e_ignorado(self):
        cids = self.projeto_com_provas("pv-regra")
        self.enfileirar_tarefa(id_="outra:1", regra="env_drift", verde=False)
        token, mid = self.maquina_com_token()
        con = banco.conectar()
        try:
            con.execute("UPDATE fila SET maquina_id = ?, projeto = 'pv-regra',"
                        " estado = 'rodando' WHERE id = 'outra:1'", (mid,))
            con.commit()
        finally:
            con.close()
        r = self.resultado(token, "outra:1", [
            {"prova": PROVA, "ok": True, "criterios": cids[:2], "motivo": ""}])
        self.assertEqual(r.status, 200, r.corpo)
        self.assertEqual(banco.provas_da_conta(self.uid), {})

    def test_criterio_de_outra_conta_e_descartado_e_contado(self):
        meus = self.projeto_com_provas("pv-meu3")
        uid2, _ = self.outra_conta()
        dela = self.projeto_com_provas("pv-dela3", usuario_id=uid2)
        tarefa, token = self.tarefa_rodando("pv-meu3")
        r = self.resultado(token, tarefa, [
            {"prova": PROVA, "ok": True, "criterios": [meus[0], dela[0]],
             "motivo": ""}])
        j = json.loads(r.corpo)
        self.assertEqual(j["provas_gravadas"], 1)
        self.assertEqual(j["provas_descartadas"], 1)
        mia = banco.provas_da_conta(self.uid)
        self.assertEqual([l["criterio_id"] for l in mia["pv-meu3"]], [meus[0]])
        self.assertEqual(banco.provas_da_conta(uid2), {})

    def test_o_projeto_do_corpo_e_o_dono_do_corpo_sao_ignorados(self):
        meus = self.projeto_com_provas("pv-meu4")
        uid2, _ = self.outra_conta()
        self.projeto_com_provas("pv-dela4", usuario_id=uid2)
        tarefa, token = self.tarefa_rodando("pv-meu4")
        self.resultado(token, tarefa, [
            {"prova": PROVA, "ok": True, "criterios": meus[:1], "motivo": ""}],
            projeto="pv-dela4", usuario_id=uid2)
        self.assertEqual(list(banco.provas_da_conta(self.uid)), ["pv-meu4"])
        self.assertEqual(banco.provas_da_conta(uid2), {})

    def test_prova_diferente_da_do_criterio_nao_grava(self):
        cids = self.projeto_com_provas("pv-diff")
        tarefa, token = self.tarefa_rodando("pv-diff")
        r = self.resultado(token, tarefa, [
            {"prova": OUTRA_PROVA, "ok": True, "criterios": cids[:1],
             "motivo": ""}])
        j = json.loads(r.corpo)
        self.assertEqual((j["provas_gravadas"], j["provas_descartadas"]),
                         (0, 1))

    def test_item_torto_e_descartado_sem_derrubar_os_bons(self):
        cids = self.projeto_com_provas("pv-torto")
        tarefa, token = self.tarefa_rodando("pv-torto")
        r = self.resultado(token, tarefa, [
            "texto", 7,
            {"prova": PROVA, "ok": True, "criterios": ["x" * 65],
             "motivo": ""},
            {"prova": PROVA, "ok": True, "criterios": cids[:1],
             "motivo": "m" * 301},
            {"prova": PROVA, "ok": True, "criterios": cids[:1],
             "motivo": "\ud800"},
            {"prova": PROVA, "ok": True, "criterios": cids[:1],
             "motivo": "bom"}])
        self.assertEqual(r.status, 200, r.corpo)
        j = json.loads(r.corpo)
        self.assertEqual(j["provas_gravadas"], 1)
        self.assertEqual(j["provas_descartadas"], 5)

    def test_sha_torto_e_lista_acima_do_teto_nao_gravam(self):
        cids = self.projeto_com_provas("pv-sha")
        tarefa, token = self.tarefa_rodando("pv-sha")
        bom = {"prova": PROVA, "ok": True, "criterios": cids[:1], "motivo": ""}
        r = self.resultado(token, tarefa, [bom], sha="NAO-E-HEX")
        self.assertEqual(r.status, 200, r.corpo)
        self.assertEqual(banco.provas_da_conta(self.uid), {})
        teto = documentos.MAX_DOCUMENTOS * documentos.MAX_CRITERIOS
        r = self.resultado(token, tarefa, [bom] * (teto + 1))
        self.assertEqual(banco.provas_da_conta(self.uid), {})

    def test_prova_trocada_depois_do_resultado_volta_a_nao_verificada(self):
        cids = self.projeto_com_provas("pv-troca")
        tarefa, token = self.tarefa_rodando("pv-troca")
        self.resultado(token, tarefa, [
            {"prova": PROVA, "ok": True, "criterios": cids[:2], "motivo": ""},
            {"prova": OUTRA_PROVA, "ok": True, "criterios": cids[2:],
             "motivo": ""}])
        self.assertEqual(self.progresso("pv-troca")["progresso"]["estado"],
                         "medido")
        d = documento([criterio(1, "Primeiro criterio", prova="python test_novo.py"),
                       criterio(2, "Segundo criterio", prova="python test_novo.py"),
                       criterio(3, "Terceiro criterio", prova="python test_novo.py")])
        self.com_projeto("pv-troca", documentacao(d))
        pr = self.progresso("pv-troca")["progresso"]
        self.assertEqual(pr["estado"], "nao_verificado")
        self.assertEqual(pr["comprovados"], 0)

    def test_o_selo_de_saude_nao_muda_com_as_provas(self):
        cids = self.projeto_com_provas("pv-selo", )
        antes = [p for p in self.dados()["projetos"] if p["nome"] == "pv-selo"][0]
        tarefa, token = self.tarefa_rodando("pv-selo")
        self.resultado(token, tarefa, [
            {"prova": PROVA, "ok": False, "criterios": cids[:2], "motivo": ""}])
        depois = [p for p in self.dados()["projetos"]
                  if p["nome"] == "pv-selo"][0]
        self.assertEqual(antes["progresso"]["estado"], "nao_verificado")
        self.assertEqual(depois["progresso"]["estado"], "medido")
        self.assertEqual(antes["selo"], depois["selo"])

    def test_criterio_comprovado_deixa_de_ser_desenvolvivel(self):
        cids = self.projeto_com_provas("pv-dev")
        cookies, csrf = self.sessao_e_token()
        pedir = lambda: self.pedir(  # noqa: E731
            "/api/desenvolver", "POST", {"criterio": cids[0]},
            cookies=cookies, cabecalhos={"X-Token": csrf})
        self.assertEqual(pedir().status, 200)
        self.limpar_fila()
        tarefa, token = self.tarefa_rodando("pv-dev")
        self.resultado(token, tarefa, [
            {"prova": PROVA, "ok": True, "criterios": cids[:1], "motivo": ""}])
        self.assertEqual(pedir().status, 403)

    def test_progresso_diz_se_e_provavel(self):
        self.projeto_com_provas("pv-prov")
        self.assertIs(self.progresso("pv-prov")["provavel"], True)
        self.com_projeto("pv-semprova", documentacao(
            documento([criterio(1, "x y z")])))
        self.assertIs(self.progresso("pv-semprova")["provavel"], False)
        self.projeto_com_provas("Nexa-y")
        self.assertIs(self.progresso("Nexa-y")["provavel"], False)


if __name__ == "__main__":
    unittest.main(verbosity=2)
