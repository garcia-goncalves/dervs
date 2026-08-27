# -*- coding: utf-8 -*-
"""Conferir uma assinatura ECDSA na curva P-256. So conferir.

O QUE ESTE ARQUIVO NAO E: nao e cifra nova, nao e criptografia inventada e nao
guarda segredo nenhum. E a aritmetica publicada da curva P-256 (FIPS 186-4,
tambem chamada secp256r1 e prime256v1), transcrita, para responder UMA
pergunta: "este par de numeros (r, s) foi mesmo produzido pela chave privada
que corresponde a esta chave publica, sobre este resumo?".

A parte secreta — gerar a chave, guardar a chave, assinar — acontece INTEIRA
dentro do aparelho de quem entra: no chip TPM do PC, no chip do celular, na
chave USB. Nada disso passa por aqui. Do nosso lado so chega material publico,
e por isso este arquivo nao precisa de tempo constante: nao ha o que vazar por
tempo de resposta quando tudo que ele toca ja e publico.

POR QUE ESCRITO A MAO. O projeto nao tem dependencia externa — decisao antiga,
registrada em `banco.py` — e o Python nao traz conferencia de ECDSA na
biblioteca padrao. A alternativa era adotar uma dependencia so por isto.
Escolheu-se transcrever ~150 linhas de aritmetica modular fechada, provada
contra os vetores publicados da RFC 6979 em `test_p256.py`. Isso e defensavel
justamente porque e conferencia, e nao geracao: um erro aqui recusa quem devia
entrar (barulhento, aparece na hora) em vez de vazar segredo (silencioso).

FALHA FECHADA em toda porta: qualquer coisa fora do esperado devolve False ou
None. Nunca uma excecao para quem chamou tratar, porque `except` esquecido em
caminho de autenticacao vira porta aberta.
"""
from __future__ import annotations

import hashlib

# Os parametros publicados da P-256. Conferidos em test_p256.py contra a norma,
# e a conferencia nao e cerimonia: um digito trocado aqui produziria uma curva
# diferente, onde as contas fechariam entre si e nao fechariam com o navegador.
P = 0xFFFFFFFF00000001000000000000000000000000FFFFFFFFFFFFFFFFFFFFFFFF
A = -3 % P
B = 0x5AC635D8AA3A93E7B3EBBD55769886BC651D06B0CC53B0F63BCE3C3E27D2604B
N = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551
G = (0x6B17D1F2E12C4247F8BCE6E563A440F277037D812DEB33A0F4A13945D898C296,
     0x4FE342E2FE1A7F9B8EE7EB4A7C0F9E162BCE33576B315ECECBB6406837BF51F5)

# 32 bytes por coordenada, e o ponto nao comprimido leva um 0x04 na frente.
TAMANHO = 32
NAO_COMPRIMIDO = 0x04


# ------------------------------------------------------- aritmetica do ponto
#
# Coordenadas afins, e o ponto no infinito e `None`. Ha representacao mais
# rapida (Jacobiana, que evita uma inversao por passo), e ela foi descartada de
# proposito: uma conferencia custa uns milissegundos, acontece uma vez por
# login, e o codigo abaixo da para ler e comparar linha a linha com a formula
# publicada. Velocidade que ninguem sente nao paga a leitura mais dificil.

def somar(p1, p2):
    """P + Q na curva. `None` e o ponto no infinito, o elemento neutro."""
    if p1 is None:
        return p2
    if p2 is None:
        return p1
    x1, y1 = p1
    x2, y2 = p2
    if x1 == x2:
        # Mesmo x com y oposto: os dois se cancelam e o resultado e o infinito.
        # `(y1 + y2) % P == 0` cobre tambem o caso y1 == y2 == 0, onde a
        # tangente e vertical — dobrar ali dividiria por zero.
        if (y1 + y2) % P == 0:
            return None
        # Dobrar: a inclinacao e a da tangente.
        m = (3 * x1 * x1 + A) * pow(2 * y1, -1, P) % P
    else:
        m = (y2 - y1) * pow(x2 - x1, -1, P) % P
    x3 = (m * m - x1 - x2) % P
    return (x3, (m * (x1 - x3) - y1) % P)


def multiplicar(k, ponto):
    """k*P, por dobrar-e-somar. Devolve `None` quando cai no infinito."""
    if ponto is None or k % N == 0:
        return None
    k = k % N
    resultado = None
    atual = ponto
    while k:
        if k & 1:
            resultado = somar(resultado, atual)
        atual = somar(atual, atual)
        k >>= 1
    return resultado


def ponto_valido(ponto) -> bool:
    """O ponto pertence mesmo a curva?

    Conferir isto e a defesa contra o ataque de curva invalida: uma chave
    publica forjada que cai numa curva vizinha, de ordem pequena, permite
    resolver a chave privada em poucas tentativas. Aqui nao ha chave privada
    nossa em jogo, mas a norma manda conferir e custa tres linhas.
    """
    if not isinstance(ponto, tuple) or len(ponto) != 2:
        return False
    x, y = ponto
    if not isinstance(x, int) or not isinstance(y, int):
        return False
    if not (0 <= x < P and 0 <= y < P):
        return False
    return (y * y - (x * x * x + A * x + B)) % P == 0


