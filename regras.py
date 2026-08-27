# -*- coding: utf-8 -*-
"""Motor de pendencias do HUB — as 18 regras.

O HUB responde uma pergunta so: "o que precisa de mim agora?". Este arquivo e
onde essa pergunta vira lista.

TRES INVARIANTES, e o teste cobre os tres:

  1. TODA PENDENCIA TEM UMA ACAO. Se nao ha o que fazer a respeito, nao e
     pendencia: e estatistica, e estatistica vai para a tabela de baixo. Painel
     que lista o que o dono nao pode resolver treina ele a ignorar a lista.
  2. AUSENCIA NAO E FALHA. Se a camada do GitHub nao foi coletada, o motor fica
     calado sobre CI, PR e vulnerabilidade. Inventar "CI vermelha" porque o
     numero nao chegou e a maneira mais rapida de perder a confianca do dono.
  3. O ID E ESTAVEL. "regra:projeto", nao um hash do texto. E o id que permite
     silenciar uma pendencia e ela continuar silenciada na coleta seguinte.

Este modulo e PURO: entra dicionario, sai lista. Nao le disco, nao chama rede,
nao roda comando — e por isso da para testar as 18 regras em um segundo.
"""
from __future__ import annotations

from datetime import datetime, timezone

# Os quatro tipos de acao que a tela sabe executar.
#   abrir_url — o navegador abre o link (CI, PR, alerta de seguranca)
#   vscode    — abre o VS Code na pasta ou no arquivo
#   rodar     — o servidor executa um comando da lista branca em servir.py
#   copiar    — copia um texto pronto para a area de transferencia
ACOES = ("abrir_url", "vscode", "rodar", "copiar")

ORDEM = {"alta": 0, "media": 1, "baixa": 2}

# Limiares, num lugar so — sao o que o dono vai querer ajustar primeiro.
DIAS_SUJO = 1          # trabalho sem commit vira pendencia depois de 1 dia
DIAS_PR = 7            # PR aberto sem se mexer
DIAS_GRAFO = 7         # indice do grafo velho
DIAS_ABANDONO = 30     # projeto sem commit
PCT_COTA = 80          # cota de minutos do Actions


def _p(regra, gravidade, projeto, texto, acao, detalhe="", risco=0):
    """`risco` desempata DENTRO da gravidade; nunca atravessa gravidades.

    Regra que nao sabe medir risco deixa em zero e ordena pelo nome, como
    sempre. So a de alerta de seguranca preenche hoje, e por um motivo medido:
    ver `risco_alerta`.
    """
    return {
        "id": "%s:%s" % (regra, projeto),
        "regra": regra,
        "gravidade": gravidade,
        "projeto": projeto,
        "texto": texto,
        "detalhe": detalhe,
        "acao": acao,
        "risco": risco,
    }


