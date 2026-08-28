# -*- coding: utf-8 -*-
"""O vigia da superfície do servidor.

Este arquivo existe para responder, sozinho e para sempre, a uma pergunta:
**este servidor consegue rodar um comando na máquina de quem o hospeda?**

Até a etapa 7 do DERVS a resposta era sim, e nem dava para vê-la: o despacho
era uma cadeia de `if self.path…` espalhada por dois métodos, e a rota que
disparava uma sessão do Claude estava no meio dela.

TRÊS DECISÕES DE PROJETO, e as três são o ponto do teste:

1. **Ele lê `servir.ROTAS` em memória, não o texto do arquivo.** Um grep por
   `"/api/acao"` não veria `"/api/" + nome` — e uma rota montada por
   concatenação executa exatamente igual a uma escrita à mão. Importar o módulo
   e iterar a estrutura de verdade é a única leitura que não mente.

2. **Ele reprova se `ROTAS` não existir.** Sem isso, o jeito mais fácil de
   "consertar" este teste seria apagar a tabela e voltar para a cadeia de `if`,
   que é justamente o estado que ele foi escrito para impedir.

3. **Ele olha o comportamento, não só o nome** (acrescentado na revisão de
   26/08/2026). Nome é rótulo: uma rota `/api/diagnostico` apontando para
   `Hub._diagnostico` — dois nomes limpos — com `subprocess.run` dentro do corpo
   passava pelo vigia da primeira versão. Agora ele segue o grafo de chamadas.
   E confere que ninguém acrescentou um `do_PUT` à classe, que despacharia por
   fora da tabela inteira.

    python test_rotas.py
"""
from __future__ import annotations

import re
import unittest

import servir


# `exec` cobre `exec`, `execucao` e `executar`; `acao` cobre `/api/acao`.
# Lista de bloqueio, e não de permissão, de propósito: uma rota nova com nome
# criativo deve doer aqui antes de chegar ao servidor.
PROIBIDO = re.compile(r"acao|execucao|exec|terminal|pty|shell|comando|grafo",
                      re.IGNORECASE)

# O que a etapa 7 amputou. Se qualquer um destes reaparecer como atributo do
# módulo, alguém trouxe a execução de volta pela porta dos fundos.
AMPUTADOS = ("ACOES", "ACOES_SEM_PROJETO", "executar_acao", "caminho_do_grafo",
             "grafo_estado", "acao_git_push", "acao_docker_up", "acao_vscode",
             "executor_claude", "executor_mecanico", "execucao", "fila")


class ATabelaExiste(unittest.TestCase):
    """Sem a tabela não há vigia — e é por isso que a ausência dela reprova."""

    def test_rotas_existe_e_nao_esta_vazia(self):
        self.assertTrue(hasattr(servir, "ROTAS"),
                        "servir.ROTAS sumiu. O despacho voltou a ser uma cadeia "
                        "de if? Esta tabela é o contrato da etapa 7.")
        self.assertTrue(servir.ROTAS, "a tabela de rotas está vazia.")

    def test_toda_rota_tem_metodo_e_funcao_de_verdade(self):
        for caminho, rota in servir.ROTAS.items():
            self.assertIn(rota.metodo, ("GET", "POST"), caminho)
            self.assertTrue(callable(rota.funcao), caminho)


class NenhumaRotaExecutaComando(unittest.TestCase):
    """O coração do vigia."""

    def test_nenhum_caminho_cheira_a_execucao(self):
        for caminho in servir.ROTAS:
            with self.subTest(caminho=caminho):
                self.assertIsNone(PROIBIDO.search(caminho),
                                  "a rota %r casa com a lista de bloqueio. Se "
                                  "ela executa comando, ela não entra; se o "
                                  "nome só parece, troque o nome." % caminho)

    def test_nenhuma_funcao_de_rota_cheira_a_execucao(self):
        # O caminho pode ser inocente e o destino não: /api/tarefa apontando
        # para `executar_acao` passaria no teste acima.
        for caminho, rota in servir.ROTAS.items():
            with self.subTest(caminho=caminho):
                self.assertIsNone(PROIBIDO.search(rota.funcao.__name__),
                                  "%s aponta para %s" % (caminho,
                                                         rota.funcao.__name__))

    def test_as_rotas_antigas_nao_respondem_mais(self):
        for velha in ("/api/acao", "/api/execucao", "/grafo", "/grafo/",
                      "/api/grafo"):
            with self.subTest(rota=velha):
                self.assertIsNone(servir.ROTAS.get(velha))


