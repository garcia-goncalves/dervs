# -*- coding: utf-8 -*-
"""Os pedidos ao servidor na tela Conectar (Conectar simples, entrega C, E3).

O dono pede "reiniciar este sistema" ou "voltar este projeto para a versao
anterior"; o servidor faz, e cada pedido so anda com a digital ou o PIN. O que a
tela nao pode fazer, e nenhum teste de "o botao existe" pega:

  - mostrar botao onde o servidor nao ofereceu (`reiniciavel` e `=== true`, nunca
    "nao e falso") nem no sistema que guarda dado de saude;
  - mandar o pedido ao DERVS antes do "Pode fazer", ou mandar `maquina_id` como
    texto (um `dataset`/`<select>` entrega texto, e o servidor exige inteiro);
  - dizer "feito" por falta de resposta: o servidor que nao pegou o pedido, ou
    pegou e nao contou, nunca vira sucesso (Lei 2);
  - tratar "cancelei a digital" como erro, ou erro como sucesso;
  - mostrar a linha com pedidos a quem nao tem chave de acesso;
  - falar a lingua de quem construiu (assinatura, docker, sudo, deploy...).

As funcoes de montagem sao EXECUTADAS em node com o DOM de mentira de
`test_conectar_tela.py` (o mesmo molde de `test_servidor_tela.py`); sem node os
casos de comportamento sao pulados e os de texto e de fonte continuam.

    python test_pedidos_tela.py
"""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from test_conectar_tela import funcao, jargao_em, sem_comentarios
from test_servidor_tela import rode

RAIZ = Path(__file__).resolve().parent
JS = (RAIZ / "assets" / "painel.js").read_text(encoding="utf-8")
CSS = (RAIZ / "assets" / "painel.css").read_text(encoding="utf-8")

# I6 do plano: os nomes que o teste de fio (etapa F) le.
FUNCOES_NOVAS = ("fraseDoPedido", "fraseDoMotivo", "fraseDoErroDePedido", "ultimoPedido",
                 "pedidoEmAndamento", "estadoDoPedido", "botaoDePedido", "faixaDoPedido",
                 "linkParaConta", "blocoDosPedidos", "base64urlParaBytes", "bytesParaBase64url",
                 "pedirAoServidor", "fazerOPedido", "linhaParaColar")

# ------------------------------------------------------------------ fixtures
# Os do design: vps-ovh com pedidos ligados, e vps-teste so olhando.
def sistema(nome, extra=""):
    return ('{ nome: "%s", estado: "running", saude: "", desde: "2026-10-08T12:00:00+00:00", '
            'reinicios: 0, %s }' % (nome, extra))


SISTEMAS = ", ".join([
    sistema("grimoire-web", "reiniciavel: true, bloqueado: false"),
    sistema("dervs-app", "reiniciavel: true, bloqueado: false"),
    sistema("grimoire-db", "reiniciavel: true, bloqueado: false"),
    sistema("ajudei-db", "reiniciavel: false, bloqueado: true"),
])

ORDENS = "{ chaves_ok: true, linha_velha: false, voltaveis: ['grimoire', 'dervs'], pedidos: [] }"


def servidor(ordens=ORDENS, estado="medido", sistemas=SISTEMAS, nome="vps-ovh"):
    # `maquina_id` como TEXTO, de proposito: e como ele chega de um `dataset`.
    return ('{ maquina_id: "7", nome: "%s", estado: "%s", medido_em: ha(12), docker_mudo: false, '
            'sistemas: [%s], ordens: %s }' % (nome, estado, sistemas, ordens))


def com_pedidos(*pedidos):
    return ORDENS.replace("pedidos: []", "pedidos: [%s]" % ", ".join(pedidos))


def pedido(tipo, alvo, estado, quando="ha(40)", codigo="null", motivo="null", numero="'4e1d'"):
    return ("{ numero: %s, tipo: '%s', alvo: '%s', estado: '%s', quando: %s, codigo: %s, motivo: %s }"
            % (numero, tipo, alvo, estado, quando, codigo, motivo))


AJUDAS = r"""
const botoesDe = (n) => achaTodos(n, x => x.tag === 'button');
const rotulos = (n) => botoesDe(n).map(b => b.textContent);
const acharBotao = (n, t) => acha(n, x => x.tag === 'button' && x.textContent === t);
const linhaDe = (c, classe, nome) => acha(c, x => x.tag === 'li' && x.className.split(' ').includes(classe)
  && x.filhos.length && x.filhos[0].textContent === nome);
"""


def vai(caso, srv, depois, respostas="[]"):
    """Pinta o cartao com `srv` e roda `depois`, que imprime o JSON do caso."""
    return rode(caso, AJUDAS + "ESTADO = { servidores_ligados: [%s] };\ncartaoDosServidores();\n"
                "const c = $('#servidores-corpo');\n" % srv + depois, respostas)


