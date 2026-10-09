"""Provas do `ajudante_servidor.py` - o programa que roda no SERVIDOR do dono.

Ele mexe com o Docker, o gerenciador de servicos e a rede. A CI roda sem nada
disso, entao TUDO aqui e por duble: `rodar` e `abrir` falsos, uma raiz
temporaria no lugar da "/" e nenhum processo de verdade. O que os dubles nao
provam (Docker e systemd reais) esta nomeado em `docs/operacao/ligar-um-servidor.md`.

Os guardas de FONTE sao funcoes que recebem o texto, e cada um e provado
sabotando uma copia em memoria: guarda que nunca reprova nao guarda nada.
"""

import ast
import datetime
import json
import os
import re
import shutil
import sys
import tempfile
import time
import unittest
import unittest.mock
from pathlib import Path

import ajudante_servidor as aj

FORMATO_ESPERADO = '{{.Name}}\t{{.State.Status}}\t{{if .State.Health}}{{.State.Health.Status}}{{end}}\t{{.State.StartedAt}}\t{{.RestartCount}}\t{{.Config.Image}}\t{{index .Config.Labels "com.docker.compose.project"}}\t{{index .Config.Labels "org.opencontainers.image.revision"}}'

PROIBIDO = re.compile(
    r"\bEnv\b|\.env\b|\.conf\b|\{\{\s*json|\.Config\.Env|executor"
    r"|agente/(pacote|relatorio|resultado|voz)|\blogs\b")

FONTE = Path(aj.__file__).read_text(encoding="ascii")


def problemas_do_fonte(fonte):
    """Tudo que a lei do arquivo proibe, de uma vez. [] = limpo."""
    achados = []
    if not fonte.isascii():
        achados.append("nao e ASCII puro")
    try:
        arvore = ast.parse(fonte, feature_version=(3, 8))
    except SyntaxError as e:
        return achados + ["nao e Python 3.8: %s" % e]
    marcas = [l for l in fonte.splitlines() if l.rstrip().endswith("# DERVS:ALVO")]
    if len(marcas) != 1:
        achados.append("a marca DERVS:ALVO deveria aparecer em 1 linha")
    if PROIBIDO.search(fonte):
        achados.append("texto proibido: %s" % PROIBIDO.search(fonte).group(0))

    padrao = set(sys.stdlib_module_names)
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            nomes = [a.name.split(".")[0] for a in no.names]
        elif isinstance(no, ast.ImportFrom):
            nomes = ["."] if no.level else [(no.module or "").split(".")[0]]
        else:
            continue
        achados += ["import fora da padrao: %s" % n for n in nomes
                    if n not in padrao]

    # "docker" so nos dois comandos de leitura.
    liberados = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id in ("ARGV_DO_PS", "ARGV_DO_INSPECT")
                for t in no.targets):
            liberados |= {id(n) for n in ast.walk(no.value)}
    for no in ast.walk(arvore):
        if (isinstance(no, ast.Constant) and no.value == "docker"
                and id(no) not in liberados):
            achados.append("literal 'docker' fora dos dois comandos de leitura")

    # `subprocess` so dentro de `rodar`, com lista e sem shell.
    dentro = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.FunctionDef) and no.name == "rodar":
            dentro |= {id(n) for n in ast.walk(no)}
    for no in ast.walk(arvore):
        if isinstance(no, ast.Name) and no.id == "subprocess" \
                and id(no) not in dentro:
            achados.append("subprocess fora de `rodar`")
        if isinstance(no, ast.Attribute) and no.attr in ("system", "popen"):
            achados.append("os.%s existe" % no.attr)
        if isinstance(no, ast.keyword) and no.arg == "shell" and not (
                isinstance(no.value, ast.Constant) and no.value.value is False):
            achados.append("shell diferente de False")
        if (isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute)
                and no.func.attr == "run" and no.args
                and isinstance(no.args[0], ast.Constant)):
            achados.append("subprocess.run com texto, nao lista")
    if not any(isinstance(n, ast.keyword) and n.arg == "shell"
               for n in ast.walk(arvore)):
        achados.append("`shell=False` deveria estar escrito")

    # `if __name__` no fim.
    linhas = fonte.splitlines()
    idx = [i for i, l in enumerate(linhas) if l.startswith("if __name__")]
    if len(idx) != 1 or any(l.strip() and not l.startswith((" ", "\t"))
                            for l in linhas[idx[0] + 1:] if idx):
        achados.append("`if __name__` fora do fim")
    return achados


