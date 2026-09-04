# -*- coding: utf-8 -*-
"""E5 de "Servidores multiplos" (04/09/2026): `novo["sites"]` vira lista, um
item por servidor.

`coletar_github._monta_sites` monta, por projeto, uma medicao por servidor
onde a conta declarou endereco (pela tela, via `banco.enderecos_por_servidor`),
preservando POR SERVIDOR a medicao anterior quando a nova vier `ok=None` —
nunca a do vizinho, nunca a lista inteira.

O CASO DO FIO INTEIRO nao pode ser apagado nem simplificado: banco de
verdade -> trecho de coleta -> `banco.montar_estado` -> `regras.avaliar` ->
pendencias `site_fora`, uma por servidor fora do ar, com ids diferentes. Sem
ele, E3 (banco) e E2 (regras) provam cada metade contra dublê e a entrega
pode estar morta — foi exatamente o que aconteceu com a Auditoria Profunda em
02/09/2026, com 26 suites verdes e a funcionalidade inalcancavel.

    python test_servidores.py
"""
from __future__ import annotations

import os
import unittest

# Precisa vir ANTES de importar `banco`: sem isto o teste passa aqui e fica
# vermelho so na CI (`45963da`, 29/08/2026).
os.environ.setdefault("DERVS_AMBIENTE", "local")
os.environ.setdefault("DERVS_COFRE",
                      "chave-de-teste-que-nao-e-segredo-nenhum-0123456789")

import banco            # noqa: E402
import coletar_github   # noqa: E402
import regras           # noqa: E402


class _ConexaoDeMentira:
    """O bastante para `coletar_github.main()` rodar sem banco de verdade:
    ele so commita e fecha."""

    def commit(self):
        pass

    def close(self):
        pass


class MontaSites(unittest.TestCase):
    """`coletar_github._monta_sites`, isolada, contra `mede_site` de mentira."""

    def setUp(self):
        self._mede_original = coletar_github.mede_site
        self.addCleanup(setattr, coletar_github, "mede_site", self._mede_original)

    def _dublado_mede_site(self, respostas: dict) -> None:
        coletar_github.mede_site = lambda url: dict(
            respostas[url], url=url, ms=1, tentativas=1)

    def test_dois_servidores_dois_itens_ordenados_com_medido_em_proprio(self):
        itens = [
            {"servidor_id": 1, "servidor": "AWS", "url": "https://aws.exemplo"},
            {"servidor_id": 2, "servidor": "OVH", "url": "https://ovh.exemplo"},
        ]
        self._dublado_mede_site({
            "https://aws.exemplo": {"ok": True, "codigo": 200, "erro": ""},
            "https://ovh.exemplo": {"ok": True, "codigo": 200, "erro": ""},
        })
        sites = coletar_github._monta_sites("proj", itens, "", {})
        self.assertEqual([s["servidor"] for s in sites], ["AWS", "OVH"])
        self.assertTrue(all(s["medido_em"] for s in sites),
                        "todo item tem o proprio carimbo")

    def test_um_fora_outro_nao_medido_preserva_so_o_do_nao_medido(self):
        """Sabota com TAMANHO, nao so com presenca: dois servidores, senao
        `sites[0]` acertaria por acidente (a mesma licao de 02/09)."""
        itens = [
            {"servidor_id": 1, "servidor": "AWS", "url": "https://aws.exemplo"},
            {"servidor_id": 2, "servidor": "OVH", "url": "https://ovh.exemplo"},
        ]
        antes_gh = {"sites": [
            {"servidor_id": 1, "servidor": "AWS", "url": "https://aws.exemplo",
             "ok": True, "codigo": 200, "erro": "", "medido_em": "velho-aws"},
            {"servidor_id": 2, "servidor": "OVH", "url": "https://ovh.exemplo",
             "ok": True, "codigo": 200, "erro": "", "medido_em": "velho-ovh"},
        ]}
        self._dublado_mede_site({
            "https://aws.exemplo": {"ok": False, "codigo": 500, "erro": ""},
            "https://ovh.exemplo": {"ok": None, "codigo": 0, "erro": "nao_resolveu"},
        })
        sites = coletar_github._monta_sites("proj", itens, "", antes_gh)
        por_id = {s["servidor_id"]: s for s in sites}
        # O A tem medicao NOVA: nao foi preservado.
        self.assertFalse(por_id[1]["ok"])
        self.assertNotEqual(por_id[1]["medido_em"], "velho-aws")
        # O B nao foi medido: preserva o PROPRIO anterior, nunca o do A.
        self.assertTrue(por_id[2]["ok"])
        self.assertEqual(por_id[2]["medido_em"], "velho-ovh")

    def test_sem_endereco_nenhum_e_sem_url_prod_devolve_lista_vazia(self):
        self.assertEqual(coletar_github._monta_sites("proj", [], "", {}), [])

    def test_so_com_url_prod_do_casos_json_gera_um_item_com_servidor_vazio(self):
        self._dublado_mede_site(
            {"https://arquivo.exemplo": {"ok": True, "codigo": 200, "erro": ""}})
        sites = coletar_github._monta_sites(
            "proj", [], "https://arquivo.exemplo", {})
        self.assertEqual(len(sites), 1)
        self.assertEqual(sites[0]["servidor"], "")
        self.assertEqual(sites[0]["servidor_id"], 0)

    def test_o_banco_vence_o_arquivo_quando_ha_os_dois(self):
        itens = [{"servidor_id": 1, "servidor": "OVH",
                  "url": "https://do-banco.exemplo"}]
        self._dublado_mede_site(
            {"https://do-banco.exemplo": {"ok": True, "codigo": 200, "erro": ""}})
        sites = coletar_github._monta_sites(
            "proj", itens, "https://do-arquivo.exemplo", {})
        self.assertEqual([s["url"] for s in sites], ["https://do-banco.exemplo"])