# ===================================================================== botoes
class OsBotoesSoExistemOndeOServidorOfereceu(unittest.TestCase):
    def test_reiniciar_so_onde_reiniciavel_e_verdadeiro(self):
        r = vai(self, servidor(), "console.log(JSON.stringify({ b: rotulos(c) }));")
        self.assertEqual(r["b"].count("Reiniciar"), 3)          # grimoire-web, dervs-app, grimoire-db
        self.assertEqual(r["b"].count("Voltar"), 2)             # grimoire, dervs
        self.assertIn("Desligar este servidor", r["b"])

    def test_o_sistema_de_saude_nao_tem_botao_e_diz_por_que(self):
        r = vai(self, servidor(), "const li = linhaDe(c, 'sistema-do-servidor', 'ajudei-db');\n"
                "console.log(JSON.stringify({ t: li.textContent, b: rotulos(li) }));")
        self.assertEqual(r["b"], [])
        self.assertIn("fica de fora: guarda dado de saúde", r["t"])

    def test_sem_o_campo_nao_ha_botao_nunca_pelo_nao_e_falso(self):
        """Sabotar `=== true` por `!== false` deixa o servidor antigo com botao."""
        sem_campo = sistema("grimoire-web")                    # nem reiniciavel, nem bloqueado
        r = vai(self, servidor(sistemas=sem_campo), "console.log(JSON.stringify({ b: rotulos(c) }));")
        self.assertNotIn("Reiniciar", r["b"])
        falso = sistema("grimoire-web", "reiniciavel: false, bloqueado: false")
        r = vai(self, servidor(sistemas=falso), "console.log(JSON.stringify({ b: rotulos(c) }));")
        self.assertNotIn("Reiniciar", r["b"])

    def test_servidor_que_so_olha_nao_ganha_botao_e_ganha_o_convite(self):
        r = vai(self, servidor(ordens="null"), "console.log(JSON.stringify({ b: rotulos(c), t: c.textContent }));")
        self.assertNotIn("Reiniciar", r["b"])
        self.assertNotIn("Voltar", r["b"])
        self.assertIn("Este servidor só olha.", r["t"])
        self.assertIn("Quero poder pedir coisas", r["b"])

    def test_o_convite_abre_a_linha_com_pedidos(self):
        r = vai(self, servidor(ordens="null"),
                "await acharBotao(c, 'Quero poder pedir coisas').clicar();\n"
                "console.log(JSON.stringify({ buscas, t: c.textContent }));",
                "[resposta(200, LINHA)]")
        self.assertEqual(r["buscas"], ["/api/ajudante/linha"])
        self.assertIn("Código de conferência do arquivo", r["t"])

    def test_servidor_sem_dados_nao_ganha_botao_nem_convite(self):
        r = vai(self, servidor(ordens="null", estado="sem_dados"),
                "console.log(JSON.stringify({ b: rotulos(c), t: c.textContent }));")
        self.assertNotIn("Reiniciar", r["b"])
        self.assertNotIn("Quero poder pedir coisas", r["b"])
        self.assertNotIn("só olha", r["t"])

    def test_servidor_antigo_sem_a_chave_ordens_nada_de_novo_aparece(self):
        antigo = servidor().replace(", ordens: " + ORDENS, "")
        r = vai(self, antigo, "console.log(JSON.stringify({ b: rotulos(c), t: c.textContent }));")
        self.assertEqual(r["b"], ["Desligar este servidor", "Ligar outro servidor"])
        self.assertNotIn("só olha", r["t"])

    def test_sem_chave_de_acesso_viva_os_botoes_somem_e_a_tela_manda_cadastrar(self):
        r = vai(self, servidor(ordens=ORDENS.replace("chaves_ok: true", "chaves_ok: false")),
                "const a = acha(c, n => n.tag === 'a');\n"
                "console.log(JSON.stringify({ b: rotulos(c), t: c.textContent, href: a.href, rot: a.textContent }));")
        self.assertNotIn("Reiniciar", r["b"])
        self.assertNotIn("Voltar", r["b"])
        self.assertIn("Você não tem mais nenhuma chave de acesso, então este servidor não aceita pedidos "
                      "seus. Cadastre uma em Conta e cole a linha de novo.", r["t"])
        self.assertEqual((r["href"], r["rot"]), ("#/conta", "Ir para Conta"))

    def test_linha_velha_avisa_e_os_botoes_continuam(self):
        r = vai(self, servidor(ordens=ORDENS.replace("linha_velha: false", "linha_velha: true")),
                "console.log(JSON.stringify({ b: rotulos(c), t: c.textContent }));")
        self.assertIn("A lista de aparelhos que podem mandar pedidos mudou desde que você ligou este "
                      "servidor. Os aparelhos antigos continuam valendo; para os novos, cole a linha de novo.",
                      r["t"])
        self.assertIn("Ver a linha nova", r["b"])
        self.assertEqual(r["b"].count("Reiniciar"), 3)

    def test_voltar_vazio_diz_a_frase_do_design(self):
        r = vai(self, servidor(ordens=ORDENS.replace("['grimoire', 'dervs']", "[]")),
                "console.log(JSON.stringify({ b: rotulos(c), t: c.textContent }));")
        self.assertIn("Voltar a versão anterior", r["t"])
        self.assertIn("Nenhum projeto deste servidor pode voltar de versão ainda.", r["t"])
        self.assertNotIn("Voltar", r["b"])

    def test_o_nome_do_alvo_vem_de_fora_e_entra_como_texto(self):
        r = vai(self, servidor(ordens=ORDENS.replace("'grimoire'", "'<b>x</b>'")),
                "console.log(JSON.stringify({ t: c.textContent }));")
        self.assertIn("<b>x</b>", r["t"])


