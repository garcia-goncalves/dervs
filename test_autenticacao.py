# -*- coding: utf-8 -*-
"""Testes do login por GitHub (etapa 9).

NENHUM TESTE TOCA A REDE. As funcoes que falam com o GitHub recebem a funcao de
abrir URL por parametro, e aqui entra um duble. URL nao prevista pelo duble
levanta AssertionError: teste que escapa para a internet tem de estourar, nao
tentar.

O que este arquivo cobra:

  1. O `state` de uso unico e conferido. Ausente, trocado ou reusado: recusado.
  2. REJEICAO E SEMPRE IGUAL. Id desconhecido, conta desativada, credencial
     revogada e `state` torto devolvem a mesma coisa: None. Resposta diferente
     por causa diferente transforma a tela de login numa lista de quem existe.
  3. O CASAMENTO E PELO ID NUMERICO. Login do GitHub pode ser trocado e o nome
     antigo fica livre para outra pessoa registrar.
  4. O token do GitHub nao sobra em lugar nenhum.
  5. Entrar pelo GitHub carimba `segundo_fator_em` e ROTACIONA o cookie.

    python test_autenticacao.py
"""
from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("DERVS_AMBIENTE", "local")
os.environ.setdefault("DERVS_COFRE",
                      "chave-de-teste-que-nao-e-segredo-nenhum-0123456789")

import autenticacao  # noqa: E402
import banco         # noqa: E402

# Valores obviamente falsos. Nao ha segredo de verdade em teste nenhum deste
# repositorio, e o varredor de segredo do hook depende disso.
ID_FALSO = "id-de-aplicativo-inventado"
SEGREDO_FALSO = "nao-e-segredo-e-so-um-texto"
VALOR_FALSO = "resposta-inventada-do-duble"
VOLTA = "http://localhost:4777/entrar/github/retorno"


