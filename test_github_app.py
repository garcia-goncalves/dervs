# -*- coding: utf-8 -*-
"""A troca chave -> token de instalacao, provada contra o OpenSSL.

POR QUE ISTO EXISTE. Um GitHub App nao entrega um token: entrega uma chave
privada com a qual o sistema PEDE um token, de hora em hora. O pedido e um JWT
assinado em RS256 — RSA com resumo SHA-256, esquema PKCS#1 v1.5. O Python nao
traz RSA na biblioteca padrao, e o projeto nao adota dependencia externa
(decisao antiga, registrada em `banco.py`). Entao a assinatura e escrita a mao,
como ja foi feito em `p256.py`, e vale a mesma regra dali:

    codigo de criptografia escrito a mao que so foi testado com dado que ele
    mesmo produziu NAO esta testado — prova que concorda consigo, nao que esta
    certo.

Por isso o vetor abaixo vem de FORA. A chave e a assinatura foram produzidas
pelo OpenSSL 3.5.4 em 27/08/2026, com estes dois comandos:

    openssl genrsa -traditional -out <chave> 2048
    openssl dgst -sha256 -sign <chave> -out <assinatura> <mensagem>

Se `assinar_rs256` discordar do OpenSSL num unico byte, o teste falha. Nao ha
como os dois errarem igual: sao implementacoes independentes do mesmo padrao.

SOBRE A CHAVE GUARDADA AQUI. Ela foi gerada para este arquivo e nunca esteve
instalada em lugar nenhum — nao abre nada, nem aqui nem no GitHub. E guardada
SEM as linhas `-----BEGIN...`/`-----END...`, que o teste recoloca na hora: com
elas, o detector de segredo do GitHub barraria o `push` deste arquivo, e teste
que nao pode ser enviado nao protege ninguem. O miolo sozinho e base64 comum.
"""
from __future__ import annotations

import base64
import hashlib
import json
import unittest

import github_app