# ====================================================================== frase
class AFraseEOsTextosDoDialogo(unittest.TestCase):
    def test_a_frase_e_letra_por_letra_a_do_servidor(self):
        r = rode(self, "console.log(JSON.stringify([fraseDoPedido('reiniciar', 'grimoire-web', 'vps-ovh'), "
                 "fraseDoPedido('voltar', 'grimoire', 'vps-ovh')]));")
        self.assertEqual(r, ["Reiniciar o sistema “grimoire-web” no servidor “vps-ovh”",
                             "Voltar “grimoire” para a versão anterior no servidor “vps-ovh”"])

    def test_clicar_so_pergunta_e_nada_sai_antes_do_pode_fazer(self):
        r = vai(self, servidor(),
                "await acharBotao(linhaDe(c, 'sistema-do-servidor', 'grimoire-web'), 'Reiniciar').clicar();\n"
                "console.log(JSON.stringify({ conf: confirmacoes, escritas, buscas }));")
        self.assertEqual(len(r["conf"]), 1)
        o = r["conf"][0]
        self.assertEqual(o["titulo"], "Reiniciar o sistema “grimoire-web” no servidor “vps-ovh”")
        self.assertEqual((o["sim"], o["nao"]), ("Pode fazer", "Agora não"))
        self.assertIn("O sistema para e volta sozinho, em alguns segundos.", o["texto"])
        self.assertIn("Depois do clique, o seu aparelho pede a digital ou o PIN.", o["texto"])
        self.assertEqual((r["escritas"], r["buscas"]), ([], []))

    def test_voltar_pergunta_com_a_frase_e_o_texto_dele(self):
        r = vai(self, servidor(),
                "await acharBotao(linhaDe(c, 'voltavel', 'dervs'), 'Voltar').clicar();\n"
                "console.log(JSON.stringify({ conf: confirmacoes, escritas }));")
        o = r["conf"][0]
        self.assertEqual(o["titulo"], "Voltar “dervs” para a versão anterior no servidor “vps-ovh”")
        self.assertIn("O servidor põe no ar de novo a versão que estava antes da última publicação.", o["texto"])
        self.assertEqual(r["escritas"], [])


# ======================================================================= o fio
PREPARADO = ("{ numero: '4e1d2c3b5a6978f0e1d2c3b4a5968778', desafio: 'I1hYDAUhTGY5VpoQX-AjUNLOox129P1vbq2JZEUJDYQ', "
             "rp_id: 'dervs.com.br', chaves: ['AQID', 'BAUGBw'], segundos: 300, "
             "frase: 'Reiniciar o sistema “grimoire-web” no servidor “vps-ovh”' }")

# O navegador falso: `get` guarda o que recebeu e devolve a credencial pronta.
NAVEGADOR = r"""
const gets = [];
const CRED = { id: 'Y3JlZA', response: { clientDataJSON: new Uint8Array([1, 2, 3]).buffer,
  authenticatorData: new Uint8Array([4, 5, 6, 7]).buffer, signature: new Uint8Array([250, 251, 252]).buffer } };
function navegadorCom(get) {
  Object.defineProperty(globalThis, 'navigator', { configurable: true, value: { credentials: { get } } });
}
navegadorCom(async (o) => { gets.push(o); return CRED; });
const clicaReiniciar = async () => {
  await acharBotao(linhaDe(c, 'sistema-do-servidor', 'grimoire-web'), 'Reiniciar').clicar();
  await aoSim();
};
"""


