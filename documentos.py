# -*- coding: utf-8 -*-
"""O leitor de documentacao e a conta do progresso de cada projeto.

O DERVS mede "quanto o projeto esta desenvolvido" lendo os criterios de
aceitacao dos `docs/esteira/<slug>/briefing.md`. Este modulo e a fonte UNICA de
tres coisas, para que o agente (que le o disco) e o servidor (que conta) nunca
discordem:

  - o formato do documento (`ler_briefing`, `ler_projeto`);
  - a lista fechada de provas (`prova_permitida`);
  - a conta (`progresso`, `detalhar`).

PURO DE PROPOSITO. So biblioteca padrao, nenhum processo filho, nada de banco,
de fila ou de execucao: `servir.py` e `coletar.py` o importam, e a imagem so
leva o que `servir.py` alcanca (`test_imagem.PROIBIDOS`). Os padroes de texto
sao compilados AQUI, no topo: `test_rotas` reprova qualquer `compile` alcancavel
a partir de uma rota, e compilar dentro de funcao seria esse caso.

O QUE ESTE MODULO NUNCA FAZ: rodar a prova. Nesta entrega nenhuma prova roda
(fase 2). Por isso todo criterio sai "nao verificado": `[x]` escrito a mao e uma
DECLARACAO (`declarados`), e declaracao nunca entra em `comprovados`. Um numero
de progresso que conta o que ninguem provou e o numero errado com cara de certo
que a Lei 2 do painel proibe.

FORMATO (o mesmo texto esta em `docs/A-DOCUMENTACAO-QUE-O-DERVS-LE.md`):

  - arquivo `docs/esteira/<slug>/briefing.md`, slug `[a-z0-9][a-z0-9-]{0,79}`;
  - a secao e a linha exata `## criterio_de_aceitacao`, ate a proxima `## `;
  - criterio: linha `- [ ] texto` ou `- [x] texto`, sem recuo. Item numerado
    (`1. `) dentro da secao e ERRO, nao criterio;
  - prova (opcional): linha `Prova: comando` LOGO ABAIXO do criterio;
  - aprovacao: linha `Aprovado em: AAAA-MM-DD`, FORA da secao.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path

VERSAO = 1

# Tetos. Cortar sempre deixa marca em `erros` do documento: um numero calculado
# sobre a parte que coube, sem dizer que houve corte, e mentira por omissao.
MAX_DOCUMENTOS = 30
MAX_CRITERIOS = 40          # por documento
MAX_TEXTO = 300
MAX_PROVA = 200
MAX_ARQUIVO = 256 * 1024
MAX_ERROS = 10              # por documento
MAX_VARRIDOS = 120          # briefings ABERTOS por leitura, com ou sem criterio
# O projeto INTEIRO e descartado pelo servidor acima de 64 KiB
# (`banco.MAX_BYTES_POR_PROJETO`), e uma chave gorda derruba todas as outras
# medidas junto. Esta chave nunca passa de 24 KiB.
MAX_JSON = 24 * 1024

SECAO = "## criterio_de_aceitacao"

SLUG = re.compile(r"[a-z0-9][a-z0-9-]{0,79}")
_CRITERIO = re.compile(r"- \[( |x|X)\] (.+)")
_NUMERADO = re.compile(r"\s*[0-9]+\.\s.*")
_PROVA = re.compile(r"\s*Prova:\s*(.+)")
_MAL_FORMADO = re.compile(r"\s*[-*+]\s*\[[ xX]?\].*")
_APROVADO = re.compile(r"Aprovado em:\s*([0-9]{4}-[0-9]{2}-[0-9]{2})\s*")

# A lista fechada de provas. Duas trancas INDEPENDENTES, e as duas valem:
# primeiro o conjunto de caracteres proibidos (recusa com motivo proprio), depois
# a forma inteira tem de casar com um destes tres padroes. Tirar uma das duas
# ainda deixa a outra de pe — e cada uma tem o seu teste.
_PROVA_PYTHON = re.compile(r"python (test_[A-Za-z0-9_]+\.py)")
_PROVA_PYTEST = re.compile(
    r"python -m pytest ([A-Za-z0-9_][A-Za-z0-9_./-]*\.py)")
_PROVA_NPM = re.compile(r"npm test")
# `% ^ \` entram porque `npm` (e o `.CMD` do Windows) passa pelo interpretador
# de comandos, que os trata como metacaracteres.
CARACTERES_PROIBIDOS = frozenset(";&|$`<>()\"'\n\r\t\\%^")

PALAVRAS_SENSIVEIS = ("senha", "token", "segredo", "chave", "pagamento",
                      "paciente", "prontuario", "autentica", "login",
                      "migration", "deploy", "producao")


# ---------------------------------------------------------------- o parser
def _data_valida(texto) -> bool:
    if not isinstance(texto, str) or not _APROVADO.fullmatch(
            "Aprovado em: " + texto):
        return False
    try:
        datetime.strptime(texto, "%Y-%m-%d")
    except ValueError:
        return False
    return True


def ler_briefing(texto, slug) -> dict:
    """Um briefing vira `{slug, arquivo, aprovado_em, erros, cortado, criterios}`.

    Nunca levanta: texto estranho vira lista de erros. Briefing sem a secao nao
    e erro e nao tem criterio (e briefing antigo: aparece "sem documentacao").
    """
    erros = []
    cortado = False
    texto = texto if isinstance(texto, str) else ""
    if len(texto) > MAX_ARQUIVO:
        texto = texto[:MAX_ARQUIVO]
        cortado = True
        erros.append("arquivo maior que 256 KiB: só o começo foi lido")

    linhas = texto.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    criterios = []
    aprovado_em = ""
    viu_aprovacao = False
    dentro = False
    alvo = None          # o criterio que aceita a linha `Prova:` logo abaixo
    excedentes = 0
    textos_cortados = 0

    for linha in linhas:
        if linha.startswith("## "):
            dentro = linha.rstrip() == SECAO
            alvo = None
            continue
        if not dentro:
            m = _APROVADO.fullmatch(linha)
            if m and not viu_aprovacao:
                viu_aprovacao = True
                if _data_valida(m.group(1)):
                    aprovado_em = m.group(1)
                else:
                    erros.append("data de aprovação inválida: use AAAA-MM-DD")
            continue

        m = _CRITERIO.fullmatch(linha)
        if m and m.group(2).strip():
            alvo = None
            if len(criterios) >= MAX_CRITERIOS:
                excedentes += 1
                alvo = {}        # descarta tambem a prova dele, sem acusar "solta"
                continue
            corpo = m.group(2).strip()
            if len(corpo) > MAX_TEXTO:
                corpo = corpo[:MAX_TEXTO]
                textos_cortados += 1
            alvo = {"n": len(criterios) + 1, "texto": corpo,
                    "marcado": m.group(1) in ("x", "X"), "prova": ""}
            criterios.append(alvo)
            continue
        if _NUMERADO.fullmatch(linha):
            alvo = None
            erros.append("critério numerado não conta: use - [ ]")
            continue
        m = _PROVA.fullmatch(linha)
        if m:
            if alvo is None:
                erros.append("prova solta: a linha Prova: precisa vir logo "
                             "abaixo de um critério")
            elif "prova" in alvo and not alvo["prova"]:
                valor = m.group(1).strip()
                if len(valor) > MAX_PROVA:
                    # Cortar poderia fabricar OUTRO comando valido.
                    erros.append("prova longa demais (máximo 200 caracteres)")
                else:
                    alvo["prova"] = valor
            alvo = None      # so uma prova por criterio; a segunda e solta
            continue
        if _MAL_FORMADO.fullmatch(linha) or _CRITERIO.fullmatch(linha):
            alvo = None
            erros.append("critério mal formado: use - [ ] texto ou - [x] texto, "
                         "sem recuo")
            continue
        alvo = None

    if excedentes:
        cortado = True
        erros.append("%d critério(s) além do limite de %d foram ignorados"
                     % (excedentes, MAX_CRITERIOS))
    if textos_cortados:
        cortado = True
        erros.append("%d critério(s) tiveram o texto cortado em %d caracteres"
                     % (textos_cortados, MAX_TEXTO))
    if len(erros) > MAX_ERROS:
        erros = erros[:MAX_ERROS]
        cortado = True
    return {"slug": slug, "arquivo": _arquivo_de(slug),
            "aprovado_em": aprovado_em, "erros": erros, "cortado": cortado,
            "criterios": criterios}


def _arquivo_de(slug) -> str:
    return "docs/esteira/%s/briefing.md" % slug


def _tamanho(obj) -> int:
    return len(json.dumps(obj, ensure_ascii=False).encode("utf-8"))


def _caber(docs: list) -> None:
    """Corta do FIM ate o pacote caber em MAX_JSON. So o ultimo documento que
    sobrar fica cortado pela metade; os de tras saem inteiros."""
    reserva = 512                       # para as duas notas que entram depois
    tirados = 0
    cortou = False
    while docs and _tamanho({"versao": VERSAO, "documentos": docs}) > \
            MAX_JSON - reserva:
        excesso = _tamanho({"versao": VERSAO, "documentos": docs}) \
            - (MAX_JSON - reserva)
        while excesso > 0 and docs:
            ultimo = docs[-1]
            if ultimo["criterios"]:
                c = ultimo["criterios"].pop()
                excesso -= _tamanho(c) + 2
                ultimo["cortado"] = True
                cortou = True
            else:
                excesso -= _tamanho(docs.pop()) + 2
                tirados += 1
                cortou = True
    if not cortou or not docs:
        return
    ultimo = docs[-1]
    ultimo["cortado"] = True
    ultimo["erros"].append("critérios cortados para caber no relatório "
                           "(24 KiB por projeto)")
    if tirados:
        ultimo["erros"].append("%d documento(s) não couberam no relatório"
                               % tirados)


def ler_projeto(raiz) -> dict:
    """Le `docs/esteira/*/briefing.md` de um repositorio.

    Devolve `{"versao": 1, "documentos": [...]}`. Pasta ausente = lista vazia
    (e uma resposta: "nao ha documentacao"). Briefing sem criterio e sem erro
    nao entra. Um arquivo que nao deu para ler e pulado sem derrubar o resto.
    Quem chama trata excecao como "nao sei" e OMITE a chave.
    """
    raiz = Path(raiz)
    base = raiz / "docs" / "esteira"
    docs = []
    if base.is_dir():
        # `resolve()` segue link simbolico E junction do Windows (que
        # `is_symlink()` nao ve). Tudo o que for lido tem de continuar DENTRO do
        # repositorio depois de resolvido, senao o conteudo de fora entraria no
        # relatorio. Recusar e dizer: calar apagaria o motivo do "sem documentacao".
        try:
            dentro = raiz.resolve()
            esteira = base.resolve()
            if not (esteira.is_relative_to(dentro / "docs")
                    and (dentro / "docs").resolve().is_relative_to(dentro)):
                raise OSError("fora do repositório")
        except (OSError, ValueError, RuntimeError):
            return {"versao": VERSAO, "documentos": [{
                "slug": "docs", "arquivo": "docs/esteira", "aprovado_em": "",
                "erros": ["a pasta docs/esteira aponta para fora do "
                          "repositório (link): não foi lida"],
                "cortado": False, "criterios": []}]}
        varridos = 0
        for pasta in sorted(base.iterdir(), key=lambda p: p.name):
            if len(docs) > MAX_DOCUMENTOS:
                break              # o 31o so prova que ha mais; nao abre o resto
            if not SLUG.fullmatch(pasta.name):
                continue
            arquivo = pasta / "briefing.md"
            # Link simbolico nao: ele poderia apontar para fora do repositorio
            # e o conteudo de la entraria no relatorio.
            if (pasta.is_symlink() or not pasta.is_dir()
                    or arquivo.is_symlink() or not arquivo.is_file()):
                continue
            try:
                if not (arquivo.resolve().is_relative_to(esteira)
                        and pasta.resolve().is_relative_to(esteira)):
                    continue
            except (OSError, ValueError, RuntimeError):
                continue
            # Briefing sem criterio nao vira documento, mas abrir custa igual:
            # o teto de aberturas vale para quem so tem arquivo antigo.
            if varridos >= MAX_VARRIDOS:
                break
            varridos += 1
            try:
                with arquivo.open("rb") as f:
                    bruto = f.read(MAX_ARQUIVO + 1)
            except OSError:
                continue
            grande = len(bruto) > MAX_ARQUIVO
            d = ler_briefing(bruto[:MAX_ARQUIVO].decode("utf-8-sig", "replace"),
                             pasta.name)
            if grande and not d["cortado"]:
                d["cortado"] = True
                d["erros"].append("arquivo maior que 256 KiB: só o começo "
                                  "foi lido")
            if not d["criterios"] and not d["erros"]:
                continue
            docs.append(d)
    if len(docs) > MAX_DOCUMENTOS:
        docs = docs[:MAX_DOCUMENTOS]
        docs[-1]["cortado"] = True
        docs[-1]["erros"].append("há mais documentos que o limite de %d; o "
                                 "resto foi ignorado" % MAX_DOCUMENTOS)
    _caber(docs)
    return {"versao": VERSAO, "documentos": docs}


# ----------------------------------------------------------- a prova permitida
def prova_permitida(texto):
    """`(ok, motivo, argv)`. Quando `ok`, o motivo e "" e `argv` e a lista que
    a fase 2 passara ao sistema operacional SEM shell. Senao, `argv` e [].

    A prova e dado de fora: escrita por quem tem escrita no repositorio. Nada
    aqui a executa — e nada que nao case EXATAMENTE com uma das tres formas
    passa.
    """
    if not isinstance(texto, str):
        return False, "a prova não é um texto", []
    prova = texto.strip()
    if not prova:
        return False, "sem prova", []
    if len(prova) > MAX_PROVA:
        return False, "prova longa demais", []
    for c in prova:
        if c in CARACTERES_PROIBIDOS:
            return False, "caractere proibido na prova: %r" % c, []
    m = _PROVA_PYTHON.fullmatch(prova)
    if m:
        return True, "", ["python", m.group(1)]
    m = _PROVA_PYTEST.fullmatch(prova)
    if m:
        partes = m.group(1).split("/")
        if any(p in ("", ".", "..") for p in partes):
            return False, "caminho fora do projeto", []
        return True, "", ["python", "-m", "pytest", m.group(1)]
    if _PROVA_NPM.fullmatch(prova):
        return True, "", ["npm", "test"]
    return False, "prova fora da lista fechada", []


# --------------------------------------------------------------- o que e sensivel
def criterio_sensivel(texto) -> bool:
    """O criterio mexe em algo que a IA nao desenvolve sem revisao humana?

    Lista de palavras: tem falso negativo (quem escreve "credencial" escapa), e
    por isso NAO e a trava real — a trava real e a tarefa vermelha, que espera o
    "Pode fazer" do dono. E a primeira peneira, para o botao nem aparecer.
    """
    if not isinstance(texto, str):
        return True
    sem_acento = "".join(c for c in unicodedata.normalize("NFKD", texto)
                         if not unicodedata.combining(c)).lower()
    return any(p in sem_acento for p in PALAVRAS_SENSIVEIS)


def id_do_criterio(projeto, slug, n, texto) -> str:
    """O id de um criterio: derivado, estavel, e com o PROJETO dentro.

    O servidor acha o criterio recalculando este id sobre os dados DA CONTA de
    quem pediu; o navegador nunca escolhe projeto, documento nem texto.
    """
    bruto = "\0".join((str(projeto), str(slug), str(n), str(texto)))
    return "c" + hashlib.sha256(bruto.encode("utf-8")).hexdigest()[:20]


def recusa_de_desenvolvimento(aprovado_em, marcado, texto, bloqueio="") -> str:
    """Por que este criterio NAO pode ser desenvolvido, ou "" se pode.

    Uma funcao so para a tela (`desenvolvivel`/`motivo`) e para a rota que
    recusa: o botao nunca oferece o que o servidor recusaria. A ordem e a do
    contrato. `bloqueio` ja vem decidido por quem conhece os projetos.
    """
    if not (aprovado_em or ""):
        return "documento nao aprovado"
    if bloqueio:
        return bloqueio
    if criterio_sensivel(texto):
        return "criterio sensivel"
    if marcado:
        return "criterio ja marcado"
    return ""


# ------------------------------------------------------------------ a conta
def _limpar(documentacao):
    """`(documentos limpos, descartados)`, ou `(None, 0)` se nao da para ler.

    O servidor NAO confia no agente: refaz os tipos e os tetos, recalcula o
    caminho do arquivo a partir do slug, e ignora qualquer `percentual` que
    venha no meio. Item malformado e descartado E CONTADO (vai para `erros_n`).
    """
    if not isinstance(documentacao, dict):
        return None, 0
    brutos = documentacao.get("documentos")
    if not isinstance(brutos, list):
        return None, 0
    descartados = 0
    docs = []
    for b in brutos:
        if len(docs) >= MAX_DOCUMENTOS:
            descartados += 1
            continue
        if (not isinstance(b, dict) or not isinstance(b.get("slug"), str)
                or not SLUG.fullmatch(b["slug"])
                or not isinstance(b.get("criterios"), list)):
            descartados += 1
            continue
        criterios = []
        for c in b["criterios"]:
            if (not isinstance(c, dict) or type(c.get("n")) is not int
                    or c["n"] < 1 or not isinstance(c.get("texto"), str)
                    or not c["texto"].strip()
                    or len(criterios) >= MAX_CRITERIOS):
                descartados += 1
                continue
            prova = c.get("prova")
            criterios.append({
                "n": c["n"], "texto": c["texto"][:MAX_TEXTO],
                "marcado": c.get("marcado") is True,
                "prova": prova if isinstance(prova, str)
                and len(prova) <= MAX_PROVA else ""})
        erros = b.get("erros")
        erros = [e[:300] for e in erros if isinstance(e, str)][:MAX_ERROS] \
            if isinstance(erros, list) else []
        aprovado = b.get("aprovado_em")
        docs.append({
            "slug": b["slug"], "arquivo": _arquivo_de(b["slug"]),
            "aprovado_em": aprovado if _data_valida(aprovado) else "",
            "erros": erros, "criterios": criterios})
    if descartados and not docs:
        return None, 0            # nada legivel: "nao sei", nunca "nao ha"
    return docs, descartados


def _situacao(c, cid, provas) -> str:
    """comprovado | prova_falhou | nao_verificado | falta.

    So um RESULTADO de prova (`True`/`False`, nada mais) move o criterio para
    `comprovado`/`prova_falhou`. Sem resultado: se alguem afirma que esta feito
    (`[x]`) ou existe prova aceita para rodar, e `nao_verificado`; se nada
    afirma nada, `falta`.
    """
    r = provas.get(cid) if isinstance(provas, dict) else None
    if r is True:
        return "comprovado"
    if r is False:
        return "prova_falhou"
    if c["marcado"] or prova_permitida(c["prova"])[0]:
        return "nao_verificado"
    return "falta"


def progresso(documentacao, projeto, medido_em, provas=None) -> dict:
    """A conta. RECALCULADA a partir dos criterios crus, sempre.

    Estados: `sem_dados` (a chave nao veio: agente antigo ou leitura que falhou),
    `sem_documentacao` (veio, e nao ha criterio), `nao_verificado` (ha criterio,
    nenhuma prova rodou) e `medido`. `percentual` so existe em `medido`; nos
    outros e `None` — nunca 0, nunca 100.
    """
    docs, descartados = _limpar(documentacao)
    if docs is None:
        return {"estado": "sem_dados", "percentual": None, "total": 0,
                "comprovados": 0, "falhos": 0, "nao_verificados": 0,
                "faltam": 0, "declarados": 0, "medido_em": None,
                "documentos_n": 0, "erros_n": 0}
    conta = {"comprovado": 0, "prova_falhou": 0, "nao_verificado": 0,
             "falta": 0}
    declarados = 0
    for d in docs:
        for c in d["criterios"]:
            cid = id_do_criterio(projeto, d["slug"], c["n"], c["texto"])
            s = _situacao(c, cid, provas)
            conta[s] += 1
            if s == "nao_verificado" and c["marcado"]:
                declarados += 1
    total = sum(conta.values())
    comprovados, falhos = conta["comprovado"], conta["prova_falhou"]
    if not total:
        estado, percentual = "sem_documentacao", None
    elif comprovados + falhos:
        estado, percentual = "medido", comprovados * 100 // total
    else:
        estado, percentual = "nao_verificado", None
    return {"estado": estado, "percentual": percentual, "total": total,
            "comprovados": comprovados, "falhos": falhos,
            "nao_verificados": conta["nao_verificado"],
            "faltam": conta["falta"], "declarados": declarados,
            "medido_em": medido_em, "documentos_n": len(docs),
            "erros_n": sum(len(d["erros"]) for d in docs) + descartados}


def detalhar(documentacao, projeto, provas=None, bloqueio="") -> list:
    """Os documentos e os criterios, um por um, como `/api/progresso` entrega."""
    docs, _ = _limpar(documentacao)
    saida = []
    for d in docs or []:
        criterios = []
        for c in d["criterios"]:
            cid = id_do_criterio(projeto, d["slug"], c["n"], c["texto"])
            situacao = _situacao(c, cid, provas)
            motivo = recusa_de_desenvolvimento(
                d["aprovado_em"], c["marcado"] or situacao == "comprovado",
                c["texto"], bloqueio)
            criterios.append({
                "id": cid, "n": c["n"], "texto": c["texto"],
                "marcado": c["marcado"], "prova": c["prova"],
                "prova_aceita": prova_permitida(c["prova"])[0],
                "situacao": situacao, "desenvolvivel": not motivo,
                "motivo": motivo})
        saida.append({"slug": d["slug"], "arquivo": d["arquivo"],
                      "aprovado_em": d["aprovado_em"], "erros": d["erros"],
                      "criterios": criterios})
    return saida


def achar_criterio(documentacao, projeto, criterio_id, provas=None,
                   bloqueio=""):
    """`(documento, criterio)` do id dado, ou `None`. O id e recalculado; o que
    o cliente manda nunca indexa nada."""
    for d in detalhar(documentacao, projeto, provas=provas, bloqueio=bloqueio):
        for c in d["criterios"]:
            if c["id"] == criterio_id:
                return d, c
    return None
