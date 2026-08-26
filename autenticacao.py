# -*- coding: utf-8 -*-
"""Quem e voce: o caminho do GitHub, e a sessao que sai dele.

O DERVS nao guarda senha no caminho normal. Quem confere identidade e o GitHub,
que ja obriga segundo fator na conta — identidade e segundo fator acontecem no
mesmo passo, e essa e uma decisao de confianca declarada em
docs/superpowers/specs/2026-08-26-login-cortina-github-design.md.

O que sobra para este modulo e conferir se aquela identidade esta na tabela
`credencial`. Nao esta, e nunca esteve, na mao de quem chega: conta so nasce
pelo comando `convidar`, rodado por quem tem acesso a maquina.

Este arquivo nao desenha HTML e nao conhece a cortina. Recebe `abrir` no lugar
de `urllib.request.urlopen` para que o teste nunca toque a rede.
"""
from __future__ import annotations

import hmac
import json
import secrets
import sys
import urllib.parse
import urllib.request

import banco

AUTORIZAR = "https://github.com/login/oauth/authorize"
TROCAR = "https://github.com/login/oauth/access_token"
EU = "https://api.github.com/user"
QUEM = "https://api.github.com/users/"

# GitHub fora do ar nao pode segurar uma linha de execucao do servidor para
# sempre.
ESPERA = 10
HORAS_DE_SESSAO = 12
_CABECALHO = {"Accept": "application/vnd.github+json", "User-Agent": "dervs"}


class ErroDoGithub(Exception):
    pass


def novo_state() -> str:
    """Valor de uso unico que amarra a ida ao GitHub com a volta.

    Sem ele, um site qualquer consegue mandar o navegador de volta com um
    `code` de OUTRA conta e entrar como ela.
    """
    return secrets.token_urlsafe(24)


def url_de_autorizacao(client_id: str, redirect_uri: str, state: str) -> str:
    # `scope` vazio de proposito: o DERVS quer saber QUEM e, e mais nada. Nao
    # pede para ler repositorio nem para escrever, entao um token roubado deste
    # fluxo nao serve para nada no GitHub.
    return AUTORIZAR + "?" + urllib.parse.urlencode({
        "client_id": client_id, "redirect_uri": redirect_uri,
        "state": state, "scope": "", "allow_signup": "false"})


def trocar_code(code: str, client_id: str, client_secret: str, abrir=None) -> str:
    """Troca o codigo de uso unico por um token, de servidor para servidor."""
    abrir = abrir or urllib.request.urlopen
    corpo = urllib.parse.urlencode({
        "client_id": client_id, "client_secret": client_secret,
        "code": code}).encode("utf-8")
    # No CORPO, nunca na URL: url vai parar em log de proxy e em historico.
    req = urllib.request.Request(TROCAR, data=corpo, headers=dict(
        _CABECALHO, Accept="application/json"))
    with abrir(req, timeout=ESPERA) as r:
        resposta = json.loads(r.read().decode("utf-8"))
    token = resposta.get("access_token")
    if not token:
        # NAO ponha `resposta` inteira na mensagem: em alguns erros o OAuth
        # devolve de volta o que foi enviado, e mensagem de excecao vai para
        # log. So o campo `error`, que e um codigo curto e publico.
        raise ErroDoGithub("o GitHub nao devolveu token: %s"
                           % resposta.get("error", "sem motivo"))
    return token


def identidade(token: str, abrir=None) -> dict:
    """Quem e o dono do token. `2fa` vem None quando o GitHub nao diz."""
    abrir = abrir or urllib.request.urlopen
    req = urllib.request.Request(EU, headers=dict(
        _CABECALHO, Authorization="Bearer " + token))
    with abrir(req, timeout=ESPERA) as r:
        u = json.loads(r.read().decode("utf-8"))
    return {"id": str(u.get("id") or ""), "login": u.get("login") or "",
            "2fa": u.get("two_factor_authentication")}


def entrar_por_github(code, state, state_esperado, con, client_id,
                      client_secret, abrir=None):
    """Devolve o cookie da sessao, ou None. NUNCA diz por que falhou.

    Motivo diferente por causa diferente e o que transforma uma tela de login
    numa lista de quem existe: "essa conta nao esta autorizada" ja confirma que
    a conta existe.
    """
    if not state or not state_esperado or not hmac.compare_digest(
            str(state), str(state_esperado)):
        return None
    token = None
    try:
        token = trocar_code(code, client_id, client_secret, abrir=abrir)
        quem = identidade(token, abrir=abrir)
    except (ErroDoGithub, OSError, ValueError, KeyError):
        return None
    finally:
        # O token do GitHub morre aqui. Nao vai ao banco, nao vai a log, e nao
        # e devolvido a quem chamou.
        token = None
    if not quem["id"]:
        return None
    if quem["2fa"] is False:
        # So barra quando o GitHub AFIRMA que nao ha segundo fator. Campo
        # ausente cai na decisao declarada na spec.
        return None
    usuario = banco.usuario_por_github(quem["id"], con=con)
    if not usuario:
        return None

    cookie = banco.novo_token()
    banco.abrir_sessao(usuario["id"], cookie,
                       banco.prazo(HORAS_DE_SESSAO * 3600), con=con)
    # `cookie_novo` NAO e opcional fora de teste: `banco.confirmar_segundo_fator`
    # documenta que passar vazio MANTEM o identificador, e identificador igual
    # antes e depois de autenticar e o que faz fixacao de sessao funcionar. Aqui
    # o cookie nasce nesta funcao e nao houve "antes", entao a fixacao nem se
    # aplica — mas rotacionar custa uma linha e mantem o contrato do modulo
    # valendo para quem ler depois.
    final = banco.confirmar_segundo_fator(cookie, banco.novo_token(), con=con)
    con.execute("UPDATE credencial SET usado_em = ?"
                " WHERE tipo = 'github' AND identificador = ?",
                (banco.agora(), quem["id"]))
    con.commit()
    return final


# ---------------------------------------------------------------- o convite
#
# A UNICA porta para criar conta, e ela nao passa pela web. E de proposito que
# criar conta custe um comando de quem tem acesso a maquina: e isso que mantem
# o cadastro fechado sem precisar de uma lista de convidados em lugar nenhum.

def convidar(login: str, email: str, con=None, abrir=None) -> int:
    """Cria conta e amarra ao id NUMERICO do GitHub. Devolve o id da conta."""
    abrir = abrir or urllib.request.urlopen
    req = urllib.request.Request(
        QUEM + urllib.parse.quote((login or "").strip()), headers=_CABECALHO)
    with abrir(req, timeout=ESPERA) as r:
        u = json.loads(r.read().decode("utf-8"))
    if not u.get("id"):
        raise ErroDoGithub("login do GitHub nao encontrado: %s" % login)
    fechar = con is None
    con = con or banco.conectar()
    try:
        uid = banco.criar_usuario(email, nome=u.get("name") or login, con=con)
        banco.ligar_github(uid, str(u["id"]), con=con)
        return uid
    finally:
        if fechar:
            con.close()


USO = """uso: python autenticacao.py convidar <login-do-github> <email>

Cria a conta e a amarra ao id numerico do GitHub. Nao ha caminho pela web.
"""


def main(argv) -> int:
    if len(argv) == 4 and argv[1] == "convidar":
        uid = convidar(argv[2], argv[3])
        print("conta criada: %s (id %d)" % (argv[3], uid))
        return 0
    sys.stderr.write(USO)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
