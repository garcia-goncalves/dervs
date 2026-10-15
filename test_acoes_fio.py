# -*- coding: utf-8 -*-
"""O FIO INTEIRO dos pedidos ao servidor (entrega C, etapa F).

MOTIVO: as tres pontas dos pedidos foram provadas cada uma contra duble.
`test_ajudante_acoes` roda o ajudante contra um painel de mentira,
`test_ordens_servidor` conversa com o servidor assinando com uma chave de TESTE,
e `test_pedidos_tela` executa o `painel.js` em node com respostas inventadas.
Ninguem provava que a ordem que o DERVS monta e a que o ajudante confere sao o
mesmo texto, nem que o que a tela le e o que o servidor entrega -- o buraco que
ja deixou 26 suites verdes com a Auditoria morta.

Aqui o ajudante e BAIXADO de `/ajudante/servidor.py`, instalado com `--ordens`
numa raiz temporaria (Docker falso) e conversa com o servidor de verdade. A
assinatura e a do `VETOR_DE_FORA`, produzida pelo OpenSSL: o vetor foi assinado
para o dominio de producao, entao as costumes de teste do servidor
(`Hub._rp_id`, `Hub._numero_da_ordem`, `Hub._segundos_agora`) fixam dominio,
numero e relogio da ordem do vetor, e o `ordens.json` gravado pelo instalador
tem `ident`, `origem` e `rp_id` trocados pelos do vetor (escrito aqui, com este
motivo).

    python test_acoes_fio.py
"""
from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import os
import re
import shutil
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("DERVS_AMBIENTE", "local")
os.environ.setdefault("DERVS_COFRE",
                      "chave-de-teste-que-nao-e-segredo-nenhum-0123456789")

import ajudante_servidor  # noqa: E402
import banco         # noqa: E402
import p256          # noqa: E402
import servir        # noqa: E402
import tarefas       # noqa: E402
from test_servir import BaseServidorDeVerdade  # noqa: E402
from test_servidor_fio import campos, funcao, sem_comentarios  # noqa: E402
from test_servidor_tela import rode  # noqa: E402
from test_ajudante_acoes import (  # noqa: E402
    B64_REINICIAR, B64_VOLTAR, CAMPOS, CAMPOS_VOLTAR, HASH_REINICIAR,
    HASH_VOLTAR, NUMERO, ORIGEM, RP, SERVIDOR, VETOR_DE_FORA, AGORA, chave_de)

AQUI = Path(__file__).resolve().parent
JS = (AQUI / "assets" / "painel.js").read_text(encoding="utf-8")
CRED_ID = "Y3JlZC1kby10ZXN0ZQ"           # o id da credencial do teste
ID_FALSO = "b" * 64
T_SERVIDOR = 1791558000                    # o relogio do DERVS no vetor


def b64url(cru):
    return base64.urlsafe_b64encode(cru).rstrip(b"=").decode("ascii")


def docker_falso(argv, prazo):
    """O Docker de mentira: dois sistemas, os dois comandos de leitura."""
    if argv[:1] == ["id"]:
        return False, ""                       # o usuario ainda nao existe
    if tuple(argv[:4]) == ("docker", "ps", "-aq", "--no-trunc"):
        return True, ID_FALSO + "\n"
    if tuple(argv[:3]) == ("docker", "inspect", "--format"):
        return True, "\t".join([
            "/grimoire-web", "running", "healthy", "2026-10-08T12:00:00.5Z",
            "2", "grimoire:vps", "grimoire", ""]) + "\n"
    return True, ""


