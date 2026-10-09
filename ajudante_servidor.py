"""O ajudante do servidor: instala, pareia e conta ao DERVS o que roda ali.

Este arquivo e baixado do painel, conferido por SHA-256 e rodado UMA vez com
`sudo python3 -I dervs-ajudante.py`. Depois disso um temporizador do sistema o
chama a cada 30 segundos com `medir`, num usuario so dele, e ele manda ao
painel o inventario: quais sistemas estao de pe, desde quando e qual versao foi
publicada por ultimo. `remover` desfaz tudo.

LEIS QUE ESTE ARQUIVO OBEDECE, e o motivo de cada uma:

1. UM ARQUIVO, BIBLIOTECA PADRAO PURA, PYTHON 3.8. Roda num servidor onde nada
   foi instalado e onde o repositorio nao existe. `test_ajudante_servidor.py`
   le o proprio fonte com `ast` e reprova import de fora, ou sintaxe nova.

2. SO OLHA, SALVO DUAS COISAS. O grupo `docker` equivale a administrador: o
   "so olhar" aqui e do CODIGO, nao do sistema. Por isso so dois comandos de
   leitura do Docker existem (`ARGV_DO_PS` e `ARGV_DO_INSPECT`), o formato do
   segundo escolhe os campos um a um, e o teste reprova qualquer outro jeito de
   chamar o Docker. A medicao nunca recebe ordem e este programa nao se
   atualiza. A UNICA excecao e o subcomando `ordens`, DESLIGADO por padrao: so
   existe se o dono colou a linha "com pedidos", e entao faz no maximo duas
   coisas (`ARGV_DO_REINICIO` e `ARGV_DA_VOLTA`), por ordem assinada com a
   digital dele, conferida AQUI, sozinha, antes de qualquer acao.

3. NADA SEGREDO NO QUE SAI. Quem fez a publicacao (o 4o campo do historico) e
   descartado na leitura. O que sobe e uma lista fechada de campos.

4. FALHA FECHADA. Qualquer passo que nao deu para e diz o motivo em portugues,
   com um codigo de saida proprio. Nunca levanta para quem chamou.

5. ASCII PURO. O servidor do painel monta este arquivo em ASCII; um acento
   derruba a rota.
"""

import base64
import datetime
import hashlib
import hmac
import http.client
import json
import os
import re
import secrets
import shutil
import socket
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

# ------------------------------------------------------- o que o painel injeta
#
# O painel LE este arquivo do disco e troca a linha abaixo antes de entregar. A
# marca no fim da linha e o que ele procura: nao a apague.
ALVO = ""     # DERVS:ALVO

USUARIO = "dervs-ajudante"
PASTA_DOS_DADOS = "/var/lib/dervs-ajudante"
PASTA_DO_PROGRAMA = "/opt/dervs-ajudante"
PROGRAMA = PASTA_DO_PROGRAMA + "/dervs-ajudante.py"
ARQUIVO_DO_PAREAMENTO = PASTA_DOS_DADOS + "/agente.json"
SERVICO = "/etc/systemd/system/dervs-ajudante.service"
TEMPORIZADOR = "/etc/systemd/system/dervs-ajudante.timer"
PASTA_DO_HISTORICO = "/var/log/deploy"
HISTORICO = PASTA_DO_HISTORICO + "/historico.log"

OK = 0
SEM_ROOT = 2
SEM_REQUISITO = 3
SEM_PAREAMENTO = 4
SEM_REDE = 5
RECUSADO = 6

# Os dois UNICOS comandos do Docker. O formato nomeia cada campo lido; nada de
# `json` inteiro, porque o objeto inteiro carrega o que nao se deve ler.
ARGV_DO_PS = ("docker", "ps", "-aq", "--no-trunc")
FORMATO_DO_INSPECT = '{{.Name}}\t{{.State.Status}}\t{{if .State.Health}}{{.State.Health.Status}}{{end}}\t{{.State.StartedAt}}\t{{.RestartCount}}\t{{.Config.Image}}\t{{index .Config.Labels "com.docker.compose.project"}}\t{{index .Config.Labels "org.opencontainers.image.revision"}}'
ARGV_DO_INSPECT = ("docker", "inspect", "--format", FORMATO_DO_INSPECT)

# Os dois UNICOS pedidos que este programa faz, e so com ordem assinada. O nome
# do sistema ou do projeto entra como argumento SEPARADO, nunca num texto.
ARGV_DO_REINICIO = ("docker", "restart")
ARGV_DA_VOLTA = ("sudo", "-n", "/usr/local/bin/deploy")
PRAZO_DO_REINICIO = 120
PRAZO_DA_VOLTA = 1200
# Motivos de recusa: a mesma lista, na mesma ordem, nas tres pontas.
MOTIVOS_DA_RECUSA = ("forma", "outro_servidor", "vencida", "assinatura", "desafio",
                     "origem", "aparelho", "bloqueado", "desconhecido", "repetida",
                     "cheio", "teto")
MAX_NUMEROS = 200
TETO_POR_HORA = 6
# Mesmo conjunto de `tarefas.PROJETOS_BLOQUEADOS` (dado de paciente); um teste
# compara os dois e a resposta das duas funcoes.
PROJETOS_BLOQUEADOS = frozenset({"ajudei-saude"})

PASTA_DAS_ORDENS = "/etc/dervs-ajudante"
ARQUIVO_DAS_ORDENS = PASTA_DAS_ORDENS + "/ordens.json"
ARQUIVO_DOS_NUMEROS = PASTA_DOS_DADOS + "/numeros.json"
SUDOERS = "/etc/sudoers.d/dervs-ajudante"
SUDOERS_NOVO = "/etc/sudoers.d/.dervs-ajudante.novo"
SERVICO_DAS_ORDENS = "/etc/systemd/system/dervs-ajudante-ordens.service"
TEMPORIZADOR_DAS_ORDENS = "/etc/systemd/system/dervs-ajudante-ordens.timer"
MAX_CHAVES = 5
MAX_VOLTAVEIS = 200

MAX_ITENS = 200
ESPERA = 30
TETO_DA_RESPOSTA = 64 * 1024
TETO_DO_HISTORICO = 1024 * 1024
_CODIGO_CURTO = re.compile(r"[2-9A-HJKMNP-Z]{4}-[2-9A-HJKMNP-Z]{4}")
_NOME_OK = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ._-")
_HEX = frozenset("0123456789abcdef")
_ISO_UTC = "%Y-%m-%dT%H:%M:%S+00:00"


# ------------------------------------------------------- as duas portas do mundo

def rodar(argv, prazo):
    """Roda UM programa. (deu_certo, saida). Lista, nunca shell, nunca levanta."""
    try:
        fim = subprocess.run(list(argv), shell=False, capture_output=True,
                             timeout=prazo)
    except (OSError, subprocess.SubprocessError):
        return False, ""
    saida = (fim.stdout or b"").decode("utf-8", "replace")
    return fim.returncode == 0, saida


