# -*- coding: utf-8 -*-
"""Testes das tabelas que tiram o HUB de uma maquina so (etapa 8).

Seis tabelas novas — usuario, sessao, maquina, pareamento, projeto_conectado e
pendencia_arquivada — mais a migracao que da dono a `pendencia_estado`.

O que este arquivo cobra, alem de "a tabela existe":

  1. NADA DE SEGREDO EM CLARO. Senha, token do agente, codigo de pareamento e
     segredo do segundo fator entram na tabela ja irreversiveis ou cifrados.
     Retroencaixar isso na etapa 9 exigiria migrar dado e rotacionar segredo.
  2. ARQUIVAR DEIXA RASTRO. Motivo e data sao obrigatorios. Arquivamento
     permanente sem rastro e pior que o silencio de 24 h que ele substitui.
  3. O DONO DA LINHA. `pendencia_estado` nao tinha coluna de dono: com dois
     usuarios, o "x" de um escondia o alerta do outro. Isso e IDOR por desenho
     de esquema, e o conserto e aqui, na migracao — nao na rota.
  4. O BANCO VELHO SOBE. Um hub.db do dia 26/08 abre no esquema novo sem
     perder linha, e o que estava la vira do dono local.

    python test_banco.py
"""
from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Chave fixa do cofre: o teste nao pode depender de arquivo no disco do dono
# nem gravar um. Tem de ser definida ANTES de importar banco.
# Precisa de 32 caracteres ou mais: o banco recusa chave curta, porque frase
# curta se quebra offline a partir de uma copia do hub.db.
os.environ.setdefault("DERVS_COFRE",
                      "chave-de-teste-que-nao-e-segredo-nenhum-0123456789")

import banco  # noqa: E402


def iso(dt) -> str:
    return dt.isoformat(timespec="seconds")


AGORA = datetime(2026, 8, 26, 14, 0, 0, tzinfo=timezone.utc)


def daqui(**kw) -> str:
    return iso(AGORA + timedelta(**kw))


# O esquema como ele era ANTES desta etapa, reduzido ao que a migracao toca.
# Existe para provar que um hub.db real do dia 26/08 sobe sem perder nada.
ESQUEMA_VELHO = """
CREATE TABLE medida (
    projeto TEXT NOT NULL, camada TEXT NOT NULL,
    medido_em TEXT NOT NULL, dados TEXT NOT NULL,
    PRIMARY KEY (projeto, camada));
CREATE TABLE pendencia_estado (
    id TEXT PRIMARY KEY, silenciada_ate TEXT, anotado_em TEXT NOT NULL);
"""


class Cofre(unittest.TestCase):
    """Cifrar e conferir — a parte que nao pode nascer para depois."""

    def test_o_hash_da_senha_nao_contem_a_senha(self):
        guardado = banco.hash_senha("teste1234")
        self.assertNotIn("teste1234", guardado)
        self.assertTrue(guardado.startswith("scrypt$"))

    def test_a_senha_certa_confere_e_a_errada_nao(self):
        guardado = banco.hash_senha("teste1234")
        self.assertTrue(banco.conferir_senha("teste1234", guardado))
        self.assertFalse(banco.conferir_senha("teste1235", guardado))

    def test_a_mesma_senha_gera_hashes_diferentes(self):
        """Sem sal, duas contas com a mesma senha ficam visiveis uma para a outra."""
        self.assertNotEqual(banco.hash_senha("teste1234"), banco.hash_senha("teste1234"))

    def test_hash_de_guardado_torto_nao_explode_devolve_falso(self):
        for lixo in ("", "scrypt$", "scrypt$a$b$c$d$e", "outra-coisa"):
            self.assertFalse(banco.conferir_senha("teste1234", lixo))

    def test_o_texto_cifrado_nao_contem_o_texto_claro(self):
        blob = banco.cifrar("JBSWY3DPEHPK3PXP")
        self.assertNotIn("JBSWY3DPEHPK3PXP", blob)
        self.assertEqual(banco.decifrar(blob), "JBSWY3DPEHPK3PXP")

    def test_cifrar_duas_vezes_da_blobs_diferentes(self):
        self.assertNotEqual(banco.cifrar("igual"), banco.cifrar("igual"))

    def test_blob_adulterado_e_recusado_nao_devolve_lixo(self):
        blob = banco.cifrar("JBSWY3DPEHPK3PXP")
        partes = blob.split("$")
        partes[2] = "AAAA" + partes[2][4:]
        with self.assertRaises(ValueError):
            banco.decifrar("$".join(partes))

    def test_texto_longo_e_acentuado_volta_igual(self):
        """A cifra e por blocos: o teste tem de passar do primeiro bloco."""
        claro = "pendencia com acento: coracao, informacao " * 20
        self.assertEqual(banco.decifrar(banco.cifrar(claro)), claro)

    def test_hash_de_token_e_estavel_e_nao_e_o_token(self):
        t = banco.novo_token()
        self.assertEqual(banco.hash_token(t), banco.hash_token(t))
        self.assertNotEqual(banco.hash_token(t), t)
        self.assertNotEqual(banco.novo_token(), banco.novo_token())


