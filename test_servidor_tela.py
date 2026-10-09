# -*- coding: utf-8 -*-
"""O cartao "Seus servidores" da tela Conectar e a linha "No ar" do projeto
(Conectar simples, entrega B, etapa E4).

O que a tela nao pode fazer, e nenhum teste de "o botao existe" pega:

  - dizer que o servidor esta bem com uma medicao velha (Lei 2: passados 180 s
    o estado e "sem dados", e a lista de sistemas some junto);
  - dizer "nenhum servidor" quando a leitura nao veio (o servidor antigo nao
    tem a chave `servidores_ligados`: isso e "nao olhei");
  - recriar o bloco da linha a cada repintura (a pessoa esta copiando);
  - esconder o veredito "nao sei" atras de um "igual" ou "diferente";
  - abrir o fluxo ao vivo com lista vazia ou fora das telas que o usam;
  - falar a lingua de quem construiu (contêiner, systemd, ssh...).

As funcoes de montagem sao EXECUTADAS em node com o DOM de mentira de
`test_conectar_tela.py`; sem node os casos de comportamento sao pulados e os de
texto e de fonte continuam.

    python test_servidor_tela.py
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

from test_conectar_tela import (HTML, PRELUDIO_DA_REDE, PRELUDIO_DE_TEMPO,
                                constante, funcao, fontes, jargao_em, roda,
                                sem_comentarios)

RAIZ = Path(__file__).resolve().parent
JS = (RAIZ / "assets" / "painel.js").read_text(encoding="utf-8")

# C10 do plano: os nomes que o teste de fio (etapa F) le.
FUNCOES = ("criar", "haQuanto", "hora", "marcaDaPorta", "botaoEmAcoes", "detalhes",
           "desdeQuando", "linhaDeSistema", "linhaDeServidorLigado",
           "listaDeServidoresLigados", "blocoDaLinhaDoAjudante", "cartaoDosServidores", "ligarUmServidor",
           "linhaDoNoAr", "linhasDoNoAr", "fecharFluxoDosServidores",
           "ligarFluxoDosServidores", "desligarServidor",
           # Entrega C (pedidos ao servidor): as que as de cima passaram a chamar.
           # Os casos delas moram em test_pedidos_tela.py.
           "linhaParaColar", "fraseDoPedido", "fraseDoMotivo", "fraseDoErroDePedido", "ultimoPedido",
           "pedidoEmAndamento", "estadoDoPedido", "botaoDePedido", "faixaDoPedido", "linkParaConta",
           "blocoDosPedidos", "base64urlParaBytes", "bytesParaBase64url", "pedirAoServidor",
           "fazerOPedido")

ESTADO_INICIAL = r"""
let ESTADO = null;
let PAGINA_VELHA = false;
let FLUXO_SERVIDORES = null;
globalThis.window = globalThis;
const faixas = [], recarregou = [];
function abrirFaixaPaginaVelha() { PAGINA_VELHA = true; faixas.push(1); }
async function carregar() { recarregou.push("carregar"); return true; }
function navegar() { recarregou.push("navegar"); }
function rota() { return { tela: "conectar" }; }
globalThis.EventSource = class {
  constructor(url) { this.url = url; this.ouvintes = {}; this.fechado = false; this.readyState = 0;
                     abertos.push(this); }
  addEventListener(t, f) { this.ouvintes[t] = f; }
  close() { this.fechado = true; this.readyState = 2; }
};
const abertos = [];
const timers = [];
globalThis.setTimeout = (f, ms) => { timers.push([f, ms]); return 1; };
const LINHA = { linha: "d=\"$(mktemp -d)\" && cd \"$d\" && curl -fsSL https://dervs.com.br/ajudante/servidor.py -o dervs-ajudante.py && "
                + "echo \"" + "a".repeat(64) + "  dervs-ajudante.py\" | sha256sum -c - && sudo python3 -I dervs-ajudante.py",
                sha256: "a".repeat(64), endereco: "https://dervs.com.br/ajudante/servidor.py" };