class OFioDaTelaDoCliqueAteOServidor(unittest.TestCase):
    def feliz(self):
        return vai(self, servidor(),
                   NAVEGADOR + "await clicaReiniciar();\n"
                   "console.log(JSON.stringify({ escritas, recados, recarregou, "
                   "get: gets.length ? { rpId: gets[0].publicKey.rpId, uv: gets[0].publicKey.userVerification, "
                   "tempo: gets[0].publicKey.timeout, desafio: Array.from(gets[0].publicKey.challenge), "
                   "ids: gets[0].publicKey.allowCredentials.map(a => [a.type, Array.from(a.id)]) } : null, "
                   "tipoDoId: typeof escritas[0][1].maquina_id }));",
                   "[resposta(200, %s), resposta(200, {ok: true})]" % PREPARADO)

    def test_preparar_recebe_o_maquina_id_como_numero(self):
        """Sabotar `+s.maquina_id` por `s.maquina_id` manda o texto "7" e volta 400."""
        r = self.feliz()
        self.assertEqual(r["escritas"][0], ["/api/maquinas/ordem/preparar",
                                            {"maquina_id": 7, "tipo": "reiniciar", "alvo": "grimoire-web"}])
        self.assertEqual(r["tipoDoId"], "number")

    def test_a_digital_e_pedida_com_o_que_o_servidor_mandou(self):
        g = self.feliz()["get"]
        self.assertEqual((g["rpId"], g["uv"], g["tempo"]), ("dervs.com.br", "required", 300000))
        self.assertEqual(g["desafio"][:4], [0x23, 0x58, 0x58, 0x0C])       # I1hYDA... em bytes
        self.assertEqual(len(g["desafio"]), 32)
        self.assertEqual(g["ids"], [["public-key", [1, 2, 3]], ["public-key", [4, 5, 6, 7]]])

    def test_assinar_recebe_os_cinco_campos_em_base64url(self):
        e = self.feliz()["escritas"]
        self.assertEqual(len(e), 2)
        self.assertEqual(e[1], ["/api/maquinas/ordem/assinar", {
            "numero": "4e1d2c3b5a6978f0e1d2c3b4a5968778", "cred_id": "Y3JlZA",
            "cliente": "AQID", "autenticador": "BAUGBw", "assinatura": "-vv8"}])   # 250,251,252 -> "-vv8"

    def test_sucesso_diz_pedido_enviado_e_recarrega(self):
        r = self.feliz()
        self.assertEqual(r["recados"][0][0], "pedido enviado. O resultado aparece neste cartão.")
        self.assertFalse(r["recados"][0][1])
        self.assertEqual(r["recarregou"], ["carregar"])

    def test_enquanto_espera_a_digital_a_faixa_repete_a_frase_e_tudo_fica_desabilitado(self):
        r = vai(self, servidor(),
                NAVEGADOR + "let solta; navegadorCom((o) => new Promise(f => { solta = f; }));\n"
                "const p = clicaReiniciar();\n"
                "await new Promise(f => setImmediate(f));\n"
                "const faixa = acha(c, n => n.className === 'faixa-do-pedido');\n"
                "const durante = { faixa: faixa && faixa.textContent, b: rotulos(c), "
                "off: botoesDe(c).filter(b => b.getAttribute('aria-disabled') === 'true').length, "
                "titulo: botoesDe(c).filter(b => b.title).map(b => b.title)[0] };\n"
                "solta(CRED); await p;\n"
                "console.log(JSON.stringify({ durante, depois: c.textContent }));",
                "[resposta(200, %s), resposta(200, {ok: true})]" % PREPARADO)
        d = r["durante"]
        self.assertEqual(d["faixa"], "Confira: Reiniciar o sistema “grimoire-web” no servidor "
                                     "“vps-ovh”. O pedido vence em 5 minutos.")
        self.assertIn("Esperando a sua digital…", d["b"])
        self.assertEqual(d["b"].count("Esperando a sua digital…"), 1)
        self.assertEqual(d["off"], 5)                        # 3 Reiniciar + 2 Voltar; o Desligar fica livre
        self.assertEqual(d["titulo"], "Espere o pedido anterior terminar.")
        self.assertNotIn("Confira:", r["depois"])

    def test_botao_desabilitado_nao_pergunta(self):
        r = vai(self, servidor(ordens=com_pedidos(pedido("reiniciar", "dervs-app", "enviado"))),
                "const b = acharBotao(linhaDe(c, 'sistema-do-servidor', 'grimoire-web'), 'Reiniciar');\n"
                "await b.clicar();\n"
                "console.log(JSON.stringify({ conf: confirmacoes.length, aria: b.getAttribute('aria-disabled') }));")
        self.assertEqual((r["conf"], r["aria"]), (0, "true"))

    def test_voltar_vai_pelo_mesmo_fio_com_tipo_voltar(self):
        r = vai(self, servidor(),
                NAVEGADOR + "await acharBotao(linhaDe(c, 'voltavel', 'grimoire'), 'Voltar').clicar();\nawait aoSim();\n"
                "console.log(JSON.stringify({ e: escritas[0] }));",
                "[resposta(409, {motivo: 'ocupado'})]")
        self.assertEqual(r["e"], ["/api/maquinas/ordem/preparar",
                                  {"maquina_id": 7, "tipo": "voltar", "alvo": "grimoire"}])

    def depois_de(self, respostas, nav=""):
        return vai(self, servidor(),
                   NAVEGADOR + nav + "await clicaReiniciar();\n"
                   "console.log(JSON.stringify({ t: c.textContent, escritas: escritas.length, gets: gets.length, "
                   "faixas: faixas.length, b: rotulos(c) }));", respostas)

    def test_cancelar_a_digital_nao_manda_nada_e_nao_e_erro(self):
        for nav in ("navegadorCom(async () => { const e = new Error('x'); e.name = 'NotAllowedError'; throw e; });",
                    "navegadorCom(async () => { const e = new Error('x'); e.name = 'AbortError'; throw e; });",
                    "navegadorCom(async () => null);"):
            with self.subTest(nav=nav[:60]):
                r = self.depois_de("[resposta(200, %s)]" % PREPARADO, nav)
                self.assertEqual(r["escritas"], 1)                       # so o preparar; assinar nao saiu
                self.assertIn("Você cancelou. Nada foi pedido ao servidor.", r["t"])
                self.assertNotIn("pedido enviado", r["t"])
                self.assertEqual(r["b"].count("Reiniciar"), 3)           # o botao voltou ao normal

    def test_outro_erro_do_navegador_nao_finge_cancelamento(self):
        r = self.depois_de("[resposta(200, %s)]" % PREPARADO,
                           "navegadorCom(async () => { const e = new Error('x'); e.name = 'SecurityError'; throw e; });")
        self.assertIn("Não deu para conferir a sua digital. Nada foi pedido. Tente de novo.", r["t"])
        self.assertNotIn("cancelou", r["t"])

    def test_cada_resposta_de_erro_ao_preparar_vira_a_frase_do_design(self):
        casos = [
            (409, "{motivo: 'so_olha'}", "Este servidor só olha. Para ele aceitar pedidos, cole a linha com pedidos."),
            (409, "{motivo: 'sem_dados'}", "O servidor não conta nada há mais de 3 minutos. Espere ele voltar a medir."),
            (409, "{motivo: 'ocupado'}", "Já há um pedido em andamento neste servidor. Espere ele terminar."),
            (409, "{motivo: 'sem_chave'}", "Nenhum aparelho seu é conhecido por este servidor. Cole a linha com pedidos de novo."),
            (403, "{motivo: 'bloqueado'}", "Este sistema guarda dado de saúde e fica de fora sempre."),
            (404, "{erro: 'nao achei'}", "Não achei este servidor na sua conta. Recarregue a página."),
            (400, "{erro: 'pedido invalido'}", "Esse sistema não está mais na medição. Recarregue a página."),
            (429, "{erro: 'nao deu'}", "Muitos pedidos em pouco tempo. Tente daqui a alguns minutos."),
            (500, "{}", "Não consegui falar com o DERVS. Nada foi pedido. Tente de novo."),
            (409, "{motivo: 'inventado'}", "Não consegui falar com o DERVS. Nada foi pedido. Tente de novo."),
        ]
        for status, corpo, frase in casos:
            with self.subTest(status=status, corpo=corpo):
                r = self.depois_de("[resposta(%d, %s)]" % (status, corpo))
                self.assertIn(frase, r["t"])
                self.assertEqual((r["gets"], r["escritas"]), (0, 1))     # nem pediu a digital
                self.assertEqual(r["b"].count("Reiniciar"), 3)

    def test_erros_ao_assinar_e_rede(self):
        casos = [("resposta(401, {erro: 'nao deu'})", "Não deu para conferir a sua digital. Nada foi pedido. Tente de novo."),
                 ("resposta(429, {erro: 'nao deu'})", "Muitos pedidos em pouco tempo. Tente daqui a alguns minutos.")]
        for resp, frase in casos:
            with self.subTest(frase=frase[:30]):
                r = self.depois_de("[resposta(200, %s), %s]" % (PREPARADO, resp))
                self.assertIn(frase, r["t"])
                self.assertNotIn("pedido enviado", r["t"])
                self.assertEqual((r["gets"], r["escritas"]), (1, 2))
        r = self.depois_de("[Promise.reject(new Error('rede'))]")
        self.assertIn("Não consegui falar com o DERVS. Nada foi pedido. Tente de novo.", r["t"])

    def test_sem_suporte_do_navegador_nem_chega_a_preparar(self):
        r = self.depois_de("[]", "Object.defineProperty(globalThis, 'navigator', { configurable: true, value: {} });")
        self.assertIn("Este navegador não sabe pedir a digital. Use o Chrome, o Edge ou o Safari atualizados.", r["t"])
        self.assertEqual(r["escritas"], 0)

    def test_pagina_velha_deixa_a_faixa_central_falar_e_nao_repete(self):
        r = self.depois_de("[resposta(403, {motivo: 'pagina_velha'})]")
        self.assertNotIn("Não consegui falar", r["t"])
        self.assertNotIn("Confira:", r["t"])
        self.assertEqual(r["b"].count("Reiniciar"), 3)

    def test_resposta_do_servidor_torta_nao_vira_digital(self):
        r = self.depois_de("[resposta(200, {numero: 'x'})]")
        self.assertEqual(r["gets"], 0)
        self.assertIn("Não consegui falar com o DERVS. Nada foi pedido.", r["t"])