def _do_projeto(p: dict) -> list:
    nome = p["nome"]
    caminho = p.get("caminho", "")
    g = p.get("git") or {}
    versionado = bool(g.get("versionado"))
    # `is False` de proposito, e nao `not g.get(...)`: retrato gravado antes
    # desta chave existir nao tem opiniao sobre o assunto, e dado antigo nao
    # deve virar enxurrada de "nao medi".
    git_mudo = versionado and g.get("medido") is False
    gh = p.get("github")            # None = camada nao coletada (ver invariante 2)
    pesado = p.get("pesado") or {}
    itens = []

    # ------------------------------------------------------------------ altas
    # 1. CI vermelha
    ci = (gh or {}).get("ci") or {}
    if ci.get("conclusao") == "failure":
        itens.append(_p(
            "ci_vermelha", "alta", nome,
            "A verificação automática do GitHub falhou em %s." % nome,
            {"tipo": "abrir_url", "rotulo": "Ver o que falhou", "url": ci.get("url", "")},
            detalhe=ci.get("quando", "")))

    # 2. Container que DEVIA estar no ar e caiu.
    # "Devia" nao e "o casos.json declara containers": e "o projeto esta aberto
    # no VS Code agora", que e a regra pela qual o vigia-vscode sobe e derruba o
    # Docker desta maquina. Sem esse filtro a caixa nasceu com seis alarmes de
    # projeto fechado — nenhum deles pendencia, todos ensinando o dono a ignorar
    # a lista. aberto_no_editor None = nao deu para saber; entao ficamos calados.
    esperados = p.get("containers_esperados") or []
    vivos = [c for c in (p.get("containers") or [])
             if c.get("saudavel") and not c.get("reiniciando")]
    if esperados and not vivos and p.get("aberto_no_editor") is True:
        acao = ({"tipo": "rodar", "rotulo": "Subir", "comando": "docker_up", "projeto": nome}
                if p.get("compose")
                else {"tipo": "vscode", "rotulo": "Abrir a pasta", "caminho": caminho})
        itens.append(_p(
            "container_caido", "alta", nome,
            "O %s devia ter container no ar e não tem nenhum saudável." % nome,
            acao, detalhe="esperados: " + ", ".join(esperados)))

    # 3. Vulnerabilidade aberta (Dependabot)
    v = (gh or {}).get("vulns") or {}
    if v.get("total"):
        itens.append(_p(
            "vulnerabilidade", gravidade_alerta(v), nome,
            frase_alerta(nome, v) + _ressalva_de_idade(v),
            {"tipo": "abrir_url", "rotulo": "Ver os alertas", "url": v.get("url", "")},
            detalhe=detalhe_alerta(v), risco=risco_alerta(v)))

    # 4. Trabalho nao commitado ha mais de um dia
    dias_sujo = g.get("sujos_dias")
    if versionado and g.get("sujos") and dias_sujo is not None and dias_sujo >= DIAS_SUJO:
        itens.append(_p(
            "nao_commitado", "alta", nome,
            "%d arquivo(s) alterado(s) há %d dia(s) sem salvar no histórico."
            % (g["sujos"], dias_sujo),
            {"tipo": "vscode", "rotulo": "Abrir no VS Code", "caminho": caminho},
            detalhe=", ".join(g.get("sujos_lista") or [])[:200]))

    # 5. Commit so no disco
    if versionado and g.get("ahead"):
        itens.append(_p(
            "nao_enviado", "alta", nome,
            "%d commit(s) existem só neste computador — se o disco morrer, morrem junto."
            % g["ahead"],
            {"tipo": "rodar", "rotulo": "Enviar ao GitHub", "comando": "git_push",
             "projeto": nome}))

    # 6. Memoria do projeto em CRLF
    # Existe porque o erro e calado: em CRLF o harness ignora o frontmatter e a
    # memoria nunca carrega. Sem o HUB, ninguem descobre.
    crlf = p.get("memoria_crlf") or []
    if crlf:
        itens.append(_p(
            "memoria_crlf", "alta", nome,
            "%d arquivo(s) de memória do %s estão com quebra de linha do Windows — "
            "assim o Claude nunca carrega essa memória." % (len(crlf), nome),
            {"tipo": "rodar", "rotulo": "Converter", "comando": "crlf_para_lf",
             "projeto": nome},
            detalhe=", ".join(crlf)))

    # ------------------------------------------------------------------ medias
    # 8. Indice do grafo ausente ou velho
    gr = p.get("grafo") or {}
    if not gr.get("indexado"):
        itens.append(_p(
            "grafo_velho", "media", nome,
            "O %s não está no grafo de código — sem ele eu leio arquivo por arquivo."
            % nome,
            {"tipo": "copiar", "rotulo": "Copiar o pedido",
             "texto": "indexe o grafo de código do %s" % nome}))
    elif (gr.get("dias") or 0) > DIAS_GRAFO:
        itens.append(_p(
            "grafo_velho", "media", nome,
            "O grafo de código do %s foi montado há %d dias e não se atualiza sozinho."
            % (nome, gr["dias"]),
            {"tipo": "copiar", "rotulo": "Copiar o pedido",
             "texto": "reindexe o grafo de código do %s" % nome}))

    # 9. PR aberto parado
    for pr in ((gh or {}).get("prs") or []):
        if (pr.get("dias") or 0) >= DIAS_PR:
            itens.append(_p(
                "pr_parado", "media", nome,
                "O pedido de alteração #%s do %s está parado há %d dias."
                % (pr.get("numero"), nome, pr["dias"]),
                {"tipo": "abrir_url", "rotulo": "Abrir", "url": pr.get("url", "")},
                detalhe="pedido #%s, parado ha %d dias"
                        % (pr.get("numero"), pr["dias"])))
                # SEGURANCA: o `detalhe` desta pendencia ja foi `pr["titulo"]`, e
                # esse titulo e texto CRU da API do GitHub — qualquer um que abra
                # um PR num repositorio do dono escolhe o que vai escrito ali. O
                # `detalhe` entra no prompt da sessao do botao "Resolver", que roda
                # com Bash auto-aprovado; era injecao de prompt virando execucao de
                # comando na maquina. Aqui so entra numero e dias, calculados por
                # nos. O titulo continua a um clique, no botao "Abrir".
            break          # um item por projeto: a caixa e para agir, nao para listar

    # 15. O site de producao nao respondeu
    #
    # E a unica pendencia desta lista que o CLIENTE percebe antes do dono. Tudo
    # o mais aqui — CI, grafo, dependencia — e coisa que so machuca o dono.
    #
    # O QUE ESTA REGRA NAO GARANTE, e vale repetir onde alguem va ler: responder
    # 200 na raiz nao e o mesmo que estar funcionando. Banco caido atras de uma
    # home estatica continua devolvendo 200. Isto pega o apagao, nao a doenca.
    site = (gh or {}).get("site") or {}
    if site and site.get("ok") is False:
        motivo = ("respondeu com erro %s" % site["codigo"]
                  if site.get("codigo") else "não respondeu")
        itens.append(_p(
            "site_fora", "alta", nome,
            "O site de produção do %s %s." % (nome, motivo),
            # A URL vai na ACAO, que o navegador trata como endereco. No TEXTO
            # entra so o nome do projeto e um motivo escrito por nos: texto de
            # arquivo nao entra cru em string que pode acabar num prompt.
            {"tipo": "abrir_url", "rotulo": "Abrir o site",
             "url": site.get("url", "")},
            detalhe="código %s" % (site.get("codigo") or "sem resposta")))

    # 16. Trabalho pronto no GitHub que nunca foi publicado
    #
    # Calado quando o repositorio nao tem workflow de deploy identificavel:
    # nao saber nao e o mesmo que estar atrasado (invariante 2).
    dep = (gh or {}).get("deploy") or {}
    atras = dep.get("atras")
    if isinstance(atras, int) and atras > 0:
        itens.append(_p(
            "nao_publicado", "media", nome,
            "%d commit(s) do %s estão no GitHub e ainda não foram publicados."
            % (atras, nome),
            {"tipo": "abrir_url", "rotulo": "Ver as publicações",
             "url": dep.get("url", "")},
            detalhe="último deploy: %s" % (dep.get("sha") or "desconhecido")[:12]))

    # 10. Dependencia com correcao de seguranca disponivel
    deps = pesado.get("deps_inseguras") or []
    if deps:
        itens.append(_p(
            "dependencia_insegura", "media", nome,
            "%d dependência(s) do %s têm correção de segurança disponível."
            % (len(deps), nome),
            {"tipo": "copiar", "rotulo": "Copiar o comando",
             "texto": "cd %s && npm audit fix" % caminho},
            detalhe=", ".join(deps[:12])))

    # 17. A auditoria de dependencia TENTOU rodar e falhou
    #
    # Nao viola o invariante 2. "A camada pesada nunca rodou" continua sendo
    # silencio: sem a marca `auditoria_falhou`, este bloco nem acorda. O que
    # falamos aqui e um fato medido — tentamos auditar e nao conseguimos —, e
    # nao um alarme inventado a partir de numero que nao chegou.
    #
    # Existe porque o contrario ja aconteceu: por um defeito de invocacao, o
    # `npm audit` nunca rodava em Linux, devolvia lista vazia, e a regra 10
    # ficava calada. Tela limpa por cegueira e a pior mentira de um painel,
    # porque e indistinguivel de boa noticia.
    if pesado.get("auditoria_falhou"):
        itens.append(_p(
            "auditoria_nao_rodou", "baixa", nome,
            "Não consegui auditar as dependências do %s — não sei se há falha de "
            "segurança nele." % nome,
            {"tipo": "copiar", "rotulo": "Copiar o comando",
             "texto": "cd %s && npm audit" % caminho},
            detalhe="rode o comando para ver o erro do npm com seus olhos"))

    # 11. Exemplo de variaveis divergente do arquivo real
    # So NOMES de variavel entram aqui. Valor de segredo nunca sai do disco.
    drift = p.get("env_drift") or {}
    faltando, sobrando = drift.get("faltando") or [], drift.get("sobrando") or []
    if faltando or sobrando:
        partes = []
        if faltando:
            partes.append("faltam no exemplo: " + ", ".join(faltando))
        if sobrando:
            partes.append("estão só no exemplo: " + ", ".join(sobrando))
        itens.append(_p(
            "env_drift", "media", nome,
            "O arquivo de exemplo de variáveis do %s não bate com o real — "
            "quem clonar o projeto não consegue rodar." % nome,
            {"tipo": "copiar", "rotulo": "Copiar as diferenças",
             "texto": " | ".join(partes)},
            detalhe=" | ".join(partes)))

    # ------------------------------------------------------------------ baixas
    # 12. Sem commit ha mais de 30 dias
    if versionado and (g.get("dias_parado") or 0) > DIAS_ABANDONO:
        itens.append(_p(
            "abandonado", "baixa", nome,
            "O %s não recebe commit há %d dias." % (nome, g["dias_parado"]),
            {"tipo": "vscode", "rotulo": "Abrir e decidir", "caminho": caminho}))

    # 13. Sem remoto no GitHub
    # `git_mudo` barra aqui porque a acao e destrutiva: sem a resposta do git,
    # `tem_remoto` some do retrato, esta regra concluia "existe so neste
    # computador" de um repo que TEM GitHub, e entregava ao dono um `git init`
    # em cima dele. Alarme inventado ja e ruim; com acao destrutiva junto, e
    # estrago.
    if not git_mudo and (not versionado or not g.get("tem_remoto")):
        itens.append(_p(
            "sem_remoto", "baixa", nome,
            "O %s não tem cópia no GitHub — existe só neste computador." % nome,
            {"tipo": "copiar", "rotulo": "Copiar o comando",
             "texto": "cd %s && git init && gh repo create %s --private --source=. --push"
                      % (caminho, nome)}))

    # 18. O git nao respondeu por este projeto
    #
    # Irma da regra 17, mesma logica: fato medido ("tentei e nao consegui"),
    # nao alarme tirado de numero ausente. Enquanto ela nao existia, git
    # quebrado virava "arvore limpa, 0 commits, nunca publicado" — tela
    # tranquila por cegueira, indistinguivel de boa noticia.
    if git_mudo:
        itens.append(_p(
            "git_nao_medido", "media", nome,
            "Não consegui ler o git do %s — o que a tela mostra dele não foi "
            "medido." % nome,
            {"tipo": "copiar", "rotulo": "Copiar o comando",
             "texto": "cd %s && git status" % caminho},
            detalhe="rode o comando para ver o erro do git com seus olhos"))

    # 14. Estudo de caso vazio
    if p.get("caso_vazio"):
        itens.append(_p(
            "caso_vazio", "baixa", nome,
            "O %s não tem descrição escrita — o painel sabe medir, não sabe contar "
            "o que ele é." % nome,
            {"tipo": "vscode", "rotulo": "Escrever", "caminho": p.get("casos_json", "")}))

    return itens


