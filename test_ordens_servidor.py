# -*- coding: utf-8 -*-
"""Conectar simples, entrega C: os pedidos ao servidor, do lado do DERVS (E2).

    python test_ordens_servidor.py

Contratos de `docs/superpowers/plans/dervs-conectar-acoes-c.md` (I1 a I5) e
`docs/esteira/conectar-acoes/spec.md` (C1, C2, C6 a C9, C11): a linha com
pedidos, a medicao com o bloco `ordens`, preparar, assinar, a busca e o
desfecho do ajudante, e o que `/api/dados` mostra.

A ASSINATURA AQUI E DE TESTE (o assinador de `test_passkey.py`): este arquivo
prova a logica das ROTAS. A conta de criptografia do DERVS e conferida por
fora (RFC 6979, `test_p256`), e o vetor de FORA novo prova o ajudante em
`test_ajudante_acoes` e o fio em `test_acoes_fio`.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("DERVS_AMBIENTE", "local")
os.environ.setdefault("DERVS_COFRE",
                      "chave-de-teste-que-nao-e-segredo-nenhum-0123456789")

import banco      # noqa: E402
import cortina    # noqa: E402
import passkey    # noqa: E402
import servir     # noqa: E402
import tarefas    # noqa: E402
from test_passkey import (_assinar, _client_data, _dados_do_autenticador,  # noqa: E402
                          _par_de_chaves)
from test_servidor_ligado import _Base as _BaseLigado   # noqa: E402
from test_servidor_ligado import _corpo as _corpo_da_medicao  # noqa: E402

IDENT = "7f3a9c2e5b8d41f6a0c3e9b2d4f6a8c1"
NUMERO = "4e1d2c3b5a6978f0e1d2c3b4a5968778"
T0 = 1791558000
RECUSA = {"erro": "nao deu"}
NAO_ACHEI = {"erro": "nao achei"}
CAMPOS_DA_ORDEM = {"servidor", "tipo", "alvo", "numero", "criado", "vence",
                   "cliente", "autenticador", "assinatura"}


def sistema(nome, projeto="", estado="running"):
    return {"nome": nome, "projeto": projeto, "estado": estado,
            "saude": "healthy", "desde": "2026-10-08T12:00:00+00:00",
            "reinicios": 0, "imagem": "x:vps", "sha": ""}


SISTEMAS = [sistema("grimoire-web", "grimoire"), sistema("dervs-app", "dervs"),
            sistema("ajudei-db", "ajudei-saude")]


def fixo(segundos):
    """O relogio das ordens, preso (a costura `Hub._segundos_agora`)."""
    return mock.patch.object(servir.Hub, "_segundos_agora",
                             staticmethod(lambda: segundos))


class _Base(_BaseLigado):
    def setUp(self):
        super().setUp()
        con = banco.conectar()
        try:
            con.execute("DELETE FROM maquina WHERE tipo = 'servidor'")
            con.execute("DELETE FROM chave_de_acesso")
            con.commit()
        finally:
            con.close()

    # ------------------------------------------------------------ o cenario
    def chave(self, uid=None, apelido="Celular"):
        """Cadastra uma chave de acesso viva. (privada, publica, cred_id)."""
        privada, publica = _par_de_chaves()
        cred = passkey.b64url(os.urandom(32))
        banco.guardar_chave_de_acesso(uid or self.uid, cred, publica,
                                      apelido=apelido)
        return privada, publica, cred

    def bloco(self, *chaves, voltaveis=("dervs", "grimoire"), ident=IDENT):
        return {"versao": 1, "ident": ident,
                "chaves": [banco.impressao_da_chave(*c[1]) for c in chaves],
                "voltaveis": list(voltaveis)}

    def cenario(self, nome="vps-ovh", sistemas=None, com_ordens=True,
                sessao=None, chaves=None, uid=None):
        """Servidor ligado, uma chave do dono, medicao COM o bloco `ordens`."""
        uid = uid or self.uid
        chaves = [self.chave(uid)] if chaves is None else chaves
        segredo, m = self.ligar_servidor(nome, sessao=sessao)
        corpo = _corpo_da_medicao(sistemas=SISTEMAS if sistemas is None
                                  else sistemas)
        if com_ordens:
            corpo["ordens"] = self.bloco(*chaves)
        r = self.medir(segredo, corpo)
        self.assertEqual(200, r.status, r.corpo)
        return {"segredo": segredo, "m": m, "chaves": chaves,
                "sessao": sessao or self.sessao_e_token()}

    def preparar(self, c, tipo="reiniciar", alvo="grimoire-web", mid=None,
                 sessao=None):
        return self.dono("/api/maquinas/ordem/preparar",
                         {"maquina_id": mid if mid is not None
                          else c["m"]["id"], "tipo": tipo, "alvo": alvo},
                         sessao=sessao or c["sessao"])

    def origem(self):
        return "http://127.0.0.1:%d" % self.porta

    def assinatura(self, prep, chave, numero=None, origem=None,
                   rp_id="127.0.0.1", flags=0x05, contador=1, desafio=None,
                   assina_com=None, cred=None):
        """O corpo de `assinar`, como o navegador mandaria."""
        privada, _publica, cred_id = chave
        desafio = desafio or passkey.de_b64url(prep["desafio"])
        cliente = _client_data("webauthn.get", desafio,
                               origem=origem or self.origem())
        aut = _dados_do_autenticador(rp_id=rp_id, flags=flags,
                                     contador=contador)
        sig = _assinar(assina_com or privada,
                       aut + hashlib.sha256(cliente).digest())
        return {"numero": numero or prep["numero"], "cred_id": cred or cred_id,
                "cliente": passkey.b64url(cliente),
                "autenticador": passkey.b64url(aut),
                "assinatura": passkey.b64url(sig)}

    def assinar(self, c, corpo, sessao=None):
        return self.dono("/api/maquinas/ordem/assinar", corpo,
                         sessao=sessao or c["sessao"])

    def pedido_assinado(self, c, tipo="reiniciar", alvo="grimoire-web",
                        contador=1):
        """Prepara e assina pela rota. Devolve o corpo de `preparar`."""
        r = self.preparar(c, tipo, alvo)
        self.assertEqual(200, r.status, r.corpo)
        prep = self.json(r)
        r = self.assinar(c, self.assinatura(prep, c["chaves"][0],
                                            contador=contador))
        self.assertEqual((200, {"ok": True}), (r.status, self.json(r)), r.corpo)
        return prep

    def buscar(self, c):
        return self.como_maquina(c["segredo"], "/agente/servidor/ordens", {})

    def ordem_no_banco(self, numero):
        con = banco.conectar()
        try:
            l = con.execute("SELECT * FROM ordem_de_servidor WHERE numero = ?",
                            (numero,)).fetchone()
            return dict(l) if l else None
        finally:
            con.close()

    def servidor_no_painel(self, c, sessao=None):
        for s in self.dados(sessao or c["sessao"])["servidores_ligados"]:
            if s["maquina_id"] == c["m"]["id"]:
                return s
        self.fail("o servidor nao esta em /api/dados")


# =========================================================== a linha (C1, I1)

class ALinhaComPedidos(_Base):
    FONTE = ('# -*- coding: ascii -*-\nALVO = ""   # DERVS:ALVO\n'
             'print(ALVO)\n')

    def setUp(self):
        super().setUp()
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        arquivo = Path(self.pasta.name) / "ajudante_servidor.py"
        arquivo.write_text(self.FONTE, encoding="utf-8")
        trocar = mock.patch.object(servir.Hub, "AJUDANTE", arquivo)
        trocar.start()
        self.addCleanup(trocar.stop)

    def linha_do_dono(self):
        cookies, _ = self.sessao_e_token()
        r = self.pedir("/api/ajudante/linha", cookies=cookies)
        self.assertEqual(200, r.status, r.corpo)
        return self.json(r)

    @staticmethod
    def forma(chave):
        return "%064x.%064x" % chave[1]

    def test_duas_chaves_a_linha_termina_nelas_e_o_resumo_e_o_mesmo(self):
        k1 = self.chave(apelido="Celular do Thiago")
        k2 = self.chave(apelido="PIN do notebook")
        d = self.linha_do_dono()
        self.assertEqual(
            d["linha"] + " instalar --ordens "
            + self.forma(k2) + "," + self.forma(k1), d["linha_com_ordens"])
        self.assertEqual(["PIN do notebook", "Celular do Thiago"],
                         d["chaves_na_linha"])
        self.assertEqual({"linha", "sha256", "endereco", "linha_com_ordens",
                          "chaves_na_linha"}, set(d))
        # o arquivo e a linha so-olhar nao mudaram: o resumo e o do download
        baixado = self.pedir("/ajudante/servidor.py", com_origem=False)
        self.assertEqual(hashlib.sha256(baixado.corpo.encode("ascii"))
                         .hexdigest(), d["sha256"])
        self.assertTrue(d["linha"].endswith("sudo python3 -I dervs-ajudante.py"))

    def test_sem_chave_viva_e_nulo_e_lista_vazia(self):
        d = self.linha_do_dono()
        self.assertIsNone(d["linha_com_ordens"])
        self.assertEqual([], d["chaves_na_linha"])
        self.assertTrue(d["linha"])

    def test_chave_revogada_fica_de_fora(self):
        k1 = self.chave(apelido="velha")
        k2 = self.chave(apelido="nova")
        con = banco.conectar()
        try:
            con.execute("UPDATE chave_de_acesso SET revogada_em = 'x'"
                        " WHERE cred_id = ?", (k1[2],))
            con.commit()
        finally:
            con.close()
        d = self.linha_do_dono()
        self.assertEqual(["nova"], d["chaves_na_linha"])
        self.assertTrue(d["linha_com_ordens"].endswith(self.forma(k2)))
        self.assertNotIn(self.forma(k1), d["linha_com_ordens"])

    def test_no_maximo_cinco_chaves_as_mais_novas(self):
        todas = [self.chave(apelido="c%d" % i) for i in range(7)]
        d = self.linha_do_dono()
        self.assertEqual(["c6", "c5", "c4", "c3", "c2"], d["chaves_na_linha"])
        fim = d["linha_com_ordens"].split(" --ordens ")[1].split(",")
        self.assertEqual([self.forma(k) for k in todas[:1:-1]][:5], fim)

    def test_uma_chave_de_outra_conta_nao_entra(self):
        outro = banco.criar_usuario("outro-%s@teste.local"
                                    % banco.novo_token()[:6])
        self.chave(uid=outro, apelido="dele")
        self.assertIsNone(self.linha_do_dono()["linha_com_ordens"])


# ==================================================== a medicao (C2, I2)

class AMedicaoComOBlocoDePedidos(_Base):
    def gravada(self, m):
        con = banco.conectar()
        try:
            return json.loads(con.execute(
                "SELECT dados FROM medicao_de_servidor WHERE maquina_id = ?",
                (m["id"],)).fetchone()[0])
        finally:
            con.close()

    def medir_com(self, bloco):
        segredo, m = self.ligar_servidor()
        r = self.medir(segredo, _corpo_da_medicao(ordens=bloco))
        self.assertEqual(200, r.status, r.corpo)
        return r, self.gravada(m)

    def test_o_bloco_do_contrato_entra_e_a_resposta_continua_curta(self):
        k = self.chave()
        bloco = self.bloco(k)
        r, dados = self.medir_com(bloco)
        self.assertEqual({"ok": True, "invalidos": 0}, self.json(r))
        self.assertEqual(bloco, dados["ordens"])

    def test_sem_o_bloco_a_chave_nao_existe(self):
        segredo, m = self.ligar_servidor()
        self.medir(segredo)
        self.assertNotIn("ordens", self.gravada(m))

    def test_ident_torto_derruba_o_bloco_inteiro(self):
        k = self.chave()
        for ident in ("g" * 32, "A" * 32, "a" * 31, "a" * 33, 5, None, ""):
            r, dados = self.medir_com(dict(self.bloco(k), ident=ident))
            self.assertNotIn("ordens", dados, ident)
            self.assertGreaterEqual(self.json(r)["invalidos"], 1)

    def test_versao_diferente_de_1_derruba_o_bloco(self):
        k = self.chave()
        for versao in (2, 0, "1", True, None):
            _r, dados = self.medir_com(dict(self.bloco(k), versao=versao))
            self.assertNotIn("ordens", dados, versao)

    def test_bloco_que_nao_e_dicionario_e_descartado(self):
        for torto in ([1], "x", 5, True):
            r, dados = self.medir_com(torto)
            self.assertNotIn("ordens", dados, torto)
            self.assertGreaterEqual(self.json(r)["invalidos"], 1)

    def test_seis_chaves_viram_cinco_e_contam(self):
        ks = [self.chave() for _ in range(6)]
        r, dados = self.medir_com(self.bloco(*ks))
        self.assertEqual(5, len(dados["ordens"]["chaves"]))
        self.assertEqual(1, self.json(r)["invalidos"])

    def test_impressao_torta_e_descartada(self):
        k = self.chave()
        torta = [banco.impressao_da_chave(*k[1]), "XYZ", "A" * 16, 7,
                 "a" * 15]
        r, dados = self.medir_com(dict(self.bloco(k), chaves=torta))
        self.assertEqual([banco.impressao_da_chave(*k[1])],
                         dados["ordens"]["chaves"])
        self.assertEqual(4, self.json(r)["invalidos"])

    def test_voltavel_bloqueado_ou_torto_e_descartado(self):
        k = self.chave()
        voltaveis = ["grimoire", "ajudei-saude", "ajudei-saude-web",
                     "Grimoire", "a_b", "-x", "", 5, "x" * 64]
        r, dados = self.medir_com(dict(self.bloco(k), voltaveis=voltaveis))
        self.assertEqual(["grimoire"], dados["ordens"]["voltaveis"])
        self.assertEqual(8, self.json(r)["invalidos"])

    def test_201_voltaveis_passam_cortados_em_200(self):
        k = self.chave()
        nomes = ["p%d" % i for i in range(201)]
        r, dados = self.medir_com(dict(self.bloco(k), voltaveis=nomes))
        self.assertEqual(200, len(dados["ordens"]["voltaveis"]))
        self.assertEqual(1, self.json(r)["invalidos"])

    def test_chave_desconhecida_dentro_do_bloco_e_descartada_e_contada(self):
        k = self.chave()
        r, dados = self.medir_com(dict(self.bloco(k), comando="rm -rf /"))
        self.assertNotIn("comando", dados["ordens"])
        self.assertEqual(1, self.json(r)["invalidos"])

    def test_a_resposta_nunca_leva_ordem_nem_tarefa(self):
        k = self.chave()
        r, _dados = self.medir_com(self.bloco(k))
        self.assertEqual({"ok", "invalidos"}, set(self.json(r)))


# ================================================== preparar (C7, I4)

class PrepararOPedido(_Base):
    def test_200_com_os_campos_do_contrato_e_o_desafio_do_vetor(self):
        c = self.cenario()
        with fixo(T0), mock.patch.object(servir.Hub, "_numero_da_ordem",
                                         staticmethod(lambda: NUMERO)):
            r = self.preparar(c)
        self.assertEqual(200, r.status, r.corpo)
        d = self.json(r)
        self.assertEqual({"numero", "desafio", "rp_id", "chaves", "segundos",
                          "frase"}, set(d))
        self.assertEqual(NUMERO, d["numero"])
        # o mesmo desafio da tabela I0: ident, tipo, alvo, numero e relogio
        self.assertEqual("I1hYDAUhTGY5VpoQX-AjUNLOox129P1vbq2JZEUJDYQ",
                         d["desafio"])
        self.assertEqual("127.0.0.1", d["rp_id"])
        self.assertEqual([c["chaves"][0][2]], d["chaves"])
        self.assertEqual(300, d["segundos"])
        l = self.ordem_no_banco(NUMERO)
        self.assertEqual((T0, T0 + 300, IDENT, "reiniciar", "grimoire-web"),
                         (l["criado"], l["vence"], l["ident"], l["tipo"],
                          l["alvo"]))
        self.assertIsNone(l["assinada_em"])

    def test_o_desafio_e_o_resumo_do_texto_remontado(self):
        c = self.cenario()
        d = self.json(self.preparar(c, "voltar", "grimoire"))
        l = self.ordem_no_banco(d["numero"])
        texto = tarefas.texto_da_ordem({
            "servidor": IDENT, "tipo": "voltar", "alvo": "grimoire",
            "numero": d["numero"], "criado": l["criado"], "vence": l["vence"]})
        self.assertEqual(passkey.b64url(hashlib.sha256(
            texto.encode("ascii")).digest()), d["desafio"])

    def test_a_frase_exata_dos_dois_tipos(self):
        c = self.cenario(nome="vps-ovh")
        self.assertEqual(
            "Reiniciar o sistema “grimoire-web” no servidor "
            "“vps-ovh”",
            self.json(self.preparar(c))["frase"])
        con = banco.conectar()
        try:
            con.execute("DELETE FROM ordem_de_servidor")
            con.commit()
        finally:
            con.close()
        self.assertEqual(
            "Voltar “grimoire” para a versão anterior no "
            "servidor “vps-ovh”",
            self.json(self.preparar(c, "voltar", "grimoire"))["frase"])

    def test_a_frase_mora_numa_funcao_so(self):
        self.assertEqual(
            "Reiniciar o sistema “a” no servidor “b”",
            servir.Hub._frase_do_pedido("reiniciar", "a", "b"))
        self.assertEqual(
            "Voltar “a” para a versão anterior no servidor "
            "“b”", servir.Hub._frase_do_pedido("voltar", "a", "b"))

    def test_outra_conta_e_id_inexistente_dao_o_mesmo_404(self):
        outro = banco.criar_usuario("outro-%s@teste.local"
                                    % banco.novo_token()[:6])
        sessao_dele = self.sessao_de(outro)
        dele = self.cenario("vps-dele", sessao=sessao_dele,
                            chaves=[self.chave(outro)], uid=outro)
        c = self.cenario()
        de_outra = self.preparar(c, mid=dele["m"]["id"])
        inexistente = self.preparar(c, mid=10 ** 9)
        self.assertEqual((404, NAO_ACHEI), (de_outra.status,
                                            self.json(de_outra)))
        self.assertEqual((de_outra.status, de_outra.corpo),
                         (inexistente.status, inexistente.corpo))
        self.assertIsNone(self.ordem_no_banco(NUMERO))

    def test_computador_e_servidor_revogado_tambem_sao_404(self):
        c = self.cenario()
        _segredo, maq = self.maquina_com_token()
        r = self.preparar(c, mid=maq)
        self.assertEqual((404, NAO_ACHEI), (r.status, self.json(r)))
        banco.revogar_maquina(c["m"]["id"], self.uid)
        r = self.preparar(c)
        self.assertEqual(404, r.status)

    def test_corpo_torto_e_400(self):
        c = self.cenario()
        for corpo in ({"maquina_id": "1", "tipo": "reiniciar", "alvo": "x"},
                      {"maquina_id": True, "tipo": "reiniciar", "alvo": "x"},
                      {"maquina_id": c["m"]["id"], "tipo": "publicar",
                       "alvo": "grimoire-web"},
                      {"maquina_id": c["m"]["id"], "tipo": "reiniciar",
                       "alvo": 5},
                      {"maquina_id": c["m"]["id"], "tipo": "reiniciar"},
                      {}):
            r = self.dono("/api/maquinas/ordem/preparar", corpo,
                          sessao=c["sessao"])
            self.assertEqual((400, {"erro": "pedido invalido"}),
                             (r.status, self.json(r)), corpo)

    def test_so_olha_e_409(self):
        c = self.cenario(com_ordens=False)
        r = self.preparar(c)
        self.assertEqual((409, {"motivo": "so_olha"}), (r.status, self.json(r)))

    def test_servidor_sem_nenhuma_medicao_tambem_so_olha(self):
        _segredo, m = self.ligar_servidor()
        r = self.dono("/api/maquinas/ordem/preparar",
                      {"maquina_id": m["id"], "tipo": "reiniciar",
                       "alvo": "grimoire-web"})
        self.assertEqual((409, {"motivo": "so_olha"}), (r.status, self.json(r)))

    def test_medicao_de_181_segundos_e_sem_dados(self):
        c = self.cenario()
        self.envelhecer(c["m"]["id"], 181)
        r = self.preparar(c)
        self.assertEqual((409, {"motivo": "sem_dados"}),
                         (r.status, self.json(r)))

    def test_a_segunda_ordem_e_ocupado(self):
        c = self.cenario()
        self.assertEqual(200, self.preparar(c).status)
        r = self.preparar(c, "voltar", "grimoire")
        self.assertEqual((409, {"motivo": "ocupado"}), (r.status, self.json(r)))

    def test_projeto_bloqueado_por_nome_ou_pelo_rotulo_e_403(self):
        c = self.cenario(sistemas=SISTEMAS + [
            sistema("meu-banco", "Ajudei_Saude")])
        c["chaves"]       # a chave ja esta no cenario
        for tipo, alvo in (("voltar", "ajudei-saude"),
                           ("reiniciar", "ajudei-db"),
                           ("reiniciar", "meu-banco"),
                           ("reiniciar", "Ajudei_Saude"),
                           ("reiniciar", "AJUDEI SAUDE"),
                           ("voltar", "ajudei-saude-web")):
            r = self.preparar(c, tipo, alvo)
            self.assertEqual((403, {"motivo": "bloqueado"}),
                             (r.status, self.json(r)), alvo)

    def test_o_bloqueio_chama_o_helper_unico(self):
        chamadas = []
        real = tarefas.projeto_bloqueado
        c = self.cenario()
        with mock.patch.object(tarefas, "projeto_bloqueado",
                               lambda n: chamadas.append(n) or real(n)):
            self.preparar(c)
        self.assertIn("grimoire-web", chamadas)
        self.assertIn("grimoire", chamadas)         # o rotulo do sistema

    def test_alvo_nao_medido_e_400(self):
        c = self.cenario()
        for tipo, alvo in (("reiniciar", "nao-existe"),
                           ("voltar", "projeto-que-nao-volta"),
                           ("voltar", "grimoire-web"),     # sistema nao e projeto
                           ("reiniciar", "grimoire"),      # projeto nao e sistema
                           ("reiniciar", "a=b"), ("voltar", "Grimoire")):
            r = self.preparar(c, tipo, alvo)
            self.assertEqual((400, {"erro": "pedido invalido"}),
                             (r.status, self.json(r)), alvo)

    def test_sem_chave_que_o_servidor_conheca_e_409(self):
        c = self.cenario()
        self.chave()                # chave nova: o servidor ainda nao a conhece
        con = banco.conectar()
        try:
            con.execute("UPDATE chave_de_acesso SET revogada_em = 'x'"
                        " WHERE cred_id = ?", (c["chaves"][0][2],))
            con.commit()
        finally:
            con.close()
        r = self.preparar(c)
        self.assertEqual((409, {"motivo": "sem_chave"}),
                         (r.status, self.json(r)))

    def test_so_as_chaves_que_o_servidor_conhece_vao_na_resposta(self):
        c = self.cenario()
        nova = self.chave()
        d = self.json(self.preparar(c))
        self.assertEqual([c["chaves"][0][2]], d["chaves"])
        self.assertNotIn(nova[2], d["chaves"])

    def test_o_21o_pedido_e_429_e_nada_mais_trava(self):
        c = self.cenario()
        for i in range(20):
            self.assertIn(self.preparar(c).status, (200, 409), i)
        r = self.preparar(c)
        self.assertEqual((429, RECUSA), (r.status, self.json(r)))
        self.assertEqual(200, self.medir(c["segredo"]).status)
        r = self.pedir("/entrar/chave", "POST", {})
        self.assertNotEqual(429, r.status)

    def test_sem_sessao_e_401_e_sem_token_de_pagina_e_403(self):
        c = self.cenario()
        corpo = {"maquina_id": c["m"]["id"], "tipo": "reiniciar",
                 "alvo": "grimoire-web"}
        self.assertEqual(401, self.pedir(
            "/api/maquinas/ordem/preparar", "POST", corpo).status)
        cookies, _ = self.sessao_e_token()
        r = self.pedir("/api/maquinas/ordem/preparar", "POST", corpo,
                       cookies=cookies, cabecalhos={"X-Token": "errado"})
        self.assertEqual(403, r.status)
        r = self.pedir("/api/maquinas/ordem/preparar", "POST", corpo,
                       cookies=cookies, com_origem=False,
                       cabecalhos={"X-Token": "x"})
        self.assertEqual(403, r.status)


# =================================================== assinar (C7, I4)

class AssinarOPedido(_Base):
    def pronto(self):
        c = self.cenario()
        return c, self.json(self.preparar(c))

    def recusado(self, c, corpo, sessao=None):
        r = self.assinar(c, corpo, sessao=sessao)
        self.assertEqual((401, RECUSA), (r.status, self.json(r)), corpo)

    def test_valido_e_200_e_grava_o_que_o_ajudante_vai_conferir(self):
        c, prep = self.pronto()
        corpo = self.assinatura(prep, c["chaves"][0], contador=7)
        r = self.assinar(c, corpo)
        self.assertEqual((200, {"ok": True}), (r.status, self.json(r)))
        l = self.ordem_no_banco(prep["numero"])
        self.assertIsNotNone(l["assinada_em"])
        self.assertEqual((corpo["cred_id"], corpo["cliente"],
                          corpo["autenticador"], corpo["assinatura"]),
                         (l["cred_id"], l["cliente"], l["autenticador"],
                          l["assinatura"]))
        guardada = banco.chave_de_acesso(c["chaves"][0][2])
        self.assertEqual(7, guardada["contador"])

    def test_a_ordem_ja_assinada_nao_assina_de_novo(self):
        c, prep = self.pronto()
        self.assertEqual(200, self.assinar(
            c, self.assinatura(prep, c["chaves"][0], contador=1)).status)
        self.recusado(c, self.assinatura(prep, c["chaves"][0], contador=2))

    def test_chave_de_outra_conta(self):
        c, prep = self.pronto()
        outro = banco.criar_usuario("outro-%s@teste.local"
                                    % banco.novo_token()[:6])
        alheia = self.chave(outro)
        self.recusado(c, self.assinatura(prep, alheia))

    def test_chave_revogada_na_hora(self):
        c, prep = self.pronto()
        con = banco.conectar()
        try:
            con.execute("UPDATE chave_de_acesso SET revogada_em = 'x'")
            con.commit()
        finally:
            con.close()
        self.recusado(c, self.assinatura(prep, c["chaves"][0]))

    def test_chave_da_conta_que_o_servidor_nao_conhece(self):
        c, prep = self.pronto()
        nova = self.chave()
        self.recusado(c, self.assinatura(prep, nova))

    def test_assinatura_de_outra_chave_privada(self):
        c, prep = self.pronto()
        intrusa, _ = _par_de_chaves()
        self.recusado(c, self.assinatura(prep, c["chaves"][0],
                                         assina_com=intrusa))

    def test_desafio_de_outra_ordem(self):
        c, prep = self.pronto()
        self.recusado(c, self.assinatura(prep, c["chaves"][0],
                                         desafio=os.urandom(32)))

    def test_numero_de_outra_ordem_ou_inexistente(self):
        c, prep = self.pronto()
        for numero in ("f" * 32, "curto", 5, None, "G" * 32):
            self.recusado(c, dict(self.assinatura(prep, c["chaves"][0]),
                                  numero=numero))

    def test_ordem_de_outra_conta_nao_assina(self):
        c, prep = self.pronto()
        outro = banco.criar_usuario("outro-%s@teste.local"
                                    % banco.novo_token()[:6])
        sessao_dele = self.sessao_de(outro)
        self.recusado(c, self.assinatura(prep, c["chaves"][0]),
                      sessao=sessao_dele)
        self.assertIsNone(self.ordem_no_banco(prep["numero"])["assinada_em"])

    def test_origem_fora_do_conjunto(self):
        c, prep = self.pronto()
        self.recusado(c, self.assinatura(prep, c["chaves"][0],
                                         origem="http://phish.example"))

    def test_outro_dominio_sem_uv_e_com_extensao(self):
        c, prep = self.pronto()
        self.recusado(c, self.assinatura(prep, c["chaves"][0],
                                         rp_id="exemplo.net"))
        self.recusado(c, self.assinatura(prep, c["chaves"][0], flags=0x01))
        for flags in (0x45, 0x85):                  # AT e ED ligados
            aut = (hashlib.sha256(b"127.0.0.1").digest()
                   + bytes([flags]) + (1).to_bytes(4, "big"))
            corpo = self.assinatura(prep, c["chaves"][0])
            corpo["autenticador"] = passkey.b64url(aut)
            self.recusado(c, corpo)
        self.assertIsNone(self.ordem_no_banco(prep["numero"])["assinada_em"])

    def test_autenticador_que_nao_tem_37_bytes(self):
        c, prep = self.pronto()
        corpo = self.assinatura(prep, c["chaves"][0])
        longo = passkey.de_b64url(corpo["autenticador"]) + b"\x00"
        self.recusado(c, dict(corpo, autenticador=passkey.b64url(longo)))

    def test_contador_que_nao_sobe(self):
        c, prep = self.pronto()
        banco.usar_chave_de_acesso(
            banco.chave_de_acesso(c["chaves"][0][2])["id"], 9)
        self.recusado(c, self.assinatura(prep, c["chaves"][0], contador=4))
        self.assertIsNone(self.ordem_no_banco(prep["numero"])["assinada_em"])

    def test_ordem_vencida(self):
        c = self.cenario()
        with fixo(T0):
            prep = self.json(self.preparar(c))
        with fixo(T0 + 301):
            self.recusado(c, self.assinatura(prep, c["chaves"][0]))
        with fixo(T0 + 300):
            self.assertEqual(200, self.assinar(
                c, self.assinatura(prep, c["chaves"][0])).status)

    def test_corpo_incompleto_ou_torto(self):
        c, prep = self.pronto()
        bom = self.assinatura(prep, c["chaves"][0])
        for campo in bom:
            self.recusado(c, {k: v for k, v in bom.items() if k != campo})
        self.recusado(c, dict(bom, assinatura="!!!"))
        self.recusado(c, dict(bom, cliente="x" * 5000))

    def test_balcao_proprio_e_o_pedido_continua_vivo(self):
        c, prep = self.pronto()
        for i in range(20):
            self.assertEqual(401, self.assinar(c, {"numero": "x"}).status, i)
        r = self.assinar(c, self.assinatura(prep, c["chaves"][0]))
        self.assertEqual(429, r.status)
        self.assertEqual(200, self.medir(c["segredo"]).status)


# ================================================ o ajudante busca (C8, I3)

class OAjudanteBusca(_Base):
    def test_computador_e_403_antes_do_balcao(self):
        segredo, maq = self.maquina_com_token()
        for _ in range(100):
            cortina.registrar_tentativa("maquina:%d" % maq, time.time(),
                                        balcao="servidor_ordens", teto=10 ** 6)
        for caminho in ("/agente/servidor/ordens",
                        "/agente/servidor/desfecho"):
            r = self.como_maquina(segredo, caminho, {})
            self.assertEqual((403, {"erro": "so servidor"}),
                             (r.status, self.json(r)), caminho)

    def test_sem_token_e_401(self):
        for caminho in ("/agente/servidor/ordens", "/agente/servidor/desfecho"):
            self.assertEqual(401, self.computador(caminho, {}).status)

    def test_sem_json_e_415(self):
        c = self.cenario()
        r = self.pedir("/agente/servidor/ordens", "POST", corpo_cru=b"{}",
                       com_origem=False,
                       cabecalhos={"Authorization": "Token " + c["segredo"],
                                   "Content-Type": "text/plain"})
        self.assertEqual(415, r.status)

    def test_nada_assinado_e_ordem_nula(self):
        c = self.cenario()
        r = self.buscar(c)
        self.assertEqual((200, {"ordem": None}), (r.status, self.json(r)))
        self.preparar(c)                                # preparada, sem assinar
        self.assertEqual({"ordem": None}, self.json(self.buscar(c)))

    def test_assinada_sai_com_os_campos_e_so_uma_vez(self):
        c = self.cenario()
        with fixo(T0):
            prep = self.pedido_assinado(c)
            r = self.buscar(c)
        self.assertEqual(200, r.status, r.corpo)
        ordem = self.json(r)["ordem"]
        self.assertEqual(CAMPOS_DA_ORDEM, set(ordem))
        self.assertEqual((IDENT, "reiniciar", "grimoire-web", prep["numero"],
                          T0, T0 + 300),
                         tuple(ordem[k] for k in ("servidor", "tipo", "alvo",
                                                  "numero", "criado",
                                                  "vence")))
        l = self.ordem_no_banco(prep["numero"])
        self.assertEqual((l["cliente"], l["autenticador"], l["assinatura"]),
                         (ordem["cliente"], ordem["autenticador"],
                          ordem["assinatura"]))
        self.assertIsNotNone(l["entregue_em"])
        self.assertEqual(
            [("servidor", IDENT), ("alvo", "grimoire-web")],
            [(k, ordem[k]) for k in ("servidor", "alvo")])
        with fixo(T0):
            self.assertEqual({"ordem": None}, self.json(self.buscar(c)))

    def test_o_texto_remontado_da_ordem_entregue_e_o_que_foi_assinado(self):
        c = self.cenario()
        with fixo(T0):
            prep = self.pedido_assinado(c, "voltar", "dervs")
            ordem = self.json(self.buscar(c))["ordem"]
        texto = tarefas.texto_da_ordem({k: ordem[k] for k in (
            "servidor", "tipo", "alvo", "numero", "criado", "vence")})
        self.assertEqual(passkey.b64url(hashlib.sha256(
            texto.encode("ascii")).digest()), prep["desafio"])

    def test_assinada_ha_121_segundos_nunca_mais_sai(self):
        c = self.cenario()
        with fixo(T0):
            prep = self.pedido_assinado(c)
        with fixo(T0 + 121):
            self.assertEqual({"ordem": None}, self.json(self.buscar(c)))
        self.assertIsNone(self.ordem_no_banco(prep["numero"])["entregue_em"])

    def test_assinada_ha_120_segundos_ainda_sai(self):
        c = self.cenario()
        with fixo(T0):
            self.pedido_assinado(c)
        with fixo(T0 + 120):
            self.assertIsNotNone(self.json(self.buscar(c))["ordem"])

    def test_ordem_de_outra_maquina_da_mesma_conta_nunca_sai(self):
        a = self.cenario("vps-a")
        b = self.cenario("vps-b", chaves=a["chaves"])
        with fixo(T0):
            prep = self.pedido_assinado(a)
            self.assertEqual({"ordem": None}, self.json(self.buscar(b)))
            self.assertEqual(prep["numero"],
                             self.json(self.buscar(a))["ordem"]["numero"])

    def test_o_91o_pedido_e_429(self):
        c = self.cenario()
        for i in range(90):
            self.assertEqual(200, self.buscar(c).status, i)
        r = self.buscar(c)
        self.assertEqual((429, RECUSA), (r.status, self.json(r)))
        self.assertEqual(200, self.medir(c["segredo"]).status)   # balcao proprio


# ====================================================== o desfecho (C8, I3)

class ODesfecho(_Base):
    def entregue(self):
        c = self.cenario()
        with fixo(T0):
            prep = self.pedido_assinado(c)
            self.assertIsNotNone(self.json(self.buscar(c))["ordem"])
        return c, prep["numero"]

    def desfecho(self, c, numero, desfecho, codigo=None, motivo=None, **mais):
        corpo = {"numero": numero, "desfecho": desfecho, "codigo": codigo,
                 "motivo": motivo}
        corpo.update(mais)
        return self.como_maquina(c["segredo"], "/agente/servidor/desfecho",
                                 corpo)

    def test_cada_combinacao_valida_grava(self):
        casos = (("feita", 0, None), ("falhou", 1, None),
                 ("falhou", 255, None), ("recusada", None, "origem"),
                 ("recusada", None, "teto"), ("nao_sei", None, None))
        for desfecho, codigo, motivo in casos:
            con = banco.conectar()
            try:
                con.execute("DELETE FROM ordem_de_servidor")
                con.commit()
            finally:
                con.close()
            c, numero = self.entregue()
            r = self.desfecho(c, numero, desfecho, codigo, motivo)
            self.assertEqual((200, {"ok": True}), (r.status, self.json(r)),
                             (desfecho, codigo, motivo))
            l = self.ordem_no_banco(numero)
            self.assertEqual((desfecho, codigo, motivo),
                             (l["desfecho"], l["codigo"], l["motivo"]))
            self.assertIsNotNone(l["terminada_em"])

    def test_combinacao_torta_e_400(self):
        c, numero = self.entregue()
        tortas = (("feita", 1, None), ("feita", None, None),
                  ("feita", 0, "origem"), ("falhou", 0, None),
                  ("falhou", 256, None), ("falhou", None, None),
                  ("falhou", 1, "teto"), ("falhou", True, None),
                  ("recusada", None, "xx"), ("recusada", None, None),
                  ("recusada", 1, "origem"), ("nao_sei", 0, None),
                  ("nao_sei", None, "teto"), ("ok", None, None),
                  (None, None, None), ("feita", "0", None))
        for desfecho, codigo, motivo in tortas:
            r = self.desfecho(c, numero, desfecho, codigo, motivo)
            self.assertEqual((400, {"erro": "corpo invalido"}),
                             (r.status, self.json(r)),
                             (desfecho, codigo, motivo))
        for numero_torto in ("curto", 5, None, "G" * 32):
            r = self.desfecho(c, numero_torto, "feita", 0)
            self.assertEqual(400, r.status, numero_torto)
        self.assertEqual(400, self.desfecho(c, numero, "feita", 0,
                                            extra="x").status)
        self.assertIsNone(self.ordem_no_banco(numero)["desfecho"])

    def test_ordem_de_outra_maquina_e_404(self):
        c, numero = self.entregue()
        outra = self.cenario("vps-b", chaves=c["chaves"])
        r = self.desfecho(outra, numero, "feita", 0)
        self.assertEqual((404, NAO_ACHEI), (r.status, self.json(r)))
        self.assertIsNone(self.ordem_no_banco(numero)["desfecho"])

    def test_ordem_nao_entregue_ou_inexistente_e_404(self):
        c = self.cenario()
        with fixo(T0):
            prep = self.pedido_assinado(c)             # assinada, nao entregue
        self.assertEqual(404, self.desfecho(c, prep["numero"], "feita",
                                            0).status)
        self.assertEqual(404, self.desfecho(c, "f" * 32, "feita", 0).status)

    def test_ordem_que_ja_tem_desfecho_e_404(self):
        c, numero = self.entregue()
        self.assertEqual(200, self.desfecho(c, numero, "feita", 0).status)
        r = self.desfecho(c, numero, "falhou", 2)
        self.assertEqual((404, NAO_ACHEI), (r.status, self.json(r)))
        self.assertEqual("feita", self.ordem_no_banco(numero)["desfecho"])

    def test_o_31o_e_429(self):
        c, numero = self.entregue()
        for i in range(30):
            self.assertEqual(404, self.desfecho(c, "f" * 32, "feita", 0).status)
        self.assertEqual(429, self.desfecho(c, numero, "feita", 0).status)
        self.assertEqual(200, self.medir(c["segredo"]).status)


# ======================================================= o painel (C9, I5)

class OQueOPainelMostra(_Base):
    def test_so_olha_tem_ordens_nulo_e_nada_e_reiniciavel(self):
        c = self.cenario(com_ordens=False)
        s = self.servidor_no_painel(c)
        self.assertIn("ordens", s)
        self.assertIsNone(s["ordens"])
        self.assertTrue(s["sistemas"])
        for x in s["sistemas"]:
            self.assertIs(False, x["reiniciavel"], x["nome"])

    def test_sem_dados_tem_ordens_nulo(self):
        c = self.cenario()
        self.envelhecer(c["m"]["id"], 400)
        s = self.servidor_no_painel(c)
        self.assertEqual("sem_dados", s["estado"])
        self.assertIsNone(s["ordens"])
        self.assertTrue(all(x["reiniciavel"] is False for x in s["sistemas"]))

    def test_servidor_pareado_sem_medicao_tem_ordens_nulo(self):
        _segredo, m = self.ligar_servidor()
        s = self.servidor_no_painel({"m": m, "sessao": self.sessao_e_token()})
        self.assertIsNone(s["ordens"])

    def test_reiniciavel_e_bloqueado_por_sistema(self):
        c = self.cenario(sistemas=SISTEMAS + [sistema("ajudei-saude-web")])
        s = self.servidor_no_painel(c)
        por_nome = {x["nome"]: (x["reiniciavel"], x["bloqueado"])
                    for x in s["sistemas"]}
        self.assertEqual({"grimoire-web": (True, False),
                          "dervs-app": (True, False),
                          "ajudei-db": (False, True),
                          "ajudei-saude-web": (False, True)}, por_nome)
        self.assertEqual({"nome", "projeto", "estado", "saude", "desde",
                          "reinicios", "reiniciavel", "bloqueado"},
                         set(s["sistemas"][0]))

    def test_o_bloco_com_chaves_ok_e_linha_em_dia(self):
        c = self.cenario()
        o = self.servidor_no_painel(c)["ordens"]
        self.assertEqual({"chaves_ok": True, "linha_velha": False,
                          "voltaveis": ["dervs", "grimoire"], "pedidos": []},
                         o)

    def test_chaves_ok_falso_sem_chave_viva_conhecida(self):
        c = self.cenario()
        con = banco.conectar()
        try:
            con.execute("UPDATE chave_de_acesso SET revogada_em = 'x'")
            con.commit()
        finally:
            con.close()
        o = self.servidor_no_painel(c)["ordens"]
        # o servidor ainda conhece 1 chave e a conta tem 0: a linha esta velha
        self.assertEqual((False, True), (o["chaves_ok"], o["linha_velha"]))

    def test_linha_velha_com_uma_chave_nova_e_com_uma_removida(self):
        c = self.cenario()
        self.assertIs(False, self.servidor_no_painel(c)["ordens"]["linha_velha"])
        nova = self.chave()
        o = self.servidor_no_painel(c)["ordens"]
        self.assertEqual((True, True), (o["chaves_ok"], o["linha_velha"]))
        con = banco.conectar()
        try:
            con.execute("UPDATE chave_de_acesso SET revogada_em = 'x'"
                        " WHERE cred_id = ?", (nova[2],))
            con.commit()
        finally:
            con.close()
        self.assertIs(False, self.servidor_no_painel(c)["ordens"]["linha_velha"])
        con = banco.conectar()
        try:
            con.execute("UPDATE chave_de_acesso SET revogada_em = 'x'"
                        " WHERE cred_id = ?", (c["chaves"][0][2],))
            con.commit()
        finally:
            con.close()
        o = self.servidor_no_painel(c)["ordens"]
        self.assertEqual((False, True), (o["chaves_ok"], o["linha_velha"]))

    def test_voltaveis_nunca_leva_projeto_bloqueado(self):
        c = self.cenario()
        con = banco.conectar()
        try:      # um dado de antes da trava, ou gravado por fora
            dados = json.loads(con.execute(
                "SELECT dados FROM medicao_de_servidor WHERE maquina_id = ?",
                (c["m"]["id"],)).fetchone()[0])
            dados["ordens"]["voltaveis"].append("ajudei-saude")
            con.execute("UPDATE medicao_de_servidor SET dados = ?"
                        " WHERE maquina_id = ?",
                        (json.dumps(dados), c["m"]["id"]))
            con.commit()
        finally:
            con.close()
        self.assertEqual(["dervs", "grimoire"],
                         self.servidor_no_painel(c)["ordens"]["voltaveis"])

    # ---- os 8 estados de `pedidos`, com o relogio preso
    def inserir(self, c, numero, tipo="reiniciar", alvo="grimoire-web", *,
                assinada=None, entregue=None, terminada=None, desfecho=None,
                codigo=None, motivo=None):
        iso = lambda s: None if s is None else banco._iso_de(s)
        con = banco.conectar()
        try:
            con.execute(
                "INSERT INTO ordem_de_servidor (numero, usuario_id,"
                " maquina_id, ident, tipo, alvo, criado, vence, assinada_em,"
                " entregue_em, terminada_em, desfecho, codigo, motivo)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (numero, self.uid, c["m"]["id"], IDENT, tipo, alvo, T0 - 100,
                 T0 + 200, iso(assinada), iso(entregue), iso(terminada),
                 desfecho, codigo, motivo))
            con.commit()
        finally:
            con.close()

    def pedidos(self, c):
        with fixo(T0):
            return self.servidor_no_painel(c)["ordens"]["pedidos"]

    def test_cada_estado_com_o_carimbo_certo(self):
        c = self.cenario()
        n = lambda i: "%032x" % i
        casos = [
            # (estado, carimbo esperado, campos)
            ("enviado", T0 - 120, dict(assinada=T0 - 120)),
            ("nao_pegou", T0 - 121, dict(assinada=T0 - 121)),
            ("fazendo", T0 - 1800, dict(assinada=T0 - 1900,
                                        entregue=T0 - 1800)),
            ("sem_resposta", T0 - 1801, dict(assinada=T0 - 1900,
                                             entregue=T0 - 1801)),
            ("feito", T0 - 5, dict(assinada=T0 - 60, entregue=T0 - 30,
                                   terminada=T0 - 5, desfecho="feita",
                                   codigo=0)),
            ("nao_deu", T0 - 5, dict(assinada=T0 - 60, entregue=T0 - 30,
                                     terminada=T0 - 5, desfecho="falhou",
                                     codigo=3)),
            ("recusado", T0 - 5, dict(assinada=T0 - 60, entregue=T0 - 30,
                                      terminada=T0 - 5, desfecho="recusada",
                                      motivo="teto")),
            ("nao_sei", T0 - 5, dict(assinada=T0 - 60, entregue=T0 - 30,
                                     terminada=T0 - 5, desfecho="nao_sei")),
        ]
        for i, (estado, quando, campos) in enumerate(casos, 1):
            con = banco.conectar()
            try:
                con.execute("DELETE FROM ordem_de_servidor")
                con.commit()
            finally:
                con.close()
            self.inserir(c, n(i), **campos)
            p, = self.pedidos(c)
            self.assertEqual(estado, p["estado"], estado)
            self.assertEqual(banco._iso_de(quando), p["quando"], estado)
            self.assertEqual({"numero", "tipo", "alvo", "estado", "quando",
                              "codigo", "motivo"}, set(p))
            # `codigo` so no nao_deu e `motivo` so no recusado (I5)
            self.assertEqual(
                (campos["codigo"] if estado == "nao_deu" else None,
                 campos["motivo"] if estado == "recusado" else None),
                (p["codigo"], p["motivo"]), estado)

    def test_nunca_feito_sem_o_desfecho_do_ajudante(self):
        c = self.cenario()
        # terminada_em preenchida, mas o ajudante nunca contou: nao e "feito"
        self.inserir(c, "%032x" % 1, assinada=T0 - 60, entregue=T0 - 30,
                     terminada=T0 - 5)
        p, = self.pedidos(c)
        self.assertEqual("fazendo", p["estado"])
        self.assertNotEqual("feito", p["estado"])

    def test_as_cinco_mais_novas_assinadas_e_so_as_assinadas(self):
        c = self.cenario()
        for i in range(1, 8):
            self.inserir(c, "%032x" % i, assinada=T0 - 1000 + i)
        self.inserir(c, "%032x" % 99)                       # so preparada
        self.assertEqual(["%032x" % i for i in (7, 6, 5, 4, 3)],
                         [p["numero"] for p in self.pedidos(c)])

    def test_pedidos_de_outra_conta_nao_aparecem(self):
        outro = banco.criar_usuario("outro-%s@teste.local"
                                    % banco.novo_token()[:6])
        sessao_dele = self.sessao_de(outro)
        dele = self.cenario("vps-dele", sessao=sessao_dele,
                            chaves=[self.chave(outro)], uid=outro)
        con = banco.conectar()
        try:
            con.execute(
                "INSERT INTO ordem_de_servidor (numero, usuario_id,"
                " maquina_id, ident, tipo, alvo, criado, vence, assinada_em)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                ("%032x" % 5, outro, dele["m"]["id"], IDENT, "reiniciar",
                 "x", T0, T0 + 300, banco._iso_de(T0)))
            con.commit()
        finally:
            con.close()
        c = self.cenario()
        self.assertEqual([], self.pedidos(c))
        with fixo(T0):
            visto = self.servidor_no_painel(dele, sessao=sessao_dele)
        self.assertEqual(1, len(visto["ordens"]["pedidos"]))

    def test_montar_estado_nao_muda(self):
        self.cenario()
        e = banco.montar_estado(usuario_id=self.uid)
        self.assertNotIn("servidores_ligados", e)
        self.assertNotIn("ordens", json.dumps(e))


if __name__ == "__main__":
    unittest.main(verbosity=0)