class _Mundo(BaseServidorDeVerdade):
    """Roda o fio UMA vez por classe e guarda tudo o que viu. Sem testes."""

    TIPO, ALVO, CASO, BASE = "reiniciar", "grimoire-web", "valido", CAMPOS
    CODIGO_DE_FAZER = 0
    DESLIGAR_ANTES_DE_BUSCAR = False
    ESTADO = ("cookies", "csrf", "linha", "baixado", "chamadas", "raiz",
              "preparado", "assinado", "feitos", "dados_depois", "ordem",
              "repetida", "repetida_feitos", "repetida_desfechos",
              "erros_da_linha", "saida", "token", "maquina_id",
              "depois_de_desligar", "reinstalou")

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        servir.ORIGENS_OK = servir.ORIGENS_OK | {ORIGEM}   # restaurado pela base
        for nome, novo in (
                ("_rp_id", lambda self: RP),
                ("_numero_da_ordem", staticmethod(lambda: NUMERO)),
                ("_segundos_agora", staticmethod(lambda: T_SERVIDOR))):
            p = mock.patch.object(servir.Hub, nome, novo)
            p.start()
            cls.addClassCleanup(p.stop)

    def mundo(self):
        cls = type(self)
        if "_rodou" not in cls.__dict__:
            self._montar()
            cls._rodou = {k: getattr(self, k, None) for k in self.ESTADO}
        self.__dict__.update(cls._rodou)
        return self

    # ------------------------------------------------------------ utilidades
    def dono(self, caminho, corpo):
        return self.pedir(caminho, "POST", corpo, cookies=self.cookies,
                          cabecalhos={"X-Token": self.csrf})

    def dados(self):
        r = self.pedir("/api/dados", cookies=self.cookies)
        self.assertEqual(r.status, 200, r.corpo)
        return json.loads(r.corpo)

    def corpo_de_assinar(self, numero):
        v = VETOR_DE_FORA[self.CASO]
        return {"numero": numero, "cred_id": CRED_ID,
                "cliente": b64url(v["cliente"].encode("ascii")),
                "autenticador": b64url(bytes.fromhex(v["autenticador"])),
                "assinatura": b64url(bytes.fromhex(v["assinatura"]))}

    # -------------------------------------------------------------- o fluxo
    def _montar(self):
        self.cookies, self.csrf = self.sessao_e_token()
        k1 = VETOR_DE_FORA["publica_k1"]
        banco.guardar_chave_de_acesso(
            self.uid, CRED_ID, (int(k1["x"], 16), int(k1["y"], 16)),
            apelido="Celular do teste", contador=0)
        banco.gravar("grimoire", "local", {"nome": "grimoire"},
                     usuario_id=self.uid)

        # O arquivo baixado SEM sessao; a linha com pedidos COM ela.
        r = self.pedir("/ajudante/servidor.py", com_origem=False)
        self.assertEqual(r.status, 200, r.corpo[:300])
        self.baixado = r.corpo.encode("ascii")
        r = self.pedir("/api/ajudante/linha", cookies=self.cookies)
        self.assertEqual(r.status, 200, r.corpo)
        self.linha = json.loads(r.corpo)
        self.assertEqual(hashlib.sha256(self.baixado).hexdigest(),
                         self.linha["sha256"])
        com = self.linha["linha_com_ordens"]
        self.assertIsInstance(com, str)
        textos = com.split(" --ordens ", 1)[1].split(",")

        tmp = tempfile.TemporaryDirectory()
        type(self).addClassCleanup(tmp.cleanup)
        base = Path(tmp.name)
        solto = base / "baixado"
        solto.mkdir()
        (solto / "dervs-ajudante.py").write_bytes(self.baixado)
        raiz = base / "raiz"
        for pasta in ("run/systemd/system", "var/log/deploy", "proc"):
            (raiz / pasta).mkdir(parents=True)
        (raiz / "var/log/deploy/historico.log").write_text(
            "2026-10-08 12:00:00 grimoire ana 20261008-120000-abc1234 OK\n",
            encoding="ascii")
        (raiz / "proc/uptime").write_text("123456.78 99.0\n", encoding="ascii")
        (raiz / "proc/loadavg").write_text("0.12 0.30 0.25 1/100 5\n",
                                           encoding="ascii")
        (raiz / "proc/meminfo").write_text(
            "MemTotal:        4000000 kB\nMemAvailable:    1200000 kB\n",
            encoding="ascii")
        self.raiz = str(raiz)

        espec = importlib.util.spec_from_file_location(
            "ajudante_baixado_das_ordens", str(solto / "dervs-ajudante.py"))
        aj = importlib.util.module_from_spec(espec)
        espec.loader.exec_module(aj)

        self.chamadas, self.erros_da_linha, self.saida = [], [], []
        linhas = []

        def abrir(metodo, url, corpo, token, prazo):
            codigo, dados = aj.abrir(metodo, url, corpo, token, prazo)
            self.chamadas.append((url, corpo, codigo, dados))
            if url.endswith("/agente/pedir") and codigo == 200:
                linha = threading.Thread(target=navegador,
                                         args=(dados["codigo"],), daemon=True)
                linhas.append(linha)
                linha.start()
            return codigo, dados

        def navegador(codigo):
            try:
                a = self.pedir("/api/pedido/autorizar", "POST",
                               {"codigo": codigo}, cookies=self.cookies,
                               cabecalhos={"X-Token": self.csrf})
                self.assertEqual(a.status, 200, a.corpo)
            except BaseException as e:           # a linha nao propaga sozinha
                self.erros_da_linha.append(e)

        def que_docker_existe(nome):
            return "/usr/bin/docker" if nome == "docker" else None

        def instalar(com_ordens):
            return aj.instalar(
                alvo=aj.ALVO, raiz=self.raiz, rodar=docker_falso, abrir=abrir,
                dormir=lambda s: time.sleep(0.2), eh_root=lambda: True,
                dono=lambda caminho, usuario: None, nome="vps-fio",
                saida=self.saida.append,
                ordens=textos if com_ordens else None)

        with mock.patch.object(shutil, "which", que_docker_existe), \
                mock.patch.object(aj, "_comando_de_publicar_ok",
                                  lambda raiz: True):
            self.assertEqual(instalar(True), 0, "\n".join(self.saida))
            for linha in linhas:
                linha.join(timeout=10)
            self.assertEqual(self.erros_da_linha, [])
            # O vetor foi assinado para o DOMINIO DE PRODUCAO: o `ordens.json`
            # que o instalador gravou ganha o ident, a origem e o rp_id dele.
            cam = Path(aj._p(self.raiz, aj.ARQUIVO_DAS_ORDENS))
            cfg = json.loads(cam.read_text("ascii"))
            self.assertEqual(cfg["voltaveis"], ["grimoire"])
            cfg.update(ident=SERVIDOR, origem=ORIGEM, rp_id=RP)
            cam.write_text(json.dumps(cfg), encoding="ascii")
            self.assertEqual(aj.medir(alvo=aj.ALVO, raiz=self.raiz,
                                      rodar=docker_falso, abrir=abrir), 0)
            self.maquina_id = self.dados()["servidores_ligados"][0]["maquina_id"]

            r = self.dono("/api/maquinas/ordem/preparar", {
                "maquina_id": self.maquina_id, "tipo": self.TIPO,
                "alvo": self.ALVO})
            self.preparado = (r.status, json.loads(r.corpo))
            self.assertEqual(r.status, 200, r.corpo)
            r = self.dono("/api/maquinas/ordem/assinar",
                          self.corpo_de_assinar(self.preparado[1]["numero"]))
            self.assinado = (r.status, r.corpo)
            self.assertEqual(r.status, 200, r.corpo)

            if self.DESLIGAR_ANTES_DE_BUSCAR:
                # Cola a linha so de olhar por cima: o ajudante desliga os
                # pedidos, e a medicao deixa de trazer o bloco.
                self.assertEqual(instalar(False), 0, "\n".join(self.saida))
                self.depois_de_desligar = Path(
                    aj._p(self.raiz, aj.ARQUIVO_DAS_ORDENS)).exists()
                antes = len(self.chamadas)
                self.assertEqual(aj.ordens(
                    alvo=aj.ALVO, raiz=self.raiz, rodar=docker_falso,
                    abrir=abrir, fazer=self.fazer_falso, agora=AGORA), aj.OK)
                self.reinstalou = len(self.chamadas) - antes
                self.feitos = []
                return

            self.feitos = []
            antes = len(self.chamadas)
            self.assertEqual(aj.ordens(
                alvo=aj.ALVO, raiz=self.raiz, rodar=docker_falso, abrir=abrir,
                fazer=self.fazer_falso, agora=AGORA), aj.OK)
            self.novas = self.chamadas[antes:]
            self.ordem = next(c[3]["ordem"] for c in self.novas
                              if c[0].endswith("/agente/servidor/ordens"))
            self.dados_depois = self.dados()

            # Segunda passada: a MESMA ordem outra vez. Nunca chega a `fazer`.
            reentrega, desfechos, feitos2 = [], [], []

            def abrir_de_novo(metodo, url, corpo, token, prazo):
                if url.endswith("/agente/servidor/ordens"):
                    return 200, {"ordem": self.ordem}
                desfechos.append(corpo)
                return 200, {"ok": True}

            self.assertEqual(aj.ordens(
                alvo=aj.ALVO, raiz=self.raiz, rodar=docker_falso,
                abrir=abrir_de_novo,
                fazer=lambda argv, prazo: feitos2.append(argv) or 0,
                agora=AGORA + 5), aj.OK)
            self.repetida_feitos, self.repetida_desfechos = feitos2, desfechos

    def fazer_falso(self, argv, prazo):
        self.feitos.append((list(argv), prazo))
        return self.CODIGO_DE_FAZER


