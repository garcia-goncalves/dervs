# -*- coding: utf-8 -*-
"""O cartao "GitHub" da tela Conectar, com varias contas (Conectar simples).

O que a tela nao pode fazer, e nenhum teste de "o botao existe" pega:

  - mostrar o NUMERO da instalacao no lugar do nome da conta;
  - montar link para fora do github.com (o endereco vem do servidor, e o nome
    da conta vem do GitHub: dado de fora, so `textContent` e link filtrado);
  - esconder as contas de quem tem mais de uma;
  - continuar com o botao "Procurar minhas contas" (a procura e sozinha);
  - transformar o 429 do nosso proprio automatismo num erro na cara do dono;
  - dizer "nenhuma conta" quando a leitura falhou (a Lei 2: "nao olhei").

As funcoes de montagem sao EXECUTADAS em node com um DOM de mentira (o mesmo de
`test_conectar_tela.py`); sem node os casos de comportamento sao pulados e os
de texto continuam.

    python test_github_tela.py
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

from test_conectar_tela import (PRELUDIO_DA_REDE, PRELUDIO_DE_TEMPO, constante,
                                funcao, fontes, roda)

RAIZ = Path(__file__).resolve().parent
JS = (RAIZ / "assets" / "painel.js").read_text(encoding="utf-8")

FUNCOES = ("criar", "haQuanto", "marcaDaPorta", "linhaComChave", "detalhes",
           "cartaoDeLigacao", "linhaDeRepositorio", "linhaDeContaDoGithub",
           "cartaoDoGithub", "procurarContasUmaVez", "repintarGithub",
           "procurarContasDoGithub")

ESTADO_INICIAL = r"""
let GITHUB = null, GITHUB_LIDO_EM = "";
let PAGINA_VELHA = false;
let PROCUROU_GITHUB = false;
let GITHUB_PROCURA = { fase: "", achou: "" };
globalThis.location = { search: "", hash: "#/conectar" };
const ligou = [], procurou = [], pintou = [];
function ligarOGithub() { ligou.push(1); }
function pintarConectar() { pintou.push(1); }
function rota() { return { tela: "conectar" }; }
async function olharOGithub() { GITHUB = NOVO_GITHUB || GITHUB; GITHUB_LIDO_EM = ha(0); }
let NOVO_GITHUB = null;
async function escrever(url) { procurou.push(url); const r = RESPOSTAS.shift(); return r; }
async function carregar() {}
"""


def rode(caso, script, respostas="[]"):
    return roda(caso, [PRELUDIO_DA_REDE, PRELUDIO_DE_TEMPO, ESTADO_INICIAL]
                + fontes(*FUNCOES, consts=("ESTADO_DA_PORTA", "DETALHES_ABERTOS")),
                "RESPOSTAS = " + respostas + ";\n" + script)


CONTA = ('{ conta_login: "loja-da-ana", conta_tipo: "User", medidos: 5, '
         'medido_em: ha(240), gerenciar_url: "https://github.com/settings/installations/1", '
         'repositorios: [{ projeto: "loja-da-ana", slug: "loja-da-ana/site", medido: true, oculto: false }] }')


class AContaMostraNomeTipoMedicaoELinkSeguro(unittest.TestCase):
    def conta(self, c):
        return rode(self, "const li = linhaDeContaDoGithub(%s);\n"
                    "const links = achaTodos(li, n => n.tag === 'a');\n"
                    "console.log(JSON.stringify({ texto: li.textContent, "
                    "links: links.map(a => [a.href, a.rel, a.target]) }));" % c)

    def test_pessoal_mostra_o_nome_nunca_o_numero_e_a_medicao(self):
        r = self.conta(CONTA.replace("medidos: 5", "medidos: 5, installation_id: 4242, id: 4242"))
        self.assertIn("loja-da-ana", r["texto"])
        self.assertIn("pessoal", r["texto"])
        self.assertIn("mede 5 repositórios · mediu há 4 minutos", r["texto"])
        self.assertNotIn("4242", r["texto"])

    def test_organizacao_diz_organizacao(self):
        r = self.conta(CONTA.replace('"User"', '"Organization"'))
        self.assertIn("organização", r["texto"])
        self.assertNotIn("pessoal", r["texto"])

    def test_um_repositorio_fica_no_singular_e_nenhum_diz_que_nao_mediu(self):
        um = self.conta(CONTA.replace("medidos: 5", "medidos: 1"))
        self.assertIn("mede 1 repositório · mediu", um["texto"])
        zero = self.conta(CONTA.replace("medidos: 5", "medidos: null"))
        self.assertIn("ainda não mediu repositórios", zero["texto"])
        self.assertNotIn("mede 0", zero["texto"])

    def test_o_link_abre_em_aba_nova_sem_referrer_e_diz_isso_ao_leitor(self):
        r = self.conta(CONTA)
        self.assertEqual(r["links"], [["https://github.com/settings/installations/1",
                                       "noopener noreferrer", "_blank"]])
        self.assertIn("Escolher repositórios no GitHub", r["texto"])
        self.assertIn("abre o GitHub em outra aba", r["texto"])

    def test_link_fora_do_github_nao_e_montado(self):
        for ruim in ("javascript:alert(1)", "http://github.com/x",
                     "https://github.com.evil.com/x", "//github.com/x",
                     "https://evil.com/https://github.com/"):
            with self.subTest(url=ruim):
                r = self.conta(CONTA.replace("https://github.com/settings/installations/1", ruim))
                self.assertEqual(r["links"], [])

    def test_o_nome_da_conta_vem_de_fora_e_entra_como_texto(self):
        r = self.conta(CONTA.replace('"loja-da-ana", conta_tipo', '"<img src=x onerror=1>", conta_tipo'))
        self.assertIn("<img src=x onerror=1>", r["texto"])

    def test_os_repositorios_ficam_num_details_fechado_com_a_chave(self):
        r = rode(self, "const li = linhaDeContaDoGithub(%s);\n"
                 "const d = acha(li, n => n.tag === 'details');\n"
                 "console.log(JSON.stringify({ aberto: d.open, resumo: acha(d, n => n.tag === 'summary').textContent,"
                 " chaves: achaTodos(d, n => n.tag === 'input').map(i => i.attrs['aria-label']) }));" % CONTA)
        self.assertFalse(r["aberto"])
        self.assertEqual(r["resumo"], "Ver o repositório")
        self.assertEqual(r["chaves"], ["Mostrar no painel: loja-da-ana"])

    def test_dois_ou_mais_dizem_quantos(self):
        c = CONTA.replace("repositorios: [", "repositorios: [{ projeto: 'b', slug: 'x/b', medido: false, oculto: true }, ")
        r = rode(self, "const li = linhaDeContaDoGithub(%s);\n"
                 "console.log(JSON.stringify({ t: acha(li, n => n.tag === 'summary').textContent, "
                 "texto: li.textContent }));" % c)
        self.assertEqual(r["t"], "Ver os 2 repositórios")
        self.assertIn("ainda não medido", r["texto"])


class OCartaoNaoMenteSobreOEstado(unittest.TestCase):
    def cartao(self, preparo):
        return rode(self, preparo + "\nconst c = cartaoDoGithub();\n"
                    "console.log(JSON.stringify({ texto: c.textContent, "
                    "botoes: achaTodos(c, n => n.tag === 'button').map(b => [b.textContent, b.disabled]) }));")

    def test_nao_leu_diz_que_nao_olhou_e_nao_diz_nenhuma_conta(self):
        r = self.cartao("")
        self.assertIn("Isso não quer dizer que ela não está conectada — quer dizer que não olhei.", r["texto"])
        self.assertNotIn("Nenhuma conta do GitHub ligada", r["texto"])
        self.assertIn("não deu para conferir", r["texto"])

    def test_sem_conta_diz_o_que_ela_traria_e_o_botao_e_o_primeiro_passo(self):
        r = self.cartao("GITHUB = { instalacoes: [], da_para_instalar: true }; GITHUB_LIDO_EM = ha(1);")
        self.assertIn("Nenhuma conta do GitHub ligada ainda.", r["texto"])
        self.assertIn("não conectado", r["texto"])
        self.assertEqual(r["botoes"], [["Conectar conta do GitHub", False]])

    def test_com_contas_o_botao_vira_conectar_outra(self):
        r = self.cartao("GITHUB = { instalacoes: [%s, %s], da_para_instalar: true }; GITHUB_LIDO_EM = ha(1);"
                        % (CONTA, CONTA.replace("loja-da-ana", "clinica-agenda-org")))
        self.assertIn("Contas ligadas: 2.", r["texto"])
        self.assertEqual(r["botoes"][0], ["Conectar outra conta do GitHub", False])
        self.assertIn("clinica-agenda-org", r["texto"])
        self.assertIn("loja-da-ana", r["texto"])    # nenhuma esconde a outra

    def test_aplicativo_nao_registrado_desliga_o_botao_e_diz_por_que(self):
        r = self.cartao("GITHUB = { instalacoes: [], da_para_instalar: false }; GITHUB_LIDO_EM = ha(1);")
        self.assertEqual(r["botoes"], [["Conectar conta do GitHub", True]])
        self.assertIn("o aplicativo do GitHub ainda não foi registrado neste servidor", r["texto"])

    def test_voltou_sem_confirmar_nao_e_erro(self):
        r = self.cartao("GITHUB = { instalacoes: [], da_para_instalar: true }; GITHUB_LIDO_EM = ha(1);"
                        "location.search = '?github=nao-deu';")
        self.assertIn("Não deu para confirmar a conta.", r["texto"])
        self.assertIn("O DERVS só liga a conta depois que o GitHub confirma.", r["texto"])
        self.assertIn("não deu para conferir", r["texto"])

    def test_nao_existe_botao_de_procurar_minhas_contas(self):
        r = self.cartao("GITHUB = { instalacoes: [], da_para_instalar: true }; GITHUB_LIDO_EM = ha(1);")
        for b in r["botoes"]:
            self.assertNotIn("Procurar", b[0])
        self.assertNotIn("Procurar minhas contas", JS)

    def test_tentar_de_novo_so_existe_no_estado_de_erro(self):
        base = "GITHUB = { instalacoes: [], da_para_instalar: true }; GITHUB_LIDO_EM = ha(1);"
        normal = self.cartao(base)
        self.assertNotIn("Tentar de novo", [b[0] for b in normal["botoes"]])
        erro = self.cartao(base + "GITHUB_PROCURA = { fase: 'erro', achou: '' };")
        self.assertIn(["Tentar de novo", False], erro["botoes"])
        self.assertIn("Não consegui procurar suas contas agora. Isso não quer dizer que não há — "
                      "quer dizer que não olhei.", erro["texto"])
        self.assertIn("não deu para conferir", erro["texto"])

    def test_procurando_e_achou_falam_numa_regiao_viva(self):
        base = "GITHUB = { instalacoes: [], da_para_instalar: true }; GITHUB_LIDO_EM = ha(1);"
        r = rode(self, base + "GITHUB_PROCURA = { fase: 'procurando', achou: '' };\n"
                 "const a = cartaoDoGithub();\n"
                 "GITHUB_PROCURA = { fase: '', achou: 'Achei e liguei a conta loja-da-ana.' };\n"
                 "const b = cartaoDoGithub();\n"
                 "const viva = (c) => acha(c, n => n.attrs['aria-live'] === 'polite');\n"
                 "console.log(JSON.stringify({ a: viva(a).textContent, b: viva(b).textContent }));")
        self.assertEqual(r["a"], "Procurando suas contas no GitHub…")
        self.assertEqual(r["b"], "Achei e liguei a conta loja-da-ana.")

    def test_procura_que_nao_achou_nada_fica_em_silencio(self):
        r = rode(self, "GITHUB = { instalacoes: [], da_para_instalar: true }; GITHUB_LIDO_EM = ha(1);\n"
                 "const c = cartaoDoGithub();\n"
                 "console.log(JSON.stringify({ viva: acha(c, n => n.attrs['aria-live'] === 'polite').textContent }));")
        self.assertEqual(r["viva"], "")

    def test_como_desligar_so_aparece_com_conta_e_manda_para_o_github(self):
        sem = self.cartao("GITHUB = { instalacoes: [], da_para_instalar: true }; GITHUB_LIDO_EM = ha(1);")
        com = self.cartao("GITHUB = { instalacoes: [%s], da_para_instalar: true }; GITHUB_LIDO_EM = ha(1);" % CONTA)
        self.assertNotIn("Para desligar uma conta", sem["texto"])
        self.assertIn("Para desligar uma conta, remova o aplicativo no próprio GitHub", com["texto"])


class AProcuraAutomaticaEUmaPorCarga(unittest.TestCase):
    def test_nao_procura_antes_de_saber_se_o_aplicativo_existe(self):
        r = rode(self, "procurarContasUmaVez(); GITHUB = { da_para_instalar: false }; procurarContasUmaVez();\n"
                 "console.log(JSON.stringify({ n: procurou.length }));")
        self.assertEqual(r["n"], 0)

    def test_chamada_varias_vezes_procura_uma_so(self):
        r = rode(self, "GITHUB = { instalacoes: [], da_para_instalar: true };\n"
                 "procurarContasUmaVez(); procurarContasUmaVez(); procurarContasUmaVez();\n"
                 "await new Promise(f => setImmediate(f));\n"
                 "console.log(JSON.stringify({ n: procurou.length, urls: procurou }));",
                 "[resposta(200, {ok: true, ligadas: 0})]")
        self.assertEqual(r["n"], 1)
        self.assertEqual(r["urls"], ["/api/github/procurar"])

    def test_429_fica_calado(self):
        r = rode(self, "GITHUB = { instalacoes: [], da_para_instalar: true };\n"
                 "await procurarContasDoGithub();\n"
                 "console.log(JSON.stringify({ procura: GITHUB_PROCURA }));",
                 "[resposta(429, {erro: 'nao deu'})]")
        self.assertEqual(r["procura"], {"fase": "", "achou": ""})

    def test_falha_do_servidor_ou_do_github_vira_o_estado_de_erro(self):
        for resp in ("resposta(500, {})", "resposta(200, {ok: false})"):
            with self.subTest(resp=resp):
                r = rode(self, "GITHUB = { instalacoes: [], da_para_instalar: true };\n"
                         "await procurarContasDoGithub();\n"
                         "console.log(JSON.stringify({ procura: GITHUB_PROCURA }));", "[%s]" % resp)
                self.assertEqual(r["procura"]["fase"], "erro")

    def test_pagina_velha_nao_repete_o_erro_no_cartao(self):
        r = rode(self, "GITHUB = { instalacoes: [], da_para_instalar: true }; PAGINA_VELHA = true;\n"
                 "await procurarContasDoGithub();\n"
                 "console.log(JSON.stringify({ procura: GITHUB_PROCURA }));",
                 "[resposta(403, {motivo: 'pagina_velha'})]")
        self.assertEqual(r["procura"]["fase"], "")

    def test_conta_nova_e_anunciada_pelo_nome(self):
        r = rode(self, "GITHUB = { instalacoes: [{ conta_login: 'a' }], da_para_instalar: true };\n"
                 "NOVO_GITHUB = { instalacoes: [{ conta_login: 'a' }, { conta_login: 'loja-da-ana' }], da_para_instalar: true };\n"
                 "await procurarContasDoGithub();\n"
                 "console.log(JSON.stringify({ procura: GITHUB_PROCURA }));",
                 "[resposta(200, {ok: true, ligadas: 1})]")
        self.assertEqual(r["procura"]["achou"], "Achei e liguei a conta loja-da-ana.")

    def test_a_procura_vai_pela_funcao_que_leva_o_token(self):
        corpo = funcao("procurarContasDoGithub")
        self.assertIn('escrever("/api/github/procurar")', corpo)
        self.assertNotRegex(corpo, r'fetch\(')


class OTextoDoCartaoDoGithubNaoTemJargaoNemHtml(unittest.TestCase):
    def codigo(self):
        sem = re.sub(r"/\*.*?\*/", "", "".join(funcao(n) for n in FUNCOES), flags=re.S)
        return re.sub(r"(?m)^\s*//[^\n]*$", "", sem)

    def test_nada_de_innerhtml(self):
        for proibido in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write"):
            with self.subTest(proibido=proibido):
                self.assertNotIn(proibido, self.codigo())

    def test_sem_conversao_de_numero_proibida(self):
        self.assertIsNone(re.search(r"Number\(|parseInt\(", self.codigo()))

    def test_o_cartao_le_a_lista_do_servidor_e_nao_so_um_numero(self):
        corpo = funcao("cartaoDoGithub")
        self.assertIn("GITHUB.instalacoes", corpo)
        corpo = funcao("linhaDeContaDoGithub")
        for campo in ("conta_login", "gerenciar_url", "conta_tipo", "medidos", "medido_em", "repositorios"):
            self.assertIn("c." + campo, corpo)

    def test_a_chave_do_repositorio_e_a_mesma_do_computador(self):
        self.assertIn("linhaComChave(", funcao("linhaDeRepositorio"))
        self.assertIn("linhaComChave(", funcao("linhaDeProjetoVisto"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