class Esquema(unittest.TestCase):

    def setUp(self):
        self.con = banco.conectar(":memory:")

    def tearDown(self):
        self.con.close()

    def tabelas(self):
        return sorted(l[0] for l in self.con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%'"))

    def test_as_dezesseis_tabelas_existem(self):
        """A lista e escrita a mao de proposito: tabela nova reprova a suite.

        Nao e cerimonia. Uma tabela que aparece sem ninguem notar e uma tabela
        sem teste, sem migracao pensada e — se guardar dado de pessoa — sem
        decisao sobre o que acontece quando a conta e apagada.
        """
        self.assertEqual(self.tabelas(), [
            "chave_de_acesso", "codigo_recuperacao", "credencial", "fila",
            "gasto", "historico", "instalacao", "maquina", "medida",
            "pareamento", "pendencia_arquivada", "pendencia_estado",
            "pendencia_vida", "projeto_conectado", "sessao", "usuario"])

    def test_as_seis_tabelas_antigas_nao_perderam_coluna(self):
        """A etapa 8 acrescenta. So `pendencia_estado` muda, e so ganhando dono."""
        esperado = {
            "medida": {"projeto", "camada", "medido_em", "dados"},
            "historico": {"medido_em", "chave", "valor"},
            "pendencia_vida": {"id", "regra", "projeto", "gravidade",
                               "visto_em", "ultimo_em", "fechada_em"},
            "gasto": {"id", "quando", "origem", "custo_usd"},
        }
        for tabela, colunas in esperado.items():
            tem = {l[1] for l in self.con.execute("PRAGMA table_info(%s)" % tabela)}
            self.assertTrue(colunas <= tem, "%s perdeu coluna: %s" % (tabela, colunas - tem))

    def test_a_chave_estrangeira_esta_ligada(self):
        """Sem isto, `ON DELETE CASCADE` e so comentario bonito no esquema."""
        self.assertEqual(self.con.execute("PRAGMA foreign_keys").fetchone()[0], 1)


class Usuario(unittest.TestCase):

    def setUp(self):
        self.con = banco.conectar(":memory:")
        self.uid = banco.criar_usuario("dono@teste.local", "teste1234",
                                       nome="Dono", con=self.con)

    def tearDown(self):
        self.con.close()

    def test_a_senha_nao_aparece_em_lugar_nenhum_da_linha(self):
        linha = self.con.execute("SELECT * FROM usuario WHERE id=?", (self.uid,)).fetchone()
        self.assertNotIn("teste1234", " ".join(str(v) for v in tuple(linha)))

    def test_o_email_e_guardado_em_minuscula_e_sem_espaco(self):
        outro = banco.criar_usuario("  MAIUSCULA@Teste.Local ", "teste1234", con=self.con)
        u = banco.usuario_por_email("maiuscula@teste.local", con=self.con)
        self.assertEqual(u["id"], outro)

    def test_o_mesmo_email_duas_vezes_e_recusado(self):
        with self.assertRaises(sqlite3.IntegrityError):
            banco.criar_usuario("DONO@teste.local", "outra", con=self.con)

    def test_usuario_recem_criado_esta_sem_segundo_fator(self):
        """A etapa 9 nega toda rota de dado a quem esta assim. Comeca assim.

        Desde que o segredo saiu da `usuario`, "sem segundo fator" e a AUSENCIA
        de uma credencial de TOTP — a negativa continua sendo o padrao, agora
        por nao existir linha nenhuma em vez de por uma coluna em NULL.
        """
        self.assertEqual(
            self.con.execute("SELECT COUNT(*) FROM credencial"
                             " WHERE usuario_id=? AND tipo='totp'",
                             (self.uid,)).fetchone()[0], 0)

    def test_o_segredo_do_segundo_fator_nao_fica_em_claro_na_tabela(self):
        banco.guardar_totp(self.uid, "JBSWY3DPEHPK3PXP", con=self.con)
        cru = self.con.execute("SELECT segredo_hash FROM credencial"
                               " WHERE usuario_id=? AND tipo='totp'",
                               (self.uid,)).fetchone()[0]
        self.assertNotIn("JBSWY3DPEHPK3PXP", cru)
        self.assertEqual(banco.ler_totp(self.uid, con=self.con), "JBSWY3DPEHPK3PXP")

    def test_confirmar_o_segundo_fator_carimba_a_data(self):
        banco.guardar_totp(self.uid, "JBSWY3DPEHPK3PXP", con=self.con)
        self.assertIsNone(self.con.execute(
            "SELECT usado_em FROM credencial WHERE usuario_id=? AND tipo='totp'",
            (self.uid,)).fetchone()[0], "guardar nao pode equivaler a conferir")
        banco.confirmar_totp(self.uid, con=self.con)
        self.assertIsNotNone(self.con.execute(
            "SELECT usado_em FROM credencial WHERE usuario_id=? AND tipo='totp'",
            (self.uid,)).fetchone()[0])

    def test_usuario_que_nao_existe_devolve_nada_e_nao_explode(self):
        self.assertIsNone(banco.usuario_por_email("ninguem@teste.local", con=self.con))
        self.assertIsNone(banco.ler_totp(9999, con=self.con))


class Sessao(unittest.TestCase):

    def setUp(self):
        self.con = banco.conectar(":memory:")
        self.uid = banco.criar_usuario("dono@teste.local", "teste1234", con=self.con)
        self.cookie = banco.novo_token()
        banco.abrir_sessao(self.uid, self.cookie, expira_em=daqui(hours=8), con=self.con)

    def tearDown(self):
        self.con.close()

    def test_o_cookie_nao_e_guardado_em_claro(self):
        """Vazar o banco nao pode ser o mesmo que vazar as sessoes vivas."""
        guardados = [l[0] for l in self.con.execute("SELECT id FROM sessao")]
        self.assertNotIn(self.cookie, guardados)

    def test_a_sessao_vale_e_sabe_de_quem_e(self):
        s = banco.sessao_valida(self.cookie, agora_iso=iso(AGORA), con=self.con)
        self.assertIsNotNone(s)
        self.assertEqual(s["usuario_id"], self.uid)

    def test_a_sessao_nasce_sem_segundo_fator_conferido(self):
        s = banco.sessao_valida(self.cookie, agora_iso=iso(AGORA), con=self.con)
        self.assertIsNone(s["segundo_fator_em"])
        banco.confirmar_segundo_fator(self.cookie, con=self.con)
        s = banco.sessao_valida(self.cookie, agora_iso=iso(AGORA), con=self.con)
        self.assertIsNotNone(s["segundo_fator_em"])

    def test_sessao_vencida_nao_vale_mais(self):
        s = banco.sessao_valida(self.cookie, agora_iso=daqui(hours=9), con=self.con)
        self.assertIsNone(s)

    def test_sessao_encerrada_nao_vale_mais(self):
        banco.encerrar_sessao(self.cookie, con=self.con)
        self.assertIsNone(banco.sessao_valida(self.cookie, agora_iso=iso(AGORA),
                                              con=self.con))

    def test_cookie_desconhecido_nao_vale(self):
        self.assertIsNone(banco.sessao_valida(banco.novo_token(),
                                              agora_iso=iso(AGORA), con=self.con))

    def test_apagar_o_usuario_leva_as_sessoes_dele(self):
        self.con.execute("DELETE FROM usuario WHERE id=?", (self.uid,))
        self.con.commit()
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM sessao").fetchone()[0], 0)


class Pareamento(unittest.TestCase):
    """O codigo de seis digitos que casa uma maquina com uma conta (etapa 11)."""

    def setUp(self):
        self.con = banco.conectar(":memory:")
        self.uid = banco.criar_usuario("dono@teste.local", "teste1234", con=self.con)
        self.codigo = "123456"
        banco.abrir_pareamento(self.uid, self.codigo, expira_em=daqui(minutes=10),
                               con=self.con)

    def tearDown(self):
        self.con.close()

    def test_o_codigo_nao_fica_em_claro(self):
        guardados = [l[0] for l in self.con.execute("SELECT codigo_hash FROM pareamento")]
        self.assertNotIn(self.codigo, guardados)

    def test_o_codigo_certo_pareia_e_devolve_um_token_de_maquina(self):
        token = banco.usar_pareamento(self.codigo, "notebook do dono",
                                      agora_iso=iso(AGORA), con=self.con)
        self.assertTrue(token)
        m = banco.maquina_por_token(token, con=self.con)
        self.assertEqual(m["usuario_id"], self.uid)
        self.assertEqual(m["nome"], "notebook do dono")

    def test_o_token_da_maquina_nao_fica_em_claro(self):
        token = banco.usar_pareamento(self.codigo, "n", agora_iso=iso(AGORA), con=self.con)
        guardados = [l[0] for l in self.con.execute("SELECT token_hash FROM maquina")]
        self.assertNotIn(token, guardados)

    def test_o_mesmo_codigo_nao_pareia_duas_vezes(self):
        banco.usar_pareamento(self.codigo, "um", agora_iso=iso(AGORA), con=self.con)
        self.assertIsNone(banco.usar_pareamento(self.codigo, "dois",
                                                agora_iso=iso(AGORA), con=self.con))

    def test_codigo_vencido_nao_pareia(self):
        self.assertIsNone(banco.usar_pareamento(self.codigo, "x",
                                                agora_iso=daqui(minutes=11), con=self.con))

    def test_chute_errado_nao_mata_o_pareamento_de_ninguem(self):
        """A versao anterior contava o chute contra TODOS os pareamentos abertos.

        Cinco chutes de um estranho matavam o pareamento de todas as contas —
        negacao de servico de um usuario sobre o outro, com cinco requisicoes.
        O teto de forca bruta e por origem e mora na rota (etapa 11).
        """
        for _ in range(8):
            self.assertIsNone(banco.usar_pareamento("000000", "x",
                                                    agora_iso=iso(AGORA), con=self.con))
        self.assertTrue(banco.usar_pareamento(self.codigo, "legitimo",
                                              agora_iso=iso(AGORA), con=self.con))

    def test_codigo_repetido_e_recusado_nao_rouba_a_conta_do_outro(self):
        """Era o pior defeito do lote, e era silencioso.

        Com `INSERT OR REPLACE`, dois usuarios sorteando o mesmo codigo faziam a
        linha do primeiro sumir sem erro — e a maquina DELE nascia dentro da
        conta do segundo, com projetos e alertas junto.
        """
        outro = banco.criar_usuario("outro@teste.local", "teste1234", con=self.con)
        with self.assertRaises(sqlite3.IntegrityError):
            banco.abrir_pareamento(outro, self.codigo, expira_em=daqui(minutes=10),
                                   con=self.con)
        token = banco.usar_pareamento(self.codigo, "x", agora_iso=iso(AGORA),
                                      con=self.con)
        self.assertEqual(banco.maquina_por_token(token, con=self.con)["usuario_id"],
                         self.uid)

    def test_novo_codigo_tem_seis_digitos_e_preserva_o_zero_a_esquerda(self):
        for _ in range(50):
            c = banco.novo_codigo()
            self.assertEqual(len(c), 6)
            self.assertTrue(c.isdigit())

    def test_token_de_maquina_desconhecido_nao_abre_nada(self):
        self.assertIsNone(banco.maquina_por_token(banco.novo_token(), con=self.con))

    def test_maquina_revogada_nao_abre_mais(self):
        token = banco.usar_pareamento(self.codigo, "n", agora_iso=iso(AGORA), con=self.con)
        m = banco.maquina_por_token(token, con=self.con)
        banco.revogar_maquina(m["id"], m["usuario_id"], con=self.con)
        self.assertIsNone(banco.maquina_por_token(token, con=self.con))


class ProjetoConectado(unittest.TestCase):

    def setUp(self):
        self.con = banco.conectar(":memory:")
        uid = banco.criar_usuario("dono@teste.local", "teste1234", con=self.con)
        banco.abrir_pareamento(uid, "123456", expira_em=daqui(minutes=10), con=self.con)
        token = banco.usar_pareamento("123456", "n", agora_iso=iso(AGORA), con=self.con)
        self.maq = banco.maquina_por_token(token, con=self.con)["id"]

    def tearDown(self):
        self.con.close()

    def test_o_mesmo_projeto_visto_de_novo_nao_duplica(self):
        banco.ver_projeto(self.maq, "dervs", r"C:\repos\dervs", visto_em=iso(AGORA),
                          con=self.con)
        banco.ver_projeto(self.maq, "dervs", r"C:\repos\dervs", visto_em=daqui(hours=1),
                          con=self.con)
        linhas = banco.projetos_da_maquina(self.maq, con=self.con)
        self.assertEqual(len(linhas), 1)
        self.assertEqual(linhas[0]["visto_em"], daqui(hours=1))

    def test_projeto_arquivado_sai_da_lista_viva_mas_continua_na_tabela(self):
        banco.ver_projeto(self.maq, "sumiu", "", visto_em=iso(AGORA), con=self.con)
        banco.arquivar_projeto(self.maq, "sumiu", con=self.con)
        self.assertEqual(banco.projetos_da_maquina(self.maq, con=self.con), [])
        self.assertEqual(
            self.con.execute("SELECT COUNT(*) FROM projeto_conectado").fetchone()[0], 1)

    def test_apagar_a_maquina_leva_os_projetos_dela(self):
        banco.ver_projeto(self.maq, "dervs", "", visto_em=iso(AGORA), con=self.con)
        self.con.execute("DELETE FROM maquina WHERE id=?", (self.maq,))
        self.con.commit()
        self.assertEqual(
            self.con.execute("SELECT COUNT(*) FROM projeto_conectado").fetchone()[0], 0)


class Arquivamento(unittest.TestCase):
    """O arquivamento permanente — o irmao definitivo do 'esconder por 24 h'."""

    def setUp(self):
        self.con = banco.conectar(":memory:")
        self.a = banco.criar_usuario("a@teste.local", "teste1234", con=self.con)
        self.b = banco.criar_usuario("b@teste.local", "teste1234", con=self.con)

    def tearDown(self):
        self.con.close()

    def test_arquivar_sem_motivo_e_recusado(self):
        """Arquivamento permanente sem rastro e pior que o silencio de 24 h."""
        with self.assertRaises(ValueError):
            banco.arquivar("grafo_velho:dervs", self.a, motivo="  ", con=self.con)

    def test_arquivar_guarda_motivo_e_data(self):
        banco.arquivar("grafo_velho:dervs", self.a, motivo="nao vale o esforco",
                       con=self.con)
        linha = self.con.execute("SELECT * FROM pendencia_arquivada").fetchone()
        self.assertEqual(linha["motivo"], "nao vale o esforco")
        self.assertTrue(linha["arquivado_em"])

    def test_o_arquivo_de_um_nao_esconde_nada_do_outro(self):
        banco.arquivar("grafo_velho:dervs", self.a, motivo="x", con=self.con)
        self.assertEqual(banco.arquivadas(self.a, con=self.con), {"grafo_velho:dervs"})
        self.assertEqual(banco.arquivadas(self.b, con=self.con), set())

    def test_desarquivar_devolve_a_pendencia_e_deixa_rastro(self):
        banco.arquivar("grafo_velho:dervs", self.a, motivo="x", con=self.con)
        banco.desarquivar("grafo_velho:dervs", self.a, con=self.con)
        self.assertEqual(banco.arquivadas(self.a, con=self.con), set())
        linha = self.con.execute("SELECT * FROM pendencia_arquivada").fetchone()
        self.assertTrue(linha["desarquivado_em"])

    def test_arquivar_de_novo_atualiza_o_motivo_e_reabre_o_rastro(self):
        banco.arquivar("g:d", self.a, motivo="primeiro", con=self.con)
        banco.desarquivar("g:d", self.a, con=self.con)
        banco.arquivar("g:d", self.a, motivo="segundo", con=self.con)
        linha = self.con.execute("SELECT * FROM pendencia_arquivada").fetchone()
        self.assertEqual(linha["motivo"], "segundo")
        self.assertIsNone(linha["desarquivado_em"])
        self.assertEqual(
            self.con.execute("SELECT COUNT(*) FROM pendencia_arquivada").fetchone()[0], 1)


class SilenciarPorDono(unittest.TestCase):
    """O 'x' de 24 h deixa de ser global. Era IDOR por desenho de esquema."""

    def setUp(self):
        self.con = banco.conectar(":memory:")
        self.a = banco.criar_usuario("a@teste.local", "teste1234", con=self.con)
        self.b = banco.criar_usuario("b@teste.local", "teste1234", con=self.con)

    def tearDown(self):
        self.con.close()

    # `agora_iso` fixo nos dois testes abaixo pelo mesmo motivo do terceiro, e
    # a falta dele era uma bomba-relogio: `AGORA` e 26/08/2026, `daqui(hours=24)`
    # e 27/08, e sem `agora_iso` a comparacao era contra o relogio DE VERDADE.
    # Os dois passaram por um dia e ficaram vermelhos sozinhos em 27/08/2026,
    # sem ninguem tocar em banco.py — CI vermelha por data, que e o defeito mais
    # caro de diagnosticar porque nao aparece em nenhum diff.
    def test_o_x_de_um_usuario_nao_esconde_o_alerta_do_outro(self):
        banco.silenciar("grafo_velho:dervs", daqui(hours=24), usuario_id=self.a,
                        con=self.con)
        self.assertIn("grafo_velho:dervs",
                      banco.silenciadas(usuario_id=self.a, agora_iso=iso(AGORA),
                                        con=self.con))
        self.assertEqual(banco.silenciadas(usuario_id=self.b, agora_iso=iso(AGORA),
                                           con=self.con), {})

    def test_sem_dizer_o_dono_a_linha_e_do_dono_local(self):
        """Compatibilidade: o painel de uma maquina so continua funcionando."""
        banco.silenciar("g:d", daqui(hours=24), con=self.con)
        self.assertIn("g:d", banco.silenciadas(agora_iso=iso(AGORA), con=self.con))
        self.assertEqual(banco.silenciadas(usuario_id=self.a, agora_iso=iso(AGORA),
                                           con=self.con), {})

    def test_dois_usuarios_silenciam_a_mesma_pendencia_sem_um_apagar_o_outro(self):
        # `agora_iso` fixo de proposito: sem ele o teste depende da hora em que
        # roda, e um prazo curto vence antes de a CI chegar nesta linha.
        banco.silenciar("g:d", daqui(hours=24), usuario_id=self.a, con=self.con)
        banco.silenciar("g:d", daqui(hours=1), usuario_id=self.b, con=self.con)
        self.assertEqual(banco.silenciadas(usuario_id=self.a, agora_iso=iso(AGORA),
                                           con=self.con)["g:d"], daqui(hours=24))
        self.assertEqual(banco.silenciadas(usuario_id=self.b, agora_iso=iso(AGORA),
                                           con=self.con)["g:d"], daqui(hours=1))

    def test_o_prazo_vencido_para_de_esconder(self):
        banco.silenciar("g:d", daqui(hours=1), usuario_id=self.a, con=self.con)
        self.assertEqual(banco.silenciadas(usuario_id=self.a, agora_iso=daqui(hours=2),
                                           con=self.con), {})


class MigracaoDoBancoVelho(unittest.TestCase):
    """Um hub.db real do dia 26/08 tem de abrir aqui sem perder linha."""

    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        self.caminho = Path(self.pasta.name) / "velho.db"
        velho = sqlite3.connect(self.caminho)
        velho.executescript(ESQUEMA_VELHO)
        velho.execute("INSERT INTO medida VALUES ('dervs','local','2026-08-26T10:00:00+00:00','{}')")
        velho.execute("INSERT INTO pendencia_estado VALUES ('grafo_velho:dervs',?,?)",
                      (daqui(hours=24), iso(AGORA)))
        velho.commit()
        velho.close()

    def tearDown(self):
        self.pasta.cleanup()

    def test_o_dado_antigo_sobrevive_e_vira_do_dono_local(self):
        con = banco.conectar(self.caminho)
        try:
            self.assertEqual(
                con.execute("SELECT COUNT(*) FROM medida").fetchone()[0], 1)
            self.assertIn("grafo_velho:dervs", banco.silenciadas(agora_iso=iso(AGORA),
                                                                 con=con))
            colunas = {l[1] for l in con.execute("PRAGMA table_info(pendencia_estado)")}
            self.assertIn("usuario_id", colunas)
        finally:
            con.close()

    def test_abrir_duas_vezes_nao_duplica_nem_quebra(self):
        """A migracao roda em toda conexao: tem de ser inofensiva na segunda."""
        banco.conectar(self.caminho).close()
        con = banco.conectar(self.caminho)
        try:
            self.assertEqual(
                con.execute("SELECT COUNT(*) FROM pendencia_estado").fetchone()[0], 1)
        finally:
            con.close()



class ContaDesativada(unittest.TestCase):
    """Fechar a conta tem de fechar a porta — inclusive de quem ja esta dentro."""

    def setUp(self):
        self.con = banco.conectar(":memory:")
        self.uid = banco.criar_usuario("dono@teste.local", "teste1234", con=self.con)
        self.cookie = banco.novo_token()
        banco.abrir_sessao(self.uid, self.cookie, expira_em=daqui(hours=8), con=self.con)
        banco.abrir_pareamento(self.uid, "123456", expira_em=daqui(minutes=10),
                               con=self.con)
        self.token = banco.usar_pareamento("123456", "n", agora_iso=iso(AGORA),
                                           con=self.con)
        self.con.execute("UPDATE usuario SET desativado_em=? WHERE id=?",
                         (iso(AGORA), self.uid))
        self.con.commit()

    def tearDown(self):
        self.con.close()

    def test_a_sessao_que_ja_estava_aberta_para_de_valer(self):
        """Sem isto, o cookie no navegador sobrevive ao fechamento da conta."""
        self.assertIsNone(banco.sessao_valida(self.cookie, agora_iso=iso(AGORA),
                                              con=self.con))

    def test_o_agente_da_maquina_para_de_ser_aceito(self):
        self.assertIsNone(banco.maquina_por_token(self.token, con=self.con))

    def test_o_login_tambem_nao_acha_mais_a_conta(self):
        self.assertIsNone(banco.usuario_por_email("dono@teste.local", con=self.con))
        self.assertIsNone(banco.credencial_por_email("dono@teste.local", con=self.con))


class NadaDeSegredoNaSaida(unittest.TestCase):

    def setUp(self):
        self.con = banco.conectar(":memory:")
        self.uid = banco.criar_usuario("dono@teste.local", "teste1234", con=self.con)
        banco.guardar_totp(self.uid, "JBSWY3DPEHPK3PXP", con=self.con)

    def tearDown(self):
        self.con.close()

    def test_usuario_por_email_nao_devolve_senha_nem_segredo(self):
        """Era um `SELECT *`: bastava a etapa 9 devolver o dicionario num JSON."""
        u = banco.usuario_por_email("dono@teste.local", con=self.con)
        self.assertNotIn("senha_hash", u)
        self.assertNotIn("totp_segredo", u)

    def test_quem_precisa_da_senha_pede_pelo_nome(self):
        uid, guardado = banco.credencial_por_email("dono@teste.local", con=self.con)
        self.assertEqual(uid, self.uid)
        self.assertTrue(banco.conferir_senha("teste1234", guardado))

    def test_o_segredo_cifrado_de_um_nao_serve_na_linha_do_outro(self):
        """A cifra amarra o blob ao dono. Copiar de linha em linha nao decifra."""
        outro = banco.criar_usuario("outro@teste.local", "teste1234", con=self.con)
        blob = self.con.execute("SELECT segredo_hash FROM credencial"
                                " WHERE usuario_id=? AND tipo='totp'",
                                (self.uid,)).fetchone()[0]
        self.con.execute("INSERT INTO credencial (usuario_id, tipo, identificador,"
                         " segredo_hash, criado_em) VALUES (?,'totp',?,?,?)",
                         (outro, str(outro), blob, banco.agora()))
        self.con.commit()
        with self.assertRaises(ValueError):
            banco.ler_totp(outro, con=self.con)


class SubirDeNivelTrocaOCookie(unittest.TestCase):

    def setUp(self):
        self.con = banco.conectar(":memory:")
        uid = banco.criar_usuario("dono@teste.local", "teste1234", con=self.con)
        self.velho = banco.novo_token()
        banco.abrir_sessao(uid, self.velho, expira_em=daqui(hours=8), con=self.con)

    def tearDown(self):
        self.con.close()

    def test_o_cookie_de_antes_do_segundo_fator_deixa_de_valer(self):
        """Fixacao de sessao: quem plantou o cookie antes do login ficaria dentro."""
        novo = banco.novo_token()
        self.assertEqual(banco.confirmar_segundo_fator(self.velho, novo, con=self.con),
                         novo)
        self.assertIsNone(banco.sessao_valida(self.velho, agora_iso=iso(AGORA),
                                              con=self.con))
        s = banco.sessao_valida(novo, agora_iso=iso(AGORA), con=self.con)
        self.assertIsNotNone(s["segundo_fator_em"])


class OPrazoTemUmFormatoSo(unittest.TestCase):
    """A comparacao de prazo e por TEXTO, entao o formato e regra, nao estilo."""

    def setUp(self):
        self.con = banco.conectar(":memory:")
        self.uid = banco.criar_usuario("dono@teste.local", "teste1234", con=self.con)

    def tearDown(self):
        self.con.close()

    def test_prazo_produz_o_formato_que_o_banco_aceita(self):
        banco.abrir_sessao(self.uid, banco.novo_token(), expira_em=banco.prazo(3600),
                           con=self.con)

    def test_o_banco_recusa_prazo_com_Z_no_lugar_do_fuso(self):
        """'…T20:00:00Z' > '…T20:00:00+00:00' em texto: o Z sempre vence, e a
        sessao sobreviveria ao proprio vencimento."""
        with self.assertRaises(sqlite3.IntegrityError):
            banco.abrir_sessao(self.uid, banco.novo_token(),
                               expira_em="2026-08-26T20:00:00Z", con=self.con)


class OCofreNaoInventaChave(unittest.TestCase):

    def setUp(self):
        self.antigo = dict(os.environ)
        self.pasta = tempfile.TemporaryDirectory()
        banco._CHAVE_EM_MEMORIA = None

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.antigo)
        banco._CHAVE_EM_MEMORIA = None
        self.pasta.cleanup()

    def test_chave_curta_e_recusada_com_a_receita_na_mensagem(self):
        os.environ["DERVS_COFRE"] = "curta"
        with self.assertRaises(ValueError) as e:
            banco.chave_do_cofre()
        self.assertIn("secrets.token_urlsafe", str(e.exception))

    def test_fora_do_ambiente_local_ele_se_recusa_a_criar_a_chave(self):
        """Fabricar outra chave por variavel esquecida no servidor faria todo
        segredo ja guardado virar 'adulterado', em silencio. Melhor nao subir."""
        os.environ.pop("DERVS_COFRE", None)
        os.environ.pop("DERVS_AMBIENTE", None)
        os.environ["DERVS_COFRE_ARQUIVO"] = str(Path(self.pasta.name) / "c.chave")
        with self.assertRaises(RuntimeError):
            banco.chave_do_cofre()

    def test_no_ambiente_local_ela_nasce_e_e_estavel(self):
        os.environ.pop("DERVS_COFRE", None)
        os.environ["DERVS_AMBIENTE"] = "local"
        alvo = Path(self.pasta.name) / "c.chave"
        os.environ["DERVS_COFRE_ARQUIVO"] = str(alvo)
        primeira = banco.chave_do_cofre()
        self.assertTrue(alvo.exists())
        banco._CHAVE_EM_MEMORIA = None
        self.assertEqual(banco.chave_do_cofre(), primeira)