def risco_alerta(v: dict) -> int:
    """Peso para desempatar quatro linhas que sao todas "alta".

    POR QUE EXISTE: medido no painel em 25/08/2026, com a severidade ja na
    frase, as quatro linhas sairam `investrix` (12 altos, zero critico) ANTES de
    `workspace-medconsultoria` (6 criticos) — porque `i` vem antes de `w`. A
    frase dizia a verdade e a ordem mandava o dono para o lugar errado. Consertar
    o texto sem consertar a ordem resolve metade do problema.

    Critico vale 100 e alto vale 1, entao UM critico ganha de qualquer numero
    plausivel de altos: sao coisas diferentes, nao a mesma moeda em quantidades
    diferentes. Moderado e baixo valem ZERO de proposito — sao 47 dos 203
    alertas reais, e se contassem seriam eles a decidir o desempate.

    Severidade nao medida da zero. Aqui isso e so ordem; quem impede o rebaixamento
    de quem nao foi medido e `gravidade_alerta`, que devolve "alta" nesse caso.
    """
    sev = v.get("sev") or {}
    return (sev.get("critical") or 0) * 100 + (sev.get("high") or 0)


def gravidade_alerta(v: dict) -> str:
    """Alta so quando ha critico ou alto — com DUAS excecoes que sobem de volta.

    Ordenar por contagem inverte o risco: medido em 25/08/2026, o
    medconsultoria tinha 93 alertas (11 baixos) e o workspace-medconsultoria 19,
    dos quais 6 CRITICOS. A tela mandava o dono comecar pelo lado errado.

    As excecoes existem porque NAO SABER nao e o mesmo que SER SEGURO:

      sem `sev`   coleta antiga no banco, ou permissao que so deu o total.
      `amostra`   o GraphQL le 100 alertas por vez; o critico pode estar
                  justamente entre os que nao vieram.

    Nos dois casos fica alta. Rebaixar por falta de medicao seria mais uma forma
    de o painel mentir com numero certo.
    """
    sev = v.get("sev")
    if not sev or v.get("amostra"):
        return "alta"
    return "alta" if (sev.get("critical") or sev.get("high")) else "media"


