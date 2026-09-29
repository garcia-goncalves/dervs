"""Provas do `conectador.py` — o programa que roda FORA deste servidor.

Ele roda na maquina de quem baixa: mexe com `tkinter`, com a rede e com o
agendador do Windows. A CI roda em Linux, sem agendador, sem janela grafica e
sem painel. Entao TUDO aqui e por duble: nenhum teste chama `schtasks` de
verdade nem bate na rede. Um teste que precisasse disso ficaria vermelho por
motivo errado, e um teste vermelho por motivo errado e desligado em duas
semanas.
"""

import ast
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import conectador


class UmArquivoSoBibliotecaPadraoSo(unittest.TestCase):
    """A lei 1 do arquivo, conferida no proprio fonte.

    Nao basta ler os imports do topo: `escolher_pasta` importa `tkinter` la
    dentro do `try`, e um `import requests` escondido dentro de uma funcao
    passaria por qualquer olhada rapida. `ast` ve todos.
    """

    @classmethod
    def setUpClass(cls):
        cls.fonte = Path(conectador.__file__).read_text(encoding="utf-8")
        cls.arvore = ast.parse(cls.fonte)

    def _importados(self):
        nomes = set()
        for no in ast.walk(self.arvore):
            if isinstance(no, ast.Import):
                for a in no.names:
                    nomes.add(a.name.split(".")[0])
            elif isinstance(no, ast.ImportFrom):
                if no.level:                      # `from . import x`
                    nomes.add(".")
                elif no.module:
                    nomes.add(no.module.split(".")[0])
        return nomes

    def test_todo_import_e_da_biblioteca_padrao(self):
        padrao = set(sys.stdlib_module_names)
        fora = sorted(n for n in self._importados() if n not in padrao)
        self.assertEqual([], fora,
                         "o conectador roda onde nada foi instalado: %s" % fora)

    def test_nenhum_import_de_modulo_deste_repositorio(self):
        aqui = Path(conectador.__file__).parent
        deste_repo = {p.stem for p in aqui.glob("*.py")} | {"agente"}
        deste_repo.discard("conectador")
        invasores = sorted(self._importados() & deste_repo)
        self.assertEqual([], invasores,
                         "ele roda numa maquina sem o repositorio: %s" % invasores)

    def test_o_fonte_inteiro_e_ascii(self):
        """O que ele IMPRIME nao pode ter acento — o console do Windows nao mostra.

        A regra e cobrada no que sai pela tela: toda string literal do arquivo.
        Os comentarios e docstrings ficam de fora porque ninguem os le no
        console; o proprio agente ja e cobrado assim em
        `test_conectar_ponta_a_ponta.py:266`.
        """
        sujas = []
        for no in ast.walk(self.arvore):
            if isinstance(no, ast.Constant) and isinstance(no.value, str):
                if no.value.strip() and not no.value.isascii():
                    if no is not getattr(no, "_doc", None):
                        sujas.append(no.value[:60])
        # As docstrings tem acento de proposito; tire-as da conta.
        docs = set()
        for no in ast.walk(self.arvore):
            if isinstance(no, (ast.Module, ast.FunctionDef, ast.ClassDef)):
                d = ast.get_docstring(no, clean=False)
                if d:
                    docs.add(d[:60])
        sujas = [s for s in sujas if s not in docs]
        self.assertEqual([], sujas, "texto com acento vai para o console: %s" % sujas)

    def test_o_dunder_main_fica_no_fim(self):
        """Ja houve teste neste repositorio que nunca rodou por causa disso."""
        linhas = [i for i, l in enumerate(self.fonte.splitlines())
                  if l.startswith('if __name__ == "__main__":')]
        self.assertEqual(1, len(linhas))
        depois = self.fonte.splitlines()[linhas[0] + 1:]
        self.assertTrue(all(not l.strip() or l.startswith((" ", "\t"))
                            for l in depois),
                        "ha codigo de modulo depois do bloco __main__")

    def test_as_duas_marcas_que_o_servidor_troca_existem(self):
        """A rota da etapa A3 injeta por essas marcas. Apagar uma a quebra."""
        self.assertIn("# DERVS:CODIGO", self.fonte)
        self.assertIn("# DERVS:ALVO", self.fonte)