class MigracaoInterrompida(unittest.TestCase):
    """Uma queda no meio da reconstrucao nao pode nem perder dado nem travar."""

    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        self.caminho = Path(self.pasta.name) / "velho.db"
        velho = sqlite3.connect(self.caminho)
        velho.executescript(ESQUEMA_VELHO)
        velho.execute("INSERT INTO pendencia_estado VALUES ('g:d',?,?)",
                      (daqui(hours=24), iso(AGORA)))
        velho.commit()
        velho.close()

    def tearDown(self):
        self.pasta.cleanup()

    def test_sobra_de_uma_tentativa_anterior_nao_trava_o_banco_para_sempre(self):
        """A `_nova` orfa fazia `conectar()` explodir em TODA chamada — servidor
        e coletores fora do ar ate alguem dropar a tabela na mao."""
        c = sqlite3.connect(self.caminho)
        c.execute("CREATE TABLE pendencia_estado_nova (id TEXT, usuario_id INTEGER,"
                  " silenciada_ate TEXT, anotado_em TEXT)")
        c.commit()
        c.close()
        con = banco.conectar(self.caminho)
        try:
            self.assertIn("g:d", banco.silenciadas(agora_iso=iso(AGORA), con=con))
        finally:
            con.close()

    def test_chave_na_ordem_errada_tambem_e_corrigida(self):
        """Um banco que passou por versao intermediaria desta etapa tem a coluna
        de dono, mas com a chave em (id, usuario_id). A migracao olha a CHAVE,
        nao a existencia da coluna — a proxima chance custaria outra
        reconstrucao de tabela."""
        meio = Path(self.pasta.name) / "meio.db"
        c = sqlite3.connect(meio)
        c.executescript("""
            CREATE TABLE pendencia_estado (
                id TEXT NOT NULL, usuario_id INTEGER NOT NULL DEFAULT 0,
                silenciada_ate TEXT, anotado_em TEXT NOT NULL,
                PRIMARY KEY (id, usuario_id));""")
        c.execute("INSERT INTO pendencia_estado VALUES ('g:d', 7, ?, ?)",
                  (daqui(hours=24), iso(AGORA)))
        c.commit()
        c.close()
        con = banco.conectar(meio)
        try:
            forma = list(con.execute("PRAGMA table_info(pendencia_estado)"))
            chave = [l[1] for l in sorted((l for l in forma if l[5]),
                                          key=lambda l: l[5])]
            self.assertEqual(chave, ["usuario_id", "id"])
            # E o dono NAO foi zerado no caminho.
            self.assertIn("g:d", banco.silenciadas(usuario_id=7, agora_iso=iso(AGORA),
                                                   con=con))
        finally:
            con.close()

    def test_a_reconstrucao_e_tudo_ou_nada(self):
        """Sem transacao, uma queda entre o DROP e o RENAME apagava a tabela e
        deixava a copia orfa — e a migracao nunca mais tentava de novo."""
        con = banco.conectar(self.caminho)
        con.close()
        c = sqlite3.connect(self.caminho)
        try:
            sobrou = [l[0] for l in c.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
                " AND name LIKE '%_nova'")]
            self.assertEqual(sobrou, [])
            self.assertEqual(
                c.execute("SELECT COUNT(*) FROM pendencia_estado").fetchone()[0], 1)
        finally:
            c.close()