class ONovoSitesSempreExiste(unittest.TestCase):
    """`coletar_github.main()` de ponta a ponta, com banco e rede de mentira:
    confere o dicionario que de fato chega em `banco.gravar`, nao um pedaco
    isolado."""

    def _rodar(self, por_servidor: dict, url_no_arquivo: str,
              respostas_mede_site: dict) -> dict:
        capturado = {}
        local = {"git": {"remoto_slug": "dono/repo"}}
        if url_no_arquivo:
            local["url_prod"] = url_no_arquivo

        def gravar(nome, camada, dados, con=None, *, usuario_id):
            if camada == "github":
                capturado.update(dados)

        for alvo, nome, valor in (
                (banco, "ler_tudo", lambda **k: {"projeto": {
                    "local": {"dados": local}}}),
                (banco, "conectar", lambda *a, **k: _ConexaoDeMentira()),
                (banco, "conta_local", lambda *a, **k: 1),
                (banco, "enderecos_por_servidor",
                 lambda uid, con=None: por_servidor),
                (banco, "gravar", gravar),
                (coletar_github, "mede_deploy", lambda *a, **k: {}),
                (coletar_github, "mede_site",
                 lambda u: dict(respostas_mede_site[u], url=u, ms=1, tentativas=1)),
                (coletar_github, "_gh_graphql", lambda q: (
                    {"r0": {"nameWithOwner": "dono/repo",
                            "url": "https://github.com/dono/repo",
                            "defaultBranchRef": {"name": "main", "target": {}}}},
                    None))):
            self.addCleanup(setattr, alvo, nome, getattr(alvo, nome))
            setattr(alvo, nome, valor)
        coletar_github.main()
        return capturado

    def test_sem_endereco_nenhum_sites_vazio_e_sem_a_chave_singular(self):
        novo = self._rodar({}, "", {})
        self.assertEqual(novo["sites"], [])
        self.assertNotIn("site", novo,
                         "\"site\" singular deixa de ser escrito nesta etapa")

    def test_com_endereco_no_banco_sites_carrega_um_item(self):
        por_servidor = {"projeto": [
            {"servidor_id": 1, "servidor": "OVH", "url": "https://ovh.exemplo"}]}
        novo = self._rodar(por_servidor, "",
                           {"https://ovh.exemplo": {"ok": True, "codigo": 200,
                                                      "erro": ""}})
        self.assertEqual(len(novo["sites"]), 1)
        self.assertEqual(novo["sites"][0]["servidor"], "OVH")
        self.assertNotIn("site", novo)


