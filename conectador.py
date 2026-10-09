"""O conectador: o primeiro minuto numa maquina, sem terminal.

Este arquivo e o miolo do `conectar-dervs.cmd` que o painel entrega: o `.cmd`
baixa o Python oficial, extrai ESTE programa do proprio fim e o roda. A pessoa
da dois cliques e pronto: ele pede a pasta dos projetos, faz um pedido ao
painel, abre o navegador para a pessoa clicar em Autorizar, recebe o token,
grava token e pasta em ~/.dervs/agente.json e registra a tarefa agendada que
faz a maquina continuar reportando.

TRES LEIS QUE ESTE ARQUIVO OBEDECE, e o motivo de cada uma:

1. UM ARQUIVO, BIBLIOTECA PADRAO PURA. Nenhum import fora da padrao e nenhum
   import de modulo deste repositorio: ele roda numa maquina onde o repositorio
   pode nem existir. `test_conectador.py` le o proprio fonte com `ast` e
   reprova qualquer import que fuja disso.

2. FALHA FECHADA E SEM LIXO. Fechar a janela sem escolher nao pareia, nao grava
   arquivo nenhum e nao agenda nada - sai com codigo diferente de zero dizendo
   o motivo, em portugues. Meio pareamento e pior que nenhum: ele mente para
   quem olha o painel depois.

3. NADA FORA DE ASCII no que ele imprime. O console do Windows nao mostra, e o
   agente ja e cobrado disso por `test_conectar_ponta_a_ponta.py:266`.

O QUE ELE NAO FAZ, e esta escrito no plano: ele NAO instala o DERVS. Uma
medicao precisa de `coletar.py`, `banco.py` e `tarefas.py` - cerca de 4.600
linhas - na maquina. Quando ele nao acha o repositorio, ele pareia assim mesmo
e DIZ que o relato continuo depende dele. Tarefa agendada que morre calada e
pior que tarefa agendada nenhuma.
"""

import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

# ------------------------------------------------------- o que o painel injeta
#
# O servidor LE este arquivo do disco e troca a linha abaixo antes de entregar
# (`servir.py` nao importa este modulo: importar arrastaria `tkinter` para
# dentro do servidor e para dentro de `test_imagem.modulos_de_runtime()`).
# A marca no fim da linha e o que ele procura: nao a apague. O codigo de seis
# digitos saiu daqui: agora nasce no computador, por `pedir`.
ALVO = ""     # DERVS:ALVO

# O codigo que o painel mostra: 8 caracteres do alfabeto sem 0, 1, I, L e O.
# Entra numa URL, entao so este formato passa.
_CODIGO_CURTO = re.compile(r"[2-9A-HJKMNP-Z]{4}-[2-9A-HJKMNP-Z]{4}")

NOME_DA_TAREFA = "DERVS - reportar"
ESPERA = 60          # segundos de paciencia com a rede
TETO_DA_RESPOSTA = 64 * 1024

SAIU_BEM = 0
SEM_PASTA = 2
SEM_PAREAMENTO = 3
SEM_ALVO = 4
SEM_PACOTE = 5


# ------------------------------------------------------------------- a saida

def fala(texto: str) -> None:
    """Imprime sem quebrar em console que nao aceita acento.

    O console do Windows abre em cp1252 ou cp437 conforme a maquina; um
    caractere fora de ASCII levanta UnicodeEncodeError e o programa morre com
    traceback em vez de com a mensagem. O texto deste arquivo ja e todo ASCII,
    e esta troca e a rede para o que vier de fora (nome de pasta, por exemplo).
    """
    try:
        print(texto)
    except UnicodeEncodeError:
        print(texto.encode("ascii", "replace").decode("ascii"))


