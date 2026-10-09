"""O ajudante do servidor: instala, pareia e conta ao DERVS o que roda ali.

Este arquivo e baixado do painel, conferido por SHA-256 e rodado UMA vez com
`sudo python3 dervs-ajudante.py`. Depois disso um temporizador do sistema o
chama a cada 30 segundos com `medir`, num usuario so dele, e ele manda ao
painel o inventario: quais sistemas estao de pe, desde quando e qual versao foi
publicada por ultimo. `remover` desfaz tudo.

LEIS QUE ESTE ARQUIVO OBEDECE, e o motivo de cada uma:

1. UM ARQUIVO, BIBLIOTECA PADRAO PURA, PYTHON 3.8. Roda num servidor onde nada
   foi instalado e onde o repositorio nao existe. `test_ajudante_servidor.py`
   le o proprio fonte com `ast` e reprova import de fora, ou sintaxe nova.

2. SO OLHA. O grupo `docker` equivale a administrador: o "so olhar" aqui e do
   CODIGO, nao do sistema. Por isso so dois comandos de leitura do Docker
   existem (`ARGV_DO_PS` e `ARGV_DO_INSPECT`), o formato do segundo escolhe os
   campos um a um, e o teste reprova qualquer outro jeito de chamar o Docker.
   O servidor do painel tambem nao entrega nada de volta a este programa: ele
   nao recebe ordem, nao se atualiza e nao le configuracao dos sistemas.

3. NADA SEGREDO NO QUE SAI. Quem fez a publicacao (o 4o campo do historico) e
   descartado na leitura. O que sobe e uma lista fechada de campos.

4. FALHA FECHADA. Qualquer passo que nao deu para e diz o motivo em portugues,
   com um codigo de saida proprio. Nunca levanta para quem chamou.

5. ASCII PURO. O servidor do painel monta este arquivo em ASCII; um acento
   derruba a rota.
"""

import datetime
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
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
        except OSError:
            bruto = b""
    except (urllib.error.URLError, OSError, ValueError):
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


def _gravar(caminho, texto, modo):
    """Grava por arquivo novo + troca atomica: nunca um arquivo pela metade."""
    passagem = caminho + ".novo"
    try:
        os.unlink(passagem)
    except OSError:
        pass
    fd = os.open(passagem, os.O_WRONLY | os.O_CREAT | os.O_EXCL, modo)
    with os.fdopen(fd, "w", encoding="ascii", newline="\n") as arq:
        arq.write(texto)
    os.replace(passagem, caminho)
    if os.name != "nt":
        os.chmod(caminho, modo)


def _ler_pareamento(raiz):
    try:
        with open(_p(raiz, ARQUIVO_DO_PAREAMENTO), encoding="ascii") as arq:
            dados = json.load(arq)
    except (OSError, ValueError):
        return {}
    return dados if isinstance(dados, dict) else {}


def _inteiro(valor, padrao, minimo, maximo):
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
    intervalo = _inteiro(dados.get("intervalo"), 5, 2, 30)
    prazo = _inteiro(dados.get("minutos"), 10, 1, 30) * 60
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


# ------------------------------------------------------------------ instalar