def _ressalva_de_idade(v: dict) -> str:
    """" — não consegui reler há N dias", quando o número é reaproveitado.

    O coletor mantém o último número conhecido quando não consegue reler os
    alertas (token sem permissão, campo negado). Manter é certo: zerar apagaria
    um alerta real. Mas manter CALADO é pior que zerar — o painel republica uma
    medição de semanas atrás como se fosse de agora, e ninguém fica sabendo
    enquanto a permissão não voltar.
    """
    dias = v.get("dias_sem_reler")
    if not isinstance(dias, int) or dias < 1:
        return ""
    return (" Não consigo reler esse número há %d dia(s), então ele pode estar "
            "velho." % dias)


def frase_alerta(nome: str, v: dict) -> str:
    total = v["total"]
    sev = v.get("sev")
    if not sev:
        return "%d alerta(s) de segurança aberto(s) em %s." % (total, nome)
    if v.get("amostra"):
        # Com amostra a distribuicao vista NAO descreve o conjunto. A frase so
        # pode dar um piso, e tem de dizer que e piso.
        return ("%d alerta(s) de segurança aberto(s) em %s — mais do que cabe "
                "numa leitura só, então isto é o que deu para ver: pelo menos "
                "%d pacote(s) distinto(s)." % (total, nome, v.get("pacotes") or 0))

    graves = []
    if sev.get("critical"):
        graves.append("%d crítico(s)" % sev["critical"])
    if sev.get("high"):
        graves.append("%d alto(s)" % sev["high"])
    pacotes = v.get("pacotes") or 0
    if graves:
        return ("%s entre %d alerta(s) de segurança em %s, em %d pacote(s)."
                % (" e ".join(graves), total, nome, pacotes))
    # Sem grave nenhum a palavra "crítico" nao aparece: dizer "nenhum crítico"
    # planta na tela justamente a palavra que a linha existe para nao gritar.
    return ("%d alerta(s) de segurança em %s, todos moderados ou baixos, "
            "em %d pacote(s)." % (total, nome, pacotes))