def tem_alguem_lendo() -> bool:
    """A pausa do fim so acontece quando ha uma pessoa na frente do console.

    ESTA E A ARMADILHA QUE MORDE PRIMEIRO. O console fechar antes de a pessoa
    ler e o defeito obvio; a pausa dentro da TAREFA AGENDADA e o defeito caro,
    porque o processo fica pendurado para sempre e ninguem ve. O agendador roda
    sem console: `stdin` nao e um terminal, e e isso que separa os dois casos.
    """
    try:
        return bool(sys.stdin and sys.stdin.isatty()
                    and sys.stdout and sys.stdout.isatty())
    except (AttributeError, ValueError):
        return False


def pausa() -> None:
    if not tem_alguem_lendo():
        return
    try:
        input("\nAperte Enter para fechar. ")
    except (EOFError, KeyboardInterrupt):
        pass


# -------------------------------------------------------------------- a pasta

def sugestao_de_pasta() -> str:
    """`%USERPROFILE%\\source\\repos` quando ela existe; a casa quando nao."""
    palpite = Path.home() / "source" / "repos"
    return str(palpite if palpite.is_dir() else Path.home())


def escolher_pasta(sugestao: str = "") -> str:
    """A janela do sistema, com o `input()` como o mesmo caminho por outra porta.

    `import tkinter` VAI dentro do try de proposito. Os builds da Microsoft
    Store vem sem Tcl/Tk, e `tkinter` NAO e instalavel por pip: quem cair nesse
    Python ficaria travado numa janela que nunca abre. E o mesmo galho serve uma
    VPS por SSH, onde nao ha janela grafica nenhuma - e uma VPS e exatamente o
    outro caso de uso desta porta.
    """
    sugestao = sugestao or sugestao_de_pasta()
    if os.name == "nt":
        # O Python embutivel do Windows NAO traz tkinter. A janela vem do
        # PowerShell que o sistema ja tem; so se ele falhar (OSError, Constrained
        # Language Mode, prazo) o programa tenta tkinter e depois o teclado.
        escolhida = pelo_powershell(sugestao)
        if escolhida is not None:
            return escolhida
    try:
        import tkinter
        from tkinter import filedialog
    except Exception:                      # ImportError, e o que mais vier
        return pasta_pelo_teclado(sugestao)
    janela = None
    try:
        janela = tkinter.Tk()
        janela.withdraw()
        escolhida = filedialog.askdirectory(
            title="Onde ficam os seus projetos?", initialdir=sugestao)
    except Exception:
        # O `import` DEU CERTO e a janela nao abriu. E o caso da VPS por SSH
        # com `python3-tk` instalado e sem `DISPLAY`: `Tk()` levanta `TclError`
        # ali dentro. Antes isto caia em `escolhida = ""`, e o programa dizia
        # "voce fechou sem escolher uma pasta" - culpando a pessoa por algo que
        # ela nao fez, e sem lhe dar caminho nenhum. Achado pela revisao de
        # Python, conferido com `Tk()` dublado para levantar.
        return pasta_pelo_teclado(sugestao)
    finally:
        if janela is not None:
            try:
                janela.destroy()
            except Exception:
                pass
    return (escolhida or "").strip()


# ASCII puro. A sugestao NAO entra aqui: vai na variavel de ambiente
# DERVS_SUGESTAO, porque um caminho com aspas no meio do script seria codigo.
# $ErrorActionPreference = Stop faz o Add-Type que falha (Constrained Language
# Mode) sair com codigo de erro, em vez de seguir e nao abrir nada.
_SCRIPT_DA_PASTA = (
    "$ErrorActionPreference = 'Stop'; "
    "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
    "Add-Type -AssemblyName System.Windows.Forms; "
    "$d = New-Object System.Windows.Forms.FolderBrowserDialog; "
    "$d.Description = 'Onde ficam os seus projetos?'; "
    "$d.SelectedPath = $env:DERVS_SUGESTAO; "
    "if ($d.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) "
    "{ [Console]::Out.Write($d.SelectedPath) }")