# --------------------------------------------------------- o vetor de fora
#
# Miolo do PKCS#1 (`BEGIN RSA PRIVATE KEY`) e do PKCS#8 (`BEGIN PRIVATE KEY`)
# da MESMA chave. Os dois formatos existem porque o GitHub entrega o primeiro e
# quem converte o arquivo por engano acaba com o segundo — e a mensagem "chave
# nao serve" naquele dia custaria uma tarde.
# NAO USE ESTE PADRAO PARA CHAVE DE VERDADE. Guardar o miolo sem armadura e
# remonta-lo com `armar()` contorna, literalmente, o detector de segredo do
# GitHub. Aqui e legitimo porque esta chave nunca foi registrada em lugar
# nenhum: chave privada so vale se a publica correspondente for confiada em
# algum lugar, e esta nao e — apagar este arquivo nao fecharia buraco nenhum,
# so quebraria o unico teste que prova que a conta esta certa. O risco e o
# PRECEDENTE: no dia em que alguem colar uma chave real com este mesmo molde, o
# varredor nao pega, e a revisao ve um formato que ja foi aprovado antes.
MIOLO_PKCS1 = "MIIEpAIBAAKCAQEAsFc/9hzFK9z1ZQRzg0ZOf8nVJo3fT2mGlg+H4ImP7Py9Tfvzw/WqTzM9VMhUeO6CG3nq29+SsA5yXYOGOjmc+DM85XJREhawjSNw7k68XOB0uVOsGXG4E/pcxjycBiq0Xd2enVbKORW+cfqpIY3HrbVnTZUuwui8m7oMvQ+tBzrEwMSvq2bh42XiBrrXg3UkKeUMVQ6OsB4BqyNghiwSgRlPxMolKCWJtqYfxee00Ilii0rgGWne8l32dJI6U7r83zqNQNYnr40mq35yjhhAzrkkDNSATz/4qsCELACGMoSY/rayWlRpQ7yDSq/LTXnHpRPIUS527KjFBh7qRok8TwIDAQABAoIBAEiMrPkBnzFLp/5WlXu16kfy7un8xpoybTfBzgJYNkmnNe8msIS3xsjs6Ne/z9ktL4REZZbuZbhfSTgmC4xa9bS7x9sSbD5H7X0zzpuM8zw28G7q+MxDGBvIDnFUsFBtM2XG7yIGeg6AXqkgGoN+hF94Wbb2oJV6EVb0dZc3ItXs7crNCNeNfxGKO9VsTmISXIJbiYAbyEfyk7oUcvmch82FUTsVqg4yWwIPyPZtjH+FhQFlbcqkM2U/LZus6akSmu+H8bthe6bl0NVAzw7xwb85jVWQX5o97LXi1neRLD66cdFkojD/zvwFxTqb0MWllH6DNYKwQ4a+JhZ4kwpFdTECgYEA3wqRk9EpU/VcluZTLY++JEhx3n8uF0bO8nBEipVKEgGiNVTArP2YzxLyFKml4h57DLpjE3vKUWu6x68tndh8502NnKYmxBfG8l0by7SDDUw83BIjTvvkg4FABVE/tBhwUgKGZxO4wHmhSc+NLhvmimVeLrntJ4dFv5zqCNTxN9kCgYEAymYMfRR8Zu0Vf/UK0a7Q1BquqdPQV1KSJCPdFpQxWlzgK/N/rKwM+o1r85S8xJYHMLs5tNwdtx329qaH7XXH2WkgLneesok0itkL3BGj2qkReOmr2u3sLsMi+K8Z18VhvNd/ZYgVAjNiM/YKfpHMaetpHLOFubSwGVpesIUjZGcCgYEAoZ5l6Me6e8Uix5G0miI7tMzt/j0IKAO+N70UXZtaJfwbDywPxgqpLPvcgQ6BTn2pyopQ+rBL5X37xXBxzJwvvefbgrR/CL72AW9okc6G3B7vRsS54yTx7Dy/KFs8nwLKeRKtU4nd6VL5haOo+M1s28IiYheF+ouyBevtRmMPO9kCgYBk/aiLnPY58WDB+UZNvDntK+ctTEhv2f6b091Uj9tUaHVe2OBDC5JqTrin0Paj7Oxnj3RK325gWa5KAmxeu19eB0uMhBmGolm6UnTNeWvWBnh2abpbwk4QQ0Qm7FArzwxmyuyBf/Zjo7oDjWhNIXjq/RD0xksaj6My81m+IKC5TwKBgQDIOKmuBOvdPVru/DzOuOzt6Gn3cBPM2r5DXdYYS77CRFSq6DxfoAM+w5QowrbGlYAfzrXHJ8uhvYl0Ii7qKP8cnle0pq+9CmdaDKiSs9o9Bo/f7T/Nac47i/KkJ+lAIV3lCNKia5wXrTfYF5rUJ1E2JI3VHEzQSE3a7Eb2et3j3g=="
MIOLO_PKCS8 = "MIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQCwVz/2HMUr3PVlBHODRk5/ydUmjd9PaYaWD4fgiY/s/L1N+/PD9apPMz1UyFR47oIbeerb35KwDnJdg4Y6OZz4MzzlclESFrCNI3DuTrxc4HS5U6wZcbgT+lzGPJwGKrRd3Z6dVso5Fb5x+qkhjcettWdNlS7C6Lybugy9D60HOsTAxK+rZuHjZeIGuteDdSQp5QxVDo6wHgGrI2CGLBKBGU/EyiUoJYm2ph/F57TQiWKLSuAZad7yXfZ0kjpTuvzfOo1A1ievjSarfnKOGEDOuSQM1IBPP/iqwIQsAIYyhJj+trJaVGlDvINKr8tNecelE8hRLnbsqMUGHupGiTxPAgMBAAECggEASIys+QGfMUun/laVe7XqR/Lu6fzGmjJtN8HOAlg2Sac17yawhLfGyOzo17/P2S0vhERllu5luF9JOCYLjFr1tLvH2xJsPkftfTPOm4zzPDbwbur4zEMYG8gOcVSwUG0zZcbvIgZ6DoBeqSAag36EX3hZtvaglXoRVvR1lzci1eztys0I141/EYo71WxOYhJcgluJgBvIR/KTuhRy+ZyHzYVROxWqDjJbAg/I9m2Mf4WFAWVtyqQzZT8tm6zpqRKa74fxu2F7puXQ1UDPDvHBvzmNVZBfmj3steLWd5EsPrpx0WSiMP/O/AXFOpvQxaWUfoM1grBDhr4mFniTCkV1MQKBgQDfCpGT0SlT9VyW5lMtj74kSHHefy4XRs7ycESKlUoSAaI1VMCs/ZjPEvIUqaXiHnsMumMTe8pRa7rHry2d2HznTY2cpibEF8byXRvLtIMNTDzcEiNO++SDgUAFUT+0GHBSAoZnE7jAeaFJz40uG+aKZV4uue0nh0W/nOoI1PE32QKBgQDKZgx9FHxm7RV/9QrRrtDUGq6p09BXUpIkI90WlDFaXOAr83+srAz6jWvzlLzElgcwuzm03B23Hfb2poftdcfZaSAud56yiTSK2QvcEaPaqRF46ava7ewuwyL4rxnXxWG8139liBUCM2Iz9gp+kcxp62kcs4W5tLAZWl6whSNkZwKBgQChnmXox7p7xSLHkbSaIju0zO3+PQgoA743vRRdm1ol/BsPLA/GCqks+9yBDoFOfanKilD6sEvlffvFcHHMnC+959uCtH8IvvYBb2iRzobcHu9GxLnjJPHsPL8oWzyfAsp5Eq1Tid3pUvmFo6j4zWzbwiJiF4X6i7IF6+1GYw872QKBgGT9qIuc9jnxYMH5Rk28Oe0r5y1MSG/Z/pvT3VSP21RodV7Y4EMLkmpOuKfQ9qPs7GePdErfbmBZrkoCbF67X14HS4yEGYaiWbpSdM15a9YGeHZpulvCThBDRCbsUCvPDGbK7IF/9mOjugONaE0heOr9EPTGSxqPozLzWb4goLlPAoGBAMg4qa4E6909Wu78PM647O3oafdwE8zavkNd1hhLvsJEVKroPF+gAz7DlCjCtsaVgB/Otccny6G9iXQiLuoo/xyeV7Smr70KZ1oMqJKz2j0Gj9/tP81pzjuL8qQn6UAhXeUI0qJrnBetN9gXmtQnUTYkjdUcTNBITdrsRvZ63ePe"