def ponto_de_bytes(cru):
    """Le a chave publica no formato que o navegador manda. None se torta.

    So o formato NAO COMPRIMIDO (0x04 + X + Y). O comprimido (0x02/0x03) exige
    extrair raiz quadrada modular; nenhum autenticador em uso manda assim, e
    implementar caminho que ninguem exercita e implementar caminho que ninguem
    testa.
    """
    if not isinstance(cru, (bytes, bytearray)):
        return None
    if len(cru) != 1 + 2 * TAMANHO or cru[0] != NAO_COMPRIMIDO:
        return None
    ponto = (int.from_bytes(cru[1:1 + TAMANHO], "big"),
             int.from_bytes(cru[1 + TAMANHO:], "big"))
    return ponto if ponto_valido(ponto) else None


# ------------------------------------------------------------ a conferencia

def conferir(publica, resumo, r, s) -> bool:
    """A assinatura (r, s) bate com este resumo, sob esta chave publica?

    `resumo` sao os 32 bytes de um SHA-256 ja calculado — nao o texto original.
    A norma manda usar os bits MAIS SIGNIFICATIVOS do resumo quando ele for
    maior que a ordem da curva; com SHA-256 e P-256 os dois tem 256 bits, entao
    nao ha corte a fazer, e o `int.from_bytes` direto e a leitura correta.
    """
    if not isinstance(resumo, (bytes, bytearray)):
        return False
    if not ponto_valido(publica):
        return False
    if not isinstance(r, int) or not isinstance(s, int):
        return False
    # A norma: r e s tem de estar em [1, N-1]. Fora disso a conta degenera —
    # com s = 0 nao ha inverso, e com r = 0 a comparacao final vira trivial.
    if not (1 <= r < N and 1 <= s < N):
        return False

    e = int.from_bytes(resumo, "big")
    w = pow(s, -1, N)
    u1 = e * w % N
    u2 = r * w % N
    ponto = somar(multiplicar(u1, G), multiplicar(u2, publica))
    if ponto is None:
        return False
    return ponto[0] % N == r


def conferir_bytes(publica, mensagem, assinatura_der) -> bool:
    """O caminho de cima, para quem tem a mensagem crua e o DER do navegador."""
    par = assinatura_de_der(assinatura_der)
    if par is None:
        return False
    return conferir(publica, hashlib.sha256(mensagem).digest(), par[0], par[1])


# ------------------------------------------------- desembrulhar o DER de fora
#
# Isto e um PARSER DE DADO HOSTIL, e cada recusa abaixo tem nome.
#
# O navegador entrega a assinatura em DER: uma SEQUENCE com dois INTEGER. E um
# formato com regra de forma canonica, e quem afrouxa a forma abre espaco para
# maleabilidade — a mesma assinatura reescrita de N maneiras diferentes, cada
# uma valida, o que quebra qualquer defesa que dependa de "ja vi esta exata
# assinatura antes". Aqui a forma e conferida byte a byte e o que sobrar
# depois da estrutura reprova o conjunto.

TETO_DO_DER = 80  # 2 INTEGER de ate 33 bytes, mais 6 de estrutura. Sobra folga.


def assinatura_de_der(cru):
    """Devolve (r, s), ou None. NUNCA levanta excecao."""
    if not isinstance(cru, (bytes, bytearray)) or len(cru) < 8:
        return None
    if len(cru) > TETO_DO_DER:
        # Sem teto, um DER de 1 MiB vira um inteiro de 1 MiB e a exponenciacao
        # modular seguinte para o servidor. Recusar pelo tamanho e a defesa
        # mais barata que existe, e vem antes de qualquer leitura.
        return None
    if cru[0] != 0x30:
        return None
    # Comprimento em forma curta apenas: o DER de uma assinatura P-256 nunca
    # passa de 80 bytes, entao a forma longa (0x81...) aqui e sinal de que
    # alguem esta testando o parser, nao um navegador.
    tamanho = cru[1]
    if tamanho > 0x7F or 2 + tamanho != len(cru):
        # A igualdade e o ponto: nao basta caber, tem de terminar exatamente
        # aqui. Sobra no fim e o vetor classico de maleabilidade.
        return None
    corpo = bytes(cru[2:])
    r, resto = _inteiro(corpo)
    if r is None:
        return None
    s, resto = _inteiro(resto)
    if s is None or resto:
        return None
    return (r, s)


def _inteiro(corpo):
    """Le um INTEGER do DER. Devolve (valor, o que sobrou) ou (None, b'')."""
    if len(corpo) < 2 or corpo[0] != 0x02:
        return None, b""
    n = corpo[1]
    if n == 0 or n > 0x7F or len(corpo) < 2 + n:
        # n == 0 e um INTEGER sem digito nenhum, que DER proibe.
        return None, b""
    valor = corpo[2:2 + n]
    if valor[0] & 0x80:
        # Primeiro bit ligado, em DER, e numero NEGATIVO. Assinatura nao tem
        # componente negativo; o formato exige um 0x00 na frente nesse caso, e
        # quem o omite esta mandando outra coisa.
        return None, b""
    if n > 1 and valor[0] == 0x00 and not (valor[1] & 0x80):
        # Zero a esquerda que nao era necessario: forma nao canonica, e o
        # caminho mais simples de reescrever a mesma assinatura de outro jeito.
        return None, b""
    return int.from_bytes(valor, "big"), corpo[2 + n:]