class OFonteObedeceAsLeis(unittest.TestCase):

    def test_o_fonte_de_verdade_esta_limpo(self):
        self.assertEqual([], problemas_do_fonte(FONTE))

    def test_o_formato_do_inspect_e_o_do_contrato(self):
        self.assertEqual(FORMATO_ESPERADO, aj.FORMATO_DO_INSPECT)
        self.assertEqual(("docker", "ps", "-aq", "--no-trunc"), aj.ARGV_DO_PS)
        self.assertEqual(("docker", "inspect", "--format", FORMATO_ESPERADO),
                         aj.ARGV_DO_INSPECT)

    def test_a_marca_do_painel_e_o_alvo_vazio(self):
        self.assertEqual("", aj.ALVO)

    # Cada sabotagem abaixo e uma copia em memoria: o guarda tem de acusar.
    def _acusa(self, trocar, por, trecho):
        self.assertIn(trocar, FONTE, "a sabotagem nao acharia o alvo")
        achados = problemas_do_fonte(FONTE.replace(trocar, por, 1))
        self.assertTrue(any(trecho in a for a in achados),
                        "o guarda nao acusou %r: %s" % (trecho, achados))

    def test_acusa_o_json_inteiro_do_inspect(self):
        self._acusa('{{.Config.Image}}', '{{json .Config.Env}}', "proibido")

    def test_acusa_um_terceiro_comando_do_docker(self):
        self._acusa('USUARIO = "dervs-ajudante"',
                    'USUARIO = "docker"', "docker")

    def test_acusa_shell_verdadeiro(self):
        self._acusa("shell=False", "shell=True", "shell")

    def test_acusa_import_de_fora(self):
        self._acusa("import datetime\n", "import datetime\nimport requests\n",
                    "import fora")

    def test_acusa_acento(self):
        self._acusa("Nada foi alterado.", "Nada foi alteradoç.", "ASCII")

    def test_acusa_sintaxe_nova_demais(self):
        self._acusa("def _tira(valor):",
                    "def _tira(valor):\n    match valor:\n        case 1:\n"
                    "            return 1\n    return 2\n\n\ndef _tira2(valor):",
                    "3.8")

    def test_acusa_subprocess_fora_do_rodar(self):
        self._acusa("def _root():", "def _root():\n    subprocess.call(['x'])\n"
                    "    return 0\n\n\ndef _root_velho():", "fora de `rodar`")

    def test_acusa_dunder_main_no_meio(self):
        self._acusa('if __name__ == "__main__":\n    sys.exit(main())\n',
                    'if __name__ == "__main__":\n    sys.exit(main())\nX = 1\n',
                    "fora do fim")

    def test_acusa_ler_a_saida_dos_registros(self):
        self._acusa("Roda UM programa.", "Roda UM programa. Tambem le logs.",
                    "proibido")


class Dubles:
    """`rodar` e `abrir` falsos que gravam o que receberam."""

    def __init__(self, respostas_rodar=None, roteiro_abrir=None):
        self.chamadas = []
        self.requisicoes = []
        self.respostas_rodar = respostas_rodar or {}
        self.roteiro_abrir = roteiro_abrir or {}
        self.sonos = []

    def rodar(self, argv, prazo):
        self.chamadas.append(list(argv))
        for prefixo, resposta in self.respostas_rodar.items():
            if tuple(argv[:len(prefixo)]) == prefixo:
                return resposta
        return True, ""

    def abrir(self, metodo, url, corpo, token, prazo):
        self.requisicoes.append((metodo, url, corpo, token))
        for sufixo, respostas in self.roteiro_abrir.items():
            if url.endswith(sufixo):
                if isinstance(respostas, list):
                    return respostas.pop(0) if len(respostas) > 1 else respostas[0]
                return respostas
        return 0, None

    def dormir(self, segundos):
        self.sonos.append(segundos)

    def argvs(self, programa):
        return [c for c in self.chamadas if c[0] == programa]

    def urls(self):
        return [u.rsplit("/agente/", 1)[-1] for _, u, _, _ in self.requisicoes]


TOKEN = "tok-de-teste"
PEDIDO = {"pedido": "p" * 24, "codigo": "K7M4-2QXP", "minutos": 10, "intervalo": 2}


def roteiro_feliz():
    return {"/agente/pedir": (200, dict(PEDIDO)),
            "/agente/esperar": [(202, {"estado": "esperando"}),
                                (200, {"token": TOKEN})],
            "/agente/servidor": (200, {"ok": True, "invalidos": 0})}


class ComRaiz(unittest.TestCase):
    ALVO = "https://painel.exemplo.test"

    def setUp(self):
        self.pasta = tempfile.mkdtemp(prefix="ajudante-")
        self.addCleanup(shutil.rmtree, self.pasta, True)
        self.raiz = self.pasta
        (Path(self.raiz) / "run" / "systemd" / "system").mkdir(parents=True)
        log = Path(self.raiz) / "var" / "log" / "deploy"
        log.mkdir(parents=True)
        self.historico = log / "historico.log"
        self.historico.write_text("", encoding="ascii")
        proc = Path(self.raiz) / "proc"
        proc.mkdir()
        (proc / "uptime").write_text("123456.78 99999.0\n")
        (proc / "loadavg").write_text("0.12 0.30 0.25 1/200 999\n")
        (proc / "meminfo").write_text(
            "MemTotal:        4000000 kB\nMemFree: 1 kB\n"
            "MemAvailable:    1200000 kB\n")
        quem = unittest.mock.patch.object(
            shutil, "which", lambda n, *a, **k: "/usr/bin/" + n)
        quem.start()
        self.addCleanup(quem.stop)

    def instalar(self, d, **extra):
        saidas = []
        args = dict(alvo=self.ALVO, raiz=self.raiz, rodar=d.rodar, abrir=d.abrir,
                    dormir=d.dormir, eh_root=lambda: True,
                    dono=lambda c, u: None, nome="vps-teste", saida=saidas.append)
        args.update(extra)
        return aj.instalar(**args), saidas


