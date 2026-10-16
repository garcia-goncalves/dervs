# -*- coding: utf-8 -*-
"""A linha com pedidos só sai depois de um toque, e leva só a chave tocada.

MOTIVO (2a revisao de seguranca da entrega C, 16/10/2026): cadastrar chave de
acesso pede so sessao + CSRF, e `GET /api/ajudante/linha` punha na linha com
pedidos as 5 chaves vivas mais novas da conta. Quem roubasse a sessao
cadastrava a propria chave e esperava o dono colar a linha na VPS: dai em
diante reiniciava e voltava versoes sem toque do dono. Plano e decisao:
docs/superpowers/plans/dervs-linha-com-toque.md.

O fecho: a chave do intruso mora no aparelho DELE. O toque do dono so sai da
chave do dono, e a linha leva aquela chave e nenhuma outra.

    python test_linha_com_toque.py
"""
from __future__ import annotations

import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("DERVS_AMBIENTE", "local")
os.environ.setdefault("DERVS_COFRE",
                      "chave-de-teste-que-nao-e-segredo-nenhum-0123456789")

import banco      # noqa: E402
import passkey    # noqa: E402
import servir     # noqa: E402
from test_ordens_servidor import _Base  # noqa: E402
from test_passkey import (_assinar, _client_data,  # noqa: E402
                          _dados_do_autenticador)

DESAFIO = "/api/ajudante/linha/desafio"
PEDIDOS = "/api/ajudante/linha/pedidos"


class _Linha(_Base):
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
        self.sessao = self.sessao_e_token()

    @staticmethod
    def forma(chave):
        return "%064x.%064x" % chave[1]

    def linha_so_olhar(self):
        r = self.pedir("/api/ajudante/linha", cookies=self.sessao[0])
        self.assertEqual(200, r.status, r.corpo)
        return self.json(r)

    def desafio(self, sessao=None):
        """(resposta, cookies para o passo seguinte: a sessao + o bilhete)."""
        sessao = sessao or self.sessao
        r = self.dono(DESAFIO, {}, sessao=sessao)
        cookies = dict(sessao[0])
        if "desafio" in r.cookies:
            cookies["desafio"] = r.cookies["desafio"]
        return r, cookies

    def toque(self, chave, d, flags=0x05, origem=None, contador=1):
        privada, _publica, cred = chave
        cliente = _client_data("webauthn.get", passkey.de_b64url(d["desafio"]),
                               origem=origem or self.origem())
        aut = _dados_do_autenticador(rp_id="127.0.0.1", flags=flags,
                                     contador=contador)
        sig = _assinar(privada, aut + hashlib.sha256(cliente).digest())
        return {"cred_id": cred, "cliente": passkey.b64url(cliente),
                "autenticador": passkey.b64url(aut),
                "assinatura": passkey.b64url(sig)}

    def pedidos(self, corpo, cookies, csrf=None):
        return self.pedir(PEDIDOS, "POST", corpo, cookies=cookies,
                          cabecalhos={"X-Token": csrf or self.sessao[1]})

    def tocar(self, chave, **k):
        r, cookies = self.desafio()
        self.assertEqual(200, r.status, r.corpo)
        return self.pedidos(self.toque(chave, self.json(r), **k), cookies)


class ALinhaSemToqueNaoLevaChaveNenhuma(_Linha):
    def test_a_linha_so_olhar_e_os_campos_exatos(self):
        self.chave(apelido="PIN do Windows")
        d = self.linha_so_olhar()
        self.assertEqual({"linha", "sha256", "endereco", "tem_chave"}, set(d))
        self.assertTrue(d["tem_chave"])
        self.assertNotIn("--ordens", d["linha"])
        self.assertTrue(d["linha"].endswith("sudo python3 -I dervs-ajudante.py"))

    def test_sem_chave_viva_tem_chave_e_falso(self):
        self.assertFalse(self.linha_so_olhar()["tem_chave"])

    def test_chave_so_de_outra_conta_nao_conta(self):
        outro = banco.criar_usuario("outro-%s@teste.local"
                                    % banco.novo_token()[:6])
        self.chave(uid=outro)
        self.assertFalse(self.linha_so_olhar()["tem_chave"])


