# -*- coding: utf-8 -*-
"""A tomada onde um braco e ligado.

O DERVS vai ter dois bracos. Hoje so um esta ligado — o Claude Code, que ja
existia e estava desligado (`execucao.py`, 1215 linhas, 91 testes). O Codex
entra na Fatia 3, e a unica coisa que este arquivo precisa garantir e que
ligar o segundo seja ACRESCENTAR uma implementacao, nao refazer nada.

Por isso `ExecutorCodex` ja existe aqui, com `disponivel()` devolvendo `False`.
Uma tomada vazia que ninguem consegue testar nao e uma tomada: e uma promessa.

**`execucao.py` nao e reescrito.** Ele tem 91 testes e a medicao de campo
colada no topo — quanto custa ligar uma sessao, e o quanto o `--max-budget-usd`
estourou. Este arquivo o EMBRULHA: `iniciar`, `estado`, `parar` e
`esperar_terminar` continuam sendo dele.

**A segunda camada do teto.** `Executor.rodar` chama `tarefas.pode_rodar` ANTES
de montar qualquer comando. O servidor ja recusou entregar a tarefa que nao
cabe; aqui ele recusa de novo.

O QUE ESTA CAMADA E, COM HONESTIDADE (corrigido em 03/09/2026): ela NAO e
independente. Uma versao anterior deste texto dizia que "a de fora depende de o
painel estar certo, e esta nao depende de nada" — e falso, e uma revisao de
seguranca derrubou. `agente/enviar.py` chama `rodar` sem `repinturas` e sem
`maquina`, entao aqui `cabe_no_teto` e sempre verdadeiro e a conferencia de
`executa` nem roda; e `aprovado_em`, `tentativas` e `parada_pedida_em` sao
exatamente os numeros que o painel mandou. Ela e um ECO dos fatos do painel,
util contra bug de entrega — e foi assim que o defeito de 03/09/2026 apareceu —
e inutil contra um painel mentiroso.

Prometer defesa que nao existe e pior que nao ter a defesa: faz a proxima
pessoa parar de olhar para o lado que realmente decide, que e o servidor.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

AQUI = Path(__file__).resolve().parent
if str(AQUI.parent) not in sys.path:
    sys.path.insert(0, str(AQUI.parent))

import auditoria  # noqa: E402
import banco      # noqa: E402
import documentos # noqa: E402
import execucao   # noqa: E402
import tarefas    # noqa: E402


class Executor:
    """O contrato. Tres coisas, e so tres.

    `rodar` devolve um dicionario no formato do DESFECHO descrito em
    `tarefas.py` — o mesmo que sobe por `POST /agente/resultado`. Quem escreve
    um braco novo nao precisa ler o servidor: le o contrato.
    """

    nome = "abstrato"

    def disponivel(self) -> bool:
        """Esta maquina consegue rodar este braco AGORA?"""
        raise NotImplementedError

    def rodar(self, tarefa: dict, teto_usd=None, ao_progredir=None,
              gasto_usd=0.0, repinturas=None, maquina=None) -> dict:
        raise NotImplementedError

    # A guarda comum, e ela mora na base para nao existir em duas versoes.
    def _recusar_se_nao_pode(self, tarefa, gasto_usd, repinturas, maquina):
        """`None` se pode rodar; o desfecho de recusa se nao pode."""
        pode, motivo = tarefas.pode_rodar(tarefa, gasto_usd, "", repinturas,
                                          maquina)
        if pode:
            return None
        return {
            "tipo": "desfecho",
            "id": (tarefa or {}).get("id") or "",
            "estado": "falha",
            "ramo": "", "resumo": "", "diff": "", "pr_url": "",
            "rodadas": 0, "custo_usd": 0.0,
            "erro": motivo,
            "recusada": True,
        }


class ExecutorClaude(Executor):
    """O braco que ja existia, agora alcancavel.

    Nada aqui monta comando, peneira ambiente ou clona repositorio: tudo isso
    e `execucao.py`, e ele ja e testado.
    """

    nome = "claude"

    # De quanto em quanto tempo o laco olha a sessao. Mais curto que o
    # intervalo com que o agente FALA com o painel
    # (`tarefas.SEGUNDOS_ENTRE_PROGRESSOS`), para nunca ser ele o gargalo.
    SEGUNDOS_ENTRE_OLHADAS = 1.0
    # Teto duro da sessao inteira. `--max-budget-usd` foi medido estourando
    # 4,5x; o relogio nao estoura.
    SEGUNDOS_DE_SESSAO = 1800

    def disponivel(self) -> bool:
        """Ha um binario do Claude Code nesta maquina?

        Nao roda nada para descobrir: montar o comando ja diz. Perguntar
        `claude --version` custaria uma subida de processo a cada volta do
        laco do agente.
        """
        try:
            return bool(execucao.montar_comando())
        except Exception:                      # noqa: BLE001 — falha fechada
            return False

    def rodar(self, tarefa: dict, teto_usd=None, ao_progredir=None,
              gasto_usd=0.0, repinturas=None, maquina=None) -> dict:
        recusa = self._recusar_se_nao_pode(tarefa, gasto_usd, repinturas,
                                           maquina)
        if recusa is not None:
            return recusa

        pendencia = {
            "id": tarefa.get("id") or "",
            "projeto": tarefa.get("projeto") or "",
            "regra": tarefa.get("regra") or "",
            "detalhe": tarefa.get("detalhe") or "",
            "gravidade": tarefa.get("gravidade") or "media",
        }
        caminho = tarefa.get("caminho") or tarefa.get("projeto_caminho") or ""
        teto = tarefa.get("teto_usd") if teto_usd is None else teto_usd

        # `contabilizar=False`: o custo desta sessao vai para a linha da `fila`
        # pelo desfecho. Deixar `True` contaria o mesmo gasto duas vezes.
        decisao = execucao.iniciar(pendencia, caminho, teto_usd=teto,
                                   contabilizar=False)
        if decisao != "iniciar":
            return {
                "tipo": "desfecho", "id": pendencia["id"], "estado": "falha",
                "ramo": "", "resumo": "", "diff": "", "pr_url": "",
                "rodadas": 0, "custo_usd": 0.0,
                "erro": ("ja ha uma sessao rodando nesta maquina"
                         if decisao == "mesma"
                         else "esta maquina recusou comecar a sessao"),
                "recusada": True,
            }

        return self._acompanhar(pendencia["id"], ao_progredir)

    def _acompanhar(self, tarefa_id: str, ao_progredir) -> dict:
        """Le a sessao enquanto ela roda e empurra o que aparece.

        `ao_progredir(retrato)` pode devolver `True` para dizer "pare". E por
        ai que o botao Parar do painel chega ate aqui: o agente pergunta ao
        painel de cinco em cinco segundos, e a resposta volta por este retorno.
        """
        entregues = 0
        fim = time.time() + self.SEGUNDOS_DE_SESSAO
        while time.time() < fim:
            retrato = execucao.estado(entregues)
            entregues = retrato.get("total_de_linhas", entregues)
            if ao_progredir is not None:
                try:
                    if ao_progredir(retrato):
                        execucao.parar()
                        break
                except Exception:              # noqa: BLE001
                    # Falha ao FALAR com o painel nao pode matar a sessao. O
                    # trabalho ja esta feito pela metade; perde-lo por causa de
                    # um cabo de rede seria o pior dos dois mundos.
                    pass
            if retrato.get("estado") in execucao.ESTADOS_TERMINAIS:
                break
            time.sleep(self.SEGUNDOS_ENTRE_OLHADAS)
        else:
            execucao.parar()

        final = execucao.estado(entregues)
        terminou_bem = final.get("estado") == "ok"
        return {
            "tipo": "desfecho",
            "id": tarefa_id,
            "estado": "ok" if terminou_bem else "falha",
            "ramo": final.get("ramo") or "",
            "resumo": final.get("resumo") or final.get("manchete") or "",
            "diff": final.get("diff") or "",
            "pr_url": final.get("pr_url") or "",
            "rodadas": int(final.get("rodadas") or 0),
            "custo_usd": float(final.get("custo_usd") or 0.0),
            "erro": "" if terminou_bem else (final.get("corpo") or
                                             final.get("manchete") or
                                             "a sessao nao terminou bem"),
        }


class ExecutorAuditor(Executor):
    """O braco SO-LEITURA (Auditoria Profunda, 02/09/2026): le um repositorio
    e devolve achados, nunca abre pull request.

    Nada aqui monta comando nem clona repositorio: tudo isso e
    `execucao.auditar`, a irma so-leitura de `execucao.iniciar`. O desfecho
    sobe pelo contrato de `tarefas.CAMPOS_DO_DESFECHO` MAIS UM CAMPO,
    `achados`, que carrega o JSON cru que o agente respondeu (o esquema pedido
    por `--json-schema`). Quem valida aquele JSON e `auditoria.validar`, do
    lado do servidor, nunca este arquivo.

    O JSON NAO VAI NO `resumo`: `servir._resultado` corta o `resumo` em 4.000
    caracteres, e um JSON cortado nao e um JSON menor, e lixo. O teto do campo
    proprio e `auditoria.TETO_DOS_ACHADOS`.
    """

    nome = auditoria.EXECUTOR

    SEGUNDOS_ENTRE_OLHADAS = 1.0
    SEGUNDOS_DE_SESSAO = 1800

    def disponivel(self) -> bool:
        try:
            return bool(execucao.montar_comando_de_auditoria())
        except Exception:                      # noqa: BLE001 — falha fechada
            return False

    def rodar(self, tarefa: dict, teto_usd=None, ao_progredir=None,
              gasto_usd=0.0, repinturas=None, maquina=None) -> dict:
        recusa = self._recusar_se_nao_pode(tarefa, gasto_usd, repinturas,
                                           maquina)
        if recusa is not None:
            return recusa

        projeto = tarefa.get("projeto") or ""
        caminho = tarefa.get("caminho") or tarefa.get("projeto_caminho") or ""
        teto = tarefa.get("teto_usd") if teto_usd is None else teto_usd

        decisao = execucao.auditar(projeto, caminho, teto_usd=teto)
        if decisao != "iniciar":
            return {
                "tipo": "desfecho", "id": tarefa.get("id") or "",
                "estado": "falha", "ramo": "", "resumo": "", "diff": "",
                "pr_url": "", "rodadas": 0, "custo_usd": 0.0,
                "erro": "ja ha uma sessao rodando nesta maquina",
                "recusada": True,
            }

        return self._acompanhar(tarefa.get("id") or "", ao_progredir)

    def _acompanhar(self, tarefa_id: str, ao_progredir) -> dict:
        """Igual a `ExecutorClaude._acompanhar`, sobre o estado da auditoria."""
        entregues = 0
        fim = time.time() + self.SEGUNDOS_DE_SESSAO
        while time.time() < fim:
            retrato = execucao.estado_auditoria(entregues)
            entregues = retrato.get("total_de_linhas", entregues)
            if ao_progredir is not None:
                try:
                    if ao_progredir(retrato):
                        execucao.parar_auditoria()
                        break
                except Exception:              # noqa: BLE001
                    pass
            if retrato.get("estado") in execucao.ESTADOS_TERMINAIS:
                break
            time.sleep(self.SEGUNDOS_ENTRE_OLHADAS)
        else:
            execucao.parar_auditoria()

        final = execucao.estado_auditoria(entregues)
        terminou_bem = final.get("estado") == "ok"
        return {
            "tipo": "desfecho",
            "id": tarefa_id,
            "estado": "ok" if terminou_bem else "falha",
            "ramo": "", "diff": "", "pr_url": "",
            "resumo": final.get("resumo") or "",
            # O CAMPO QUE FECHA O FIO. Sem ele o desfecho subia sem `achados`,
            # e o bloco de gravacao de `servir._resultado` — que so roda com
            # essa chave — era INALCANCAVEL: a auditoria rodava, gastava o teto
            # do dia e nao gravava nada. Vai separado do `resumo` de proposito:
            # o `resumo` e cortado em 4.000 caracteres do outro lado, e isso
            # destruiria o JSON de qualquer auditoria de verdade.
            "achados": final.get("achados") or "",
            "rodadas": int(final.get("rodadas") or 0),
            "custo_usd": float(final.get("custo_usd") or 0.0),
            "erro": "" if terminou_bem else (final.get("corpo") or
                                             final.get("manchete") or
                                             "a auditoria nao terminou bem"),
        }


# ---------------------------------------------------------------------------
# O braco da PROVA (fase 2 do progresso por documentacao): roda os comandos da
# lista fechada de `documentos.prova_permitida`, numa COPIA, sem shell, e
# devolve um veredito por prova. Sem IA, sem custo.
#
# LEI 2: o veredito e `True`, `False` ou `None` ("nao sei"), e `None` NUNCA vira
# falha. Prova que nao rodou (modulo ausente, nenhum teste coletado, prazo
# estourado, executavel ausente) nao e criterio reprovado: e criterio sem
# resposta. Zerar o que nao deu para medir apagaria um fato.
# ---------------------------------------------------------------------------

PRAZO_POR_PROVA = 600
PRAZO_DA_TAREFA = 1500
TETO_DO_RESUMO = 4000
TETO_DA_CAUDA = 1500
# Quanto o teste pode escrever antes de ser morto: a saida vai para um arquivo
# temporario e, sem teto, um laço de print enche o disco.
TETO_DA_SAIDA = 8 * 1024 * 1024

# Alem do que `execucao.ambiente_da_filha` ja tira. A filha MANTEM `ANTHROPIC_*`
# porque a sessao de IA precisa; um teste de terceiro nao precisa de nada disso.
_PREFIXOS_FORA = ("ANTHROPIC_", "CLAUDE_CODE_", "DERVS_")
_NOMES_FORA = ("PYTHONPATH", "PYTHONSTARTUP", "PYTHONHOME", "PYTEST_ADDOPTS",
               "PYTEST_PLUGINS", "NODE_OPTIONS", "DATABASE_URL", "REDIS_URL",
               "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY")
# Segredo costuma morar em variavel de nome neutro (`*_DSN`, `*_URL` de banco,
# proxy com usuario:senha). O filtro e por nome, entao so cobre o que se nomeia.
_SUFIXOS_FORA = ("_DSN", "_DATABASE_URL", "_CONNECTION_STRING")


def argv_da_prova(argv):
    """O argv que roda de verdade, ou `None` se esta fase nao o roda.

    `python` vira o interpretador DESTE processo, em caminho absoluto: a
    palavra crua seria resolvida pelo PATH e pela pasta do repositorio, e um
    `python.exe` plantado la dentro rodaria no lugar. `npm test` fica de fora.
    """
    if not isinstance(argv, (list, tuple)) or not argv:
        return None
    if argv[0] == "python":
        return [execucao._python_com_console(sys.executable)] + list(argv[1:])
    return None


def ambiente_da_prova(base=None) -> dict:
    limpo = execucao.ambiente_da_filha(base)
    for nome in list(limpo):
        alto = nome.upper()
        if (alto.startswith(_PREFIXOS_FORA) or alto in _NOMES_FORA
                or alto.endswith(_SUFIXOS_FORA)):
            del limpo[nome]
    limpo["PYTHONDONTWRITEBYTECODE"] = "1"
    return limpo


def _nenhum_teste_rodou(cauda: str) -> bool:
    """A cauda de um codigo 0 NAO mostra um teste que rodou de verdade?

    Prova positiva, nao ausencia de prova: um arquivo vazio, sem classe ou
    com o `if __name__` fora do lugar sai 0 e nao imprime resumo nenhum — e
    isso nao e "comprovado" (Lei 2). So vale o resumo do unittest com N>0
    e nem todos pulados, ou o do pytest com ao menos 1 passed."""
    ran = re.search(r"\bRan (\d+) tests?\b", cauda)
    if ran:
        n = int(ran.group(1))
        pulados = re.search(r"\bOK \(skipped=(\d+)", cauda)
        return n == 0 or bool(pulados and int(pulados.group(1)) >= n)
    return not re.search(r"\b[1-9]\d* passed\b", cauda)


def veredito(argv, codigo, cauda):
    """`(True|False|None, motivo)`. So `False` quando o proprio executor de
    testes disse que um teste falhou; qualquer outra coisa e `None`."""
    if codigo == 0:
        # Saiu 0 nao quer dizer que algo foi provado: teste todo pulado ou
        # nenhum coletado tambem sai 0 (Lei 2: nao vira "comprovado").
        if _nenhum_teste_rodou(cauda or ""):
            return None, ("nao deu para confirmar que algum teste rodou "
                          "(nenhum resumo de teste na saida)")
        return True, ""
    pytest = "pytest" in (argv or [])
    if pytest:
        # Codigo 1 tambem e o de `python -m pytest` SEM pytest instalado
        # ("No module named pytest"): so o resumo "N failed" prova teste caindo.
        if codigo == 1 and re.search(r"\b\d+ failed\b", cauda or ""):
            return False, "o pytest apontou teste falhando"
        return None, ("o pytest saiu com codigo %s (nao e falha de teste: "
                      "nenhum teste coletado, erro de uso ou interrupcao)"
                      % codigo)
    if "FAILED (" in (cauda or ""):
        return False, "o unittest apontou teste falhando"
    return None, ("o teste saiu com codigo %s sem o resumo de falha do "
                  "unittest (erro de importacao ou de ambiente?)" % codigo)


class ExecutorProva(Executor):
    """Roda as provas APROVADAS pelo dono, so as que ainda existem na copia."""

    nome = tarefas.EXECUTOR_DA_PROVA

    SEGUNDOS_ENTRE_OLHADAS = 1.0
    PRAZO_POR_PROVA = PRAZO_POR_PROVA
    PRAZO_DA_TAREFA = PRAZO_DA_TAREFA

    def disponivel(self) -> bool:
        return bool(sys.executable) and Path(sys.executable).exists()

    @staticmethod
    def _matar(proc) -> None:
        """Mata a ARVORE: o teste pode ter filhos, e so o pai morreria."""
        try:
            comando = execucao.comando_para_matar(proc.pid)
            if comando is not None:
                subprocess.run(comando, stdin=subprocess.DEVNULL,
                               stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=30,
                               shell=False, creationflags=execucao.SEM_JANELA)
            else:
                import signal
                os.killpg(proc.pid, signal.SIGKILL)
        except Exception:                      # noqa: BLE001
            pass
        try:
            proc.kill()
        except Exception:                      # noqa: BLE001
            pass
        try:
            proc.wait(timeout=10)
        except Exception:                      # noqa: BLE001
            pass

    @staticmethod
    def _job_da_arvore(proc):
        """Windows: `taskkill /T` nao acha filho de pai que ja saiu. Um Job
        Object guarda a arvore inteira ate o fim; fora do Windows (o grupo
        resolve) ou se falhar, `None`."""
        if not sys.platform.startswith("win"):
            return None
        try:
            import ctypes
            from ctypes import wintypes
            k = ctypes.WinDLL("kernel32", use_last_error=True)
            k.CreateJobObjectW.restype = wintypes.HANDLE
            k.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
            k.AssignProcessToJobObject.argtypes = [wintypes.HANDLE,
                                                   wintypes.HANDLE]
            job = k.CreateJobObjectW(None, None)
            if not job:
                return None
            # Se o agente morrer no meio da prova, o Windows fecha o handle do
            # Job e mata a arvore junto (sem isso o teste sobrevive ao agente).
            class _Basico(ctypes.Structure):
                _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64),
                            ("PerJobUserTimeLimit", ctypes.c_int64),
                            ("LimitFlags", wintypes.DWORD),
                            ("MinimumWorkingSetSize", ctypes.c_size_t),
                            ("MaximumWorkingSetSize", ctypes.c_size_t),
                            ("ActiveProcessLimit", wintypes.DWORD),
                            ("Affinity", ctypes.c_size_t),
                            ("PriorityClass", wintypes.DWORD),
                            ("SchedulingClass", wintypes.DWORD)]

            class _Io(ctypes.Structure):
                _fields_ = [(n, ctypes.c_uint64) for n in (
                    "ReadOperationCount", "WriteOperationCount",
                    "OtherOperationCount", "ReadTransferCount",
                    "WriteTransferCount", "OtherTransferCount")]

            class _Extendido(ctypes.Structure):
                _fields_ = [("Basic", _Basico), ("Io", _Io),
                            ("ProcessMemoryLimit", ctypes.c_size_t),
                            ("JobMemoryLimit", ctypes.c_size_t),
                            ("PeakProcessMemoryUsed", ctypes.c_size_t),
                            ("PeakJobMemoryUsed", ctypes.c_size_t)]

            info = _Extendido()
            info.Basic.LimitFlags = 0x2000          # KILL_ON_JOB_CLOSE
            k.SetInformationJobObject.argtypes = [
                wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
            if not k.SetInformationJobObject(job, 9, ctypes.byref(info),
                                             ctypes.sizeof(info)):
                k.CloseHandle.argtypes = [wintypes.HANDLE]
                k.CloseHandle(job)
                return None
            if not k.AssignProcessToJobObject(job, int(proc._handle)):
                k.CloseHandle.argtypes = [wintypes.HANDLE]
                k.CloseHandle(job)
                return None
            return job
        except Exception:                      # noqa: BLE001
            return None

    @staticmethod
    def _matar_job(job) -> None:
        if job is None:
            return
        try:
            import ctypes
            from ctypes import wintypes
            k = ctypes.WinDLL("kernel32", use_last_error=True)
            k.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
            k.CloseHandle.argtypes = [wintypes.HANDLE]
            k.TerminateJobObject(job, 1)
            k.CloseHandle(job)
        except Exception:                      # noqa: BLE001
            pass

    def _rodar_uma(self, argv, copia, ate, ao_progredir):
        """`(codigo|None, cauda, motivo)`. `codigo None` = nao terminou/rodou;
        `motivo` diz por que."""
        extra = ({"start_new_session": True}
                 if not sys.platform.startswith("win") else {})
        flags = ((execucao.SEM_JANELA | execucao.GRUPO_PROPRIO)
                 if sys.platform.startswith("win") else 0)
        with tempfile.TemporaryFile() as saida:
            try:
                proc = subprocess.Popen(
                    argv, cwd=str(copia), env=ambiente_da_prova(),
                    stdin=subprocess.DEVNULL, stdout=saida,
                    stderr=subprocess.STDOUT, shell=False,
                    creationflags=flags, **extra)
            except OSError as e:
                return None, "", "nao consegui iniciar o teste: %s" % e
            job = self._job_da_arvore(proc)
            fim = time.time() + min(self.PRAZO_POR_PROVA, max(0, ate - time.time()))
            motivo = ""
            while proc.poll() is None:
                if ao_progredir is not None:
                    try:
                        if ao_progredir({"estado": "rodando", "linhas": [],
                                         "custo_usd": 0.0}):
                            motivo = "voce pediu para parar"
                    except Exception:          # noqa: BLE001
                        pass
                if not motivo and time.time() >= fim:
                    motivo = "o prazo da prova estourou"
                if not motivo and saida.seek(0, 2) > TETO_DA_SAIDA:
                    motivo = "saida grande demais"
                if motivo:
                    self._matar(proc)
                    break
                time.sleep(self.SEGUNDOS_ENTRE_OLHADAS)
            if not motivo:
                # Terminou sozinho: filho largado em segundo plano nao fica.
                self._matar(proc)
            self._matar_job(job)
            tamanho = saida.seek(0, 2)
            saida.seek(max(0, tamanho - TETO_DA_CAUDA))
            cauda = saida.read().decode("utf-8", "replace")
        if motivo:
            return None, cauda, motivo
        return proc.returncode, cauda, ""

    def rodar(self, tarefa: dict, teto_usd=None, ao_progredir=None,
              gasto_usd=0.0, repinturas=None, maquina=None) -> dict:
        recusa = self._recusar_se_nao_pode(tarefa, gasto_usd, repinturas,
                                           maquina)
        if recusa is not None:
            return recusa

        id_ = tarefa.get("id") or ""
        projeto = tarefa.get("projeto") or ""

        def falha(erro, **mais):
            d = {"tipo": "desfecho", "id": id_, "estado": "falha", "ramo": "",
                 "resumo": "", "diff": "", "pr_url": "", "rodadas": 0,
                 "custo_usd": 0.0, "erro": erro}
            d.update(mais)
            return d

        pedidas = documentos.provas_do_pedido(tarefa.get("detalhe") or "",
                                              banco.MARCA_DA_PROVA)
        if not pedidas:
            return falha("o pedido nao traz nenhuma prova valida")
        caminho = tarefa.get("caminho") or tarefa.get("projeto_caminho") or ""
        if not caminho:
            return falha("o computador nao sabe onde este projeto esta")

        copia = Path(execucao.BASE_COPIAS) / ("dervs-prova-%s" % execucao.id_curto())
        try:
            ok, saida = execucao.criar_copia(caminho, copia, "dervs-prova")
            if not ok:
                return falha("nao consegui abrir a copia: %s" % saida[:300])
            sha = execucao.sha_da_copia(copia)
            try:
                doc = documentos.ler_projeto(copia)
            except Exception as e:             # noqa: BLE001
                return falha("nao consegui ler a documentacao da copia: %s"
                             % str(e)[:200], sha=sha)
            aceitas = documentos.provas_aceitas(doc, projeto)

            provas, linhas, parou = [], [], False
            ate = time.time() + self.PRAZO_DA_TAREFA
            for prova in pedidas:
                criterios = aceitas.get(prova)
                if criterios is None:
                    provas.append({"prova": prova, "ok": None, "criterios": [],
                                   "motivo": "a prova nao esta mais na "
                                             "documentacao da copia"})
                    continue
                if parou or time.time() >= ate:
                    provas.append({"prova": prova, "ok": None,
                                   "criterios": criterios,
                                   "motivo": "nao deu tempo ou a tarefa foi "
                                             "parada"})
                    continue
                argv = argv_da_prova(documentos.prova_permitida(prova)[2])
                if argv is None:
                    provas.append({"prova": prova, "ok": None,
                                   "criterios": criterios,
                                   "motivo": "esta fase nao roda este tipo de "
                                             "prova"})
                    continue
                codigo, cauda, motivo = self._rodar_uma(argv, copia, ate,
                                                        ao_progredir)
                if motivo:
                    ok_, mot = None, motivo
                    parou = parou or motivo == "voce pediu para parar"
                elif codigo is None:
                    ok_, mot = None, "nao rodou"
                else:
                    ok_, mot = veredito(argv, codigo, cauda)
                provas.append({"prova": prova, "ok": ok_, "motivo": mot,
                               "criterios": criterios})
                if ok_ is not True:
                    linhas.append((prova, cauda))
        finally:
            execucao.remover_copia(caminho, copia)

        rotulo = {True: "passou", False: "FALHOU", None: "sem veredito"}
        resumo = "\n".join("%s: %s" % (p["prova"], rotulo[p["ok"]])
                           for p in provas)
        for prova, cauda in linhas:
            resumo += "\n\n--- %s ---\n%s" % (prova, cauda.strip())
        return {
            "tipo": "desfecho", "id": id_,
            "estado": "falha" if parou else "ok",
            "ramo": "", "diff": "", "pr_url": "", "rodadas": 0,
            "custo_usd": 0.0, "resumo": resumo[:TETO_DO_RESUMO],
            "erro": "voce pediu para parar" if parou else "",
            "provas": provas, "sha": sha,
        }


class ExecutorCodex(Executor):
    """O segundo braco. Previsto, e desligado.

    Ele existe para que ligar o Codex seja escrever este corpo — e nao mexer
    no agente, no painel e no contrato ao mesmo tempo.
    """

    nome = "codex"

    def disponivel(self) -> bool:
        return False

    def rodar(self, tarefa: dict, teto_usd=None, ao_progredir=None,
              gasto_usd=0.0, repinturas=None, maquina=None) -> dict:
        raise NotImplementedError(
            "o segundo braco (Codex) e da Fatia 3. A tomada esta pronta; a "
            "implementacao, nao.")


# A lista dos bracos, por nome. O painel manda `executor` no corpo da tarefa, e
# e esta tabela que decide qual objeto responde. Nome desconhecido devolve
# `None`, e quem chama trata como recusa — nunca como "usa o padrao".
EXECUTORES = {
    ExecutorClaude.nome: ExecutorClaude,
    ExecutorAuditor.nome: ExecutorAuditor,
    ExecutorProva.nome: ExecutorProva,
    ExecutorCodex.nome: ExecutorCodex,
}


def executor_de(nome: str):
    """A instancia do braco pedido, ou `None`. Falha fechada."""
    classe = EXECUTORES.get((nome or "").strip())
    return classe() if classe else None
