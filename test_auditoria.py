# -*- coding: utf-8 -*-
"""Testes de `auditoria.py` — a fundacao da Auditoria Profunda (Etapa 1).

Cobre os DEZ acoplamentos por nome que a spec cria (secao "Os acoplamentos
por nome") e as respectivas sabotagens obrigatorias do plano
(`docs/superpowers/plans/dervs-auditoria-profunda.md`, Etapa 1):

  1a. a linha nao entra no id
  1b. o id nao depende da ordem em que os achados chegam
  1c. um achado invalido invalida a corrida INTEIRA (nunca lista parcial)
  1d. POR TAMANHO: 61 achados, so o ultimo invalido, recusa tudo
  1e. `..` no caminho e recusado
  1f. as cinco categorias sao a MESMA lista (esquema, CATEGORIAS, REGRAS)
  1g. nenhuma regra tem dois-pontos dentro do nome
  1h. o JSON do esquema serializado nao contem os seis metacaracteres do CMD
  1i. `tarefas.so_dado is execucao.so_dado` (identidade, nao igualdade)
  1j. `teto_da_auditoria` nunca ultrapassa o que sobra do dia

    python test_auditoria.py
"""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

import auditoria
import tarefas

AQUI = Path(__file__).resolve().parent


def achado_valido(**kw) -> dict:
    """Um achado minimo e valido. Os testes trocam so o que interessa a eles."""
    base = {
        "arquivo": "banco.py",
        "linha": 10,
        "categoria": "seguranca",
        "gravidade": "alta",
        "frase": "A função de login falha aberta quando o token está vazio.",
        "o_que_fazer": "Recusar o pedido quando o token vier vazio, em vez de deixar passar.",
    }
    base.update(kw)
    return base


class Impressao(unittest.TestCase):
    """O id estavel — o coracao da entrega (contradicao resolvida nº 4)."""

    def test_e_deterministica(self):
        a = auditoria.impressao("banco.py", "seguranca", "Um problema real")
        b = auditoria.impressao("banco.py", "seguranca", "Um problema real")
        self.assertEqual(a, b)
        self.assertEqual(len(a), 12)
        int(a, 16)  # so hexadigitos

    def test_normalizacao_ignora_maiusculas_espacos_e_pontuacao_final(self):
        a = auditoria.impressao("x.py", "bug", "Erro Simples.")
        b = auditoria.impressao("x.py", "bug", "  erro   simples  ")
        self.assertEqual(a, b)

    def test_arquivo_ou_categoria_diferentes_dao_ids_diferentes(self):
        base = auditoria.impressao("a.py", "bug", "mesmo texto aqui")
        outro_arquivo = auditoria.impressao("b.py", "bug", "mesmo texto aqui")
        outra_categoria = auditoria.impressao("a.py", "doc", "mesmo texto aqui")
        self.assertNotEqual(base, outro_arquivo)
        self.assertNotEqual(base, outra_categoria)

    def test_1a_a_linha_nao_entra_no_id(self):
        """Sabotagem 1a: incluir `linha` no calculo de `impressao` faz duas
        auditorias com a linha deslocada darem ids DIFERENTES — este caso
        tem de reprovar nessa hora."""
        a = achado_valido(linha=10)
        b = achado_valido(linha=9999)
        ida = auditoria.id_do_achado("auditoria_seguranca", "dervs", a)
        idb = auditoria.id_do_achado("auditoria_seguranca", "dervs", b)
        self.assertEqual(ida, idb)


