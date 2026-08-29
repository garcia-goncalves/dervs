# -*- coding: utf-8 -*-
"""Mede esta maquina e manda o resultado para um DERVS.

    # a primeira vez, com o codigo de seis digitos que o painel mostrou:
    python -m agente.enviar --alvo https://dervs.com.br --codigo 123456

    # depois disso, so:
    python -m agente.enviar --alvo https://dervs.com.br

    # de dez em dez minutos, sem sair:
    python -m agente.enviar --alvo https://dervs.com.br --intervalo 600

O TOKEN NUNCA ENTRA NA LINHA DE COMANDO. Argumento de processo aparece na lista
de processos da maquina inteira, e em alguns sistemas para qualquer usuario. O
codigo de seis digitos entra porque ele e de uso unico e vive dez minutos; o
token, que nao vence, so entra e sai por arquivo — `~/.dervs/agente.json`, ou
onde `DERVS_AGENTE_ARQUIVO` disser.

NADA AQUI ESCUTA PORTA. Ver o docstring do pacote para o porque.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# `coletar` mora na raiz do repositorio, um nivel acima deste pacote.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import coletar
import tarefas  # noqa: E402


ESPERA = 60          # segundos de paciencia com a rede, por pedido
TETO_DA_RESPOSTA = 64 * 1024


# --------------------------------------------------------------- o token

def arquivo_do_token() -> Path:
    """Onde o token mora. FORA do repositorio, sempre.

    Token dentro da pasta do projeto e token commitado no dia em que alguem
    rodar `git add -A` com pressa — e token commitado e token vazado, mesmo que
    o commit seja desfeito um minuto depois.
    """
    bruto = os.environ.get("DERVS_AGENTE_ARQUIVO")
    if bruto:
        return Path(bruto).expanduser()
    return Path.home() / ".dervs" / "agente.json"


def _lido() -> dict:
    try:
        dados = json.loads(arquivo_do_token().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return dados if isinstance(dados, dict) else {}


def token_de(alvo: str) -> str:
    return str(_lido().get(_chave(alvo), {}).get("token") or "")


def guardar_token(alvo: str, token: str, maquina: str = "") -> Path:
    """Grava o token com permissao 600 onde o sistema operacional souber.

    A pasta e criada com 700 pelo mesmo motivo: no Windows a chamada nao faz
    nada e a heranca do perfil do usuario e o que protege; no Linux e no Mac,
    onde este agente tambem roda, o padrao do sistema deixaria o arquivo legivel
    por qualquer conta da maquina.

    ESCREVE NUM TEMPORARIO E TROCA POR CIMA. Duas razoes, as duas apontadas por
    revisao:

    1. O modo do `os.open` so vale para arquivo NOVO. Escrever direto no destino
       que ja existe com permissao frouxa deixava o token exposto entre a
       escrita e o `chmod` — e o `chmod` falha em silencio. Um temporario criado
       com `O_EXCL` NUNCA existe antes, entao nasce sempre com 600.
    2. `os.replace` e atomico. Escrever por cima com `O_TRUNC` significava que
       uma queda no meio da escrita perdia TODOS os tokens desta maquina, e nao
       so o que estava entrando.
    """
    destino = arquivo_do_token()
    destino.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    dados = _lido()
    dados[_chave(alvo)] = {"token": token, "maquina": maquina,
                           "guardado_em": time.strftime("%Y-%m-%dT%H:%M:%S")}
    texto = json.dumps(dados, ensure_ascii=False, indent=2)
    passagem = destino.with_name(destino.name + ".novo")
    try:
        passagem.unlink()             # sobra de uma queda anterior
    except OSError:
        pass
    fd = os.open(passagem, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as arq:
        arq.write(texto)
    os.replace(passagem, destino)
    return destino


def _chave(alvo: str) -> str:
    """Um token por alvo. Sem isto, parear com o DERVS de teste apagava o token
    do DERVS de verdade, e o dono so descobria pelo painel parado."""
    return alvo.rstrip("/").lower()


# ----------------------------------------------------------------- a rede

class ErroDoAlvo(Exception):
    """Falha que o dono precisa LER, e nao um traceback."""


# Onde `http://` continua valendo: a maquina do proprio dono, sem rede no meio.
LOCAIS = ("localhost", "127.0.0.1", "::1")


def conferir_alvo(alvo: str) -> str:
    """`http://` num endereco de fora manda o token em CLARO no cabecalho.

    Uma letra a menos digitada e a credencial da maquina viaja legivel por todo
    salto do caminho. Achado da revisao de seguranca da etapa 11.
    """
    alvo = (alvo or "").strip().rstrip("/")
    if not alvo:
        raise ErroDoAlvo("--alvo vazio. Exemplo: --alvo https://dervs.com.br")
    try:
        partes = urllib.parse.urlsplit(alvo)
    except ValueError as e:
        # Sem isto o dono levava um traceback: `main` so captura `ErroDoAlvo`.
        raise ErroDoAlvo("nao entendi o endereco %r (%s)" % (alvo, e)) from None
    if partes.fragment or partes.query:
        # `--alvo http://x#y` passava e depois engolia o caminho na
        # concatenacao de `_falar`, virando um 404 sem explicacao.
        raise ErroDoAlvo("o endereco do DERVS nao leva `?` nem `#`. Veio: %r"
                         % alvo)
    if partes.scheme not in ("http", "https"):
        raise ErroDoAlvo("o endereco tem de comecar com https:// (ou http:// "
                         "para o DERVS da sua propria maquina). Veio: %r" % alvo)
    if partes.scheme == "http" and (partes.hostname or "") not in LOCAIS:
        raise ErroDoAlvo(
            "recusei falar com %s por http://: o token da maquina iria em "
            "claro, legivel por quem estiver no caminho. Use https://." % alvo)
    return alvo


class _SemRedirecionar(urllib.request.HTTPRedirectHandler):
    """O `urlopen` segue redirecionamento LEVANDO o `Authorization` junto.

    O `HTTPRedirectHandler` do CPython repassa todos os cabecalhos menos
    `content-length` e `content-type`, sem tirar o `Authorization` na troca de
    host. Um 302 do alvo para `http://outro-host/` entregava o token da maquina
    em texto — e quem controla o alvo hoje so tem o HASH dele. Achado da revisao
    da correcao.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ErroDoAlvo(
            "o alvo respondeu com um desvio (%s) para %s, e eu nao sigo desvio: "
            "o cabecalho com o token da maquina iria junto. Confira o endereco."
            % (code, newurl))


