# -*- coding: utf-8 -*-
"""Recalcula o contraste da paleta do DERVS, lendo assets/dervs.css.

MOTIVO: numero de contraste escrito a mao em documento de design envelhece em
silencio. Aqui a conta e a formula de luminancia relativa da WCAG 2.2.

E LE O CSS DE VERDADE, nao uma copia. Ate 27/08/2026 este script tinha a paleta
digitada dentro dele, duplicada do design.md. No dia em que assets/dervs.css
passou a existir, essa copia virou uma mentira em potencial: bastava alguem
mudar uma cor no CSS para o script continuar aprovando a cor velha, com cara de
verificacao. Verificacao que nao olha o artefato real passa por engano -- e a
lei 2 deste repositorio e que o painel nao pode mentir.

Minimo: 4,5:1 para texto e 3:1 para contorno que carrega significado.
Sai com codigo 1 se qualquer par reprovar, para a CI poder cobrar.

Uso: python docs/esteira/dervs/contraste.py
"""
from __future__ import annotations

import pathlib
import re
import sys

CSS = pathlib.Path(__file__).resolve().parents[3] / "assets" / "dervs.css"

# O nome curto usado aqui -> o token do CSS.
TOKENS = {
    "fundo": "--fundo",
    "elevado": "--fundo-elevado",
    "texto": "--texto",
    "suave": "--texto-suave",
    "borda": "--borda",
    "borda_forte": "--borda-forte",
    "acao": "--acao",
    "acao_texto": "--acao-texto",
    "saudavel": "--estado-saudavel",
    "atencao": "--estado-atencao",
    "quebrado": "--estado-quebrado",
    "sem_dados": "--estado-sem-dados",
}

# Os textos que precisam de 4,5:1 sobre fundo E sobre cartao.
TEXTOS = ("texto", "suave", "saudavel", "atencao", "quebrado", "sem_dados")


def luminancia(cor: str) -> float:
    cor = cor.lstrip("#")
    canais = [int(cor[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    canais = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in canais]
    return 0.2126 * canais[0] + 0.7152 * canais[1] + 0.0722 * canais[2]


def razao(a: str, b: str) -> float:
    la, lb = luminancia(a), luminancia(b)
    alto, baixo = max(la, lb), min(la, lb)
    return (alto + 0.05) / (baixo + 0.05)


def bloco(css: str, seletor: str) -> str:
    """O corpo da primeira regra cujo seletor bate. Sem regex aninhada: acha o
    seletor e le ate a chave que fecha."""
    inicio = css.index(seletor)
    abre = css.index("{", inicio)
    profundidade = 0
    for i in range(abre, len(css)):
        if css[i] == "{":
            profundidade += 1
        elif css[i] == "}":
            profundidade -= 1
            if profundidade == 0:
                return css[abre + 1 : i]
    raise ValueError(f"bloco de {seletor} nao fecha")


def paleta(corpo: str, onde: str) -> dict[str, str]:
    valores = dict(re.findall(r"(--[a-z0-9-]+):\s*(#[0-9a-fA-F]{6})\s*;", corpo))
    faltando = [t for t in TOKENS.values() if t not in valores]
    if faltando:
        raise SystemExit(f"REPROVA: {onde} nao define {', '.join(faltando)}")
    return {curto: valores[token] for curto, token in TOKENS.items()}


def conferir(nome: str, p: dict[str, str]) -> int:
    reprovas = 0
    print("==", nome)
    for chave in TEXTOS:
        sobre_fundo = razao(p[chave], p["fundo"])
        sobre_cartao = razao(p[chave], p["elevado"])
        passou = min(sobre_fundo, sobre_cartao) >= 4.5
        reprovas += 0 if passou else 1
        print(
            "  %-10s fundo %5.2f  elevado %5.2f  %s"
            % (chave, sobre_fundo, sobre_cartao, "OK" if passou else "REPROVA")
        )

    acao = razao(p["acao"], p["acao_texto"])
    passou = acao >= 4.5
    reprovas += 0 if passou else 1
    print("  %-10s %5.2f  %s" % ("acao/texto", acao, "OK" if passou else "REPROVA"))

    print(
        "  %-10s %5.2f  (decorativa, sem exigencia)"
        % ("borda", razao(p["borda"], p["fundo"]))
    )

    forte = razao(p["borda_forte"], p["fundo"])
    passou = forte >= 3.0
    reprovas += 0 if passou else 1
    print(
        "  %-10s %5.2f  %s (min 3,0)" % ("borda-forte", forte, "OK" if passou else "REPROVA")
    )
    return reprovas


def main() -> int:
    if not CSS.exists():
        print(f"REPROVA: {CSS} nao existe")
        return 1
    css = CSS.read_text(encoding="utf-8")
    print(f"lido de {CSS.relative_to(CSS.parents[1])}\n")

    reprovas = conferir("CLARO", paleta(bloco(css, ":root {"), "o bloco :root"))
    reprovas += conferir(
        "ESCURO",
        paleta(bloco(css, ':root[data-theme="dark"]'), 'o bloco [data-theme="dark"]'),
    )

    # O tema do sistema tem de ser identico ao tema escolhido a mao. Se os dois
    # divergirem, quem usa o padrao do sistema ve uma paleta que ninguem mediu.
    do_sistema = paleta(
        bloco(css, ':root:not([data-theme="light"])'), "o bloco do tema do sistema"
    )
    do_botao = paleta(bloco(css, ':root[data-theme="dark"]'), "o bloco do botao")
    if do_sistema != do_botao:
        diferentes = [k for k in do_sistema if do_sistema[k] != do_botao[k]]
        print(f"\nREPROVA: escuro do sistema difere do escuro do botao em {diferentes}")
        reprovas += 1

    print()
    if reprovas:
        print(f"{reprovas} par(es) REPROVA(M).")
        return 1
    print("Todos os pares passam.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