class MigracaoParaCredencial(unittest.TestCase):
    """Um hub.db da etapa 8 abre no esquema da 9 sem perder usuario nem segredo.

    Senha e TOTP eram COLUNAS da `usuario`. Isso amarra a pessoa a um jeito de
    entrar, e uma conta que so usa GitHub nao tem senha nenhuma para pos ali.
    """

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.caminho = str(Path(self.dir.name) / "hub.db")
        self.addCleanup(self.dir.cleanup)

    def _banco_da_etapa_8(self):
        """Recria a forma ANTIGA na mao.

        Nao importe o esquema de hoje aqui: o teste tem de descrever o passado,
        senao ele para de testar migracao no dia em que o esquema mudar de novo.
        """
        c = sqlite3.connect(self.caminho)
        c.executescript("""
            CREATE TABLE usuario (
                id                 INTEGER PRIMARY KEY AUTOINCREMENT CHECK (id <> 0),
                email              TEXT NOT NULL UNIQUE,
                nome               TEXT NOT NULL DEFAULT '',
                senha_hash         TEXT NOT NULL,
                totp_segredo       TEXT,
                totp_confirmado_em TEXT,
                criado_em          TEXT NOT NULL,
                desativado_em      TEXT);
            CREATE TABLE sessao (
                id               TEXT PRIMARY KEY,
                usuario_id       INTEGER NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
                criado_em        TEXT NOT NULL,
                expira_em        TEXT NOT NULL,
                segundo_fator_em TEXT,
                encerrada_em     TEXT);
        """)
        c.execute("INSERT INTO usuario (email, nome, senha_hash, totp_segredo,"
                  " totp_confirmado_em, criado_em) VALUES (?,?,?,?,?,?)",
                  ("thiago@teste.local", "Thiago", "scrypt$aaa", "cifrado$bbb",
                   iso(AGORA), iso(AGORA)))
        # Uma filha apontando para a usuario: se a reconstrucao deixar orfao, e
        # aqui que aparece.
        c.execute("INSERT INTO sessao (id, usuario_id, criado_em, expira_em)"
                  " VALUES ('h1', 1, ?, ?)", (iso(AGORA), iso(AGORA)))
        c.commit()
        c.close()

    def test_usuario_sobrevive_e_segredos_viram_credencial(self):
        self._banco_da_etapa_8()
        con = banco.conectar(self.caminho)
        try:
            u = con.execute("SELECT id, email FROM usuario").fetchall()
            self.assertEqual(len(u), 1)
            self.assertEqual(u[0]["email"], "thiago@teste.local")
            colunas = {l[1] for l in con.execute("PRAGMA table_info(usuario)")}
            self.assertNotIn("senha_hash", colunas)
            self.assertNotIn("totp_segredo", colunas)
            self.assertNotIn("totp_confirmado_em", colunas)
            cred = {l["tipo"]: l["segredo_hash"] for l in
                    con.execute("SELECT tipo, segredo_hash FROM credencial"
                                " WHERE usuario_id = ?", (u[0]["id"],))}
            self.assertEqual(cred["senha"], "scrypt$aaa")
            self.assertEqual(cred["totp"], "cifrado$bbb")
        finally:
            con.close()

    def test_a_sessao_antiga_nao_fica_orfa(self):
        self._banco_da_etapa_8()
        con = banco.conectar(self.caminho)
        try:
            self.assertEqual(list(con.execute("PRAGMA foreign_key_check")), [])
            self.assertEqual(
                con.execute("SELECT usuario_id FROM sessao").fetchone()[0], 1)
        finally:
            con.close()

    def test_migracao_e_idempotente(self):
        self._banco_da_etapa_8()
        banco.conectar(self.caminho).close()
        banco.conectar(self.caminho).close()
        con = banco.conectar(self.caminho)
        try:
            self.assertEqual(
                con.execute("SELECT COUNT(*) FROM credencial").fetchone()[0], 2)
        finally:
            con.close()

    def test_dois_usuarios_nao_reivindicam_o_mesmo_github(self):
        con = banco.conectar(self.caminho)
        try:
            a = con.execute("INSERT INTO usuario (email, criado_em) VALUES (?,?)",
                            ("a@teste.local", iso(AGORA))).lastrowid
            b = con.execute("INSERT INTO usuario (email, criado_em) VALUES (?,?)",
                            ("b@teste.local", iso(AGORA))).lastrowid
            con.execute("INSERT INTO credencial (usuario_id, tipo, identificador,"
                        " criado_em) VALUES (?,'github','4242',?)", (a, iso(AGORA)))
            with self.assertRaises(sqlite3.IntegrityError):
                con.execute("INSERT INTO credencial (usuario_id, tipo, identificador,"
                            " criado_em) VALUES (?,'github','4242',?)", (b, iso(AGORA)))
        finally:
            con.close()

    def test_tipo_de_credencial_inventado_e_recusado(self):
        con = banco.conectar(self.caminho)
        try:
            uid = con.execute("INSERT INTO usuario (email, criado_em) VALUES (?,?)",
                              ("c@teste.local", iso(AGORA))).lastrowid
            with self.assertRaises(sqlite3.IntegrityError):
                con.execute("INSERT INTO credencial (usuario_id, tipo, identificador,"
                            " criado_em) VALUES (?,'sei-la','x',?)", (uid, iso(AGORA)))
        finally:
            con.close()

    def test_apagar_usuario_leva_a_credencial_junto(self):
        con = banco.conectar(self.caminho)
        try:
            uid = con.execute("INSERT INTO usuario (email, criado_em) VALUES (?,?)",
                              ("d@teste.local", iso(AGORA))).lastrowid
            con.execute("INSERT INTO credencial (usuario_id, tipo, identificador,"
                        " criado_em) VALUES (?,'github','555',?)", (uid, iso(AGORA)))
            con.execute("DELETE FROM usuario WHERE id = ?", (uid,))
            self.assertEqual(
                con.execute("SELECT COUNT(*) FROM credencial").fetchone()[0], 0)
        finally:
            con.close()

    def test_instalacao_admite_uma_linha_so(self):
        con = banco.conectar(self.caminho)
        try:
            con.execute("INSERT OR IGNORE INTO instalacao (id, criada_em)"
                        " VALUES (1, ?)", (iso(AGORA),))
            with self.assertRaises(sqlite3.IntegrityError):
                con.execute("INSERT INTO instalacao (id, criada_em) VALUES (2, ?)",
                            (iso(AGORA),))
        finally:
            con.close()