class OsDoisCaminhosDaPasta(unittest.TestCase):
    """A janela quando da, e o `input()` quando nao da. Nunca travar."""

    def setUp(self):
        self.tk_antes = sys.modules.get("tkinter")
        self.fd_antes = sys.modules.get("tkinter.filedialog")
        self.addCleanup(self._devolver)

    def _devolver(self):
        for nome, antes in (("tkinter", self.tk_antes),
                            ("tkinter.filedialog", self.fd_antes)):
            if antes is None:
                sys.modules.pop(nome, None)
            else:
                sys.modules[nome] = antes

    def test_com_tkinter_a_janela_e_chamada(self):
        chamadas = {}

        class JanelaFalsa:
            def withdraw(self):
                chamadas["withdraw"] = True

            def destroy(self):
                chamadas["destroy"] = True

        class FileDialogFalso:
            @staticmethod
            def askdirectory(**kw):
                chamadas["askdirectory"] = kw
                return "C:/projetos"

        tk = type(sys)("tkinter")
        tk.Tk = lambda: JanelaFalsa()
        tk.filedialog = FileDialogFalso
        sys.modules["tkinter"] = tk
        sys.modules["tkinter.filedialog"] = FileDialogFalso

        self.assertEqual("C:/projetos", conectador.escolher_pasta("C:/sug"))
        self.assertIn("askdirectory", chamadas)
        self.assertTrue(chamadas.get("withdraw"))
        self.assertTrue(chamadas.get("destroy"), "a janela tem de ser fechada")

    def test_sem_tkinter_ele_cai_no_input_e_nao_levanta(self):
        """Builds da Microsoft Store vem sem Tcl/Tk, e nao da para instalar."""
        sys.modules["tkinter"] = None          # forca ImportError
        sys.modules["tkinter.filedialog"] = None
        entrada = io.StringIO('  "C:/outra/pasta"  \n')
        antes = sys.stdin
        sys.stdin = entrada
        self.addCleanup(setattr, sys, "stdin", antes)
        saida = io.StringIO()
        antes_out = sys.stdout
        sys.stdout = saida
        try:
            escolhida = conectador.escolher_pasta("C:/sug")
        finally:
            sys.stdout = antes_out
        self.assertEqual("C:/outra/pasta", escolhida)
        self.assertIn("Sugestao", saida.getvalue())

    def test_sem_tkinter_e_sem_ninguem_digitando_ele_devolve_vazio(self):
        sys.modules["tkinter"] = None
        sys.modules["tkinter.filedialog"] = None
        antes = sys.stdin
        sys.stdin = io.StringIO("")            # EOF na primeira leitura
        self.addCleanup(setattr, sys, "stdin", antes)
        saida = io.StringIO()
        antes_out = sys.stdout
        sys.stdout = saida
        try:
            self.assertEqual("", conectador.escolher_pasta("C:/sug"))
        finally:
            sys.stdout = antes_out