_ABRIDOR = urllib.request.build_opener(_SemRedirecionar)


def _falar(alvo: str, caminho: str, corpo: dict, token: str = "") -> dict:
    dados = json.dumps(corpo, ensure_ascii=False).encode("utf-8")
    pedido = urllib.request.Request(
        alvo.rstrip("/") + caminho, data=dados, method="POST",
        headers={"Content-Type": "application/json", "User-Agent": "dervs-agent"})
    if token:
        pedido.add_header("Authorization", "Token " + token)
    try:
        with _ABRIDOR.open(pedido, timeout=ESPERA) as r:
            return json.loads(r.read(TETO_DA_RESPOSTA) or b"{}")
    except urllib.error.HTTPError as e:
        raise ErroDoAlvo(_explicar(caminho, e.code)) from None
    except (urllib.error.URLError, OSError) as e:
        raise ErroDoAlvo("nao consegui falar com %s (%s). O endereco esta certo "
                         "e a maquina tem internet?" % (alvo, e)) from None
    except ValueError:
        raise ErroDoAlvo("%s respondeu algo que nao e JSON. E mesmo um DERVS?"
                         % alvo) from None


def _explicar(caminho: str, codigo: int) -> str:
    """O erro em portugues, porque quem le isto e o dono da maquina."""
    if codigo == 429:
        # Hifen, e nao travessao: esta frase e IMPRESSA no console do Windows,
        # onde `—` sai como `?`. Achado em 29/08/2026, e ja estava assim.
        return ("o alvo recusou por excesso de tentativas. Espere quinze "
                "minutos, e gere um codigo novo no painel.")
    if codigo == 401 and caminho.endswith("/parear"):
        # O QUARTO MOTIVO E O QUE MAIS ENGANA, e faltava. Quem tem dois DERVS
        # — o do servidor e o da propria maquina — gera o numero num painel e
        # cola no outro. Bancos separados, entao o segundo recusa, corretamente.
        # A frase antiga listava tres causas e nenhuma era essa: o dono leu como
        # defeito do produto. Aconteceu em 29/08/2026.
        return ("o codigo de seis digitos nao serve. Quatro motivos possiveis: "
                "foi digitado errado; ja passou dos dez minutos; ja foi usado "
                "por outra maquina; ou o numero saiu do painel de outro DERVS. "
                "Cada DERVS tem o banco dele, e o numero so vale no painel onde "
                "nasceu. Confira se o --alvo e o mesmo endereco que voce abriu "
                "no navegador, e gere outro numero la.")
    if codigo in (401, 403):
        return ("esta maquina nao esta mais autorizada. Se ela foi removida no "
                "painel, pareie de novo com um codigo novo.")
    if codigo == 404:
        return "o alvo respondeu 404. Esse endereco e mesmo de um DERVS?"
    return "o alvo respondeu %d." % codigo


# ------------------------------------------------------------- o trabalho

def nome_desta_maquina() -> str:
    return platform.node() or "maquina sem nome"