class IdDoAchado(unittest.TestCase):

    def test_formato_regra_dois_pontos_projeto_dois_pontos_impressao(self):
        achado = achado_valido()
        id_ = auditoria.id_do_achado("auditoria_seguranca", "dervs", achado)
        partes = id_.split(":")
        self.assertEqual(len(partes), 3, "o id tem de ter exatamente 3 partes")
        self.assertEqual(partes[0], "auditoria_seguranca")
        self.assertEqual(partes[1], "dervs")
        self.assertEqual(len(partes[2]), 12)

    def test_1b_ordem_embaralhada_da_os_mesmos_ids(self):
        """Sabotagem 1b: se o calculo do id dependesse da posicao do achado
        na lista, embaralhar a ordem mudaria os ids. Aqui o id vem so dos
        campos do achado, nunca de onde ele estava na lista."""
        a1 = achado_valido(arquivo="a.py", frase="Primeiro achado de teste por aqui.")
        a2 = achado_valido(arquivo="b.py", frase="Segundo achado de teste por aqui.")

        bruto1 = json.dumps({"achados": [a1, a2]})
        bruto2 = json.dumps({"achados": [a2, a1]})
        achados1, motivo1 = auditoria.validar(bruto1)
        achados2, motivo2 = auditoria.validar(bruto2)
        self.assertEqual(motivo1, "")
        self.assertEqual(motivo2, "")

        ids1 = sorted(auditoria.id_do_achado("auditoria_seguranca", "dervs", a)
                     for a in achados1)
        ids2 = sorted(auditoria.id_do_achado("auditoria_seguranca", "dervs", a)
                     for a in achados2)
        self.assertEqual(ids1, ids2)

    def test_1g_regra_com_dois_pontos_e_incompativel_com_o_formato(self):
        """Sabotagem 1g: renomear `auditoria_seguranca` para
        `auditoria:seguranca` faz o id ter 4 partes ao dividir por ":" — quem
        le e `execucao.py:1058`, `pendencia_id.split(":")[0]`. Nenhuma regra
        de `auditoria.REGRAS` pode conter dois-pontos."""
        for regra in auditoria.REGRAS.values():
            self.assertNotIn(":", regra)
        self.assertNotIn(":", auditoria.REGRA_DE_VENCIMENTO)


class Caminho(unittest.TestCase):

    def test_caminho_relativo_normal_e_aceito(self):
        self.assertTrue(auditoria.caminho_aceitavel("banco.py"))
        self.assertTrue(auditoria.caminho_aceitavel("assets/painel.js"))

    def test_1e_caminho_com_ponto_ponto_e_recusado(self):
        self.assertFalse(auditoria.caminho_aceitavel("../../.ssh/config"))
        self.assertFalse(auditoria.caminho_aceitavel("a/../../b.py"))

    def test_caminho_absoluto_unix_e_recusado(self):
        self.assertFalse(auditoria.caminho_aceitavel("/etc/passwd"))

    def test_caminho_absoluto_windows_e_recusado(self):
        self.assertFalse(auditoria.caminho_aceitavel(r"C:\Windows\system32"))

    def test_caminho_comecando_com_barra_invertida_e_recusado(self):
        self.assertFalse(auditoria.caminho_aceitavel(r"\segredo\arquivo.txt"))

    def test_caminho_vazio_e_recusado(self):
        self.assertFalse(auditoria.caminho_aceitavel(""))
        self.assertFalse(auditoria.caminho_aceitavel(None))