def instalar(alvo=ALVO, raiz="/", rodar=None, abrir=None, dormir=time.sleep,
             eh_root=None, dono=None, nome=None, saida=print):
    rodar = rodar or _RODAR
    abrir = abrir or _ABRIR
    dono = dono or shutil.chown
    alvo = _alvo_limpo(alvo)
    nome = nome or nome_desta_maquina()

    if not (eh_root() if eh_root is not None else _root()):
        saida("Preciso de poder de administrador. Rode de novo assim:")
        saida("  sudo python3 dervs-ajudante.py")
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
    if not token:
        fim, token = _parear(alvo, nome, abrir, dormir, saida)
        if fim != OK:
            return fim
        # O token sai UMA vez do painel: guarda JA, antes de qualquer outro passo.
        arquivo = _p(raiz, ARQUIVO_DO_PAREAMENTO)
        try:
            _gravar(arquivo, json.dumps({"alvo": alvo, "token": token}), 0o600)
            dono(arquivo, USUARIO)
        except (OSError, LookupError):
            saida("Autorizado, mas nao consegui guardar o acesso. Rode de novo.")
            return SEM_REQUISITO
        saida("Autorizado.")

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
    if os.path.isdir(pasta_log) and shutil.which("setfacl"):
        rodar(["setfacl", "-m", "u:%s:x" % USUARIO, pasta_log], 10)
        arquivo_log = _p(raiz, HISTORICO)
        if os.path.isfile(arquivo_log):
            rodar(["setfacl", "-m", "u:%s:r" % USUARIO, arquivo_log], 10)
        rodar(["setfacl", "-d", "-m", "u:%s:r" % USUARIO, pasta_log], 10)

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
    if medir(alvo, raiz, rodar, abrir) != OK:
        saida("A primeira medicao nao subiu agora; o temporizador tenta de novo.")
    saida("Em ate um minuto o servidor aparece no painel, em Seus servidores.")
    saida("Para tirar: sudo python3 " + PROGRAMA + " remover")
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
    """(docker_mudo, lista). `docker_mudo` e verdade quando nao deu para ver."""
    ok, bruto = rodar(list(ARGV_DO_PS), 30)
    if not ok:
        return True, []
    ids = [i for i in bruto.split() if all(c in _HEX for c in i)][:MAX_ITENS]
    if not ids:
        return False, []
    ok, bruto = rodar(list(ARGV_DO_INSPECT) + ids, 60)
    if not ok:
        return True, []
    achados = []
    for linha in bruto.splitlines():
        campos = linha.split("\t")
        if len(campos) != 8:
            continue
        nome = _tira(campos[0]).lstrip("/")
        if not nome:
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
    return False, achados


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


def medir(alvo=ALVO, raiz="/", rodar=None, abrir=None):
    rodar = rodar or _RODAR
    abrir = abrir or _ABRIR
    cred = _ler_pareamento(raiz)
    token = cred.get("token") if isinstance(cred.get("token"), str) else ""
    destino = _alvo_limpo(cred.get("alvo")) or _alvo_limpo(alvo)
    if not token or not destino:
        print("Este servidor ainda nao foi autorizado no painel.")
        return SEM_PAREAMENTO
    mudo, sistemas = _sistemas(rodar)
    corpo = {"versao": 1, "docker_mudo": mudo, "servidor": _servidor(raiz),
             "sistemas": sistemas, "publicacoes": _publicacoes(raiz)}
    codigo, _resposta = abrir("POST", destino + "/agente/servidor", corpo,
                              token, ESPERA)
    if codigo == 200 or codigo == 429:
        return OK
    if codigo == 401:
        print("O painel nao reconhece mais este servidor. Rode a instalacao de novo.")
        return SEM_PAREAMENTO
    if codigo == 403:
        print("O painel recusou a medicao deste servidor.")
        return RECUSADO
    print("Nao consegui falar com o painel agora.")
    return SEM_REDE


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
    pasta_log = _p(raiz, PASTA_DO_HISTORICO)
    if os.path.isdir(pasta_log) and shutil.which("setfacl"):
        rodar(["setfacl", "-x", "u:" + USUARIO, pasta_log], 10)
        arquivo_log = _p(raiz, HISTORICO)
        if os.path.isfile(arquivo_log):
            rodar(["setfacl", "-x", "u:" + USUARIO, arquivo_log], 10)
        rodar(["setfacl", "-d", "-x", "u:" + USUARIO, pasta_log], 10)
    rodar(["userdel", USUARIO], 30)
    shutil.rmtree(_p(raiz, PASTA_DO_PROGRAMA), ignore_errors=True)
    shutil.rmtree(_p(raiz, PASTA_DOS_DADOS), ignore_errors=True)
    print("Removido. No painel este servidor passa a mostrar 'Sem dados'.")
    return OK


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    comando = argv[0] if argv else "instalar"
    if comando == "instalar":
        return instalar()
    if comando == "medir":
        return medir()
    if comando == "remover":
        return remover()
    print("Uso: python3 dervs-ajudante.py [instalar | medir | remover]")
    return 1


if __name__ == "__main__":
    sys.exit(main())