class FecharSemEscolherNaoDeixaLixo(unittest.TestCase):
    """A lei 2. Os dubles ESTOURAM se forem chamados — e essa e a prova."""

    def setUp(self):
        self.casa = tempfile.TemporaryDirectory()
        self.addCleanup(self.casa.cleanup)
        self.arquivo = Path(self.casa.name) / "agente.json"
        self.antes_texto = json.dumps(
            {"https://dervs.com.br": {"token": "jaexistia", "maquina": "velha"}},
            ensure_ascii=False, indent=2)
        self.arquivo.write_text(self.antes_texto, encoding="utf-8")
        os.environ["DERVS_AGENTE_ARQUIVO"] = str(self.arquivo)
        self.addCleanup(os.environ.pop, "DERVS_AGENTE_ARQUIVO", None)

    def _explodir(self, *a, **k):
        raise AssertionError("nao podia ter sido chamado")

    def test_sem_pasta_nada_de_rede_nada_de_escrita_nada_de_agendador(self):
        os.environ["DERVS_ALVO"] = "https://dervs.com.br"
        os.environ["DERVS_CODIGO"] = "123456"
        self.addCleanup(os.environ.pop, "DERVS_ALVO", None)
        self.addCleanup(os.environ.pop, "DERVS_CODIGO", None)
        original = (conectador.escolher_pasta, conectador.parear,
                    conectador.gravar, conectador.agendar, subprocess.run)
        conectador.escolher_pasta = lambda *a, **k: ""
        conectador.parear = self._explodir
        conectador.gravar = self._explodir
        conectador.agendar = self._explodir
        subprocess.run = self._explodir

        def devolver():
            (conectador.escolher_pasta, conectador.parear, conectador.gravar,
             conectador.agendar, subprocess.run) = original
        self.addCleanup(devolver)

        saida, antes_out = io.StringIO(), sys.stdout
        antes_in, sys.stdin = sys.stdin, io.StringIO("")
        sys.stdout = saida
        try:
            codigo = conectador.main()
        finally:
            sys.stdout, sys.stdin = antes_out, antes_in

        self.assertEqual(conectador.SEM_PASTA, codigo)
        self.assertNotEqual(0, codigo, "falha fechada: nunca zero")
        # BYTE A BYTE: o arquivo tem de estar exatamente como estava.
        self.assertEqual(self.antes_texto,
                         self.arquivo.read_text(encoding="utf-8"))
        self.assertIn("Nada foi alterado", saida.getvalue())

    def test_pareamento_recusado_nao_grava_nem_agenda(self):
        original = (conectador.escolher_pasta, conectador.parear,
                    conectador.gravar, conectador.agendar)
        conectador.escolher_pasta = lambda *a, **k: self.casa.name
        conectador.parear = lambda *a, **k: ""      # o painel recusou
        conectador.gravar = self._explodir
        conectador.agendar = self._explodir

        def devolver():
            (conectador.escolher_pasta, conectador.parear, conectador.gravar,
             conectador.agendar) = original
        self.addCleanup(devolver)

        os.environ["DERVS_ALVO"] = "https://dervs.com.br"
        os.environ["DERVS_CODIGO"] = "123456"
        self.addCleanup(os.environ.pop, "DERVS_ALVO", None)
        self.addCleanup(os.environ.pop, "DERVS_CODIGO", None)

        saida, antes_out = io.StringIO(), sys.stdout
        antes_in, sys.stdin = sys.stdin, io.StringIO("")
        sys.stdout = saida
        try:
            codigo = conectador.main()
        finally:
            sys.stdout, sys.stdin = antes_out, antes_in

        self.assertEqual(conectador.SEM_PAREAMENTO, codigo)
        self.assertEqual(self.antes_texto,
                         self.arquivo.read_text(encoding="utf-8"))

    def test_gravar_preserva_o_que_ja_estava_e_acrescenta_a_raiz(self):
        conectador.gravar("https://outro.exemplo", "tokennovo", "D:/proj")
        dados = json.loads(self.arquivo.read_text(encoding="utf-8"))
        self.assertEqual("jaexistia",
                         dados["https://dervs.com.br"]["token"],
                         "o token do outro alvo nao pode sumir")
        self.assertEqual("tokennovo", dados["https://outro.exemplo"]["token"])
        self.assertEqual(["D:/proj"], dados["raizes"])

    def test_gravar_nao_repete_a_mesma_raiz(self):
        conectador.gravar("https://a.exemplo", "t1", "D:/proj")
        conectador.gravar("https://a.exemplo", "t2", "d:/PROJ")
        dados = json.loads(self.arquivo.read_text(encoding="utf-8"))
        self.assertEqual(1, len(dados["raizes"]))

    def test_o_temporario_nao_fica_para_tras(self):
        conectador.gravar("https://a.exemplo", "t1", "D:/proj")
        sobras = list(Path(self.casa.name).glob("*.novo"))
        self.assertEqual([], sobras)