# ==================================================================== estados
class CadaEstadoDoPedidoDiz(unittest.TestCase):
    def estado(self, **campos):
        base = dict(tipo="reiniciar", alvo="grimoire-web", estado="enviado", quando="ha(40)")
        base.update(campos)
        srv = servidor(ordens=com_pedidos(pedido(**base)))
        return vai(self, srv,
                   "const li = linhaDe(c, 'sistema-do-servidor', 'grimoire-web');\n"
                   "const p = acha(li, n => n.className === 'pedido');\n"
                   "const marca = p && acha(p, n => n.className === 'marca');\n"
                   "console.log(JSON.stringify({ t: p ? p.textContent : null, cor: marca && marca.dataset.cor, "
                   "rotulo: marca && marca.filhos[1].textContent, numero: p && p.dataset.numero }));")

    def test_os_oito_estados_com_a_frase_exata(self):
        casos = [
            ("enviado", {}, "pedido enviado há 40 segundos", "neutro"),
            ("fazendo", {}, "o servidor está fazendo, há 40 segundos", "neutro"),
            ("nao_pegou", {}, "o servidor não pegou o pedido. Nada foi feito. Confira se ele está medindo "
                              "(o carimbo acima) e peça de novo.", "atencao"),
            ("feito", {"quando": "ha(12)"}, "feito há 12 segundos", "verde"),
            ("nao_deu", {"codigo": "1"}, "não deu certo (código 1). Confira o sistema na lista acima: se ele "
                                         "estiver parado, peça de novo.", "vermelho"),
            ("sem_resposta", {"quando": "ha(1860)"}, "o servidor pegou o pedido há 31 minutos e não contou como "
                                                     "terminou. Não sei se foi feito.", "neutro"),
            ("nao_sei", {}, "o servidor não conseguiu saber se terminou. Confira o sistema na lista acima.", "neutro"),
            ("recusado", {"motivo": "'teto'"}, "o servidor recusou o pedido: já foram 6 pedidos na última hora, "
                                                "o máximo. Tente de novo mais tarde.", "vermelho"),
        ]
        for estado, extra, frase, cor in casos:
            with self.subTest(estado=estado):
                r = self.estado(estado=estado, **extra)
                self.assertIn(frase, r["t"])
                self.assertEqual(r["cor"], cor)
                self.assertEqual(r["numero"], "4e1d")

    def test_so_feito_diz_feito_e_so_ele_e_verde(self):
        """Sabotar `nao_pegou` para `feito` derruba este caso (e o de cima)."""
        for estado in ("enviado", "fazendo", "nao_pegou", "nao_deu", "recusado", "sem_resposta", "nao_sei", "inventado"):
            with self.subTest(estado=estado):
                r = self.estado(estado=estado)
                self.assertNotEqual(r["rotulo"], "feito")
                self.assertNotEqual(r["cor"], "verde")
                self.assertNotRegex(r["t"], r"feito há")
                self.assertNotIn("deu certo", r["t"].replace("não deu certo", ""))

    def test_estado_que_a_tela_nao_conhece_vira_nao_sei(self):
        r = self.estado(estado="inventado")
        self.assertEqual(r["rotulo"], "não sei")
        self.assertEqual(r["cor"], "neutro")

    def test_cada_motivo_da_recusa_tem_a_frase_da_tabela(self):
        tabela = {
            "teto": "já foram 6 pedidos na última hora, o máximo. Tente de novo mais tarde.",
            "vencida": "o pedido chegou depois dos 5 minutos. Peça de novo.",
            "repetida": "este pedido já tinha sido usado.",
            "bloqueado": "este sistema guarda dado de saúde e fica de fora sempre.",
            "desconhecido": "o servidor não encontrou esse sistema ou projeto agora.",
            "outro_servidor": "o pedido era para outra ligação deste servidor. Recarregue a página e peça de novo.",
            "cheio": "o servidor está com pedidos demais guardados. Tente daqui a 5 minutos.",
        }
        for m in ("assinatura", "desafio", "origem", "aparelho", "forma"):
            tabela[m] = ("o servidor não reconheceu a sua digital neste pedido. Se a lista de aparelhos mudou, "
                         "cole a linha de novo.")
        for motivo, frase in tabela.items():
            with self.subTest(motivo=motivo):
                r = self.estado(estado="recusado", motivo="'%s'" % motivo)
                self.assertIn("o servidor recusou o pedido: " + frase, r["t"])
        r = self.estado(estado="recusado", motivo="'constructor'")           # nome de objeto nao e motivo
        self.assertEqual(r["t"].split("recusou o pedido")[1], ".")
        r = self.estado(estado="recusado")
        self.assertTrue(r["t"].endswith("o servidor recusou o pedido."))

    def test_o_pedido_aparece_na_linha_do_alvo_e_so_o_mais_novo(self):
        srv = servidor(ordens=com_pedidos(
            pedido("reiniciar", "grimoire-web", "feito", numero="'novo'"),
            pedido("reiniciar", "grimoire-web", "nao_deu", codigo="1", numero="'velho'"),
            pedido("voltar", "grimoire", "nao_deu", codigo="1", quando="ha(540)", numero="'volta'")))
        r = vai(self, srv,
                "const num = (li) => achaTodos(li, n => n.className === 'pedido').map(n => n.dataset.numero);\n"
                "console.log(JSON.stringify({ web: num(linhaDe(c, 'sistema-do-servidor', 'grimoire-web')), "
                "app: num(linhaDe(c, 'sistema-do-servidor', 'dervs-app')), "
                "volta: num(linhaDe(c, 'voltavel', 'grimoire')), outra: num(linhaDe(c, 'voltavel', 'dervs')) }));")
        self.assertEqual(r, {"web": ["novo"], "app": [], "volta": ["volta"], "outra": []})

    def test_pedido_de_alvo_que_sumiu_fica_numa_linha_ultimo_pedido(self):
        srv = servidor(ordens=com_pedidos(pedido("reiniciar", "sumiu-app", "feito", quando="ha(12)")))
        r = vai(self, srv, "console.log(JSON.stringify({ t: c.textContent }));")
        self.assertIn("Último pedido: reiniciar sumiu-app", r["t"])
        self.assertIn("feito há 12 segundos", r["t"])
        sem = vai(self, servidor(ordens=com_pedidos(pedido("reiniciar", "grimoire-web", "feito"))),
                  "console.log(JSON.stringify({ t: c.textContent }));")
        self.assertNotIn("Último pedido", sem["t"])

    def test_enviado_e_fazendo_travam_os_botoes_e_os_outros_nao(self):
        for estado, travado in (("enviado", True), ("fazendo", True), ("feito", False), ("nao_pegou", False),
                                ("nao_deu", False), ("recusado", False), ("sem_resposta", False), ("nao_sei", False)):
            with self.subTest(estado=estado):
                r = vai(self, servidor(ordens=com_pedidos(pedido("reiniciar", "dervs-app", estado))),
                        "console.log(JSON.stringify({ off: botoesDe(c).filter(b => "
                        "b.getAttribute('aria-disabled') === 'true').length }));")
                self.assertEqual(r["off"], 5 if travado else 0)


