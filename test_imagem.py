# -*- coding: utf-8 -*-
"""A imagem de produção leva tudo o que precisa, e nada além.

POR QUE ESTE ARQUIVO EXISTE.

Na etapa 16 o `Dockerfile` foi aberto pela primeira vez desde a etapa 7. Entre
uma coisa e outra nasceram sete arquivos de runtime — `autenticacao.py`,
`cortina.py`, `passkey.py`, `p256.py`, `index-cortina.html`, `portas.html` e a
pasta `assets/` — e NENHUM deles estava na lista de cópia. A imagem morria no
primeiro `import autenticacao`, e a verificação automática continuava verde o
tempo todo, porque ela roda os testes, não a imagem.

Este é o tipo de defeito que só aparece no dia da publicação, com o site fora do
ar e alguém procurando a causa às pressas. O teste abaixo o transforma numa
linha vermelha antes do commit.

As duas perguntas são simétricas, e as duas importam:

  - FALTA ALGUMA COISA? Todo módulo que `servir.py` importa, direta ou
    indiretamente, tem de entrar na imagem. Senão ela nem sobe.
  - SOBRA ALGUMA COISA? `execucao.py`, `fila.py` e `barreira.py` estão fora de
    propósito, e `vivo/` está fora porque uma linha dele rodando no servidor é
    execução remota de comando aberta para a internet. A doutrina do
    `Dockerfile` é que a barreira é a imagem, não a ausência de rota.

Este arquivo lê o `Dockerfile` como texto. Ele não constrói imagem e não precisa
de Docker instalado — quem confere a imagem de verdade é o workflow de
publicação, que a sobe e bate na porta dela antes de trocar o que está no ar.

    python test_imagem.py
"""
from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

AQUI = Path(__file__).resolve().parent
DOCKERFILE = AQUI / "Dockerfile"

# O que NUNCA pode entrar, mesmo que alguém acrescente sem querer.
PROIBIDOS = ("execucao.py", "fila.py", "barreira.py", "hub.db", "cofre.chave",
             "agente/executor.py")

# O pacote que `GET /agente/pacote` entrega a um computador (contrato C6 do
# plano do Conectar simples), na mesma ordem de `Hub.PACOTE`. O servidor LE
# estes arquivos do disco: nenhum e importado por ele por este caminho, entao
# so este teste os pega faltando. `agente/executor.py` NAO esta aqui de
# proposito - o computador so mede.
PACOTE_DO_COMPUTADOR = ("agente/__init__.py", "agente/enviar.py", "coletar.py",
                        "banco.py", "documentos.py", "tarefas.py")


def copiados() -> set[str]:
    """O que o Dockerfile copia, pelo nome, na forma `COPY origem /destino`."""
    achados = set()
    for linha in DOCKERFILE.read_text(encoding="utf-8").splitlines():
        limpa = linha.strip()
        if not limpa.upper().startswith("COPY "):
            continue
        # As opções do COPY (`--chown=`, `--from=`) vêm antes da origem. Sem
        # descartá-las, `partes[1]` pegaria a opção no lugar do nome do
        # arquivo: o arquivo real ficaria fora de `copiados()` e o teste
        # acusaria como faltando algo que na verdade entrou. Apontado pela
        # revisão de Python de 28/08/2026 — hoje o Dockerfile não usa opção
        # nenhuma, e é justamente por isso que valia consertar antes.
        partes = [p for p in limpa.split()[1:] if not p.startswith("--")]
        if len(partes) >= 2:
            achados.add(partes[0].rstrip("/"))
    return achados