class _SemRedirecionar(urllib.request.HTTPRedirectHandler):
    """Redirecionar levaria o cabecalho Authorization para outro endereco."""

    def redirect_request(self, *a, **k):
        return None


_ABRIDOR = urllib.request.build_opener(_SemRedirecionar)


def abrir(metodo, url, corpo, token, prazo):
    """Uma chamada ao painel. (codigo, dict|None); codigo 0 = sem resposta.

    O token vai so no cabecalho e NUNCA e impresso.
    """
    dados = None if corpo is None else json.dumps(corpo).encode("ascii")
    pedido = urllib.request.Request(
        url, data=dados, method=metodo,
        headers={"Content-Type": "application/json",
                 "User-Agent": "dervs-ajudante"})
    if token:
        pedido.add_header("Authorization", "Token " + token)
    try:
        with _ABRIDOR.open(pedido, timeout=prazo) as resposta:
            codigo, bruto = resposta.status, resposta.read(TETO_DA_RESPOSTA + 1)
    except urllib.error.HTTPError as e:
        codigo = e.code
        try:
            bruto = e.read(TETO_DA_RESPOSTA + 1)
        except (OSError, http.client.HTTPException):
            bruto = b""
    except (urllib.error.URLError, OSError, ValueError,
            http.client.HTTPException):
        return 0, None
    if len(bruto) > TETO_DA_RESPOSTA:
        return codigo, None
    try:
        lido = json.loads(bruto.decode("utf-8") or "{}")
    except ValueError:
        return codigo, None
    return codigo, lido if isinstance(lido, dict) else None


_RODAR = rodar
_ABRIR = abrir


# ------------------------------------------------------------------- utilidades

def _p(raiz, caminho):
    """`caminho` absoluto do servidor, sob a `raiz` (a "/" de verdade em producao)."""
    return os.path.join(raiz, *caminho.strip("/").split("/"))


def _root():
    geteuid = getattr(os, "geteuid", None)
    return bool(geteuid) and geteuid() == 0


def nome_desta_maquina():
    """O nome do servidor no formato que o painel aceita; o resto vira `-`."""
    try:
        bruto = socket.gethostname() or "servidor"
    except OSError:
        bruto = "servidor"
    limpo = "".join(c if c in _NOME_OK else "-" for c in bruto)[:40].strip()
    return limpo or "servidor"


def _gravar(caminho, texto, modo, dono=None):
    """Grava por arquivo novo + troca atomica: nunca um arquivo pela metade.

    Modo e dono sao trocados no DESCRITOR, antes da troca: na pasta do usuario
    do ajudante, um chmod/chown por caminho seguiria um link que ele pusesse
    ali, e o root daria a ele um arquivo do sistema. O `O_EXCL` recusa link.
    """
    passagem = caminho + ".novo"
    try:
        os.unlink(passagem)
    except OSError:
        pass
    # Nasce 0600 (so o dono escreve) e o modo final vem pelo descritor, depois
    # de escrito: um modo sem escrita (0440) no `open` deixaria o arquivo
    # somente-leitura no Windows (nem apagar nem trocar), e no Linux o
    # resultado final e o mesmo.
    fd = os.open(passagem, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="ascii", newline="\n") as arq:
        arq.write(texto)
        arq.flush()
        if hasattr(os, "fchmod") and os.name != "nt":
            os.fchmod(arq.fileno(), modo)
        if dono is not None:
            dono(arq.fileno(), USUARIO)
    os.replace(passagem, caminho)


def _ler_pareamento(raiz):
    try:
        with open(_p(raiz, ARQUIVO_DO_PAREAMENTO), encoding="ascii") as arq:
            dados = json.load(arq)
    except (OSError, ValueError):
        return {}
    return dados if isinstance(dados, dict) else {}


def _limitado(valor, padrao, minimo, maximo):
    if isinstance(valor, bool) or not isinstance(valor, int):
        return padrao
    return max(minimo, min(maximo, valor))


def _sha_ou_vazio(texto):
    texto = str(texto or "")
    if 7 <= len(texto) <= 40 and all(c in _HEX for c in texto):
        return texto
    return ""


def _alvo_limpo(alvo):
    return str(alvo or "").strip().rstrip("/")


# ------------------------------------------------------------------- as unidades

def texto_do_servico():
    return "\n".join([
        "[Unit]",
        "Description=DERVS - conta ao painel o que roda neste servidor",
        "",
        "[Service]",
        "Type=oneshot",
        "User=" + USUARIO,
        "ExecStart=%s %s medir" % (sys.executable or "/usr/bin/python3", PROGRAMA),
        "NoNewPrivileges=yes",
        "ProtectSystem=strict",
        "ProtectHome=yes",
        "PrivateTmp=yes",
        "ReadWritePaths=" + PASTA_DOS_DADOS,
        "RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6",
        "UMask=0077",
        "PrivateDevices=yes",
        "ProtectKernelTunables=yes",
        "ProtectKernelModules=yes",
        "ProtectControlGroups=yes",
        "RestrictSUIDSGID=yes",
        "LockPersonality=yes",
        "CapabilityBoundingSet=",
        ""])


def texto_do_temporizador():
    return "\n".join([
        "[Unit]",
        "Description=DERVS - medir este servidor a cada 30 segundos",
        "",
        "[Timer]",
        "OnBootSec=30s",
        "OnUnitActiveSec=30s",
        "AccuracySec=1s",
        "",
        "[Install]",
        "WantedBy=timers.target",
        ""])


# ----------------------------------------------------------------- o pareamento

def _parear(alvo, nome, abrir, dormir, saida):
    """Pede, mostra o codigo e espera o clique. (codigo_de_saida, token)."""
    codigo, dados = abrir("POST", alvo + "/agente/pedir",
                          {"maquina": nome, "tipo": "servidor"}, None, ESPERA)
    if codigo == 0:
        saida("Nao consegui falar com o painel. Confira a internet do servidor.")
        return SEM_REDE, ""
    dados = dados or {}
    if (codigo != 200 or not _CODIGO_CURTO.fullmatch(str(dados.get("codigo") or ""))
            or len(str(dados.get("pedido") or "")) < 16):
        saida("O painel recusou o pedido. Tente de novo em alguns minutos.")
        return RECUSADO, ""
    intervalo = _limitado(dados.get("intervalo"), 5, 2, 30)
    prazo = _limitado(dados.get("minutos"), 10, 1, 30) * 60
    saida("")
    saida("Este servidor: " + nome)
    saida("Codigo: " + dados["codigo"])
    saida("Abra no seu computador:  " + alvo + "/#/conectar?autorizar="
          + dados["codigo"])
    saida("Confira que o nome e o codigo sao estes e clique em Autorizar,")
    saida("digitando o codigo se o painel pedir. Se voce nao reconhece este")
    saida("pedido, nao clique: ele vence sozinho.")
    gasto = 0
    while gasto < prazo:
        estado, resposta = abrir("POST", alvo + "/agente/esperar",
                                 {"pedido": dados["pedido"]}, None, ESPERA)
        if estado == 200:
            token = str((resposta or {}).get("token") or "")
            if token:
                return OK, token
            return RECUSADO, ""
        if estado in (400, 401, 403, 404):
            saida("O painel nao liberou este servidor (o pedido vale alguns minutos).")
            return SEM_PAREAMENTO, ""
        if estado == 429:
            intervalo = min(intervalo * 2, 60)
        dormir(intervalo)
        gasto += intervalo
    saida("O painel nao liberou este servidor a tempo. Rode de novo.")
    return SEM_PAREAMENTO, ""