class OModuloNaoGuardaMaisAExecucao(unittest.TestCase):
    """A tabela pode estar limpa e o módulo ainda carregar a arma."""

    def test_os_nomes_amputados_sumiram(self):
        for nome in AMPUTADOS:
            with self.subTest(nome=nome):
                self.assertFalse(
                    hasattr(servir, nome),
                    "servir.%s voltou. `execucao.py` e `fila.py` continuam no "
                    "repositório de propósito, mas SEM rota apontando para "
                    "eles." % nome)


# Nomes que, alcancados a partir de uma rota, significam execucao. Nao e uma
# lista de tudo que e perigoso — e a lista do que este servidor JAMAIS precisa
# fazer a pedido de uma requisicao. `coletar` entra porque ele roda os
# coletores por subprocess; o laco de tempo pode chama-lo, uma rota nao.
EXECUTA = {"subprocess", "system", "popen", "Popen", "spawnl", "spawnv",
           "spawnv_passfds", "execv", "execl", "execvp", "startfile", "eval",
           "exec", "compile", "__import__", "coletar"}

# Os unicos verbos HTTP que a classe pode responder. `do_HEAD` esta aqui porque
# ele recusa (405) — precisa existir para nao cair no handler de arquivos.
VERBOS_PERMITIDOS = {"do_GET", "do_POST", "do_HEAD"}


def _alcancaveis(funcao, vistos=None):
    """Todos os nomes que `funcao` usa, seguindo as chamadas dentro de `servir`.

    Olhar so o corpo da funcao da rota nao basta: `_dados` e inocente, mas ela
    chama `_estado`, que chama outra coisa. A execucao pode estar tres saltos
    abaixo de um nome inofensivo. Esta funcao anda o grafo de chamadas ate onde
    ele sai do modulo (banco, regras, memoria — modulos, nao funcoes daqui).
    """
    vistos = vistos if vistos is not None else set()
    codigo = getattr(funcao, "__code__", None)
    if codigo is None or id(funcao) in vistos:
        return set()
    vistos.add(id(funcao))
    nomes = set(codigo.co_names)
    for nome in list(nomes):
        alvo = getattr(servir.Hub, nome, None) or getattr(servir, nome, None)
        if callable(alvo):
            nomes |= _alcancaveis(alvo, vistos)
    return nomes


class NenhumaRotaAlcancaExecucao(unittest.TestCase):
    """O furo que a revisao de 26/08/2026 achou no primeiro vigia.

    Ele olhava so o NOME do caminho e o NOME da funcao. Uma rota chamada
    `/api/diagnostico` apontando para `Hub._diagnostico` — dois nomes limpos —
    com `subprocess.run(["git","push"])` dentro do corpo passava inteira.

    Nome e rotulo. Este teste olha o comportamento: segue o grafo de chamadas a
    partir de cada rota e reprova se ele alcanca qualquer forma de executar.
    """

    def test_nenhuma_rota_alcanca_subprocess(self):
        for caminho, rota in servir.ROTAS.items():
            with self.subTest(caminho=caminho):
                achados = _alcancaveis(rota.funcao) & EXECUTA
                self.assertEqual(achados, set(),
                                 "a rota %s alcanca %s" % (caminho,
                                                           sorted(achados)))

    def test_o_servidor_nao_cita_o_comando_que_apaga_conta(self):
        """`autenticacao.remover` nasceu em 28/08/2026 como comando de quem tem
        acesso a maquina, igual ao convite. Uma rota que o alcancasse daria a
        qualquer sessao o poder de apagar a conta do outro dono.

        O andarilho de cima nao serve aqui: `servir` ja importa `autenticacao`
        para a volta do GitHub, entao o nome do modulo e alcancavel de forma
        legitima. O que nao pode existir e a CHAMADA, e ela e um texto exato.
        """
        import inspect
        fonte = inspect.getsource(servir)
        self.assertNotIn("autenticacao.remover", fonte)
        self.assertIn("autenticacao.", fonte,
                      "se o modulo deixar de ser usado aqui, o teste acima "
                      "passa por ausencia e para de vigiar")

    def test_o_andarilho_realmente_enxerga_o_corpo(self):
        """Se `_alcancaveis` parasse de andar, o teste acima passaria vazio.

        `_dados` nao cita `banco` no proprio corpo — quem cita e `_estado`, um
        salto abaixo. Ver `banco` aqui prova que o andarilho desceu.
        """
        self.assertIn("banco", _alcancaveis(servir.Hub._dados))


