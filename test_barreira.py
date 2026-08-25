# -*- coding: utf-8 -*-
"""A barreira e uma lista de recusas — e lista de recusa so vale testada.

Cada teste aqui e um ataque concreto ou um comando honesto. Os dois lados
importam: barreira que barra o trabalho legitimo e desligada na primeira
sexta-feira, e ai nao protege nada.
"""
import io
import json
import unittest

import barreira


class ComandoHonestoPassa(unittest.TestCase):
    """O que a sessao PRECISA fazer para consertar alguma coisa."""

    def test_os_comandos_do_dia_a_dia(self):
        for comando in [
            "git status --porcelain",
            "git diff",
            "git add -A",
            'git commit -m "fix(env): alinha o .env.example"',
            "git log --oneline -5",
            "git -C . status",
            "python -m pytest -q",
            "python -m pytest test_fila.py::Teto -x",
            "pytest -q",
            "npm test",
            "npm run test -- --run",
            "ls -la",
            "cat package.json",
            "sed -n '1,40p' servir.py",
            "grep -rn 'TETO' fila.py",
            "find . -name '*.py'",
            "cat .env.example | head -20",
            "python -m pytest 2>/dev/null",
            "wc -l $(ls *.py)",
        ]:
            self.assertEqual(barreira.vetar_bash(comando), "", comando)


class OQueOriginouTudoIsto(unittest.TestCase):
    """`git push` saindo da copia alcancava o repositorio de verdade."""

    def test_push_direto(self):
        self.assertIn("alcança o repositório", barreira.vetar_bash("git push origin main"))

    def test_push_forcado_escondido_atras_de_um_and(self):
        motivo = barreira.vetar_bash("git add -A && git commit -m x && git push --force")
        self.assertIn("alcança o repositório", motivo)

    def test_push_com_o_C_antes(self):
        """`git -C pasta push`: o primeiro nao-hifen e "pasta", nao "push"."""
        self.assertIn("alcança o repositório", barreira.vetar_bash("git -C sub push"))

    def test_mexer_no_remoto(self):
        self.assertNotEqual(barreira.vetar_bash("git remote add mau http://x"), "")

    def test_cegar_a_trava_do_diff(self):
        """`git config diff.noprefix true` cegaria a trava para sempre."""
        self.assertNotEqual(barreira.vetar_bash("git config diff.noprefix true"), "")


class NadaSaiDaMaquina(unittest.TestCase):
    def test_os_que_falam_com_a_rede(self):
        for comando in ["curl http://x/y", "wget http://x", "gh pr create",
                        "ssh servidor", "scp a b", "docker run x",
                        "pip install requests", "npm install", "npx algo",
                        "aws s3 cp a b"]:
            self.assertNotEqual(barreira.vetar_bash(comando), "", comando)

    def test_a_frase_explica_que_e_a_rede(self):
        self.assertIn("rede", barreira.vetar_bash("curl http://x"))


class InterpretadorDeTextoSolto(unittest.TestCase):
    """Se `python -c` passa, a barreira esta lendo `python` e liberando tudo."""

    def test_python_c(self):
        self.assertNotEqual(
            barreira.vetar_bash('python -c "import urllib.request"'), "")

    def test_node_e(self):
        self.assertNotEqual(barreira.vetar_bash('node -e "require(\'http\')"'), "")

    def test_shell_dentro_do_shell(self):
        for comando in ["bash -c 'git push'", "sh script.sh", "powershell -c x",
                        "cmd /c dir", "xargs git push", "env curl http://x"]:
            self.assertNotEqual(barreira.vetar_bash(comando), "", comando)

    def test_python_m_so_libera_a_lista(self):
        self.assertNotEqual(barreira.vetar_bash("python -m pip install x"), "")
        self.assertNotEqual(barreira.vetar_bash("python -m http.server"), "")
        self.assertEqual(barreira.vetar_bash("python -m pytest"), "")

    def test_find_exec_roda_qualquer_coisa(self):
        self.assertNotEqual(
            barreira.vetar_bash("find . -name '*.py' -exec curl http://x {} ;"), "")