def modulos_de_runtime() -> set[str]:
    """Todo módulo local que `servir.py` alcança, seguindo import por import.

    Vai fundo de propósito: `servir.py` importa `autenticacao`, que importa
    `github_app`, que importa `p256`. Uma lista feita à mão pararia no primeiro
    nível e deixaria passar exatamente o que quebrou na etapa 16.
    """
    locais = {p.stem for p in AQUI.glob("*.py")}
    vistos: set[str] = set()
    fila = ["servir"]
    while fila:
        modulo = fila.pop()
        if modulo in vistos:
            continue
        vistos.add(modulo)
        arquivo = AQUI / (modulo + ".py")
        if not arquivo.exists():
            continue
        arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
        for no in ast.walk(arvore):
            if isinstance(no, ast.Import):
                for apelido in no.names:
                    raiz = apelido.name.split(".")[0]
                    if raiz in locais:
                        fila.append(raiz)
            elif isinstance(no, ast.ImportFrom) and no.module and no.level == 0:
                raiz = no.module.split(".")[0]
                if raiz in locais:
                    fila.append(raiz)
    return vistos


class OQueAImagemPrecisa(unittest.TestCase):

    def test_todo_modulo_importado_entra_na_imagem(self):
        copia = copiados()
        faltando = sorted("%s.py" % m for m in modulos_de_runtime()
                          if "%s.py" % m not in copia)
        self.assertEqual(
            faltando, [],
            "O Dockerfile nao copia estes modulos, e o servidor os importa. "
            "A imagem morre na subida, com ImportError, e nenhum teste pega: "
            "%s" % ", ".join(faltando))

    def test_os_coletores_entram_mesmo_sem_aparecer_como_import(self):
        """`servir.py` chama os coletores como processo separado, por caminho.

        Eles não aparecem em nenhum `import`, então o teste de cima não os vê.
        Sem eles as camadas quebram no primeiro ciclo — e quebram calado, num
        subprocesso, longe do log principal.
        """
        copia = copiados()
        for coletor in ("coletar.py", "coletar_github.py", "coletar_pesado.py",
                        "github_app.py"):
            self.assertIn(coletor, copia,
                          "%s e chamado por servir.py e nao esta na imagem"
                          % coletor)

    def test_as_paginas_e_os_assets_entram(self):
        """A pasta `assets/` é o caso mais traiçoeiro dos três.

        `servir.py` monta a lista de estáticos permitidos LENDO A PASTA na
        subida. Sem ela a lista nasce vazia: o servidor sobe, responde 200 na
        página, e a página chega sem folha de estilo e sem fonte nenhuma. Nada
        no log diz por quê.
        """
        copia = copiados()
        for arquivo in ("index.html", "index-cortina.html", "portas.html",
                        "casos.json", "robots.txt", "assets", "conectador.py",
                        "conectador.cmd"):
            self.assertIn(arquivo, copia,
                          "%s e servido em producao e nao esta na imagem"
                          % arquivo)

    def test_o_conectador_entra_LIDO_e_nunca_importado(self):
        """O caso que a pergunta "falta alguma coisa?" nao pega sozinha.

        `servir.py` LE o `conectador.py` do disco e injeta o codigo de
        pareamento; ele nao o importa. Entao o arquivo e invisivel para
        `test_todo_modulo_importado_entra_na_imagem`, e uma rota que responde
        200 aqui quebraria em producao — o modo de falha exato da etapa 16.

        A outra metade importa igual: importar o conectador arrastaria
        `tkinter` para dentro do servidor, e `tkinter` nao esta na imagem.
        """
        self.assertIn("conectador.py", copiados())
        self.assertNotIn("conectador", modulos_de_runtime(),
                         "servir.py passou a IMPORTAR o conectador; isso traz "
                         "tkinter para dentro do servidor")
        fonte = (AQUI / "servir.py").read_text(encoding="utf-8")
        arvore = ast.parse(fonte)
        for no in ast.walk(arvore):
            if isinstance(no, ast.Import):
                self.assertNotIn("conectador", [a.name for a in no.names])
            elif isinstance(no, ast.ImportFrom):
                self.assertNotEqual("conectador", no.module)


    def test_o_pacote_do_computador_inteiro_entra_na_imagem(self):
        """O servidor LE estes seis arquivos e os entrega por `/agente/pacote`.
        Faltar um na imagem e o servidor responder 503 so em producao."""
        copia = copiados()
        for arquivo in PACOTE_DO_COMPUTADOR:
            with self.subTest(arquivo=arquivo):
                self.assertIn(arquivo, copia,
                              "%s e entregue ao computador e nao esta na imagem"
                              % arquivo)

    def test_o_pacote_nao_leva_o_braco_executor(self):
        self.assertNotIn("agente/executor.py", PACOTE_DO_COMPUTADOR)
        self.assertNotIn("agente/executor.py", copiados())

    def test_o_pacote_e_lido_nunca_importado(self):
        """`agente` e pacote, nao modulo da raiz: se `servir.py` o importasse,
        o executor viria junto e o Dockerfile teria de leva-lo."""
        self.assertNotIn("agente", modulos_de_runtime())