const buscas = [];
const confirmacoes = [], escritas = [], recados = [];
function confirmar(o, f) { confirmacoes.push(o); globalThis.aoSim = f; }
const escrever = async (u, c) => { escritas.push([u, c]); return RESPOSTAS.shift(); };
function recado(texto, ruim) { recados.push([texto, !!ruim]); }
"""


def rode(caso, script, respostas="[]"):
    return roda(caso, [PRELUDIO_DA_REDE, PRELUDIO_DE_TEMPO, ESTADO_INICIAL]
                + fontes(*FUNCOES, consts=("ESTADO_DA_PORTA", "DETALHES_ABERTOS",
                                           "LIGAR_SERVIDOR", "TELAS_DO_FLUXO_DOS_SERVIDORES")),
                "RESPOSTAS = " + respostas + ";\n"
                "globalThis.fetch = async (u) => { buscas.push(u); const r = RESPOSTAS.shift();"
                " if (r === 'rede') throw new Error('rede'); return r; };\n" + script)


VPS = ('{ maquina_id: 7, nome: "vps-ovh", estado: "medido", medido_em: ha(12), docker_mudo: false, '
       'sistemas: [ { nome: "dervs-app", estado: "running", saude: "healthy", desde: "2026-10-08T12:00:00+00:00", reinicios: 0 }, '
       '{ nome: "grimoire-web", estado: "running", saude: "", desde: "2026-10-01T09:30:00+00:00", reinicios: 0 }, '
       '{ nome: "ajudei-db", estado: "running", saude: "", desde: "2026-10-08T12:00:00+00:00", reinicios: 2 } ] }')


class OCartaoDizOEstadoDeCadaServidor(unittest.TestCase):
    def cartao(self, preparo):
        return rode(self, preparo + "\ncartaoDosServidores();\nconst c = $('#servidores-corpo');\n"
                    "console.log(JSON.stringify({ texto: c.textContent, "
                    "botoes: achaTodos(c, n => n.tag === 'button').map(b => b.textContent) }));")

    def test_vazio_diz_o_que_o_servidor_traria_e_o_botao_e_o_primeiro_passo(self):
        r = self.cartao("ESTADO = { servidores_ligados: [] };")
        self.assertIn("Ligue um servidor para ver, por dentro, o que está rodando nele e qual versão de "
                      "cada projeto está no ar. O ajudante só olha o que roda no servidor. Para ficar de "
                      "pé, a linha cria um usuário e um temporizador nele; você tira quando quiser.",
                      r["texto"])
        self.assertNotIn("não muda nada lá", r["texto"])
        self.assertEqual(r["botoes"], ["Ligar um servidor"])

    def test_sem_a_chave_e_nao_olhei_nunca_nenhum_servidor(self):
        for estado in ("ESTADO = null;", "ESTADO = { projetos: [] };", "ESTADO = { servidores_ligados: 'x' };"):
            with self.subTest(estado=estado):
                r = self.cartao(estado)
                self.assertIn("quer dizer que não olhei", r["texto"])
                self.assertNotIn("Ligue um servidor para ver", r["texto"])
                self.assertEqual(r["botoes"], [])

    def test_medido_mostra_nome_e_quando_e_os_sistemas(self):
        r = self.cartao("ESTADO = { servidores_ligados: [%s] };" % VPS)
        self.assertIn("vps-ovh", r["texto"])
        self.assertIn("medido há 12 segundos", r["texto"])
        self.assertIn("Sistemas rodando neste servidor", r["texto"])
        for nome in ("dervs-app", "grimoire-web", "ajudei-db"):
            self.assertIn(nome, r["texto"])
        self.assertNotIn("Sem dados", r["texto"])

    def test_passados_os_180_segundos_diz_sem_dados_e_nao_lista_sistemas(self):
        velho = VPS.replace('estado: "medido"', 'estado: "sem_dados"').replace("ha(12)", "ha(240)")
        r = self.cartao("ESTADO = { servidores_ligados: [%s] };" % velho)
        self.assertIn("Sem dados há 4 minutos — o servidor parou de contar.", r["texto"])
        self.assertNotIn("medido há", r["texto"])
        self.assertNotIn("dervs-app", r["texto"])           # nada velho com cara de atual
        self.assertNotIn("de pé", r["texto"])

    def test_pareado_e_ainda_sem_medicao_nao_diz_zero_sistemas(self):
        s = '{ maquina_id: 7, nome: "vps-ovh", estado: "sem_dados", medido_em: null, docker_mudo: null, sistemas: [] }'
        r = self.cartao("ESTADO = { servidores_ligados: [%s] };" % s)
        self.assertIn("vps-ovh", r["texto"])
        self.assertIn("ainda não contou nada", r["texto"])
        self.assertNotIn("Nenhum sistema", r["texto"])

    def test_sem_docker_diz_que_nao_viu_e_nao_diz_nenhum_sistema(self):
        mudo = VPS.replace("docker_mudo: false", "docker_mudo: true").replace("sistemas: [", "sistemas: [], x: [")
        r = self.cartao("ESTADO = { servidores_ligados: [%s] };" % mudo)
        self.assertIn("Não consegui ver os sistemas deste servidor.", r["texto"])
        self.assertNotIn("Nenhum sistema", r["texto"])
        self.assertNotIn("Sistemas rodando", r["texto"])

    def test_medido_sem_nenhum_sistema_diz_isso(self):
        vazio = VPS.replace("sistemas: [", "sistemas: [], x: [")
        r = self.cartao("ESTADO = { servidores_ligados: [%s] };" % vazio)
        self.assertIn("Nenhum sistema rodando neste servidor agora.", r["texto"])

    def test_com_servidor_o_botao_vira_ligar_outro(self):
        r = self.cartao("ESTADO = { servidores_ligados: [%s] };" % VPS)
        self.assertEqual(r["botoes"], ["Desligar este servidor", "Ligar outro servidor"])

    def test_o_nome_vem_de_fora_e_entra_como_texto(self):
        r = self.cartao("ESTADO = { servidores_ligados: [%s] };"
                        % VPS.replace('"vps-ovh"', '"<img src=x onerror=1>"'))
        self.assertIn("<img src=x onerror=1>", r["texto"])


class DesligarUmServidor(unittest.TestCase):
    """S1: sem este botao, o token de um servidor ligado nao tinha como morrer."""

    def botoes(self, servidor):
        r = rode(self, "ESTADO = { servidores_ligados: [%s] };\ncartaoDosServidores();\n"
                 "console.log(JSON.stringify({ b: achaTodos($('#servidores-corpo'), n => n.tag === 'button')"
                 ".map(b => b.textContent) }));" % servidor)
        return r["b"]

    def test_todo_servidor_tem_o_botao_medido_sem_dados_e_mudo(self):
        velho = VPS.replace('estado: "medido"', 'estado: "sem_dados"')
        nunca = '{ maquina_id: 8, nome: "vps-2", estado: "sem_dados", medido_em: null, docker_mudo: null, sistemas: [] }'
        mudo = VPS.replace("docker_mudo: false", "docker_mudo: true")
        for s in (VPS, velho, nunca, mudo):
            with self.subTest(s=s[:60]):
                self.assertEqual(1, self.botoes(s).count("Desligar este servidor"))

    def clicar(self, respostas):
        return rode(self, "ESTADO = { servidores_ligados: [%s] };\ncartaoDosServidores();\n"
                    "acha($('#servidores-corpo'), n => n.tag === 'button' && "
                    "n.textContent === 'Desligar este servidor').clicar();\n"
                    "const antes = escritas.length;\nawait aoSim();\n"
                    "console.log(JSON.stringify({ antes, escritas, recados, recarregou, "
                    "titulo: confirmacoes[0].titulo, texto: confirmacoes[0].texto, "
                    "sim: confirmacoes[0].sim, nao: confirmacoes[0].nao }));" % VPS, respostas)

    def test_pergunta_antes_e_so_entao_tira_pela_rota_de_maquina(self):
        r = self.clicar("[resposta(200, {ok: true})]")
        self.assertEqual(r["antes"], 0)                     # nada sai sem a confirmacao
        self.assertEqual(r["titulo"], "Desligar “vps-ovh”?")
        self.assertEqual((r["sim"], r["nao"]), ("Desligar", "Manter ligado"))
        self.assertIn("Para tirar o ajudante de dentro do servidor", r["texto"])
        self.assertEqual(r["escritas"], [["/api/maquinas/remover", {"id": 7}]])
        self.assertEqual(r["recarregou"], ["carregar"])
        self.assertFalse(r["recados"][0][1])

    def test_falha_diz_que_nao_desligou(self):
        r = self.clicar("[resposta(404, {erro: 'nao existe'})]")
        self.assertEqual(r["recados"], [["não conseguimos desligar o servidor. Tente de novo.", True]])
        self.assertEqual(r["recarregou"], [])


class UmSistemaDizOQueEstaFazendo(unittest.TestCase):
    def sistema(self, campos):
        return rode(self, "const li = linhaDeSistema({ nome: 'x-app', desde: '2026-10-08T12:00:00+00:00', "
                    "reinicios: 0, saude: '', estado: 'running', %s });\n"
                    "console.log(JSON.stringify({ texto: li.textContent }));" % campos)["texto"]

    def test_os_quatro_estados_em_palavras(self):
        self.assertIn("de pé", self.sistema(""))
        self.assertIn("com problema", self.sistema("saude: 'unhealthy'"))
        self.assertIn("reiniciando", self.sistema("estado: 'restarting'"))
        for parado in ("exited", "dead", "paused", "created", "removing"):
            with self.subTest(estado=parado):
                self.assertIn("parado", self.sistema("estado: '%s'" % parado))

    def test_saude_ruim_de_quem_nao_esta_rodando_nao_vira_com_problema(self):
        t = self.sistema("estado: 'exited', saude: 'unhealthy'")
        self.assertIn("parado", t)
        self.assertNotIn("com problema", t)

    def test_reiniciou_so_com_mais_de_zero_e_no_singular_quando_um(self):
        self.assertNotIn("reiniciou", self.sistema("reinicios: 0"))
        self.assertNotIn("reiniciou", self.sistema("reinicios: null"))
        self.assertIn("reiniciou 2 vezes", self.sistema("reinicios: 2"))
        self.assertIn("reiniciou 1 vez", self.sistema("reinicios: 1"))
        self.assertNotIn("1 vezes", self.sistema("reinicios: 1"))

    def test_desde_quando_aparece_e_data_torta_some(self):
        self.assertRegex(self.sistema(""), r"desde \d{2}/\d{2}/\d{4}")
        self.assertNotIn("desde", self.sistema("desde: ''"))
        self.assertNotIn("desde", self.sistema("desde: 'ontem'"))
        self.assertNotIn("Invalid", self.sistema("desde: 'ontem'"))


class OFluxoDaLinhaParaColar(unittest.TestCase):
    def test_clicar_busca_a_linha_e_diz_preparando_enquanto_espera(self):
        r = rode(self, "ESTADO = { servidores_ligados: [] };\n"
                 "let solta; RESPOSTAS.push(new Promise(f => { solta = f; }));\n"
                 "cartaoDosServidores();\n"
                 "const b = acha($('#servidores-corpo'), n => n.tag === 'button');\n"
                 "const p = b.clicar();\n"
                 "const durante = $('#servidores-corpo').textContent;\n"
                 "solta(resposta(200, LINHA)); await p;\n"
                 "console.log(JSON.stringify({ durante, buscas }));")
        self.assertIn("Preparando a linha…", r["durante"])
        self.assertEqual(r["buscas"], ["/api/ajudante/linha"])

    def ligando(self, depois=""):
        return rode(self, "ESTADO = { servidores_ligados: [] };\ncartaoDosServidores();\n"
                    "await acha($('#servidores-corpo'), n => n.tag === 'button').clicar();\n"
                    "const c = $('#servidores-corpo');\n" + depois +
                    "\nconsole.log(JSON.stringify({ texto: c.textContent, "
                    "ordem: c.filhos.length && todos(c).filter(n => n.tag === 'button' || n.tag === 'pre')"
                    ".map(n => n.tag === 'pre' ? 'pre' : n.textContent), "
                    "pre: (acha(c, n => n.tag === 'pre') || {}).textContent, "
                    "passos: achaTodos(c, n => n.tag === 'li').map(n => n.textContent), "
                    "det: achaTodos(c, n => n.tag === 'details').map(n => [n.open, "
                    "acha(n, m => m.tag === 'summary').textContent]), extra: typeof extra === 'undefined' ? null : extra }));",
                    "[resposta(200, LINHA)]")

    def test_mostra_a_linha_com_copiar_acima_e_o_roteiro_de_quatro_passos(self):
        r = self.ligando()
        self.assertTrue(r["pre"].startswith('d="$(mktemp -d)" && cd "$d" && curl -fsSL https://dervs.com.br/ajudante/servidor.py'))
        self.assertEqual(r["ordem"][0], "Copiar")                       # acima do bloco
        self.assertEqual(r["ordem"][1], "pre")
        self.assertEqual(r["passos"], [
            "Abra o terminal do servidor (o PuTTY ou o terminal do DERVS-VOZ) e entre como de costume.",
            "Cole a linha de cima e aperte Enter. Ela pode pedir a sua senha do servidor.",
            "Vai aparecer um código de 8 letras e números, como K7M4-2QXP (mais um endereço). Abra "
            "esta mesma tela no seu computador e clique em Autorizar (digite o código só se a tela "
            "pedir).",
            "Pronto: em até um minuto o servidor aparece aqui."])
        self.assertIn("Se der errado", r["texto"])
        self.assertIn("O servidor não tem Python. Cole sudo apt install -y python3 e rode a linha de novo.",
                      r["texto"])
        self.assertIn("Não rode nada: recarregue esta página e copie a linha de novo.", r["texto"])
        for frase in ("Apareceu Preciso de poder de administrador? Rode de novo com sudo na frente.",
                      "Apareceu Nao achei o Docker ou Este servidor nao usa o gerenciador de servicos? "
                      "Esta máquina não serve para o ajudante; nada foi alterado.",
                      "Apareceu O painel nao liberou este servidor? O pedido venceu. Rode a linha de "
                      "novo e autorize em poucos minutos."):
            self.assertIn(frase, r["texto"])

    def test_as_frases_de_erro_sao_as_que_o_ajudante_imprime(self):
        """A tela cita o terminal: cada frase citada tem de existir no ajudante."""
        ajudante = (RAIZ / "ajudante_servidor.py").read_text(encoding="ascii")
        codigos = re.findall(r'criar\("code", "", "([^"]+)"\)', funcao("blocoDaLinhaDoAjudante"))
        citadas = [c for c in codigos if c[0].isupper() and " " in c]
        self.assertEqual(4, len(citadas), codigos)
        for frase in citadas:
            with self.subTest(frase=frase):
                self.assertIn(frase, ajudante)

    def test_o_passo_do_codigo_bate_com_o_que_o_ajudante_mostra(self):
        ajudante = (RAIZ / "ajudante_servidor.py").read_text(encoding="ascii")
        self.assertIn('saida("Codigo: "', ajudante)
        self.assertIn('/#/conectar?autorizar=', ajudante)
        self.assertIn("digitando o codigo se o painel pedir", ajudante)

    def test_o_que_isso_faz_vem_fechado_e_diz_como_tirar(self):
        r = self.ligando()
        self.assertEqual(r["det"], [[False, "O que isso faz?"]])
        self.assertIn("Ele nunca lê senhas, arquivos de configuração nem os dados dos sistemas, não recebe "
                      "ordens e não se atualiza sozinho.", r["texto"])
        self.assertIn("sudo python3 /opt/dervs-ajudante/dervs-ajudante.py remover", r["texto"])
        self.assertIn("e clique em Desligar este servidor", r["texto"])
        self.assertIn("Código de conferência do arquivo (SHA-256): " + "a" * 64 + ". A linha já compara "
                      "o arquivo com este código. Ele prova que chegou inteiro, não de quem veio.",
                      r["texto"])
        self.assertNotIn("impressão digital", r["texto"])

    def test_repintar_nao_recria_o_bloco_da_linha(self):
        r = self.ligando("const antes = acha(c, n => n.tag === 'pre');\ncartaoDosServidores();\n"
                         "var extra = acha($('#servidores-corpo'), n => n.tag === 'pre') === antes;")
        self.assertTrue(r["extra"])

    def test_copiar_usa_a_area_de_transferencia_e_avisa(self):
        r = self.ligando("var extra0 = acha(c, n => n.tag === 'button' && n.textContent === 'Copiar')"
                         ".getAttribute('aria-label');\nconst copiados = [];\n"
                         "Object.defineProperty(globalThis, 'navigator', { configurable: true, "
                         "value: { clipboard: { writeText: async (t) => { copiados.push(t); } } } });\n"
                         "await acha(c, n => n.tag === 'button' && n.textContent === 'Copiar').clicar();\n"
                         "var extra = [copiados.length, copiados[0] === LINHA.linha, c.textContent, extra0];")
        self.assertEqual(r["extra"][:2], [1, True])
        self.assertEqual(r["extra"][3], "Copiar a linha para colar no servidor")
        self.assertIn("Copiado", r["extra"][2])

    def test_copiar_que_falha_manda_copiar_a_mao(self):
        r = self.ligando("Object.defineProperty(globalThis, 'navigator', { configurable: true, "
                         "value: { clipboard: { writeText: async () => { throw new Error('x'); } } } });\n"
                         "await acha(c, n => n.tag === 'button' && n.textContent === 'Copiar').clicar();\n"
                         "var extra = c.textContent;")
        self.assertIn("Não deu para copiar. Selecione a linha e copie à mão.", r["extra"])

    def test_erro_do_servidor_ou_da_rede_vira_frase_nossa_com_tentar_de_novo(self):
        for resp in ("resposta(503, {erro: 'x'})", "'rede'", "resposta(500, {})", "resposta(200, {sem: 1})"):
            with self.subTest(resp=resp):
                r = rode(self, "ESTADO = { servidores_ligados: [] };\ncartaoDosServidores();\n"
                         "await acha($('#servidores-corpo'), n => n.tag === 'button').clicar();\n"
                         "const c = $('#servidores-corpo');\n"
                         "console.log(JSON.stringify({ texto: c.textContent, "
                         "botoes: achaTodos(c, n => n.tag === 'button').map(b => b.textContent) }));",
                         "[%s]" % resp)
                self.assertIn("Não consegui preparar a linha agora.", r["texto"])
                self.assertEqual(r["botoes"], ["Tentar de novo"])
                self.assertNotIn("curl", r["texto"])

    def test_403_de_pagina_velha_abre_a_faixa_central_e_nao_repete_o_erro(self):
        r = rode(self, "ESTADO = { servidores_ligados: [] };\ncartaoDosServidores();\n"
                 "await acha($('#servidores-corpo'), n => n.tag === 'button').clicar();\n"
                 "console.log(JSON.stringify({ faixas: faixas.length, texto: $('#servidores-corpo').textContent }));",
                 "[resposta(403, {erro: 'entre de novo'})]")
        self.assertEqual(r["faixas"], 1)
        self.assertNotIn("Não consegui preparar", r["texto"])

    def test_quando_o_servidor_aparece_na_lista_o_bloco_da_linha_sai(self):
        r = self.ligando("ESTADO = { servidores_ligados: [%s] };\ncartaoDosServidores();\n"
                         "var extra = c.textContent;" % VPS)
        self.assertNotIn("curl", r["extra"])
        self.assertIn("vps-ovh", r["extra"])

    def test_dois_cliques_seguidos_buscam_uma_vez(self):
        r = rode(self, "ESTADO = { servidores_ligados: [] };\n"
                 "let solta; RESPOSTAS.push(new Promise(f => { solta = f; }));\n"
                 "cartaoDosServidores();\n"
                 "const b = acha($('#servidores-corpo'), n => n.tag === 'button');\n"
                 "const p1 = b.clicar(); const p2 = ligarUmServidor();\n"
                 "solta(resposta(200, LINHA)); await p1; await p2;\n"
                 "console.log(JSON.stringify({ n: buscas.length }));")
        self.assertEqual(r["n"], 1)


class OVereditoNoCartaoDoProjeto(unittest.TestCase):
    def linha(self, n):
        return rode(self, "const l = linhaDoNoAr(%s);\nconsole.log(JSON.stringify({ texto: l.textContent }));" % n)["texto"]

    BASE = ('{ servidor: "vps-ovh", estado: "medido", medido_em: ha(30), sha: "96eb3fc", '
            'publicado_em: "2026-09-29T15:15:00+00:00", veredito: "%s", atras: %s }')

    def test_os_quatro_vereditos_com_as_palavras_do_design(self):
        casos = [("igual", "null", "igual ao GitHub"),
                 ("atras", "3", "3 mudanças atrás do GitHub"),
                 ("atras", "1", "1 mudança atrás do GitHub"),
                 ("diferente", "null", "diferente do GitHub"),
                 ("nao_sei", "null", "não sei qual versão está no ar")]
        for veredito, atras, frase in casos:
            with self.subTest(veredito=veredito, atras=atras):
                t = self.linha(self.BASE % (veredito, atras))
                self.assertIn("No ar em vps-ovh: versão de ", t)
                self.assertRegex(t, r"versão de \d{2}/\d{2}/\d{4}")
                self.assertIn(frase, t)

    def test_veredito_desconhecido_vira_nao_sei_nunca_um_sim(self):
        t = self.linha(self.BASE % ("talvez", "null"))
        self.assertIn("não sei qual versão está no ar", t)
        self.assertNotIn("igual", t)

    def test_servidor_sem_dados_nunca_afirma_igual(self):
        t = self.linha((self.BASE % ("igual", "null")).replace('"medido"', '"sem_dados"'))
        self.assertIn("não sei qual versão está no ar", t)
        self.assertNotIn("igual ao GitHub", t)

    def test_sem_data_de_publicacao_so_o_servidor_e_o_veredito(self):
        t = self.linha((self.BASE % ("igual", "null")).replace('publicado_em: "2026-09-29T15:15:00+00:00"',
                                                                  "publicado_em: null"))
        self.assertIn("No ar em vps-ovh: igual ao GitHub", t)
        self.assertNotIn("versão de", t)

    def test_a_lista_vazia_nao_pinta_linha_nenhuma(self):
        r = rode(self, "console.log(JSON.stringify({ a: linhasDoNoAr({ no_ar: [] }).length, "
                 "b: linhasDoNoAr({}).length, c: linhasDoNoAr({ no_ar: null }).length, "
                 "d: linhasDoNoAr({ no_ar: [%s, %s] }).length }));" % ((self.BASE % ("igual", "null"),) * 2))
        self.assertEqual(r, {"a": 0, "b": 0, "c": 0, "d": 2})

    def test_o_nome_do_servidor_e_texto(self):
        t = self.linha((self.BASE % ("igual", "null")).replace('"vps-ovh"', '"<b>x</b>"'))
        self.assertIn("<b>x</b>", t)

    def test_painel_e_detalhe_chamam_a_mesma_funcao(self):
        self.assertIn("linhasDoNoAr(p)", funcao("pintarPainel"))
        self.assertIn("linhasDoNoAr(p)", funcao("pintarProjeto"))


class AutorizarUmServidor(unittest.TestCase):
    FONTES = ("criar", "botaoEmAcoes", "prazoEmPalavras", "codigoDeAutorizar", "pintarAutorizar",
              "autorizarPedido", "fecharAutorizar", "olharOPedido")

    def rode(self, script, respostas="[]"):
        prelude = (r"""
