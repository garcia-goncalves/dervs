# -*- coding: utf-8 -*-
"""O workflow de publicacao leva ao servidor o que abre a porta.

POR QUE ESTE ARQUIVO EXISTE.

Em 28/08/2026 o dervs.com.br foi publicado com a verificacao verde, o dominio
respondendo 200 e a aparencia certa na tela. E **ninguem conseguia entrar**.

A cadeia era esta, e cada elo estava individualmente correto:

  - em producao `/entrar/local` NAO entra na tabela de rotas (`servir.py`,
    `if E_LOCAL:`), entao `/entrar/github` e a unica porta que existe;
  - `/entrar/github` responde 404 sem `DERVS_GITHUB_ID` e `DERVS_GITHUB_SECRET`;
  - as duas moravam no repositorio como variable e secret desde 27/08, e o
    workflow de publicacao nunca as levava para o `/opt/dervs/.env`;
  - e o roteiro de operacao chamava esse passo de **opcional**, com a frase "o
    site sobe igual, so sem o botao".

Nenhum teste podia falhar, porque nenhum teste olhava para esse caminho.

A cortina tinha o mesmo formato de defeito, um degrau adiante: a combinacao de
seis digitos nasce sorteada na primeira subida e e impressa uma vez, no registro
daquele container. Cada publicacao recria o container. `cortina.trocar()` existia
desde a etapa 9 e **nada no produto o chamava** — perder o numero era ficar
trancado para fora do proprio site, sem recuperacao.

Este arquivo le o `publicar.yml` como texto e como YAML. Ele nao publica nada e
nao precisa de rede.

    python test_publicar.py
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

AQUI = Path(__file__).parent
WORKFLOW = AQUI / ".github" / "workflows" / "publicar.yml"


def texto() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def passo_do_servidor() -> str:
    """O passo que fala com a VPS, como texto.

    A GUARDA vem junto de proposito: se o nome do passo mudar e este recorte
    voltar vazio, todos os casos abaixo passariam sobre string vazia — verdes,
    e sobre nada. E a lei 2 deste repositorio aplicada ao proprio teste.
    """
    t = texto()
    i = t.index("- name: Trocar o container")
    j = t.index("\n      - name:", i + 10)
    trecho = t[i:j]
    assert len(trecho) > 2000, (
        "o passo do servidor saiu com %d caracteres; o recorte quebrou e os "
        "casos seguintes passariam vazios." % len(trecho))
    return trecho


class APortaChegaAoServidor(unittest.TestCase):
    """As credenciais do OAuth App, sem as quais nao ha entrada nenhuma."""

    def setUp(self):
        self.passo = passo_do_servidor()

    def test_o_workflow_le_as_duas_credenciais_do_repositorio(self):
        for origem in ("vars.DERVS_GITHUB_ID", "secrets.DERVS_GITHUB_SECRET"):
            self.assertIn(
                origem, self.passo,
                "o passo do servidor nao le %s. Sem isso o /opt/dervs/.env "
                "sobe sem credencial e /entrar/github responde 404 — e em "
                "producao nao ha segunda porta." % origem)

    def test_as_duas_sao_gravadas_no_env_do_servidor(self):
        for chave in ("DERVS_GITHUB_ID=", "DERVS_GITHUB_SECRET="):
            self.assertRegex(
                self.passo, r">>\s*\.env\.novo" ,
                "nada e acrescentado ao .env do servidor.")
            self.assertIn(
                'echo "%s' % chave, self.passo,
                "%s nao e escrita no .env do servidor." % chave)

    def test_o_valor_nao_viaja_pela_linha_de_comando(self):
        """O achado da etapa 16, aplicado ao que foi acrescentado depois.

        `ssh alvo VAR=segredo comando` e `docker exec -e VAR=segredo` poem o
        valor no argv, legivel em /proc/<pid>/cmdline por qualquer conta local
        da VPS — que serve outros oito sistemas. Tudo tem de ir por STDIN.
        """
        self.assertNotRegex(
            self.passo, r"docker exec [^\n]*-e\s+\w+=",
            "docker exec -e poe o valor no argv do processo; use STDIN.")
        for nome in ("OAUTH_SECRET", "CORTINA"):
            # `%q` cita o valor para o shell remoto; o bloco inteiro entra pelo
            # STDIN do ssh, que nenhum `ps` mostra.
            self.assertIn(
                "printf '" + nome + "=%q", self.passo,
                nome + " nao viaja por STDIN citado com %q.")

    def test_faltar_credencial_avisa_em_vez_de_silenciar(self):
        """Publicar sem porta pode ser uma escolha; nao pode ser uma surpresa."""
        self.assertIn("AVISO: sem DERVS_GITHUB_ID", self.passo,
                      "sem as credenciais a publicacao segue calada.")


class ACortinaTemVolta(unittest.TestCase):
    """A combinacao de seis digitos pode ser trocada de fora."""

    def setUp(self):
        self.passo = passo_do_servidor()

    def test_o_workflow_chama_cortina_trocar(self):
        self.assertIn(
            "cortina.trocar(", self.passo,
            "nada no workflow chama cortina.trocar(). A combinacao nasce "
            "sorteada, e impressa uma vez no registro do container, e o "
            "registro morre na publicacao seguinte: sem esta chamada, perder "
            "o numero e perder o site.")

    def test_a_troca_e_opcional(self):
        """Sem o segredo, a publicacao nao pode falhar nem trocar nada."""
        self.assertIn('if [ -n "${CORTINA:-}" ]; then', self.passo,
                      "a troca da cortina nao esta atras de um teste de vazio.")

    def test_cortina_trocar_existe_com_essa_assinatura(self):
        """O workflow chama codigo de verdade, nao um nome que ja mudou."""
        import cortina
        self.assertTrue(callable(cortina.trocar))
        with self.assertRaises(ValueError):
            cortina.trocar("12345", None)   # cinco digitos param antes do banco


class ExisteUmaConta(unittest.TestCase):
    """A terceira peca da primeira subida.

    Cortina aberta e botao do GitHub ligado nao bastam: `convidar()` e a unica
    porta para criar conta, e nada a chamava no servidor. O sintoma nao ajuda
    ninguem — o retorno do GitHub responde igual no sucesso e no fracasso, de
    proposito, entao autorizar caia na capa sem uma palavra.
    """

    def setUp(self):
        self.passo = passo_do_servidor()

    def test_o_workflow_convida_o_dono(self):
        self.assertIn(
            "autenticacao.convidar(", self.passo,
            "nada no workflow cria a conta do dono. O site sobe com a porta "
            "aberta e nenhuma conta atras dela.")

    def test_o_convite_nao_se_repete(self):
        """`convidar` estoura na segunda vez, e nao ha comando para apagar
        conta criada errada: repetir cegamente quebraria toda publicacao
        seguinte."""
        self.assertIn("SELECT 1 FROM usuario WHERE email = ?", self.passo,
                      "o convite nao consulta se a PESSOA ja tem conta. Contar"
                      " credenciais no total pularia o segundo dono para"
                      " sempre: o DERVS tem mais de um.")
        self.assertNotIn("convidar(login, email) || true", self.passo)

    def test_o_erro_de_verdade_nao_e_engolido(self):
        """Idempotencia pela contagem, nunca por `|| true`: um `|| true` faria
        falha de rede e conta-ja-existe darem a mesma linha verde."""
        for engolidor in ("|| true", "|| echo", "2>/dev/null"):
            self.assertNotIn(
                "convidar" + engolidor, self.passo.replace(" ", ""))

    def test_login_e_email_nao_vao_pelo_argv(self):
        self.assertNotRegex(
            self.passo, r"autenticacao\.py convidar",
            "o CLI recebe login e e-mail como argumentos, e argv e legivel em "
            "/proc por qualquer conta local da VPS. Use STDIN.")
        self.assertIn("printf 'DONOS=%q", self.passo)

    def test_convidar_existe_com_essa_assinatura(self):
        import autenticacao
        self.assertTrue(callable(autenticacao.convidar))


class PublicarContinuaSendoDecisaoDeGente(unittest.TestCase):
    """O que foi acrescentado nao pode ter afrouxado a trava principal."""

    def test_o_unico_gatilho_e_o_botao(self):
        t = texto()
        cabeca = t[:t.index("jobs:")]
        for automatico in ("on: push", "\n  push:", "\n  schedule:",
                           "\n  workflow_run:", "\n  pull_request:"):
            self.assertNotIn(
                automatico, cabeca,
                "gatilho automatico %r no workflow de publicacao." % automatico)
        self.assertIn("workflow_dispatch:", cabeca)

    def test_a_palavra_publicar_continua_exigida(self):
        self.assertIn("inputs.confirmar == 'PUBLICAR'", texto())

    def test_publicacao_cortada_no_meio_nao_e_permitida(self):
        self.assertIn("cancel-in-progress: false", texto())


if __name__ == "__main__":
    unittest.main(verbosity=2)