class ODesafio(_Linha):
    def test_exige_sessao(self):
        self.assertEqual(401, self.pedir(DESAFIO, "POST", {}).status)

    def test_exige_o_anti_csrf(self):
        r = self.pedir(DESAFIO, "POST", {}, cookies=self.sessao[0])
        self.assertEqual(403, r.status)

    def test_lista_so_as_chaves_vivas_da_conta(self):
        minha = self.chave(apelido="minha")
        velha = self.chave(apelido="velha")
        outro = banco.criar_usuario("outro-%s@teste.local"
                                    % banco.novo_token()[:6])
        alheia = self.chave(uid=outro)
        con = banco.conectar()
        try:
            con.execute("UPDATE chave_de_acesso SET revogada_em = 'x'"
                        " WHERE cred_id = ?", (velha[2],))
            con.commit()
        finally:
            con.close()
        r, cookies = self.desafio()
        self.assertEqual(200, r.status, r.corpo)
        d = self.json(r)
        self.assertEqual({"desafio", "rp_id", "chaves", "segundos"}, set(d))
        self.assertEqual([minha[2]], d["chaves"])
        self.assertNotIn(alheia[2], d["chaves"])
        self.assertIn("desafio", cookies)


class OToqueDaALinhaComSoAChaveTocada(_Linha):
    def test_o_toque_do_dono_poe_so_a_chave_dele(self):
        dono = self.chave(apelido="PIN do Windows")
        intruso = self.chave(apelido="iPhone")      # cadastrada com a sessao roubada
        r = self.tocar(dono)
        self.assertEqual(200, r.status, r.corpo)
        d = self.json(r)
        self.assertEqual({"linha_com_ordens", "chave"}, set(d))
        self.assertEqual(self.linha_so_olhar()["linha"] + " instalar --ordens " + self.forma(dono),
                         d["linha_com_ordens"])
        self.assertNotIn(self.forma(intruso), d["linha_com_ordens"])
        self.assertEqual("PIN do Windows", d["chave"]["apelido"])
        self.assertTrue(d["chave"]["criado_em"])

    def test_o_toque_avanca_o_contador_da_chave(self):
        dono = self.chave()
        self.assertEqual(200, self.tocar(dono, contador=7).status)
        self.assertEqual(7, banco.chave_de_acesso(dono[2])["contador"])

    def test_o_desafio_vale_uma_vez_so(self):
        dono = self.chave()
        r, cookies = self.desafio()
        corpo = self.toque(dono, self.json(r))
        self.assertEqual(200, self.pedidos(corpo, cookies).status)
        self.assertEqual(401, self.pedidos(corpo, cookies).status)

    def test_sem_o_bilhete_do_desafio_e_recusado(self):
        dono = self.chave()
        r, cookies = self.desafio()
        corpo = self.toque(dono, self.json(r))
        cookies.pop("desafio")
        self.assertEqual(401, self.pedidos(corpo, cookies).status)

    def test_chave_de_outra_conta_e_recusada(self):
        outro = banco.criar_usuario("outro-%s@teste.local"
                                    % banco.novo_token()[:6])
        alheia = self.chave(uid=outro)
        self.chave()
        self.assertEqual(401, self.tocar(alheia).status)

    def test_chave_revogada_e_recusada(self):
        dono = self.chave()
        con = banco.conectar()
        try:
            con.execute("UPDATE chave_de_acesso SET revogada_em = 'x'"
                        " WHERE cred_id = ?", (dono[2],))
            con.commit()
        finally:
            con.close()
        self.assertEqual(401, self.tocar(dono).status)

    def test_sem_verificar_a_pessoa_e_recusado(self):
        """UP sem UV: tocou, mas sem PIN nem digital."""
        self.assertEqual(401, self.tocar(self.chave(), flags=0x01).status)

    def test_de_outro_site_e_recusado(self):
        r = self.tocar(self.chave(), origem="https://dervs.com.br.golpe.example")
        self.assertEqual(401, r.status)

    def test_exige_o_anti_csrf(self):
        dono = self.chave()
        r, cookies = self.desafio()
        corpo = self.toque(dono, self.json(r))
        r2 = self.pedir(PEDIDOS, "POST", corpo, cookies=cookies)
        self.assertEqual(403, r2.status)


if __name__ == "__main__":
    unittest.main()