# ============================================================= a linha para colar
LINHA2 = ("{ linha: 'LINHA-SO-OLHAR', sha256: '" + "a" * 64 + "', endereco: 'https://dervs.com.br/ajudante/servidor.py', "
          "linha_com_ordens: 'LINHA-SO-OLHAR --ordens 00.11,22.33', "
          "chaves_na_linha: ['Celular do Thiago', 'PIN do notebook'] }")


class AsDuasLinhasParaColar(unittest.TestCase):
    def bloco(self, d, depois=""):
        return rode(self, "const b = blocoDaLinhaDoAjudante(%s);\n%s"
                    "console.log(JSON.stringify({ t: b.textContent, "
                    "pres: achaTodos(b, n => n.tag === 'pre').map(n => n.textContent), "
                    "h3: achaTodos(b, n => n.tag === 'h3').map(n => n.textContent), "
                    "det: achaTodos(b, n => n.tag === 'details').map(n => [n.open, acha(n, m => m.tag === 'summary').textContent]), "
                    "botoes: achaTodos(b, n => n.tag === 'button').map(n => n.textContent), "
                    "links: achaTodos(b, n => n.tag === 'a').map(n => [n.href, n.textContent]), x: typeof x === 'undefined' ? null : x }));"
                    % (d, depois))

    def test_com_chave_as_duas_escolhas_uma_embaixo_da_outra(self):
        r = self.bloco(LINHA2)
        self.assertEqual(r["h3"][:2], ["Só olhar", "Olhar e aceitar pedidos"])
        self.assertEqual(r["pres"], ["LINHA-SO-OLHAR", "LINHA-SO-OLHAR --ordens 00.11,22.33"])
        self.assertEqual(r["botoes"].count("Copiar"), 2)
        self.assertIn("O servidor conta o que está rodando nele. O DERVS não consegue pedir nada a ele.", r["t"])
        self.assertIn("Além de contar, o servidor aceita dois pedidos seus: reiniciar um sistema e voltar um "
                      "projeto para a versão anterior. Cada pedido só anda com a sua digital ou o seu PIN.", r["t"])
        self.assertIn("Poderão mandar pedidos: Celular do Thiago, PIN do notebook.", r["t"])
        self.assertIn("Se o servidor já estava ligado, ela troca o jeito dele sem perder o que ele já contou.", r["t"])
        self.assertIn("Para voltar a só olhar, cole no servidor a linha Só olhar. Os pedidos são desligados na hora.", r["t"])
        self.assertEqual(r["links"], [])                       # a escolha de cadastrar chave so aparece sem chave

    def test_o_copiar_da_segunda_copia_a_linha_com_pedidos(self):
        r = self.bloco(LINHA2, "Object.defineProperty(globalThis, 'navigator', { configurable: true, "
                       "value: { clipboard: { writeText: async (t) => { copiados.push(t); } } } });\n"
                       "var copiados = [];\n"
                       "const bs = achaTodos(b, n => n.tag === 'button' && n.textContent === 'Copiar');\n"
                       "await bs[1].clicar(); await bs[0].clicar();\n"
                       "var x = [copiados, bs.map(n => n.getAttribute('aria-label'))];\n")
        self.assertEqual(r["x"][0], ["LINHA-SO-OLHAR --ordens 00.11,22.33", "LINHA-SO-OLHAR"])
        self.assertEqual(r["x"][1], ["Copiar a linha para colar no servidor",
                                     "Copiar a linha com pedidos para colar no servidor"])

    def test_o_que_isso_faz_da_linha_com_pedidos_vem_fechado_e_diz_o_limite_inteiro(self):
        r = self.bloco(LINHA2)
        self.assertEqual(r["det"], [[False, "O que isso faz?"],
                                    [False, "O que isso faz? (olhar e aceitar pedidos)"]])
        for frase in (
                "deixa o servidor aceitar dois pedidos seus — reiniciar um sistema que ele está vendo e voltar "
                "um projeto para a versão que estava no ar antes da última.",
                "ele não apaga, não para, não lê dados nem senhas e não aceita nenhuma ordem escrita.",
                "é o próprio servidor quem confere que foi o seu aparelho, que o pedido é recente e que ainda "
                "não foi usado.",
                "O limite, com todas as letras: o seu aparelho não mostra qual pedido você está aprovando — ele "
                "mostra só “dervs.com.br”. Se alguém tomasse o dervs.com.br, poderia trocar o pedido na "
                "hora do seu toque. Sem um toque seu, nada acontece.",
                "cada toque vira no máximo um pedido desta lista — reiniciar um sistema ou voltar um projeto "
                "liberado —, nunca no Ajudei, nunca um comando, e no máximo 6 por hora em cada servidor.",
                "Se o seu aparelho pedir a digital sem você ter clicado em “Pode fazer”, recuse.",
                "cole a linha Só olhar (desliga os pedidos) ou a linha de remover, que já está acima."):
            with self.subTest(frase=frase[:40]):
                self.assertIn(frase, r["t"])

    def test_sem_chave_a_linha_com_pedidos_nao_existe_e_a_tela_ensina_a_cadastrar(self):
        d = LINHA2.replace("linha_com_ordens: 'LINHA-SO-OLHAR --ordens 00.11,22.33'", "linha_com_ordens: null") \
                  .replace("chaves_na_linha: ['Celular do Thiago', 'PIN do notebook']", "chaves_na_linha: []")
        r = self.bloco(d)
        self.assertEqual(r["pres"], ["LINHA-SO-OLHAR"])
        self.assertNotIn("--ordens", r["t"])
        self.assertEqual(r["links"], [["#/conta", "Cadastrar uma chave de acesso"]])
        self.assertIn("Para o servidor aceitar pedidos, você precisa de uma chave de acesso (a digital do "
                      "celular ou o PIN do computador). Cadastre uma e volte aqui.", r["t"])
        self.assertNotIn("Olhar e aceitar pedidos", r["t"])
        self.assertEqual(r["det"], [[False, "O que isso faz?"]])

    def test_servidor_antigo_sem_o_campo_mostra_so_a_linha_de_sempre(self):
        d = "{ linha: 'LINHA-SO-OLHAR', sha256: '" + "a" * 64 + "' }"
        r = self.bloco(d)
        self.assertEqual(r["pres"], ["LINHA-SO-OLHAR"])
        self.assertEqual((r["h3"], r["links"]), (["Se der errado"], []))


