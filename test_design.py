# -*- coding: utf-8 -*-
"""Os oito itens verificaveis do design, virados teste. Etapa 15 do plano.

MOTIVO: `docs/esteira/dervs/design.md` fecha com uma lista chamada "Como esta
fase se prova". Enquanto ela e prosa, ela vale ate a primeira pressa. Um `#fff`
digitado direto num componente, um `--estado-quebrado` emprestado para pintar
um botao, a palavra "loading" numa tela -- nada disso quebra nada, nada disso
aparece numa revisao apressada, e a feiura volta de fininho. A lista aqui vira
verificacao automatica, e a verificacao roda em todo envio.

DUAS COISAS QUE ESTE ARQUIVO NAO FAZ, e diz na propria saida:

  - o item 5 (em 360x640 a linha mostra selo, nome, motivo e carimbo juntos)
    exige olho humano num navegador de verdade;
  - o clique da etapa 14 -- os botoes fazerem o que prometem -- idem.

Teste que se cala sobre o que nao cobre deixa a impressao de cobertura total,
e essa impressao e pior que a lacuna. Por isso `resumo_do_que_falta()` imprime
os dois no fim.

A LEI 2 DESTE REPOSITORIO manda aqui tambem: o painel nao pode mentir, e teste
nao pode mentir sobre o painel. Cada caso comeca provando que a extracao achou
o que ia examinar. Busca que nao acha nada passa vazia e verde -- e um teste
verde por engano e pior que teste nenhum, porque ninguem volta nele.

    python test_design.py
"""
from __future__ import annotations

import importlib.util
import re
import sys
import unittest
from pathlib import Path

AQUI = Path(__file__).parent
CSS = AQUI / "assets" / "dervs.css"
HTML = AQUI / "index.html"
# O layout e o script da tela viviam DENTRO do index.html ate 28/08/2026.
# A CSP de producao descarta estilo e script embutidos (commit 496f710), e
# eles sairam para arquivo proprio. O teste segue os arquivos: apontar para
# o index.html vazio faria toda busca achar zero e passar vazia -- foi
# exatamente o que as guardas 1c e 8a pegaram.
PAINEL_CSS = AQUI / "assets" / "painel.css"
PAINEL_JS = AQUI / "assets" / "painel.js"

# O verificador de contraste da etapa 13 e importado, nao reescrito. Ele ja le
# o CSS de verdade (a licao de 27/08/2026: ate aquele dia ele guardava uma
# COPIA da paleta, e uma copia aprova a cor velha com cara de verificacao).
# Reescrever a formula da WCAG aqui criaria a segunda copia pelo mesmo motivo.
_spec = importlib.util.spec_from_file_location(
    "contraste", AQUI / "docs" / "esteira" / "dervs" / "contraste.py")
contraste = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(contraste)


# --------------------------------------------------------------- ferramentas
def css() -> str:
    return CSS.read_text(encoding="utf-8")


def html() -> str:
    return HTML.read_text(encoding="utf-8")


def sem_comentarios_css(texto: str) -> str:
    """Comentario nao e regra. O cabecalho do CSS cita `#fff` e `--estado-*`
    justamente para explicar as regras que este teste cobra -- procurar cor
    literal sem tirar os comentarios reprovaria o texto que descreve a lei."""
    return re.sub(r"/\*.*?\*/", " ", texto, flags=re.S)


def blocos_de_token(texto: str) -> list[tuple[int, int]]:
    """Os intervalos (inicio, fim) dos blocos onde cor literal E PERMITIDA.

    Sao tres, e so tres: o `:root` claro e os dois blocos de tema escuro. E o
    unico lugar do sistema onde um `#rrggbb` pode aparecer.
    """
    faixas = []
    for seletor in (":root {",
                    "@media (prefers-color-scheme: dark)",
                    ':root[data-theme="dark"]'):
        i = texto.index(seletor)
        abre = texto.index("{", i)
        fundo = 0
        for j in range(abre, len(texto)):
            if texto[j] == "{":
                fundo += 1
            elif texto[j] == "}":
                fundo -= 1
                if fundo == 0:
                    faixas.append((i, j))
                    break
        else:
            raise AssertionError("bloco %r nao fecha em dervs.css" % seletor)
    return faixas