def pelo_powershell(sugestao: str):
    """A janela de pasta do Windows. "" = a pessoa fechou; None = nao deu.

    Fechar a janela e uma RESPOSTA e devolve "" (quem chama nao pergunta de
    novo). Ja `None` quer dizer que o PowerShell nao serviu, e o proximo
    caminho da fila assume. `-STA` e obrigatorio para o dialogo abrir.
    """
    ambiente = dict(os.environ)
    ambiente["DERVS_SUGESTAO"] = sugestao
    try:
        fim = subprocess.run(
            ["powershell.exe", "-NoProfile", "-STA", "-Command", _SCRIPT_DA_PASTA],
            shell=False, capture_output=True, timeout=900, env=ambiente)
    except (OSError, subprocess.SubprocessError):
        return None
    if fim.returncode != 0:
        return None
    return (fim.stdout or b"").decode("utf-8-sig", "replace").strip()


def pasta_pelo_teclado(sugestao: str) -> str:
    """O mesmo passo por outra porta: sem janela, pergunta e segue."""
    fala("Nao consegui abrir a janela de escolher pasta neste Python.")
    fala("Digite o caminho da pasta onde ficam seus projetos e aperte Enter.")
    fala("Sugestao: " + sugestao)
    try:
        return (input("Pasta: ") or "").strip().strip('"')
    except (EOFError, KeyboardInterrupt):
        return ""


# --------------------------------------------------------------------- a rede

_NOME_OK = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ._-")


def nome_desta_maquina() -> str:
    """O nome do computador no formato que o painel aceita: so letras,
    digitos, espaco, ponto, sublinhado e hifen, ate 40. O resto vira `-`."""
    try:
        bruto = socket.gethostname() or "computador"
    except OSError:
        bruto = "computador"
    return "".join(c if c in _NOME_OK else "-" for c in bruto)[:40].strip()         or "computador"


class _SemRedirecionar(urllib.request.HTTPRedirectHandler):
    """Redirecionar levaria o cabecalho Authorization para outro endereco."""

    def redirect_request(self, *a, **k):
        return None


_ABRIDOR = urllib.request.build_opener(_SemRedirecionar)


def dormir(segundos: float) -> None:
    time.sleep(segundos)


def _chamar(alvo: str, caminho: str, corpo=None, token: str = "",
            teto: int = TETO_DA_RESPOSTA):
    """Uma chamada ao painel. Devolve (codigo, dict); codigo 0 = sem resposta.

    Falha fechada: nunca levanta, quem chama decide o que dizer. Sem corpo e
    GET, com corpo e POST. O token vai so no cabecalho e NUNCA e impresso.
    """
    dados = None if corpo is None else json.dumps(corpo).encode("utf-8")
    pedido = urllib.request.Request(
        alvo.rstrip("/") + caminho, data=dados,
        method="GET" if corpo is None else "POST",
        headers={"Content-Type": "application/json",
                 "User-Agent": "dervs-conectador"})
    if token:
        pedido.add_header("Authorization", "Token " + token)
    try:
        with _ABRIDOR.open(pedido, timeout=ESPERA) as resposta:
            codigo, bruto = resposta.status, resposta.read(teto + 1)
    except urllib.error.HTTPError as e:
        codigo = e.code
        try:
            bruto = e.read(teto + 1)
        except OSError:
            bruto = b""
    except (urllib.error.URLError, OSError, ValueError):
        return 0, {}
    if len(bruto) > teto:
        return codigo, {}
    try:
        resposta_json = json.loads(bruto.decode("utf-8") or "{}")
    except ValueError:
        return codigo, {}
    return codigo, resposta_json if isinstance(resposta_json, dict) else {}


def pedir(alvo: str, nome: str = ""):
    """POST /agente/pedir. Devolve o dicionario do painel, ou None."""
    codigo, dados = _chamar(alvo, "/agente/pedir",
                            {"maquina": nome or nome_desta_maquina()})
    if codigo != 200:
        return None
    if not _CODIGO_CURTO.fullmatch(str(dados.get("codigo") or "")):
        return None
    if len(str(dados.get("pedido") or "")) < 16:
        return None
    return dados