def _novo_acesso(alvo, nome, raiz, abrir, dormir, saida, dono):
    """Pareia e guarda o token JA, antes de qualquer outro passo: ele sai UMA
    vez do painel. (codigo_de_saida, token)."""
    fim, token = _parear(alvo, nome, abrir, dormir, saida)
    if fim != OK:
        return fim, ""
    arquivo = _p(raiz, ARQUIVO_DO_PAREAMENTO)
    try:
        _gravar(arquivo, json.dumps({"alvo": alvo, "token": token}), 0o600,
                dono)
    except (OSError, LookupError):
        saida("Autorizado, mas nao consegui guardar o acesso. Rode de novo.")
        return SEM_REQUISITO, ""
    saida("Autorizado.")
    return OK, token


# ------------------------------------------------------------------ instalar

def instalar(alvo=ALVO, raiz="/", rodar=None, abrir=None, dormir=time.sleep,
             eh_root=None, dono=None, nome=None, saida=print, ordens=None):
    """`ordens`: as chaves da linha com pedidos (textos `x.y`). Sem elas, os
    pedidos que existissem neste servidor sao DESLIGADOS."""
    rodar = rodar or _RODAR
    abrir = abrir or _ABRIR
    dono = dono or shutil.chown
    alvo = _alvo_limpo(alvo)
    nome = nome or nome_desta_maquina()

    if not (eh_root() if eh_root is not None else _root()):
        saida("Preciso de poder de administrador. Rode de novo assim:")
        saida("  sudo python3 -I dervs-ajudante.py")
        return SEM_ROOT
    if sys.version_info < (3, 8):
        saida("O Python deste servidor e velho demais (preciso do 3.8 ou mais novo).")
        return SEM_REQUISITO
    if not os.path.isdir(_p(raiz, "/run/systemd/system")):
        saida("Este servidor nao usa o gerenciador de servicos que eu preciso.")
        saida("Nada foi alterado.")
        return SEM_REQUISITO
    if not shutil.which(ARGV_DO_PS[0]):
        saida("Nao achei o Docker neste servidor. Nada foi alterado.")
        return SEM_REQUISITO
    if not alvo:
        saida("Este arquivo veio sem o endereco do painel. Baixe-o de novo.")
        return SEM_PAREAMENTO

    ok, _ = rodar(["id", USUARIO], 10)
    if not ok:
        ok, _ = rodar(["useradd", "--system", "--no-create-home", "--shell",
                       "/usr/sbin/nologin", "--groups", ARGV_DO_PS[0], USUARIO], 30)
        if not ok:
            saida("Nao consegui criar o usuario do ajudante. Nada foi ligado.")
            return SEM_REQUISITO
    dados_dir = _p(raiz, PASTA_DOS_DADOS)
    try:
        os.makedirs(dados_dir, mode=0o700, exist_ok=True)
        if os.name != "nt":
            os.chmod(dados_dir, 0o700)
        dono(dados_dir, USUARIO)
    except (OSError, LookupError):
        saida("Nao consegui preparar a pasta do ajudante. Nada foi ligado.")
        return SEM_REQUISITO

    cred = _ler_pareamento(raiz)
    token = ""
    if _alvo_limpo(cred.get("alvo")) == alvo and isinstance(cred.get("token"), str):
        token = cred["token"]
    guardado = bool(token)
    if not token:
        fim, token = _novo_acesso(alvo, nome, raiz, abrir, dormir, saida, dono)
        if fim != OK:
            return fim

    try:
        casa = _p(raiz, PASTA_DO_PROGRAMA)
        os.makedirs(casa, mode=0o755, exist_ok=True)
        destino = _p(raiz, PROGRAMA)
        shutil.copyfile(os.path.abspath(__file__), destino)
        if os.name != "nt":
            os.chmod(casa, 0o755)
            os.chmod(destino, 0o755)
    except OSError:
        saida("Nao consegui copiar o ajudante para o servidor. Nada foi ligado.")
        return SEM_REQUISITO

    pasta_log = _p(raiz, PASTA_DO_HISTORICO)
    if os.path.isdir(pasta_log):
        # `-P`: nunca seguir link simbolico.
        leu = bool(shutil.which("setfacl"))
        if leu:
            leu = rodar(["setfacl", "-P", "-m", "u:%s:x" % USUARIO, pasta_log],
                        10)[0]
            arquivo_log = _p(raiz, HISTORICO)
            if os.path.isfile(arquivo_log):
                leu = rodar(["setfacl", "-P", "-m", "u:%s:r" % USUARIO,
                             arquivo_log], 10)[0] and leu
            leu = rodar(["setfacl", "-P", "-d", "-m", "u:%s:r" % USUARIO,
                         pasta_log], 10)[0] and leu
        if not leu:
            saida("Aviso: nao consegui dar ao ajudante a leitura do historico de"
                  " publicacoes.")
            saida("O resto funciona, mas a versao no ar de cada projeto vai"
                  " aparecer como 'nao sei'.")

    try:
        for caminho, texto in ((SERVICO, texto_do_servico()),
                               (TEMPORIZADOR, texto_do_temporizador())):
            destino = _p(raiz, caminho)
            os.makedirs(os.path.dirname(destino), exist_ok=True)
            _gravar(destino, texto, 0o644)
    except OSError:
        saida("Nao consegui registrar o ajudante no sistema. Nada foi ligado.")
        return SEM_REQUISITO
    rodar(["systemctl", "daemon-reload"], 60)
    ok, _ = rodar(["systemctl", "enable", "--now", "dervs-ajudante.timer"], 60)
    if not ok:
        saida("Nao consegui ligar o temporizador do ajudante.")
        return SEM_REQUISITO

    saida("Ligado: a cada 30 segundos este servidor conta ao painel o que roda nele.")
    if ordens is None:
        if _ordens_desligar(raiz, rodar):
            saida("Os pedidos do painel a este servidor foram DESLIGADOS.")
    else:
        _ordens_ligar(ordens, alvo, raiz, rodar, saida)
    ditos = []
    fim = medir(alvo, raiz, rodar, abrir, saida=ditos.append)
    if fim == SEM_PAREAMENTO and guardado:
        # O acesso guardado morreu (o dono desligou o servidor no painel):
        # colar a linha de novo tem de resolver. Uma vez so, nunca um laco.
        saida("O painel nao reconhece mais o acesso guardado. Vamos autorizar"
              " de novo.")
        try:
            os.unlink(_p(raiz, ARQUIVO_DO_PAREAMENTO))
        except OSError:
            pass
        fim, token = _novo_acesso(alvo, nome, raiz, abrir, dormir, saida, dono)
        if fim != OK:
            return fim
        ditos = []
        fim = medir(alvo, raiz, rodar, abrir, saida=ditos.append)
    if fim != OK:
        for texto in ditos:
            saida(texto)
        saida("A primeira medicao nao subiu agora; o temporizador tenta de novo.")
    saida("Em ate um minuto o servidor aparece no painel, em Seus servidores.")
    saida("Para tirar: sudo python3 " + PROGRAMA + " remover")
    saida("e clique em Desligar este servidor no painel.")
    return OK