class OComandoEscondidoDentroDoOutro(unittest.TestCase):
    """Substituicao de comando e um comando — leitura ingenua nao ve."""

    def test_dentro_de_cifrao_parentese(self):
        self.assertNotEqual(barreira.vetar_bash("echo $(curl http://x)"), "")

    def test_dentro_de_crase(self):
        self.assertNotEqual(barreira.vetar_bash("echo `git push`"), "")

    def test_depois_de_um_pipe(self):
        self.assertNotEqual(barreira.vetar_bash("cat x | ssh servidor"), "")

    def test_depois_de_ponto_e_virgula(self):
        self.assertNotEqual(barreira.vetar_bash("ls ; gh pr merge 1"), "")


class NaoSaiDaCopia(unittest.TestCase):
    def test_caminho_absoluto(self):
        for comando in ["cat /etc/passwd", "cat C:/Users/Desktop/.claude/settings.json",
                        "cat ~/.ssh/id_rsa", "ls $HOME"]:
            self.assertNotEqual(barreira.vetar_bash(comando), "", comando)

    def test_subir_com_dois_pontos(self):
        self.assertNotEqual(barreira.vetar_bash("cat ../../segredo.txt"), "")

    def test_dev_null_continua_passando(self):
        """Barrar `2>/dev/null` seria transformar a barreira em pedra."""
        self.assertEqual(barreira.vetar_bash("python -m pytest 2>/dev/null"), "")

    def test_a_pasta_git_e_intocavel(self):
        """.git/hooks vira execucao de codigo no proximo commit."""
        self.assertNotEqual(barreira.vetar_bash("echo x > .git/hooks/pre-commit"), "")
        self.assertNotEqual(barreira.vetar_bash("cat .git/config"), "")

    def test_redirecao_e_o_caminho_lateral(self):
        """Quem so olha o programa ve um `echo` inocente."""
        self.assertNotEqual(
            barreira.vetar_bash("echo mau >> ../projeto-real/x.py"), "")


class OPorteiroDoWriteEDoEdit(unittest.TestCase):
    def test_escrever_fora_da_copia(self):
        self.assertNotEqual(barreira.vetar_caminho("C:/Users/Desktop/.claude/x.md"), "")

    def test_escrever_dentro_da_copia(self):
        self.assertEqual(barreira.vetar_caminho("src/app.py"), "")


class OContratoDoHook(unittest.TestCase):
    """0 deixa passar, 2 barra, e o motivo sai no stderr."""

    def _rodar(self, evento):
        erro = io.StringIO()
        codigo = barreira.main(io.StringIO(json.dumps(evento)), erro)
        return codigo, erro.getvalue()

    def test_comando_honesto_sai_zero(self):
        codigo, erro = self._rodar({"tool_name": "Bash",
                                    "tool_input": {"command": "git status"}})
        self.assertEqual(codigo, 0)
        self.assertEqual(erro, "")

    def test_comando_barrado_sai_dois_e_explica(self):
        codigo, erro = self._rodar({"tool_name": "Bash",
                                    "tool_input": {"command": "git push"}})
        self.assertEqual(codigo, 2)
        self.assertIn("Barrado pela barreira", erro)

    def test_ferramenta_que_nao_e_da_conta_dele_passa(self):
        codigo, _ = self._rodar({"tool_name": "Read",
                                 "tool_input": {"file_path": "/qualquer"}})
        self.assertEqual(codigo, 0)

    def test_evento_ilegivel_BARRA(self):
        """Porteiro que nao leu o cracha nao abre a porta."""
        erro = io.StringIO()
        self.assertEqual(barreira.main(io.StringIO("{nao e json"), erro), 2)

    def test_evento_vazio_nao_explode(self):
        erro = io.StringIO()
        self.assertEqual(barreira.main(io.StringIO(""), erro), 0)


if __name__ == "__main__":
    unittest.main()