class OComandoDaTarefaAgendada(unittest.TestCase):
    """Montado como DADO, e conferido como dado. Nunca chamado de verdade."""

    def test_o_argv_e_uma_lista_comecando_por_schtasks(self):
        argv = conectador.argumentos_do_schtasks("C:/x/agente/enviar.py",
                                                 "https://dervs.com.br/")
        self.assertIsInstance(argv, list)
        self.assertEqual("schtasks", argv[0])
        self.assertIn("/Create", argv)
        self.assertIn("/TN", argv)
        self.assertIn("/TR", argv)
        self.assertIn("/F", argv)

    def test_o_tr_sobrevive_a_caminho_com_espaco(self):
        argv = conectador.argumentos_do_schtasks(
            r"C:\Program Files\dervs\agente\enviar.py", "https://dervs.com.br")
        tr = argv[argv.index("/TR") + 1]
        self.assertIn(r'"C:\Program Files\dervs\agente\enviar.py"', tr,
                      "sem aspas o agendador quebra o caminho em dois argumentos")

    def test_a_barra_final_do_alvo_nao_entra_no_comando(self):
        tr = conectador.comando_da_tarefa("/x/enviar.py", "https://dervs.com.br/")
        self.assertIn('--alvo "https://dervs.com.br"', tr)
        self.assertNotIn('dervs.com.br/"', tr)

    def test_o_alvo_TAMBEM_vai_entre_aspas(self):
        """Um endereco com espaco quebrava a tarefa em silencio: o agendador
        cortava no espaco e o agente recebia meio endereco. Apontado pela
        revisao de seguranca de 01/09/2026."""
        tr = conectador.comando_da_tarefa("/x/enviar.py", "https://um site/")
        self.assertIn('--alvo "https://um site"', tr)

    def test_o_plano_b_nao_usa_ONLOGON_e_reporta_uma_vez(self):
        """ONLOGON exige administrador; MINUTE nao. Sem --intervalo o agente
        reporta uma vez e sai, senao cada acordada empilharia um laco."""
        argv = conectador.argumentos_do_schtasks("/x/enviar.py", "https://d",
                                                 plano_b=True)
        self.assertNotIn("ONLOGON", argv)
        self.assertEqual("MINUTE", argv[argv.index("/SC") + 1])
        self.assertEqual("10", argv[argv.index("/MO") + 1])
        self.assertNotIn("--intervalo", argv[argv.index("/TR") + 1])

    def test_o_plano_A_continua_com_laco(self):
        argv = conectador.argumentos_do_schtasks("/x/enviar.py", "https://d")
        self.assertEqual("ONLOGON", argv[argv.index("/SC") + 1])
        self.assertIn("--intervalo 60", argv[argv.index("/TR") + 1])

    def test_agendar_nunca_usa_shell(self):
        vistos = {}

        class Fim:
            returncode = 0

        def falso_run(argv, **kw):
            vistos["argv"] = argv
            vistos["kw"] = kw
            return Fim()

        antes, subprocess.run = subprocess.run, falso_run
        antes_nome, os.name = os.name, "nt"
        self.addCleanup(setattr, subprocess, "run", antes)
        self.addCleanup(setattr, os, "name", antes_nome)

        self.assertTrue(conectador.agendar("C:/x/agente/enviar.py",
                                           "https://dervs.com.br"))
        self.assertIsInstance(vistos["argv"], list)
        self.assertFalse(vistos["kw"].get("shell", False),
                         "shell=True faria o caminho escolhido pela pessoa "
                         "atravessar o interpretador de comandos")

    def test_fora_do_windows_ele_nao_agenda_e_nao_mente(self):
        def explodir(*a, **k):
            raise AssertionError("schtasks nao existe fora do Windows")

        antes, subprocess.run = subprocess.run, explodir
        antes_nome, os.name = os.name, "posix"
        self.addCleanup(setattr, subprocess, "run", antes)
        self.addCleanup(setattr, os, "name", antes_nome)
        self.assertFalse(conectador.agendar("/x/agente/enviar.py",
                                            "https://dervs.com.br"))

    def test_agendar_devolve_False_quando_o_schtasks_falha(self):
        def falso_run(argv, **kw):
            raise OSError("nao achei o schtasks")

        antes, subprocess.run = subprocess.run, falso_run
        antes_nome, os.name = os.name, "nt"
        self.addCleanup(setattr, subprocess, "run", antes)
        self.addCleanup(setattr, os, "name", antes_nome)
        self.assertFalse(conectador.agendar("C:/x/agente/enviar.py", "https://d"))


class APausaNaoPenduraOAgendador(unittest.TestCase):
    """A armadilha que morde primeiro: a pausa dentro da tarefa agendada."""

    def test_sem_terminal_nao_ha_pausa(self):
        class NaoTerminal(io.StringIO):
            def isatty(self):
                return False

        antes_in, antes_out = sys.stdin, sys.stdout
        sys.stdin, sys.stdout = NaoTerminal(""), NaoTerminal()
        try:
            self.assertFalse(conectador.tem_alguem_lendo())
            conectador.pausa()          # se pendurasse, o teste nunca voltaria
        finally:
            sys.stdin, sys.stdout = antes_in, antes_out

    def test_com_terminal_ela_espera_o_enter(self):
        vistos = []

        class Terminal(io.StringIO):
            def isatty(self):
                return True

        import builtins
        antes_input = builtins.input
        builtins.input = lambda *a: vistos.append(a) or ""
        antes_in, antes_out = sys.stdin, sys.stdout
        sys.stdin, sys.stdout = Terminal(""), Terminal()
        try:
            self.assertTrue(conectador.tem_alguem_lendo())
            conectador.pausa()
        finally:
            builtins.input = antes_input
            sys.stdin, sys.stdout = antes_in, antes_out
        self.assertEqual(1, len(vistos))

    def test_stdin_ausente_nao_levanta(self):
        antes = sys.stdin
        sys.stdin = None
        try:
            self.assertFalse(conectador.tem_alguem_lendo())
        finally:
            sys.stdin = antes