# --------------------------------------------------------------------- medir

def _tira(valor):
    valor = str(valor).strip()
    return "" if valor == "<no value>" else valor


def _iso_do_docker(texto):
    """`2026-10-08T12:00:00.123Z` vira `2026-10-08T12:00:00+00:00`; o resto, ""."""
    texto = _tira(texto)
    if len(texto) < 19 or texto.startswith("0001") or texto[10] != "T":
        return ""
    candidato = texto[:19] + "+00:00"
    try:
        datetime.datetime.strptime(candidato, _ISO_UTC)
    except ValueError:
        return ""
    return candidato


def _sistemas(rodar):
    """(docker_mudo, lista). `docker_mudo` e verdade quando nao deu para ver
    TUDO: linha descartada nunca vira um sistema a menos em silencio."""
    for _volta in range(2):
        ok, bruto = rodar(list(ARGV_DO_PS), 30)
        if not ok:
            return True, []
        ids = [i for i in bruto.split() if all(c in _HEX for c in i)][:MAX_ITENS]
        if not ids:
            return False, []
        # Um id que sumiu entre as duas perguntas faz o inspect falhar
        # inteiro: pergunta de novo a lista, uma vez.
        ok, bruto = rodar(list(ARGV_DO_INSPECT) + ids, 60)
        if ok:
            break
    else:
        return True, []
    achados, mudo = [], False
    for linha in bruto.splitlines():
        if not linha.strip():
            continue
        campos = linha.split("\t")
        if len(campos) != 8:
            mudo = True
            continue
        nome = _tira(campos[0]).lstrip("/")
        if not nome:
            mudo = True
            continue
        try:
            reinicios = int(_tira(campos[4]))
        except ValueError:
            reinicios = None
        achados.append({
            "nome": nome, "projeto": _tira(campos[6]),
            "estado": _tira(campos[1]).lower(),
            "saude": _tira(campos[2]).lower(),
            "desde": _iso_do_docker(campos[3]), "reinicios": reinicios,
            "imagem": _tira(campos[5]), "sha": _sha_ou_vazio(_tira(campos[7]))})
    return mudo, achados


def _ler_proc(raiz, nome):
    try:
        with open(_p(raiz, "/proc/" + nome), encoding="ascii",
                  errors="replace") as arq:
            return arq.read(8192)
    except OSError:
        return ""


def _numero(texto):
    try:
        valor = float(texto)
    except (TypeError, ValueError):
        return None
    return valor if valor == valor and abs(valor) != float("inf") and valor >= 0 \
        else None


def _servidor(raiz):
    uptime = _ler_proc(raiz, "uptime").split()
    carga = _ler_proc(raiz, "loadavg").split()
    memoria = {}
    for linha in _ler_proc(raiz, "meminfo").splitlines():
        pedacos = linha.replace(":", " ").split()
        if len(pedacos) >= 2 and pedacos[0] in ("MemTotal", "MemAvailable"):
            memoria[pedacos[0]] = _numero(pedacos[1])
    ligado = _numero(uptime[0]) if uptime else None
    try:
        estat = os.statvfs(raiz)
        total, livre = estat.f_blocks * estat.f_frsize, estat.f_bavail * estat.f_frsize
    except (OSError, AttributeError):
        total = livre = None
    return {
        "ligado_s": None if ligado is None else int(ligado),
        "carga_1m": _numero(carga[0]) if len(carga) > 0 else None,
        "carga_5m": _numero(carga[1]) if len(carga) > 1 else None,
        "carga_15m": _numero(carga[2]) if len(carga) > 2 else None,
        "memoria_total_kb": memoria.get("MemTotal"),
        "memoria_disponivel_kb": memoria.get("MemAvailable"),
        "disco_total_b": total, "disco_livre_b": livre}


def _quando_em_utc(data, hora):
    """O historico grava a hora LOCAL do servidor; sobe em UTC."""
    for formato in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            naive = datetime.datetime.strptime(data + " " + hora, formato)
            return naive.astimezone(datetime.timezone.utc).strftime(_ISO_UTC)
        except (ValueError, OverflowError, OSError):
            continue
    return ""


def _publicacoes(raiz):
    """Por projeto, a ultima publicacao que DEU CERTO.

    Linha do kit de publicacao: `data hora PROJETO QUEM versao resultado`. O
    4o campo (quem) e descartado AQUI, na leitura: nao existe depois disto.
    Falha que voltou ao que estava nao muda o que esta no ar; a que nao
    conseguiu voltar deixa o estado desconhecido (sha vazio).
    """
    try:
        with open(_p(raiz, HISTORICO), "rb") as arq:
            tamanho = arq.seek(0, 2)
            cortado = tamanho > TETO_DO_HISTORICO
            arq.seek(max(0, tamanho - TETO_DO_HISTORICO))
            texto = arq.read().decode("ascii", "replace")
    except OSError:
        return []
    linhas = texto.splitlines()[1 if cortado else 0:]
    por_projeto = {}
    for linha in linhas:
        partes = linha.split()
        if len(partes) != 6:
            continue
        data, hora, projeto, _quem, versao, resultado = partes
        projeto = projeto[:128]
        quando = _quando_em_utc(data, hora)
        if not quando:
            continue
        atual = por_projeto.setdefault(projeto, {"ok": None, "perdido": False})
        if resultado.startswith("OK"):
            pedacos = versao.split("-", 2)
            sha = _sha_ou_vazio(pedacos[2]) if len(pedacos) == 3 else ""
            atual["ok"] = {"projeto": projeto, "quando": quando, "sha": sha,
                           "resultado": resultado[:40]}
            atual["perdido"] = False
        elif resultado == "FALHOU-AO-VOLTAR":
            atual["perdido"] = True
    saida = []
    for projeto, atual in por_projeto.items():
        if atual["ok"] is None:
            continue
        if atual["perdido"]:
            saida.append({"projeto": projeto, "quando": "", "sha": "",
                          "resultado": "FALHOU-AO-VOLTAR"})
        else:
            saida.append(atual["ok"])
    return saida[:MAX_ITENS]