class NenhumVerboEscapaDaTabela(unittest.TestCase):
    """O segundo furo da mesma revisao.

    O `BaseHTTPRequestHandler` despacha por `do_<METODO>`: basta alguem definir
    um `do_PUT` na classe para existir um caminho que nunca passa por `ROTAS`,
    nunca aparece em `sorted(servir.ROTAS)` e nunca entra no radar dos testes
    acima. A tabela so e o contrato enquanto ela for o UNICO contrato.
    """

    def test_a_classe_nao_ganhou_verbo_novo(self):
        verbos = {n for n in dir(servir.Hub) if n.startswith("do_")}
        sobrando = verbos - VERBOS_PERMITIDOS
        self.assertEqual(sobrando, set(),
                         "Hub.%s despacha por fora da tabela de rotas"
                         % sorted(sobrando))


class ODespachoUsaSoATabela(unittest.TestCase):
    """Rota que existe fora da tabela é rota que o vigia não enxerga."""

    def test_get_e_post_apenas_despacham(self):
        # Se `do_GET` voltar a ter lógica própria, ele volta a ser um lugar
        # onde uma rota pode morar escondida da tabela.
        for metodo in ("do_GET", "do_POST"):
            with self.subTest(metodo=metodo):
                fonte = getattr(servir.Hub, metodo).__code__
                self.assertNotIn("path", fonte.co_names,
                                 "%s voltou a olhar self.path direto." % metodo)
                self.assertIn("_despachar", fonte.co_names)

    def test_a_query_nao_muda_a_rota(self):
        # `/api/dados?x=1` tem de casar `/api/dados` — e `/api/acao?x` não pode
        # virar nada.
        self.assertIn("/api/dados", servir.ROTAS)
        self.assertNotIn("/api/dados?x=1", servir.ROTAS)


