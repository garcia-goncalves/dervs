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

import http.client
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
# Teto do que se le de fora. A resposta do GitHub aqui tem alguns KiB; sem teto,
# quem conseguir se pos no meio manda um corpo infinito e a memoria acaba.
TETO_DA_RESPOSTA = 64 * 1024
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
        resposta = json.loads(r.read(TETO_DA_RESPOSTA).decode("utf-8"))
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
        u = json.loads(r.read(TETO_DA_RESPOSTA).decode("utf-8"))
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
    try:
        # O token do GitHub nao e gravado, nao e registrado em log e nao volta
        # para quem chamou: ele vive so nas duas linhas abaixo. NAO da para
        # apaga-lo da memoria em CPython — uma versao anterior deste codigo tinha
        # um `finally: token = None` com um comentario dizendo que "o token morre
        # aqui", e isso era falso: reatribuir a variavel local nao toca o texto
        # no heap, que fica ate o coletor de lixo passar.
        token = trocar_code(code, client_id, client_secret, abrir=abrir)
        quem = identidade(token, abrir=abrir)
    except (ErroDoGithub, OSError, ValueError, KeyError, http.client.HTTPException):
        return None
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
        # `safe=""`: o padrao do `quote` deixa a barra passar, e ai
        # `convidar "../orgs/x"` sairia da rota /users/. So alcancavel por quem
        # ja digita na linha de comando da maquina, mas custa uma palavra.
        QUEM + urllib.parse.quote((login or "").strip(), safe=""),
        headers=_CABECALHO)
    with abrir(req, timeout=ESPERA) as r:
        u = json.loads(r.read(TETO_DA_RESPOSTA).decode("utf-8"))
    if not u.get("id"):
        raise ErroDoGithub("login do GitHub nao encontrado: %s" % login)
    fechar = con is None
    con = con or banco.conectar()
    try:
        # TUDO OU NADA. `banco.criar_usuario` commita sozinho: sem esta guarda,
        # um id do GitHub ja ligado a outra conta fazia a `usuario` ficar
        # gravada e a credencial estourar — sobrava uma conta que nao loga, com
        # o e-mail queimado pelo UNIQUE e nenhum comando para apaga-la. Repetir
        # o convite com o e-mail certo passava a estourar tambem.
        uid = banco.criar_usuario(email, nome=u.get("name") or login, con=con)
        try:
            banco.ligar_github(uid, str(u["id"]), con=con)
        except Exception:
            con.execute("DELETE FROM usuario WHERE id = ?", (uid,))
            con.commit()
            raise
        return uid
    finally:
        if fechar:
            con.close()


# ------------------------------------------------------------- o desconvite
#
# O irmao que faltava. Errar o e-mail num convite era permanente: `email` e
# UNIQUE em `usuario`, entao o endereco ficava queimado e o unico conserto era
# abrir o banco do servidor a mao.
#
# As tabelas de credencial, sessao, maquina, pareamento, chave e codigo estao
# amarradas por `ON DELETE CASCADE` e somem sozinhas — `banco.conectar` liga o
# `PRAGMA foreign_keys`. As tabelas de DECISAO (`pendencia_estado`,
# `pendencia_arquivada`, `medida`) nao tem chave estrangeira de proposito: o
# DONO_LOCAL = 0 nao e um usuario de verdade. Por isso elas sao apagadas aqui,
# nominalmente.
#
# Nada disto corre risco de vazar para uma conta futura: `usuario.id` e
# AUTOINCREMENT, e o SQLite nunca reaproveita um numero. A limpeza e higiene,
# nao contencao de vazamento.
_TABELAS_SEM_CASCATA = ("pendencia_estado", "pendencia_arquivada", "medida")


def remover(email: str, con=None) -> int:
    """Apaga a conta daquele e-mail e tudo que pende dela. Devolve o id."""
    fechar = con is None
    con = con or banco.conectar()
    try:
        # `incluir_desativados`: sem ele o comando responderia "nao ha conta
        # com este e-mail" para uma conta que existe e esta apenas desativada,
        # e ela ficaria impossivel de apagar — o buraco que este comando veio
        # fechar, de novo, so que calado.
        u = banco.usuario_por_email(email, con=con, incluir_desativados=True)
        if u is None:
            raise ValueError("nao ha conta com este e-mail: %s" % email)
        uid = u["id"]
        # Nao ha cadastro pela web: se depois desta remocao nao sobrar nenhuma
        # conta QUE ENTRA, o DERVS fica trancado para sempre e o conserto seria
        # exatamente o que este comando existe para nao exigir — mexer no banco
        # do servidor a mao.
        #
        # Contar linhas da tabela nao serve: conta desativada nao entra
        # (`entrar_por_github` a recusa), entao ela nao e saida para ninguem.
        sobram = con.execute(
            "SELECT COUNT(*) FROM usuario"
            " WHERE desativado_em IS NULL AND id <> ?", (uid,)).fetchone()[0]
        if sobram == 0:
            raise ValueError(
                "esta e a unica conta que ainda entra no DERVS; apaga-la "
                "trancaria o sistema para sempre. Convide a conta nova ANTES "
                "de apagar esta.")
        for tabela in _TABELAS_SEM_CASCATA:
            con.execute("DELETE FROM %s WHERE usuario_id = ?" % tabela, (uid,))
        con.execute("DELETE FROM usuario WHERE id = ?", (uid,))
        con.commit()
        return uid
    except Exception:
        # A remocao sao varios DELETE numa transacao implicita. Sem este
        # rollback, uma falha no meio deixava os apagados PENDENTES na conexao
        # — e quando `con` vem de fora, o proximo commit de outra pessoa
        # gravaria a meia-remocao sem ninguem pedir.
        con.rollback()
        raise
    finally:
        if fechar:
            con.close()


USO = """uso: python autenticacao.py convidar <login-do-github> <email>
     python autenticacao.py remover <email> APAGAR

convidar  cria a conta e a amarra ao id numerico do GitHub.
remover   apaga a conta daquele e-mail, com tudo que pende dela, e libera o
          endereco para um convite novo. A palavra APAGAR e obrigatoria: e o
          que separa o comando de um errinho de digitacao. A ultima conta do
          sistema nao pode ser apagada.

Nao ha caminho pela web para nenhum dos dois.
"""


def main(argv) -> int:
    if len(argv) == 4 and argv[1] == "convidar":
        uid = convidar(argv[2], argv[3])
        print("conta criada: %s (id %d)" % (argv[3], uid))
        return 0
    if len(argv) == 4 and argv[1] == "remover" and argv[3] == "APAGAR":
        try:
            uid = remover(argv[2])
        except ValueError as e:
            sys.stderr.write("%s\n" % e)
            return 1
        print("conta apagada: %s (id %d)" % (argv[2], uid))
        return 0
    sys.stderr.write(USO)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