const AUTORIZAR = { codigo: '', dados: null, fase: '', prazo: null, fim: 0, botao: null, focou: false, digitado: '' };
let PAGINA_VELHA = false;
globalThis.esperas = []; globalThis.escritas = []; globalThis.cartoes = [];
function esperarMaquinaNova(onde, min, modo) { esperas.push(1); }
function cartaoDosServidores() { cartoes.push("cartao"); }
function ligarFluxoDosServidores() { cartoes.push("fluxo"); }
let ESTADO = null;
async function carregar() { cartoes.push("carregar"); return true; }
const escrever = async (url, corpo) => { escritas.push([url, corpo]); return RESPOSTAS.shift(); };
""")
        return roda(self, [PRELUDIO_DA_REDE, prelude] + [funcao(n) for n in self.FONTES],
                    "RESPOSTAS = " + respostas + ";\n" + script)

    PEDIDO = '{ codigo: "K7M4-2QXP", maquina: "vps-ovh", minutos: 8, estado: "esperando", tipo: "servidor", mesma_rede: false }'

    def test_titulo_frase_e_botao_de_servidor(self):
        r = self.rode("pintarAutorizar(%s);\nconst b = $('#conectar-autorizar');\n"
                      "console.log(JSON.stringify({ texto: b.textContent, "
                      "botoes: achaTodos(b, n => n.tag === 'button').map(x => x.textContent) }));" % self.PEDIDO)
        self.assertIn("Autorizar este servidor?", r["texto"])
        self.assertIn("Um servidor chamado vps-ovh quer se ligar à sua conta. Ele só vai olhar, mas "
                      "precisa de poder de administrador no servidor.", r["texto"])
        self.assertEqual(r["botoes"], ["Autorizar este servidor"])
        self.assertNotIn("computador", r["texto"])

    def test_computador_continua_igual(self):
        r = self.rode("pintarAutorizar(%s);\nconsole.log(JSON.stringify({ texto: $('#conectar-autorizar').textContent }));"
                      % self.PEDIDO.replace('tipo: "servidor"', 'tipo: "computador"').replace("mesma_rede: false", "mesma_rede: true"))
        self.assertIn("Autorizar este computador?", r["texto"])
        self.assertIn("O computador vps-ovh pediu para se ligar ao seu painel", r["texto"])
        r = self.rode("pintarAutorizar({ codigo: 'K7M4-2QXP', maquina: 'PC', minutos: 8, estado: 'esperando' });\n"
                      "console.log(JSON.stringify({ texto: $('#conectar-autorizar').textContent }));")
        self.assertIn("Autorizar este computador?", r["texto"])           # pedido sem `tipo` (servidor antigo)

    def test_sucesso_diz_onde_o_servidor_vai_aparecer_e_recarrega_o_cartao(self):
        r = self.rode("AUTORIZAR.dados = %s; AUTORIZAR.codigo = 'K7M4-2QXP';\n"
                      "await autorizarPedido();\n"
                      "console.log(JSON.stringify({ texto: $('#conectar-autorizar').textContent, "
                      "esperas: esperas.length, cartoes, escritas }));" % self.PEDIDO,
                      "[resposta(200, {ok: true})]")
        self.assertIn("Autorizado. Em até um minuto o servidor aparece em Seus servidores.", r["texto"])
        self.assertEqual(r["esperas"], 0)                    # a espera e a do computador
        self.assertEqual(r["cartoes"], ["carregar", "cartao", "fluxo"])
        self.assertEqual(r["escritas"], [["/api/pedido/autorizar", {"codigo": "K7M4-2QXP"}]])


class OFluxoAoVivoDosServidores(unittest.TestCase):
    COM = "ESTADO = { servidores_ligados: [%s] };\n" % VPS

    def test_abre_so_com_servidor_ligado_e_sem_id(self):
        r = rode(self, "ESTADO = { servidores_ligados: [] };\nligarFluxoDosServidores('conectar');\n"
                 "const vazio = abertos.length;\n" + self.COM + "ligarFluxoDosServidores('conectar');\n"
                 "ligarFluxoDosServidores('painel');\n"
                 "console.log(JSON.stringify({ vazio, urls: abertos.map(a => a.url) }));")
        self.assertEqual(r["vazio"], 0)
        self.assertEqual(r["urls"], ["/api/eventos"])          # um so, e sem `?id`

    def test_so_nas_telas_painel_projeto_e_conectar(self):
        r = rode(self, self.COM + "ligarFluxoDosServidores('trabalho');\nligarFluxoDosServidores('conta');\n"
                 "ligarFluxoDosServidores('alerta');\nconst fora = abertos.length;\n"
                 "ligarFluxoDosServidores('projeto');\n"
                 "console.log(JSON.stringify({ fora, dentro: abertos.length }));")
        self.assertEqual(r, {"fora": 0, "dentro": 1})

    def test_sair_da_tela_fecha(self):
        r = rode(self, self.COM + "ligarFluxoDosServidores('painel');\nligarFluxoDosServidores('trabalho');\n"
                 "console.log(JSON.stringify({ fechado: abertos[0].fechado, solto: FLUXO_SERVIDORES === null }));")
        self.assertEqual(r, {"fechado": True, "solto": True})

    def test_lista_que_esvazia_fecha(self):
        r = rode(self, self.COM + "ligarFluxoDosServidores('painel');\nESTADO = { servidores_ligados: [] };\n"
                 "ligarFluxoDosServidores('painel');\nconsole.log(JSON.stringify({ fechado: abertos[0].fechado }));")
        self.assertTrue(r["fechado"])

    def test_o_aviso_servidor_recarrega_e_repinta(self):
        r = rode(self, self.COM + "ligarFluxoDosServidores('painel');\n"
                 "await abertos[0].ouvintes.servidor({ data: '{\"medido_em\":\"x\"}' });\n"
                 "console.log(JSON.stringify({ recarregou }));")
        self.assertEqual(r["recarregou"], ["carregar", "navegar"])

    def test_fim_religa_em_meio_segundo(self):
        r = rode(self, self.COM + "ligarFluxoDosServidores('painel');\nabertos[0].ouvintes.fim();\n"
                 "const esperando = timers.map(t => t[1]);\ntimers[0][0]();\n"
                 "console.log(JSON.stringify({ esperando, fechado: abertos[0].fechado, n: abertos.length }));")
        self.assertEqual(r["esperando"], [500])
        self.assertTrue(r["fechado"])
        self.assertEqual(r["n"], 2)

    def test_fluxo_morto_de_vez_nao_trava_a_proxima_tentativa(self):
        r = rode(self, self.COM + "ligarFluxoDosServidores('painel');\nabertos[0].readyState = 2;\n"
                 "abertos[0].onerror();\nligarFluxoDosServidores('painel');\n"
                 "console.log(JSON.stringify({ n: abertos.length }));")
        self.assertEqual(r["n"], 2)

    def test_sem_eventsource_no_navegador_o_relogio_de_um_minuto_basta(self):
        r = rode(self, self.COM + "delete globalThis.EventSource;\nligarFluxoDosServidores('painel');\n"
                 "console.log(JSON.stringify({ n: abertos.length, solto: FLUXO_SERVIDORES === null }));")
        self.assertEqual(r, {"n": 0, "solto": True})

    def test_a_navegacao_pergunta_pelo_fluxo(self):
        self.assertIn("ligarFluxoDosServidores(tela)", funcao("navegar"))


class OTextoNaoTemJargaoNemHtml(unittest.TestCase):
    def codigo(self):
        return sem_comentarios("".join(funcao(n) for n in FUNCOES))

    def test_nada_de_innerhtml_nem_conversao_de_numero_proibida(self):
        for proibido in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "Number(",
                         "parseInt(", ".style", "style="):
            with self.subTest(proibido=proibido):
                self.assertNotIn(proibido, self.codigo())

    def test_as_funcoes_novas_estao_entre_os_marcadores_do_guarda_de_jargao(self):
        ini = JS.index("/* === CONECTAR: início === */")
        fim = JS.index("/* === CONECTAR: fim === */")
        for nome in ("cartaoDosServidores", "linhaDeServidorLigado", "linhaDeSistema",
                     "linhaDoNoAr", "blocoDaLinhaDoAjudante", "ligarFluxoDosServidores"):
            with self.subTest(funcao=nome):
                self.assertTrue(ini < JS.index("function %s(" % nome) < fim)

    def literais(self):
        return "\n".join(re.findall(r'"(?:[^"\\\n]|\\.)*"', self.codigo()))

    def test_jargao_ausente_do_texto_visivel(self):
        extra = (r"\bssh\b", r"systemd", r"cont[eê]iner", r"\bdocker\s+ps\b")
        texto = self.literais()
        self.assertGreater(len(texto), 2500)
        self.assertEqual(jargao_em(texto), [])
        for p in extra:
            with self.subTest(padrao=p):
                self.assertIsNone(re.search(p, texto, re.I))

    def test_a_palavra_certa_inserida_num_textcontent_seria_pega(self):
        """A guarda da guarda: sabotar o texto de verdade e exigir que acuse."""
        sabotado = JS.replace('"Preparando a linha…"', '"Preparando o contêiner…"', 1)
        self.assertNotEqual(sabotado, JS)
        trecho = "".join(re.search(r"^(?:async )?function %s\(.*?\n}\n" % n, sabotado, re.S | re.M).group(0)
                         for n in FUNCOES)
        literais = "\n".join(re.findall(r'"(?:[^"\\\n]|\\.)*"', sem_comentarios(trecho)))
        self.assertIsNotNone(re.search(r"cont[eê]iner", literais, re.I))
        self.assertIsNone(re.search(r"cont[eê]iner", self.literais(), re.I))

    def test_os_literais_que_o_teste_de_fio_procura(self):
        self.assertIn('fetch("/api/ajudante/linha"', JS)
        self.assertIn('new EventSource("/api/eventos")', JS)
        self.assertNotIn('new EventSource("/api/eventos?', JS.replace('"/api/eventos?id="', ""))
        self.assertIn('addEventListener("servidor"', JS)

    def test_cada_funcao_le_os_campos_do_contrato(self):
        esperado = {
            "cartaoDosServidores": ("servidores_ligados",),
            "linhaDeServidorLigado": ("maquina_id", "nome", "estado", "medido_em", "docker_mudo", "sistemas"),
            "linhaDeSistema": ("nome", "estado", "saude", "desde", "reinicios"),
            "linhaDoNoAr": ("servidor", "estado", "publicado_em", "veredito", "atras"),   # medido_em e sha: so no JSON
            "blocoDaLinhaDoAjudante": ("linha", "sha256"),
        }
        for nome, campos in esperado.items():
            corpo = funcao(nome)
            for campo in campos:
                with self.subTest(funcao=nome, campo=campo):
                    self.assertRegex(corpo, r"\.%s\b" % campo)

    def test_o_servidor_novo_nao_e_um_quinto_item_de_menu(self):
        self.assertEqual(len(re.findall(r'<a [^>]*data-tela="', HTML)), 4)


class OHtmlDoCartao(unittest.TestCase):
    def test_o_cartao_vem_depois_de_seus_sites_com_titulo_e_corpo_vivo(self):
        sites = HTML.index('id="cartao-sites"')
        cartao = HTML.index('id="cartao-servidores"')
        self.assertGreater(cartao, sites)
        trecho = HTML[cartao - 60:cartao + 700]
        self.assertIn('aria-labelledby="servidores-titulo"', trecho)
        self.assertIn('<h2 id="servidores-titulo">Seus servidores</h2>', trecho)
        # `aria-labelledby` so vale num elemento com papel: `div` puro nao tem.
        self.assertRegex(trecho, r'<div [^>]*id="cartao-servidores"[^>]*role="group"')
        # O corpo inteiro repinta de minuto em minuto: anunciado, falaria tudo
        # de novo. Quem fala e so o aviso de copia.
        corpo = re.search(r'<div [^>]*id="servidores-corpo"[^>]*>', trecho).group(0)
        self.assertNotIn("aria-live", corpo)
        self.assertNotIn("style=", trecho)

    def test_o_corpo_nao_traz_o_bloco_da_linha_no_html(self):
        cartao = HTML.index('id="cartao-servidores"')
        fim = HTML.index("</section>", cartao)
        self.assertNotIn("curl", HTML[cartao:fim])


if __name__ == "__main__":
    unittest.main(verbosity=2)