class AsCorrecoesDaRevisao(unittest.TestCase):
    """Cada achado das revisoes de 26/08/2026 tem aqui o teste que o fecha."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.caminho = str(Path(self.dir.name) / "hub.db")
        self.addCleanup(self.dir.cleanup)

    def _forcar_estado_pre_etapa_9(self):
        """A migracao ja rodou neste banco; devolve a coluna para ela rodar de
        novo, agora por cima do estado que o teste montou."""
        con = banco.conectar(self.caminho)
        try:
            con.execute("PRAGMA foreign_keys=OFF")
            con.execute("ALTER TABLE usuario ADD COLUMN senha_hash TEXT")
            con.commit()
        finally:
            con.close()

    def test_orfao_HERDADO_nao_trava_o_conectar_para_sempre(self):
        """A pergunta certa e "eu piorei alguma coisa?", nao "esta tudo limpo?".

        A primeira versao comparava o banco inteiro contra zero: um orfao que ja
        estava la abortava a migracao, e como isso acontece dentro de
        `conectar()` — que roda em toda requisicao — o banco ficava inacessivel
        para sempre, sem caminho de volta no codigo.
        """
        con = banco.conectar(self.caminho)
        try:
            con.execute("PRAGMA foreign_keys=OFF")
            # Orfao numa FILHA da usuario, que e o caso dificil: ele nao foi
            # criado por esta migracao, entao ela nao pode se recusar a rodar.
            con.execute("INSERT INTO maquina (id, usuario_id, token_hash,"
                        " criado_em) VALUES (77, 999999, 'x', ?)", (iso(AGORA),))
            # E outro em tabela que nada tem a ver com a `usuario`.
            con.execute("INSERT INTO projeto_conectado (maquina_id, projeto,"
                        " visto_em) VALUES (4242, 'orfao', ?)", (iso(AGORA),))
            con.commit()
        finally:
            con.close()
        self._forcar_estado_pre_etapa_9()
        for _ in range(3):
            banco.conectar(self.caminho).close()
        # E o dado legitimo passou pela migracao intacto.
        con = banco.conectar(self.caminho)
        try:
            self.assertEqual(
                con.execute("SELECT COUNT(*) FROM maquina").fetchone()[0], 1)
        finally:
            con.close()

    def test_o_contador_de_orfaos_enxerga_o_que_promete(self):
        """A guarda so vale se o contador for verdadeiro. Se `_orfaos` devolvesse
        zero sempre, a comparacao antes/depois passaria em qualquer coisa."""
        con = banco.conectar(self.caminho)
        try:
            self.assertEqual(banco._orfaos(con), 0)
            con.execute("PRAGMA foreign_keys=OFF")
            con.execute("INSERT INTO maquina (usuario_id, token_hash, criado_em)"
                        " VALUES (12345, 'tok', ?)", (iso(AGORA),))
            con.commit()
            self.assertEqual(banco._orfaos(con), 1)
        finally:
            con.close()

    def test_o_contador_ignora_tabela_que_ainda_nao_existe(self):
        """O ESQUEMA roda DEPOIS da migracao: num hub.db antigo varias filhas
        ainda nao nasceram, e `PRAGMA foreign_key_check(x)` numa tabela ausente
        levanta erro em vez de devolver zero."""
        c = sqlite3.connect(self.caminho)
        c.execute("CREATE TABLE usuario (id INTEGER PRIMARY KEY,"
                  " email TEXT UNIQUE, criado_em TEXT)")
        c.commit()
        try:
            self.assertEqual(banco._orfaos(c), 0)
        finally:
            c.close()


    def test_a_sequencia_do_autoincrement_sobrevive(self):
        """Sem isto, um id ja usado seria reemitido — e `pendencia_estado` e
        `pendencia_arquivada` de proposito NAO tem chave estrangeira para
        `usuario`, entao as linhas da conta antiga seriam herdadas em silencio.
        """
        c = sqlite3.connect(self.caminho)
        c.executescript("""
            CREATE TABLE usuario (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                email         TEXT NOT NULL UNIQUE,
                nome          TEXT NOT NULL DEFAULT '',
                senha_hash    TEXT NOT NULL,
                criado_em     TEXT NOT NULL,
                desativado_em TEXT);""")
        for i in (1, 2, 3):
            c.execute("INSERT INTO usuario (email, senha_hash, criado_em)"
                      " VALUES (?,?,?)", ("u%d@t.local" % i, "x", iso(AGORA)))
        c.execute("DELETE FROM usuario WHERE id = 3")
        c.commit()
        antes = c.execute("SELECT seq FROM sqlite_sequence WHERE name='usuario'"
                          ).fetchone()[0]
        c.close()
        self.assertEqual(antes, 3)
        con = banco.conectar(self.caminho)
        try:
            depois = con.execute(
                "SELECT seq FROM sqlite_sequence WHERE name='usuario'").fetchone()[0]
            self.assertEqual(depois, antes,
                             "a sequencia voltou e um id sera reemitido")
        finally:
            con.close()

    def test_o_esquema_e_a_constante_da_migracao_nao_divergem(self):
        """As duas copias do CREATE da `credencial` so eram mantidas iguais por
        um comentario. Divergir e silencioso: banco novo ganha a coluna, banco
        migrado nao, e o `CREATE TABLE IF NOT EXISTS` vira no-op."""
        def normalizar(t):
            corpo = t[t.index("("):t.rindex(")")]
            palavras = []
            for linha in corpo.splitlines():
                palavras += linha.split("--")[0].split()
            return " ".join(palavras)
        do_esquema = banco.ESQUEMA[banco.ESQUEMA.index(
            "CREATE TABLE IF NOT EXISTS credencial"):]
        do_esquema = do_esquema[:do_esquema.index(");") + 1]
        self.assertEqual(normalizar(do_esquema),
                         normalizar(banco._CREATE_CREDENCIAL))

    def test_o_identificador_de_senha_tem_de_ser_o_dono(self):
        """Tira a garantia "uma senha por pessoa" da convencao e poe no banco."""
        con = banco.conectar(self.caminho)
        try:
            uid = banco.criar_usuario("x@teste.local", con=con)
            with self.assertRaises(sqlite3.IntegrityError):
                con.execute("INSERT INTO credencial (usuario_id, tipo,"
                            " identificador, criado_em) VALUES (?,'senha',?,?)",
                            (uid, "x@teste.local", iso(AGORA)))
        finally:
            con.close()

    def test_credencial_de_github_com_login_de_texto_e_recusada(self):
        """Nada impedia gravar o login ali, e casar por texto e entregar a conta
        a quem pegar o nome abandonado."""
        con = banco.conectar(self.caminho)
        try:
            uid = banco.criar_usuario("y@teste.local", con=con)
            with self.assertRaises(sqlite3.IntegrityError):
                banco.ligar_github(uid, "thiago", con=con)
            banco.ligar_github(uid, "4242", con=con)
        finally:
            con.close()


class AcessoPorGithub(unittest.TestCase):
    """Quem entra pelo GitHub nao tem senha, e o casamento e pelo id numerico."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.con = banco.conectar(str(Path(self.dir.name) / "hub.db"))
        self.addCleanup(self.con.close)

    def test_conta_sem_senha_e_valida(self):
        uid = banco.criar_usuario("thiago@teste.local", con=self.con)
        self.assertIsNone(banco.credencial_por_email("thiago@teste.local",
                                                     con=self.con))
        self.assertIsNotNone(banco.usuario_por_email("thiago@teste.local",
                                                     con=self.con))
        banco.ligar_github(uid, "4242", con=self.con)
        self.assertEqual(banco.usuario_por_github("4242", con=self.con)["id"], uid)

    def test_a_conta_com_senha_continua_achavel_pela_porta_de_emergencia(self):
        uid = banco.criar_usuario("andre@teste.local", "teste1234", con=self.con)
        achado = banco.credencial_por_email("andre@teste.local", con=self.con)
        self.assertIsNotNone(achado)
        self.assertEqual(achado[0], uid)
        self.assertTrue(banco.conferir_senha("teste1234", achado[1]))

    def test_github_desconhecido_devolve_none(self):
        self.assertIsNone(banco.usuario_por_github("999999", con=self.con))

    def test_conta_desativada_nao_entra_por_github(self):
        uid = banco.criar_usuario("desligado@teste.local", con=self.con)
        banco.ligar_github(uid, "777", con=self.con)
        self.con.execute("UPDATE usuario SET desativado_em = ? WHERE id = ?",
                         (banco.agora(), uid))
        self.con.commit()
        self.assertIsNone(banco.usuario_por_github("777", con=self.con))

    def test_credencial_revogada_nao_entra(self):
        uid = banco.criar_usuario("rafael@teste.local", con=self.con)
        banco.ligar_github(uid, "888", con=self.con)
        self.con.execute("UPDATE credencial SET revogada_em = ?"
                         " WHERE tipo='github' AND identificador='888'",
                         (banco.agora(),))
        self.con.commit()
        self.assertIsNone(banco.usuario_por_github("888", con=self.con))

    def test_a_saida_nao_traz_segredo_nenhum(self):
        uid = banco.criar_usuario("s@teste.local", "teste1234", con=self.con)
        banco.ligar_github(uid, "1234", con=self.con)
        banco.guardar_totp(uid, "JBSWY3DPEHPK3PXP", con=self.con)
        u = banco.usuario_por_github("1234", con=self.con)
        self.assertEqual(set(u), set(banco.COLUNAS_USUARIO))
        for proibido in ("senha_hash", "segredo_hash", "totp_segredo"):
            self.assertNotIn(proibido, u)

    def test_o_mesmo_github_em_duas_contas_e_recusado(self):
        a = banco.criar_usuario("a2@teste.local", con=self.con)
        b = banco.criar_usuario("b2@teste.local", con=self.con)
        banco.ligar_github(a, "5150", con=self.con)
        with self.assertRaises(sqlite3.IntegrityError):
            banco.ligar_github(b, "5150", con=self.con)

    def test_espaco_em_volta_do_id_nao_cria_conta_paralela(self):
        uid = banco.criar_usuario("e@teste.local", con=self.con)
        banco.ligar_github(uid, "  606  ", con=self.con)
        self.assertEqual(banco.usuario_por_github("606", con=self.con)["id"], uid)


