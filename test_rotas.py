# -*- coding: utf-8 -*-
"""O vigia da superfície do servidor.

Este arquivo existe para responder, sozinho e para sempre, a uma pergunta:
**este servidor consegue rodar um comando na máquina de quem o hospeda?**

Até a etapa 7 do DERVS a resposta era sim, e nem dava para vê-la: o despacho
era uma cadeia de `if self.path…` espalhada por dois métodos, e a rota que
disparava uma sessão do Claude estava no meio dela.

DUAS DECISÕES DE PROJETO, e as duas são o ponto do teste:

1. **Ele lê `servir.ROTAS` em memória, não o texto do arquivo.** Um grep por
   `"/api/acao"` não veria `"/api/" + nome` — e uma rota montada por
   concatenação executa exatamente igual a uma escrita à mão. Importar o módulo
   e iterar a estrutura de verdade é a única leitura que não mente.

2. **Ele reprova se `ROTAS` não existir.** Sem isso, o jeito mais fácil de
   "consertar" este teste seria apagar a tabela e voltar para a cadeia de `if`,
   que é justamente o estado que ele foi escrito para impedir.

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


if __name__ == "__main__":
    unittest.main(verbosity=0)