def medir(alvo=ALVO, raiz="/", rodar=None, abrir=None, saida=print):
    rodar = rodar or _RODAR
    abrir = abrir or _ABRIR
    cred = _ler_pareamento(raiz)
    token = cred.get("token") if isinstance(cred.get("token"), str) else ""
    destino = _alvo_limpo(cred.get("alvo")) or _alvo_limpo(alvo)
    if not token or not destino:
        saida("Este servidor ainda nao foi autorizado no painel.")
        return SEM_PAREAMENTO
    mudo, sistemas = _sistemas(rodar)
    corpo = {"versao": 1, "docker_mudo": mudo, "servidor": _servidor(raiz),
             "sistemas": sistemas, "publicacoes": _publicacoes(raiz)}
    pedidos = _bloco_dos_pedidos(raiz)
    if pedidos is not None:
        corpo["ordens"] = pedidos
    codigo, _resposta = abrir("POST", destino + "/agente/servidor", corpo,
                              token, ESPERA)
    if codigo == 200 or codigo == 429:
        return OK
    if codigo == 401:
        saida("O painel nao reconhece mais este servidor. Cole a linha do painel"
              " de novo neste servidor.")
        return SEM_PAREAMENTO
    if codigo == 403:
        saida("O painel recusou a medicao deste servidor.")
        return RECUSADO
    saida("Nao consegui falar com o painel agora.")
    return SEM_REDE


# ============================================================ os pedidos (C)
#
# Nada daqui roda sem `/etc/dervs-ajudante/ordens.json`, e esse arquivo so existe
# se o dono colou a linha "com pedidos". A ordem chega ASSINADA com a digital
# dele; quem confere e este programa, sozinho, sem acreditar no painel: o painel
# nao consegue fazer o ajudante conferir uma coisa e fazer outra, porque o texto
# da ordem e REMONTADO daqui dos campos recebidos (nunca recebido pronto).

# A conta P-256 abaixo e COPIA de `p256.py` (este arquivo e lido, nao importa o
# repositorio). `test_ajudante_acoes` compara a arvore de cada funcao e o valor
# de cada constante com o original, e confere a RFC 6979 A.2.5 por aqui.
P = 0xFFFFFFFF00000001000000000000000000000000FFFFFFFFFFFFFFFFFFFFFFFF
A = -3 % P
B = 0x5AC635D8AA3A93E7B3EBBD55769886BC651D06B0CC53B0F63BCE3C3E27D2604B
N = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551
G = (0x6B17D1F2E12C4247F8BCE6E563A440F277037D812DEB33A0F4A13945D898C296,
     0x4FE342E2FE1A7F9B8EE7EB4A7C0F9E162BCE33576B315ECECBB6406837BF51F5)
TETO_DO_DER = 80


def somar(p1, p2):
    if p1 is None:
        return p2
    if p2 is None:
        return p1
    x1, y1 = p1
    x2, y2 = p2
    if x1 == x2:
        if (y1 + y2) % P == 0:
            return None
        m = (3 * x1 * x1 + A) * pow(2 * y1, -1, P) % P
    else:
        m = (y2 - y1) * pow(x2 - x1, -1, P) % P
    x3 = (m * m - x1 - x2) % P
    return (x3, (m * (x1 - x3) - y1) % P)


def multiplicar(k, ponto):
    if ponto is None or k % N == 0:
        return None
    k = k % N
    resultado = None
    atual = ponto
    while k:
        if k & 1:
            resultado = somar(resultado, atual)
        atual = somar(atual, atual)
        k >>= 1
    return resultado


def ponto_valido(ponto) -> bool:
    if not isinstance(ponto, tuple) or len(ponto) != 2:
        return False
    x, y = ponto
    if not isinstance(x, int) or not isinstance(y, int):
        return False
    if not (0 <= x < P and 0 <= y < P):
        return False
    return (y * y - (x * x * x + A * x + B)) % P == 0


def conferir(publica, resumo, r, s) -> bool:
    if not isinstance(resumo, (bytes, bytearray)):
        return False
    if not ponto_valido(publica):
        return False
    if not isinstance(r, int) or not isinstance(s, int):
        return False
    if not (1 <= r < N and 1 <= s < N):
        return False

    e = int.from_bytes(resumo, "big")
    w = pow(s, -1, N)
    u1 = e * w % N
    u2 = r * w % N
    ponto = somar(multiplicar(u1, G), multiplicar(u2, publica))
    if ponto is None:
        return False
    return ponto[0] % N == r


def assinatura_de_der(cru):
    if not isinstance(cru, (bytes, bytearray)) or len(cru) < 8:
        return None
    if len(cru) > TETO_DO_DER:
        return None
    if cru[0] != 0x30:
        return None
    tamanho = cru[1]
    if tamanho > 0x7F or 2 + tamanho != len(cru):
        return None
    corpo = bytes(cru[2:])
    r, resto = _inteiro(corpo)
    if r is None:
        return None
    s, resto = _inteiro(resto)
    if s is None or resto:
        return None
    return (r, s)


def _inteiro(corpo):
    if len(corpo) < 2 or corpo[0] != 0x02:
        return None, b""
    n = corpo[1]
    if n == 0 or n > 0x7F or len(corpo) < 2 + n:
        return None, b""
    valor = corpo[2:2 + n]
    if valor[0] & 0x80:
        return None, b""
    if n > 1 and valor[0] == 0x00 and not (valor[1] & 0x80):
        return None, b""
    return int.from_bytes(valor, "big"), corpo[2 + n:]


def impressao(x, y):
    """Os 16 primeiros hex do SHA-256 de x||y (32 bytes cada): o nome curto de
    uma chave, o mesmo que o painel calcula."""
    cru = x.to_bytes(32, "big") + y.to_bytes(32, "big")
    return hashlib.sha256(cru).hexdigest()[:16]


# ---------------------------------------------------------------- a ordem (C0)

_ALVO_REINICIAR = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
_ALVO_VOLTAR = re.compile(r"[a-z0-9][a-z0-9-]{0,62}")
_CAMPOS_DA_ORDEM = frozenset(("servidor", "tipo", "alvo", "numero", "criado", "vence"))
_B64URL = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")


def _hex_de(texto, tamanho):
    return (isinstance(texto, str) and len(texto) == tamanho
            and all(c in _HEX for c in texto))


def _segundos_ok(valor):
    return (isinstance(valor, int) and not isinstance(valor, bool)
            and 0 <= valor and len(str(valor)) <= 10)


def _campos_ok(campos):
    """Os seis campos, cada um no formato. Nao olha a janela de 300 s."""
    if not isinstance(campos, dict) or set(campos) != _CAMPOS_DA_ORDEM:
        return False
    if not (_hex_de(campos["servidor"], 32) and _hex_de(campos["numero"], 32)):
        return False
    if campos["tipo"] == "reiniciar":
        forma = _ALVO_REINICIAR
    elif campos["tipo"] == "voltar":
        forma = _ALVO_VOLTAR
    else:
        return False
    alvo = campos["alvo"]
    return (isinstance(alvo, str) and forma.fullmatch(alvo) is not None
            and _segundos_ok(campos["criado"]) and _segundos_ok(campos["vence"]))


