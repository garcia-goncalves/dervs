# -*- coding: utf-8 -*-
"""Motor de pendencias do HUB — as 14 regras.

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
nao roda comando — e por isso da para testar as 14 regras em um segundo.
"""
from __future__ import annotations

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


def _p(regra, gravidade, projeto, texto, acao, detalhe=""):
    return {
        "id": "%s:%s" % (regra, projeto),
        "regra": regra,
        "gravidade": gravidade,
        "projeto": projeto,
        "texto": texto,
        "detalhe": detalhe,
        "acao": acao,
    }


def _do_projeto(p: dict) -> list:
    nome = p["nome"]
    caminho = p.get("caminho", "")
    g = p.get("git") or {}
    versionado = bool(g.get("versionado"))
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
            "vulnerabilidade", "alta", nome,
            "%d alerta(s) de segurança aberto(s) em %s." % (v["total"], nome),
            {"tipo": "abrir_url", "rotulo": "Ver os alertas", "url": v.get("url", "")}))

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
                detalhe=pr.get("titulo", "")))
            break          # um item por projeto: a caixa e para agir, nao para listar

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
    if not versionado or not g.get("tem_remoto"):
        itens.append(_p(
            "sem_remoto", "baixa", nome,
            "O %s não tem cópia no GitHub — existe só neste computador." % nome,
            {"tipo": "copiar", "rotulo": "Copiar o comando",
             "texto": "cd %s && git init && gh repo create %s --private --source=. --push"
                      % (caminho, nome)}))

    # 14. Estudo de caso vazio
    if p.get("caso_vazio"):
        itens.append(_p(
            "caso_vazio", "baixa", nome,
            "O %s não tem descrição escrita — o painel sabe medir, não sabe contar "
            "o que ele é." % nome,
            {"tipo": "vscode", "rotulo": "Escrever", "caminho": p.get("casos_json", "")}))

    return itens


def avaliar(projetos, quota=None, silenciadas=None) -> list:
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

    calados = silenciadas or {}
    itens = [i for i in itens if i["id"] not in calados]
    itens.sort(key=lambda i: (ORDEM[i["gravidade"]], i["projeto"], i["regra"]))
    return itens
