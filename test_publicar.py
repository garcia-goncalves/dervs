# -*- coding: utf-8 -*-
"""O workflow de publicacao leva ao servidor o que abre a porta.

POR QUE ESTE ARQUIVO EXISTE.

Em 28/08/2026 o dervs.com.br foi publicado com a verificacao verde, o dominio
respondendo 200 e a aparencia certa na tela. E **ninguem conseguia entrar**.

A cadeia era esta, e cada elo estava individualmente correto:

  - em producao `/entrar/local` NAO entra na tabela de rotas (`servir.py`,
    `if E_LOCAL:`), entao `/entrar/github` e a unica porta que existe;
  - `/entrar/github` responde 404 sem `DERVS_GITHUB_ID` e `DERVS_GITHUB_SECRET`;
  - as duas moravam no repositorio como variable e secret desde 27/08, e o
    workflow de publicacao nunca as levava para o `/opt/dervs/.env`;
  - e o roteiro de operacao chamava esse passo de **opcional**, com a frase "o
    site sobe igual, so sem o botao".

Nenhum teste podia falhar, porque nenhum teste olhava para esse caminho.

A cortina tinha o mesmo formato de defeito, um degrau adiante: a combinacao de
seis digitos nasce sorteada na primeira subida e e impressa uma vez, no registro
daquele container. Cada publicacao recria o container. `cortina.trocar()` existia
desde a etapa 9 e **nada no produto o chamava** — perder o numero era ficar
trancado para fora do proprio site, sem recuperacao.

Este arquivo le o `publicar.yml` como texto e como YAML. Ele nao publica nada e
nao precisa de rede.

    python test_publicar.py
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

AQUI = Path(__file__).parent
WORKFLOW = AQUI / ".github" / "workflows" / "publicar.yml"


def texto() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def passo_do_servidor() -> str:
    """O passo que fala com a VPS, como texto.

    A GUARDA vem junto de proposito: se o nome do passo mudar e este recorte
    voltar vazio, todos os casos abaixo passariam sobre string vazia — verdes,
    e sobre nada. E a lei 2 deste repositorio aplicada ao proprio teste.
    """
    t = texto()
    i = t.index("- name: Trocar o container")
    j = t.index("\n      - name:", i + 10)
    trecho = t[i:j]
    assert len(trecho) > 2000, (
        "o passo do servidor saiu com %d caracteres; o recorte quebrou e os "
        "casos seguintes passariam vazios." % len(trecho))
    return trecho


class APortaChegaAoServidor(unittest.TestCase):
    """As credenciais do OAuth App, sem as quais nao ha entrada nenhuma."""

    def setUp(self):
        self.passo = passo_do_servidor()

    def test_o_workflow_le_as_duas_credenciais_do_repositorio(self):
        for origem in ("vars.DERVS_GITHUB_ID", "secrets.DERVS_GITHUB_SECRET"):
            self.assertIn(
                origem, self.passo,
                "o passo do servidor nao le %s. Sem isso o /opt/dervs/.env "
                "sobe sem credencial e /entrar/github responde 404 — e em "
                "producao nao ha segunda porta." % origem)

    def test_as_duas_sao_gravadas_no_env_do_servidor(self):
        for chave in ("DERVS_GITHUB_ID=", "DERVS_GITHUB_SECRET="):
            self.assertRegex(
                self.passo, r">>\s*\.env\.novo" ,
                "nada e acrescentado ao .env do servidor.")
            self.assertIn(
                'echo "%s' % chave, self.passo,
                "%s nao e escrita no .env do servidor." % chave)

    def test_o_valor_nao_viaja_pela_linha_de_comando(self):
        """O achado da etapa 16, aplicado ao que foi acrescentado depois.

        `ssh alvo VAR=segredo comando` e `docker exec -e VAR=segredo` poem o
        valor no argv, legivel em /proc/<pid>/cmdline por qualquer conta local
        da VPS — que serve outros oito sistemas. Tudo tem de ir por STDIN.
        """
        self.assertNotRegex(
            self.passo, r"docker exec [^\n]*-e\s+\w+=",
            "docker exec -e poe o valor no argv do processo; use STDIN.")
        for nome in ("OAUTH_SECRET", "CORTINA"):
            # `%q` cita o valor para o shell remoto; o bloco inteiro entra pelo
            # STDIN do ssh, que nenhum `ps` mostra.
            self.assertIn(
                "printf '" + nome + "=%q", self.passo,
                nome + " nao viaja por STDIN citado com %q.")

    def test_faltar_credencial_avisa_em_vez_de_silenciar(self):
        """Publicar sem porta pode ser uma escolha; nao pode ser uma surpresa."""
        self.assertIn("AVISO: sem DERVS_GITHUB_ID", self.passo,
                      "sem as credenciais a publicacao segue calada.")


class ACortinaTemVolta(unittest.TestCase):
    """A combinacao de seis digitos pode ser trocada de fora."""

    def setUp(self):
        self.passo = passo_do_servidor()

    def test_o_workflow_chama_cortina_trocar(self):
        self.assertIn(
            "cortina.trocar(", self.passo,
            "nada no workflow chama cortina.trocar(). A combinacao nasce "
            "sorteada, e impressa uma vez no registro do container, e o "
            "registro morre na publicacao seguinte: sem esta chamada, perder "
            "o numero e perder o site.")

    def test_a_troca_e_opcional(self):
        """Sem o segredo, a publicacao nao pode falhar nem trocar nada."""
        self.assertIn('if [ -n "${CORTINA:-}" ]; then', self.passo,
                      "a troca da cortina nao esta atras de um teste de vazio.")

    def test_cortina_trocar_existe_com_essa_assinatura(self):
        """O workflow chama codigo de verdade, nao um nome que ja mudou."""
        import cortina
        self.assertTrue(callable(cortina.trocar))
        with self.assertRaises(ValueError):
            cortina.trocar("12345", None)   # cinco digitos param antes do banco


class ExisteUmaConta(unittest.TestCase):
    """A terceira peca da primeira subida.

    Cortina aberta e botao do GitHub ligado nao bastam: `convidar()` e a unica
    porta para criar conta, e nada a chamava no servidor. O sintoma nao ajuda
    ninguem — o retorno do GitHub responde igual no sucesso e no fracasso, de
    proposito, entao autorizar caia na capa sem uma palavra.
    """

    def setUp(self):
        self.passo = passo_do_servidor()

    def test_o_workflow_convida_o_dono(self):
        self.assertIn(
            "autenticacao.convidar(", self.passo,
            "nada no workflow cria a conta do dono. O site sobe com a porta "
            "aberta e nenhuma conta atras dela.")

    def test_o_convite_nao_se_repete(self):
        """`convidar` estoura na segunda vez, e nao ha comando para apagar
        conta criada errada: repetir cegamente quebraria toda publicacao
        seguinte."""
        self.assertIn("SELECT 1 FROM usuario WHERE email = ?", self.passo,
                      "o convite nao consulta se a PESSOA ja tem conta. Contar"
                      " credenciais no total pularia o segundo dono para"
                      " sempre: o DERVS tem mais de um.")
        self.assertNotIn("convidar(login, email) || true", self.passo)

    def test_o_erro_de_verdade_nao_e_engolido(self):
        """Idempotencia pela contagem, nunca por `|| true`: um `|| true` faria
        falha de rede e conta-ja-existe darem a mesma linha verde."""
        for engolidor in ("|| true", "|| echo", "2>/dev/null"):
            self.assertNotIn(
                "convidar" + engolidor, self.passo.replace(" ", ""))

    def test_login_e_email_nao_vao_pelo_argv(self):
        self.assertNotRegex(
            self.passo, r"autenticacao\.py convidar",
            "o CLI recebe login e e-mail como argumentos, e argv e legivel em "
            "/proc por qualquer conta local da VPS. Use STDIN.")
        self.assertIn("printf 'DONOS=%q", self.passo)

    def test_convidar_existe_com_essa_assinatura(self):
        import autenticacao
        self.assertTrue(callable(autenticacao.convidar))


class PublicarContinuaSendoDecisaoDeGente(unittest.TestCase):
    """O que foi acrescentado nao pode ter afrouxado a trava principal."""

    def test_o_unico_gatilho_e_o_botao(self):
        t = texto()
        cabeca = t[:t.index("jobs:")]
        for automatico in ("on: push", "\n  push:", "\n  schedule:",
                           "\n  workflow_run:", "\n  pull_request:"):
            self.assertNotIn(
                automatico, cabeca,
                "gatilho automatico %r no workflow de publicacao." % automatico)
        self.assertIn("workflow_dispatch:", cabeca)

    def test_a_palavra_publicar_continua_exigida(self):
        self.assertIn("inputs.confirmar == 'PUBLICAR'", texto())

    def test_publicacao_cortada_no_meio_nao_e_permitida(self):
        self.assertIn("cancel-in-progress: false", texto())



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


class AChaveDoAppChegaInteira(unittest.TestCase):
    """A chave privada tem varias linhas, e arquivo de ambiente nao tem.

    `github_app.chave_de_pem` ignora as linhas de armadura e junta o resto, o
    que faz uma UNICA linha de base64 puro funcionar — medido nos dois formatos
    em 02/09/2026. O que NAO funciona e o jeito ingenuo, `tr -d '\n'` sobre o
    arquivo inteiro: a armadura gruda no miolo, vira uma linha so comecando com
    `-----`, o filtro a descarta inteira e a chave sai vazia. A diferenca entre
    os dois e uma linha de `grep`, e ela e a razao desta classe existir.
    """

    def setUp(self):
        self.passo = passo_do_servidor()

    def test_a_armadura_sai_antes_de_a_chave_virar_uma_linha(self):
        self.assertRegex(
            self.passo, r"grep -v[^\n]*-----",
            "a chave e achatada sem tirar as linhas -----BEGIN/-----END "
            "antes; o resultado e uma linha unica que comeca com '-----', que "
            "chave_de_pem descarta INTEIRA. A chave chegaria vazia e a volta "
            "da instalacao falharia sempre, em silencio.")

    def test_a_chave_nao_viaja_pela_linha_de_comando(self):
        """Presenca do jeito certo NAO exclui a presenca do jeito errado.

        A primeira versao so cobrava que `printf 'APP_KEY=%q` existisse -- e
        continuava verde com um `docker exec -e K="$APP_KEY"` acrescentado ao
        lado, porque o `printf` seguia la. Guarda que nao pode reprovar o que o
        nome dela promete. Achado da revisao de seguranca de 02/09/2026, pelo
        criterio do proprio CLAUDE.md.

        Agora a assercao e de AUSENCIA: as duas variaveis com material de chave
        so podem aparecer nas linhas que as poem em STDIN ou as escrevem no
        arquivo de ambiente. Qualquer outra mencao -- `docker exec -e`, um
        `echo` de depuracao, um prefixo de ambiente no `ssh` -- reprova.
        """
        self.assertIn(
            "printf 'APP_KEY=%q", self.passo,
            "a chave privada do App nao viaja por STDIN citado com %q; "
            "qualquer conta local desta VPS de 26 containers a leria em "
            "/proc/<pid>/cmdline durante a publicacao.")
        # O bloco `env:` do passo entra aqui: e ele que traz o segredo do
        # cofre do repositorio para o ambiente do runner, e sem ele nada
        # funciona. O que esta guarda persegue e a chave em ARGV.
        # O QUE ESTA GUARDA PERSEGUE E O VALOR EXPANDIDO, nao o nome.
        # `grep -e '^DERVS_GITHUB_APP_KEY='` cita o nome e nao expande nada;
        # `docker exec -e K="$APP_KEY"` poe o VALOR no argv, legivel em
        # /proc/<pid>/cmdline por qualquer conta local desta VPS de 26
        # containers. Sao coisas diferentes, e so a segunda vaza.
        expansao = re.compile(r"\$\{?(APP_KEY|chave_numa_linha)\b")
        #: Onde o valor PODE aparecer: no STDIN citado com %q, na escrita do
        #: arquivo de ambiente, no achatamento que o produz, e na peneira de
        #: forma (`case` e embutido do shell -- nao cria processo, nao tem
        #: argv). Qualquer outro lugar reprova.
        permitidas = (
            "printf 'APP_KEY=%q",
            'echo "DERVS_GITHUB_APP_KEY=$chave_numa_linha"',
            "chave_numa_linha=$(printf",
            'case "${chave_numa_linha:-}" in',
        )
        for linha in self.passo.splitlines():
            if linha.lstrip().startswith("#") or not expansao.search(linha):
                continue
            self.assertTrue(
                any(p in linha for p in permitidas),
                "o VALOR da chave do App e expandido numa linha que nao e o "
                "STDIN, a escrita no arquivo de ambiente, o achatamento nem a "
                "peneira -- e por ai que ele vaza para /proc: %s"
                % linha.strip())

    def test_os_tres_valores_sao_peneirados_antes_de_serem_gravados(self):
        """Presenca nao e validade, e o arquivo de ambiente e lido pelo shell.

        Dois achados da revisao de seguranca de 02/09/2026, reproduzidos em
        bash de verdade, e a mesma peneira fecha os dois:

        1. Uma chave PEM CIFRADA (`Proc-Type: 4,ENCRYPTED`) nao tem `-----`
           nessas linhas: elas escapam do `grep -v` e sao coladas no miolo. O
           resultado NAO e vazio, entao um teste de presenca passa, a
           publicacao fica verde dizendo "gravadas" -- e toda tentativa de
           conectar termina em "nao deu para conferir".
        2. `DERVS_GITHUB_APP_SLUG=ab$(comando)cd` executaria o comando dentro
           do servidor.

        Medido depois da correcao: dos nove casos, um aceito e oito recusados
        pelo motivo certo, incluindo nova linha, espaco e ponto-e-virgula.
        """
        for peneira, alvo in (
                ("*[!A-Za-z0-9-]*", "APP_SLUG"),
                ("*[!0-9]*", "APP_ID"),
                ("*[!A-Za-z0-9+/=]*", "a chave em base64")):
            self.assertIn(
                peneira, self.passo,
                "falta a peneira de forma para %s. Sem ela, presenca passa "
                "por validade -- e um valor com `$(...)` chega a ser lido "
                "pelo shell do servidor." % alvo)

    def test_o_aviso_nao_afirma_o_que_nao_foi_verificado(self):
        """Nada aqui apaga linha do arquivo de ambiente do servidor.

        A mensagem antiga dizia que "a porta 2 nao aparece na tela", e isso
        podia ser FALSO: valores de uma publicacao anterior seguem de pe.
        Alguem que apagasse o segredo do repositorio para retirar uma chave
        suspeita leria aquilo e acreditaria ter retirado -- com a chave viva no
        processo. Lei 2 deste repositorio, aplicada ao log da publicacao.
        """
        self.assertIn("CONTINUA", self.passo,
                      "o aviso nao diz que o que ja esta no servidor continua "
                      "valendo.")
        self.assertNotIn("a porta 2 (conectar a conta do GitHub) nao",
                         self.passo,
                         "o aviso voltou a afirmar um estado do servidor que "
                         "este passo nao verifica.")

    def test_o_arquivo_de_ambiente_do_servidor_nao_e_executado(self):
        """`. ./.env` EXECUTA o que estiver escrito la, e exporta tudo.

        Duas consequencias: um valor com `$(...)` vira comando, e a chave
        privada mais a chave do cofre passam a ser herdadas por todo processo
        seguinte -- legiveis em /proc/<pid>/environ. Duas linhas de `grep`
        resolvem, lendo como TEXTO.
        """
        # Linha de comentario nao executa nada -- e o comentario que explica
        # a decisao cita justamente o comando proibido. Guarda que le texto
        # cru reprovaria a propria explicacao.
        executaveis = "\n".join(l for l in self.passo.splitlines()
                                if not l.lstrip().startswith("#"))
        self.assertNotIn(
            ". ./.env", executaveis,
            "o roteiro voltou a sourcear o arquivo de ambiente do servidor.")
        self.assertIn("grep -m1 '^DERVS_PORTA=", self.passo,
                      "a porta nao e mais lida como texto.")

    def test_o_rascunho_do_env_e_apagado_se_o_roteiro_morrer(self):
        """Sobra um arquivo com a chave privada dentro se ninguem limpar."""
        trap = [l for l in self.passo.splitlines() if "trap " in l]
        self.assertTrue(trap, "o roteiro perdeu o trap de saida.")
        self.assertIn(".env.novo", trap[0],
                      "o rascunho do arquivo de ambiente nao e apagado na "
                      "saida: se o roteiro morrer entre a escrita e o `mv`, "
                      "fica no disco um arquivo com a chave privada.")

    def test_as_tres_chegam_ao_env_do_servidor(self):
        for chave in ("DERVS_GITHUB_APP_SLUG=", "DERVS_GITHUB_APP_ID=",
                      "DERVS_GITHUB_APP_KEY="):
            self.assertIn(
                'echo "%s' % chave, self.passo,
                "%s nao e escrita no /opt/dervs/.env. Sem ela no arquivo, o "
                "compose passa vazio para o container." % chave)

if __name__ == "__main__":
    unittest.main(verbosity=2)