def _inteiro(valor, padrao: int, minimo: int, maximo: int) -> int:
    if isinstance(valor, bool) or not isinstance(valor, int):
        return padrao
    return max(minimo, min(maximo, valor))


def conectar_pelo_navegador(alvo: str, nome: str = "") -> str:
    """Pede, mostra o codigo, abre o navegador e espera o clique. "" = nao deu.

    A pessoa so confere o nome e o codigo na tela do painel e clica em
    Autorizar. O `pedido` (segredo deste computador) nunca e impresso, e o
    token tambem nao. Sem token: nada foi gravado em lugar nenhum.
    """
    nome = nome or nome_desta_maquina()
    dados = pedir(alvo, nome)
    if dados is None:
        return ""
    codigo = dados["codigo"]
    intervalo = _inteiro(dados.get("intervalo"), 5, 2, 30)
    prazo = _inteiro(dados.get("minutos"), 10, 1, 30) * 60
    fala("")
    fala("Este computador: " + nome)
    fala("Codigo: " + codigo)
    fala("Vou abrir o navegador. Confira que o nome e o codigo sao estes e")
    fala("clique em Autorizar. Se voce nao reconhece este pedido, feche a janela.")
    url = alvo.rstrip("/") + "/#/conectar?autorizar=" + codigo
    try:
        abriu = webbrowser.open(url)
    except Exception:                      # navegador ausente, sem sessao grafica
        abriu = False
    if not abriu:
        fala("Nao consegui abrir o navegador. Abra este endereco:")
        fala("  " + url)
    gasto = 0
    while gasto < prazo:
        estado, resposta = _chamar(alvo, "/agente/esperar",
                                   {"pedido": dados["pedido"]})
        if estado == 200:
            return str(resposta.get("token") or "")
        if estado in (400, 401, 403, 404):
            return ""
        if estado == 429:
            intervalo = min(intervalo * 2, 60)
        dormir(intervalo)                  # 202, 5xx ou sem resposta: tenta de novo
        gasto += intervalo
    return ""


# ------------------------------------------------------------------ o arquivo

def arquivo_de_configuracao() -> Path:
    """O MESMO caminho que `agente/enviar.py:47` usa. Fora do repositorio."""
    bruto = os.environ.get("DERVS_AGENTE_ARQUIVO")
    if bruto:
        return Path(bruto).expanduser()
    return Path.home() / ".dervs" / "agente.json"