class _MundoDeReiniciar(_Mundo):
    """O mesmo mundo para as classes que so leem dele (sem testes proprios)."""


# ===================================================================== o fio
class OPedidoAtravessaTudo(_MundoDeReiniciar):
    def test_o_desafio_que_o_servidor_devolve_e_o_do_vetor(self):
        self.mundo()
        status, prep = self.preparado
        self.assertEqual(prep["desafio"], B64_REINICIAR)
        self.assertEqual(prep["numero"], NUMERO)
        self.assertEqual(prep["rp_id"], RP)
        self.assertEqual(prep["chaves"], [CRED_ID])
        self.assertEqual(prep["segundos"], 300)

    def test_a_ordem_entregue_e_a_do_vetor_e_o_ajudante_a_aceitou(self):
        self.mundo()
        o = self.ordem
        self.assertEqual({k: o[k] for k in CAMPOS}, CAMPOS)
        v = VETOR_DE_FORA["valido"]
        self.assertEqual(
            b64url(v["cliente"].encode("ascii")), o["cliente"])

    def test_o_ajudante_fez_o_pedido_exato_e_contou(self):
        self.mundo()
        self.assertEqual(self.feitos, [(["docker", "restart", "grimoire-web"],
                                        self.feitos[0][1])])
        desfecho = next(c for c in self.chamadas
                        if c[0].endswith("/agente/servidor/desfecho"))
        self.assertEqual(desfecho[1], {"numero": NUMERO, "desfecho": "feita",
                                       "codigo": 0, "motivo": None})
        self.assertEqual(desfecho[2:], (200, {"ok": True}))

    def test_o_painel_traz_o_pedido_feito(self):
        self.mundo()
        s = self.dados_depois["servidores_ligados"][0]
        self.assertTrue(s["ordens"]["chaves_ok"])
        self.assertFalse(s["ordens"]["linha_velha"])
        self.assertEqual(s["ordens"]["voltaveis"], ["grimoire"])
        p = s["ordens"]["pedidos"]
        self.assertEqual(1, len(p), p)
        self.assertEqual((p[0]["numero"], p[0]["tipo"], p[0]["alvo"],
                          p[0]["estado"], p[0]["codigo"], p[0]["motivo"]),
                         (NUMERO, "reiniciar", "grimoire-web", "feito",
                          None, None))

    def test_a_repetida_nunca_chega_a_fazer(self):
        self.mundo()
        self.assertEqual(self.repetida_feitos, [])
        self.assertEqual(self.repetida_desfechos, [{
            "numero": NUMERO, "desfecho": "recusada", "codigo": None,
            "motivo": "repetida"}])