class AInstalacao(ComRaiz):

    def test_instala_pareia_e_liga_o_temporizador(self):
        d = Dubles(respostas_rodar={("id",): (False, "")},
                   roteiro_abrir=roteiro_feliz())
        codigo, saidas = self.instalar(d)
        self.assertEqual(aj.OK, codigo)
        texto = "\n".join(saidas)
        self.assertIn("K7M4-2QXP", texto)
        self.assertIn(self.ALVO + "/#/conectar?autorizar=K7M4-2QXP", texto)
        self.assertNotIn(TOKEN, texto)
        self.assertNotIn(PEDIDO["pedido"], texto)
        # o pedido leva o nome limpo e o tipo
        self.assertEqual(("POST", self.ALVO + "/agente/pedir",
                          {"maquina": "vps-teste", "tipo": "servidor"}, None),
                         d.requisicoes[0])
        # o token gravado, com o alvo
        cfg = Path(self.raiz) / "var" / "lib" / "dervs-ajudante" / "agente.json"
        self.assertEqual({"alvo": self.ALVO, "token": TOKEN},
                         json.loads(cfg.read_text()))
        if os.name != "nt":
            self.assertEqual(0o600, cfg.stat().st_mode & 0o777)
            self.assertEqual(0o700, cfg.parent.stat().st_mode & 0o777)
        # a copia de si mesmo
        self.assertTrue((Path(self.raiz) / "opt" / "dervs-ajudante"
                         / "dervs-ajudante.py").is_file())
        # usuario
        useradd = d.argvs("useradd")
        self.assertEqual(1, len(useradd))
        self.assertEqual(["useradd", "--system", "--no-create-home", "--shell",
                          "/usr/sbin/nologin", "--groups", "docker",
                          "dervs-ajudante"], useradd[0])
        # ACLs: pasta, arquivo, padrao; nenhuma segue link simbolico
        self.assertEqual(3, len(d.argvs("setfacl")))
        for argv in d.argvs("setfacl"):
            self.assertEqual("-P", argv[1], argv)
        self.assertNotIn("historico", texto)       # deu certo: nada a avisar
        self.assertIn(["systemctl", "daemon-reload"], d.chamadas)
        self.assertIn(["systemctl", "enable", "--now", "dervs-ajudante.timer"],
                      d.chamadas)
        # a primeira medicao subiu com o token
        self.assertEqual(TOKEN, d.requisicoes[-1][3])
        self.assertTrue(d.requisicoes[-1][1].endswith("/agente/servidor"))

    def test_as_unidades_do_systemd(self):
        d = Dubles(roteiro_abrir=roteiro_feliz())
        self.instalar(d)
        base = Path(self.raiz) / "etc" / "systemd" / "system"
        servico = (base / "dervs-ajudante.service").read_text().splitlines()
        for linha in ("Type=oneshot", "User=dervs-ajudante",
                      "NoNewPrivileges=yes", "ProtectSystem=strict",
                      "ProtectHome=yes", "PrivateTmp=yes",
                      "ReadWritePaths=/var/lib/dervs-ajudante",
                      "RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6",
                      "UMask=0077", "PrivateDevices=yes",
                      "ProtectKernelTunables=yes", "ProtectKernelModules=yes",
                      "ProtectControlGroups=yes", "RestrictSUIDSGID=yes",
                      "LockPersonality=yes", "CapabilityBoundingSet=",
                      "ExecStart=%s /opt/dervs-ajudante/dervs-ajudante.py medir"
                      % sys.executable):
            self.assertIn(linha, servico)
        tempo = (base / "dervs-ajudante.timer").read_text().splitlines()
        for linha in ("OnBootSec=30s", "OnUnitActiveSec=30s", "AccuracySec=1s",
                      "WantedBy=timers.target"):
            self.assertIn(linha, tempo)

    def test_o_dono_do_acesso_e_trocado_pelo_descritor_nunca_pelo_caminho(self):
        """A pasta e do usuario do ajudante: ele poderia trocar `agente.json`
        por um link para um arquivo do sistema, e o root seguiria o link."""
        vistos = []
        d = Dubles(roteiro_abrir=roteiro_feliz())
        codigo, _ = self.instalar(d, dono=lambda c, u: vistos.append((c, u)))
        self.assertEqual(aj.OK, codigo)
        arquivo = str(Path(self.raiz) / "var" / "lib" / "dervs-ajudante"
                      / "agente.json")
        self.assertNotIn(arquivo, [c for c, _ in vistos])
        self.assertNotIn(arquivo + ".novo", [c for c, _ in vistos])
        self.assertTrue(any(isinstance(c, int) and u == "dervs-ajudante"
                            for c, u in vistos), vistos)
        if os.name != "nt":
            with unittest.mock.patch.object(os, "chmod") as chmod:
                self.instalar(Dubles(roteiro_abrir={
                    **roteiro_feliz(), "/agente/servidor": (401, {})}))
            self.assertNotIn(arquivo, [c.args[0] for c in chmod.call_args_list])

    def test_setfacl_que_falha_avisa_que_o_no_ar_vai_ser_nao_sei(self):
        d = Dubles(respostas_rodar={("setfacl",): (False, "")},
                   roteiro_abrir=roteiro_feliz())
        codigo, saidas = self.instalar(d)
        self.assertEqual(aj.OK, codigo)
        texto = "\n".join(saidas)
        self.assertIn("Aviso: nao consegui dar ao ajudante a leitura do historico"
                      " de publicacoes.", texto)
        self.assertIn("'nao sei'", texto)
        self.assertTrue(texto.isascii())

    def test_reinstalar_com_acesso_morto_pede_autorizacao_de_novo(self):
        """O dono tirou o servidor no painel e cola a linha de novo: o acesso
        guardado da 401. A linha tem de resolver, nao repetir o erro."""
        self.instalar(Dubles(roteiro_abrir=roteiro_feliz()))
        d = Dubles(roteiro_abrir={
            "/agente/pedir": (200, dict(PEDIDO)),
            "/agente/esperar": (200, {"token": "tok-novo"}),
            "/agente/servidor": [(401, {}), (200, {"ok": True})]})
        codigo, saidas = self.instalar(d)
        self.assertEqual(aj.OK, codigo, saidas)
        self.assertEqual(["servidor", "pedir", "esperar", "servidor"], d.urls())
        self.assertEqual("tok-novo", d.requisicoes[-1][3])
        cfg = Path(self.raiz) / "var" / "lib" / "dervs-ajudante" / "agente.json"
        self.assertEqual("tok-novo", json.loads(cfg.read_text())["token"])
        texto = "\n".join(saidas)
        self.assertIn("K7M4-2QXP", texto)
        self.assertNotIn("Cole a linha", texto)     # o 401 ja foi resolvido aqui

    def test_acesso_morto_de_novo_nao_vira_laco(self):
        self.instalar(Dubles(roteiro_abrir=roteiro_feliz()))
        d = Dubles(roteiro_abrir={
            "/agente/pedir": (200, dict(PEDIDO)),
            "/agente/esperar": (200, {"token": "tok-novo"}),
            "/agente/servidor": (401, {})})
        codigo, saidas = self.instalar(d)
        self.assertEqual(1, d.urls().count("pedir"))
        self.assertEqual(2, d.urls().count("servidor"))
        self.assertEqual(aj.OK, codigo)
        self.assertIn("A primeira medicao nao subiu agora", "\n".join(saidas))

    def test_rodar_de_novo_nao_pede_outro_codigo(self):
        d = Dubles(roteiro_abrir=roteiro_feliz())
        self.instalar(d)
        d2 = Dubles(roteiro_abrir=roteiro_feliz())
        codigo, _ = self.instalar(d2)
        self.assertEqual(aj.OK, codigo)
        self.assertNotIn("pedir", d2.urls())
        self.assertNotIn("esperar", d2.urls())
        self.assertEqual(TOKEN, d2.requisicoes[0][3])

    def test_alvo_diferente_pede_de_novo(self):
        self.instalar(Dubles(roteiro_abrir=roteiro_feliz()))
        d = Dubles(roteiro_abrir=roteiro_feliz())
        self.instalar(d, alvo="https://outro.exemplo.test")
        self.assertIn("pedir", d.urls())

    def test_o_usuario_que_ja_existe_nao_e_recriado(self):
        d = Dubles(roteiro_abrir=roteiro_feliz())
        self.instalar(d)
        self.assertEqual([["id", "dervs-ajudante"]], d.argvs("id"))
        d = Dubles(respostas_rodar={("id",): (False, "")},
                   roteiro_abrir=roteiro_feliz())
        self.instalar(d)
        self.assertEqual(1, len(d.argvs("useradd")))

    def test_sem_root(self):
        d = Dubles()
        codigo, saidas = self.instalar(d, eh_root=lambda: False)
        self.assertEqual(aj.SEM_ROOT, codigo)
        self.assertEqual([], d.chamadas)
        self.assertIn("sudo", "\n".join(saidas))

    def test_sem_systemd_nada_e_alterado(self):
        shutil.rmtree(Path(self.raiz) / "run")
        d = Dubles()
        codigo, _ = self.instalar(d)
        self.assertEqual(aj.SEM_REQUISITO, codigo)
        self.assertEqual([], d.chamadas)
        self.assertEqual([], d.requisicoes)

    def test_sem_docker(self):
        with unittest.mock.patch.object(shutil, "which", lambda *a, **k: None):
            d = Dubles()
            codigo, _ = self.instalar(d)
        self.assertEqual(aj.SEM_REQUISITO, codigo)
        self.assertEqual([], d.chamadas)

    def test_python_velho_demais(self):
        with unittest.mock.patch.object(sys, "version_info", (3, 6, 0)):
            d = Dubles()
            codigo, _ = self.instalar(d)
        self.assertEqual(aj.SEM_REQUISITO, codigo)

    def test_painel_sem_resposta(self):
        codigo, _ = self.instalar(Dubles())
        self.assertEqual(aj.SEM_REDE, codigo)
        self.assertFalse((Path(self.raiz) / "etc").exists())

    def test_painel_recusa_o_pedido(self):
        d = Dubles(roteiro_abrir={"/agente/pedir": (400, {"erro": "x"})})
        codigo, _ = self.instalar(d)
        self.assertEqual(aj.RECUSADO, codigo)

    def test_dono_nao_autoriza(self):
        d = Dubles(roteiro_abrir={"/agente/pedir": (200, dict(PEDIDO)),
                                  "/agente/esperar": (404, {"erro": "x"})})
        codigo, _ = self.instalar(d)
        self.assertEqual(aj.SEM_PAREAMENTO, codigo)
        self.assertFalse((Path(self.raiz) / "etc").exists())
        self.assertFalse((Path(self.raiz) / "var" / "lib" / "dervs-ajudante"
                          / "agente.json").exists())

    def test_o_429_dobra_a_espera_e_o_prazo_acaba(self):
        d = Dubles(roteiro_abrir={"/agente/pedir": (200, dict(PEDIDO)),
                                  "/agente/esperar": (429, {})})
        codigo, _ = self.instalar(d)
        self.assertEqual(aj.SEM_PAREAMENTO, codigo)
        self.assertEqual([4, 8, 16, 32, 60], d.sonos[:5])

    def test_o_codigo_torto_do_painel_e_recusado(self):
        torto = dict(PEDIDO, codigo="../../etc")
        d = Dubles(roteiro_abrir={"/agente/pedir": (200, torto)})
        codigo, _ = self.instalar(d)
        self.assertEqual(aj.RECUSADO, codigo)

    def test_systemctl_que_falha_nao_diz_ligado(self):
        d = Dubles(respostas_rodar={("systemctl", "enable"): (False, "")},
                   roteiro_abrir=roteiro_feliz())
        codigo, saidas = self.instalar(d)
        self.assertEqual(aj.SEM_REQUISITO, codigo)
        self.assertNotIn("Ligado", "\n".join(saidas))


