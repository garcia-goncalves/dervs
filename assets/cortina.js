(function () {
  "use strict";
  var porta = document.getElementById("porta");
  var campo = document.getElementById("combinacao");
  var slots = Array.prototype.slice.call(document.querySelectorAll(".slot"));
  var enviando = false;

  function pintar() {
    campo.value = campo.value.replace(/\D/g, "").slice(0, 6);
    slots.forEach(function (s, i) {
      if (i < campo.value.length) { s.setAttribute("data-cheia", ""); }
      else { s.removeAttribute("data-cheia"); }
    });
  }

  campo.addEventListener("input", pintar);

  porta.addEventListener("click", function (e) {
    var b = e.target.closest("button");
    if (!b) { return; }
    if (b.hasAttribute("data-d")) { campo.value += b.getAttribute("data-d"); }
    else if (b.hasAttribute("data-apagar")) { campo.value = campo.value.slice(0, -1); }
    else { return; }
    pintar();
    campo.focus();
  });

  // A resposta do servidor e IDENTICA para chave certa e errada, de proposito:
  // o tempo e o corpo nao podem dizer quantos digitos bateram. Quem sabe a
  // diferenca e o proximo carregamento — se a porta abriu, ela aparece. Sem
  // este aviso, recusa vira tela que nao faz nada, e tela que nao faz nada
  // parece defeito. Ja custou uma sessao inteira de quem estava do outro lado.
  try {
    if (sessionStorage.getItem("tentou") && !document.querySelector(".entrar")) {
      document.getElementById("recusa").hidden = false;
    }
    sessionStorage.removeItem("tentou");
  } catch (err) {}

  porta.addEventListener("submit", function (e) {
    e.preventDefault();
    if (enviando) { return; }
    enviando = true;
    try { sessionStorage.setItem("tentou", "1"); } catch (err) {}
    fetch("/entrada", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ combinacao: campo.value })
    }).catch(function () {
    }).then(function () { location.reload(); });
  });

  pintar();
})();