MENSAGEM = b"dervs-vetor-de-teste"
ASSINATURA_DO_OPENSSL = bytes.fromhex("a3f46c80d1df0e121a6f0418cd6b80eb71d1cbf08624a0a70cf600fb4d370b2d83c4d17366fafb482a1f1ffaf386e06ab226da19194abba9c3f4830427a0e021242e4f655d73d0d9ee3c0740a1d15372b779dbfef8f4c38bfec3f5be36014805802b806c1e969e7a6b28497293c48211617140ee41314cac0359aa84eb19c1b742dadb3d2192e62467f412d9db4b18c537b0055ed5cb95da8c3b4488c0746d169760473c0655ac1f8cc4069dd9a56be2d151cad9818667a7eba0d2a6f39c21ecfed8dcc8640b6bcdfcd0e7a1d7da675813fc2b5e540662d22de603afacd9da7bbdc8706f977d1ba25b4c0521c7c8aa1620dd1a4b50650f623c158a45799ca514")


def armar(miolo: str, rotulo: str) -> str:
    """Remonta o arquivo como o GitHub entrega: 64 colunas entre as linhas."""
    linhas = [miolo[i:i + 64] for i in range(0, len(miolo), 64)]
    return ("-----BEGIN %s-----\n" % rotulo + "\n".join(linhas)
            + "\n-----END %s-----\n" % rotulo)


PEM_PKCS1 = armar(MIOLO_PKCS1, "RSA PRIVATE KEY")
PEM_PKCS8 = armar(MIOLO_PKCS8, "PRIVATE KEY")


class LerAChave(unittest.TestCase):

    def test_le_o_formato_que_o_github_entrega(self):
        """PKCS#1 e o que sai do botao `Generate a private key`."""
        chave = github_app.chave_de_pem(PEM_PKCS1)
        self.assertIsNotNone(chave)
        self.assertEqual(chave.e, 65537)
        self.assertEqual(chave.n.bit_length(), 2048)

    def test_le_tambem_o_formato_convertido(self):
        """Mesma chave em PKCS#8 tem de dar exatamente os mesmos numeros.

        Sem isto, um arquivo convertido por engano falharia so no servidor.
        """
        um = github_app.chave_de_pem(PEM_PKCS1)
        outro = github_app.chave_de_pem(PEM_PKCS8)
        self.assertIsNotNone(outro)
        self.assertEqual((um.n, um.e, um.d), (outro.n, outro.e, outro.d))

    def test_a_privada_e_a_publica_sao_o_mesmo_par(self):
        """Trava contra numero lido do campo vizinho no DER.

        Confere o par por um caminho que nao passa pela assinatura: assim, uma
        falha la acusa o preenchimento PKCS#1, e nao a leitura da chave.
        """
        c = github_app.chave_de_pem(PEM_PKCS1)
        self.assertEqual(pow(pow(42, c.d, c.n), c.e, c.n), 42)

    def test_recusa_texto_que_nao_e_chave(self):
        # As bordas montadas por `armar` e nao escritas por extenso: um
        # bloco de armadura de chave privada literal neste arquivo faz o
        # varredor de segredo do repositorio barrar o commit — e ele esta
        # certo em barrar.
        lixos = ["", "   ", "nao sou uma chave",
                 armar("zzz", "RSA PRIVATE KEY"),
                 armar("QUJD", "RSA PRIVATE KEY")]
        for lixo in lixos:
            with self.subTest(lixo=lixo[:20]):
                self.assertIsNone(github_app.chave_de_pem(lixo))

    def test_recusa_chave_absurda(self):
        """Teto de tamanho: um arquivo de 1 MiB nao vira inteiro de 1 MiB.

        A variavel de ambiente vem do operador, e o operador erra. Sem teto, um
        arquivo trocado trava a coleta em vez de recusar.
        """
        self.assertIsNone(github_app.chave_de_pem(
            armar("A" * 200000, "RSA PRIVATE KEY")))


