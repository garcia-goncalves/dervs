# -*- coding: utf-8 -*-
"""Repintar a MESMA tela não pode jogar a pessoa para o topo.

MOTIVO: `navegar()` serve a dois papéis -- trocar de tela (o `hashchange`) e
repintar a tela atual quando chega dado novo (o relógio de um minuto, e o
fluxo `/api/eventos` a cada medição de servidor, de 30 em 30 s). Ela terminava
SEMPRE em `window.scrollTo(0, 0)`: com um servidor ligado, quem lia o fim da
tela Conectar era puxado ao topo a cada meio minuto (achado do dono no
ensaio da F-2, 16/10/2026).

A regra: sobe ao topo só quando a TELA mudou (nome + alvo). O parâmetro
`?autorizar=` não conta -- `fecharAutorizar` o tira por `replaceState`, e a
repintura seguinte é a mesma tela.

A função `navegar` é EXECUTADA em node, com o resto do painel trocado por
dublês (o que `navegar` chama não importa aqui, só o que ela faz com a
rolagem). Sem node, o caso é pulado.

    python test_rolagem_tela.py
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

AQUI = Path(__file__).parent
JS = (AQUI / "assets" / "painel.js").read_text(encoding="utf-8")


def _trecho(padrao: str) -> str:
    m = re.search(padrao, JS, re.S | re.M)
    assert m, "nao achei no painel.js: %s" % padrao
    return m.group(0)


PROGRAMA = r"""
const contagem = { topo: 0 };
const location = { hash: "" };
const loja = {
  contagem, JSON, console,
  location,
  history: { replaceState: (_a, _b, h) => { location.hash = h; } },
  window: { scrollTo: () => { contagem.topo += 1; } },
  ESPERA: { t: 0 },
};
const nada = () => undefined;
const escopo = new Proxy(loja, {
  has: () => true,
  get: (alvo, k) => {
    if (k === Symbol.unscopables) return undefined;
    if (k in alvo) return alvo[k];
    if (k in globalThis) return globalThis[k];
    return nada;
  },
  set: (alvo, k, v) => { alvo[k] = v; return true; },
});
with (escopo) {
  eval(%s);
  const passos = [];
  const ir = (h) => { location.hash = h; navegar(); passos.push(contagem.topo); };
  const repintar = () => { navegar(); passos.push(contagem.topo); };
  ir("#/conectar");                 // 1: entrou numa tela -> topo
  repintar();                       // 1: mesma tela -> fica
  repintar();                       // 1
  ir("#/painel");                   // 2: outra tela -> topo
  ir("#/conectar?autorizar=K7M4-2QXP");  // 3: outra tela -> topo
  history.replaceState(null, "", "#/conectar");
  repintar();                       // 3: so o parametro saiu -> fica
  ir("#/projeto/a");                // 4
  ir("#/projeto/b");                // 5: outro alvo e outra tela
  repintar();                       // 5
  console.log(JSON.stringify(passos));
}
"""


class RepintarNaoSobeAoTopo(unittest.TestCase):
    def test_so_trocar_de_tela_sobe_ao_topo(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("sem node")
        partes = [
            _trecho(r"^const ROTAS_ANTIGAS = \{.*?\n\};\n"),
            _trecho(r"^function rota\(\) \{.*?\n\}\n"),
            _trecho(r"^function navegar\(\) \{.*?\n\}\n"),
        ]
        guarda = re.search(r"^let TELA_PINTADA\b[^\n]*\n", JS, re.M)
        if guarda:
            partes.insert(0, guarda.group(0).replace("let ", "var ", 1))
        prog = PROGRAMA % json.dumps("".join(partes))
        r = subprocess.run([node, "-"], input=prog, capture_output=True,
                           text=True, timeout=30, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout), [1, 1, 1, 2, 3, 3, 4, 5, 5])

    def test_a_guarda_existe_no_codigo(self):
        """Sem node o caso acima pula; este cobra pelo texto que a subida ao
        topo depende da troca de tela, e não é incondicional."""
        corpo = _trecho(r"^function navegar\(\) \{.*?\n\}\n")
        self.assertNotRegex(corpo, r"(?m)^  window\.scrollTo\(0, 0\);")
        self.assertIn("TELA_PINTADA", corpo)


if __name__ == "__main__":
    unittest.main()