def _lido(destino: Path) -> dict:
    try:
        dados = json.loads(destino.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return dados if isinstance(dados, dict) else {}


def gravar(alvo: str, token: str, raiz: str, nome: str = "") -> Path:
    """Grava token e raiz DE UMA VEZ, preservando o que ja estava no arquivo.

    O PADRAO DE ESCRITA FOI COPIADO DE `agente/enviar.py:72` (`guardar_token`),
    e nao reinventado. As duas razoes escritas la valem aqui inteiras:

    1. O modo do `os.open` so vale para arquivo NOVO. Escrever direto por cima
       de um destino que ja existe com permissao frouxa deixa o token exposto
       entre a escrita e o `chmod` - e o `chmod` falha em silencio.
    2. `os.replace` e atomico. Uma queda no meio da escrita perderia TODOS os
       tokens desta maquina, e nao so o que estava entrando.

    A chave `raizes` e a mesma que `coletar.py` le (etapa A1): uma lista de
    caminhos, no topo do arquivo. As outras chaves ficam intactas - o token de
    OUTRO alvo mora aqui do lado.
    """
    destino = arquivo_de_configuracao()
    destino.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    dados = _lido(destino)
    dados[alvo.rstrip("/").lower()] = {
        "token": token, "maquina": nome or nome_desta_maquina(),
        "guardado_em": time.strftime("%Y-%m-%dT%H:%M:%S")}
    raizes = [str(r) for r in dados.get("raizes") or [] if str(r).strip()]
    if not any(str(r).lower() == raiz.lower() for r in raizes):
        raizes.append(raiz)
    dados["raizes"] = raizes
    texto = json.dumps(dados, ensure_ascii=False, indent=2)
    passagem = destino.with_name(destino.name + ".novo")
    try:
        passagem.unlink()                 # sobra de uma queda anterior
    except OSError:
        pass
    fd = os.open(passagem, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as arq:
        arq.write(texto)
    os.replace(passagem, destino)
    return destino


# ------------------------------------------------------------------ o pacote

# O pacote do painel (contrato C6) e CODIGO que este PC vai executar: so passa
# nome de arquivo `.py` da raiz ou de `agente/`, em minusculas, sem barra
# invertida, sem `..`, sem caminho absoluto. UM caminho fora disso recusa o
# pacote INTEIRO - pacote parcial seria um programa que ninguem testou.
TETO_DO_PACOTE = 16 * 1024 * 1024
_CAMINHO_DO_PACOTE = re.compile(r"(agente/)?[a-z_]{1,40}\.py")


def casa_do_programa() -> Path:
    """Onde o programa mora nesta maquina. Fora da pasta de projetos."""
    bruto = os.environ.get("DERVS_CASA")
    if bruto:
        return Path(bruto).expanduser()
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / "DERVS" / "programa"
    return Path.home() / ".dervs" / "programa"


def buscar_pacote(alvo: str, token: str):
    """GET /agente/pacote. Devolve (codigo, dict)."""
    return _chamar(alvo, "/agente/pacote", token=token, teto=TETO_DO_PACOTE)


def gravar_pacote(pacote, casa: Path) -> bool:
    """Valida TUDO e so depois grava. False = nada foi gravado."""
    arquivos = pacote.get("arquivos") if isinstance(pacote, dict) else None
    if not isinstance(arquivos, list) or not arquivos:
        return False
    prontos = {}
    for item in arquivos:
        if not isinstance(item, dict):
            return False
        caminho, conteudo = item.get("caminho"), item.get("conteudo")
        if not isinstance(caminho, str) or not isinstance(conteudo, str):
            return False
        if not _CAMINHO_DO_PACOTE.fullmatch(caminho):
            return False
        try:
            prontos[caminho] = conteudo.encode("utf-8")
        except UnicodeEncodeError:
            return False
    if "agente/enviar.py" not in prontos:
        return False
    try:
        (casa / "agente").mkdir(parents=True, exist_ok=True)
        for caminho, bruto in prontos.items():
            destino = casa / caminho
            passagem = destino.with_name(destino.name + ".novo")
            passagem.write_bytes(bruto)
            os.replace(passagem, destino)
    except OSError:
        return False
    return True


def primeiro_relato(agente: str, alvo: str) -> bool:
    """Roda o agente uma vez, com o Python do console, para o painel ja ver dados."""
    try:
        fim = subprocess.run([sys.executable, agente, "--alvo", alvo.rstrip("/")],
                             shell=False, capture_output=True, timeout=180)
    except (OSError, subprocess.SubprocessError):
        return False
    if fim.returncode != 0:
        fala("O primeiro relato falhou:")
        fala((fim.stderr or b"")[-400:].decode("utf-8", "replace").strip())
        return False
    return True


# ------------------------------------------------------------ a tarefa agendada

def interprete_da_tarefa() -> str:
    """`pythonw.exe` (sem janela) ao lado do Python do console, quando existe.

    A tarefa agendada roda a cada login; com `python.exe` ela abriria uma
    janela preta de console toda vez.
    """
    atual = sys.executable or "python"
    sem_janela = Path(atual).with_name("pythonw.exe")
    try:
        if sem_janela.is_file():
            return str(sem_janela)
    except OSError:
        pass
    return atual


def comando_da_tarefa(agente: str, alvo: str, uma_vez: bool = False,
                      interprete: str = "") -> str:
    """O valor de /TR, montado como DADO.

    `schtasks` tem regra de aspas propria: o valor de /TR e uma linha de comando
    que o agendador reexecuta, e um caminho com espaco (`C:\\Program Files`)
    sem aspas vira dois argumentos la dentro. As aspas entram AQUI, uma vez, e
    `test_conectador.py` prova isso com um caminho com espaco.
    """
    fim = "" if uma_vez else " --intervalo 60"
    return '"%s" "%s" --alvo "%s"%s' % (
        interprete or sys.executable or "python", agente, alvo.rstrip("/"), fim)


def argumentos_do_schtasks(agente: str, alvo: str, plano_b: bool = False,
                           interprete: str = "") -> list:
    """A LISTA de argumentos. Nunca string unica, nunca `shell=True`.

    Uma string unica com `shell=True` faz o caminho da pasta escolhida pela
    pessoa atravessar o interpretador de comandos do Windows. Lista fecha isso
    de uma vez: o sistema recebe argumento por argumento.

    `ONLOGON` exige administrador e, sem ele, falha com "Acesso negado" - foi
    assim que um computador ficou 26 dias calado. O plano B, `MINUTE`, nao
    exige: a tarefa acorda a cada 10 minutos e o agente reporta UMA vez e sai.
    """
    if plano_b:
        return ["schtasks", "/Create", "/TN", NOME_DA_TAREFA,
                "/TR", comando_da_tarefa(agente, alvo, True, interprete),
                "/SC", "MINUTE", "/MO", "10", "/F"]
    return ["schtasks", "/Create", "/TN", NOME_DA_TAREFA,
            "/TR", comando_da_tarefa(agente, alvo, False, interprete),
            "/SC", "ONLOGON", "/F"]


def agendar(agente: str, alvo: str, plano_b: bool = False,
            interprete: str = "") -> bool:
    """Registra a tarefa. Devolve False sem levantar quando nao deu.

    `schtasks` e do Windows. No macOS e no Linux este arquivo pareia e grava a
    raiz, e NAO agenda nada - e quem chama diz isso, em vez de fingir que
    agendou.
    """
    if os.name != "nt":
        return False
    try:
        fim = subprocess.run(
            argumentos_do_schtasks(agente, alvo, plano_b, interprete),
            shell=False, capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return False
    return fim.returncode == 0


# ---------------------------------------------------------------------- o fluxo

def perguntar(rotulo: str) -> str:
    try:
        return (input(rotulo) or "").strip()
    except (EOFError, KeyboardInterrupt):
        return ""


def token_gravado(alvo: str) -> str:
    """O token que este PC ja tem para este alvo ("" se nao tem)."""
    gravado = _lido(arquivo_de_configuracao()).get(alvo.rstrip("/").lower())
    if not isinstance(gravado, dict):
        return ""
    return str(gravado.get("token") or "")


def _sem_pacote(gravou: bool = False) -> int:
    fala("")
    if gravou:
        # O token so existe uma vez (o painel nao o entrega de novo): ja esta
        # guardado, e a proxima rodada entra por ele sem pedir nada.
        fala("Nao consegui receber o programa do painel agora, mas este")
        fala("computador ja esta autorizado. Rode este arquivo de novo em")
        fala("alguns minutos.")
    else:
        fala("Nao consegui receber o programa do painel. Nada foi gravado neste")
        fala("computador. Tente de novo em alguns minutos.")
    pausa()
    return SEM_PACOTE


def main() -> int:
    fala("=" * 62)
    fala("DERVS - conectar este computador")
    fala("=" * 62)

    alvo = (ALVO or os.environ.get("DERVS_ALVO") or "").strip()
    if not alvo:
        alvo = perguntar("Endereco do painel (ex.: https://dervs.com.br): ")
    if not alvo:
        fala("")
        fala("Sem o endereco do painel nao da para conectar. Nada foi alterado.")
        pausa()
        return SEM_ALVO

    fala("")
    fala("Passo 1 de 3 - escolha a pasta onde ficam os seus projetos.")
    pasta = escolher_pasta()
    if not pasta or not Path(pasta).is_dir():
        # NADA aconteceu ate aqui: nem rede, nem arquivo, nem agendador.
        fala("")
        fala("Voce fechou sem escolher uma pasta. Nada foi alterado neste")
        fala("computador: nenhum token gravado e nenhuma tarefa criada.")
        pausa()
        return SEM_PASTA
    fala("Pasta escolhida: " + str(pasta))

    nome = nome_desta_maquina()
    cred = token_gravado(alvo)
    pacote = {}
    if cred:
        # Este PC ja foi ligado: nao pede de novo. O pacote e a prova de que o
        # token ainda vale (401 = recusado, e ai pareia como se fosse a 1a vez).
        codigo, pacote = buscar_pacote(alvo, cred)
        if codigo == 401:
            cred = ""
        elif codigo != 200:
            return _sem_pacote()
    if not cred:
        fala("")
        fala("Passo 2 de 3 - conectando com o painel pelo navegador.")
        cred = conectar_pelo_navegador(alvo, nome)
        if not cred:
            fala("")
            fala("O painel nao liberou este computador (o pedido vale 10 minutos).")
            fala("Rode este arquivo de novo e clique em Autorizar no navegador.")
            fala("Nada foi alterado neste computador.")
            pausa()
            return SEM_PAREAMENTO
        # O token sai UMA vez do painel: guarda JA, antes de qualquer outra
        # chamada que possa falhar (o pacote), senao o resgate se perde.
        gravar(alvo, cred, str(pasta), nome)
        codigo, pacote = buscar_pacote(alvo, cred)
        if codigo != 200:
            return _sem_pacote(gravou=True)

    if pacote.get("so_mede") is not True:
        # Este PC tem o braco executor ligado (ou o painel nao disse): trocar a
        # tarefa agendada o mataria. So acrescenta a pasta.
        gravar(alvo, cred, str(pasta), nome)
        fala("")
        fala("Este computador ja estava ligado ao painel e faz mais do que medir.")
        fala("Acrescentei a pasta escolhida e nao mexi no resto.")
        pausa()
        return SAIU_BEM

    casa = casa_do_programa()
    if not gravar_pacote(pacote, casa):
        return _sem_pacote(gravou=True)
    gravar(alvo, cred, str(pasta), nome)
    fala("Conectado. Este computador ja aparece no painel.")

    fala("")
    fala("Passo 3 de 3 - manter o relato ligado sozinho.")
    agente = str(casa / "agente" / "enviar.py")
    interprete = interprete_da_tarefa()
    if agendar(agente, alvo, interprete=interprete):
        fala("Pronto: a tarefa '" + NOME_DA_TAREFA + "' roda a cada login.")
    elif os.name != "nt":
        fala("Este sistema nao e Windows, entao NAO agendei nada - o agendador")
        fala("usado aqui e o do Windows. Para reportar sozinho, chame:")
        fala("  python " + agente + " --alvo " + alvo.rstrip("/") + " --intervalo 60")
    elif agendar(agente, alvo, plano_b=True, interprete=interprete):
        fala("Sem permissao de administrador para rodar a cada login, entao usei")
        fala("o plano B: a tarefa '" + NOME_DA_TAREFA + "' acorda a cada 10 minutos.")
    else:
        fala("Nao consegui criar a tarefa agendada (o Windows pode ter pedido")
        fala("permissao de administrador). O pareamento acima valeu. Para")
        fala("reportar agora, chame:")
        fala("  python " + agente + " --alvo " + alvo.rstrip("/") + " --intervalo 60")

    fala("")
    fala("Mandando a primeira medicao...")
    if primeiro_relato(agente, alvo):
        fala("Pronto. Esta janela fecha em 10 segundos.")
        dormir(10)
    else:
        fala("O computador esta ligado, mas a primeira medicao nao subiu agora.")
        fala("A tarefa agendada tenta de novo sozinha.")
        pausa()
    return SAIU_BEM


if __name__ == "__main__":
    sys.exit(main())