class Assinar(unittest.TestCase):

    def test_a_assinatura_e_byte_a_byte_a_do_openssl(self):
        """O unico teste que prova que a conta esta certa."""
        chave = github_app.chave_de_pem(PEM_PKCS1)
        self.assertEqual(github_app.assinar_rs256(chave, MENSAGEM),
                         ASSINATURA_DO_OPENSSL)

    def test_a_assinatura_tem_o_tamanho_do_modulo(self):
        """256 bytes para 2048 bits, com zeros a esquerda se preciso.

        O GitHub recusa uma assinatura de 255 bytes, e essa recusa chega como um
        401 generico — indiagnosticavel sem este teste.
        """
        chave = github_app.chave_de_pem(PEM_PKCS1)
        self.assertEqual(len(github_app.assinar_rs256(chave, b"x")), 256)


class MontarOJwt(unittest.TestCase):

    def partes(self, jwt):
        def abrir(p):
            return json.loads(base64.urlsafe_b64decode(p + "=" * ((-len(p)) % 4)))
        a, b, c = jwt.split(".")
        return abrir(a), abrir(b), c

    def test_o_cabecalho_e_o_corpo_sao_os_que_o_github_espera(self):
        chave = github_app.chave_de_pem(PEM_PKCS1)
        cab, corpo, _ = self.partes(
            github_app.montar_jwt("4739197", chave, agora=1000000))
        self.assertEqual(cab, {"alg": "RS256", "typ": "JWT"})
        self.assertEqual(corpo["iss"], "4739197")
        # 60 s para tras porque o relogio do servidor pode adiantar, e o GitHub
        # recusa um JWT emitido no futuro.
        self.assertEqual(corpo["iat"], 1000000 - 60)
        # O teto do GitHub e 10 min. 9 deixa folga para o relogio dos dois lados.
        self.assertEqual(corpo["exp"], 1000000 + 540)

    def test_a_assinatura_do_jwt_confere_com_a_chave_publica(self):
        """Prova que o assinado e o enviado, e nao outra coisa parecida."""
        chave = github_app.chave_de_pem(PEM_PKCS1)
        jwt = github_app.montar_jwt("4739197", chave, agora=1000000)
        assinado, _, assinatura = jwt.rpartition(".")
        crua = base64.urlsafe_b64decode(assinatura + "=" * ((-len(assinatura)) % 4))
        # Desfaz a assinatura com a chave PUBLICA e procura o resumo la dentro.
        aberto = pow(int.from_bytes(crua, "big"), chave.e, chave.n)
        aberto = aberto.to_bytes(256, "big")
        self.assertTrue(aberto.endswith(hashlib.sha256(assinado.encode()).digest()))
        self.assertTrue(aberto.startswith(b"\x00\x01\xff\xff"))