def detalhe_alerta(v: dict) -> str:
    """O escopo aparece aqui como FATO, e so aqui.

    Ele nunca entra em `gravidade_alerta`: medido no workspace-medconsultoria
    que o mesmo `vitest` volta DEVELOPMENT num manifesto e RUNTIME noutro, entao
    "é só ferramenta de teste" esconderia um critico de producao.
    """
    sev = v.get("sev")
    if not sev:
        return ""
    partes = ["%d %s" % (sev[k], r) for k, r in
              (("critical", "crítico"), ("high", "alto"),
               ("moderate", "moderado"), ("low", "baixo")) if sev.get(k)]
    if v.get("defeitos"):
        partes.append("%d defeito(s) distinto(s)" % v["defeitos"])
    escopo = v.get("escopo") or {}
    if escopo.get("runtime"):
        partes.append("%d em dependência de produção" % escopo["runtime"])
    return " · ".join(partes)


def avaliar(projetos, quota=None, silenciadas=None,
            arquivadas=None) -> list:
    """Retrato dos projetos -> lista de pendencias, mais grave primeiro."""
    itens = []
    for p in projetos:
        itens.extend(_do_projeto(p))

    # 7. Cota de minutos do Actions — e da conta inteira, nao de um projeto.
    # Projeto "" e proposital: a pendencia nao pertence a repositorio nenhum.
    if quota and (quota.get("pct") or 0) >= PCT_COTA:
        itens.append(_p(
            "cota_actions", "alta", "",
            "As verificações automáticas do GitHub já consumiram %d%% da cota do mês "
            "(%s de %s minutos)." % (quota["pct"], quota.get("minutos"), quota.get("cota")),
            {"tipo": "abrir_url", "rotulo": "Ver o consumo",
             "url": quota.get("url", "https://github.com/settings/billing")}))

    # Duas maneiras de sumir, e a diferenca entre elas e o prazo. `silenciadas`
    # esconde por 24 h e volta sozinha. `arquivadas` e o dono dizendo "isto esta
    # certo assim" — e nao tem volta automatica, por isso nao ha data aqui. O
    # defeito que isto corrige: projeto arquivado de proposito voltava a cutucar
    # todo dia, para sempre, e caixa que repete alarme resolvido ensina o dono a
    # ignorar a caixa inteira.
    calados = silenciadas or {}
    guardadas = arquivadas or set()
    itens = [i for i in itens
             if i["id"] not in calados and i["id"] not in guardadas]
    itens.sort(key=lambda i: (ORDEM[i["gravidade"]], i["projeto"], i["regra"]))
    return itens


