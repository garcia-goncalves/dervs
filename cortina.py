# -*- coding: utf-8 -*-
"""A cortina: o que o DERVS mostra antes de admitir que e um sistema.

ISTO NAO E A FECHADURA, e o comentario esta aqui para que ninguem trate como
se fosse. Seis digitos sao um milhao de combinacoes. O que a cortina compra e
outra coisa, e nao e pouca: robo que varre a internet atras de tela de login
nao encontra tela de login nenhuma, entao nem tenta.

O valor real de conferir AQUI, no servidor, em vez de no navegador, e que o
formulario de login nao viaja ate o navegador antes da hora. Quem der Ctrl+U na
primeira visita nao acha a palavra secreta, porque nao ha palavra nenhuma na
pagina — so um teclado que manda seis digitos para ca.

Quem protege o dado e o login do GitHub, em `autenticacao.py`, mais a lista de
contas na tabela `credencial`.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import threading

import banco

TETO = 5              # tentativas por origem dentro da janela
JANELA = 900          # segundos (15 minutos)
MINUTOS_DO_SELO = 10

# Local e de mentira: dado de teste nao e segredo, e esta escrito no README para
# o dono nao ter de decorar nada na propria maquina. No servidor a combinacao e
# sorteada e mostrada uma vez so.
COMBINACAO_LOCAL = "000000"

_SEIS_DIGITOS = re.compile(r"^\d{6}$")

_tentativas: dict = {}
# ThreadingHTTPServer atende cada pedido numa linha de execucao propria: duas
# tentativas simultaneas mexeriam neste dicionario ao mesmo tempo.
_trava = threading.Lock()


def _e_local() -> bool:
    return (os.environ.get("DERVS_AMBIENTE") or "").strip().lower() == "local"


# ------------------------------------------------------------- a combinacao

def combinacao_atual(con) -> str:
    """A impressao digital gravada, ou string vazia. NUNCA o numero."""
    l = con.execute("SELECT combinacao_hash FROM instalacao WHERE id = 1").fetchone()
    return (l["combinacao_hash"] if l else None) or ""


def garantir_combinacao(con):
    """Gera na primeira subida e devolve o numero EM CLARO, uma unica vez.

    Devolve None se ja existia. Quem chama imprime uma vez e esquece: depois
    desta linha o numero nao existe em lugar nenhum deste sistema — so a
    impressao digital, que nao volta a ser numero.
    """
    # Ler e escrever na mesma transacao: dois processos subindo juntos gerariam
    # dois numeros diferentes, o segundo venceria, e o primeiro teria impresso
    # na tela uma combinacao que nao abre nada — e ela nao aparece de novo.
    con.execute("BEGIN IMMEDIATE")
    try:
        con.execute("INSERT OR IGNORE INTO instalacao (id, criada_em)"
                    " VALUES (1, ?)", (banco.agora(),))
        if combinacao_atual(con):
            con.commit()
            return None
        numero = COMBINACAO_LOCAL if _e_local() else banco.novo_codigo(6)
        con.execute("UPDATE instalacao SET combinacao_hash = ?,"
                    " combinacao_em = ? WHERE id = 1",
                    (banco.hash_senha(numero), banco.agora()))
        con.commit()
    except Exception:
        con.rollback()
        raise
    return numero


def trocar(combinacao, con) -> None:
    """Troca a combinacao. Recusa o que nao for exatamente seis digitos."""
    if not _SEIS_DIGITOS.match(combinacao or ""):
        raise ValueError("a combinacao tem de ser exatamente seis digitos")
    con.execute("INSERT OR IGNORE INTO instalacao (id, criada_em) VALUES (1, ?)",
                (banco.agora(),))
    _gravar(combinacao, con)


def _gravar(numero: str, con) -> None:
    # scrypt, e nao o HMAC de `banco.hash_codigo` que existe e e mais rapido:
    # o HMAC depende da chave do cofre, e quem consegue copiar o hub.db da
    # maquina costuma levar o cofre.chave junto — ai o milhao de combinacoes
    # cai em segundos. Com scrypt a mesma varredura custa cerca de um dia de
    # processador. Um dia nao e "seguro"; e "caro o bastante para uma cortina",
    # e e por isso que a fechadura continua sendo a camada do GitHub.
    con.execute("UPDATE instalacao SET combinacao_hash = ?, combinacao_em = ?"
                " WHERE id = 1", (banco.hash_senha(numero), banco.agora()))
    con.commit()


def conferir(combinacao, con) -> bool:
    """Falha FECHADA: sem combinacao gravada, ninguem entra.

    A comparacao e de tempo constante — `banco.conferir_senha` termina em
    `hmac.compare_digest` —, entao o tempo de resposta nao diz quantos digitos
    bateram.
    """
    # A forma e conferida ANTES do scrypt: sem isto, uma string de 1 KiB custa o
    # mesmo `scrypt` de ~16 MiB que seis digitos, e quem chuta escolhe o
    # tamanho. A combinacao tem forma fixa e conhecida — barra-se pela forma.
    if not _SEIS_DIGITOS.match(combinacao or ""):
        return False
    guardado = combinacao_atual(con)
    if not guardado:
        return False
    return banco.conferir_senha(combinacao, guardado)


# ------------------------------------------------------------------ o selo
#
# O que o navegador guarda depois de acertar. E so um prazo assinado: nao ha
# nada a consultar no banco, porque dez minutos e passageiro demais para
# justificar uma linha de tabela.

def selar(agora_s: float, chave: bytes, minutos: int = MINUTOS_DO_SELO) -> str:
    ate = "%d" % int(agora_s + minutos * 60)
    return ate + "." + _assinar(ate, chave)


def selo_valido(selo, agora_s: float, chave: bytes) -> bool:
    ate, _, assinatura = (selo or "").partition(".")
    # `isdigit` tambem barra o sinal de menos e o vazio, e o limite de tamanho
    # segura o que entra em `int()`.
    if not ate.isdigit() or len(ate) > 20 or not assinatura:
        return False
    if not hmac.compare_digest(_assinar(ate, chave), assinatura):
        return False
    return agora_s <= int(ate)


def _assinar(ate: str, chave: bytes) -> str:
    return hmac.new(chave, ("cortina|" + ate).encode("utf-8"),
                    hashlib.sha256).hexdigest()


# ------------------------------------------------------- o teto por origem
#
# Por ORIGEM e na ROTA, nao no recurso. A etapa 8 removeu um contador que vivia
# na tabela de pareamento justamente porque contar no recurso deixa um estranho
# matar o acesso de todo mundo com cinco chutes. A etapa 11 reusa isto para o
# codigo de seis digitos do pareamento — e a divida que ela tinha anotada.
#
# Em memoria de proposito: reiniciar o servidor zera o contador, e isso e
# aceitavel para uma cortina. Persistir daria a quem chuta um jeito de encher o
# disco de outra pessoa.

def registrar_tentativa(origem: str, agora_s: float) -> bool:
    """Anota a tentativa e diz se ela pode ser conferida. UMA funcao so.

    Antes eram duas — `pode_tentar` e `anotar_tentativa` —, cada uma pegando o
    lock por conta propria. Entre a saida de uma e a entrada da outra nao havia
    nada: N pedidos simultaneos liam todos "ainda cabe" antes de qualquer um
    anotar, e o teto de cinco virava "o quanto eu consigo paralelizar". O
    servidor e `ThreadingHTTPServer`, entao os N chegam mesmo.

    Isso importava mais do que parece: a spec sustenta a escolha de seis digitos
    dizendo que o teto por origem e o que a segura. Teto que so vale
    sequencialmente nao segura nada. Havia ainda o custo — cada conferencia paga
    um `scrypt` de ~16 MiB, e duzentos em paralelo sao uns 3 GiB.
    """
    with _trava:
        _podar(agora_s)
        vistas = _tentativas.setdefault(origem, [])
        if len(vistas) >= TETO:
            return False
        vistas.append(agora_s)
        return True


def origens_lembradas() -> set:
    with _trava:
        return set(_tentativas)


def zerar_tentativas() -> None:
    with _trava:
        _tentativas.clear()


def _podar(agora_s: float) -> None:
    """Sem isto o dicionario cresce por IP ate o processo morrer."""
    for origem in list(_tentativas):
        recentes = [t for t in _tentativas[origem] if agora_s - t < JANELA]
        if recentes:
            _tentativas[origem] = recentes
        else:
            del _tentativas[origem]