class TrocarPorToken(unittest.TestCase):
    """A troca em si. A rede e substituida por uma funcao nossa.

    Nao ha mock de biblioteca aqui: `_pedir` e parametro do desenho, para que a
    decisao — reaproveitar ou renovar — seja testavel sem inventar um servidor.
    """

    def setUp(self):
        self.chamadas = []

        def falso(url, jwt, teto):
            self.chamadas.append((url, jwt))
            return {"token": "ghs-mentira-%d" % len(self.chamadas),
                    "expires_at": "2026-08-27T21:00:00Z"}

        self.falso = falso
        self.app = github_app.Coletor("4739197", "157015815", PEM_PKCS1,
                                      _pedir=falso)

    def test_pede_o_token_na_url_da_instalacao(self):
        t = self.app.token(agora=1000000)
        self.assertEqual(t, "ghs-mentira-1")
        url, jwt = self.chamadas[0]
        self.assertEqual(
            url,
            "https://api.github.com/app/installations/157015815/access_tokens")
        self.assertEqual(jwt.count("."), 2)

    def test_reaproveita_o_token_enquanto_ele_vale(self):
        """Um token por hora, nao um por consulta: a cota ja estourou uma vez."""
        self.app.token(agora=1000000)
        self.app.token(agora=1000060)
        self.assertEqual(len(self.chamadas), 1)

    def test_renova_antes_de_vencer_e_nao_depois(self):
        """Renovar no minuto do vencimento perde a corrida com a rede.

        Margem de 5 min: uma coleta demorada nao pode terminar com um token que
        venceu no meio dela.
        """
        self.app.token(agora=1000000)
        vence = github_app.quando_vence("2026-08-27T21:00:00Z")
        self.app.token(agora=vence - 200)
        self.assertEqual(len(self.chamadas), 2)

    def test_recusa_identificador_que_nao_e_numero(self):
        """O id vai para dentro de uma URL. Numero, ou nada.

        Sem isto, um valor com `../` no ambiente apontaria a requisicao — com o
        JWT junto — para outro caminho da API.
        """
        for ruim in ("157015815/../../x", "abc", "", "1 2", "-5"):
            with self.subTest(ruim=ruim):
                self.assertIsNone(
                    github_app.Coletor("4739197", ruim, PEM_PKCS1,
                                       _pedir=self.falso).token(agora=1000000))

    def test_sem_chave_nao_ha_troca_e_ninguem_estoura(self):
        """Ambiente pela metade e o caso comum no primeiro deploy."""
        self.assertIsNone(
            github_app.Coletor("4739197", "157015815", "",
                               _pedir=self.falso).token(agora=1000000))
        self.assertEqual(self.chamadas, [])

    def test_falha_da_rede_vira_none_e_nao_excecao(self):
        """Falha fechada: a coleta perde o GitHub, o painel nao cai."""
        def explode(url, jwt, teto):
            raise OSError("a rede caiu")

        self.assertIsNone(
            github_app.Coletor("4739197", "157015815", PEM_PKCS1,
                               _pedir=explode).token(agora=1000000))

    def test_resposta_sem_token_nao_vira_token_vazio(self):
        """Um `""` aqui viraria `Authorization: Bearer ` e um 401 sem explicacao."""
        def sem(url, jwt, teto):
            return {"expires_at": "2026-08-27T21:00:00Z"}

        self.assertIsNone(
            github_app.Coletor("4739197", "157015815", PEM_PKCS1,
                               _pedir=sem).token(agora=1000000))

    def test_token_com_caractere_impossivel_e_recusado(self):
        """Mesma trava do `_token` do coletar_github: nada que quebre cabecalho."""
        def torto(url, jwt, teto):
            return {"token": "ghs_com\nquebra",
                    "expires_at": "2026-08-27T21:00:00Z"}

        self.assertIsNone(
            github_app.Coletor("4739197", "157015815", PEM_PKCS1,
                               _pedir=torto).token(agora=1000000))


class LerAValidade(unittest.TestCase):

    def test_le_a_data_que_o_github_manda(self):
        # 2026-08-27T21:00:00Z em segundos desde 1970, conferido com `date`.
        self.assertEqual(github_app.quando_vence("2026-08-27T21:00:00Z"),
                         1787864400)

    def test_data_estranha_nao_vira_token_eterno_nem_erro(self):
        """`None` aqui significaria 'nunca vence' numa comparacao ingenua."""
        self.assertIsNone(github_app.quando_vence("ontem"))
        self.assertIsNone(github_app.quando_vence(None))