# --------------------------------------------------------------------- o selo
#
# Validade de cada camada, em segundos. Nao e "quando o numero apodrece": e a
# partir de quando ele deixa de servir para AFIRMAR alguma coisa. A cadencia de
# coleta e local 60 s, github 20 min, pesado 24 h; cada validade aqui e algumas
# cadencias, para que uma coleta que falhou uma vez nao apague o selo inteiro.
VALIDADE = {"local": 10 * 60, "github": 2 * 3600, "pesado": 48 * 3600}

# De qual camada cada regra depende. Regra que nao esta neste mapa NAO pinta o
# selo, e isso e decisao, nao esquecimento: `abandonado` e `caso_vazio` sao
# constatacao (nao ha o que fazer hoje), `grafo_velho` volta a cada 7 dias para
# sempre, e `memoria_crlf` e convencao interna do Claude Code — nenhuma das
# quatro quer dizer que o projeto esta doente. Elas continuam na lista de
# pendencias; so nao mandam na cor.
CAMADA_DA_REGRA = {
    "container_caido": "local",
    "nao_commitado": "local",
    "nao_enviado": "local",
    "env_drift": "local",
    "sem_remoto": "local",
    "git_nao_medido": "local",
    "ci_vermelha": "github",
    "vulnerabilidade": "github",
    "pr_parado": "github",
    "site_fora": "github",
    "nao_publicado": "github",
    "dependencia_insegura": "pesado",
    "auditoria_nao_rodou": "pesado",
}


def _idade(iso, agora):
    """Segundos desde o carimbo. `None` quando nao ha carimbo legivel.

    `None` e o valor que sobrevive ate a tela. Devolver 0 aqui — "acabou de ser
    medido" — para um carimbo ausente e exatamente o defeito que esta etapa
    existe para matar: seria indistinguivel de uma medida real.
    """
    try:
        t = datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return (agora - t).total_seconds()