class TodaRotaDeclaraAcesso(unittest.TestCase):
    """NEGA POR PADRAO, INCLUSIVE NO TESTE (etapa 9).

    A armadilha que este bloco existe para fechar: a lista de rotas protegidas
    ser escrita a mao num `if` em algum lugar, e nascer desatualizada na
    primeira rota nova. Aqui a lista nao existe -- cada rota carrega a propria
    classificacao no terceiro campo da tupla, e ROTA SEM CLASSIFICACAO REPROVA
    A SUITE. Esquecer de classificar nao pode dar acesso.
    """

    # A quarta entrou na etapa 11, e ela e diferente das outras tres: nao e
    # pessoa do outro lado, e uma MAQUINA com token proprio. Alargar este
    # conjunto e a unica forma legitima de acrescentar uma classe de acesso —
    # e por isso os dois testes logo abaixo cobram, nominalmente, que ela
    # signifique alguma coisa no despacho.
    VALIDOS = servir.ACESSOS      # a lista mora em servir.py, e so la

    def test_toda_rota_declara_acesso(self):
        for caminho, rota in servir.ROTAS.items():
            with self.subTest(rota=caminho):
                self.assertIn(getattr(rota, "acesso", None), self.VALIDOS,
                              "rota sem classificacao declarada: %s" % caminho)

    def test_a_tupla_tem_os_tres_campos(self):
        """Sem isto, voltar `Rota` para dois campos faria o teste acima passar
        por `getattr` devolvendo None em tudo -- e ai o vigia mentiria."""
        self.assertEqual(servir.Rota._fields, ("metodo", "funcao", "acesso"))

    def test_o_que_le_dado_do_dono_exige_sessao(self):
        """A classificacao nao pode ser so um rotulo bonito: as rotas que
        chegam ao banco do dono tem de estar em `dado`, nominalmente."""
        for caminho in ("/api/dados", "/api/silenciar"):
            self.assertEqual(servir.ROTAS[caminho].acesso, "dado", caminho)

    def test_a_capa_e_a_entrada_sao_abertas(self):
        """Se a capa exigisse sessao, ninguem conseguiria nem tentar entrar."""
        for caminho in ("/", "/entrada"):
            self.assertEqual(servir.ROTAS[caminho].acesso, "aberta", caminho)

    # ---------------------------------------------------------- os estaticos
    #
    # `index.html` NAO e servido sem sessao — `_pagina` devolve a capa nesses
    # casos. Mas os dois arquivos que ele carrega eram servidos a qualquer um,
    # e juntos eles sao a tela inteira: o desenho, os nomes dos campos e a
    # lista de rotas da API que o painel chama. Custo aceito em 496f710 e
    # fechado aqui.

    SO_COM_SESSAO = ("/assets/painel.js", "/assets/painel.css")

    def test_os_arquivos_do_painel_exigem_sessao(self):
        for caminho in self.SO_COM_SESSAO:
            with self.subTest(arquivo=caminho):
                self.assertIn(caminho, servir.ROTAS,
                              "arquivo renomeado? a protecao casa por caminho "
                              "exato, entao um rename reabre o arquivo em "
                              "silencio: %s" % caminho)
                self.assertEqual(servir.ROTAS[caminho].acesso, "dado", caminho)

    def test_o_que_a_capa_carrega_continua_aberto(self):
        """A trava acima nao pode subir alto demais. Quem ainda nao digitou a
        combinacao precisa da folha de estilo e do teclado da cortina — sem
        eles a capa chega sem desenho e sem botao."""
        for caminho in ("/assets/cortina.css", "/assets/cortina.js"):
            with self.subTest(arquivo=caminho):
                self.assertEqual(servir.ROTAS[caminho].acesso, "aberta",
                                 caminho)

    def test_entrar_exige_a_cortina(self):
        for caminho in servir.ROTAS:
            if caminho.startswith("/entrar/"):
                self.assertEqual(servir.ROTAS[caminho].acesso, "cortina", caminho)

    def test_o_que_o_agente_manda_exige_token_de_maquina(self):
        """A ingestao NAO pode ser "aberta". Ela escreve no banco do dono."""
        self.assertEqual(servir.ROTAS["/agente/relatorio"].acesso, "maquina")

    def test_a_classe_maquina_e_conferida_no_despacho(self):
        """Rotulo que ninguem le e pior que rotulo nenhum: da a impressao de
        haver guarda. O despacho tem de citar a classe e o token."""
        import inspect
        fonte = inspect.getsource(servir.Hub._despachar)
        self.assertIn('rota.acesso == "maquina"', fonte)
        self.assertIn("maquina_por_token", fonte)

    def test_nenhuma_rota_de_dono_aceita_token_de_maquina(self):
        """O token do agente vale para reportar, e para mais nada. Se ele
        abrisse `/api/dados`, um relatorio roubado viraria o painel inteiro."""
        for caminho, rota in servir.ROTAS.items():
            if caminho.startswith("/api/") and caminho != "/api/maquinas":
                self.assertNotEqual(rota.acesso, "maquina", caminho)

    def test_nao_existe_rota_de_registro(self):
        """Cadastro fechado. Conta so nasce por `autenticacao.convidar`, que e
        comando de quem tem acesso a maquina."""
        for proibida in ("/api/registro", "/registro", "/cadastro",
                         "/api/usuarios"):
            self.assertNotIn(proibida, servir.ROTAS)

    def test_a_porta_local_nao_existe_fora_do_ambiente_local(self):
        """A defesa nao e um `if` dentro da rota: e a rota NAO ESTAR NA TABELA.

        O primeiro desenho prometia "duas travas independentes" dentro da funcao,
        e a revisao mostrou que a segunda nunca disparava — `_despachar` ja tinha
        barrado o Host. Rota ausente da tabela e verificavel aqui, em memoria,
        sem subir servidor nenhum.
        """
        import os
        e_local = (os.environ.get("DERVS_AMBIENTE") or "").lower() == "local"
        self.assertEqual("/entrar/local" in servir.ROTAS, e_local,
                         "a porta local so pode existir no ambiente local")

    def test_o_token_global_nao_voltou(self):
        """`servir.TOKEN` era um valor so para o servidor inteiro. Com
        multiusuario ele seria a chave de todo mundo: o anti-CSRF passou a ser
        derivado da sessao de quem pede."""
        self.assertFalse(hasattr(servir, "TOKEN"))


if __name__ == "__main__":
    unittest.main(verbosity=0)