def texto_da_ordem(campos):
    """O texto canonico da ordem (7 linhas, sem quebra no fim), ou None se
    qualquer campo estiver fora do formato. O desafio da digital e o SHA-256
    deste texto."""
    if not _campos_ok(campos) or campos["vence"] - campos["criado"] != 300:
        return None
    return "\n".join([
        "dervs-ordem=1", "servidor=" + campos["servidor"], "tipo=" + campos["tipo"],
        "alvo=" + campos["alvo"], "numero=" + campos["numero"],
        "criado=%d" % campos["criado"], "vence=%d" % campos["vence"]])


def _de_b64url(texto, maximo):
    """base64url SEM padding, estrito; None se torto ou maior que `maximo`."""
    if (not isinstance(texto, str) or len(texto) > maximo * 2
            or any(c not in _B64URL for c in texto) or len(texto) % 4 == 1):
        return None
    try:
        cru = base64.urlsafe_b64decode(texto + "=" * (-len(texto) % 4))
    except ValueError:
        return None
    return cru if len(cru) <= maximo else None


def _b64url(cru):
    return base64.urlsafe_b64encode(cru).rstrip(b"=").decode("ascii")


def _bloqueado(nome):
    """Mesma regra de `tarefas.projeto_bloqueado`: minusculas, `_`, espaco e `.`
    viram `-`; igual ou prefixo na fronteira do `-`."""
    if not isinstance(nome, str):
        return False
    n = re.sub(r"[_\s.]+", "-", nome.strip().lower())
    return any(n == b or n.startswith(b + "-") for b in PROJETOS_BLOQUEADOS)


def _ponto_de(par):
    """`[x_hex, y_hex]` (64 hex cada) -> ponto NA CURVA, ou None."""
    if not (isinstance(par, list) and len(par) == 2
            and all(_hex_de(t, 64) for t in par)):
        return None
    ponto = (int(par[0], 16), int(par[1], 16))
    return ponto if ponto_valido(ponto) else None


def conferir_ordem(ordem, config, numeros, feitas, agora, sistemas_agora):
    """None se a ordem passou nas conferencias; senao o motivo (de
    `MOTIVOS_DA_RECUSA`). Para na primeira que falha. `sistemas_agora` e uma
    funcao sem argumento que devolve os sistemas de AGORA (lista de dicts com
    `nome` e `projeto`); so e chamada quando `reiniciar` chega ao passo 9."""
    try:
        return _conferir(ordem, config, numeros, feitas, agora, sistemas_agora)
    except (AttributeError, KeyError, TypeError, ValueError, OverflowError):
        return "forma"


def _conferir(ordem, config, numeros, feitas, agora, sistemas_agora):
    if not isinstance(ordem, dict):
        return "forma"
    campos = {k: ordem.get(k) for k in _CAMPOS_DA_ORDEM}
    if not _campos_ok(campos):
        return "forma"
    cliente = _de_b64url(ordem.get("cliente"), 4096)
    autent = _de_b64url(ordem.get("autenticador"), 37)
    assin = _de_b64url(ordem.get("assinatura"), 80)
    if cliente is None or autent is None or len(autent) != 37 or assin is None:
        return "forma"
    if campos["servidor"] != config.get("ident"):
        return "outro_servidor"
    if (campos["vence"] - campos["criado"] != 300
            or not (campos["criado"] - 120 <= agora <= campos["vence"])):
        return "vencida"
    resumo = hashlib.sha256(autent + hashlib.sha256(cliente).digest()).digest()
    par = assinatura_de_der(assin)
    chaves = [_ponto_de(c) for c in (config.get("chaves") or [])[:MAX_CHAVES]]
    if par is None or not any(c is not None and conferir(c, resumo, par[0], par[1])
                              for c in chaves):
        return "assinatura"
    try:
        lido = json.loads(cliente.decode("utf-8"))
    except ValueError:
        return "desafio"
    esperado = _b64url(hashlib.sha256(texto_da_ordem(campos).encode("ascii")).digest())
    desafio = lido.get("challenge") if isinstance(lido, dict) else None
    if (not isinstance(desafio, str) or lido.get("type") != "webauthn.get"
            or not hmac.compare_digest(desafio.encode("ascii", "replace"),
                                       esperado.encode("ascii"))):
        return "desafio"
    origem = lido.get("origin")
    if (not isinstance(origem, str) or origem != config.get("origem")
            or lido.get("crossOrigin", False) is not False):
        return "origem"
    rp_id = config.get("rp_id")
    flags = autent[32]
    if (not isinstance(rp_id, str)
            or autent[:32] != hashlib.sha256(rp_id.encode("ascii", "replace")).digest()
            or not flags & 0x01 or not flags & 0x04 or flags & 0xC0):
        return "aparelho"
    alvo = campos["alvo"]
    if _bloqueado(alvo):
        return "bloqueado"
    if campos["tipo"] == "voltar":
        if alvo not in (config.get("voltaveis") or []):
            return "desconhecido"
    else:
        achados = [s for s in sistemas_agora() if s.get("nome") == alvo]
        if achados and _bloqueado(achados[0].get("projeto")):
            return "bloqueado"
        if not achados:
            return "desconhecido"
    if campos["numero"] in numeros:
        return "repetida"
    if sum(1 for t in feitas if t > agora - 3600) >= TETO_POR_HORA:
        return "teto"
    if sum(1 for v in numeros.values() if v >= agora) >= MAX_NUMEROS:
        return "cheio"
    return None


# -------------------------------------------------- ler o que o instalador gravou

def _ler_config(raiz):
    """O `ordens.json` validado, ou None (ausente ou torto = pedidos desligados)."""
    try:
        with open(_p(raiz, ARQUIVO_DAS_ORDENS), encoding="ascii") as arq:
            dados = json.loads(arq.read(TETO_DA_RESPOSTA + 1))
    except (OSError, ValueError):
        return None
    if (not isinstance(dados, dict) or type(dados.get("versao")) is not int
            or dados["versao"] != 1 or not _hex_de(dados.get("ident"), 32)):
        return None
    if not (isinstance(dados.get("origem"), str) and dados["origem"]
            and isinstance(dados.get("rp_id"), str) and dados["rp_id"]):
        return None
    chaves, voltaveis = dados.get("chaves"), dados.get("voltaveis")
    if not (isinstance(chaves, list) and len(chaves) <= MAX_CHAVES
            and all(_ponto_de(c) is not None for c in chaves)):
        return None
    if not (isinstance(voltaveis, list) and len(voltaveis) <= MAX_VOLTAVEIS
            and all(isinstance(v, str) and _ALVO_VOLTAR.fullmatch(v) for v in voltaveis)):
        return None
    return dados


def _bloco_dos_pedidos(raiz):
    """O que a medicao conta sobre os pedidos (so impressoes, nunca a chave)."""
    config = _ler_config(raiz)
    if config is None:
        return None
    return {"versao": 1, "ident": config["ident"],
            "chaves": [impressao(*_ponto_de(c)) for c in config["chaves"]],
            "voltaveis": list(config["voltaveis"])}