def estilo_da_tela() -> str:
    """O layout do painel -- `assets/painel.css`. Ele e legitimo e guarda o
    layout, que e desta tela e de mais nenhuma. Cor, nao: cor mora nos tokens
    de `dervs.css`. Era o bloco `<style>` do index.html antes da CSP."""
    texto = PAINEL_CSS.read_text(encoding="utf-8")
    assert texto.strip(), "assets/painel.css esta vazio \u2014 confira o teste"
    return re.sub(r"/\*.*?\*/", " ", texto, flags=re.S)


CORES = re.compile(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(|\boklch\(|\bcolor-mix\(")


# ------------------------------------------------------- 1, 2 e 4: a cor
class ACorMoraNumLugarSo(unittest.TestCase):
    """Itens 1, 2 e 4 da lista.

    As tres sao a mesma disciplina vista de tres angulos: existe UM lugar onde
    a cor e escolhida, e todo o resto a consome por nome. Quando essa regra
    afrouxa, o tema escuro para de funcionar em silencio -- o componente que
    tem a cor cravada continua claro, e ninguem percebe ate abrir a tela a
    noite.
    """

    def test_1_nenhuma_cor_literal_fora_do_bloco_de_tokens(self):
        texto = sem_comentarios_css(css())
        faixas = blocos_de_token(texto)
        fora = []
        for m in CORES.finditer(texto):
            if not any(i <= m.start() <= f for i, f in faixas):
                linha = texto.count("\n", 0, m.start()) + 1
                fora.append("dervs.css:%d %s" % (linha, m.group()))
        self.assertEqual(fora, [], "cor literal fora do bloco de tokens: "
                                   + "; ".join(fora))

    def test_1b_a_busca_de_cor_realmente_acha_cor_onde_ela_deve_estar(self):
        """A guarda do item 1. Se a expressao parar de casar, o teste acima
        passa vazio e mente: zero achados fora dos tokens seria indistinguivel
        de zero achados em lugar nenhum."""
        texto = sem_comentarios_css(css())
        faixas = blocos_de_token(texto)
        dentro = [m for m in CORES.finditer(texto)
                  if any(i <= m.start() <= f for i, f in faixas)]
        self.assertGreaterEqual(
            len(dentro), 30,
            "a busca por cor achou so %d valores DENTRO dos tokens; a paleta "
            "tem dezenas. A expressao provavelmente parou de casar."
            % len(dentro))

    def test_1c_o_style_do_html_nao_guarda_cor(self):
        """O `<style>` do index.html e a segunda porta por onde a cor volta."""
        achadas = [m.group() for m in CORES.finditer(estilo_da_tela())]
        self.assertEqual(achadas, [],
                         "cor literal em assets/painel.css: %s. Layout "
                         "fica ali; cor vem de var(--...)." % achadas)

    def test_2_estado_nao_pinta_botao_link_navegacao_nem_cabecalho(self):
        """Item 2, e a regra mais facil de quebrar sem querer.

        Verde nao e cor de marca: e o estado saudavel. No dia em que um botao
        primario ficar verde, o selo verde para de significar alguma coisa
        justamente quando mais importa -- a pessoa aprende a ver verde como
        enfeite.
        """
        texto = sem_comentarios_css(css())
        faixas = blocos_de_token(texto)
        proibidos = ("botao", "link", "nav", "cabecalho", "logo", "marca")
        erros = []
        # Cada regra do CSS: seletor + corpo. Fora dos blocos de tokens.
        for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", texto):
            if any(i <= m.start() <= f for i, f in faixas):
                continue
            seletor, corpo = m.group(1), m.group(2)
            if "--estado-" not in corpo:
                continue
            alvo = seletor.lower()
            for p in proibidos:
                # `.selo` e `.regua .selo` usam estado e devem usar. O que se
                # proibe e o estado vazar para os componentes de acao.
                if p in alvo and "selo" not in alvo and "detalhe" not in alvo:
                    linha = texto.count("\n", 0, m.start()) + 1
                    erros.append("dervs.css:%d  %s" % (linha, seletor.strip()))
                    break
        self.assertEqual(erros, [],
                         "token de estado pintando componente de acao: %s"
                         % "; ".join(erros))

    def test_2b_a_leitura_de_regras_do_css_realmente_enxerga_regras(self):
        """A guarda do item 2."""
        texto = sem_comentarios_css(css())
        regras = re.findall(r"([^{}]+)\{([^{}]*)\}", texto)
        self.assertGreaterEqual(
            len(regras), 50,
            "so %d regras lidas do CSS — a folha tem muito mais. O leitor de "
            "regras quebrou, e o teste acima passaria vazio." % len(regras))
        com_estado = [s for s, c in regras if "--estado-" in c]
        self.assertTrue(com_estado,
                        "nenhuma regra usa --estado-*; ou o selo perdeu a cor, "
                        "ou a leitura quebrou.")

    def test_4_nenhuma_cor_existe_so_dentro_de_um_tema(self):
        """Item 4. Token que so existe no escuro vira `var()` sem valor no
        claro -- e `var()` sem valor nao falha: ela herda, ou some. O defeito
        aparece como um texto invisivel, nao como um erro."""
        texto = css()
        claro = dict(re.findall(r"(--[a-z0-9-]+):\s*([^;]+);",
                                contraste.bloco(texto, ":root {")))
        self.assertGreater(len(claro), 20,
                           "o :root claro definiu so %d tokens — leitura "
                           "quebrada." % len(claro))
        for seletor in ("@media (prefers-color-scheme: dark)",
                        ':root[data-theme="dark"]'):
            corpo = contraste.bloco(texto, seletor)
            escuros = dict(re.findall(r"(--[a-z0-9-]+):\s*([^;]+);", corpo))
            self.assertTrue(escuros, "o bloco %r nao define token nenhum"
                                     % seletor)
            orfaos = sorted(t for t in escuros if t not in claro)
            self.assertEqual(orfaos, [],
                             "%s define %s, que nao existe no :root claro — "
                             "no tema claro esses tokens ficam sem valor."
                             % (seletor, ", ".join(orfaos)))


# --------------------------------------------------------- 3: o contraste
class OContrasteEhRecalculado(unittest.TestCase):
    """Item 3. Nao confere o numero escrito no documento: refaz a conta.

    Numero de contraste escrito a mao envelhece calado — alguem clareia um
    cinza "so um pouquinho" e o 4,6:1 do documento continua la, agora mentindo.
    """

    MIN_TEXTO = 4.5
    MIN_CONTORNO = 3.0

    def paletas(self):
        texto = css()
        return {
            "claro": contraste.paleta(
                contraste.bloco(texto, ":root {"), "claro"),
            "escuro (sistema)": contraste.paleta(
                contraste.bloco(texto, "@media (prefers-color-scheme: dark)"),
                "escuro (sistema)"),
            "escuro (escolhido)": contraste.paleta(
                contraste.bloco(texto, ':root[data-theme="dark"]'),
                "escuro (escolhido)"),
        }

    def test_3_todo_texto_passa_de_4_5_sobre_fundo_e_sobre_cartao(self):
        # `contraste.paleta` devolve o nome curto do token ("texto", "fundo"),
        # nao o `--nome` do CSS.
        for tema, p in self.paletas().items():
            for nome in contraste.TEXTOS:
                for fundo in ("fundo", "elevado"):
                    r = contraste.razao(p[nome], p[fundo])
                    with self.subTest(tema=tema, cor=nome, sobre=fundo):
                        self.assertGreaterEqual(
                            round(r, 2), self.MIN_TEXTO,
                            "%s: %s sobre %s da %.2f:1, abaixo de %.1f:1"
                            % (tema, nome, fundo, r, self.MIN_TEXTO))

    def test_3b_a_borda_que_carrega_significado_passa_de_3(self):
        """`--borda` e decorativa e pode ser fraca. `--borda-forte` e o unico
        sinal de que um campo tem contorno — essa precisa de 3:1."""
        for tema, p in self.paletas().items():
            r = contraste.razao(p["borda_forte"], p["fundo"])
            with self.subTest(tema=tema):
                self.assertGreaterEqual(
                    round(r, 2), self.MIN_CONTORNO,
                    "%s: --borda-forte sobre --fundo da %.2f:1" % (tema, r))

    def test_3d_o_texto_do_botao_passa_sobre_a_cor_de_acao(self):
        """O par mais facil de errar: azul de acao com texto branco por cima."""
        for tema, p in self.paletas().items():
            r = contraste.razao(p["acao"], p["acao_texto"])
            with self.subTest(tema=tema):
                self.assertGreaterEqual(
                    round(r, 2), self.MIN_TEXTO,
                    "%s: texto do botao sobre --acao da %.2f:1" % (tema, r))

    def test_3c_a_conta_reprova_de_verdade(self):
        """A guarda do item 3: um verificador que aprova tudo tambem passaria
        os testes acima. Preto no preto tem de reprovar."""
        self.assertLess(contraste.razao("#000000", "#000000"), self.MIN_TEXTO)
        self.assertGreater(contraste.razao("#000000", "#ffffff"), 20)


# ------------------------------------------------------- 6: o vocabulario
# Da tabela "Vocabulario fixo" do design.md. `commit` fica de fora de
# proposito: e o nome que o dev usa, e traduzir confundiria.
PROIBIDAS = {
    "dashboard": "painel",
    "deploy": "publicar / publicação",
    "deployar": "publicar",
    "pipeline": "verificação automática",
    "scan": "medição",
    "sync": "medição",
    "host": "máquina",
    "runner": "máquina",
    "daemon": "agente",
    "worker": "agente",
    "issue": "pendência",
    "task": "pendência",
    "login": "entrar",
    "logout": "sair",
    "sign in": "entrar",
    "deletar": "excluir",
    "loading": "carregando",
}


class ATelaFalaPortugues(unittest.TestCase):
    """Item 6.

    A tela e a unica superficie que este teste examina: comentario de codigo,
    nome de funcao e nome de classe do CSS seguem em ingles ou em portugues sem
    acento, e isso e proposital -- ali quem le e o programador. O que nao pode
    e a palavra chegar ao dono.
    """

    def texto_visivel(self):
        """O que o dono ve. Nao e "o arquivo inteiro".

        TRES fontes: o texto entre as marcas do HTML, as cadeias de texto do
        `<script>` embutido, e — desde a Fatia 2 — o `assets/painel.js`.

        A terceira nao e um detalhe. Em 28/08/2026 a CSP de producao expulsou o
        script de dentro do HTML, e a partir dali este vigia passou a ler um
        `<script>` que NAO EXISTE MAIS: ele vinha verde por estar olhando para
        o vazio. Todo texto de tela escrito na Fatia 2 nasceria fora do alcance
        dele. O `test_6b` e a guarda disso.

        Comentario, nome de rota, nome de classe e chave de dado ficam de fora
        — `p.selo === "sem_dados"` nao e texto de tela, e reprovar por causa
        dele treinaria a gente a ignorar este teste.
        """
        bruto = html()
        bruto = re.sub(r"<!--.*?-->", " ", bruto, flags=re.S)
        corpo = re.sub(r"<style>.*?</style>", " ", bruto, flags=re.S)
        script = "\n".join(re.findall(r"<script>(.*?)</script>", corpo, re.S))
        script += "\n" + PAINEL_JS.read_text(encoding="utf-8")
        marcacao = re.sub(r"<script>.*?</script>", " ", corpo, flags=re.S)

        pedacos = []
        # 1. Texto entre marcas, e os atributos que o leitor de tela fala.
        pedacos += re.findall(r">([^<>]+)<", marcacao)
        pedacos += re.findall(
            r'(?:title|aria-label|placeholder|alt)="([^"]*)"', marcacao)
        # 2. No JavaScript, so o que vira texto na tela.
        script = re.sub(r"/\*.*?\*/", " ", script, flags=re.S)
        script = re.sub(r"(?m)^\s*//.*$", " ", script)
        pedacos += re.findall(
            r'(?:textContent|placeholder|title|rotulo|muitos|frase|ariaLabel)'
            r'\s*[:=]\s*"([^"]*)"', script)
        pedacos += re.findall(r'setAttribute\(\s*"aria-label"\s*,\s*"([^"]*)"',
                              script)
        return [p for p in pedacos if p.strip()]

    def test_6_nenhuma_palavra_proibida_no_texto_da_tela(self):
        erros = []
        for pedaco in self.texto_visivel():
            baixo = pedaco.lower()
            for palavra, troca in PROIBIDAS.items():
                if re.search(r"\b%s\b" % re.escape(palavra), baixo):
                    erros.append("%r em %r (diga %r)"
                                 % (palavra, pedaco.strip()[:60], troca))
        self.assertEqual(erros, [], "inglês na tela: " + " | ".join(erros))

    def test_6b_a_extracao_de_texto_visivel_acha_texto_de_verdade(self):
        """A guarda do item 6, e a mais necessaria de todas: uma expressao que
        deixa de casar transforma este arquivo num teste que aprova qualquer
        coisa."""
        pedacos = self.texto_visivel()
        # O piso subiu de 60 para 100 na Fatia 2, depois de o vigia passar a
        # ler o painel.js: medido em 29/08/2026, a extracao acha bem mais que
        # isso. Um vigia que passa vazio nao vigia nada, e este numero e o que
        # transforma "a extracao quebrou" em erro em vez de silencio.
        self.assertGreaterEqual(
            len(pedacos), 100,
            "so %d pedacos de texto extraidos da tela — ela tem muito "
            "mais. A extracao quebrou." % len(pedacos))
        junto = " ".join(pedacos)
        for esperado in ("painel", "Conectar", "projeto"):
            self.assertIn(esperado, junto,
                          "nao achei %r no texto visivel — extracao suspeita."
                          % esperado)

    def test_6d_a_extracao_alcanca_o_painel_js(self):
        """A guarda especifica do buraco de 28/08/2026.

        Sem esta assercao, alguem que apagasse a leitura do `painel.js` veria
        o `test_6b` continuar verde (o HTML sozinho ja passa do piso), e o
        vocabulario da tela inteira voltaria a nao ser conferido por ninguem.
        """
        junto = " ".join(self.texto_visivel())
        do_js = [p for p in PAINEL_JS.read_text(encoding="utf-8").splitlines()
                 if "textContent" in p and '"' in p]
        self.assertTrue(do_js, "o painel.js nao escreve texto? extracao suspeita")
        self.assertIn("assets/painel.js", str(PAINEL_JS).replace("\\", "/"))
        # MEDIDO em 29/08/2026: com o painel.js sao 103 pedacos e 2990
        # caracteres; SEM ele, 61 pedacos e 1991 caracteres. O piso de 2500
        # fica entre os dois de proposito — e o unico numero que distingue
        # "a extracao le os dois arquivos" de "voltou a ler so o HTML".
        self.assertGreater(
            len(junto), 2500,
            "o texto visivel encolheu — o painel.js saiu da extracao?")

    def test_6c_a_busca_pegaria_a_palavra_se_ela_estivesse_la(self):
        """A guarda da guarda: prova que a comparacao reprova mesmo."""
        falso = 'Ver o <span title="Loading">dashboard</span> agora'
        achou = [p for p in PROIBIDAS
                 if re.search(r"\b%s\b" % p, falso.lower())]
        self.assertEqual(sorted(achou), ["dashboard", "loading"])


# ----------------------------------------------------------- 7: o selo
ESTADOS = ("saudavel", "atencao", "quebrado", "sem_dados")


class OSeloTemQuatroSinais(unittest.TestCase):
    """Item 7.

    Cor sozinha nao e informacao: cerca de 8% dos homens nao distingue verde de
    vermelho, e nenhum leitor de tela le cor. Por isso cada estado carrega
    quatro sinais ao mesmo tempo -- cor, forma, glifo e rotulo escrito -- e os
    quatro estao DECLARADOS NO HTML, nao montados no JavaScript, exatamente
    para poderem ser cobrados por busca como esta.
    """

    def moldes(self):
        m = re.search(r'<template id="moldes-de-selo">(.*?)</template>',
                      html(), re.S)
        self.assertIsNotNone(
            m, "o <template id=\"moldes-de-selo\"> sumiu do index.html — sem "
               "ele o item 7 do design nao tem como ser verificado.")
        return m.group(1)

    def molde_de(self, estado):
        corpo = self.moldes()
        i = corpo.index('data-selo="%s"' % estado)
        fim = corpo.find("data-selo=", i + 10)
        return corpo[i:fim if fim > 0 else len(corpo)]

    def test_7_cada_estado_tem_cor_forma_glifo_e_rotulo(self):
        rotulos = {"saudavel": "saudável", "atencao": "atenção",
                   "quebrado": "quebrado", "sem_dados": "sem dados"}
        for e in ESTADOS:
            with self.subTest(estado=e):
                molde = self.molde_de(e)
                # cor: o CSS pinta lendo data-selo, e o token existe.
                self.assertIn('data-selo="%s"' % e, molde)
                self.assertIn("--estado-%s" % e.replace("_", "-"), css(),
                              "o token de cor de %r nao existe no CSS" % e)
                # forma: a classe que o CSS desenha diferente por estado.
                self.assertIn("selo__forma", molde,
                              "%r nao tem forma — sobraria so a cor" % e)
                # glifo: um simbolo textual, que o leitor de tela alcanca.
                self.assertRegex(molde, r"\[(OK|!|X|···|\.\.\.)\]",
                                 "%r nao tem glifo textual" % e)
                # rotulo: a palavra, escrita.
                self.assertIn(rotulos[e], molde,
                              "%r nao tem o rotulo %r escrito"
                              % (e, rotulos[e]))

    def test_7b_os_quatro_estados_estao_todos_la(self):
        """A guarda do item 7. Tres estados passariam nos casos acima sem que
        ninguem notasse o quarto faltando — e o quarto e justamente o `sem
        dados`, que existe para o painel poder dizer "nao sei"."""
        corpo = self.moldes()
        achados = re.findall(r'data-selo="([a-z_]+)"', corpo)
        self.assertEqual(sorted(set(achados)), sorted(ESTADOS),
                         "o template declara %s" % sorted(set(achados)))


# ------------------------------------------------------- 8: o carimbo
class NenhumNumeroSemCarimbo(unittest.TestCase):
    """Item 8, e o mais importante dos oito.

    "3 pendencias" sem data e uma afirmacao sobre o presente feita com dado de
    ontem. E a lei 2 inteira num numero so: quem le acredita que aquilo vale
    agora. Toda funcao que escreve numero na tela tem de escrever tambem
    quando aquilo foi medido.

    ARMADILHA QUE ESTE CASO EVITA, e ela estava escrita no plano: implementar
    o item 8 como busca de texto e a busca nao achar numero nenhum. O teste
    passaria verde sem ter examinado coisa alguma. Por isso o primeiro caso
    exige uma populacao minima ANTES de conferir qualquer carimbo.
    """

    # Escrever na tela. `texto:` entra porque a regua de contadores passa o
    # numero por `selo(estado, {texto: ...})`, e nao por textContent direto.
    ESCREVE = re.compile(r"\.textContent\s*=|\.title\s*=|\btexto\s*:")
    # Um numero CALCULADO. Digito solto nao serve: "Adiar 24 horas" e rotulo
    # fixo, nao medicao — reprovar por causa dele treinaria a gente a ignorar
    # este teste, que e como um teste morre.
    NUMERO = re.compile(r"\.length\b|conta\[|Number\(|parseInt\(")
    # Carimbar. SO as duas funcoes que transformam data em palavra contam:
    # `haQuanto()` ("medido há 14 minutos") e `hora()` ("Mostrando a medição
    # de 08:14"). A primeira versao aceitava tambem a palavra "carimbo" solta,
    # e a prova por mutacao derrubou isso na hora: apagando o texto do carimbo
    # da lista de projetos, o teste continuou verde — porque a VARIAVEL ainda
    # se chamava `carimbo`. Detector que se satisfaz com o nome de uma variavel
    # verifica ortografia, nao comportamento.
    # (`carimboDe()` tambem nao conta: ela so LE a data, quem a escreve na tela
    # e sempre uma das duas acima.)
    CARIMBO = re.compile(r"haQuanto\(|\bhora\(")
    # Ler dado medido.
    DADO = re.compile(r"\bESTADO\b|\bprojetos\b|\bCOMPUTADORES\b|carimboDe\(|"
                      r"\.pendencias\b|\.arquivadas\b|d\.maquinas")

    TEXTO_LITERAL = re.compile(r'"(?:[^"\\]|\\.)*"' + r"|'(?:[^'\\]|\\.)*'")

    def script(self):
        """O script da tela -- `assets/painel.js`, desde a correcao da CSP."""
        return PAINEL_JS.read_text(encoding="utf-8")

    def sem_literais(self, corpo):
        """Tira comentario e cadeia de texto. Um numero DENTRO de aspas e
        rotulo escrito a mao; o que esta regra persegue e numero calculado."""
        corpo = re.sub(r"/\*.*?\*/", " ", corpo, flags=re.S)
        corpo = re.sub(r"(?m)^\s*//.*$", " ", corpo)
        return self.TEXTO_LITERAL.sub(" ", corpo)

    def funcoes(self):
        """Cada funcao de primeiro nivel do script, com nome e corpo."""
        linhas = self.script().split("\n")
        achadas = {}
        for i, linha in enumerate(linhas):
            m = re.match(r"(?:async )?function ([A-Za-z_$][\w$]*)\s*\(", linha)
            if not m:
                continue
            fim = i + 1
            while fim < len(linhas) and linhas[fim] != "}":
                fim += 1
            achadas[m.group(1)] = "\n".join(linhas[i:fim + 1])
        return achadas

    def test_8a_a_extracao_enxerga_a_tela_inteira(self):
        """A GUARDA, e ela vem primeiro de proposito: enquanto ela nao passa,
        nenhuma afirmacao sobre carimbo vale nada.

        Os numeros abaixo sao o tamanho real da tela hoje, com folga para
        baixo. Se a leitura quebrar — a expressao das funcoes, o recorte do
        `<script>` —, e aqui que aparece, e nao num caso que passa vazio.
        """
        fs = self.funcoes()
        self.assertGreaterEqual(
            len(fs), 30,
            "so %d funcoes lidas de assets/painel.js; a tela tem mais de 40. O "
            "leitor quebrou e os casos seguintes passariam vazios." % len(fs))
        escritas = len(re.findall(r"\.textContent\s*=", self.script()))
        self.assertGreaterEqual(
            escritas, 50,
            "so %d escritas de texto na tela — a tela faz mais de 80."
            % escritas)
        carimbos = len(self.CARIMBO.findall(self.script()))
        self.assertGreaterEqual(
            carimbos, 15,
            "so %d carimbos na tela inteira. Ou eles sumiram, ou a busca "
            "quebrou; nos dois casos o item 8 parou de ser verificado."
            % carimbos)

    def test_8b_nenhuma_frase_poe_numero_calculado_sem_a_funcao_carimbar(self):
        """A conta e feita FRASE a frase, nao funcao a funcao.

        A primeira versao deste caso olhava a funcao inteira e reprovava
        `pdCobrar`, que le `d.chaves.length` so para escolher entre dois
        textos — nenhum numero chega a tela ali. Teste que reprova codigo
        correto e desligado em duas semanas, e aí ele nao protege mais nada.
        """
        nuas = []
        vistas = 0
        for nome, corpo in self.funcoes().items():
            for frase in self.sem_literais(corpo).split(";"):
                if self.ESCREVE.search(frase) and self.NUMERO.search(frase):
                    vistas += 1
                    if not self.CARIMBO.search(corpo):
                        nuas.append("%s: %s"
                                    % (nome, " ".join(frase.split())[:70]))
        self.assertGreater(
            vistas, 0,
            "nenhuma escrita de numero encontrada — a busca quebrou e este "
            "caso passaria vazio.")
        self.assertEqual(
            nuas, [],
            "numero na tela sem dizer quando foi medido: %s" % "; ".join(nuas))

    def test_8c_toda_tela_que_mostra_dado_medido_carimba(self):
        """O item 8 pelo lado largo.

        A conta por frase pega o numero calculado no JavaScript. Mas a maior
        parte dos numeros deste painel chega pronta dentro do texto que o
        servidor mandou — "3 commits nao publicados desde 11/08" e uma cadeia
        so. Nenhuma busca por digito acha esses. O que da para cobrar, e vale
        mais, e o nivel acima: quem desenha dado medido, carimba.
        """
        fs = self.funcoes()
        desenham = [n for n, c in fs.items()
                    if self.DADO.search(c)
                    and re.search(r"\.textContent\s*=|\.append\(", c)]
        self.assertGreaterEqual(
            len(desenham), 6,
            "so %d funcoes desenham dado medido; sao pelo menos 9 (painel, "
            "projeto, alerta, arquivados, computadores...). A busca quebrou."
            % len(desenham))
        nuas = [n for n in desenham if not self.CARIMBO.search(fs[n])]
        self.assertEqual(
            nuas, [],
            "estas telas mostram dado medido sem dizer de quando ele e: %s"
            % ", ".join(nuas))

    def test_8d_a_deteccao_reprovaria_uma_funcao_nua(self):
        """A guarda da guarda: prova que os casos acima sabem reprovar, e que
        sabem NAO reprovar o numero que e so rotulo."""
        nua = 'function ruim() {\n  x.textContent = conta[e] + " itens";\n}'
        self.assertTrue(self.ESCREVE.search(nua))
        self.assertTrue(self.NUMERO.search(self.sem_literais(nua)))
        self.assertFalse(self.CARIMBO.search(nua))

        boa = nua.replace("}", '  y.textContent = haQuanto(i);\n}')
        self.assertTrue(self.CARIMBO.search(boa))

        rotulo = 'function ok() {\n  b.textContent = "Adiar 24 horas";\n}'
        self.assertFalse(self.NUMERO.search(self.sem_literais(rotulo)),
                         "numero dentro de aspas e rotulo fixo, nao medicao")


# ------------------------------------------- o que este arquivo NAO cobre
NAO_AUTOMATIZAVEIS = (
    "item 5 — em 360x640, a linha de projeto mostra selo, nome, motivo e "
    "carimbo juntos, e a pagina nao rola na horizontal. Exige olho humano num "
    "navegador de verdade.",
    "o clique da etapa 14 — cada botao fazer o que promete. Exige a mao de "
    "alguem, porque a entrada do painel depende do PIN do Windows.",
)


class ATestemunhaDoQueFaltou(unittest.TestCase):
    """Um teste sobre o proprio teste.

    Ele nao verifica a tela: verifica que este arquivo continua confessando o
    que nao cobre. Se alguem apagar a lista achando que e enfeite, a suite fica
    vermelha — que e exatamente o que se quer, porque uma lista de oito itens
    com seis verificados e dois calados se le como oito verificados.
    """

    def test_a_lista_do_que_falta_continua_dita_em_voz_alta(self):
        self.assertEqual(len(NAO_AUTOMATIZAVEIS), 2)
        for item in NAO_AUTOMATIZAVEIS:
            self.assertIn("—", item)

    def test_os_seis_itens_automatizaveis_tem_caso(self):
        """Amarra a lista do design.md aos casos deste arquivo. Item novo la
        sem caso aqui deixa de passar despercebido."""
        fonte = Path(__file__).read_text(encoding="utf-8")
        for n in (1, 2, 3, 4, 6, 7, 8):
            self.assertRegex(
                fonte, r"def test_%d[a-c]?_" % n,
                "o item %d da lista do design.md nao tem caso neste arquivo"
                % n)


def resumo_do_que_falta():
    print("\n%d dos 8 itens desta lista NAO sao automatizaveis:"
          % len(NAO_AUTOMATIZAVEIS))
    for item in NAO_AUTOMATIZAVEIS:
        print("  - " + item)
    print("Os outros 6 acabaram de ser verificados contra os arquivos de "
          "verdade.\n")


class ORoteiroChamaAsTelasPeloNomeDelas(unittest.TestCase):
    """A verificacao de 28/08/2026 achou isto olhando, nao testando: a tela diz
    **Computadores** e `docs/operacao/conectar-uma-maquina.md` mandava clicar em
    **Maquinas**. O dono nao acha o botao, e conclui que o software esta
    quebrado.

    O vigia e estreito de proposito. Um teste que tentasse adivinhar quais
    palavras em negrito de um roteiro sao rotulo de tela reprovaria em cima de
    enfase comum, e teste ruidoso e teste que a gente aprende a ignorar. Este
    aqui pergunta uma coisa so: os quatro nomes do menu, como estao no HTML,
    sao os nomes que a documentacao usa?
    """

    DOCS = [AQUI / "README.md"] + sorted((AQUI / "docs" / "operacao").glob("*.md"))

    def menu(self):
        """Os rotulos do menu, lidos do HTML — nao uma copia escrita aqui."""
        bloco = re.search(r"<nav.*?</nav>", html(), re.S)
        self.assertIsNotNone(bloco, "o menu sumiu do index.html")
        nomes = re.findall(r'data-tela="[^"]+"\s*>([^<]+)<', bloco.group(0))
        self.assertEqual(len(nomes), 4, nomes)
        return nomes

    def test_o_menu_tem_os_quatro_nomes_esperados(self):
        """Se o menu mudar de forma, o teste abaixo passa vazio e nao vigia."""
        self.assertEqual(self.menu(),
                         ["Painel", "Conectar projeto", "Computadores",
                          "Formas de entrar"])

    def test_nenhum_roteiro_manda_clicar_num_botao_que_nao_existe(self):
        # O par: o nome errado que ja custou uma verificacao, e o certo.
        # Acrescentar uma linha aqui e o jeito de registrar a proxima deriva.
        trocas = {"Máquinas": "Computadores"}
        for doc in self.DOCS:
            texto = doc.read_text(encoding="utf-8")
            for errado, certo in trocas.items():
                self.assertIn(certo, self.menu(), certo)
                with self.subTest(doc=doc.name, palavra=errado):
                    self.assertNotIn(
                        "**%s**" % errado, texto,
                        "%s manda clicar em **%s**; a tela diz **%s**"
                        % (doc.name, errado, certo))


if __name__ == "__main__":
    # `exit=False` sozinho devolvia 0 mesmo com caso reprovado: em 28/08/2026
    # este arquivo imprimiu FAILED (failures=4) e a CI seguiu verde. O codigo
    # de saida tem de contar a verdade, senao o passo da CI nao verifica nada.
    _res = unittest.main(verbosity=0, exit=False).result
    resumo_do_que_falta()
    sys.exit(0 if _res.wasSuccessful() else 1)