def parear(alvo: str, codigo: str, nome: str = "") -> str:
    """Troca o codigo de seis digitos pelo token desta maquina. UMA vez so."""
    nome = nome or nome_desta_maquina()
    resposta = _falar(alvo, "/agente/parear", {"codigo": codigo, "maquina": nome})
    token = str(resposta.get("token") or "")
    if not token:
        raise ErroDoAlvo("o alvo aceitou o codigo mas nao devolveu token.")
    guardar_token(alvo, token, nome)
    return token


def enviar_uma_vez(alvo: str, medicao=None, trabalhar=True,
                   relogio=None) -> dict:
    """Mede, manda — e, se o painel pedir, TRABALHA.

    O envio E o sinal de vida; nao ha outro. E a resposta do painel e o unico
    lugar de onde uma tarefa chega: o agente continua sem escutar porta
    nenhuma. Quem pergunta e ele.

    `trabalhar=False` desliga a execucao e deixa so a medicao — e o que o
    teste usa, e e o que a maquina do dono usa enquanto ele nao autorizar.
    """
    token = token_de(alvo)
    if not token:
        raise ErroDoAlvo("esta maquina ainda nao esta pareada com %s. Rode de "
                         "novo com --codigo <seis digitos>, pegando o numero no "
                         "painel." % alvo)
    if medicao is None:
        medicao = coletar.medir()
    resposta = _falar(alvo, "/agente/relatorio", {
        "maquina": nome_desta_maquina(),
        "projetos": medicao["projetos"],
        "infra": medicao["infra"],
        # Os avisos vao JUNTO: "a raiz nao existe" e "o docker esta mudo" tem de
        # chegar ao painel remoto. Sem eles, uma medicao que nao mediu nada
        # chega do outro lado com a mesma cara de uma que nao achou nada.
        "avisos": medicao.get("avisos", []),
    }, token=token)

    tarefa = resposta.get("tarefa") if isinstance(resposta, dict) else None
    if trabalhar and isinstance(tarefa, dict) and tarefa.get("id"):
        try:
            resposta["desfecho"] = fazer_a_tarefa(alvo, token, tarefa,
                                                  medicao=medicao,
                                                  relogio=relogio)
        except Exception as e:                  # noqa: BLE001
            # UMA tarefa que explode nao pode matar o laco do agente. A maquina
            # tem de continuar reportando: parar de medir por causa de uma
            # sessao ruim deixaria o painel cego exatamente quando ha problema.
            resposta["desfecho"] = {"estado": "falha",
                                    "erro": "%s: %s" % (type(e).__name__, e)}
    return resposta


def caminho_do_projeto(nome: str, medicao=None) -> str:
    """Onde ESTE projeto vive nesta maquina. "" se ela nao o conhece.

    O painel manda o NOME do projeto, nunca um caminho: um caminho vindo da
    rede seria o painel dizendo em que pasta desta maquina mexer, e isso e
    exatamente o que a lista da medicao existe para impedir.
    """
    for p in ((medicao or {}).get("projetos") or []):
        if (p.get("nome") or p.get("projeto") or "") == nome:
            return p.get("caminho") or ""
    return ""