# ======================================================================
# As portas de entrada (chave de acesso e codigo de recuperacao)
#
# Duas tabelas novas, e a razao de cada uma estar separada da `credencial`:
#
#   chave_de_acesso     precisa de um campo que MUDA a cada uso — o contador de
#                       assinaturas. A `credencial` nao tem onde por isso, e
#                       enfiar um contador em `segredo_hash` seria mentir sobre
#                       o que a coluna guarda.
#   codigo_recuperacao  sao DEZ linhas por pessoa, e a `credencial` tem um
#                       UNIQUE (tipo, identificador) que a limita a uma.
#
# O que os testes abaixo cobram, alem de "grava e le":
#
#   1. NAO HA SEGREDO NESTAS TABELAS. A chave de acesso guarda a chave PUBLICA,
#      que nao abre nada. O codigo de recuperacao guarda so a impressao digital.
#      Vazar as duas inteiras nao entrega a conta de ninguem.
#   2. USO UNICO E ATOMICO. Codigo de recuperacao usado duas vezes ao mesmo
#      tempo, ou contador que anda para tras, sao os dois caminhos de
#      transformar uma credencial em varias.
#   3. A CONTA MORTA NAO ENTRA. Toda leitura junta com `usuario` viva, do mesmo
#      jeito que `sessao_valida` faz.