def camadas_do_selo(p: dict, agora=None) -> dict:
    """{camada: True se a medida dela ainda vale}. A prova por tras do selo."""
    agora = agora or datetime.now(timezone.utc)
    carimbos = p.get("medido_em") or {}
    vale = {}
    for camada, limite in VALIDADE.items():
        idade = _idade(carimbos.get(camada), agora)
        vale[camada] = idade is not None and idade <= limite
    return vale


def selo_do_projeto(p: dict, pendencias=None, agora=None) -> str:
    """Um de "saudavel", "atencao", "quebrado", "sem_dados".

    O QUARTO ESTADO E O MOTIVO DESTA FUNCAO EXISTIR. A conta ingenua — "nao ha
    pendencia aberta, logo verde" — pinta de verde justamente o projeto que
    ninguem mediu, porque ausencia de medida tambem produz ausencia de
    pendencia. Verde por cegueira e indistinguivel de verde por saude, e e a
    pior mentira que um painel conta.

    Entao: sem NENHUMA camada dentro da validade, o selo e `sem_dados` — nao e
    bom nem ruim, e ausencia. E cada pendencia so pinta o selo se a camada que a
    produziu ainda vale: numero de 20 minutos atras, numa camada que mede a cada
    60 s, nao afirma nada sobre agora.

    `pendencias` opcional: passe a lista JA filtrada (silenciada, arquivada)
    quando quiser que o que o dono arquivou — "isto esta certo assim" — pare de
    pintar o selo. Sem ela, a funcao calcula do zero a partir do retrato.
    """
    validas = camadas_do_selo(p, agora)
    if not any(validas.values()):
        return "sem_dados"

    nome = p.get("nome")
    if pendencias is None:
        pendencias = _do_projeto(p)

    pior = None
    for i in pendencias:
        if i.get("projeto") != nome:
            continue
        camada = CAMADA_DA_REGRA.get(i.get("regra"))
        if camada is None or not validas.get(camada):
            continue
        o = ORDEM.get(i.get("gravidade"), 9)
        pior = o if pior is None else min(pior, o)

    if pior is None:
        return "saudavel"
    return "quebrado" if pior == ORDEM["alta"] else "atencao"


# ----------------------------------------------------------------- agrupar
MIN_GRUPO = 3             # abaixo disso, repetir e mais claro que resumir

# Regra que NUNCA se dobra, por mais que se repita.
#
# Agrupar existe para matar ruido: dez "grafo velho" com a mesma acao manual sao
# dez linhas dizendo a mesma coisa. Alerta de seguranca nao e isso. Medido em
# 25/08/2026, os quatro projetos com alerta eram muito diferentes entre si — o
# workspace-medconsultoria com 6 CRITICOS em 19 alertas, e o medconsultoria com
# 93 alertas dos quais 11 baixos. "4 projetos com alertas de seguranca abertos"
# e verdade e nao ajuda: apaga justamente o numero que diz por onde comecar.
#
# Isto e o mesmo defeito que a coleta por severidade consertou um andar abaixo,
# reaparecendo aqui em cima. O ganho do agrupamento (31 pendencias -> 11 linhas)
# cai para 14 linhas, e vale a troca.
NAO_AGRUPAR = {"vulnerabilidade"}

# Rotulo curto por regra, para a linha do grupo. Sem isto o grupo diria
# "10 x grafo_velho", que e nome de variavel, nao portugues.
ROTULO_REGRA = {
    "ci_vermelha": "com a verificação automática vermelha",
    "container_caido": "com contêiner caído",
    "vulnerabilidade": "com alertas de segurança abertos",
    "nao_commitado": "com trabalho sem salvar no histórico",
    "nao_enviado": "com commit que não foi para o GitHub",
    "memoria_crlf": "com memória em quebra de linha do Windows",
    "cota_actions": "com a cota do GitHub estourando",
    "grafo_velho": "com o mapa de código velho",
    "pr_parado": "com pedido de alteração parado",
    "dependencia_insegura": "com dependência a atualizar",
    "env_drift": "com o exemplo de variáveis desatualizado",
    "abandonado": "sem commit há muito tempo",
    "sem_remoto": "sem cópia no GitHub",
    "caso_vazio": "sem descrição escrita",
    "site_fora": "com o site fora do ar",
    "nao_publicado": "com trabalho pronto e não publicado",
    "auditoria_nao_rodou": "cujas dependências não consegui auditar",
    "git_nao_medido": "cujo git não consegui ler",
}