def _ler_numeros(raiz):
    """(numeros, feitas). Ausente e vazio; existir e estar estragado e None
    (esquecer os numeros reabriria a repeticao)."""
    caminho = _p(raiz, ARQUIVO_DOS_NUMEROS)
    if not os.path.exists(caminho):
        return {}, []
    try:
        with open(caminho, encoding="ascii") as arq:
            dados = json.loads(arq.read(TETO_DO_HISTORICO))
    except (OSError, ValueError):
        return None
    if not isinstance(dados, dict):
        return None
    numeros, feitas = dados.get("numeros"), dados.get("feitas")
    if not (isinstance(numeros, dict) and isinstance(feitas, list)
            and all(_hex_de(n, 32) and _segundos_ok(v) for n, v in numeros.items())
            and all(_segundos_ok(t) for t in feitas)):
        return None
    return numeros, feitas


# ------------------------------------------------------------------ fazer (C5)

_AMBIENTE_DO_FAZER = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C"}


def fazer(argv, prazo):
    """Roda UM dos dois pedidos. O codigo de saida (0-255), ou None se nao deu
    para saber. A saida do programa e jogada fora: o registro de um deploy pode
    trazer dado de sistema de saude."""
    try:
        fim = subprocess.run(list(argv), shell=False, stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             timeout=prazo, env=dict(_AMBIENTE_DO_FAZER))
    except (OSError, subprocess.SubprocessError):
        return None
    codigo = fim.returncode
    return codigo if isinstance(codigo, int) and 0 <= codigo <= 255 else None


_FAZER = fazer


def _contar(destino, token, abrir, numero, desfecho, codigo, motivo):
    abrir("POST", destino + "/agente/servidor/desfecho",
          {"numero": numero, "desfecho": desfecho, "codigo": codigo, "motivo": motivo},
          token, ESPERA)


def ordens(alvo=ALVO, raiz="/", rodar=None, abrir=None, fazer=None, agora=time.time,
           saida=print):
    """Busca no maximo UMA ordem, confere sozinho e, se passar, faz e conta."""
    rodar = rodar or _RODAR
    abrir = abrir or _ABRIR
    fazer = fazer or _FAZER
    config = _ler_config(raiz)
    if config is None:
        return OK
    cred = _ler_pareamento(raiz)
    token = cred.get("token") if isinstance(cred.get("token"), str) else ""
    destino = _alvo_limpo(cred.get("alvo")) or _alvo_limpo(alvo)
    if not token or not destino:
        return SEM_PAREAMENTO
    codigo, resposta = abrir("POST", destino + "/agente/servidor/ordens", {}, token,
                             ESPERA)
    if codigo == 401:
        saida("O painel nao reconhece mais este servidor. Cole a linha do painel"
              " de novo neste servidor.")
        return SEM_PAREAMENTO
    if codigo == 429:
        return OK
    if codigo != 200:
        return SEM_REDE
    ordem = (resposta or {}).get("ordem")
    if not isinstance(ordem, dict) or not _hex_de(ordem.get("numero"), 32):
        return OK
    numero = ordem["numero"]
    agora = agora() if callable(agora) else agora

    def recusar(motivo):
        _contar(destino, token, abrir, numero, "recusada", None, motivo)
        return OK

    lido = _ler_numeros(raiz)
    if lido is None:
        return recusar("cheio")
    numeros = {n: v for n, v in lido[0].items() if v >= agora}
    feitas = [t for t in lido[1] if t > agora - 3600]
    motivo = conferir_ordem(ordem, config, numeros, feitas, agora,
                            lambda: _sistemas(rodar)[1])
    if motivo:
        return recusar(motivo)
    numeros[numero] = ordem["vence"]
    feitas.append(int(agora))
    try:
        _gravar(_p(raiz, ARQUIVO_DOS_NUMEROS),
                json.dumps({"numeros": numeros, "feitas": feitas}), 0o600)
    except OSError:
        return recusar("cheio")
    if ordem["tipo"] == "reiniciar":
        saiu = fazer(list(ARGV_DO_REINICIO) + [ordem["alvo"]], PRAZO_DO_REINICIO)
    else:
        saiu = fazer(list(ARGV_DA_VOLTA) + [ordem["alvo"], "--voltar"], PRAZO_DA_VOLTA)
    if saiu is None:
        _contar(destino, token, abrir, numero, "nao_sei", None, None)
    elif saiu == 0:
        _contar(destino, token, abrir, numero, "feita", 0, None)
    else:
        _contar(destino, token, abrir, numero, "falhou", saiu, None)
    return OK


# ------------------------------------------- ligar e desligar os pedidos (C1)

def texto_do_servico_das_ordens():
    """SEM as diretivas da unidade de medir: `NoNewPrivileges` mata o `sudo`,
    `ProtectSystem` deixa o disco so-leitura para o programa de publicar, e
    `CapabilityBoundingSet` vazio vale para os filhos. A contencao daqui e a
    lista fechada do codigo + a regra exata do sudo + a conferencia da digital."""
    return "\n".join([
        "[Unit]",
        "Description=DERVS - busca e faz os pedidos do painel neste servidor",
        "",
        "[Service]",
        "Type=oneshot",
        "User=" + USUARIO,
        "ExecStart=%s %s ordens" % (sys.executable or "/usr/bin/python3", PROGRAMA),
        "TimeoutStartSec=30min",
        "PrivateTmp=yes",
        ""])


def texto_do_temporizador_das_ordens():
    return "\n".join([
        "[Unit]",
        "Description=DERVS - buscar pedidos do painel a cada 30 segundos",
        "",
        "[Timer]",
        "OnBootSec=45s",
        "OnUnitActiveSec=30s",
        "AccuracySec=1s",
        "",
        "[Install]",
        "WantedBy=timers.target",
        ""])


def _linha_do_sudoers(projeto):
    """Uma regra por projeto, argumentos exatos, sem curinga."""
    return (USUARIO + " ALL=(root) " + "NOPASSWD" + ":" + " " + ARGV_DA_VOLTA[2]
            + " " + projeto + " --voltar")


def _comando_de_publicar_ok(raiz):
    """O programa de publicar so pode ser trocado pelo root? Dono root, sem
    escrita de grupo/outros, e o mesmo nas duas pastas acima dele. Senao uma
    regra de `sudo` para ele seria uma porta para quem puder trocar o arquivo."""
    caminho = ARGV_DA_VOLTA[2]
    pastas = (os.path.dirname(caminho), os.path.dirname(os.path.dirname(caminho)))
    try:
        for dado, eh_pasta in ((caminho, False), (pastas[0], True), (pastas[1], True)):
            e = os.lstat(_p(raiz, dado))
            if e.st_uid != 0 or e.st_mode & 0o022:
                return False
            if not (stat.S_ISDIR(e.st_mode) if eh_pasta else stat.S_ISREG(e.st_mode)):
                return False
    except OSError:
        return False
    return True