class AChaveDeAcesso(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.con = banco.conectar(str(Path(self.tmp) / "hub.db"))
        self.uid = banco.criar_usuario("chave@teste.local", con=self.con)
        self.chave = (0x11, 0x22)

    def tearDown(self):
        self.con.close()

    def guardar(self, cred="cred-a", chave=None, apelido="PC do dono"):
        return banco.guardar_chave_de_acesso(
            self.uid, cred, chave or self.chave, apelido=apelido, con=self.con)

    def test_grava_e_le_de_volta(self):
        self.guardar()
        lida = banco.chave_de_acesso("cred-a", con=self.con)
        self.assertEqual(lida["usuario_id"], self.uid)
        self.assertEqual(lida["chave"], self.chave)
        self.assertEqual(lida["apelido"], "PC do dono")
        self.assertEqual(lida["contador"], 0)

    def test_a_chave_publica_volta_como_par_de_inteiros(self):
        """Sem isto, a rota receberia texto e a conferencia falharia calada."""
        grande = (2 ** 250 + 7, 2 ** 249 + 13)
        self.guardar(cred="cred-g", chave=grande)
        self.assertEqual(banco.chave_de_acesso("cred-g", con=self.con)["chave"],
                         grande)

    def test_credencial_desconhecida_devolve_none(self):
        self.assertIsNone(banco.chave_de_acesso("nunca-vista", con=self.con))

    def test_o_mesmo_cred_id_duas_vezes_e_recusado(self):
        """Dois donos reivindicando a mesma credencial e sequestro de conta."""
        self.guardar()
        outro = banco.criar_usuario("outro@teste.local", con=self.con)
        with self.assertRaises(sqlite3.IntegrityError):
            banco.guardar_chave_de_acesso(outro, "cred-a", (0x33, 0x44),
                                          con=self.con)

    def test_lista_as_chaves_do_dono(self):
        self.guardar(cred="c1", apelido="PC")
        self.guardar(cred="c2", apelido="celular")
        apelidos = {c["apelido"] for c in
                    banco.chaves_de_acesso(self.uid, con=self.con)}
        self.assertEqual(apelidos, {"PC", "celular"})

    def test_a_lista_nao_mostra_a_chave_de_outro_dono(self):
        """O IDOR mais obvio, e o que a etapa 8 consertou no esquema."""
        outro = banco.criar_usuario("vizinho@teste.local", con=self.con)
        banco.guardar_chave_de_acesso(outro, "c-alheia", (1, 2), con=self.con)
        self.guardar(cred="c-minha")
        listadas = [c["cred_id"] for c in
                    banco.chaves_de_acesso(self.uid, con=self.con)]
        self.assertEqual(listadas, ["c-minha"])

    def test_a_lista_nao_devolve_a_chave_publica(self):
        """A tela nao precisa dela, e o que nao sai nao vaza por descuido."""
        self.guardar()
        for c in banco.chaves_de_acesso(self.uid, con=self.con):
            self.assertNotIn("chave", c)

    def test_revogar_tira_da_lista(self):
        i = self.guardar()
        self.assertTrue(banco.revogar_chave_de_acesso(i, self.uid, con=self.con))
        self.assertEqual(banco.chaves_de_acesso(self.uid, con=self.con), [])

    def test_revogada_nao_entra_mais(self):
        i = self.guardar()
        banco.revogar_chave_de_acesso(i, self.uid, con=self.con)
        self.assertIsNone(banco.chave_de_acesso("cred-a", con=self.con))

    def test_ninguem_revoga_a_chave_de_outro(self):
        """`WHERE id = ?` sem o dono junto e o IDOR classico de rota de remocao."""
        i = self.guardar()
        outro = banco.criar_usuario("ladrao@teste.local", con=self.con)
        self.assertFalse(banco.revogar_chave_de_acesso(i, outro, con=self.con))
        self.assertIsNotNone(banco.chave_de_acesso("cred-a", con=self.con))

    def test_revogar_duas_vezes_devolve_falso(self):
        i = self.guardar()
        banco.revogar_chave_de_acesso(i, self.uid, con=self.con)
        self.assertFalse(banco.revogar_chave_de_acesso(i, self.uid, con=self.con))

    def test_a_conta_desativada_nao_entra(self):
        """Mesmo motivo do JOIN em `sessao_valida`: desativar tem de valer ja."""
        self.guardar()
        self.con.execute("UPDATE usuario SET desativado_em = ? WHERE id = ?",
                         (banco.agora(), self.uid))
        self.con.commit()
        self.assertIsNone(banco.chave_de_acesso("cred-a", con=self.con))

    def test_apagar_a_conta_leva_as_chaves(self):
        self.guardar()
        self.con.execute("DELETE FROM usuario WHERE id = ?", (self.uid,))
        self.con.commit()
        self.assertEqual(
            self.con.execute("SELECT COUNT(*) c FROM chave_de_acesso"
                             ).fetchone()["c"], 0)


class OContadorNoBanco(unittest.TestCase):
    """O contador de clone so vale se o BANCO o fizer valer.

    Conferir em Python e gravar depois deixa uma janela entre a decisao e a
    escrita: duas copias da mesma passkey entrando ao mesmo tempo passam as
    duas pela checagem antes de qualquer uma gravar. Aqui quem decide e o
    proprio UPDATE, e quem nao levar `rowcount == 1` perdeu — o mesmo desenho
    de `usar_pareamento`.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.con = banco.conectar(str(Path(self.tmp) / "hub.db"))
        self.uid = banco.criar_usuario("cont@teste.local", con=self.con)
        self.id = banco.guardar_chave_de_acesso(self.uid, "cred-c", (1, 2),
                                                contador=5, con=self.con)

    def tearDown(self):
        self.con.close()

    def test_avancar_grava(self):
        self.assertTrue(banco.usar_chave_de_acesso(self.id, 6, con=self.con))
        self.assertEqual(banco.chave_de_acesso("cred-c", con=self.con)["contador"], 6)

    def test_avancar_marca_o_uso(self):
        banco.usar_chave_de_acesso(self.id, 6, con=self.con)
        self.assertIsNotNone(
            self.con.execute("SELECT usado_em FROM chave_de_acesso WHERE id = ?",
                             (self.id,)).fetchone()["usado_em"])

    def test_repetir_o_contador_e_recusado(self):
        self.assertFalse(banco.usar_chave_de_acesso(self.id, 5, con=self.con))

    def test_voltar_e_recusado(self):
        self.assertFalse(banco.usar_chave_de_acesso(self.id, 4, con=self.con))

    def test_o_contador_nao_muda_quando_recusa(self):
        banco.usar_chave_de_acesso(self.id, 4, con=self.con)
        self.assertEqual(banco.chave_de_acesso("cred-c", con=self.con)["contador"], 5)

    def test_chave_revogada_nao_avanca(self):
        banco.revogar_chave_de_acesso(self.id, self.uid, con=self.con)
        self.assertFalse(banco.usar_chave_de_acesso(self.id, 99, con=self.con))

    def test_autenticador_que_nao_conta(self):
        """Zero para sempre e legitimo: a norma preve autenticador sem contador."""
        i = banco.guardar_chave_de_acesso(self.uid, "cred-z", (1, 2),
                                          contador=0, con=self.con)
        self.assertTrue(banco.usar_chave_de_acesso(i, 0, con=self.con))

    def test_o_banco_e_o_python_concordam(self):
        """Duas regras escritas em dois lugares divergem. Esta trava avisa.

        `passkey.contador_ok` e o UPDATE de `usar_chave_de_acesso` decidem a
        mesma coisa em linguagens diferentes. Se alguem afrouxar uma e esquecer
        a outra, e aqui que aparece.
        """
        import passkey
        for guardado in (0, 1, 5):
            for novo in (0, 1, 5, 6):
                i = banco.guardar_chave_de_acesso(
                    self.uid, "par-%d-%d" % (guardado, novo), (1, 2),
                    contador=guardado, con=self.con)
                self.assertEqual(
                    banco.usar_chave_de_acesso(i, novo, con=self.con),
                    passkey.contador_ok(guardado, novo),
                    "guardado=%d novo=%d" % (guardado, novo))


class OsCodigosDeRecuperacao(unittest.TestCase):
    """A saida de emergencia que impede a conta de virar pane permanente.

    Sem eles, "login sem senha" com duas pessoas e uma conta a um celular
    quebrado de distancia de ficar trancada para sempre — e nao ha recuperacao
    por e-mail neste sistema, de proposito.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.con = banco.conectar(str(Path(self.tmp) / "hub.db"))
        self.uid = banco.criar_usuario("recup@teste.local", con=self.con)

    def tearDown(self):
        self.con.close()

    def test_gera_dez(self):
        self.assertEqual(len(banco.gerar_codigos_de_recuperacao(
            self.uid, con=self.con)), 10)

    def test_todos_diferentes(self):
        codigos = banco.gerar_codigos_de_recuperacao(self.uid, con=self.con)
        self.assertEqual(len(set(codigos)), 10)

    def test_nao_repetem_entre_geracoes(self):
        a = set(banco.gerar_codigos_de_recuperacao(self.uid, con=self.con))
        b = set(banco.gerar_codigos_de_recuperacao(self.uid, con=self.con))
        self.assertFalse(a & b)

    def test_tem_entropia_de_sobra(self):
        """Codigo curto e chutavel, e este nao tem teto de tentativa por conta."""
        for c in banco.gerar_codigos_de_recuperacao(self.uid, con=self.con):
            self.assertGreaterEqual(len(c.replace("-", "")), 16)

    def test_o_codigo_em_claro_nao_fica_no_banco(self):
        """A prova de que a tabela guarda impressao digital, e nao o codigo."""
        codigos = banco.gerar_codigos_de_recuperacao(self.uid, con=self.con)
        cru = open(str(Path(self.tmp) / "hub.db"), "rb").read()
        for c in codigos:
            self.assertNotIn(c.encode("ascii"), cru)
            self.assertNotIn(c.replace("-", "").encode("ascii"), cru)

    def test_o_codigo_abre_a_conta(self):
        c = banco.gerar_codigos_de_recuperacao(self.uid, con=self.con)[0]
        self.assertEqual(banco.usar_codigo_de_recuperacao(c, con=self.con),
                         self.uid)

    def test_uso_unico(self):
        c = banco.gerar_codigos_de_recuperacao(self.uid, con=self.con)[0]
        banco.usar_codigo_de_recuperacao(c, con=self.con)
        self.assertIsNone(banco.usar_codigo_de_recuperacao(c, con=self.con))

    def test_usar_um_nao_gasta_os_outros(self):
        codigos = banco.gerar_codigos_de_recuperacao(self.uid, con=self.con)
        banco.usar_codigo_de_recuperacao(codigos[0], con=self.con)
        self.assertEqual(banco.usar_codigo_de_recuperacao(codigos[1],
                                                          con=self.con), self.uid)

    def test_codigo_inventado_nao_abre(self):
        banco.gerar_codigos_de_recuperacao(self.uid, con=self.con)
        self.assertIsNone(banco.usar_codigo_de_recuperacao("NAO-EXISTE-MESMO",
                                                           con=self.con))

    def test_codigo_vazio_nao_abre(self):
        """Falha FECHADA: string vazia nao pode casar com linha nenhuma."""
        banco.gerar_codigos_de_recuperacao(self.uid, con=self.con)
        for lixo in ("", None, "   ", "-----"):
            self.assertIsNone(banco.usar_codigo_de_recuperacao(lixo, con=self.con))

    def test_aceita_digitado_torto(self):
        """Quem copia do papel erra caixa e tracinho. Isso nao e tentativa errada."""
        c = banco.gerar_codigos_de_recuperacao(self.uid, con=self.con)[0]
        torto = "  " + c.lower().replace("-", " ") + "  "
        self.assertEqual(banco.usar_codigo_de_recuperacao(torto, con=self.con),
                         self.uid)

    def test_gerar_de_novo_queima_os_antigos(self):
        """Pediu lista nova, a antiga morre — senao o papel velho continua valendo."""
        velhos = banco.gerar_codigos_de_recuperacao(self.uid, con=self.con)
        banco.gerar_codigos_de_recuperacao(self.uid, con=self.con)
        self.assertIsNone(banco.usar_codigo_de_recuperacao(velhos[0],
                                                           con=self.con))

    def test_gerar_de_novo_nao_apaga_o_rastro_do_que_foi_usado(self):
        """Codigo gasto e evidencia. Apagar a linha apaga a evidencia."""
        velhos = banco.gerar_codigos_de_recuperacao(self.uid, con=self.con)
        banco.usar_codigo_de_recuperacao(velhos[0], con=self.con)
        banco.gerar_codigos_de_recuperacao(self.uid, con=self.con)
        usados = self.con.execute(
            "SELECT COUNT(*) c FROM codigo_recuperacao WHERE usado_em IS NOT NULL"
        ).fetchone()["c"]
        self.assertEqual(usados, 1)

    def test_conta_quantos_sobraram(self):
        codigos = banco.gerar_codigos_de_recuperacao(self.uid, con=self.con)
        self.assertEqual(banco.codigos_restantes(self.uid, con=self.con), 10)
        banco.usar_codigo_de_recuperacao(codigos[0], con=self.con)
        self.assertEqual(banco.codigos_restantes(self.uid, con=self.con), 9)

    def test_o_codigo_de_um_nao_abre_a_conta_do_outro(self):
        outro = banco.criar_usuario("outro-r@teste.local", con=self.con)
        meu = banco.gerar_codigos_de_recuperacao(self.uid, con=self.con)[0]
        self.assertEqual(banco.usar_codigo_de_recuperacao(meu, con=self.con),
                         self.uid)
        self.assertNotEqual(banco.codigos_restantes(outro, con=self.con), 9)

    def test_conta_desativada_nao_entra_por_codigo(self):
        c = banco.gerar_codigos_de_recuperacao(self.uid, con=self.con)[0]
        self.con.execute("UPDATE usuario SET desativado_em = ? WHERE id = ?",
                         (banco.agora(), self.uid))
        self.con.commit()
        self.assertIsNone(banco.usar_codigo_de_recuperacao(c, con=self.con))


class AMigracaoDaMedida(unittest.TestCase):
    """A `medida` antiga nao tem dono: nao da para saber de quem e cada linha."""

    def _banco_antigo(self, emails):
        """Um hub.db no formato de antes, com as contas pedidas."""
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        caminho = Path(pasta.name) / "hub.db"
        antes = banco.BANCO
        banco.BANCO = caminho
        self.addCleanup(setattr, banco, "BANCO", antes)
        con = banco.conectar()                    # nasce ja no formato de hoje
        for e in emails:
            banco.criar_usuario(e, con=con)
        con.commit()
        # e AGORA volta a `medida` para a forma antiga, sem dono
        con.execute("DROP TABLE medida")
        con.execute("""CREATE TABLE medida (
            projeto TEXT NOT NULL, camada TEXT NOT NULL,
            medido_em TEXT NOT NULL, dados TEXT NOT NULL,
            PRIMARY KEY (projeto, camada))""")
        con.execute("INSERT INTO medida VALUES ('site','local','x','{}')")
        con.commit()
        con.close()
        return caminho

    def test_com_mais_de_uma_conta_nao_entrega_a_ninguem(self):
        """Entregar a `CONTA_LOCAL` moveria o inventario alheio — nomes de
        projeto, caminhos, contagem de alerta — para uma conta que
        `/entrar/local` abre SEM SENHA, e o `DROP TABLE` apagaria o rastro.

        Com mais de uma conta, `DONO_LOCAL`: ninguem le, e o coletor local repoe
        a medicao em 60 s. Achado da revisao da correcao, com prova rodada.
        """
        self._banco_antigo([banco.CONTA_LOCAL, "outra@empresa.com"])
        con = banco.conectar()
        self.addCleanup(con.close)
        donos = [l[0] for l in con.execute("SELECT usuario_id FROM medida")]
        self.assertEqual(donos, [banco.DONO_LOCAL],
                         "a migracao entregou dado sem dono a uma conta")

    def test_com_uma_conta_so_entrega_a_ela(self):
        """Maquina do dono: a medicao antiga E dele, e jogar no zero deixaria o
        painel vazio ate a proxima coleta."""
        self._banco_antigo([banco.CONTA_LOCAL])
        con = banco.conectar()
        self.addCleanup(con.close)
        uid = con.execute("SELECT id FROM usuario WHERE email = ?",
                          (banco.CONTA_LOCAL,)).fetchone()["id"]
        donos = [l[0] for l in con.execute("SELECT usuario_id FROM medida")]
        self.assertEqual(donos, [uid])

    def test_rodar_de_novo_nao_muda_nada(self):
        """`migrar()` roda em TODA conexao."""
        self._banco_antigo([banco.CONTA_LOCAL])
        for _ in range(3):
            banco.conectar().close()
        con = banco.conectar()
        self.addCleanup(con.close)
        self.assertEqual(len(list(con.execute("SELECT * FROM medida"))), 1)


class AContaLocalDesativada(unittest.TestCase):
    def test_nao_estoura_no_unique_do_email(self):
        """O SELECT filtrava `desativado_em IS NULL`, nao achava, e o
        `criar_usuario` seguinte estourava no UNIQUE — derrubando o servidor e a
        coleta. Achado da revisao da correcao."""
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        antes_b, antes_a = banco.BANCO, os.environ.get("DERVS_AMBIENTE")
        banco.BANCO = Path(pasta.name) / "hub.db"
        os.environ["DERVS_AMBIENTE"] = "local"
        self.addCleanup(setattr, banco, "BANCO", antes_b)
        self.addCleanup(os.environ.__setitem__, "DERVS_AMBIENTE", antes_a or "")
        con = banco.conectar()
        self.addCleanup(con.close)
        uid = banco.criar_usuario(banco.CONTA_LOCAL, con=con)
        self.assertEqual(banco.conta_local(con), uid)
        con.execute("UPDATE usuario SET desativado_em = ? WHERE id = ?",
                    (banco.agora(), uid))
        con.commit()
        self.assertEqual(banco.conta_local(con), banco.DONO_LOCAL)


class OndeMoraOBanco(unittest.TestCase):
    """O `hub.db` precisa poder morar FORA da pasta do codigo.

    No servidor o codigo vive dentro de uma imagem que e jogada fora e
    reconstruida a cada publicacao. Um `hub.db` em `/app` seria apagado junto
    com ela: toda conta, todo pareamento e toda medicao sumiriam a cada deploy,
    em silencio, e o painel voltaria a dizer "sem dados" para tudo. A variavel
    `DERVS_BANCO` aponta o arquivo para um volume, que sobrevive.
    """

    def setUp(self):
        self._antes = os.environ.get("DERVS_BANCO")
        self.addCleanup(self._restaurar)

    def _restaurar(self):
        if self._antes is None:
            os.environ.pop("DERVS_BANCO", None)
        else:
            os.environ["DERVS_BANCO"] = self._antes

    def test_sem_a_variavel_fica_ao_lado_do_codigo(self):
        os.environ.pop("DERVS_BANCO", None)
        self.assertEqual(banco._caminho_do_banco(), banco.AQUI / "hub.db")

    def test_com_a_variavel_vai_para_onde_ela_mandar(self):
        os.environ["DERVS_BANCO"] = "/dados/hub.db"
        self.assertEqual(banco._caminho_do_banco(), Path("/dados/hub.db"))

    def test_variavel_vazia_nao_vira_caminho_vazio(self):
        """Variavel definida como "" e um `docker compose` sem valor, nao um
        pedido de gravar em Path(""). Vale o padrao."""
        os.environ["DERVS_BANCO"] = "   "
        self.assertEqual(banco._caminho_do_banco(), banco.AQUI / "hub.db")


if __name__ == "__main__":
    unittest.main(verbosity=2)