class OQueAImagemNaoPodeLevar(unittest.TestCase):

    def test_nada_de_execucao_fila_barreira_banco_ou_cofre(self):
        copia = copiados()
        for proibido in PROIBIDOS:
            self.assertNotIn(
                proibido, copia,
                "%s entrou na imagem. Ver a doutrina no topo do Dockerfile."
                % proibido)

    def test_nenhum_teste_vai_para_producao(self):
        entraram = sorted(c for c in copiados() if c.startswith("test_"))
        self.assertEqual(entraram, [])

    def test_nada_de_copy_ponto_ponto(self):
        """`COPY . .` levaria vivo/, os testes, a documentação e — no dia em
        que o `.dockerignore` fosse editado sem cuidado — o `hub.db` e a chave
        do cofre. A cópia é por nome, e é assim que se prova o que entrou."""
        texto = DOCKERFILE.read_text(encoding="utf-8")
        for linha in texto.splitlines():
            limpa = linha.strip()
            if limpa.startswith("#") or not limpa.upper().startswith("COPY "):
                continue
            self.assertNotRegex(
                limpa, r"^COPY\s+\.\s",
                "O Dockerfile voltou a usar copia em bloco: %s" % limpa)
            self.assertNotIn(
                "*", limpa,
                "Curinga na copia esconde o que entra na imagem: %s" % limpa)

    def test_vivo_nao_entra_nem_por_engano(self):
        copia = copiados()
        self.assertFalse(
            [c for c in copia if c.startswith("vivo")],
            "vivo/ abre um terminal sem autenticacao. Ele nao vai para o ar.")


class OQueAImagemPromete(unittest.TestCase):
    """Os ajustes de produção que moram no próprio Dockerfile."""

    def setUp(self):
        self.texto = DOCKERFILE.read_text(encoding="utf-8")

    def test_o_banco_mora_fora_da_imagem(self):
        """Sem isto, toda conta e todo pareamento somem a cada publicação."""
        self.assertRegex(self.texto, r"DERVS_BANCO=/dados/hub\.db")
        self.assertRegex(self.texto, r'VOLUME\s+\["/dados"\]')

    def test_escuta_em_todas_as_interfaces_dentro_do_container(self):
        """127.0.0.1 dentro do container é o loopback DO CONTAINER: o nginx
        nunca chegaria lá, e o erro seria mudo — 502 e nenhuma linha de log."""
        self.assertRegex(self.texto, r"DERVS_ESCUTA=0\.0\.0\.0")

    def test_nao_mede_a_maquina_onde_roda(self):
        """No servidor a varredura local volta com zero projetos, e gravar esse
        zero por cima do que o agente mandou é a lei 2 sendo violada."""
        self.assertRegex(self.texto, r"DERVS_COLETA_LOCAL=0")

    def test_o_processo_nao_e_root(self):
        self.assertTrue(
            re.search(r"^USER dervs\s*$", self.texto, re.MULTILINE),
            "O Dockerfile nao troca para o usuario sem privilegio.")

    def test_tem_healthcheck(self):
        """Container que subiu não é container que respondeu."""
        self.assertIn("HEALTHCHECK", self.texto)


if __name__ == "__main__":
    unittest.main(verbosity=2)
