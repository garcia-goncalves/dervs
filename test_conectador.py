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
import unittest.mock
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

    def test_o_arquivo_inteiro_e_ascii_porque_o_corpo_do_cmd_e_ascii_puro(self):
        """Contrato C7: o servidor monta o `.cmd` em ASCII. Comentario com
        travessao quebraria a rota (e a extracao) so em producao."""
        self.assertTrue(self.fonte.isascii())

    def test_o_dunder_main_fica_no_fim(self):
        """Ja houve teste neste repositorio que nunca rodou por causa disso."""
        linhas = [i for i, l in enumerate(self.fonte.splitlines())
                  if l.startswith('if __name__ == "__main__":')]
        self.assertEqual(1, len(linhas))
        depois = self.fonte.splitlines()[linhas[0] + 1:]
        self.assertTrue(all(not l.strip() or l.startswith((" ", "\t"))
                            for l in depois),
                        "ha codigo de modulo depois do bloco __main__")

    def test_a_marca_que_o_servidor_troca_existe_e_a_do_codigo_nao(self):
        """O servidor injeta SO o alvo. O codigo de seis digitos saiu do arquivo:
        agora nasce no PC (pedido), e o navegador o confere."""
        com_alvo = [l for l in self.fonte.splitlines()
                    if l.rstrip().endswith("# DERVS:ALVO")]
        self.assertEqual(1, len(com_alvo))
        self.assertNotIn("DERVS:CODIGO", self.fonte)

    def test_nenhuma_linha_imita_o_marcador_do_python_embutido(self):
        """O `.cmd` corta o arquivo montado na linha `#:DERVS-PYTHON`."""
        ruins = [l for l in self.fonte.splitlines()
                 if l.startswith("#:DERVS-PYTHON")]
        self.assertEqual([], ruins)


