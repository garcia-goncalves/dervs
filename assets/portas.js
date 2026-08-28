(function () {
  "use strict";
  var portas = document.getElementById("portas");
  if (!portas) { return; }
  var aviso = document.getElementById("aviso-porta");
  var formCodigo = document.getElementById("form-codigo");
  var ocupado = false;

  function dizer(texto) { aviso.textContent = texto || ""; }

  function paraBytes(texto) {
    var limpo = texto.replace(/-/g, "+").replace(/_/g, "/");
    var cru = atob(limpo + "===".slice((limpo.length + 3) % 4));
    var saida = new Uint8Array(cru.length);
    for (var i = 0; i < cru.length; i++) { saida[i] = cru.charCodeAt(i); }
    return saida;
  }

  function paraTexto(buffer) {
    var bytes = new Uint8Array(buffer), s = "";
    for (var i = 0; i < bytes.length; i++) { s += String.fromCharCode(bytes[i]); }
    return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  }

  function pedir(url, corpo) {
    return fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(corpo || {})
    });
  }

  // ---------------------------------------------------------- chave de acesso
  //
  // `allowCredentials` fica de fora de proposito: a credencial e DESCOBRIVEL, e
  // o proprio aparelho sabe qual oferecer. Mandar a lista antes de a pessoa
  // provar quem e entregaria quantas chaves a conta tem, e os ids delas, a quem
  // so digitou a cortina.
  //
  // `userVerification: "required"` tambem e escolha, e nao descuido: aqui a
  // chave e o UNICO fator, entao e o PIN (ou a digital) que a transforma em
  // dois — algo que voce tem, mais algo que voce sabe. O servidor cobra o mesmo
  // em `passkey.conferir_entrada`, e a tela nao manda esse parametro para ele:
  // valor vindo do navegador nao decide regra de servidor.

  function temChave() {
    return !!(window.PublicKeyCredential && navigator.credentials &&
              navigator.credentials.get);
  }

  function opcoesDe(dados) {
    var cru = {
      challenge: dados.desafio,
      rpId: dados.rp_id,
      allowCredentials: [],
      userVerification: "required",
      timeout: (dados.segundos || 300) * 1000
    };
    // O caminho moderno converte o JSON sozinho. Onde ele nao existe, a
    // conversao a mao faz o mesmo — sao dois campos.
    if (window.PublicKeyCredential.parseRequestOptionsFromJSON) {
      return window.PublicKeyCredential.parseRequestOptionsFromJSON(cru);
    }
    cru.challenge = paraBytes(dados.desafio);
    return cru;
  }

  function entrarComChave() {
    if (ocupado) { return; }
    ocupado = true;
    dizer("procurando a chave neste aparelho…");
    pedir("/entrar/chave/desafio").then(function (r) {
      if (!r.ok) { throw new Error("desafio"); }
      return r.json();
    }).then(function (dados) {
      return navigator.credentials.get({ publicKey: opcoesDe(dados) });
    }).then(function (credencial) {
      if (!credencial) { throw new Error("cancelado"); }
      var r = credencial.response;
      return pedir("/entrar/chave", {
        cred_id: credencial.id,
        cliente: paraTexto(r.clientDataJSON),
        autenticador: paraTexto(r.authenticatorData),
        assinatura: paraTexto(r.signature)
      });
    }).then(function (r) {
      if (r.ok) { location.reload(); return; }
      // O servidor responde IGUAL para todo fracasso, de proposito — chave
      // desconhecida, assinatura errada e desafio vencido sao o mesmo 401.
      // Entao a tela tambem nao inventa diagnostico: diz o que fazer.
      throw new Error(r.status === 429 ? "muitas" : "recusada");
    }).catch(function (err) {
      if (err && (err.name === "NotAllowedError" || err.name === "AbortError")) {
        dizer("cancelado. A porta continua aqui quando você quiser.");
      } else if (err && err.message === "muitas") {
        dizer("tentativas demais. Espere 15 minutos ou use outra porta.");
      } else if (err && err.name === "SecurityError") {
        dizer("este endereço não confere com o da chave cadastrada.");
      } else {
        dizer("não deu. Tente outra porta, ou o código do papel.");
      }
    }).then(function () { ocupado = false; });
  }

  // ------------------------------------------------------- codigo do papel

  function mostrarCodigo() {
    formCodigo.hidden = false;
    dizer("");
    document.getElementById("codigo").focus();
  }

  formCodigo.addEventListener("submit", function (e) {
    e.preventDefault();
    if (ocupado) { return; }
    ocupado = true;
    var campo = document.getElementById("codigo");
    dizer("conferindo…");
    pedir("/entrar/codigo", { codigo: campo.value }).then(function (r) {
      if (r.ok) { location.reload(); return null; }
      return r.json().catch(function () { return {}; }).then(function () {
        dizer(r.status === 429
          ? "tentativas demais. Espere 15 minutos."
          : "esse código não abre. Cada um serve uma vez só.");
        campo.select();
      });
    }).catch(function () {
      dizer("o servidor não respondeu. Tente de novo.");
    }).then(function () { ocupado = false; });
  });

  // ------------------------------------------------------------- o menu

  portas.addEventListener("click", function (e) {
    var b = e.target.closest("[data-porta]");
    if (!b) { return; }
    if (b.getAttribute("data-porta") === "chave") { entrarComChave(); }
    else if (b.getAttribute("data-porta") === "codigo") { mostrarCodigo(); }
  });

  // Aparelho sem suporte nao pode ganhar um botao que nunca funciona. Em vez de
  // sumir com ele calado — o que deixa a pessoa procurando o que nao existe —,
  // o botao fica visivel, desligado, e diz o porque.
  if (!temChave()) {
    var botao = portas.querySelector('[data-porta="chave"]');
    if (botao) {
      botao.disabled = true;
      botao.title = "este navegador não tem suporte a chave de acesso";
      botao.textContent = "Chave de acesso — sem suporte neste navegador";
    }
  }
})();
