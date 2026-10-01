# -*- coding: utf-8 -*-
"""Testes do braco da PROVA — `ExecutorProva` em `agente/executor.py`.

Nada aqui e dublê do que importa: o repositorio e um repositorio git DE
VERDADE, o teste filho roda de verdade num processo de verdade, e o que se
confere e o que ele viu (ambiente, interpretador) e o que sobrou depois
(processo vivo, copia no disco).

Toda espera tem prazo: teste de processo sem prazo nao falha, pendura.

    python test_executor_prova.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("DERVS_AMBIENTE", "local")
os.environ.setdefault("DERVS_COFRE",
                      "chave-de-teste-que-nao-e-segredo-nenhum-0123456789")

AQUI = Path(__file__).resolve().parent
if str(AQUI) not in sys.path:
    sys.path.insert(0, str(AQUI))

import banco                       # noqa: E402
import execucao                    # noqa: E402
import tarefas                     # noqa: E402
from agente import executor as ex  # noqa: E402

TEM_PYTEST = subprocess.run(
    [sys.executable, "-c", "import pytest"], stdin=subprocess.DEVNULL,
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0

OK = ("import unittest\nclass T(unittest.TestCase):\n"
      "    def test_a(self):\n        self.assertTrue(True)\n"
      "if __name__ == '__main__':\n    unittest.main()\n")
FALHA = ("import unittest\nclass T(unittest.TestCase):\n"
         "    def test_a(self):\n        self.assertTrue(False)\n"
         "if __name__ == '__main__':\n    unittest.main()\n")
IMPORTA = "import modulo_que_nao_existe_nunca_0123\n"
PYTEST_FALHA = "def test_a():\n    assert False\n"
PYTEST_VAZIO = "x = 1\n"


def _git(pasta, *args):
    subprocess.run(["git", "-c", "user.name=x", "-c", "user.email=x@x", *args],
                   cwd=str(pasta), check=True, stdin=subprocess.DEVNULL,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def monta_repo(raiz, arquivos, provas):
    """Repositorio com os `arquivos` e um briefing cujos criterios citam as
    `provas`. Devolve o caminho."""
    repo = Path(raiz) / "repo"
    repo.mkdir()
    for nome, texto in arquivos.items():
        (repo / nome).write_text(texto, encoding="utf-8", newline="")
    pasta = repo / "docs" / "esteira" / "x"
    pasta.mkdir(parents=True)
    criterios = "".join("- [ ] criterio %d\nProva: %s\n" % (i, p)
                        for i, p in enumerate(provas))
    (pasta / "briefing.md").write_text(
        "# Briefing - x\n\nAprovado em: 2026-09-30\n\n"
        "## criterio_de_aceitacao\n\n" + criterios, encoding="utf-8",
        newline="")
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "inicio")
    return repo


def tarefa(repo, pedidas, **mais):
    t = {"id": "p1", "regra": tarefas.PROVAR, "projeto": "meu-proj",
         "executor": tarefas.EXECUTOR_DA_PROVA,
         "aprovado_em": "2026-10-01T10:00:00Z", "caminho": str(repo),
         "detalhe": "pedido\n" + "\n".join(banco.MARCA_DA_PROVA + p
                                           for p in pedidas)}
    t.update(mais)
    return t


def vivo(pid):
    if sys.platform.startswith("win"):
        r = subprocess.run(["tasklist", "/FI", "PID eq %d" % pid, "/NH"],
                           capture_output=True, text=True, timeout=30,
                           stdin=subprocess.DEVNULL)
        return str(pid) in r.stdout
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


class Base(unittest.TestCase):
    def setUp(self):
        self.raiz = tempfile.mkdtemp(prefix="dervs-tprova-")
        self.addCleanup(shutil.rmtree, self.raiz, True)
        self.copias = Path(self.raiz) / "copias"
        p = mock.patch.object(execucao, "BASE_COPIAS", self.copias)
        p.start()
        self.addCleanup(p.stop)
        self.ex = ex.ExecutorProva()
        self.ex.SEGUNDOS_ENTRE_OLHADAS = 0.1

    def roda(self, arquivos, provas, pedidas=None, **mais):
        repo = monta_repo(self.raiz, arquivos, provas)
        return self.ex.rodar(tarefa(repo, provas if pedidas is None
                                    else pedidas, **mais))

    def veredito_de(self, d, prova):
        return [p for p in d["provas"] if p["prova"] == prova][0]


class Veredito(unittest.TestCase):
    def test_zero_e_verdadeiro(self):
        self.assertEqual(ex.veredito(["x"], 0, "")[0], True)

    def test_pytest_1_com_falha_e_falso(self):
        self.assertIs(ex.veredito(["python", "-m", "pytest", "a.py"], 1,
                                  "1 failed in 0.1s")[0], False)

    def test_pytest_5_e_nao_sei(self):
        v, motivo = ex.veredito(["python", "-m", "pytest", "a.py"], 5,
                                "no tests ran")
        self.assertIsNone(v)
        self.assertTrue(motivo)

    def test_pytest_2_3_4_sao_nao_sei(self):
        for c in (2, 3, 4):
            self.assertIsNone(
                ex.veredito(["python", "-m", "pytest", "a.py"], c, "")[0])

    def test_pytest_ausente_nao_e_falha(self):
        # `python -m pytest` sem pytest instalado sai com 1: nao e teste caindo.
        self.assertIsNone(ex.veredito(["python", "-m", "pytest", "a.py"], 1,
                                      "No module named pytest")[0])

    def test_unittest_so_e_falso_com_o_resumo(self):
        a = ["python", "test_a.py"]
        self.assertIs(ex.veredito(a, 1, "Ran 1 test\n\nFAILED (failures=1)")[0],
                      False)
        self.assertIsNone(ex.veredito(a, 1, "ModuleNotFoundError: x")[0])

    def test_argv_python_e_absoluto_e_npm_fica_de_fora(self):
        a = ex.argv_da_prova(["python", "test_a.py"])
        self.assertTrue(os.path.isabs(a[0]), a)
        self.assertNotEqual(a[0], "python")
        self.assertEqual(a[1:], ["test_a.py"])
        self.assertIsNone(ex.argv_da_prova(["npm", "test"]))
        self.assertIsNone(ex.argv_da_prova([]))

    def test_ambiente_tira_o_que_nao_e_do_teste(self):
        base = {"ANTHROPIC_API_KEY": "a", "CLAUDE_CODE_X": "b", "DERVS_X": "c",
                "PYTHONPATH": "d", "PYTHONSTARTUP": "e", "PYTHONHOME": "f",
                "PYTEST_ADDOPTS": "g", "PYTEST_PLUGINS": "h",
                "NODE_OPTIONS": "i", "GITHUB_TOKEN": "j", "PATH": "/bin"}
        a = ex.ambiente_da_prova(base)
        self.assertEqual(sorted(a), ["PATH", "PYTHONDONTWRITEBYTECODE"])
        self.assertEqual(a["PYTHONDONTWRITEBYTECODE"], "1")


class RodaDeVerdade(Base):
    def test_ok_falha_e_importacao(self):
        provas = ["python test_ok.py", "python test_falha.py",
                  "python test_importa_inexistente.py"]
        d = self.roda({"test_ok.py": OK, "test_falha.py": FALHA,
                       "test_importa_inexistente.py": IMPORTA}, provas)
        self.assertEqual(d["estado"], "ok", d)
        self.assertIs(self.veredito_de(d, provas[0])["ok"], True)
        self.assertIs(self.veredito_de(d, provas[1])["ok"], False)
        nao_sei = self.veredito_de(d, provas[2])
        self.assertIsNone(nao_sei["ok"])
        self.assertTrue(nao_sei["motivo"])
        self.assertEqual(d["custo_usd"], 0.0)
        self.assertEqual(len(d["sha"]), 40)
        self.assertEqual(len(self.veredito_de(d, provas[0])["criterios"]), 1)
        self.assertIn("FAILED", d["resumo"])
        self.assertLessEqual(len(d["resumo"]), 4000)
        for campo in tarefas.CAMPOS_DO_DESFECHO:
            self.assertIn(campo, d)

    @unittest.skipUnless(TEM_PYTEST, "pytest nao instalado aqui")
    def test_pytest_falha_e_sem_teste_coletado(self):
        provas = ["python -m pytest t_falha.py", "python -m pytest t_vazio.py"]
        d = self.roda({"t_falha.py": PYTEST_FALHA, "t_vazio.py": PYTEST_VAZIO},
                      provas)
        self.assertIs(self.veredito_de(d, provas[0])["ok"], False)
        self.assertIsNone(self.veredito_de(d, provas[1])["ok"])

    def test_prazo_estoura_e_o_processo_morre(self):
        marca = Path(self.raiz) / "pid.txt"
        dorme = ("import os, time\nopen(%r, 'w').write(str(os.getpid()))\n"
                 "time.sleep(120)\n" % str(marca))
        self.ex.PRAZO_POR_PROVA = 2
        inicio = time.time()
        d = self.roda({"test_dorme.py": dorme}, ["python test_dorme.py"])
        self.assertLess(time.time() - inicio, 40)
        p = self.veredito_de(d, "python test_dorme.py")
        self.assertIsNone(p["ok"])
        self.assertIn("prazo", p["motivo"])
        pid = int(marca.read_text())
        fim = time.time() + 10
        while vivo(pid) and time.time() < fim:
            time.sleep(0.2)
        self.assertFalse(vivo(pid), "o teste continuou vivo depois do prazo")

    def test_segredo_e_variavel_do_dervs_nao_chegam_ao_filho(self):
        saida = Path(self.raiz) / "env.json"
        codigo = ("import json, os\nopen(%r, 'w').write(json.dumps("
                  "dict(os.environ)))\n" % str(saida))
        with mock.patch.dict(os.environ, {
                "ANTHROPIC_API_KEY": "sk-de-mentira", "DERVS_X": "1",
                "PYTHONPATH": "/nao/deve/chegar"}):
            d = self.roda({"test_env.py": codigo}, ["python test_env.py"])
        self.assertIs(self.veredito_de(d, "python test_env.py")["ok"], True, d)
        visto = json.loads(saida.read_text())
        chaves = {k.upper() for k in visto}
        for fora in ("ANTHROPIC_API_KEY", "DERVS_X", "PYTHONPATH"):
            self.assertNotIn(fora, chaves)
        self.assertEqual(visto.get("PYTHONDONTWRITEBYTECODE"), "1")

    def test_python_exe_plantado_no_repo_nao_e_usado(self):
        plantado = {"python.exe": "isto nao e um executavel", "python": "x",
                    "python.cmd": "@exit 9", "test_ok.py": OK}
        d = self.roda(plantado, ["python test_ok.py"])
        self.assertIs(self.veredito_de(d, "python test_ok.py")["ok"], True, d)

    def test_prova_fora_do_pedido_nao_roda(self):
        marca = Path(self.raiz) / "rodou.txt"
        intruso = "open(%r, 'w').write('x')\n" % str(marca)
        d = self.roda({"test_ok.py": OK, "test_intruso.py": intruso},
                      ["python test_ok.py", "python test_intruso.py"],
                      pedidas=["python test_ok.py"])
        self.assertFalse(marca.exists())
        self.assertEqual([p["prova"] for p in d["provas"]],
                         ["python test_ok.py"])

    def test_pedida_que_a_copia_nao_documenta_nao_roda(self):
        marca = Path(self.raiz) / "rodou2.txt"
        d = self.roda({"test_ok.py": OK,
                       "test_fora.py": "open(%r, 'w').write('x')\n" % str(marca)},
                      ["python test_ok.py"],
                      pedidas=["python test_ok.py", "python test_fora.py"])
        self.assertFalse(marca.exists())
        self.assertIsNone(self.veredito_de(d, "python test_fora.py")["ok"])

    def test_npm_test_e_nao_sei_com_motivo(self):
        d = self.roda({}, ["npm test"])
        p = self.veredito_de(d, "npm test")
        self.assertIsNone(p["ok"])
        self.assertTrue(p["motivo"])

    def test_tarefa_vermelha_nao_monta_argv(self):
        repo = monta_repo(self.raiz, {"test_ok.py": OK}, ["python test_ok.py"])
        t = tarefa(repo, ["python test_ok.py"], aprovado_em="")
        with mock.patch.object(ex, "argv_da_prova") as montou, \
                mock.patch.object(execucao, "criar_copia") as copiou:
            d = self.ex.rodar(t)
        self.assertTrue(d.get("recusada"))
        montou.assert_not_called()
        copiou.assert_not_called()

    def test_a_copia_e_apagada(self):
        self.roda({"test_ok.py": OK}, ["python test_ok.py"])
        self.assertEqual(
            [p for p in self.copias.glob("dervs-prova*")], [])

    def test_a_copia_e_apagada_mesmo_se_algo_levanta(self):
        repo = monta_repo(self.raiz, {"test_ok.py": OK}, ["python test_ok.py"])
        with mock.patch.object(ex.ExecutorProva, "_rodar_uma",
                               side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                self.ex.rodar(tarefa(repo, ["python test_ok.py"]))
        self.assertEqual(
            [p for p in self.copias.glob("dervs-prova*")], [])

    def test_esta_registrado_e_disponivel(self):
        self.assertIs(ex.EXECUTORES[tarefas.EXECUTOR_DA_PROVA],
                      ex.ExecutorProva)
        self.assertTrue(ex.ExecutorProva().disponivel())

    def test_fonte_nao_usa_shell_nem_python_cru(self):
        fonte = (AQUI / "agente" / "executor.py").read_text(encoding="utf-8")
        self.assertIn("shell=False", fonte)
        self.assertNotIn("shell=True", fonte)


if __name__ == "__main__":
    unittest.main()