class Validar(unittest.TestCase):

    def test_json_valido_com_um_achado(self):
        bruto = json.dumps({"achados": [achado_valido()]})
        achados, motivo = auditoria.validar(bruto)
        self.assertEqual(motivo, "")
        self.assertEqual(len(achados), 1)

    def test_lista_vazia_e_sucesso_com_zero_achados(self):
        """Zero achados so existe quando a corrida terminou ok com lista
        vazia — a lei 2 escrita como teste."""
        bruto = json.dumps({"achados": []})
        achados, motivo = auditoria.validar(bruto)
        self.assertEqual(motivo, "")
        self.assertEqual(achados, [])

    def test_saida_vazia_e_sem_dados_nunca_lista_vazia(self):
        achados, motivo = auditoria.validar("")
        self.assertIsNone(achados)
        self.assertTrue(motivo)

    def test_saida_none_e_sem_dados(self):
        achados, motivo = auditoria.validar(None)
        self.assertIsNone(achados)
        self.assertTrue(motivo)

    def test_json_quebrado_e_sem_dados(self):
        achados, motivo = auditoria.validar('{"achados": [truncado')
        self.assertIsNone(achados)
        self.assertTrue(motivo)

    def test_nao_e_um_objeto_json_e_sem_dados(self):
        achados, motivo = auditoria.validar("[1, 2, 3]")
        self.assertIsNone(achados)
        self.assertTrue(motivo)

    def test_falta_a_chave_achados_e_sem_dados(self):
        achados, motivo = auditoria.validar(json.dumps({"outra_coisa": []}))
        self.assertIsNone(achados)
        self.assertTrue(motivo)

    def test_campo_obrigatorio_faltando_reprova(self):
        item = achado_valido()
        del item["frase"]
        achados, motivo = auditoria.validar(json.dumps({"achados": [item]}))
        self.assertIsNone(achados)
        self.assertTrue(motivo)

    def test_campo_extra_nao_previsto_reprova(self):
        item = achado_valido(inventado="qualquer coisa")
        achados, motivo = auditoria.validar(json.dumps({"achados": [item]}))
        self.assertIsNone(achados)
        self.assertTrue(motivo)

    def test_categoria_fora_do_enum_reprova(self):
        item = achado_valido(categoria="perf")
        achados, motivo = auditoria.validar(json.dumps({"achados": [item]}))
        self.assertIsNone(achados)

    def test_gravidade_fora_do_enum_reprova(self):
        item = achado_valido(gravidade="urgente")
        achados, motivo = auditoria.validar(json.dumps({"achados": [item]}))
        self.assertIsNone(achados)

    def test_linha_fora_da_faixa_reprova(self):
        for linha in (0, -1, 2000001, "10", True):
            item = achado_valido(linha=linha)
            achados, motivo = auditoria.validar(json.dumps({"achados": [item]}))
            self.assertIsNone(achados, "linha=%r deveria reprovar" % (linha,))

    def test_frase_curta_demais_reprova(self):
        item = achado_valido(frase="curta")
        achados, motivo = auditoria.validar(json.dumps({"achados": [item]}))
        self.assertIsNone(achados)

    def test_o_que_fazer_curto_demais_reprova(self):
        item = achado_valido(o_que_fazer="curta")
        achados, motivo = auditoria.validar(json.dumps({"achados": [item]}))
        self.assertIsNone(achados)

    def test_1h_achado_com_caminho_recusado_reprova_a_corrida(self):
        item = achado_valido(arquivo="../../.ssh/config")
        achados, motivo = auditoria.validar(json.dumps({"achados": [item]}))
        self.assertIsNone(achados)
        self.assertTrue(motivo)

    def test_1c_um_achado_invalido_invalida_a_corrida_inteira(self):
        """Sabotagem 1c: se `validar` descartasse o item invalido e devolvesse
        o resto, este caso continuaria vendo achados != None. A validacao e
        tudo-ou-nada: um item ruim reprova a lista inteira, nunca so ele."""
        bom = achado_valido(arquivo="a.py")
        ruim = achado_valido(arquivo="b.py", categoria="perf")
        achados, motivo = auditoria.validar(json.dumps({"achados": [bom, ruim]}))
        self.assertIsNone(achados, "um achado invalido nao pode deixar o resto passar")
        self.assertTrue(motivo)

    def test_1d_por_tamanho_61_achados_so_o_ultimo_invalido_recusa_tudo(self):
        """Sabotagem 1d, POR TAMANHO: com apenas 1 ou 2 achados um laco que
        parasse cedo ainda tem chance de nunca alcancar o item ruim por
        coincidencia de posicao baixa. Aqui sao 61 achados, e SO o ultimo
        (indice 60) e invalido — o guarda tem de examinar a lista inteira."""
        lista = [achado_valido(arquivo="arquivo_%03d.py" % i,
                              frase="Achado numero %d de sessenta e um." % i)
                for i in range(60)]
        lista.append(achado_valido(categoria="categoria-que-nao-existe"))
        self.assertEqual(len(lista), 61)
        achados, motivo = auditoria.validar(json.dumps({"achados": lista}))
        self.assertIsNone(achados, "os 61 achados tem de ser recusados inteiros")
        self.assertTrue(motivo)

    def test_validar_aplica_limpar_e_so_dado_no_resultado(self):
        item = achado_valido(
            frase="A frase traz a etiqueta " + tarefas.FIM_DO_BLOCO + " no meio dela.")
        achados, motivo = auditoria.validar(json.dumps({"achados": [item]}))
        self.assertEqual(motivo, "")
        self.assertNotIn(tarefas.FIM_DO_BLOCO, achados[0]["frase"])