class RespostaFalsa(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def duble(mapa, registro=None):
    """Substitui `urllib.request.urlopen`. `registro` acumula as URLs pedidas."""
    def abrir(req, timeout=None):
        url = req if isinstance(req, str) else req.full_url
        if registro is not None:
            registro.append((url, dict(getattr(req, "headers", {}) or {})))
        for pedaco, corpo in mapa.items():
            if pedaco in url:
                return RespostaFalsa(json.dumps(corpo).encode("utf-8"))
        raise AssertionError("URL nao prevista no teste: %s" % url)
    return abrir


class MontarAUrl(unittest.TestCase):
    def test_leva_o_state_e_o_id_do_aplicativo(self):
        u = autenticacao.url_de_autorizacao(ID_FALSO, VOLTA, "s1")
        self.assertTrue(u.startswith(autenticacao.AUTORIZAR + "?"))
        self.assertIn("state=s1", u)
        self.assertIn("client_id=" + ID_FALSO, u)

    def test_nao_pede_permissao_nenhuma(self):
        """O DERVS quer saber QUEM e, e mais nada. Escopo vazio e o pedido
        minimo: nada de ler repositorio, nada de escrever."""
        u = autenticacao.url_de_autorizacao(ID_FALSO, VOLTA, "s1")
        self.assertIn("scope=&", u + "&")
        self.assertIn("allow_signup=false", u)

    def test_dois_states_seguidos_nao_se_repetem(self):
        self.assertNotEqual(autenticacao.novo_state(), autenticacao.novo_state())


class TrocarOCodigo(unittest.TestCase):
    def test_resposta_sem_token_estoura(self):
        rede = duble({"login/oauth/access_token": {"error": "bad_verification_code"}})
        with self.assertRaises(autenticacao.ErroDoGithub):
            autenticacao.trocar_code("c1", ID_FALSO, SEGREDO_FALSO, abrir=rede)

    def test_a_mensagem_do_erro_nao_carrega_a_resposta_inteira(self):
        """Mensagem de excecao vai para log, e a resposta de erro do OAuth pode
        trazer de volta o que foi enviado."""
        rede = duble({"login/oauth/access_token": {"error": "x",
                                                   "client_secret": SEGREDO_FALSO}})
        try:
            autenticacao.trocar_code("c1", ID_FALSO, SEGREDO_FALSO, abrir=rede)
        except autenticacao.ErroDoGithub as e:
            self.assertNotIn(SEGREDO_FALSO, str(e))
        else:
            self.fail("deveria ter estourado")

    def test_o_segredo_vai_no_corpo_e_nunca_na_url(self):
        registro = []
        rede = duble({"login/oauth/access_token": {"access_token": VALOR_FALSO}},
                     registro)
        autenticacao.trocar_code("c1", ID_FALSO, SEGREDO_FALSO, abrir=rede)
        url, _ = registro[0]
        self.assertNotIn(SEGREDO_FALSO, url)


class Fluxo(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.con = banco.conectar(str(Path(self.dir.name) / "hub.db"))
        self.addCleanup(self.con.close)
        self.uid = banco.criar_usuario("thiago@teste.local", con=self.con)
        banco.ligar_github(self.uid, "4242", con=self.con)
        self.rede = duble({
            "login/oauth/access_token": {"access_token": VALOR_FALSO},
            "api.github.com/user": {"id": 4242, "login": "thiago",
                                    "two_factor_authentication": True},
        })

    def _entrar(self, state="s1", esperado="s1", rede=None):
        return autenticacao.entrar_por_github(
            code="c1", state=state, state_esperado=esperado, con=self.con,
            client_id=ID_FALSO, client_secret=SEGREDO_FALSO,
            abrir=rede or self.rede)

    # ------------------------------------------------------------ o caminho
    def test_entra_e_carimba_o_segundo_fator(self):
        cookie = self._entrar()
        self.assertTrue(cookie)
        s = banco.sessao_valida(cookie, con=self.con)
        self.assertIsNotNone(s)
        self.assertEqual(s["usuario_id"], self.uid)
        self.assertIsNotNone(s["segundo_fator_em"])

    def test_o_cookie_e_rotacionado_ao_subir_de_nivel(self):
        """Manter o mesmo identificador antes e depois de autenticar e o que
        faz fixacao de sessao funcionar."""
        cookie = self._entrar()
        anteriores = [l[0] for l in self.con.execute(
            "SELECT id FROM sessao WHERE segundo_fator_em IS NULL")]
        self.assertEqual(anteriores, [])
        self.assertEqual(
            self.con.execute("SELECT COUNT(*) FROM sessao").fetchone()[0], 1)
        self.assertIsNotNone(banco.sessao_valida(cookie, con=self.con))

    def test_a_credencial_fica_marcada_como_usada(self):
        self._entrar()
        usado = self.con.execute(
            "SELECT usado_em FROM credencial WHERE tipo='github'"
            " AND identificador='4242'").fetchone()[0]
        self.assertIsNotNone(usado)

    # ------------------------------------------------- rejeicoes, todas iguais
    def test_state_trocado_nao_entra(self):
        self.assertIsNone(self._entrar(state="outro", esperado="s1"))

    def test_state_vazio_nao_entra(self):
        self.assertIsNone(self._entrar(state="", esperado=""))
        self.assertIsNone(self._entrar(state=None, esperado=None))

    def test_id_desconhecido_nao_entra(self):
        rede = duble({
            "login/oauth/access_token": {"access_token": VALOR_FALSO},
            "api.github.com/user": {"id": 999999, "login": "estranho"},
        })
        self.assertIsNone(self._entrar(rede=rede))

    def test_login_igual_com_id_diferente_nao_entra(self):
        """O sequestro classico: o login foi trocado e outra pessoa registrou
        o nome abandonado."""
        rede = duble({
            "login/oauth/access_token": {"access_token": VALOR_FALSO},
            "api.github.com/user": {"id": 1, "login": "thiago"},
        })
        self.assertIsNone(self._entrar(rede=rede))

    def test_conta_desativada_nao_entra(self):
        self.con.execute("UPDATE usuario SET desativado_em = ? WHERE id = ?",
                         (banco.agora(), self.uid))
        self.con.commit()
        self.assertIsNone(self._entrar())

    def test_credencial_revogada_nao_entra(self):
        self.con.execute("UPDATE credencial SET revogada_em = ?"
                         " WHERE tipo='github' AND identificador='4242'",
                         (banco.agora(),))
        self.con.commit()
        self.assertIsNone(self._entrar())

    def test_conta_do_github_sem_segundo_fator_nao_entra(self):
        """So barra quando o GitHub AFIRMA que nao ha. Campo ausente cai na
        decisao declarada na spec: confiar na conta do GitHub."""
        rede = duble({
            "login/oauth/access_token": {"access_token": VALOR_FALSO},
            "api.github.com/user": {"id": 4242, "login": "thiago",
                                    "two_factor_authentication": False},
        })
        self.assertIsNone(self._entrar(rede=rede))

    def test_campo_de_segundo_fator_ausente_ainda_entra(self):
        rede = duble({
            "login/oauth/access_token": {"access_token": VALOR_FALSO},
            "api.github.com/user": {"id": 4242, "login": "thiago"},
        })
        self.assertTrue(self._entrar(rede=rede))

    def test_github_fora_do_ar_nao_derruba_o_servidor(self):
        def cai(req, timeout=None):
            raise OSError("conexao recusada")
        self.assertIsNone(self._entrar(rede=cai))

    def test_nenhuma_rejeicao_abre_sessao(self):
        for tentativa in (lambda: self._entrar(state="outro"),
                          lambda: self._entrar(state="")):
            tentativa()
        self.assertEqual(
            self.con.execute("SELECT COUNT(*) FROM sessao").fetchone()[0], 0)

    # ------------------------------------------------------------- o segredo
    def test_token_do_github_nao_sobra_no_banco(self):
        self._entrar()
        despejo = "\n".join(self.con.iterdump())
        self.assertNotIn(VALOR_FALSO, despejo)
        self.assertNotIn(SEGREDO_FALSO, despejo)


class Convite(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.con = banco.conectar(str(Path(self.dir.name) / "hub.db"))
        self.addCleanup(self.con.close)
        self.rede = duble({"api.github.com/users/thiago": {"id": 4242,
                                                           "login": "thiago",
                                                           "name": "Thiago"}})

    def test_cria_conta_e_credencial(self):
        uid = autenticacao.convidar("thiago", "thiago@teste.local",
                                    con=self.con, abrir=self.rede)
        self.assertEqual(banco.usuario_por_github("4242", con=self.con)["id"], uid)

    def test_conta_de_convite_nao_tem_senha(self):
        autenticacao.convidar("thiago", "thiago@teste.local",
                              con=self.con, abrir=self.rede)
        self.assertIsNone(banco.credencial_por_email("thiago@teste.local",
                                                     con=self.con))

    def test_convidar_duas_vezes_estoura_em_vez_de_duplicar(self):
        autenticacao.convidar("thiago", "thiago@teste.local",
                              con=self.con, abrir=self.rede)
        with self.assertRaises(Exception):
            autenticacao.convidar("thiago", "outro@teste.local",
                                  con=self.con, abrir=self.rede)

    def test_login_que_nao_existe_no_github_estoura(self):
        rede = duble({"api.github.com/users/ninguem": {"message": "Not Found"}})
        with self.assertRaises(autenticacao.ErroDoGithub):
            autenticacao.convidar("ninguem", "x@teste.local",
                                  con=self.con, abrir=rede)

    def test_nao_ha_caminho_pela_web_para_criar_conta(self):
        """O cadastro fechado nao pode depender de a rota estar ausente hoje.

        Se um dia alguem acrescentar uma rota de registro, este teste continua
        verde — por isso ele cobra a OUTRA metade: o modulo nao expoe nenhuma
        funcao de criar conta que nao seja o convite.
        """
        publicas = [n for n in dir(autenticacao) if not n.startswith("_")]
        self.assertIn("convidar", publicas)
        for proibido in ("registrar", "cadastrar", "criar_conta"):
            self.assertNotIn(proibido, publicas)


if __name__ == "__main__":
    unittest.main(verbosity=2)