def agrupar(pendencias) -> list:
    """A lista achatada -> a lista que a tela desenha, com os repetidos juntos.

    POR QUE ISTO EXISTE: em 25/08/2026, 10 das 27 pendencias abertas eram a mesma
    regra (grafo velho) em 10 projetos, cada uma com a mesma acao manual. E 37% da
    caixa de entrada dizendo a mesma coisa — exatamente o mecanismo que o filtro
    da regra 2 existe para evitar. Caixa que nasce com muitos alarmes iguais
    ensina o dono a ignorar a caixa inteira, inclusive o alarme que importava.

    E POR QUE E UMA VISAO, NAO UM SUBSTITUTO: o /api/dados continua mandando a
    lista achatada. O botao "Resolver" recalcula a pendencia pelo `id` no
    servidor (e e isso que mantem o prompt fechado a texto de estranho), e o "x"
    de esconder por 24 h tambem e por `id`. Trocar o formato de `pendencias`
    quebraria os dois. Aqui muda o desenho; a identidade nao muda.

    Devolve entradas {"tipo": "item", "pendencia": p} ou
    {"tipo": "grupo", regra, gravidade, n, dias, texto, projetos, acao, itens}.
    """
    por_regra: dict = {}
    for p in pendencias or []:
        por_regra.setdefault(p.get("regra", ""), []).append(p)

    fora = []
    for regra, itens in por_regra.items():
        if len(itens) < MIN_GRUPO or regra in NAO_AGRUPAR:
            fora.extend({"tipo": "item", "pendencia": p} for p in itens)
            continue

        # A pior gravidade manda: um grupo com uma alta dentro nao pode descer
        # para o meio da lista so porque as outras nove sao medias.
        pior = min(ORDEM.get(p.get("gravidade"), 9) for p in itens)
        gravidade = next(g for g, o in ORDEM.items() if o == pior)
        idades = [p["dias"] for p in itens if p.get("dias") is not None]
        mais_velha = max(idades) if idades else None
        projetos = sorted({p.get("projeto", "") for p in itens} - {""})

        texto = "%d projetos %s." % (len(itens),
                                     ROTULO_REGRA.get(regra, "com a mesma pendência"))
        if mais_velha:
            texto = texto[:-1] + " (o mais antigo há %d dias)." % mais_velha

        fora.append({
            "tipo": "grupo", "regra": regra, "gravidade": gravidade,
            "n": len(itens), "dias": mais_velha, "texto": texto,
            "projetos": projetos,
            # "expandir" nao entra em ACOES: aquilo e o contrato das acoes de
            # PENDENCIA, e um grupo nao e uma pendencia. A acao de verdade
            # continua uma por item, dentro.
            "acao": {"tipo": "expandir", "rotulo": "Ver"},
            "itens": sorted(itens, key=lambda p: (-(p.get("dias") or 0),
                                                  p.get("projeto") or "")),
        })

    def chave(x):
        g = x["gravidade"] if x["tipo"] == "grupo" else x["pendencia"]["gravidade"]
        r = x["regra"] if x["tipo"] == "grupo" else x["pendencia"]["regra"]
        proj = "" if x["tipo"] == "grupo" else (x["pendencia"].get("projeto") or "")
        # O risco entra DEPOIS da gravidade: uma media com risco alto continua
        # atras de qualquer alta. Ele so desempata quem ja empatou.
        risco = 0 if x["tipo"] == "grupo" else (x["pendencia"].get("risco") or 0)
        return (ORDEM.get(g, 9), r, -risco, proj)

    fora.sort(key=chave)
    return fora