class OPedidoDeVoltarQueFalhaViraNaoDeu(_Mundo):
    TIPO, ALVO, CASO, BASE = "voltar", "grimoire", "valido_voltar", CAMPOS_VOLTAR
    CODIGO_DE_FAZER = 1

    def test_o_desafio_do_voltar_e_o_do_vetor(self):
        self.mundo()
        self.assertEqual(self.preparado[1]["desafio"], B64_VOLTAR)

    def test_o_ajudante_pediu_a_volta_exata_e_contou_a_falha(self):
        self.mundo()
        self.assertEqual([f[0] for f in self.feitos],
                         [list(ajudante_servidor.ARGV_DA_VOLTA) + ["grimoire", "--voltar"]])
        desfecho = next(c for c in self.chamadas
                        if c[0].endswith("/agente/servidor/desfecho"))
        self.assertEqual(desfecho[1], {"numero": NUMERO, "desfecho": "falhou",
                                       "codigo": 1, "motivo": None})

    def test_o_painel_diz_nao_deu_com_o_codigo(self):
        self.mundo()
        p = self.dados_depois["servidores_ligados"][0]["ordens"]["pedidos"][0]
        self.assertEqual((p["tipo"], p["alvo"], p["estado"], p["codigo"]),
                         ("voltar", "grimoire", "nao_deu", 1))

    def test_a_repetida_do_voltar_tambem_nao_faz(self):
        self.mundo()
        self.assertEqual(self.repetida_feitos, [])


