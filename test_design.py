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
    # `projetos` como PALAVRA solta (a lista, ou `m.projetos`). Como pedaco de
    # rota (`/api/projetos/mostrar`) ou de classe (`projetos-vistos`) nao e dado
    # medido: a chave "Mostrar no painel" nao escreve numero nenhum.
    DADO = re.compile(r"\bESTADO\b|(?<![/\w-])projetos(?![\w/-])|\bCOMPUTADORES\b|carimboDe\(|"
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
        """Se o menu mudar de forma, o teste abaixo passa vazio e nao vigia.

        Eram quatro ate a Fatia 2. "Trabalho" e "Consumo" entraram junto com o
        braco: a primeira e onde o dono ve e aprova o que o DERVS faz, a
        segunda e o que torna a semana de observacao uma medicao em vez de uma
        impressao. "Auditoria" entrou na Fase 4 (02/09/2026), entre as duas —
        e' a mesma familia de "o que o DERVS ja fez/esta fazendo" que
        "Trabalho" representa para o conserto, so que para o que ele leu.

        Eram sete ate o menu enxuto: agora sao quatro lugares, e as telas
        antigas viraram abas ou secoes dentro deles (`test_menu.py` cobra o
        desenho completo).
        """
        self.assertEqual(self.menu(),
                         ["Painel", "Consertar", "Conectar", "Conta"])

    def test_nenhum_roteiro_manda_clicar_num_botao_que_nao_existe(self):
        # O par: o nome errado que ja custou uma verificacao, e o certo.
        # Acrescentar uma linha aqui e o jeito de registrar a proxima deriva.
        trocas = {"Máquinas": "Computadores"}
        for doc in self.DOCS:
            texto = doc.read_text(encoding="utf-8")
            for errado, certo in trocas.items():
                # "Computadores" deixou de ser item do menu: e' o titulo de
                # uma secao da tela Conectar. O teste cobra o titulo.
                self.assertIn(">%s<" % certo, html(), certo)
                with self.subTest(doc=doc.name, palavra=errado):
                    self.assertNotIn(
                        "**%s**" % errado, texto,
                        "%s manda clicar em **%s**; a tela diz **%s**"
                        % (doc.name, errado, certo))


class ATelaDeComputadoresCasaDosDoisLados(unittest.TestCase):
    """O CSS desta tela pende de classes que o JAVASCRIPT inventa em tempo de
    execucao. Renomear um dos lados nao quebra nada: a regra simplesmente para
    de casar, e a tela volta ao que era em 29/08/2026 -- coluna de texto
    espremida a 111px e a permissao de rodar codigo escrita no mesmo cinza
    mudo do horario. VERDE, e errada.

    E o mesmo modo de falha que o CLAUDE.md ja registra para a permissao por
    caminho exato de `painel.css`: "renomear um dos dois a desliga em
    silencio". La um teste cobra os dois nomes; aqui nao havia nenhum, porque
    a tela nunca teve teste.
    """

    def marcacao(self):
        return HTML.read_text(encoding="utf-8")

    def script(self):
        return PAINEL_JS.read_text(encoding="utf-8")

    def folha(self):
        return sem_comentarios_css(PAINEL_CSS.read_text(encoding="utf-8"))

    def classes_do_script(self):
        """Os nomes que aparecem DENTRO de uma string do `painel.js`.

        Cada literal e lido inteiro e separado dos outros. A primeira versao
        buscava `"[^"]*\\bnome\\b[^"]*"` no arquivo cru e ATRAVESSAVA aspas:
        casava da aspa que FECHA um literal ate a que ABRE o proximo, varrendo
        o codigo entre os dois. Com isso `trabalha.dataset.permissao = ...`,
        que nao e string nenhuma, satisfazia a busca -- e o teste aprovava um
        `className` renomeado. Pego pela sabotagem em 29/08/2026.

        `[^"\\\\\\n]` proibe a quebra de linha de proposito: e ela que impede
        um literal de emendar no seguinte.
        """
        nomes = set()
        for literal in re.findall(r'"(?:[^"\\\n]|\\.)*"', self.script()):
            # O token vai ate o fim do identificador, MAIUSCULA INCLUSIVE.
            # Com `[a-z][a-z-]*` a leitura parava na primeira maiuscula, e
            # `"permissaoX"` continuava entregando a palavra `permissao`: um
            # `className` renomeado passava batido. Segunda sabotagem do mesmo
            # caso, no mesmo dia -- a primeira correcao nao tinha bastado.
            nomes.update(re.findall(r"[A-Za-z][A-Za-z0-9_-]*", literal))
        return nomes

    def test_a_lista_carrega_a_classe_que_o_css_procura(self):
        """Sem `computadores` no `ul`, TODAS as regras abaixo viram letra
        morta de uma vez -- e este e o unico ponto onde isso acontece.

        Le o ATRIBUTO `class`, e nao a marca inteira: `id="lista-computadores"`
        ja contem a palavra, entao procura-la no `<ul ...>` cru aprovava a
        marca sem classe nenhuma. Era um teste que so podia passar.
        """
        m = re.search(r'<ul([^>]*)id="lista-computadores"([^>]*)>',
                      self.marcacao())
        self.assertIsNotNone(m, "o `ul#lista-computadores` sumiu do index.html")
        atributos = m.group(1) + m.group(2)
        classe = re.search(r'class="([^"]*)"', atributos)
        self.assertIsNotNone(classe, "o `ul` ficou sem atributo `class`")
        self.assertIn("computadores", classe.group(1).split(),
                      "o `ul` perdeu a classe `computadores`; o CSS da tela "
                      "inteira deixa de casar sem erro nenhum. class=%r"
                      % classe.group(1))

    def test_toda_classe_que_o_css_estiliza_e_produzida_pelo_script(self):
        """O elo que ninguem ve quebrar. Cada classe usada num seletor de
        `.computadores` exige o mesmo nome saindo do JS."""
        alvos = set()
        for seletor, _ in re.findall(r"([^{}]+)\{([^{}]*)\}", self.folha()):
            if ".computadores" not in seletor:
                continue
            alvos.update(c for c in re.findall(r"\.([a-z][a-z-]*)", seletor)
                         if c != "computadores")
        self.assertGreaterEqual(len(alvos), 4, "o teste parou de achar regra; "
                                "sem isto ele aprova qualquer coisa")
        nomes = self.classes_do_script()
        for classe in sorted(alvos):
            with self.subTest(classe=classe):
                self.assertIn(
                    classe, nomes,
                    "o CSS estiliza `.computadores ... .%s`, e `painel.js` nao "
                    "escreve essa classe em string nenhuma." % classe)

    def test_os_dois_estados_da_permissao_existem_dos_dois_lados(self):
        """`[data-permissao="mede"]` e o que tira a caixa do estado seguro. Se
        o JS passar a escrever outra palavra, os dois estados ficam iguais e a
        tela para de responder a pergunta que ela existe para responder:
        QUAIS destas maquinas podem rodar codigo?"""
        no_css = set(re.findall(r'\[data-permissao="([a-z]+)"\]', self.folha()))
        no_js = set(re.findall(r'permissao\s*=\s*[^;]*?"([a-z]+)"[^;]*?"([a-z]+)"',
                               self.script()))
        no_js = set(sum(no_js, ()))
        self.assertTrue(no_css, "sumiu o seletor de estado da permissao")
        self.assertTrue(no_css <= no_js,
                        "o CSS pinta %s e o JS escreve %s" % (no_css, no_js))

    def test_o_estado_seguro_nao_usa_borda_fraca_como_unico_contorno(self):
        """Regra 3 da cor: onde o contorno E o sinal, ele passa de 3:1. Um
        `--borda` (1,39:1) ali promete uma caixa que o olho nao acha -- pior
        que caixa nenhuma. A tentacao de escrever isso e real: foi o primeiro
        rascunho desta mesma regra, em 29/08/2026."""
        bloco = re.search(r'\.computadores\s+\.permissao\[data-permissao='
                          r'"mede"\]\s*\{([^}]*)\}', self.folha())
        self.assertIsNotNone(bloco, "o estado seguro da permissao sumiu do CSS")
        self.assertNotIn("var(--borda)", bloco.group(1),
                         "contorno de 1,39:1 como unico sinal da caixa; use "
                         "`transparent` (sem caixa) ou `--borda-forte`.")

    def test_o_botao_de_remover_recua_no_texto_e_nao_no_contorno(self):
        """A hierarquia se faz no texto. Enfraquecer o CONTORNO resolveria a
        aparencia e criaria um alvo de toque que ninguem acha -- trocar um
        defeito de design por um de acessibilidade nao e conserto."""
        bloco = re.search(r'\.computadores\s+\.acoes\s+\.botao--remover\s*\{'
                          r'([^}]*)\}', self.folha())
        self.assertIsNotNone(bloco, "o freio visual do `Remover` sumiu")
        self.assertIn("color:", bloco.group(1))
        self.assertNotIn("border-color", bloco.group(1),
                         "o contorno do `Remover` tem de continuar igual ao do "
                         "outro botao: e ele que diz onde o clique vale.")


class ATelaDeAuditoriaCasaOsTresLados(unittest.TestCase):
    """Etapa 6 do plano da Auditoria Profunda (02/09/2026).

    A armadilha da sabotagem 6b: um guarda escrito como `assertIn("auditoria",
    html())` NAO PODE REPROVAR, porque `id="tela-auditoria"` ja contem a
    palavra. Por isso este caso casa as TRES ocorrencias -- a `<section id>`,
    o `data-tela` da navegacao e o `case` do `navegar()` -- e nenhuma delas
    sozinha basta.
    """

    def html_texto(self):
        return HTML.read_text(encoding="utf-8")

    def js_texto(self):
        return PAINEL_JS.read_text(encoding="utf-8")

    def test_a_secao_o_link_e_o_case_existem_e_casam_entre_si(self):
        h = self.html_texto()
        self.assertIn('id="tela-auditoria"', h,
                      "a <section id=\"tela-auditoria\"> sumiu do index.html")
        # A auditoria e' uma aba de "Consertar", nao mais item do menu.
        self.assertIn('data-aba="auditoria"', h,
                      "a aba com data-aba=\"auditoria\" sumiu")
        j = self.js_texto()
        self.assertRegex(
            j, r'case\s+"auditoria"\s*:',
            "o case \"auditoria\": sumiu do switch de navegar() em painel.js")

    def test_nenhum_achado_e_escrito_com_innerhtml(self):
        """Sabotagem 6c: achado e' texto do repositorio auditado. Se algum dia
        alguem trocar um `.textContent` por `.innerHTML` no desenho do achado,
        este caso tem de acusar."""
        j = self.js_texto()
        i = j.index("function desenharListaDeAchados")
        fim = j.index("\n}\n", i)
        corpo = j[i:fim]
        self.assertNotIn("innerHTML", corpo,
                         "achado escrito com innerHTML — quarta barreira "
                         "furada, texto do repositorio auditado pode virar "
                         "marcacao")
        self.assertIn("criterio(", corpo,
                      "desenharListaDeAchados nao chama criterio() — a busca "
                      "esta olhando para o lugar errado")

    def test_os_tres_estados_de_dado_tem_frases_diferentes(self):
        """Sabotagem 6d, e a lei 2: 'nunca auditado', 'auditoria falhou: '
        e '0 achados' nao podem se confundir. Zero achados so vale quando a
        corrida terminou 'ok' -- nunca quando ela falhou."""
        j = self.js_texto()
        i = j.index("async function pintarAuditoria")
        fim = j.index("\nasync function pedirAuditoria", i)
        corpo = j[i:fim]
        nunca = "ainda não foi auditado"
        falhou = "a auditoria falhou: "
        zero = "0 achados"
        for frase in (nunca, falhou):
            self.assertIn(frase, corpo,
                          "a frase %r sumiu de pintarAuditoria" % frase)
        self.assertIn(zero, self.js_texto(),
                      "a frase %r sumiu de desenharListaDeAchados" % zero)
        # As tres tem de ser distintas — nenhuma pode conter as outras.
        self.assertNotIn(nunca, falhou)
        self.assertNotIn(falhou, zero)
        self.assertNotIn(zero, nunca)
        # A frase de erro so pode aparecer dentro do `if` que confere que a
        # corrida NAO terminou 'ok' — nunca incondicionalmente.
        i_erro = corpo.index(falhou)
        antes = corpo[:i_erro]
        self.assertIn('corrida.estado !== "ok"', antes,
                      "a frase de erro nao esta guardada pela conferencia do "
                      "estado da corrida — poderia aparecer com a corrida ok")

    def test_nenhum_arquivo_novo_em_assets(self):
        """Sabotagem 6e. A lista de estaticos nasce lendo `assets/` na SUBIDA
        do servidor, e so `painel.js`/`painel.css` exigem sessao por caminho
        EXATO. Um `assets/auditoria.js` nasceria aberto ao publico."""
        nomes = sorted(p.name for p in (AQUI / "assets").iterdir()
                       if p.is_file())
        # A lista de hoje, e nao um numero magico: cresce so quando alguem
        # revisa deliberadamente `servir.ESTATICOS_COM_SESSAO`, nunca de
        # gancho num novo arquivo desta etapa.
        self.assertEqual(
            nomes,
            ["CREDITOS.md", "cortina.css", "cortina.js", "dervs.css",
             "favicon-180.png", "favicon.svg", "logo.svg", "painel.css",
             "painel.js", "portas.js", "selos.svg"],
            "assets/ ganhou ou perdeu arquivo — a tela de Auditoria nao "
            "pode trazer nenhum novo (ver CLAUDE.md, caminho EXATO)")
        self.assertIn("painel.js", nomes)
        self.assertIn("painel.css", nomes)


class OCardEODetalheMostramServidoresSeparados(unittest.TestCase):
    """Etapa 6 do plano 'servidores multiplos'.

    O contrato do dado ja esta pinado em `regras.py`: a camada `github` carrega
    `sites`, uma lista com um item por servidor. Esta classe cobra que o CARD
    do projeto (painel principal) e a TELA DE DETALHE leem esse formato — sem
    inventar um quinto estado de selo, e sem esquecer o carimbo por servidor.

    Nao ha runtime de JS neste repositorio (CLAUDE.md, `test_design.PAINEL_JS`
    ja documenta isso para a tela de Auditoria): os casos abaixo leem
    `painel.js`/`painel.css` como TEXTO. "O selo lista os dois nomes na tela"
    fica para o clique -- `verificacao.md` da fase 6.
    """

    def script(self):
        return PAINEL_JS.read_text(encoding="utf-8")

    def folha(self):
        return sem_comentarios_css(PAINEL_CSS.read_text(encoding="utf-8"))

    def classes_do_script(self):
        """Mesma extracao de `ATelaDeComputadoresCasaDosDoisLados` — cada
        literal e' lido inteiro, para nao atravessar aspas nem parar na
        primeira maiuscula (as duas sabotagens de 29/08/2026). O `-` entra no
        conjunto: sem ele, `marca--servidores` cortaria em `marca` e o teste
        aprovaria uma classe qualquer que comecasse com `marca`."""
        nomes = set()
        for literal in re.findall(r'"(?:[^"\\\n]|\\.)*"', self.script()):
            nomes.update(re.findall(r"[A-Za-z][A-Za-z0-9_-]*", literal))
        return nomes

    def classes_da_folha(self):
        """Cada nome de classe usado num seletor CSS, INTEIRO — casamento
        por substring (`assertIn` puro) deixaria `.marca--servidoresX`
        aprovar a busca por `.marca--servidores`, porque uma string contem a
        outra. Pego sabotando: a primeira versao deste caso nao reprovava."""
        return set(re.findall(r"\.([A-Za-z][A-Za-z0-9_-]*)", self.folha()))

    def test_a_classe_do_selo_de_servidores_casa_dos_dois_lados(self):
        """O selo "servidor(es)" do card usa `.marca--servidores`. Renomear
        so no CSS ou so no JS tem de acusar — sabotado nos dois sentidos
        antes de aceitar este caso (ver 'sabotar antes de aceitar' no plano)."""
        self.assertIn(
            "marca--servidores", self.classes_da_folha(),
            "o CSS nao estiliza `.marca--servidores` — a busca quebrou, ou "
            "a classe sumiu do painel.css")
        self.assertIn(
            "marca--servidores", self.classes_do_script(),
            "o `painel.js` nao escreve a classe `marca--servidores` em "
            "string nenhuma — o selo do card ficou sem o recuo do CSS")

    def test_os_rotulos_de_contagem_existem_e_o_plural_comeca_em_dois(self):
        """Os quatro textos de `design.md`, secao 'O selo servidor(es)'."""
        j = self.script()
        self.assertIn('"em 1 servidor"', j,
                      "o rotulo do singular sumiu — 'em 1 servidor', sem s")
        self.assertNotIn('"em 1 servidores"', j,
                         "o singular nao pode escrever 'servidores' com s")
        self.assertIn('"em " + n + " servidores"', j,
                      "o rotulo do plural nao monta 'em N servidores' a "
                      "partir da contagem — a busca quebrou, ou o texto "
                      "virou uma frase fixa")
        self.assertIn('"não está em nenhum servidor cadastrado"', j,
                      "sumiu o rotulo de 'zero servidores' do selo do card")
        self.assertIn('"não deu para conferir"', j,
                      "sumiu o rotulo de 'nao sei' — ESTADO_DA_PORTA.sem_dados")

    def test_a_linha_de_ausencia_na_tela_de_detalhe_e_a_frase_do_design(self):
        """A tela de detalhe usa a frase COM maiuscula e ponto final —
        'Nao está em nenhum servidor cadastrado.' — diferente do rotulo do
        card, que e' minusculo e sem ponto. As duas existem, e sao textos
        distintos (design.md nunca deixa 'nao se aplica' escapar)."""
        j = self.script()
        self.assertIn('"Não está em nenhum servidor cadastrado."', j,
                      "a linha de ausencia da tela de detalhe sumiu, ou "
                      "perdeu a maiuscula/o ponto final que a distingue do "
                      "rotulo do card")
        self.assertNotIn("não se aplica", j.lower(),
                         "'nao se aplica' e' proibido pelo design.md para "
                         "este estado — ausencia tem frase propria")

    def test_o_criterio_por_servidor_chama_haquanto(self):
        """test_8c (o item mais importante dos oito) pelo lado desta etapa:
        a funcao que desenha um criterio por servidor tem de carimbar CADA
        item com a PROPRIA medicao — nunca o carimbo geral do `gh`, que
        pertence a leitura inteira do GitHub e nao a cada servidor."""
        j = self.script()
        i = j.index("function pintarProjeto")
        fim = j.index("\nfunction pintarAlertasDoProjeto", i)
        corpo = j[i:fim]
        self.assertIn("sitesDoProjeto(gh)", corpo,
                      "pintarProjeto parou de ler a lista de sites por "
                      "servidor")
        self.assertIn("haQuanto(item.medido_em)", corpo,
                      "o criterio por servidor nao carimba com a medicao "
                      "DAQUELE item — um numero sem saber de quando ele e'")

    def test_o_selo_do_card_nunca_e_um_quinto_estado(self):
        """`seloDeServidores` so pode devolver os tres estados que
        `marcaDaPorta`/`ESTADO_DA_PORTA` ja conhecem — design.md e' explicito:
        'Nenhum quinto estado de selo e' criado'."""
        j = self.script()
        i = j.index("function seloDeServidores")
        fim = j.index("\n}\n", i)
        corpo = j[i:fim]
        estados = set(re.findall(r'estado:\s*"([a-z_]+)"', corpo))
        self.assertTrue(estados, "a busca de estados em seloDeServidores "
                        "nao achou nada — a extracao quebrou")
        self.assertTrue(
            estados <= {"conectado", "desconectado", "sem_dados"},
            "seloDeServidores devolve %s — so os tres estados de "
            "ESTADO_DA_PORTA sao permitidos" % estados)


class OCartaoDeConectarListaOsServidores(unittest.TestCase):
    """Etapa 7 do plano 'servidores multiplos'.

    O cartao "O seu servidor" virou "Seus servidores": cadastra, lista,
    apaga servidor, e o formulario de endereco vive DENTRO de cada bloco. Os
    textos abaixo sao os de `design.md`, secao `textos`, palavra por
    palavra -- divergir um caractere e' o mesmo defeito que "Máquinas" no
    roteiro velho (`ORoteiroChamaAsTelasPeloNomeDelas`).
    """

    def script(self):
        return PAINEL_JS.read_text(encoding="utf-8")

    def folha(self):
        return sem_comentarios_css(PAINEL_CSS.read_text(encoding="utf-8"))

    def classes_do_script(self):
        """Mesma extracao das outras classes deste arquivo: cada literal
        lido inteiro, sem atravessar aspas nem parar na primeira maiuscula
        (as duas sabotagens de 29/08/2026)."""
        nomes = set()
        for literal in re.findall(r'"(?:[^"\\\n]|\\.)*"', self.script()):
            nomes.update(re.findall(r"[A-Za-z][A-Za-z0-9_-]*", literal))
        return nomes

    def classes_da_folha(self):
        """Nome de classe INTEIRO -- `assertIn` puro deixaria `.servidorX`
        aprovar a busca por `.servidor`, porque uma string contem a outra."""
        return set(re.findall(r"\.([A-Za-z][A-Za-z0-9_-]*)", self.folha()))

    def frases_concatenadas(self):
        """`design.md` escreve frases longas, e o painel.js as monta com
        `+` entre literais quebrados em varias linhas -- um `assertIn` cru
        contra o arquivo inteiro nunca acha a frase inteira. Esta funcao
        junta cada CADEIA de literais unidos por `+` numa string so, e e' AI
        que a frase completa aparece."""
        script = re.sub(r"/\*.*?\*/", " ", self.script(), flags=re.S)
        script = re.sub(r"(?m)^\s*//.*$", " ", script)
        cadeias = re.findall(
            r'"(?:[^"\\]|\\.)*"(?:\s*\+\s*"(?:[^"\\]|\\.)*")*', script)
        return ["".join(re.findall(r'"((?:[^"\\]|\\.)*)"', c))
                for c in cadeias]

    def test_a_guarda_da_extracao_de_frases_concatenadas(self):
        """Se a busca acima parar de juntar literais quebrados, os testes de
        texto abaixo passariam vazios e mentiriam."""
        junto = self.frases_concatenadas()
        self.assertTrue(
            any("DERVS" in f and len(f) > 80 for f in junto),
            "nenhuma frase longa foi remontada -- a extracao quebrou")

    def test_o_cabecalho_e_os_campos_de_cadastro_existem_palavra_por_palavra(self):
        j = self.script()
        for texto in ("Seus servidores", "Cadastrar servidor",
                      "Nome do servidor",
                      "Padrão de subdomínio (opcional)",
                      "*.tinehost.com.br"):
            with self.subTest(texto=texto):
                self.assertIn(texto, j, "sumiu do painel.js: %r" % texto)

    def test_o_texto_de_ajuda_do_padrao_e_o_do_design(self):
        self.assertIn(
            "Se os projetos deste servidor seguem um padrão de endereço, o "
            "DERVS testa sozinho e sugere o preenchimento — você ainda "
            "confirma antes de qualquer coisa ser gravada.",
            self.frases_concatenadas())

    def test_os_tres_resumos_do_selo_geral_existem(self):
        junto = self.frases_concatenadas()
        self.assertIn(
            "Não consegui ler os servidores desta conta. Isso não quer "
            "dizer que nenhum está cadastrado — quer dizer que não olhei.",
            junto)
        self.assertIn("Há 1 servidor cadastrado.", self.script())
        self.assertIn(
            "Nenhum servidor cadastrado ainda. Cadastre o nome de um "
            "provedor (por exemplo OVH ou TineHost) para começar a gravar "
            "endereços nele.",
            junto)

    def test_a_confirmacao_de_apagar_nomeia_o_que_morre(self):
        self.assertIn(
            "Os endereços gravados nele saem do DERVS. O site em si não é "
            "tocado — só paramos de medir por aqui.",
            self.frases_concatenadas())
        self.assertIn('sim: "Apagar", nao: "Manter"', self.script())

    def test_as_classes_novas_de_servidor_casam_dos_dois_lados(self):
        """Sabotado nos dois sentidos antes de aceitar: renomear so no CSS
        ou so no JS tem de acusar (o molde e' `ATelaDeComputadoresCasaDos
        DoisLados`, ja provado assim em 29/08/2026)."""
        no_css = self.classes_da_folha()
        no_js = self.classes_do_script()
        for classe in ("servidor", "servidor__cabeca", "servidor__nome",
                       "servidor__padrao", "servidor--novo"):
            with self.subTest(classe=classe):
                self.assertIn(classe, no_css,
                              "o painel.css nao estiliza .%s" % classe)
                self.assertIn(classe, no_js,
                              "o painel.js nao escreve a classe %r em "
                              "string nenhuma" % classe)

    def test_a_tela_busca_as_tres_rotas_de_servidor(self):
        """`ATelaSoChamaRotaQueExiste` (test_servir.py) e' quem prova que a
        rota EXISTE de verdade; este caso prova so que a TELA a busca."""
        j = self.script()
        self.assertIn('fetch("/api/servidores")', j)
        self.assertIn('"/api/servidores/guardar"', j)
        self.assertIn('"/api/servidores/remover"', j)

    def test_o_formulario_de_endereco_manda_o_servidor_id(self):
        """A licao do contrato: `guardarEndereco` tem de mandar
        `servidor_id` no corpo -- sem ele `/api/enderecos/guardar` devolve
        400 (servir.py), e o formulario pareceria quebrado sem motivo."""
        j = self.script()
        i = j.index("async function guardarEndereco")
        fim = j.index("\n}\n", i)
        corpo = j[i:fim]
        self.assertIn("servidor_id: servidorId", corpo)

    def test_o_cartao_nao_pinta_lista_nem_formulario_antes_de_ler(self):
        """A armadilha do plano: 'pintar Nenhum servidor cadastrado enquanto
        a leitura ainda nao voltou' e' a lei 2 quebrada na cara do dono. O
        formulario e a lista so entram no cartao DENTRO do `if (leuServ)`."""
        j = self.script()
        i = j.index('titulo: "Seus servidores"')
        fim = j.index("\nfunction formularioDeServidorNovo", i)
        corpo = j[i:fim]
        self.assertIn("if (leuServ) {", corpo,
                      "a lista/formulario de servidor nao esta guardada "
                      "pela leitura -- pintaria antes de /api/servidores "
                      "responder")


class ASugestaoNaTelaPropoeEPara(unittest.TestCase):
    """Etapa 9 do plano 'servidores multiplos'.

    A sugestao de autodeteccao aparece DENTRO do bloco do servidor, acima do
    formulario manual, com contorno `--borda-forte` -- nunca uma cor de
    estado, porque e' proposta, nao veredito. Nada e' gravado sem o clique em
    "Usar este endereço", e ela custa rede so UMA VEZ por servidor com
    padrao, por sessao (`SERVIDORES_JA_SUGERIDOS`) -- sem isso cada repintura
    de `pintarConectar()` dispararia ate 68s de medicao no servidor.
    """

    def script(self):
        return PAINEL_JS.read_text(encoding="utf-8")

    def folha(self):
        return sem_comentarios_css(PAINEL_CSS.read_text(encoding="utf-8"))

    def test_o_texto_da_sugestao_e_os_dois_rotulos_existem_no_fonte(self):
        j = self.script()
        for texto in (
            "O endereço ",
            " respondeu e parece ser deste projeto. Quer usar este endereço "
            "para o ",
            "Usar este endereço",
            "Ignorar",
        ):
            with self.subTest(texto=texto):
                self.assertIn(texto, j, "sumiu do painel.js: %r" % texto)

    def test_a_linha_de_sugestao_usa_borda_forte_nao_cor_de_estado(self):
        """E' a diferenca entre proposta e veredito, e a unica forma
        automatizavel de cobrar isso (design.md, secao 'telas', item 1)."""
        folha = self.folha()
        self.assertIn(".sugestao {", folha,
                      "sumiu o bloco `.sugestao` do painel.css")
        i = folha.index(".sugestao {")
        fim = folha.index("}", i)
        bloco = folha[i:fim]
        self.assertIn("--borda-forte", bloco,
                      "a linha de sugestao perdeu o contorno --borda-forte")
        for proibido in ("--estado-saudavel", "--estado-quebrado"):
            with self.subTest(token=proibido):
                self.assertNotIn(
                    proibido, bloco,
                    "a linha de sugestao usa %r -- e' proposta, nao "
                    "veredito" % proibido)

    def test_o_pedido_de_sugestao_e_guardado_num_set_por_sessao(self):
        """A armadilha do plano: chamar `sugerir` dentro de `pintarConectar()`
        sem o Set dispara ate 68s de medicao a cada um dos tres disparos por
        abertura de tela (`olharOsEnderecos`, `olharOsComputadores`,
        `olharOsServidores`)."""
        j = self.script()
        self.assertIn("SERVIDORES_JA_SUGERIDOS", j,
                      "sumiu a guarda que evita repetir a medicao a cada "
                      "repintura de pintarConectar()")
        i = j.index("function blocoDeServidor")
        fim = j.index("\nfunction ", i + 10)
        corpo = j[i:fim]
        self.assertIn(
            "SERVIDORES_JA_SUGERIDOS.has(item.id)", corpo,
            "blocoDeServidor nao confere o Set antes de pedir a sugestao "
            "-- cada repintura dispararia rede de novo")

    def test_a_tela_busca_a_rota_de_sugerir(self):
        """`ATelaSoChamaRotaQueExiste` (test_servir.py) prova que a rota
        existe de verdade; este caso prova so que a TELA a busca."""
        self.assertIn('"/api/servidores/sugerir"', self.script())

    def test_usar_este_endereco_chama_guardarendereco(self):
        j = self.script()
        i = j.index("function linhaDeSugestao")
        fim = j.index("\nfunction ", i + 10)
        corpo = j[i:fim]
        self.assertIn("guardarEndereco(servidorId, projeto, url)", corpo,
                      "o botao 'Usar este endereço' parou de gravar")

    def test_ignorar_nunca_grava_e_so_some_nesta_sessao(self):
        """'Nada e gravado sem o clique' -- o botao Ignorar nunca pode
        chamar `guardarEndereco`, e some via `SUGESTOES_IGNORADAS`, nunca
        apagando a sugestao do servidor (que reapareceria na proxima
        leitura)."""
        j = self.script()
        i = j.index("function linhaDeSugestao")
        fim = j.index("\nfunction ", i + 10)
        corpo = j[i:fim]
        i2 = corpo.index('"Ignorar"')
        depois = corpo[i2:]
        fim_click = depois.index("});")
        trecho_do_clique = depois[:fim_click]
        self.assertNotIn("guardarEndereco", trecho_do_clique,
                         "Ignorar chama guardarEndereco -- ele nao pode "
                         "gravar nada")
        self.assertIn("SUGESTOES_IGNORADAS.add", trecho_do_clique,
                      "Ignorar nao guarda a escolha -- a sugestao voltaria "
                      "a aparecer sozinha na mesma sessao")


class OCustoDaAuditoriaEmDolar(unittest.TestCase):
    """`custo_usd` e dolar. A tela escrevia `R$` na frente do mesmo numero e
    mostrava R$ 1,00 para US$ 0,998 (visto no site em 02/10/2026): numero errado
    com cara de certo, a Lei 2 deste repositorio."""

    def test_custo_usd_nao_leva_cifrao_de_real(self):
        js = PAINEL_JS.read_text(encoding="utf-8")
        trecho = js[js.index("corrida.custo_usd") - 220: js.index("corrida.custo_usd") + 80]
        self.assertIn("US$", trecho)
        self.assertNotIn("custou R$", trecho)


if __name__ == "__main__":
    # `exit=False` sozinho devolvia 0 mesmo com caso reprovado: em 28/08/2026
    # este arquivo imprimiu FAILED (failures=4) e a CI seguiu verde. O codigo
    # de saida tem de contar a verdade, senao o passo da CI nao verifica nada.
    _res = unittest.main(verbosity=0, exit=False).result
    resumo_do_que_falta()
    sys.exit(0 if _res.wasSuccessful() else 1)