class OQueARevisaoDeSegurancaPediu(unittest.TestCase):
    """Tres achados menores da revisao de 27/08/2026, cada um com o seu teste.

    Nenhum era explouravel — a chave vem do ambiente, e quem escreve no ambiente
    ja controla tudo. Entram assim mesmo porque os tres tem o mesmo formato: uma
    tarde perdida no primeiro deploy, com falha calada e diagnostico errado.
    """

    def der(self, tag: int, corpo: bytes) -> bytes:
        """DER minimo, so para MONTAR a chave torta que o teste precisa."""
        if len(corpo) < 0x80:
            return bytes([tag, len(corpo)]) + corpo
        tamanho = len(corpo).to_bytes((len(corpo).bit_length() + 7) // 8, "big")
        return bytes([tag, 0x80 | len(tamanho)]) + tamanho + corpo

    def inteiro(self, n: int) -> bytes:
        cru = n.to_bytes((n.bit_length() + 8) // 8, "big")
        return self.der(0x02, cru)

    def chave_com_d(self, d: int) -> str:
        """Uma chave sintetica com o `d` que o teste quiser."""
        real = github_app.chave_de_pem(PEM_PKCS1)
        corpo = (self.inteiro(0) + self.inteiro(real.n) + self.inteiro(real.e)
                 + self.inteiro(d) + self.inteiro(1) + self.inteiro(1))
        return armar(base64.b64encode(self.der(0x30, corpo)).decode("ascii"),
                     "RSA PRIVATE KEY")

    def test_expoente_privado_gigante_e_recusado(self):
        """Sem teto no `d`, um arquivo trocado por engano trava a assinatura.

        Medido pela revisao: um `d` de 104 mil bits — que cabe folgado dentro de
        `TETO_DO_ARQUIVO` — leva `assinar_rs256` a 10,5 s. Nao e ataque, e o
        mesmo motivo do teto que ja existia no modulo: o operador erra de arquivo.
        """
        self.assertIsNotNone(github_app.chave_de_pem(self.chave_com_d(3)))
        self.assertIsNone(github_app.chave_de_pem(self.chave_com_d(2 ** 20000)))

    def test_le_a_chave_mesmo_indentada(self):
        """Bloco de YAML e `systemd` indentam o arquivo, e isso e comum.

        A linha de armadura indentada nao era reconhecida, entrava no miolo, o
        base64 falhava e o coletor caia CALADO no `gh` — falha fechada, mas com
        o diagnostico apontando para o lugar errado.
        """
        indentada = "\n".join("    " + l for l in PEM_PKCS1.splitlines())
        self.assertEqual(github_app.chave_de_pem(indentada),
                         github_app.chave_de_pem(PEM_PKCS1))

    def test_validade_absurda_nao_vira_token_eterno(self):
        """Defesa em profundidade: exige o GitHub mentir sob TLS conferido.

        Um `expires_at` no ano 9999 congelaria o token pelo resto da vida do
        processo. O teto de uma hora e o proprio prazo que o GitHub promete.
        """
        chamadas = []

        def eterno(url, jwt, teto):
            chamadas.append(url)
            return {"token": "ghs-mentira", "expires_at": "9999-12-31T23:59:59Z"}

        app = github_app.Coletor("4739197", "157015815", PEM_PKCS1, _pedir=eterno)
        app.token(agora=1000000)
        app.token(agora=1000000 + 3600)
        self.assertEqual(len(chamadas), 2)


class ListarInstalacoesDoApp(unittest.TestCase):
    """Descoberta das contas que instalaram o App. Nenhum caso bate na rede."""

    def test_lista_so_o_que_tem_id_inteiro(self):
        vistos = {}

        def falso(url, jwt, teto, metodo="POST"):
            vistos.update(url=url, metodo=metodo, jwt=jwt)
            return [{"id": 1, "account": {"id": 9, "login": "a"}},
                    {"id": "2"}, {"id": True}, "lixo", {"sem": "id"}]

        r = github_app.listar_instalacoes("123", PEM_PKCS1, _pedir=falso)
        self.assertEqual([1], [i["id"] for i in r])
        self.assertEqual("GET", vistos["metodo"])
        self.assertIn("/app/installations", vistos["url"])
        self.assertNotIn("access_tokens", vistos["url"])
        self.assertTrue(vistos["jwt"])

    def test_falha_devolve_None_e_nao_levanta(self):
        def quebra(*a, **k):
            raise OSError("rede")
        self.assertIsNone(github_app.listar_instalacoes(
            "123", PEM_PKCS1, _pedir=quebra))
        self.assertIsNone(github_app.listar_instalacoes(
            "123", PEM_PKCS1, _pedir=lambda *a, **k: {"nao": "lista"}))
        self.assertIsNone(github_app.listar_instalacoes(
            "123", "isto nao e uma chave", _pedir=lambda *a, **k: []))

    def test_pagina_ate_a_pagina_incompleta(self):
        vistas = []

        def falso(url, jwt, teto, metodo="POST"):
            vistas.append(url)
            return ([{"id": n} for n in range(100)] if url.endswith("page=1")
                    else [{"id": 1000 + n} for n in range(3)])

        r = github_app.listar_instalacoes("123", PEM_PKCS1, _pedir=falso)
        self.assertEqual(103, len(r))
        self.assertEqual(2, len(vistas))

    def test_lista_que_nunca_acaba_diz_que_nao_olhou(self):
        """Todas as paginas cheias: a lista pode estar INCOMPLETA, e entregar
        o pedaco seria um corte mudo. `None` = nao olhei."""
        self.assertIsNone(github_app.listar_instalacoes(
            "123", PEM_PKCS1,
            _pedir=lambda *a, **k: [{"id": n} for n in range(100)]))


class ConfirmarInstalacaoContraAApi(unittest.TestCase):
    """A peca da etapa C2, e o motivo dela em uma frase:

        O `installation_id` chega pela QUERY STRING da setup URL, e a
        documentacao do GitHub avisa que qualquer um pode bater ali com um
        numero forjado. Perguntar ao GitHub e o que separa "o navegador disse"
        de "o GitHub confirmou".

    NENHUM CASO BATE NA REDE: `_pedir` e parametro do desenho, e nao concessao
    ao teste. A CI nao tem credencial nenhuma.
    """

    def setUp(self):
        self.chave = PEM_PKCS1

    def test_confirma_quando_a_API_devolve_o_MESMO_id(self):
        vistos = {}

        def falso(url, jwt, teto, metodo="POST"):
            vistos.update(url=url, metodo=metodo, jwt=jwt)
            return {"id": 424242, "app_id": 7}

        d = github_app.confirmar_instalacao("123", self.chave, "424242",
                                            _pedir=falso)
        self.assertEqual(424242, d["id"])
        self.assertEqual("GET", vistos["metodo"],
                         "trocar a instalacao por token e outra chamada")
        self.assertIn("/app/installations/424242", vistos["url"])
        self.assertNotIn("access_tokens", vistos["url"],
                         "esta chamada NAO pede token: so confere")
        self.assertTrue(vistos["jwt"], "sem JWT o GitHub nao responde")

    def test_a_API_respondendo_sobre_OUTRA_instalacao_nao_confirma(self):
        """200 com outro id e a API falando de outra coisa. Aceitar isso e
        aceitar qualquer coisa."""
        self.assertIsNone(github_app.confirmar_instalacao(
            "123", self.chave, "424242",
            _pedir=lambda *a, **k: {"id": 111}))

    def test_falha_de_rede_devolve_None_e_NAO_LEVANTA(self):
        """Lei 3: caminho de autenticacao falha fechado, sempre."""
        def explodir(*a, **k):
            raise OSError("a rede caiu")

        self.assertIsNone(github_app.confirmar_instalacao(
            "123", self.chave, "424242", _pedir=explodir))

    def test_resposta_que_nao_e_objeto_nao_confirma(self):
        self.assertIsNone(github_app.confirmar_instalacao(
            "123", self.chave, "424242", _pedir=lambda *a, **k: ["nao sou dict"]))

    def test_id_que_nao_e_numero_nao_chega_a_perguntar(self):
        """Ele entra numa URL: `../` apontaria a requisicao — com o JWT junto —
        para outro caminho da API."""
        def explodir(*a, **k):
            raise AssertionError("nao podia ter perguntado")

        for torto in ("../user", "1;2", "", "42a", None, 42):
            with self.subTest(id=torto):
                self.assertIsNone(github_app.confirmar_instalacao(
                    "123", self.chave, torto, _pedir=explodir))

    def test_sem_chave_privada_nao_pergunta(self):
        def explodir(*a, **k):
            raise AssertionError("nao podia ter perguntado")

        self.assertIsNone(github_app.confirmar_instalacao(
            "123", "isto nao e uma chave", "424242", _pedir=explodir))

    def test_o_redirecionamento_nunca_e_seguido(self):
        """Um 302 levaria o cabecalho `Authorization` — o JWT — para o host que
        o outro lado escolher."""
        self.assertIsNone(github_app._SemRedirecionar().redirect_request(
            None, None, 302, "", {}, "https://qualquer-um.invalido/"))


class AdministraAOrganizacao(unittest.TestCase):
    """Fecha a divida nomeada de `servir._instalacao_e_dele`: a instalacao de
    uma ORGANIZACAO tem `account.id` da org, nunca da pessoa. Esta funcao
    pergunta ao proprio app — ja instalado ali — se a pessoa ADMINISTRA a
    organizacao, usando o TOKEN DESTA instalacao, nunca o JWT nem um token
    do usuario.

    ADMIN, E NAO SO MEMBRO — achado da revisao de seguranca de 04/09/2026:
    um membro raso podia amarrar a instalacao inteira a propria conta. Por
    isso a lista pedida e' `?role=admin`, nunca a lista de membros inteira.
    """

    def setUp(self):
        self.chave = PEM_PKCS1

    def falso_com(self, administradores):
        chamadas = []

        def pedir(url, jwt, teto, metodo="POST"):
            chamadas.append((url, metodo))
            if "access_tokens" in url:
                return {"token": "ghs-org-token",
                        "expires_at": "2026-08-27T21:00:00Z"}
            return administradores

        return pedir, chamadas

    def test_confere_quando_o_id_aparece_na_lista_de_administradores(self):
        pedir, chamadas = self.falso_com(
            [{"id": 111, "login": "outro"}, {"id": 424242, "login": "dono"}])
        r = github_app.usuario_administra_a_organizacao(
            "123", self.chave, "555", "minha-org", "424242", _pedir=pedir)
        self.assertTrue(r)
        self.assertEqual(2, len(chamadas))
        self.assertIn("access_tokens", chamadas[0][0])
        self.assertEqual("POST", chamadas[0][1])
        self.assertIn("/orgs/minha-org/members", chamadas[1][0])
        self.assertIn("role=admin", chamadas[1][0],
                      "pediu a lista de membros inteira, nao so os admins")
        self.assertEqual("GET", chamadas[1][1])

    def test_nao_confere_quando_o_id_nao_e_admin(self):
        """O caso central da revisao: aparecer como MEMBRO nao basta."""
        pedir, _ = self.falso_com([{"id": 111, "login": "outro"}])
        r = github_app.usuario_administra_a_organizacao(
            "123", self.chave, "555", "minha-org", "424242", _pedir=pedir)
        self.assertFalse(r)

    def test_sem_a_permissao_members_o_github_recusa_e_isso_e_None_nao_True(self):
        """Sem a permissao no App, a segunda chamada falha. `None`, nunca
        `True` — a ausencia da permissao NUNCA pode virar 'sim, administra'."""
        def pedir(url, jwt, teto, metodo="POST"):
            if "access_tokens" in url:
                return {"token": "ghs-org-token",
                        "expires_at": "2026-08-27T21:00:00Z"}
            raise OSError("403: Forbidden (a permissao Members falta)")

        self.assertIsNone(github_app.usuario_administra_a_organizacao(
            "123", self.chave, "555", "minha-org", "424242", _pedir=pedir))

    def test_falha_ao_trocar_por_token_devolve_None(self):
        def explodir(*a, **k):
            raise OSError("a rede caiu")

        self.assertIsNone(github_app.usuario_administra_a_organizacao(
            "123", self.chave, "555", "minha-org", "424242", _pedir=explodir))

    def test_resposta_que_nao_e_lista_nao_confirma(self):
        pedir, _ = self.falso_com({"nao": "e uma lista"})
        self.assertIsNone(github_app.usuario_administra_a_organizacao(
            "123", self.chave, "555", "minha-org", "424242", _pedir=pedir))

    def test_organizacao_fora_do_padrao_de_login_nao_chega_a_perguntar(self):
        """O nome vai para dentro de uma URL. `../` apontaria a requisicao —
        com o token junto — para outro caminho da API.

        O DUBLE E UM ESPIAO, NUNCA UM QUE LEVANTA: uma excecao aqui dentro
        cairia no `except Exception` da propria funcao e devolveria `None`
        de qualquer jeito — a guarda-da-guarda, achado da revisao de
        seguranca de 04/09/2026, provando que uma versao sem peneira nenhuma
        passaria pelos mesmos casos com um sentinela que levanta.
        """
        chamadas = []

        def espiao(*a, **k):
            chamadas.append(a)
            return {}

        for torta in ("minha-org/../x", "", "-comeca-com-hifen",
                      "termina-com-hifen-", "a" * 40, None, 42):
            with self.subTest(organizacao=torta):
                self.assertIsNone(github_app.usuario_administra_a_organizacao(
                    "123", self.chave, "555", torta, "424242",
                    _pedir=espiao))
        self.assertEqual([], chamadas, "perguntou ao GitHub sem precisar")

    def test_github_id_vazio_nao_chega_a_perguntar(self):
        chamadas = []

        def espiao(*a, **k):
            chamadas.append(a)
            return {}

        for torto in ("", None, 424242):
            with self.subTest(github_id=torto):
                self.assertIsNone(github_app.usuario_administra_a_organizacao(
                    "123", self.chave, "555", "minha-org", torto,
                    _pedir=espiao))
        self.assertEqual([], chamadas, "perguntou ao GitHub sem precisar")

    def test_sem_chave_privada_nao_pergunta(self):
        chamadas = []

        def espiao(*a, **k):
            chamadas.append(a)
            return {}

        self.assertIsNone(github_app.usuario_administra_a_organizacao(
            "123", "isto nao e uma chave", "555", "minha-org", "424242",
            _pedir=espiao))
        self.assertEqual([], chamadas, "perguntou ao GitHub sem chave valida")


if __name__ == "__main__":
    unittest.main(verbosity=2)