class UrlDoPadrao(unittest.TestCase):
    """`coletar_github.url_do_padrao` — so FORMA, sem rede. E8 de "servidores
    multiplos": o padrao vira URL candidata para a sugestao, e nada aqui bate
    em lugar nenhum."""

    def test_padrao_com_um_asterisco_vira_url(self):
        self.assertEqual(
            coletar_github.url_do_padrao("*.tinehost.com.br", "ccvp-painel"),
            "https://ccvp-painel.tinehost.com.br")

    def test_padrao_sem_asterisco_e_recusado(self):
        self.assertEqual(
            coletar_github.url_do_padrao("tinehost.com.br", "ccvp-painel"), "")

    def test_padrao_com_dois_asteriscos_e_recusado(self):
        self.assertEqual(
            coletar_github.url_do_padrao("*.tinehost.*.br", "ccvp-painel"), "")

    def test_projeto_com_barra_e_recusado(self):
        self.assertEqual(
            coletar_github.url_do_padrao("*.tinehost.com.br", "a/b"), "")

    def test_projeto_com_espaco_e_recusado(self):
        self.assertEqual(
            coletar_github.url_do_padrao("*.tinehost.com.br", "a b"), "")

    def test_projeto_com_ponto_ponto_e_recusado(self):
        self.assertEqual(
            coletar_github.url_do_padrao("*.tinehost.com.br", "a..b"), "")

    def test_padrao_vazio_e_recusado(self):
        self.assertEqual(coletar_github.url_do_padrao("", "ccvp-painel"), "")


class OFioInteiro(unittest.TestCase):
    """Banco de verdade -> trecho de coleta -> `banco.montar_estado` ->
    `regras.avaliar`: dois servidores fora do ar no mesmo projeto viram DUAS
    pendencias `site_fora`, com ids diferentes — sem isto os dois colidem no
    mesmo id e o painel some com um."""

    def setUp(self):
        self.con = banco.conectar(":memory:")
        self.dono = banco.criar_usuario("a@teste.local", "teste1234",
                                        con=self.con)
        self.s1 = banco.guardar_servidor(self.dono, "AWS", con=self.con)
        self.s2 = banco.guardar_servidor(self.dono, "OVH", con=self.con)
        banco.guardar_endereco_de_producao(
            self.dono, self.s1, "dervs", "https://aws.exemplo", con=self.con)
        banco.guardar_endereco_de_producao(
            self.dono, self.s2, "dervs", "https://ovh.exemplo", con=self.con)
        banco.gravar("dervs", "local", {"nome": "dervs"}, self.con,
                    usuario_id=self.dono)
        self._mede_original = coletar_github.mede_site
        self.addCleanup(setattr, coletar_github, "mede_site", self._mede_original)
        coletar_github.mede_site = lambda url: {
            "url": url, "ok": False, "codigo": 503, "erro": "",
            "ms": 1, "tentativas": 2}

    def tearDown(self):
        self.con.close()

    def test_dois_servidores_fora_viram_duas_pendencias_com_ids_diferentes(self):
        por_servidor = banco.enderecos_por_servidor(self.dono, con=self.con)
        novo = {"nome": "dervs"}
        novo["sites"] = coletar_github._monta_sites(
            "dervs", por_servidor.get("dervs") or [], "", {})
        banco.gravar("dervs", "github", novo, self.con, usuario_id=self.dono)
        self.con.commit()

        estado = banco.montar_estado(self.con, usuario_id=self.dono)
        pendencias = regras.avaliar(estado["projetos"])
        do_site = [p for p in pendencias if p["regra"] == "site_fora"]

        self.assertEqual(len(do_site), 2)
        self.assertEqual(len({p["id"] for p in do_site}), 2,
                         "os dois ids tem de ser diferentes")
        textos = " | ".join(p["texto"] for p in do_site)
        self.assertIn("AWS", textos)
        self.assertIn("OVH", textos)


if __name__ == "__main__":
    unittest.main()