class OsDoisCaminhosDaPasta(unittest.TestCase):
    """A janela quando da, e o `input()` quando nao da. Nunca travar."""

    def setUp(self):
        self.tk_antes = sys.modules.get("tkinter")
        self.fd_antes = sys.modules.get("tkinter.filedialog")
        self.addCleanup(self._devolver)
        # No Windows de verdade `escolher_pasta` tentaria o PowerShell primeiro.
        # Estes casos sao do que vem DEPOIS dele.
        antes = conectador.pelo_powershell
        conectador.pelo_powershell = lambda sugestao: None
        self.addCleanup(setattr, conectador, "pelo_powershell", antes)

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
        self.addCleanup(os.environ.pop, "DERVS_ALVO", None)
        original = (conectador.escolher_pasta, conectador.pedir,
                    conectador.gravar, conectador.agendar, subprocess.run)
        navegador = conectador.webbrowser.open
        conectador.webbrowser.open = self._explodir
        self.addCleanup(setattr, conectador.webbrowser, "open", navegador)
        conectador.escolher_pasta = lambda *a, **k: ""
        conectador.pedir = self._explodir
        conectador.gravar = self._explodir
        conectador.agendar = self._explodir
        subprocess.run = self._explodir

        def devolver():
            (conectador.escolher_pasta, conectador.pedir, conectador.gravar,
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
        original = (conectador.escolher_pasta, conectador.conectar_pelo_navegador,
                    conectador.gravar, conectador.agendar)
        conectador.escolher_pasta = lambda *a, **k: self.casa.name
        conectador.conectar_pelo_navegador = lambda *a, **k: ""   # o painel recusou
        conectador.gravar = self._explodir
        conectador.agendar = self._explodir

        def devolver():
            (conectador.escolher_pasta, conectador.conectar_pelo_navegador,
             conectador.gravar, conectador.agendar) = original
        self.addCleanup(devolver)

        os.environ["DERVS_ALVO"] = "https://outro.exemplo"
        self.addCleanup(os.environ.pop, "DERVS_ALVO", None)

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


class ODuble:
    """Servidor de mentira que fala os contratos C2, C3 e C6 do plano.

    Sobe `http.server` numa thread, em 127.0.0.1, porta livre. `respostas` mapeia
    caminho -> lista de (codigo, dict); cada pedido consome a primeira, e a
    ultima se repete. `registro` guarda (metodo, caminho, corpo, cabecalhos).
    """

    def __init__(self, respostas):
        import http.server
        import threading
        duble = self
        self.respostas = {k: list(v) for k, v in respostas.items()}
        self.registro = []

        class Maneja(http.server.BaseHTTPRequestHandler):
            def log_message(self_, *a):
                pass

            def _responde(self_, metodo):
                n = int(self_.headers.get("Content-Length") or 0)
                corpo = self_.rfile.read(n) if n else b""
                duble.registro.append((metodo, self_.path, corpo,
                                       dict(self_.headers)))
                fila = duble.respostas.get(self_.path.split("?")[0])
                if not fila:
                    codigo, dados = 404, {"erro": "nao existe"}
                else:
                    codigo, dados = fila[0] if len(fila) == 1 else fila.pop(0)
                bruto = json.dumps(dados).encode("utf-8")
                self_.send_response(codigo)
                self_.send_header("Content-Type", "application/json")
                self_.send_header("Content-Length", str(len(bruto)))
                self_.end_headers()
                self_.wfile.write(bruto)

            def do_POST(self_):
                self_._responde("POST")

            def do_GET(self_):
                self_._responde("GET")

        self.servidor = http.server.HTTPServer(("127.0.0.1", 0), Maneja)
        self.alvo = "http://127.0.0.1:%d" % self.servidor.server_address[1]
        self.fio = threading.Thread(target=self.servidor.serve_forever, daemon=True)
        self.fio.start()

    def fechar(self):
        self.servidor.shutdown()
        self.servidor.server_close()
        self.fio.join(5)

    def chamadas(self, caminho):
        return [r for r in self.registro if r[1].split("?")[0] == caminho]


PEDIDO_OK = (200, {"pedido": "p" * 43, "codigo": "K7M4-2QXP",
                   "minutos": 10, "intervalo": 5})


class EscolherAPastaNoWindows(unittest.TestCase):
    """Python embutivel nao traz tkinter: a pasta vem do PowerShell 5.1.

    `os.name` e `subprocess.run` sao dubles. A prova real (a janela abrir, o
    antivirus deixar) e manual e esta no plano, F-2.
    """

    def setUp(self):
        self.nt = unittest.mock.patch.object(os, "name", "nt")
        self.nt.start()
        self.addCleanup(self.nt.stop)

    def _run(self, retorno=None, erro=None):
        vistos = {}

        class Fim:
            returncode = 0
            stdout = b""
            stderr = b""

        fim = Fim()
        for k, v in (retorno or {}).items():
            setattr(fim, k, v)

        def falso(argv, **kw):
            vistos["argv"], vistos["kw"] = argv, kw
            if erro:
                raise erro
            return fim

        mock = unittest.mock.patch.object(subprocess, "run", falso)
        mock.start()
        self.addCleanup(mock.stop)
        return vistos

    def test_argv_e_lista_com_powershell_noprofile_e_sta(self):
        vistos = self._run({"stdout": b"C:\\projetos\r\n"})
        self.assertEqual("C:\\projetos", conectador.escolher_pasta("C:\\sug"))
        argv = vistos["argv"]
        self.assertIsInstance(argv, list)
        self.assertEqual("powershell.exe", argv[0])
        self.assertIn("-NoProfile", argv)
        self.assertIn("-STA", argv)
        self.assertFalse(vistos["kw"].get("shell", False))

    def test_a_sugestao_vai_no_ambiente_e_nunca_no_argv(self):
        vistos = self._run({"stdout": b"C:\\p"})
        conectador.escolher_pasta("C:\\Users\\a b'c\\repos")
        self.assertFalse(any("a b'c" in a for a in vistos["argv"]),
                         "caminho no argv atravessaria o interpretador")
        self.assertEqual("C:\\Users\\a b'c\\repos",
                         vistos["kw"]["env"]["DERVS_SUGESTAO"])

    def test_script_do_powershell_e_ascii(self):
        vistos = self._run({"stdout": b"C:\\p"})
        conectador.escolher_pasta("C:\\x")
        for a in vistos["argv"]:
            self.assertTrue(a.isascii(), a)

    def test_acento_no_caminho_volta_em_utf8_sem_bom(self):
        self._run({"stdout": "\ufeffC:\\Proje\u00e7\u00f5es\r\n".encode("utf-8")})
        self.assertEqual("C:\\Proje\u00e7\u00f5es",
                         conectador.escolher_pasta("C:\\x"))

    def test_fechar_a_janela_e_vazio_e_nao_cai_para_o_teclado(self):
        """Cancelar e resposta, nao defeito: nao pergunta de novo."""
        self._run({"stdout": b"", "returncode": 0})

        def explodir(*a, **k):
            raise AssertionError("nao podia perguntar pelo teclado")
        antes = conectador.pasta_pelo_teclado
        conectador.pasta_pelo_teclado = explodir
        self.addCleanup(setattr, conectador, "pasta_pelo_teclado", antes)
        self.assertEqual("", conectador.escolher_pasta("C:\\x"))

    def test_oserror_cai_para_tkinter_e_depois_para_o_teclado(self):
        self._run(erro=OSError("sem powershell"))
        chamadas = []
        antes = conectador.pasta_pelo_teclado
        conectador.pasta_pelo_teclado = lambda s: chamadas.append(s) or "D:/k"
        self.addCleanup(setattr, conectador, "pasta_pelo_teclado", antes)
        tk_antes = (sys.modules.get("tkinter"),
                    sys.modules.get("tkinter.filedialog"))
        sys.modules["tkinter"] = None           # sem Tcl/Tk: ImportError
        sys.modules["tkinter.filedialog"] = None

        def devolver():
            for nome, antes_ in zip(("tkinter", "tkinter.filedialog"), tk_antes):
                if antes_ is None:
                    sys.modules.pop(nome, None)
                else:
                    sys.modules[nome] = antes_
        self.addCleanup(devolver)
        self.assertEqual("D:/k", conectador.escolher_pasta("C:\\x"))
        self.assertEqual(["C:\\x"], chamadas)

    def test_constrained_language_mode_codigo_de_saida_cai_para_o_proximo(self):
        """`Add-Type` falha em CLM: o processo sai com erro e stdout vazio."""
        self._run({"returncode": 1, "stdout": b""})
        self.assertIsNone(conectador.pelo_powershell("C:\\x"))


class OPedidoEAEsperaPeloNavegador(unittest.TestCase):
    """Contratos C2 e C3, contra um servidor de mentira de verdade."""

    def setUp(self):
        self.dormidos = []
        antes = conectador.dormir
        conectador.dormir = self.dormidos.append
        self.addCleanup(setattr, conectador, "dormir", antes)
        self.abertos = []
        navegador = conectador.webbrowser.open
        conectador.webbrowser.open = lambda url, *a, **k: self.abertos.append(url)
        self.addCleanup(setattr, conectador.webbrowser, "open", navegador)
        self.saida, antes_out = io.StringIO(), sys.stdout
        sys.stdout = self.saida
        self.addCleanup(setattr, sys, "stdout", antes_out)

    def _duble(self, respostas):
        d = ODuble(respostas)
        self.addCleanup(d.fechar)
        return d

    def test_abre_o_navegador_na_tela_com_o_codigo_e_devolve_o_token(self):
        d = self._duble({"/agente/pedir": [PEDIDO_OK],
                         "/agente/esperar": [(202, {"estado": "esperando",
                                                    "intervalo": 5}),
                                             (200, {"token": "tk-secreto"})]})
        token = conectador.conectar_pelo_navegador(d.alvo, "PC-DO-ZE")
        self.assertEqual("tk-secreto", token)
        self.assertEqual([d.alvo + "/#/conectar?autorizar=K7M4-2QXP"],
                         self.abertos)
        corpo = json.loads(d.chamadas("/agente/pedir")[0][2])
        self.assertEqual({"maquina": "PC-DO-ZE"}, corpo)
        esperas = d.chamadas("/agente/esperar")
        self.assertEqual(2, len(esperas))
        self.assertEqual({"pedido": "p" * 43}, json.loads(esperas[0][2]))

    def test_mostra_o_codigo_e_o_nome_e_nunca_o_token(self):
        d = self._duble({"/agente/pedir": [PEDIDO_OK],
                         "/agente/esperar": [(200, {"token": "tk-secreto"})]})
        conectador.conectar_pelo_navegador(d.alvo, "PC-DO-ZE")
        texto = self.saida.getvalue()
        self.assertIn("K7M4-2QXP", texto)
        self.assertIn("PC-DO-ZE", texto)
        self.assertNotIn("tk-secreto", texto)
        self.assertNotIn("p" * 43, texto)       # o pedido e segredo do PC

    def test_404_na_espera_e_sem_token_e_nao_insiste(self):
        d = self._duble({"/agente/pedir": [PEDIDO_OK],
                         "/agente/esperar": [(404, {"erro": "nao existe"})]})
        self.assertEqual("", conectador.conectar_pelo_navegador(d.alvo, "pc"))
        self.assertEqual(1, len(d.chamadas("/agente/esperar")))

    def test_429_dobra_o_intervalo(self):
        d = self._duble({"/agente/pedir": [PEDIDO_OK],
                         "/agente/esperar": [(429, {"erro": "nao deu"}),
                                             (202, {"estado": "esperando"}),
                                             (200, {"token": "t"})]})
        self.assertEqual("t", conectador.conectar_pelo_navegador(d.alvo, "pc"))
        self.assertEqual([10, 10], self.dormidos)

    def test_o_prazo_acaba_e_devolve_vazio(self):
        pedido = (200, {"pedido": "p" * 43, "codigo": "K7M4-2QXP",
                        "minutos": 1, "intervalo": 5})
        d = self._duble({"/agente/pedir": [pedido],
                         "/agente/esperar": [(202, {"estado": "esperando"})]})
        self.assertEqual("", conectador.conectar_pelo_navegador(d.alvo, "pc"))
        self.assertLessEqual(sum(self.dormidos), 60 + 5)
        self.assertGreaterEqual(sum(self.dormidos), 55)

    def test_pedir_recusado_nao_abre_navegador(self):
        for codigo in (400, 429, 503):
            d = self._duble({"/agente/pedir": [(codigo, {"erro": "x"})]})
            self.assertEqual("", conectador.conectar_pelo_navegador(d.alvo, "pc"))
        self.assertEqual([], self.abertos)

    def test_pedido_sem_codigo_ou_torto_nao_vira_url(self):
        """O codigo entra numa URL: so o alfabeto do servidor passa."""
        for ruim in ("K7M4-2QXP&x=1", "k7m4-2qxp", "", "../x", "K7M4 2QXP"):
            d = self._duble({"/agente/pedir": [(200, {
                "pedido": "p" * 43, "codigo": ruim, "minutos": 10,
                "intervalo": 5})]})
            self.assertEqual("", conectador.conectar_pelo_navegador(d.alvo, "pc"))
        self.assertEqual([], self.abertos)

    def test_servidor_fora_do_ar_devolve_vazio(self):
        self.assertEqual("", conectador.conectar_pelo_navegador(
            "http://127.0.0.1:1", "pc"))


class OMoldeDoArquivoCmd(unittest.TestCase):
    """`conectador.cmd`: o que o servidor entrega junto com o Python.

    Nenhum teste de CI RODA o lote (a CI e Linux): aqui so se confere a forma.
    A prova de que ele funciona e abrir no Windows, e esta no plano (F-2).
    """

    @classmethod
    def setUpClass(cls):
        cls.caminho = Path(conectador.__file__).parent / "conectador.cmd"
        cls.bruto = cls.caminho.read_bytes()
        cls.texto = cls.bruto.decode("ascii")      # nao decodifica = nao e ASCII

    def test_e_ascii(self):
        self.assertTrue(self.bruto.isascii())

    def test_tem_o_que_o_plano_manda(self):
        for peca in ("curl.exe", "certutil -hashfile", "tar.exe",
                     r"%LOCALAPPDATA%\DERVS",
                     "https://www.python.org/ftp/python/3.14.8/"
                     "python-3.14.8-embed-amd64.zip"):
            self.assertIn(peca, self.texto)

    def test_o_hash_e_um_sha256_de_64_hexadecimais(self):
        import re
        achados = re.findall(r'(?i)set "SHA=([0-9a-f]+)"', self.texto)
        self.assertEqual(1, len(achados))
        self.assertRegex(achados[0], r"^[0-9a-fA-F]{64}$")

    def test_o_zip_e_apagado_no_ramo_do_hash_diferente(self):
        linhas = self.texto.splitlines()
        i = next(n for n, l in enumerate(linhas) if "certutil -hashfile" in l)
        ate_a_saida = []
        for l in linhas[i + 1:]:
            ate_a_saida.append(l)
            if "exit /b" in l:
                break
        self.assertTrue(any(" del " in " " + l.lower() for l in ate_a_saida),
                        "hash diferente tem de apagar o zip antes de sair")

    def test_termina_em_exit_b_errorlevel(self):
        uteis = [l.strip() for l in self.texto.splitlines()
                 if l.strip() and not l.strip().lower().startswith(("rem ", "::"))]
        self.assertEqual("exit /b %ERRORLEVEL%", uteis[-1])

    def test_nao_tem_a_linha_do_marcador_nem_truques_proibidos(self):
        self.assertFalse(any(l.startswith("#:DERVS-PYTHON")
                             for l in self.texto.splitlines()))
        baixo = self.texto.lower()
        for ruim in ("-encodedcommand", "-enc ", "bitsadmin",
                     "invoke-expression", "iex"):
            self.assertNotIn(ruim, baixo)

    def test_o_codigo_do_dash_c_nao_tem_percentual(self):
        import re
        c = re.search(r'-c "([^"]*)"', self.texto)
        self.assertIsNotNone(c)
        self.assertNotIn("%", c.group(1))

    def test_a_extracao_devolve_um_python_que_compila(self):
        """Roda o `-c` do molde de verdade, com o arquivo montado como o
        servidor monta (molde, marcador, conectador.py, tudo em CRLF)."""
        import re
        fonte = Path(conectador.__file__).read_text(encoding="utf-8")
        montado = "\r\n".join(self.texto.splitlines()
                              + ["#:DERVS-PYTHON"] + fonte.splitlines()) + "\r\n"
        c = re.search(r'-c "([^"]*)"', self.texto).group(1)
        with tempfile.TemporaryDirectory() as pasta:
            entrada = Path(pasta) / "conectar-dervs.cmd"
            saida = Path(pasta) / "conectador.py"
            entrada.write_bytes(montado.encode("ascii"))
            fim = subprocess.run([sys.executable, "-I", "-c", c, str(entrada),
                                  str(saida)], capture_output=True, timeout=60)
            self.assertEqual(0, fim.returncode, fim.stderr)
            extraido = saida.read_text(encoding="utf-8")
        ast.parse(extraido)
        self.assertEqual(fonte.splitlines(), extraido.splitlines())


if __name__ == "__main__":
    unittest.main(verbosity=2)