# ===================================================== texto, fonte e jargao
class OsPedidosNaoFalamAlinguaDeQuemConstruiu(unittest.TestCase):
    NOVAS = FUNCOES_NOVAS + ("linhaDeSistema", "linhaDeServidorLigado")

    @staticmethod
    def literais_de(codigo):
        return "\n".join(re.findall(r'"(?:[^"\\\n]|\\.)*"', sem_comentarios(codigo)))

    def codigo(self):
        return "".join(funcao(n) for n in self.NOVAS + ("blocoDaLinhaDoAjudante",))

    def visivel(self, fonte=None):
        """So o texto que a pessoa le: as funcoes novas inteiras, mais o que
        `blocoDaLinhaDoAjudante` ganhou (o resto dele e da entrega B, com as
        frases do terminal entre <code>), menos os NOMES de motivo, que sao
        chaves de uma tabela e nunca aparecem na tela."""
        fonte = fonte or JS
        def f(nome):
            return re.search(r"^(?:async )?function %s\(.*?\n}\n" % nome, fonte, re.S | re.M).group(0)
        bloco = f("blocoDaLinhaDoAjudante")
        novo = (bloco[bloco.index("const comPedidos"):bloco.index("const passos")]
                + bloco[bloco.index("bloco.append(faz);"):])
        motivo = re.sub(r'for \(const m of \[.*?\]\) frases\[m\] = naoReconheceu;', "", f("fraseDoMotivo"))
        resto = "".join(f(n) for n in self.NOVAS if n != "fraseDoMotivo")
        return self.literais_de(resto + motivo + novo)

    JARGAO_DOS_PEDIDOS = (r"webauthn", r"assinatura", r"\btoken\b", r"cont[eê]iner", r"docker", r"deploy",
                          r"\bsudo\b", r"systemd", r"\bagente\b", r"\blogin\b", r"instala[cç][aã]o")

    def test_jargao_ausente_do_texto_visivel(self):
        texto = self.visivel()
        self.assertGreater(len(texto), 4000)
        self.assertEqual(jargao_em(texto), [])
        for p in self.JARGAO_DOS_PEDIDOS:
            with self.subTest(padrao=p):
                self.assertIsNone(re.search(p, texto, re.I))

    def test_a_palavra_certa_inserida_num_texto_novo_seria_pega(self):
        """A guarda da guarda: sabotar o texto de verdade e exigir que acuse."""
        for velho, novo in (('"Esperando a sua digital…"', '"Esperando a sua assinatura no contêiner…"'),
                            ('"Quero poder pedir coisas"', '"Quero rodar o docker"')):
            with self.subTest(velho=velho):
                sabotado = JS.replace(velho, novo, 1)
                self.assertNotEqual(sabotado, JS)
                achados = re.search(r"cont[eê]iner|assinatura|docker", self.visivel(sabotado), re.I)
                self.assertIsNotNone(achados)
        self.assertIsNone(re.search(r"cont[eê]iner|assinatura|docker", self.visivel(), re.I))

    def test_as_funcoes_novas_estao_entre_os_marcadores_do_guarda_de_jargao(self):
        ini = JS.index("/* === CONECTAR: início === */")
        fim = JS.index("/* === CONECTAR: fim === */")
        for nome in FUNCOES_NOVAS:
            with self.subTest(funcao=nome):
                self.assertTrue(ini < JS.index("function %s(" % nome) < fim)

    def test_nada_de_innerhtml_nem_conversao_de_numero_proibida(self):
        for proibido in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "Number(",
                         "parseInt(", ".style", "style="):
            with self.subTest(proibido=proibido):
                self.assertNotIn(proibido, self.codigo())

    def test_o_maquina_id_vai_com_mais_unario(self):
        self.assertIn("maquina_id: +s.maquina_id", funcao("fazerOPedido"))

    def test_os_literais_que_o_teste_de_fio_procura(self):
        self.assertIn('"/api/maquinas/ordem/preparar"', JS)
        self.assertIn('"/api/maquinas/ordem/assinar"', JS)
        self.assertIn("navigator.credentials.get(", funcao("fazerOPedido"))

    def test_cada_funcao_le_os_campos_do_contrato(self):
        esperado = {
            "linhaDeSistema": ("reiniciavel", "bloqueado"),
            "linhaDeServidorLigado": ("ordens", "maquina_id"),
            "blocoDosPedidos": ("chaves_ok", "linha_velha", "voltaveis", "pedidos"),
            "estadoDoPedido": ("numero", "tipo", "alvo", "estado", "quando", "codigo", "motivo"),
            "fazerOPedido": ("numero", "desafio", "rp_id", "chaves", "segundos", "frase"),
            "fraseDoErroDePedido": ("motivo",),
            "blocoDaLinhaDoAjudante": ("linha_com_ordens", "chaves_na_linha"),
        }
        for nome, campos in esperado.items():
            corpo = funcao(nome)
            for campo in campos:
                with self.subTest(funcao=nome, campo=campo):
                    self.assertRegex(corpo, r"\b%s\b" % campo)

    def test_o_botao_exige_reiniciavel_estritamente_verdadeiro(self):
        self.assertIn("x.reiniciavel === true", funcao("linhaDeSistema"))
        self.assertNotIn("reiniciavel !==", funcao("linhaDeSistema"))