def _voltaveis(raiz):
    """Projetos que ja publicaram (historico) e que o ajudante pode voltar."""
    nomes = []
    for p in _publicacoes(raiz):
        nome = p["projeto"]
        if (_ALVO_VOLTAR.fullmatch(nome) and not _bloqueado(nome)
                and nome not in nomes):
            nomes.append(nome)
    return nomes[:MAX_VOLTAVEIS]


def _sem_arquivo(caminho):
    try:
        os.unlink(caminho)
    except OSError:
        pass


def _ordens_desligar(raiz, rodar):
    """Apaga tudo o que os pedidos puseram. True se havia algo."""
    caminhos = [_p(raiz, c) for c in (TEMPORIZADOR_DAS_ORDENS, SERVICO_DAS_ORDENS,
                                      SUDOERS, SUDOERS_NOVO)]
    pasta = _p(raiz, PASTA_DAS_ORDENS)
    if not any(os.path.exists(c) for c in caminhos) and not os.path.exists(pasta):
        return False
    if os.path.exists(caminhos[0]):
        rodar(["systemctl", "disable", "--now", "dervs-ajudante-ordens.timer"], 60)
    for c in caminhos:
        _sem_arquivo(c)
    shutil.rmtree(pasta, ignore_errors=True)
    rodar(["systemctl", "daemon-reload"], 60)
    return True


def _chaves_da_linha(textos):
    """["x.y", ...] da linha -> lista de pares de hex, ou None se algo torto."""
    if not isinstance(textos, list) or not 1 <= len(textos) <= MAX_CHAVES:
        return None
    pares = []
    for texto in textos:
        par = texto.split(".") if isinstance(texto, str) else []
        if _ponto_de(par) is None:
            return None
        pares.append(par)
    return pares


def _ordens_ligar(textos, alvo, raiz, rodar, saida):
    """Liga os pedidos. Nunca derruba a instalacao: o que nao deu so deixa os
    pedidos desligados, e a medicao segue. True se ficaram ligados."""
    pares = _chaves_da_linha(textos)
    host = urllib.parse.urlsplit(alvo).hostname
    if pares is None or not host:
        _ordens_desligar(raiz, rodar)
        saida("As chaves da linha estao tortas; os pedidos NAO foram ligados."
              " Copie a linha do painel de novo.")
        return False
    voltaveis, porque = [], ""
    if _comando_de_publicar_ok(raiz):
        voltaveis = _voltaveis(raiz)
        if not voltaveis:
            porque = "nenhum projeto deste servidor ja foi publicado"
    else:
        porque = "o programa de publicar nao esta onde ou como eu espero"
    novo, final = _p(raiz, SUDOERS_NOVO), _p(raiz, SUDOERS)
    if voltaveis:
        aceito = False
        try:
            os.makedirs(os.path.dirname(final), mode=0o755, exist_ok=True)
            _gravar(novo, "".join(_linha_do_sudoers(p) + "\n" for p in voltaveis),
                    0o440)
            if rodar(["visudo", "-cf", novo], 30)[0]:
                os.replace(novo, final)
                aceito = True
        except OSError:
            pass
        if not aceito:
            _sem_arquivo(novo)
            _sem_arquivo(final)
            voltaveis, porque = [], "o sistema nao aceitou a regra de voltar versao"
    else:
        _sem_arquivo(final)
    config = {"versao": 1, "ident": secrets.token_hex(16), "origem": alvo,
              "rp_id": host, "chaves": pares, "voltaveis": voltaveis}
    try:
        pasta = _p(raiz, PASTA_DAS_ORDENS)
        os.makedirs(pasta, mode=0o755, exist_ok=True)
        _gravar(_p(raiz, ARQUIVO_DAS_ORDENS), json.dumps(config), 0o644)
        for caminho, texto in ((SERVICO_DAS_ORDENS, texto_do_servico_das_ordens()),
                               (TEMPORIZADOR_DAS_ORDENS,
                                texto_do_temporizador_das_ordens())):
            _gravar(_p(raiz, caminho), texto, 0o644)
    except OSError:
        _ordens_desligar(raiz, rodar)
        saida("Nao consegui preparar os pedidos; ficaram DESLIGADOS.")
        return False
    rodar(["systemctl", "daemon-reload"], 60)
    if not rodar(["systemctl", "enable", "--now", "dervs-ajudante-ordens.timer"], 60)[0]:
        _ordens_desligar(raiz, rodar)
        saida("Nao consegui ligar o temporizador dos pedidos; ficaram DESLIGADOS.")
        return False
    if voltaveis:
        saida("Pedidos ligados: reiniciar sistemas; voltar a versao de: "
              + ", ".join(voltaveis) + ". O Ajudei fica de fora sempre.")
    else:
        saida("Pedidos ligados: reiniciar sistemas. Voltar a versao ficou de fora: "
              + porque + ". O Ajudei fica de fora sempre.")
    return True


# -------------------------------------------------------------------- remover

def remover(raiz="/", rodar=None, eh_root=None):
    rodar = rodar or _RODAR
    if not (eh_root() if eh_root is not None else _root()):
        print("Preciso de poder de administrador. Rode de novo assim:")
        print("  sudo python3 " + PROGRAMA + " remover")
        return SEM_ROOT
    rodar(["systemctl", "disable", "--now", "dervs-ajudante.timer"], 60)
    for caminho in (SERVICO, TEMPORIZADOR):
        try:
            os.unlink(_p(raiz, caminho))
        except OSError:
            pass
    rodar(["systemctl", "daemon-reload"], 60)
    _ordens_desligar(raiz, rodar)
    pasta_log = _p(raiz, PASTA_DO_HISTORICO)
    if os.path.isdir(pasta_log) and shutil.which("setfacl"):
        rodar(["setfacl", "-P", "-x", "u:" + USUARIO, pasta_log], 10)
        arquivo_log = _p(raiz, HISTORICO)
        if os.path.isfile(arquivo_log):
            rodar(["setfacl", "-P", "-x", "u:" + USUARIO, arquivo_log], 10)
        rodar(["setfacl", "-P", "-d", "-x", "u:" + USUARIO, pasta_log], 10)
    rodar(["userdel", USUARIO], 30)
    shutil.rmtree(_p(raiz, PASTA_DO_PROGRAMA), ignore_errors=True)
    shutil.rmtree(_p(raiz, PASTA_DOS_DADOS), ignore_errors=True)
    print("Removido deste servidor. Para tira-lo tambem da lista, clique em")
    print("Desligar este servidor no painel.")
    return OK


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    comando = argv[0] if argv else "instalar"
    if comando == "instalar":
        if len(argv) <= 1:
            return instalar()
        if len(argv) == 3 and argv[1] == "--ordens":
            return instalar(ordens=argv[2].split(","))
    elif comando == "medir":
        return medir()
    elif comando == "ordens":
        return ordens()
    elif comando == "remover":
        return remover()
    print("Uso: python3 dervs-ajudante.py [instalar | medir | ordens | remover]")
    return 1


if __name__ == "__main__":
    sys.exit(main())
