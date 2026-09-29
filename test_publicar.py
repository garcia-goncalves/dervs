# -*- coding: utf-8 -*-
"""O container recebe o que o codigo le.

POR QUE ESTE ARQUIVO EXISTE.

Em 28/08/2026 o dervs.com.br foi publicado com a verificacao verde, o dominio
respondendo 200 e a aparencia certa na tela. E **ninguem conseguia entrar**: a
unica porta de producao, `/entrar/github`, responde 404 sem `DERVS_GITHUB_ID` e
`DERVS_GITHUB_SECRET`, e nada as levava ate o processo. Em 02/09/2026 o mesmo
formato de defeito voltou um arquivo adiante (o GitHub App).

Ate 25/09/2026 este arquivo tambem lia o `.github/workflows/publicar.yml`. Esse
workflow saiu: a publicacao agora e feita do VS Code direto para a VPS
(https://github.com/garcia-goncalves/deploy-padrao), e o que ele fazia de
administracao (gravar OAuth/GitHub App no `.env`, trocar a cortina, convidar
donos) passou a ser feito a mao no servidor, com o administrador — o roteiro
esta em `docs/operacao/publicar-no-servidor.md`. Ficou aqui o que continua
valendo: o `docker-compose.yml` passa ao container toda variavel que o
servidor le, e os dois comandos que o roteiro manual chama existem.

Nao publica nada e nao precisa de rede.

    python test_publicar.py
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

AQUI = Path(__file__).parent


class OsComandosDoRoteiroManualExistem(unittest.TestCase):
    """O roteiro manual chama codigo de verdade, nao um nome que ja mudou."""

    def test_cortina_trocar_existe_com_essa_assinatura(self):
        import cortina
        self.assertTrue(callable(cortina.trocar))
        with self.assertRaises(ValueError):
            cortina.trocar("12345", None)   # cinco digitos param antes do banco

    def test_convidar_existe_com_essa_assinatura(self):
        import autenticacao
        self.assertTrue(callable(autenticacao.convidar))


# ---------------------------------------------------------------------------
# A SEGUNDA METADE DO MESMO DEFEITO DE 28/08.
#
# Aquele dia ensinou "o workflow tem de LEVAR a variavel ao /opt/dervs/.env".
# Faltava o degrau seguinte, e ele mordeu em 02/09/2026: estar no `.env` do
# servidor nao poe a variavel DENTRO do container. Quem faz isso e o bloco
# `environment:` do `docker-compose.yml`, um arquivo diferente, mantido por
# outra mao, e que ninguem compara com o codigo.
#
# `servir.py` le `DERVS_GITHUB_APP_SLUG` para decidir se oferece a instalacao
# do GitHub App (`da_para_instalar`, e o 404 de `/api/github/instalar`). O
# compose nao passava nenhuma das tres variaveis do App. A porta 2 inteira
# — conectar a conta do GitHub — estava morta em producao POR CONSTRUCAO:
# registrar o app no github.com e escrever os valores no servidor nao mudaria
# nada, porque o processo nunca os enxergaria. Falha fechada, silenciosa, e
# indistinguivel de "o dono ainda nao registrou o app".
#
# A guarda abaixo nao decora as tres: ela compara AS DUAS LISTAS. Variavel
# nova lida pelo servidor sem entrada no compose reprova, e quem quiser
# deixa-la de fora escreve o motivo em FORA_DO_COMPOSE_DE_PROPOSITO.
# ---------------------------------------------------------------------------

COMPOSE = AQUI / "docker-compose.yml"

#: Lido pelo servidor e AUSENTE do compose de proposito, com o porque.
#: Entrar aqui e uma decisao que se escreve; nao e um lugar para calar teste.
FORA_DO_COMPOSE_DE_PROPOSITO = {
    "DERVS_AMBIENTE":
        "ausencia deliberada: com `local` o servidor aceitaria conta de teste, "
        "semente de dado falso e /entrar/local sem senha. O proprio compose "
        "explica isso em comentario.",
    "DERVS_COFRE_ARQUIVO":
        "so existe nesta maquina, onde a chave mora em arquivo. No servidor a "
        "chave chega por DERVS_COFRE, que esta no compose.",
}


def variaveis_do_compose():
    """Os nomes do bloco `environment:` do servico, como o Docker os entrega."""
    t = COMPOSE.read_text(encoding="utf-8")
    i = t.index("    environment:")
    j = t.index("\n    volumes:", i)
    bloco = t[i:j]
    nomes = set(re.findall(r"^\s{6}(DERVS_[A-Z_]+):", bloco, re.M))
    # A guarda da guarda. Se o recorte quebrar (o servico mudar de nome, o
    # bloco mudar de indentacao), `nomes` sai vazio e TODO caso abaixo
    # reprovaria por motivo errado — ou, pior, um `issubset` de vazio passaria.
    assert len(nomes) >= 6, (
        "o bloco environment: do compose saiu com %d nomes; o recorte "
        "quebrou." % len(nomes))
    return nomes


def variaveis_lidas(arquivo):
    """Toda leitura de ambiente de um DERVS_* no arquivo.

    Cobre `os.environ["X"]`, `os.environ.get("X")` e `os.getenv("X")` -- as
    tres formas com o nome escrito por extenso.

    O QUE ESCAPA, e de proposito: nome guardado numa variavel
    (`os.environ.get(NOME)`), leitura montada por string, e qualquer atalho
    novo. Achar essas exigiria interpretar o codigo, e uma guarda que erra
    para os dois lados e pior que uma que erra so para um. Hoje as leituras
    de `servir.py` e `banco.py` sao todas literais -- conferido em
    02/09/2026 --, e o caso abaixo cobra que essa forma continue valendo.
    """
    t = (AQUI / arquivo).read_text(encoding="utf-8")
    nomes = set(re.findall(
        r'os\.(?:environ(?:\.get)?[\(\[]|getenv\()[\'"](DERVS_[A-Z_]+)[\'"]', t))
    assert nomes, "nenhuma variavel encontrada em %s; a busca quebrou." % arquivo
    return nomes


def leituras_indiretas(arquivo):
    """Leituras de ambiente que a busca acima NAO enxerga.

    `os.environ.get(NOME)` com o nome numa variavel passaria por baixo da
    guarda em silencio -- justamente o desfecho que ela existe para impedir.
    Melhor reprovar e obrigar quem escreveu a decidir.
    """
    t = (AQUI / arquivo).read_text(encoding="utf-8")
    return [l.strip() for l in t.splitlines()
            if re.search(r'os\.(?:environ(?:\.get)?[\(\[]|getenv\()\s*[A-Za-z_]', l)]


#: As duas expressoes acima aceitam aspa simples E dupla. A cegueira por aspa
#: e sorrateira: a guarda continua verde, so que sobre menos codigo do que
#: parece. Achado na revisao de 02/09/2026, uma revisao depois de a mesma
#: classe ter fechado a cegueira por `os.getenv`.


class OContainerRecebeOQueOCodigoLe(unittest.TestCase):
    """Estar no .env do servidor nao basta: tem de entrar no container."""

    #: Os dois modulos que rodam DENTRO da imagem e leem ambiente.
    #: `coletar.py`, `conectador.py` e `agente/enviar.py` ficam de fora porque
    #: rodam na maquina de quem le o painel, nao no servidor.
    NO_SERVIDOR = ("servir.py", "banco.py")

    def test_toda_variavel_lida_pelo_servidor_chega_ao_container(self):
        do_compose = variaveis_do_compose()
        faltando = {}
        for arquivo in self.NO_SERVIDOR:
            for nome in sorted(variaveis_lidas(arquivo)):
                if nome in do_compose or nome in FORA_DO_COMPOSE_DE_PROPOSITO:
                    continue
                faltando.setdefault(nome, []).append(arquivo)
        self.assertFalse(
            faltando,
            "estas variaveis sao lidas pelo servidor e o docker-compose.yml "
            "nao as passa para dentro do container: %s. Quem le nunca as ve, e "
            "a funcionalidade morre em silencio em producao (falha fechada, "
            "indistinguivel de 'ainda nao configurado'). Passe-as no bloco "
            "`environment:` com `${NOME:-}`, ou escreva o motivo da ausencia "
            "em FORA_DO_COMPOSE_DE_PROPOSITO."
            % ", ".join("%s (%s)" % (n, "/".join(a))
                        for n, a in sorted(faltando.items())))

    def test_toda_leitura_de_ambiente_tem_o_nome_por_extenso(self):
        """Nome guardado em variavel cegaria a guarda sem que nada avisasse."""
        for arquivo in self.NO_SERVIDOR:
            indiretas = leituras_indiretas(arquivo)
            self.assertFalse(
                indiretas,
                "%s le ambiente com o nome fora da chamada: %s. A guarda "
                "acima nao enxerga essa forma, e a variavel poderia ficar "
                "fora do compose sem ninguem notar. Escreva o nome por "
                "extenso, ou ensine `variaveis_lidas` a achar esta forma."
                % (arquivo, indiretas))

    def test_a_lista_de_excecoes_nao_guarda_nome_morto(self):
        """Excecao que ninguem le mais vira ruido que esconde a proxima."""
        lidas = set()
        for arquivo in self.NO_SERVIDOR:
            lidas |= variaveis_lidas(arquivo)
        mortas = sorted(set(FORA_DO_COMPOSE_DE_PROPOSITO) - lidas)
        self.assertFalse(
            mortas,
            "FORA_DO_COMPOSE_DE_PROPOSITO fala de %s, que o servidor nao le "
            "mais. Apague a entrada." % ", ".join(mortas))

    def test_as_tres_do_github_app_estao_no_compose(self):
        """O caso concreto de 02/09, cravado para nao voltar por descuido."""
        do_compose = variaveis_do_compose()
        for nome in ("DERVS_GITHUB_APP_SLUG", "DERVS_GITHUB_APP_ID",
                     "DERVS_GITHUB_APP_KEY"):
            self.assertIn(
                nome, do_compose,
                "%s fora do compose: a porta 2 (conectar a conta do GitHub) "
                "nao funciona em producao, e a tela diz apenas que o app nao "
                "esta registrado." % nome)

    def test_as_tres_do_github_app_nao_derrubam_o_site_se_faltarem(self):
        """`${X:?}` mata o container; estas tres tem de ser opcionais.

        O painel serve para muito mais que a porta 2. Exigi-las na subida
        trocaria uma funcionalidade ausente por um site fora do ar.
        """
        t = COMPOSE.read_text(encoding="utf-8")
        for nome in ("DERVS_GITHUB_APP_SLUG", "DERVS_GITHUB_APP_ID",
                     "DERVS_GITHUB_APP_KEY"):
            self.assertNotRegex(
                t, r"\$\{%s:\?" % nome,
                "%s com `:?` derruba o container inteiro quando falta." % nome)


if __name__ == "__main__":
    unittest.main(verbosity=2)