class OCssDosPedidosUsaSoTokensEExistemOsSeletores(unittest.TestCase):
    CLASSES = ("pedido", "pedido__frase", "pedidos", "pedidos__voltar", "voltavel", "faixa-do-pedido",
               "faixa-do-pedido--atencao", "pedido-solto")

    def test_cada_classe_que_o_js_usa_tem_regra_no_css(self):
        css = sem_comentarios(CSS)
        for c in self.CLASSES:
            if c == "pedido-solto":
                continue                      # so zera a margem; o JS a cria
            with self.subTest(classe=c):
                self.assertIn("." + c, css)
                self.assertIn(c, JS)

    def test_a_marca_de_atencao_existe_no_css_e_no_js_com_palavra_escrita(self):
        self.assertIn('.marca[data-cor="atencao"]', CSS)
        self.assertIn("atencao:     { cor: \"atencao\"", JS)
        self.assertRegex(funcao("estadoDoPedido"), r'cor = "atencao"; rotulo = "não pegou"')

    def test_nenhuma_cor_solta_nem_style_no_trecho_novo(self):
        i = CSS.index("pedidos ao servidor (entrega C)")
        bloco = sem_comentarios(CSS[i:CSS.index(".marca__glifo", i)])
        self.assertGreater(len(bloco), 800)
        self.assertNotRegex(bloco, r"#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(|\boklch\(|\bcolor-mix\(")
        self.assertIn("overflow-wrap: anywhere", bloco)
        self.assertIn('aria-disabled="true"', bloco)

    def test_em_tela_estreita_o_botao_enche_a_linha_e_so_depois_de_40rem_vai_a_direita(self):
        css = sem_comentarios(CSS)
        base = re.search(r"\.sistema-do-servidor \.acoes \.botao, \.voltavel \.acoes \.botao \{([^}]*)\}", css).group(1)
        self.assertIn("width: 100%", base)
        mq = re.search(r"@media \(min-width: 40rem\) \{(.*?)\n\}", css, re.S).group(1)
        self.assertIn("margin-left: auto", mq)


if __name__ == "__main__":
    unittest.main(verbosity=2)