class Limpar(unittest.TestCase):

    def test_corta_no_tamanho_do_esquema(self):
        item = achado_valido(frase="x" * 20 + " " + "y" * 400)
        limpo = auditoria.limpar(item)
        self.assertLessEqual(len(limpo["frase"]), 300)

    def test_remove_caracter_de_controle(self):
        item = achado_valido(frase="Uma frase com \x00 controle no meio dela.")
        limpo = auditoria.limpar(item)
        self.assertNotIn("\x00", limpo["frase"])

    def test_neutraliza_a_etiqueta_de_fechamento(self):
        item = achado_valido(
            o_que_fazer="Feche assim: " + tarefas.FIM_DO_BLOCO + " e mais texto.")
        limpo = auditoria.limpar(item)
        self.assertNotIn(tarefas.FIM_DO_BLOCO, limpo["o_que_fazer"])


class CategoriasSaoUmaListaSo(unittest.TestCase):
    """Sabotagem 1f: acrescentar "perf" ao enum do ESQUEMA sem por em
    CATEGORIAS quebra a igualdade abaixo — as tres copias tem de ser a mesma
    lista, derivada de `auditoria.CATEGORIAS`."""

    def test_enum_do_esquema_e_categorias_sao_a_mesma_lista(self):
        item = auditoria.ESQUEMA["properties"]["achados"]["items"]
        enum_categoria = item["properties"]["categoria"]["enum"]
        self.assertEqual(list(enum_categoria), list(auditoria.CATEGORIAS))

    def test_regras_tem_exatamente_as_cinco_categorias_como_chave(self):
        self.assertEqual(set(auditoria.REGRAS.keys()), set(auditoria.CATEGORIAS))

    def test_regras_e_o_prefixo_auditoria_mais_a_categoria(self):
        for categoria in auditoria.CATEGORIAS:
            self.assertEqual(auditoria.REGRAS[categoria],
                             "auditoria_" + categoria)


class EsquemaSemMetacaracteres(unittest.TestCase):
    """Sabotagem 1h: um `"pattern": "^[^<>]+$"` no esquema introduz `<`, `>`
    e `^` no JSON serializado, e a linha de comando do .CMD rouba os seis."""

    def test_json_serializado_nao_contem_metacaracteres_do_cmd(self):
        bruto = json.dumps(auditoria.ESQUEMA, ensure_ascii=True)
        for marca in ("|", "&", "<", ">", "^", "%"):
            self.assertNotIn(marca, bruto,
                             "o esquema serializado contem '%s'" % marca)

    def test_esquema_valida_como_json(self):
        bruto = json.dumps(auditoria.ESQUEMA, ensure_ascii=True)
        de_volta = json.loads(bruto)
        self.assertEqual(de_volta, auditoria.ESQUEMA)