INSPECT = "\n".join([
    "/dervs-app\trunning\thealthy\t2026-10-08T12:00:00.123456789Z\t0\tdervs:vps\tdervs\t96eb3fc1234567890123456789012345678901a",
    "/ajudei-db\trestarting\t\t2026-10-09T01:02:03Z\t2\tpostgres:16\t<no value>\t<no value>",
    "/parado\texited\t\t0001-01-01T00:00:00Z\t0\talpine\t\t",
    ""])


class AMedicao(ComRaiz):

    def preparar(self, historico="", inspect=INSPECT, ps="abc123\ndef456\n"):
        pasta = Path(self.raiz) / "var" / "lib" / "dervs-ajudante"
        pasta.mkdir(parents=True, exist_ok=True)
        (pasta / "agente.json").write_text(
            json.dumps({"alvo": self.ALVO, "token": TOKEN}))
        self.historico.write_text(historico, encoding="ascii")
        return Dubles(
            respostas_rodar={aj.ARGV_DO_PS: (True, ps),
                             aj.ARGV_DO_INSPECT[:3]: (True, inspect)},
            roteiro_abrir={"/agente/servidor": (200, {"ok": True})})

    def medir(self, d):
        codigo = aj.medir(alvo=self.ALVO, raiz=self.raiz, rodar=d.rodar,
                          abrir=d.abrir)
        return codigo, (d.requisicoes[-1][2] if d.requisicoes else None)

    def test_o_corpo_so_tem_as_chaves_do_contrato(self):
        d = self.preparar()
        codigo, corpo = self.medir(d)
        self.assertEqual(aj.OK, codigo)
        self.assertEqual({"versao", "docker_mudo", "servidor", "sistemas",
                          "publicacoes"}, set(corpo))
        self.assertEqual(1, corpo["versao"])
        self.assertIs(False, corpo["docker_mudo"])
        self.assertEqual({"ligado_s", "carga_1m", "carga_5m", "carga_15m",
                          "memoria_total_kb", "memoria_disponivel_kb",
                          "disco_total_b", "disco_livre_b"},
                         set(corpo["servidor"]))
        for s in corpo["sistemas"]:
            self.assertEqual({"nome", "projeto", "estado", "saude", "desde",
                              "reinicios", "imagem", "sha"}, set(s))
        self.assertEqual(TOKEN, d.requisicoes[-1][3])
        self.assertEqual(self.ALVO + "/agente/servidor", d.requisicoes[-1][1])

    def test_o_servidor_le_o_proc(self):
        _, corpo = self.medir(self.preparar())
        s = corpo["servidor"]
        self.assertEqual(123456, s["ligado_s"])
        self.assertEqual((0.12, 0.3, 0.25),
                         (s["carga_1m"], s["carga_5m"], s["carga_15m"]))
        self.assertEqual((4000000, 1200000),
                         (s["memoria_total_kb"], s["memoria_disponivel_kb"]))
        if hasattr(os, "statvfs"):
            self.assertGreater(s["disco_total_b"], 0)
        else:
            self.assertIsNone(s["disco_total_b"])

    def test_os_sistemas_saem_limpos(self):
        d = self.preparar()
        _, corpo = self.medir(d)
        por_nome = {s["nome"]: s for s in corpo["sistemas"]}
        self.assertEqual(["dervs-app", "ajudei-db", "parado"],
                         [s["nome"] for s in corpo["sistemas"]])
        app = por_nome["dervs-app"]
        self.assertEqual(("running", "healthy", "2026-10-08T12:00:00+00:00", 0,
                          "dervs:vps", "dervs"),
                         (app["estado"], app["saude"], app["desde"],
                          app["reinicios"], app["imagem"], app["projeto"]))
        self.assertEqual("96eb3fc1234567890123456789012345678901a", app["sha"])
        db = por_nome["ajudei-db"]
        self.assertEqual(("", "", "", 2), (db["projeto"], db["sha"],
                                           db["saude"], db["reinicios"]))
        self.assertEqual("2026-10-09T01:02:03+00:00", db["desde"])
        self.assertEqual("", por_nome["parado"]["desde"])
        # os dois comandos do contrato, e nada mais do Docker
        docker = d.argvs("docker")
        self.assertEqual(list(aj.ARGV_DO_PS), docker[0])
        self.assertEqual(list(aj.ARGV_DO_INSPECT) + ["abc123", "def456"],
                         docker[1])
        self.assertEqual(2, len(docker))

    def test_no_maximo_200_ids_vao_ao_inspect(self):
        ids = "\n".join("%064x" % i for i in range(300))
        d = self.preparar(ps=ids)
        self.medir(d)
        self.assertEqual(200, len(d.argvs("docker")[1]) - 4)

    def test_docker_que_falha_marca_mudo(self):
        d = self.preparar()
        d.respostas_rodar[aj.ARGV_DO_PS] = (False, "")
        _, corpo = self.medir(d)
        self.assertIs(True, corpo["docker_mudo"])
        self.assertEqual([], corpo["sistemas"])

    def test_inspect_que_falha_tambem_marca_mudo(self):
        d = self.preparar()
        d.respostas_rodar[aj.ARGV_DO_INSPECT[:3]] = (False, "")
        _, corpo = self.medir(d)
        self.assertIs(True, corpo["docker_mudo"])

    def test_linha_torta_nao_some_em_silencio(self):
        """Linha descartada e "nao consegui ver tudo", nunca um sistema a menos."""
        for torta in ("linha torta sem tabs",
                      "\trunning\t\t2026-10-09T01:02:03Z\t0\tx\t\t",
                      INSPECT.splitlines()[0] + "\tcampo-a-mais"):
            with self.subTest(torta=torta):
                d = self.preparar(inspect=INSPECT + torta + "\n")
                _, corpo = self.medir(d)
                self.assertIs(True, corpo["docker_mudo"])
                self.assertEqual(["dervs-app", "ajudei-db", "parado"],
                                 [s["nome"] for s in corpo["sistemas"]])

    def test_inspect_que_falha_uma_vez_e_refeito_com_ps_novo(self):
        """O id sumiu entre o ps e o inspect: refaz os dois, uma vez."""
        d = self.preparar()
        voltas = []

        def rodar(argv, prazo):
            d.chamadas.append(list(argv))
            if tuple(argv) == aj.ARGV_DO_PS:
                return True, "abc123\n" if not voltas else "def456\n"
            voltas.append(1)
            return (False, "") if len(voltas) == 1 else (True, INSPECT)
        d.rodar = rodar
        _, corpo = self.medir(d)
        self.assertIs(False, corpo["docker_mudo"])
        self.assertEqual(3, len(corpo["sistemas"]))
        docker = d.argvs("docker")
        self.assertEqual([list(aj.ARGV_DO_PS), list(aj.ARGV_DO_INSPECT) + ["abc123"],
                          list(aj.ARGV_DO_PS), list(aj.ARGV_DO_INSPECT) + ["def456"]],
                         docker)

    def test_inspect_que_falha_duas_vezes_e_mudo(self):
        d = self.preparar()
        d.respostas_rodar[aj.ARGV_DO_INSPECT[:3]] = (False, "")
        _, corpo = self.medir(d)
        self.assertIs(True, corpo["docker_mudo"])
        self.assertEqual(4, len(d.argvs("docker")))

    @unittest.skipIf(os.name == "nt" or not hasattr(time, "tzset"),
                     "o fuso do processo so se troca fora do Windows")
    def test_a_hora_local_do_historico_sobe_em_utc_de_verdade(self):
        antes = os.environ.get("TZ")

        def voltar():
            if antes is None:
                os.environ.pop("TZ", None)
            else:
                os.environ["TZ"] = antes
            time.tzset()
        self.addCleanup(voltar)
        os.environ["TZ"] = "America/Sao_Paulo"
        time.tzset()
        hist = "2026-09-29 15:15:00 dervs tiba 20260929-151500-96eb3fc OK\n"
        _, corpo = self.medir(self.preparar(historico=hist))
        self.assertEqual("2026-09-29T18:15:00+00:00",
                         corpo["publicacoes"][0]["quando"])

    def test_docker_sem_nada_rodando_nao_e_mudo(self):
        _, corpo = self.medir(self.preparar(ps=""))
        self.assertIs(False, corpo["docker_mudo"])
        self.assertEqual([], corpo["sistemas"])

    def utc(self, texto):
        naive = datetime.datetime.strptime(texto, "%Y-%m-%d %H:%M:%S")
        return naive.astimezone(datetime.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S+00:00")

    def test_as_publicacoes_e_o_descarte_de_quem_fez(self):
        hist = "\n".join([
            "2026-09-29 15:15:00 dervs tiba 20260929-151500-96eb3fc OK",
            "2026-09-30 10:00:00 dervs tiba 20260930-100000-aaaaaaa FALHOU(build)-voltou",
            "2026-09-30 11:00:00 grimoire tiba 20260930-110000-bbbbbbb OK(voltou)",
            "2026-09-30 12:00:00 ajudei tiba 20260930-120000-ccccccc OK",
            "2026-10-01 12:00:00 ajudei tiba 20261001-120000-ddddddd FALHOU-AO-VOLTAR",
            "2026-10-02 09:00:00 novo tiba 20261002-090000-antes-do-primeiro-deploy OK(estado-original)",
            "so-cinco campos aqui nao 20261002-090000-eeeeeee",
            "FALHOU tiba sem data de verdade 1 2",
            ""])
        _, corpo = self.medir(self.preparar(historico=hist))
        pub = {p["projeto"]: p for p in corpo["publicacoes"]}
        self.assertEqual({"dervs", "grimoire", "ajudei", "novo"}, set(pub))
        # a falha que VOLTOU nao muda o que esta no ar
        self.assertEqual(("96eb3fc", "OK", self.utc("2026-09-29 15:15:00")),
                         (pub["dervs"]["sha"], pub["dervs"]["resultado"],
                          pub["dervs"]["quando"]))
        self.assertEqual("bbbbbbb", pub["grimoire"]["sha"])
        # a que NAO voltou deixa o estado desconhecido
        self.assertEqual("", pub["ajudei"]["sha"])
        self.assertEqual("FALHOU-AO-VOLTAR", pub["ajudei"]["resultado"])
        # a versao de antes do primeiro deploy nao tem commit
        self.assertEqual("", pub["novo"]["sha"])
        for p in pub.values():
            self.assertEqual({"projeto", "quando", "sha", "resultado"}, set(p))
        # quem fez a publicacao nunca sai da maquina
        self.assertNotIn("tiba", json.dumps(corpo))

    def test_um_ok_depois_do_ao_voltar_conserta_o_estado(self):
        hist = ("2026-10-01 12:00:00 ajudei tiba 20261001-120000-ddddddd FALHOU-AO-VOLTAR\n"
                "2026-10-01 12:00:00 ajudei tiba 20261001-120000-ddddddd OK\n"
                "2026-10-01 13:00:00 ajudei tiba 20261001-130000-eeeeeee OK\n")
        _, corpo = self.medir(self.preparar(historico=hist))
        self.assertEqual("eeeeeee", corpo["publicacoes"][0]["sha"])

    def test_sem_historico_nao_levanta(self):
        d = self.preparar()
        self.historico.unlink()
        _, corpo = self.medir(d)
        self.assertEqual([], corpo["publicacoes"])

    def test_sem_pareamento(self):
        d = Dubles()
        codigo = aj.medir(alvo=self.ALVO, raiz=self.raiz, rodar=d.rodar,
                          abrir=d.abrir)
        self.assertEqual(aj.SEM_PAREAMENTO, codigo)
        self.assertEqual([], d.requisicoes)

    def test_os_codigos_de_resposta(self):
        for resposta, esperado in ((200, aj.OK), (429, aj.OK),
                                   (401, aj.SEM_PAREAMENTO),
                                   (403, aj.RECUSADO), (500, aj.SEM_REDE),
                                   (0, aj.SEM_REDE)):
            d = self.preparar()
            d.roteiro_abrir["/agente/servidor"] = (resposta, {})
            codigo, _ = self.medir(d)
            self.assertEqual(esperado, codigo, resposta)

    def test_o_401_do_temporizador_manda_colar_a_linha_de_novo(self):
        d = self.preparar()
        d.roteiro_abrir["/agente/servidor"] = (401, {})
        ditos = []
        codigo = aj.medir(alvo=self.ALVO, raiz=self.raiz, rodar=d.rodar,
                          abrir=d.abrir, saida=ditos.append)
        self.assertEqual(aj.SEM_PAREAMENTO, codigo)
        self.assertEqual(["O painel nao reconhece mais este servidor. Cole a linha"
                          " do painel de novo neste servidor."], ditos)

    def test_o_corpo_serializa_em_ascii(self):
        _, corpo = self.medir(self.preparar())
        json.dumps(corpo).encode("ascii")


class ARemocao(ComRaiz):

    def test_remove_tudo_o_que_a_instalacao_pos(self):
        self.instalar(Dubles(roteiro_abrir=roteiro_feliz()))
        d = Dubles()
        codigo = aj.remover(raiz=self.raiz, rodar=d.rodar, eh_root=lambda: True)
        self.assertEqual(aj.OK, codigo)
        self.assertIn(["systemctl", "disable", "--now", "dervs-ajudante.timer"],
                      d.chamadas)
        self.assertIn(["systemctl", "daemon-reload"], d.chamadas)
        self.assertIn(["userdel", "dervs-ajudante"], d.chamadas)
        self.assertEqual(3, len(d.argvs("setfacl")))
        for argv in d.argvs("setfacl"):
            self.assertEqual("-P", argv[1], argv)
        for resto in ("etc/systemd/system/dervs-ajudante.service",
                      "etc/systemd/system/dervs-ajudante.timer",
                      "opt/dervs-ajudante", "var/lib/dervs-ajudante"):
            self.assertFalse((Path(self.raiz) / resto).exists(), resto)
        self.assertTrue(self.historico.exists())

    def test_sem_root_nao_remove_nada(self):
        d = Dubles()
        codigo = aj.remover(raiz=self.raiz, rodar=d.rodar, eh_root=lambda: False)
        self.assertEqual(aj.SEM_ROOT, codigo)
        self.assertEqual([], d.chamadas)


class OMain(unittest.TestCase):

    def test_o_comando_certo_vai_para_a_funcao_certa(self):
        for argv, nome in (([], "instalar"), (["instalar"], "instalar"),
                           (["medir"], "medir"), (["remover"], "remover")):
            with unittest.mock.patch.object(aj, nome, return_value=7) as f:
                self.assertEqual(7, aj.main(argv))
                f.assert_called_once_with()

    def test_comando_desconhecido_nao_faz_nada(self):
        with unittest.mock.patch.object(aj, "instalar") as f:
            self.assertEqual(1, aj.main(["apagar-tudo"]))
            f.assert_not_called()


class OsPortoesDeVerdade(unittest.TestCase):
    """`rodar` e `abrir` reais, contra coisas inofensivas."""

    def test_rodar_roda_uma_lista_sem_shell(self):
        ok, saida = aj.rodar([sys.executable, "-c", "print('oi; echo no')"], 20)
        self.assertTrue(ok)
        self.assertEqual("oi; echo no", saida.strip())

    def test_rodar_nao_levanta(self):
        self.assertEqual((False, ""), aj.rodar(["/nao/existe/mesmo"], 5))
        ok, _ = aj.rodar([sys.executable, "-c", "raise SystemExit(3)"], 20)
        self.assertFalse(ok)

    def test_abrir_sem_rede_devolve_zero(self):
        self.assertEqual((0, None),
                         aj.abrir("GET", "http://127.0.0.1:9/x", None, None, 2))

    def test_abrir_com_resposta_torta_do_http_nao_levanta(self):
        import http.client

        class Torto:
            def __init__(self, erro):
                self.erro = erro

            def open(self, pedido, timeout):
                raise self.erro
        for erro in (http.client.BadStatusLine("x"),
                     http.client.IncompleteRead(b"")):
            with self.subTest(erro=type(erro).__name__), \
                    unittest.mock.patch.object(aj, "_ABRIDOR", Torto(erro)):
                self.assertEqual((0, None),
                                 aj.abrir("GET", "http://x.test/y", None, None, 2))


if __name__ == "__main__":
    unittest.main()