# ============================================ as duas pontas, a mesma ordem
class AsDuasPontasMontamAMesmaOrdem(unittest.TestCase):
    def setUp(self):
        self.aj = ajudante_servidor

    def casos(self):
        c = dict(CAMPOS)
        return [
            ("tabela reiniciar", c, HASH_REINICIAR),
            ("tabela voltar", dict(c, tipo="voltar", alvo="grimoire"),
             HASH_VOLTAR),
            ("alvo com =", dict(c, alvo="a=b"), None),
            ("alvo com quebra", dict(c, alvo="a\nb"), None),
            ("voltar com maiuscula",
             dict(c, tipo="voltar", alvo="Grimoire"), None),
            ("voltar com _", dict(c, tipo="voltar", alvo="gri_moire"), None),
            ("reiniciar com hifen na frente", dict(c, alvo="-grimoire"), None),
            ("numero com 31", dict(c, numero="4" * 31), None),
            ("numero com 33", dict(c, numero="4" * 33), None),
            ("numero com maiuscula", dict(c, numero="4E" + "1" * 30), None),
            ("servidor com g", dict(c, servidor="g" * 32), None),
            ("criado com zero", dict(c, criado="01791558000"), None),
            ("criado com 11 digitos",
             dict(c, criado=17915580000, vence=17915580300), None),
            ("vence 299", dict(c, vence=c["criado"] + 299), None),
            ("criado bool", dict(c, criado=True, vence=301), None),
            ("tipo publicar", dict(c, tipo="publicar"), None),
            ("campo faltando", {k: v for k, v in c.items() if k != "alvo"},
             None),
            ("campo a mais", dict(c, extra="x"), None),
        ]

    def test_o_texto_e_igual_nas_duas_pontas_e_bate_com_a_tabela(self):
        for nome, campos_, hash_ in self.casos():
            with self.subTest(nome):
                no_aj = self.aj.texto_da_ordem(dict(campos_))
                no_dervs = tarefas.texto_da_ordem(dict(campos_))
                self.assertEqual(no_aj, no_dervs)
                if hash_ is None:
                    self.assertIsNone(no_aj)
                else:
                    self.assertEqual(
                        hashlib.sha256(no_aj.encode("ascii")).hexdigest(),
                        hash_)

    def test_a_impressao_da_chave_e_a_mesma(self):
        k1 = chave_de("publica_k1")
        self.assertEqual(self.aj.impressao(*p256.G), "d875db7def232236")
        for ponto in (p256.G, k1):
            self.assertEqual(self.aj.impressao(*ponto),
                             banco.impressao_da_chave(*ponto))

    def test_os_motivos_da_recusa_sao_os_mesmos(self):
        self.assertEqual(tuple(self.aj.MOTIVOS_DA_RECUSA),
                         tuple(tarefas.MOTIVOS_DA_RECUSA))


class AFraseEAMesma(unittest.TestCase):
    def test_a_frase_do_js_e_a_do_servidor_nos_dois_tipos(self):
        casos = [("reiniciar", "grimoire-web", "vps-ovh"),
                 ("voltar", "grimoire", "vps-ovh"),
                 ("reiniciar", "a.b_c-1", "servidor do Thiago")]
        r = rode(self, "console.log(JSON.stringify(%s.map(c => "
                 "fraseDoPedido(c[0], c[1], c[2]))));" % json.dumps(casos))
        self.assertEqual(r, [servir.Hub._frase_do_pedido(*c) for c in casos])
        self.assertIn("“", r[0])          # as aspas tipograficas de verdade