class Identidade(unittest.TestCase):
    """Sabotagem 1i: redefinir `so_dado` DENTRO de `execucao.py` cria uma
    segunda copia da peneira. `assertIs`, nao `assertEqual` — duas funcoes
    IGUAIS ainda seriam objetos DIFERENTES, e e isso que o `is` pega."""

    def test_tarefas_so_dado_e_execucao_so_dado_sao_o_mesmo_objeto(self):
        import execucao
        self.assertIs(tarefas.so_dado, execucao.so_dado)

    def test_fim_do_bloco_e_o_mesmo_objeto(self):
        import execucao
        self.assertIs(tarefas.FIM_DO_BLOCO, execucao.FIM_DO_BLOCO)

    def test_o_fonte_de_execucao_nao_tem_um_segundo_valor(self):
        """Nao basta o objeto ser o mesmo agora — o FONTE nao pode voltar a
        ter uma string literal propria amanha."""
        fonte = (AQUI / "execucao.py").read_text(encoding="utf-8")
        self.assertNotIn(
            'FIM_DO_BLOCO = "</dados-coletados-nao-confiaveis>"', fonte,
            "execucao.py voltou a ter uma copia propria de FIM_DO_BLOCO")


class TetoDaAuditoria(unittest.TestCase):
    """Sabotagem 1j: trocar `max(0.0, ...)` por `min(...)` faz um gasto acima
    do teto do dia devolver um numero NEGATIVO em vez de 0.0."""

    def test_sem_gasto_o_teto_e_o_cheio(self):
        self.assertEqual(tarefas.teto_da_auditoria(0.0),
                         tarefas.TETO_AUDITORIA_USD)

    def test_1j_gasto_acima_do_teto_do_dia_da_teto_zero(self):
        estourado = 100.0 / tarefas.USD_BRL
        self.assertEqual(tarefas.teto_da_auditoria(estourado), 0.0)

    def test_nunca_ultrapassa_o_que_sobra_do_dia(self):
        quase_tudo = (tarefas.TETO_DIARIO_BRL - 1.0) / tarefas.USD_BRL
        teto = tarefas.teto_da_auditoria(quase_tudo)
        self.assertLessEqual(teto, 1.0 / tarefas.USD_BRL + 1e-9)

    def test_nunca_ultrapassa_o_teto_da_auditoria(self):
        self.assertLessEqual(tarefas.teto_da_auditoria(0.0),
                             tarefas.TETO_AUDITORIA_USD)


class ConstantesDeAcoplamento(unittest.TestCase):

    def test_executor_e_a_string_auditor(self):
        self.assertEqual(auditoria.EXECUTOR, "auditor")

    def test_executor_da_regra_mapeia_a_regra_de_vencimento_para_o_auditor(self):
        self.assertEqual(auditoria.EXECUTOR_DA_REGRA[auditoria.REGRA_DE_VENCIMENTO],
                         auditoria.EXECUTOR)

    def test_regra_de_vencimento_nao_e_igual_a_regra_ja_existente(self):
        """`regras.py` ja tem `auditoria_nao_rodou` (dependencias). Nao e a
        mesma coisa e nao pode ser confundida por prefixo."""
        self.assertNotEqual(auditoria.REGRA_DE_VENCIMENTO, "auditoria_nao_rodou")
        self.assertFalse("auditoria_nao_rodou".startswith(auditoria.REGRA_DE_VENCIMENTO))


class PurezaEIsolamento(unittest.TestCase):
    """`auditoria.py` nao pode importar `execucao`, `fila`, `banco` nem
    `servir` — o mesmo teste de isolamento que `tarefas.py` ja tem."""

    def test_o_fonte_nao_importa_execucao_fila_banco_ou_servir(self):
        fonte = (AQUI / "auditoria.py").read_text(encoding="utf-8")
        for linha in fonte.splitlines():
            nu = linha.strip()
            if nu.startswith("import ") or nu.startswith("from "):
                for proibido in ("execucao", "fila", "banco", "servir"):
                    self.assertNotIn(proibido, nu)


if __name__ == "__main__":
    unittest.main(verbosity=2)