def fazer_a_tarefa(alvo: str, token: str, tarefa: dict, medicao=None,
                   relogio=None) -> dict:
    """Roda a sessao e vai contando. Devolve o desfecho que subiu.

    O PROGRESSO E O FREIO. A cada `tarefas.SEGUNDOS_ENTRE_PROGRESSOS` o agente
    manda o que apareceu, e a RESPOSTA desse mesmo pedido traz `{"pare": true}`
    quando o dono clicou. Nao ha conexao aberta do painel para ca, e nao ha
    porta escutando: o freio viaja no pedido que o agente ja ia fazer.

    A latencia disso e ate 5 s, mais o tempo de matar a arvore de processos,
    mais os 5 s que `execucao.parar()` espera pela confirmacao. A tela tem de
    dizer isso — nao ha etapa que torne o botao instantaneo.
    """
    from agente import executor as _executor

    braco = _executor.executor_de(tarefa.get("executor") or "claude")
    if braco is None or not braco.disponivel():
        desfecho = {"tipo": "desfecho", "id": tarefa.get("id") or "",
                    "estado": "falha", "ramo": "", "resumo": "", "diff": "",
                    "pr_url": "", "rodadas": 0, "custo_usd": 0.0,
                    "erro": "esta maquina nao tem o braco %r instalado"
                            % (tarefa.get("executor") or "claude")}
        _falar(alvo, "/agente/resultado", desfecho, token=token)
        return desfecho

    agora = relogio or time.monotonic
    # Comeca ATRASADO de proposito: assim a PRIMEIRA volta ja fala com o
    # painel, em vez de esperar cinco segundos. Sem isso, toda sessao comecava
    # com cinco segundos de tela em branco — e cinco segundos de nada, logo
    # depois de o dono clicar, e o que faz uma pessoa clicar de novo.
    ultimo = [agora() - tarefas.SEGUNDOS_ENTRE_PROGRESSOS]
    entregues = [0]

    def contar(retrato):
        """Chamado pelo braco a cada volta. Devolve True para "pare"."""
        if agora() - ultimo[0] < tarefas.SEGUNDOS_ENTRE_PROGRESSOS:
            return False
        ultimo[0] = agora()
        linhas = []
        for i, texto in enumerate(retrato.get("linhas") or []):
            linhas.append([entregues[0] + i + 1, texto])
        entregues[0] += len(linhas)
        try:
            volta = _falar(alvo, "/agente/resultado", {
                "tipo": "progresso", "id": tarefa.get("id") or "",
                "frase": retrato.get("frase") or "",
                "linhas": linhas,
                "rodadas": retrato.get("rodadas") or 0,
                "custo_usd": retrato.get("custo_usd") or 0.0,
            }, token=token)
        except ErroDoAlvo:
            # A rede caiu no meio. NAO e motivo para matar a sessao: as linhas
            # que nao subiram sobem no proximo pedido, e o desfecho ainda vai
            # chegar. Devolver True aqui faria uma falha de rede parecer, para
            # o dono, um clique dele no botao Parar.
            return False
        return bool(isinstance(volta, dict) and volta.get("pare"))

    caminho = caminho_do_projeto(tarefa.get("projeto") or "", medicao)
    desfecho = braco.rodar(dict(tarefa, caminho=caminho),
                           ao_progredir=contar,
                           gasto_usd=0.0)
    # O desfecho sobe SEMPRE, inclusive quando a sessao falhou. Sem ele a
    # tarefa fica `rodando` no painel ate a varredura de 15 minutos, e ate la a
    # tela mente dizendo que ha trabalho acontecendo.
    try:
        _falar(alvo, "/agente/resultado", desfecho, token=token)
    except ErroDoAlvo:
        pass
    return desfecho


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="python -m agente.enviar",
        description="Mede esta maquina e manda para um DERVS.")
    p.add_argument("--alvo", required=True,
                   help="endereco do DERVS, ex: https://dervs.com.br")
    p.add_argument("--codigo", default="",
                   help="os seis digitos do painel, so na primeira vez")
    p.add_argument("--nome", default="",
                   help="como esta maquina aparece no painel (padrao: o nome "
                        "que ela ja tem no sistema)")
    p.add_argument("--intervalo", type=int, default=0,
                   help="se dado, repete a cada N segundos em vez de sair")
    a = p.parse_args(argv)

    try:
        # ANTES de qualquer coisa ir pela rede, inclusive do primeiro
        # pareamento: o codigo de seis digitos tambem e segredo.
        a.alvo = conferir_alvo(a.alvo)
    except ErroDoAlvo as e:
        print("ENDERECO RECUSADO: %s" % e, file=sys.stderr)
        return 2

    try:
        if a.codigo:
            parear(a.alvo, a.codigo.strip(), a.nome)
            # O token NAO e impresso. Ele fica no arquivo, e so.
            print("pareado com %s. O token ficou em %s"
                  % (a.alvo, arquivo_do_token()))
    except ErroDoAlvo as e:
        print("NAO PAREOU: %s" % e, file=sys.stderr)
        return 2

    while True:
        try:
            r = enviar_uma_vez(a.alvo)
            print("enviado: %s projetos -> %s" % (r.get("projetos", "?"), a.alvo))
            # O alvo tem teto de projetos por relatorio. Se ele cortou, quem
            # roda o agente PRECISA saber: sem esta linha, "enviado: 300
            # projetos" pareceria a conta inteira.
            if r.get("cortados"):
                print("AVISO: o alvo cortou %s projeto(s) por exceder o teto "
                      "dele." % r["cortados"], file=sys.stderr)
            # `invalidos` e outra coisa: nome vazio, nome reservado, ou entrada
            # que nem e dicionario. Sem esta linha um bug de serializacao AQUI
            # ficaria invisivel dos dois lados — o alvo recusa em silencio e o
            # agente imprime a conta cheia.
            if r.get("invalidos"):
                print("AVISO: o alvo RECUSOU %s entrada(s) por nome vazio, "
                      "reservado ou formato errado." % r["invalidos"],
                      file=sys.stderr)
        except ErroDoAlvo as e:
            # Erro de rede num laco nao pode matar o agente: a internet cai, e o
            # que interessa e ele voltar sozinho quando ela voltar.
            print("NAO ENVIOU: %s" % e, file=sys.stderr)
            if not a.intervalo:
                return 2
        if not a.intervalo:
            return 0
        time.sleep(a.intervalo)


if __name__ == "__main__":
    sys.exit(main())