# ============================== o que a tela le e o que o servidor entrega
class OQueATelaLeOServidorEntrega(_MundoDeReiniciar):
    def contido(self, lidos, reais, onde):
        self.assertTrue(lidos, "nenhum campo lido para " + onde)
        faltam = lidos - reais
        self.assertFalse(faltam, "a tela le %s que %s nao entrega (entrega: %s)"
                         % (sorted(faltam), onde, sorted(reais)))

    def test_o_servidor_ligado_e_o_bloco_dos_pedidos(self):
        s = self.mundo().dados_depois["servidores_ligados"][0]
        self.contido(campos("s", "linhaDeServidorLigado"), set(s),
                     "/api/dados (servidores_ligados)")
        self.contido(campos("o", "blocoDosPedidos"), set(s["ordens"]),
                     "/api/dados (servidores_ligados[].ordens)")
        self.assertIn("voltaveis", campos("o", "blocoDosPedidos"))
        self.contido(campos("p", "blocoDosPedidos", "estadoDoPedido"),
                     set(s["ordens"]["pedidos"][0]),
                     "/api/dados (ordens.pedidos)")
        self.contido(campos("x", "linhaDeSistema"), set(s["sistemas"][0]),
                     "/api/dados (servidores_ligados[].sistemas)")
        self.assertTrue(s["sistemas"][0]["reiniciavel"])

    def test_a_linha_com_pedidos(self):
        d = self.mundo().linha
        self.contido(campos("d", "blocoDaLinhaDoAjudante"), set(d),
                     "/api/ajudante/linha")
        self.assertEqual(d["chaves_na_linha"], ["Celular do teste"])

    def test_a_resposta_de_preparar_e_a_de_um_pedido_recusado(self):
        self.mundo()
        # Uma recusa com `motivo` sem mexer no mundo compartilhado: a conta
        # "sem chave que o servidor conheca" e 409 antes de gravar a ordem.
        with mock.patch.object(banco, "chaves_publicas_da_conta",
                               lambda *a, **k: []):
            recusa = self.dono("/api/maquinas/ordem/preparar", {
                "maquina_id": self.maquina_id, "tipo": self.TIPO,
                "alvo": self.ALVO})
        self.assertEqual((recusa.status, json.loads(recusa.corpo)),
                         (409, {"motivo": "sem_chave"}), recusa.corpo)
        lidos = campos("d", "fazerOPedido")
        self.contido(lidos, set(self.preparado[1]),
                     "/api/maquinas/ordem/preparar")
        self.contido(campos("corpo", "fazerOPedido"),
                     set(json.loads(recusa.corpo)),
                     "o 409 de /api/maquinas/ordem/preparar")

    def test_o_corpo_que_a_tela_manda_ao_assinar_e_o_que_o_servidor_le(self):
        m = re.search(r'escrever\("/api/maquinas/ordem/assinar", \{(.*?)\}\)',
                      sem_comentarios(JS), re.S)
        self.assertTrue(m, "a chamada de assinar sumiu do painel.js")
        enviados = set(re.findall(r"\b(\w+):", m.group(1)))
        self.assertEqual(enviados, set(self.corpo_de_assinar(NUMERO)))

    def test_as_rotas_citadas_na_tela_existem_com_o_metodo_certo(self):
        for rota in ("/api/maquinas/ordem/preparar",
                     "/api/maquinas/ordem/assinar"):
            self.assertIn('"%s"' % rota, JS)
            self.assertIn(rota, servir.ROTAS)
            self.assertEqual(servir.ROTAS[rota].metodo, "POST", rota)
        self.assertIn("navigator.credentials.get", JS)
        for rota in ("/agente/servidor/ordens", "/agente/servidor/desfecho"):
            self.assertEqual(servir.ROTAS[rota].metodo, "POST", rota)


# ============================================== desligado nas duas pontas
class DesligadoNasDuasPontas(_Mundo):
    DESLIGAR_ANTES_DE_BUSCAR = True

    def test_o_ajudante_desligado_nao_chama_a_rede(self):
        self.mundo()
        self.assertFalse(self.depois_de_desligar)
        self.assertEqual(self.reinstalou, 0)

    def test_a_ordem_assinada_ficou_sem_entregar(self):
        self.mundo()
        con = banco.conectar()
        try:
            linhas = con.execute(
                "SELECT entregue_em FROM ordem_de_servidor").fetchall()
        finally:
            con.close()
        self.assertEqual([tuple(l) for l in linhas], [(None,)])

    def test_o_dervs_recusa_preparar_com_so_olha_e_nao_mostra_ordens(self):
        self.mundo()
        r = self.dono("/api/maquinas/ordem/preparar", {
            "maquina_id": self.maquina_id, "tipo": "reiniciar",
            "alvo": "grimoire-web"})
        self.assertEqual((r.status, json.loads(r.corpo)),
                         (409, {"motivo": "so_olha"}))
        s = self.dados()["servidores_ligados"][0]
        self.assertIsNone(s["ordens"])
        self.assertFalse(any(x["reiniciavel"] for x in s["sistemas"]))


if __name__ == "__main__":
    unittest.main()