class AcharOAgente(unittest.TestCase):
    """Ele so ACHA o que ja esta na maquina. Nao distribui codigo-fonte."""

    def setUp(self):
        self.casa = tempfile.TemporaryDirectory()
        self.addCleanup(self.casa.cleanup)
        os.environ.pop("DERVS_REPO", None)

    def test_acha_o_agente_numa_filha_da_raiz_escolhida(self):
        repo = Path(self.casa.name) / "dervs" / "agente"
        repo.mkdir(parents=True)
        (repo / "enviar.py").write_text("# de mentira", encoding="utf-8")
        achado = conectador.achar_o_agente(self.casa.name)
        self.assertTrue(achado.endswith(os.path.join("agente", "enviar.py")))

    def test_a_variavel_de_ambiente_vence(self):
        outro = Path(self.casa.name) / "escolhido" / "agente"
        outro.mkdir(parents=True)
        (outro / "enviar.py").write_text("# de mentira", encoding="utf-8")
        os.environ["DERVS_REPO"] = str(outro.parent)
        self.addCleanup(os.environ.pop, "DERVS_REPO", None)
        self.assertEqual(str(outro / "enviar.py"),
                         conectador.achar_o_agente(self.casa.name))

    def test_sem_o_repositorio_ele_devolve_vazio_em_vez_de_levantar(self):
        vazia = Path(self.casa.name) / "so-projetos"
        vazia.mkdir()
        antes = conectador.__file__
        # Aponta o proprio arquivo para uma pasta sem `agente/`, senao ele
        # acharia o repositorio de VERDADE em que este teste roda.
        conectador.__file__ = str(vazia / "conectador.py")
        self.addCleanup(setattr, conectador, "__file__", antes)
        self.assertEqual("", conectador.achar_o_agente(str(vazia)))


class OPareamentoPelaRede(unittest.TestCase):
    """Duble de `urlopen`. A CI nao tem painel para bater."""

    def test_devolve_o_token_do_json(self):
        import urllib.request

        class Resposta:
            def __enter__(self_):
                return self_

            def __exit__(self_, *a):
                return False

            def read(self_, n=None):
                return b'{"token": "abc123"}'

        vistos = {}

        def falso(pedido, timeout=None):
            vistos["url"] = pedido.full_url
            vistos["metodo"] = pedido.get_method()
            vistos["corpo"] = pedido.data
            return Resposta()

        antes = urllib.request.urlopen
        urllib.request.urlopen = falso
        self.addCleanup(setattr, urllib.request, "urlopen", antes)

        self.assertEqual("abc123",
                         conectador.parear("https://dervs.com.br/", "123456", "pc"))
        self.assertEqual("https://dervs.com.br/agente/parear", vistos["url"])
        self.assertEqual("POST", vistos["metodo"])
        self.assertEqual({"codigo": "123456", "maquina": "pc"},
                         json.loads(vistos["corpo"].decode("utf-8")))

    def test_rede_caida_devolve_vazio_e_nao_levanta(self):
        import urllib.error
        import urllib.request

        def explodir(pedido, timeout=None):
            raise urllib.error.URLError("sem rede")

        antes = urllib.request.urlopen
        urllib.request.urlopen = explodir
        self.addCleanup(setattr, urllib.request, "urlopen", antes)
        self.assertEqual("", conectador.parear("https://x", "1", "pc"))

    def test_resposta_torta_devolve_vazio(self):
        import urllib.request

        class Resposta:
            def __enter__(self_):
                return self_

            def __exit__(self_, *a):
                return False

            def read(self_, n=None):
                return b"nao sou json"

        antes = urllib.request.urlopen
        urllib.request.urlopen = lambda p, timeout=None: Resposta()
        self.addCleanup(setattr, urllib.request, "urlopen", antes)
        self.assertEqual("", conectador.parear("https://x", "1", "pc"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
