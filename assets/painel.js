/* ==========================================================================
   O anti-falsificação DESTA sessão, injetado pelo servidor dentro da página.
   Ele não é credencial: é a prova de que o pedido saiu desta tela.
   ========================================================================== */
const TOKEN = document.querySelector('meta[name="dervs-token"]').content;
const $ = s => document.querySelector(s);

let ESTADO = null;        // o último /api/dados que chegou inteiro
let FILTRO = null;        // null = todos; senão um dos quatro estados
let COMPUTADORES = null;  // último /api/maquinas
/* Quando essa lista chegou. Guardado de propósito em vez de carimbar com a
   hora do desenho: a tela "Conectar" mostra a contagem sem ter buscado nada,
   e "agora" ali seria uma data inventada para um dado antigo. */
let COMPUTADORES_LIDO_EM = null;

/* --------------------------------------------------------------- vocabulário
   Os quatro estados, escritos. Quatro sinais independentes: cor, forma, glifo
   e rótulo. Nenhum é indispensável sozinho — a tela continua legível em preto
   e branco, para quem não distingue cores, e para leitor de tela. */
const ESTADOS = {
  saudavel:  { rotulo: "saudável",  muitos: "saudáveis",
               frase: "Tudo o que dá para medir passou." },
  atencao:   { rotulo: "atenção",   muitos: "em atenção",
               frase: "Funciona, mas alguma coisa vai piorar." },
  quebrado:  { rotulo: "quebrado",  muitos: "quebrados",
               frase: "Alguma coisa reprovou agora." },
  sem_dados: { rotulo: "sem dados", muitos: "sem dados",
               frase: "Não consegui medir." }
};
/* A ordem de leitura do painel. O saudável fica por último de propósito: quem
   está bem não precisa de atenção. */
const ORDEM = ["quebrado", "atencao", "sem_dados", "saudavel"];

/* ------------------------------------------------------------------- tempo */
/* Tempo relativo até 24 horas; data absoluta depois disso. Número sempre com
   unidade — "há 41 segundos", nunca "41". */
/* Só `http:` e `https:` viram href. O endereço de um alerta vem do banco, e o
   banco é alimentado pela coleta — hoje as duas fontes são seguras (a API do
   GitHub, e `coletar_github.url_segura`, que já exige http/https). Mas isto é
   uma trava de uma linha contra uma classe inteira: um `javascript:` gravado
   ali um dia executaria na origem do painel, com o TOKEN anti-falsificação ao
   alcance. Confia-se na fonte E se confere no destino. */
function enderecoSeguro(url) {
  try {
    const e = new URL(url, location.origin).protocol;
    return e === "http:" || e === "https:";
  } catch (_) {
    return false;
  }
}

function haQuanto(iso) {
  if (!iso) return "sem carimbo";
  const t = Date.parse(iso);
  if (isNaN(t)) return "sem carimbo";
  const s = (Date.now() - t) / 1000;
  // "há 0 segundos" é uma frase que ninguém diz. Abaixo de cinco, é "agora".
  if (s < 5) return "agora";
  if (s < 90) return "há " + Math.round(s) + " segundos";
  if (s < 5400) return "há " + Math.round(s / 60) + " minutos";
  if (s < 86400) return "há " + Math.round(s / 3600) + " horas";
  return "em " + new Date(t).toLocaleDateString("pt-BR");
}

function hora(iso) {
  const t = Date.parse(iso);
  return isNaN(t) ? "—"
    : new Date(t).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

function recado(texto, ruim) {
  const el = $("#recado");
  el.textContent = texto;
  el.classList.add("ver");
  clearTimeout(recado.t);
  recado.t = setTimeout(() => el.classList.remove("ver"), ruim ? 9000 : 4000);
}

/* --------------------------------------------------------------- o selo ---
   Uma função só monta o selo, na tela inteira. Duas montagens divergem, e a
   que divergir vai ser a que esquece o rótulo escrito — justamente o sinal que
   sobrevive à impressão em preto e branco e ao leitor de tela. */
const MOLDES = $("#moldes-de-selo").content;

function selo(estado, { como = "button", aoClicar = null, texto = "" } = {}) {
  const e = ESTADOS[estado] ? estado : "sem_dados";
  const molde = MOLDES.querySelector('[data-selo="' + e + '"]').cloneNode(true);

  /* O molde nasce `<span>`. O selo é sempre um botão quando abre alguma coisa:
     clicar tem de levar à prova que o gerou — selo que não se abre é palpite
     com cara de dado. Quando não há para onde ir, ele fica `<span>` mesmo, e
     não um botão desabilitado que o teclado percorre à toa. */
  let el = molde;
  if (como !== "span" && aoClicar) {
    el = document.createElement("button");
    el.type = "button";
    el.className = molde.className;
    el.dataset.selo = e;
    el.append(...molde.childNodes);
    el.addEventListener("click", aoClicar);
  }
  if (texto) el.querySelector(".selo__rotulo").textContent = texto;
  return el;
}

/* ------------------------------------------------------------------ rotas */
/* Endereço por âncora, e não por caminho: o servidor tem uma rota de página só
   (`/`), e é bom que continue assim — cada caminho novo é superfície nova a
   defender. O `robots.txt` já bloqueia /painel, /projeto e /maquinas para a
   Fatia 2, quando essas telas ganharem endereço próprio. */
function rota() {
  const cru = (location.hash || "#/painel").slice(2).split("/");
  return { tela: cru[0] || "painel", alvo: decodeURIComponent(cru[1] || "") };
}

function mostrar(tela) {
  for (const s of document.querySelectorAll("main > section")) {
    s.hidden = s.id !== "tela-" + tela;
  }
  for (const a of document.querySelectorAll("nav.mapa a")) {
    if (a.dataset.tela === tela) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  }
}

function navegar() {
  const { tela, alvo } = rota();
  switch (tela) {
    case "projeto":      mostrar("projeto"); pintarProjeto(alvo); break;
    case "alerta":       mostrar("alerta"); pintarAlerta(alvo); break;
    case "conectar":     mostrar("conectar"); pintarConectar(); break;
    case "computadores": mostrar("computadores"); carregarComputadores(); break;
    case "entrada":      mostrar("entrada"); pdCarregar(); break;
    default:             mostrar("painel"); pintarPainel(); break;
  }
  window.scrollTo(0, 0);
}

/* ================================================== 2. Painel ============ */

/* A pior pendência de um projeto, entre as que ainda pintam o selo. É ela que
   escreve o motivo em uma frase. */
const PESO = { alta: 0, media: 1, baixa: 2 };
function piorDe(nome) {
  let pior = null;
  for (const p of (ESTADO.pendencias || [])) {
    if (p.projeto !== nome) continue;
    if (pior === null || (PESO[p.gravidade] ?? 9) < (PESO[pior.gravidade] ?? 9)) pior = p;
  }
  return pior;
}

function carimboDe(p) {
  const c = p.medido_em || {};
  const quais = Object.values(c).filter(Boolean).map(Date.parse).filter(t => !isNaN(t));
  return quais.length ? new Date(Math.max(...quais)).toISOString() : "";
}

/* A frase de resumo, em linguagem humana, escrita a partir do dado. Se ela não
   mudar quando o dado muda, é decoração — e decoração no topo de um painel
   operacional ensina a pessoa a não ler o topo. */
function fraseDeResumo(conta, total) {
  if (!total) return "Você ainda não conectou nenhum projeto.";

  /* Tudo bem é o caso mais curto, e merece a frase mais curta. */
  if (conta.saudavel === total) {
    return total === 1 ? "O seu projeto está bem."
                       : "Os " + total + " projetos estão bem.";
  }

  /* AS CONTAS TÊM DE FECHAR. A primeira versão desta frase dizia
     "5 projetos quebrados, 6 bem" numa lista de 17 — os 4 em atenção sumiam
     do texto e ficavam só na régua. Uma frase de resumo que não soma o total
     é a mesma mentira por omissão que o quarto estado do selo existe para
     matar, só que escrita em português. */
  const partes = [];
  if (conta.quebrado) {
    partes.push(conta.quebrado === 1 ? "1 projeto quebrado"
                                     : conta.quebrado + " projetos quebrados");
  }
  if (conta.atencao) {
    partes.push(conta.atencao === 1 ? "1 pede atenção"
                                    : conta.atencao + " pedem atenção");
  }
  if (conta.saudavel) {
    partes.push(conta.saudavel === 1 ? "1 está bem"
                                     : conta.saudavel + " estão bem");
  }
  let frase = partes.join(", ") + ".";
  if (conta.sem_dados) {
    frase += conta.sem_dados === 1 ? " E 1 não foi medido."
                                   : " E " + conta.sem_dados + " não foram medidos.";
  }
  return frase;
}

function pintarPainel() {
  if (!ESTADO) return;
  const projetos = ESTADO.projetos || [];
  const conta = { saudavel: 0, atencao: 0, quebrado: 0, sem_dados: 0 };
  for (const p of projetos) conta[p.selo] = (conta[p.selo] || 0) + 1;

  $("#resumo").textContent = fraseDeResumo(conta, projetos.length);
  pintarRecomendada();

  /* A régua de contagem: quatro contadores, um por estado, cada um com forma,
     glifo e rótulo. São filtros — tocar em "quebrado" reduz a lista. */
  const regua = $("#regua");
  regua.textContent = "";
  for (const e of ORDEM) {
    const b = selo(e, {
      texto: conta[e] + " "
             + (conta[e] === 1 ? ESTADOS[e].rotulo : ESTADOS[e].muitos),
      aoClicar: () => { FILTRO = FILTRO === e ? null : e; pintarPainel(); }
    });
    b.setAttribute("aria-pressed", String(FILTRO === e));
    b.title = ESTADOS[e].frase;
    regua.append(b);
  }

  /* Ordem: quebrado, atenção, sem dados, saudável. Dentro de cada grupo, o
     medido mais recentemente primeiro. */
  const visiveis = projetos
    .filter(p => !FILTRO || p.selo === FILTRO)
    .sort((a, b) => {
      const d = ORDEM.indexOf(a.selo) - ORDEM.indexOf(b.selo);
      return d || (Date.parse(carimboDe(b)) || 0) - (Date.parse(carimboDe(a)) || 0);
    });

  const lista = $("#lista-projetos");
  lista.classList.remove("esqueleto");
  lista.textContent = "";

  if (!projetos.length) {
    lista.append(vazio(
      "Nenhum projeto conectado ainda. Quando você conectar, cada projeto vira "
      + "uma linha aqui com um selo dizendo se está saudável, se pede atenção "
      + "ou se quebrou.",
      "Conectar um projeto", "#/conectar"));
    return;
  }
  if (!visiveis.length) {
    lista.append(vazio(
      "Nenhum projeto " + ESTADOS[FILTRO].rotulo + " agora.",
      "Ver todos", null, () => { FILTRO = null; pintarPainel(); }));
    return;
  }

  for (const p of visiveis) {
    const li = document.createElement("li");
    const pior = piorDe(p.nome);

    li.append(selo(p.selo, { aoClicar: () => irPara("#/projeto/" + encodeURIComponent(p.nome)) }));

    const dizeres = document.createElement("div");
    dizeres.className = "dizeres";
    const nome = document.createElement("div");
    nome.className = "nome";
    // textContent, nunca innerHTML: o nome vem do relatório de OUTRO
    // computador, e é o campo mais fácil de envenenar em todo este painel.
    nome.textContent = p.nome;
    const motivo = document.createElement("div");
    motivo.className = "motivo";
    motivo.textContent = p.selo === "sem_dados"
      ? "Não consegui medir. " + camadasCaladas(p)
      : (pior ? pior.texto : ESTADOS[p.selo].frase);
    const carimbo = document.createElement("div");
    carimbo.className = "carimbo";
    /* "medido há 14 minutos" num projeto SEM DADOS é a mentira que este selo
       existe para não contar: o carimbo é da última medição que existiu, e não
       de uma medição que valha agora. A palavra muda junto com o estado. */
    carimbo.textContent = (p.selo === "sem_dados" ? "última medição "
                                                  : "medido ")
                        + haQuanto(carimboDe(p));
    dizeres.append(nome, motivo, carimbo);

    const abrir = document.createElement("button");
    abrir.className = "botao botao--secundario abrir";
    abrir.type = "button";
    abrir.textContent = "Ver o que gerou este selo";
    abrir.addEventListener("click",
      () => irPara("#/projeto/" + encodeURIComponent(p.nome)));

    li.append(dizeres, abrir);
    lista.append(li);
  }
}

/* A ação recomendada: a pendência mais grave da lista inteira, e o caminho até
   a tela dela. Uma só — painel com cinco chamadas de igual peso não tem
   nenhuma. Some quando não há nada a fazer, em vez de mostrar caixa vazia. */
function pintarRecomendada() {
  const caixa = $("#recomendada");
  const abertas = (ESTADO.pendencias || [])
    .slice()
    .sort((a, b) => (PESO[a.gravidade] ?? 9) - (PESO[b.gravidade] ?? 9));
  const alvo = abertas[0];
  caixa.hidden = !alvo;
  if (!alvo) return;
  $("#recomendada-texto").textContent = alvo.texto;
  $("#recomendada-carimbo").textContent =
    "visto " + haQuanto(alvo.visto_em)
    + (alvo.dias_min ? " · aberto há pelo menos " + alvo.dias_min + " dia(s)" : "");
  $("#recomendada-abrir").onclick =
    () => irPara("#/alerta/" + encodeURIComponent(alvo.id));
}

/* "Sem dados" sem dizer QUAL camada envelheceu é um veredito sem explicação —
   a mesma mentira, só que educada. */
function camadasCaladas(p) {
  /* Com a contração já pronta: "de o seu computador" é o tipo de erro que
     ninguém comete escrevendo à mão e todo mundo comete concatenando. */
  const nomes = { local: "do seu computador", github: "do GitHub",
                  pesado: "da medição pesada" };
  const calados = Object.entries(p.camadas || {})
    .filter(([, vale]) => !vale).map(([c]) => nomes[c] || c);
  if (!calados.length) return "";
  const ultimo = calados.pop();
  return "Sem notícia "
       + (calados.length ? calados.join(", ") + " nem " + ultimo : ultimo) + ".";
}

function vazio(texto, rotulo, href, aoClicar) {
  const li = document.createElement("li");
  const caixa = document.createElement("div");
  caixa.className = "vazio";
  const p = document.createElement("p");
  p.textContent = texto;
  caixa.append(p);
  if (rotulo) {
    const b = document.createElement("button");
    b.className = "botao";
    b.type = "button";
    b.textContent = rotulo;
    b.addEventListener("click", aoClicar || (() => irPara(href)));
    caixa.append(b);
  }
  li.style.display = "block";
  li.append(caixa);
  return li;
}

function irPara(hash) { location.hash = hash; }

/* ================================================== 3. Projeto =========== */

/* Um critério: rótulo, veredito nos MESMOS quatro estados, o valor com o seu
   carimbo, e a prova crua fechada por padrão. Selo na frente, prova atrás. */
function criterio(rotulo, estado, valor, carimbo, prova) {
  const d = document.createElement("details");
  d.className = "criterio";
  const s = document.createElement("summary");
  s.append(selo(estado, { como: "span" }));
  const r = document.createElement("span");
  r.className = "rotulo";
  r.textContent = rotulo;
  const v = document.createElement("span");
  v.className = "metadado";
  v.textContent = valor;
  const c = document.createElement("span");
  c.className = "carimbo";
  c.textContent = carimbo;
  s.append(r, v, c);
  d.append(s);
  const pre = document.createElement("div");
  pre.className = "prova";
  pre.textContent = prova || "Sem prova crua guardada para este critério.";
  d.append(pre);
  return d;
}

function pintarProjeto(nome) {
  if (!ESTADO) return;
  const p = (ESTADO.projetos || []).find(x => x.nome === nome);
  const colunas = $("#projeto-colunas");
  colunas.textContent = "";

  if (!p) {
    $("#projeto-nome").textContent = nome || "Projeto";
    $("#projeto-selo").textContent = "";
    $("#projeto-porque").textContent =
      "Este projeto não está na última medição. Ele pode ter sido desconectado, "
      + "ou o computador que o reportava não dá notícia.";
    $("#projeto-arquivados").textContent = "";
    return;
  }

  $("#projeto-nome").textContent = p.nome;
  const cabeca = $("#projeto-selo");
  cabeca.textContent = "";
  cabeca.append(selo(p.selo, { como: "span" }));

  const pior = piorDe(p.nome);
  $("#projeto-porque").textContent = p.selo === "sem_dados"
    ? "Não consegui medir. " + camadasCaladas(p)
    : (pior ? pior.texto : ESTADOS[p.selo].frase);

  const vale = p.camadas || {};
  const c = p.medido_em || {};
  const g = p.git || {};
  const gh = p.github || null;

  /* --- No seu computador ------------------------------------------------ */
  const local = coluna("No seu computador", colunas);
  if (!vale.local) {
    local.append(nada("O agente deste computador não reporta há mais de 10 "
                      + "minutos. O que depende dele calou.", c.local));
  } else {
    const marca = "medido " + haQuanto(c.local);
    local.append(criterio("Branch", "saudavel", g.branch || "—", marca,
                          "caminho: " + (p.caminho || "—")));
    local.append(criterio(
      "Trabalho não salvo no histórico",
      g.sujos ? "atencao" : "saudavel",
      g.sujos ? g.sujos + " arquivo(s)" : "nenhum", marca,
      (g.sujos_lista || []).join("\n")));
    local.append(criterio(
      "Commits não enviados ao GitHub",
      g.ahead ? "quebrado" : "saudavel",
      g.ahead ? g.ahead + " commit(s)" : "nenhum", marca,
      g.remoto_slug ? "remoto: " + g.remoto_slug : "sem remoto configurado"));
    const drift = (p.env_drift || {});
    const faltando = (drift.faltando || []).length + (drift.sobrando || []).length;
    local.append(criterio(
      "Chaves do .env", faltando ? "atencao" : "saudavel",
      faltando ? faltando + " diferença(s)" : "conferem", marca,
      "faltando: " + (drift.faltando || []).join(", ")
      + "\nsobrando: " + (drift.sobrando || []).join(", ")));
    const vivos = (p.containers || []).filter(x => x.saudavel && !x.reiniciando);
    local.append(criterio(
      "Contêineres",
      (p.containers_esperados || []).length && !vivos.length ? "quebrado" : "saudavel",
      vivos.length + " no ar", marca,
      (p.containers || []).map(x => x.nome + " — " + x.status).join("\n")));
    local.append(criterio(
      "Portas", "saudavel",
      (p.portas || []).filter(x => x.vivo).length + " respondendo", marca,
      (p.portas || []).map(x => x.porta + (x.vivo ? " — respondendo" : " — calada")).join("\n")));
  }

  /* --- No GitHub -------------------------------------------------------- */
  const nogh = coluna("No GitHub", colunas);
  if (!vale.github || !gh) {
    nogh.append(nada("A medição do GitHub não foi lida, ou está velha demais "
                     + "para afirmar alguma coisa.", c.github));
  } else {
    const marca = "medido " + haQuanto(c.github);
    const ci = gh.ci || {};
    nogh.append(criterio(
      "Verificação automática",
      ci.conclusao === "failure" ? "quebrado"
        : ci.conclusao === "success" ? "saudavel" : "sem_dados",
      ci.conclusao === "failure" ? "vermelha"
        : ci.conclusao === "success" ? "verde" : "não medida",
      marca, "estado: " + (ci.estado_bruto || "—") + "\n" + (ci.url || "")));
    const prs = gh.prs || [];
    nogh.append(criterio(
      "Pedidos de alteração abertos", prs.length ? "atencao" : "saudavel",
      prs.length + " aberto(s)", marca,
      prs.map(x => "#" + (x.numero ?? "?") + " " + (x.titulo || "")).join("\n")));
    nogh.append(criterio(
      "Pendências abertas", "saudavel",
      (gh.issues_total ?? "não sei") + "", marca, gh.issues_url || ""));
    const v = gh.vulns || {};
    nogh.append(criterio(
      "Alertas de segurança", v.total ? "quebrado" : "saudavel",
      v.total ? v.total + " aberto(s)" : "nenhum", marca, v.url || ""));
  }

  /* --- No ar ------------------------------------------------------------ */
  const noar = coluna("No ar", colunas);
  if (!vale.github || !gh) {
    noar.append(nada("Sem a medição do GitHub não dá para comparar o que está "
                     + "publicado com o que está no repositório.", c.github));
  } else {
    const marca = "medido " + haQuanto(c.github);
    const site = gh.site || {};
    const dep = gh.deploy || {};
    noar.append(criterio(
      "Site respondendo",
      site.ok === false ? "quebrado" : site.ok === true ? "saudavel" : "sem_dados",
      site.ok === true ? "responde" : site.ok === false ? "fora do ar" : "não medido",
      marca, (site.url || "") + "\ncódigo: " + (site.codigo ?? "sem resposta")));
    noar.append(criterio(
      "Versão publicada",
      typeof dep.atras === "number" && dep.atras > 0 ? "atencao"
        : typeof dep.atras === "number" ? "saudavel" : "sem_dados",
      typeof dep.atras === "number"
        ? (dep.atras > 0 ? dep.atras + " commit(s) atrás do GitHub" : "em dia")
        : "não medido",
      marca, JSON.stringify(dep, null, 1)));
  }

  pintarAlertasDoProjeto(p.nome);
  pintarArquivados(p.nome);
}

/* O caminho até a sexta tela. Sem esta lista o Alerta existiria e ninguém
   chegaria nele — que é o mesmo que não existir. */
function pintarAlertasDoProjeto(projeto) {
  const ul = $("#projeto-alertas");
  ul.textContent = "";
  const meus = (ESTADO.pendencias || [])
    .filter(p => p.projeto === projeto)
    .sort((a, b) => (PESO[a.gravidade] ?? 9) - (PESO[b.gravidade] ?? 9));

  if (!meus.length) {
    ul.append(vazio("Nada pede você neste projeto agora."));
    return;
  }
  for (const p of meus) {
    const li = document.createElement("li");
    const txt = document.createElement("div");
    txt.className = "dizeres";
    const t = document.createElement("div");
    t.textContent = p.texto;
    const c = document.createElement("div");
    c.className = "carimbo";
    c.textContent = "visto " + haQuanto(p.visto_em);
    txt.append(t, c);
    const b = document.createElement("button");
    b.className = "botao botao--secundario";
    b.type = "button";
    b.textContent = "Abrir";
    b.addEventListener("click", () => irPara("#/alerta/" + encodeURIComponent(p.id)));
    li.append(txt, b);
    ul.append(li);
  }
}

function coluna(titulo, onde) {
  const sec = document.createElement("section");
  sec.className = "coluna";
  const h = document.createElement("h2");
  h.textContent = titulo;
  sec.append(h);
  onde.append(sec);
  return sec;
}

/* Ausência de agente produz ausência de camada, NUNCA camada vazia. Nunca
   escrever "nenhum contêiner rodando" quando a verdade é "não perguntei". */
function nada(porque, carimbo) {
  const d = document.createElement("div");
  d.className = "vazio";
  const p = document.createElement("p");
  p.textContent = "Não consegui medir. " + porque;
  const c = document.createElement("p");
  c.className = "carimbo";
  c.textContent = carimbo ? "última medição " + haQuanto(carimbo)
                          : "nunca foi medido";
  d.append(p, c);
  return d;
}

function pintarArquivados(projeto) {
  const onde = $("#projeto-arquivados");
  onde.textContent = "";
  const meus = (ESTADO.arquivadas || [])
    .filter(a => (a.id || "").split(":").slice(1).join(":") === projeto);

  if (!meus.length) {
    const d = document.createElement("div");
    d.className = "vazio";
    d.textContent = "Nada arquivado. Quando você disser “isto está certo assim” "
                  + "para um alerta, ele fica guardado aqui, com o motivo e a data.";
    onde.append(d);
    return;
  }
  const ul = document.createElement("ul");
  ul.className = "lista";
  for (const a of meus) {
    const li = document.createElement("li");
    const txt = document.createElement("div");
    txt.className = "dizeres";
    const t = document.createElement("div");
    t.textContent = a.motivo;
    const c = document.createElement("div");
    c.className = "carimbo";
    c.textContent = "arquivado " + haQuanto(a.arquivado_em);
    txt.append(t, c);
    const b = document.createElement("button");
    b.className = "botao botao--secundario";
    b.type = "button";
    b.textContent = "Desarquivar";
    b.addEventListener("click", () => desarquivar(a.id));
    li.append(txt, b);
    ul.append(li);
  }
  onde.append(ul);
}

/* ================================================== 6. Alerta ============ */

function pintarAlerta(id) {
  const p = (ESTADO && ESTADO.pendencias || []).find(x => x.id === id);
  const acoes = $("#alerta-acoes");
  acoes.textContent = "";
  if (!p) {
    $("#alerta-titulo").textContent = "Este alerta não está mais na lista";
    $("#alerta-texto").textContent =
      "Ou ele foi resolvido, ou está adiado, ou você o arquivou. A lista do "
      + "painel mostra o que vale agora.";
    $("#alerta-carimbo").textContent = "";
    $("#alerta-detalhe").hidden = true;
    return;
  }
  $("#alerta-titulo").textContent = p.projeto;
  $("#alerta-texto").textContent = p.texto;
  $("#alerta-carimbo").textContent =
    "visto " + haQuanto(p.visto_em)
    + (p.dias_min ? " · aberto há pelo menos " + p.dias_min + " dia(s)" : "");
  const det = $("#alerta-detalhe");
  det.hidden = !p.detalhe;
  det.textContent = p.detalhe || "";

  /* "Resolver" não é um botão genérico. Desde a etapa 7 o servidor não executa
     comando nenhum — e um botão que promete resolver e não resolve é pior que
     botão nenhum. O que aparece aqui é o que o NAVEGADOR sabe fazer sozinho, e
     ele diz exatamente o que vai acontecer. */
  const a = p.acao || {};
  if (a.tipo === "abrir_url" && a.url && enderecoSeguro(a.url)) {
    const b = document.createElement("a");
    b.className = "botao";
    b.href = a.url;
    b.target = "_blank";
    b.rel = "noopener noreferrer";
    b.textContent = a.rotulo || "Abrir";
    acoes.append(b);
  } else if (a.caminho) {
    const b = document.createElement("button");
    b.className = "botao";
    b.type = "button";
    b.textContent = "Copiar o caminho da pasta";
    b.addEventListener("click", async () => {
      try { await navigator.clipboard.writeText(a.caminho); recado("caminho copiado."); }
      catch { recado("não deu para copiar. O caminho é " + a.caminho, true); }
    });
    acoes.append(b);
  }

  const adiar = document.createElement("button");
  adiar.className = "botao botao--secundario";
  adiar.type = "button";
  adiar.textContent = "Adiar 24 horas";
  adiar.addEventListener("click", () => silenciar(p.id, 24));
  acoes.append(adiar);

  const certo = document.createElement("button");
  certo.className = "botao botao--secundario";
  certo.type = "button";
  certo.textContent = "Isto está certo assim";
  certo.addEventListener("click", () => pedirMotivo(p));
  acoes.append(certo);
}

/* ================================================== as escritas ========== */

function escrever(url, corpo) {
  return fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Token": TOKEN },
    body: JSON.stringify(corpo || {})
  });
}

async function silenciar(id, horas) {
  const r = await escrever("/api/silenciar", { id, horas });
  if (!r.ok) { recado("não conseguimos adiar. Tente de novo.", true); return; }
  recado("adiado por 24 horas.");
  await carregar();
  irPara("#/painel");
}

let ALVO_ARQUIVO = null;
function pedirMotivo(p) {
  ALVO_ARQUIVO = p;
  $("#arq-alvo").textContent = p.projeto + " — " + p.texto;
  $("#arq-motivo").value = "";
  $("#dlg-arquivar").showModal();
}

async function arquivar() {
  const motivo = $("#arq-motivo").value.trim();
  if (!motivo) { recado("escreva por que isto está certo assim.", true); return; }
  const r = await escrever("/api/arquivar", { id: ALVO_ARQUIVO.id, motivo });
  $("#dlg-arquivar").close();
  if (!r.ok) {
    /* "Tente de novo" é conselho errado quando o problema é o texto: tentar de
       novo dá o mesmo erro. Só o 400 fala pela boca do servidor — é o único
       que descreve algo que o dono pode corrigir (motivo em branco, motivo
       longo demais). 401, 403 e 500 continuam na frase genérica: o texto
       interno deles ("host nao permitido") não ajudaria ninguém. */
    const dele = r.status === 400
      ? await r.json().then(j => j && j.erro).catch(() => null)
      : null;
    recado(dele || "não conseguimos arquivar. Tente de novo.", true);
    return;
  }
  recado("arquivado. Ele fica em “Arquivados”, com o motivo e a data.");
  await carregar();
  irPara("#/projeto/" + encodeURIComponent(ALVO_ARQUIVO.projeto));
}

async function desarquivar(id) {
  const r = await escrever("/api/desarquivar", { id });
  if (!r.ok) { recado("não conseguimos desarquivar. Tente de novo.", true); return; }
  recado("de volta à lista.");
  await carregar();
  navegar();
}

/* ================================================== 4. Conectar ========== */

function pintarConectar() {
  const onde = $("#conectar-corpo");
  onde.textContent = "";

  const cartao = document.createElement("div");
  cartao.className = "cartao";
  const h = document.createElement("h2");
  const passo = document.createElement("p");

  if (COMPUTADORES && COMPUTADORES.length) {
    h.textContent = "Os projetos vêm sozinhos";
    passo.textContent =
      "Você já tem " + COMPUTADORES.length + " computador(es) conectado(s). O "
      + "agente varre as pastas com Git e reporta o que achou — não há nada "
      + "para escolher aqui: o que ele mede aparece no painel na medição "
      + "seguinte.";
    const b = document.createElement("button");
    b.className = "botao";
    b.type = "button";
    b.textContent = "Ver o painel";
    b.addEventListener("click", () => irPara("#/painel"));
    /* A contagem é um número, e número nesta tela leva carimbo como qualquer
       outro. Achado do teste do item 8: a frase dizia "você já tem 2" sem
       nunca dizer de quando era esse 2 — e ele vem da última visita à tela de
       computadores, que pode ter sido ontem. */
    const c = document.createElement("p");
    c.className = "carimbo";
    /* "contagem lida", e não só "lido": aqui o carimbo flutua num cartão cujo
       número está no meio de um parágrafo, e "lido" sozinho se lê como
       "quando esta tela foi lida". */
    c.textContent = "contagem lida " + haQuanto(COMPUTADORES_LIDO_EM);
    /* O botão vai dentro de `.acoes` — é lá que mora o `min-height: 44px`.
       Solto no cartão ele fica com ~36px de altura, abaixo do alvo de toque
       que este projeto adotou. De quebra o `.acoes` separa o carimbo do
       botão, que sem isso ficava equidistante entre o texto e a ação, sem
       dizer a que grupo pertence. */
    const acoes = document.createElement("div");
    acoes.className = "acoes";
    acoes.append(b);
    cartao.append(h, passo, c, acoes);
  } else {
    h.textContent = "Falta conectar um computador";
    passo.textContent =
      "Esta tela não abre sem isso: quem lista as pastas com Git é o agente, e "
      + "hoje nenhum computador está conectado a esta conta.";
    const b = document.createElement("button");
    b.className = "botao";
    b.type = "button";
    b.textContent = "Conectar um computador";
    b.addEventListener("click", () => irPara("#/computadores"));
    cartao.append(h, passo, b);
  }
  onde.append(cartao);

  /* O limite honesto, escrito na tela em vez de escondido: escolher a pasta
     pela tela é da Fatia 2, e prometer o contrário aqui seria a mesma mentira
     que este produto existe para não contar. */
  const nota = document.createElement("p");
  nota.className = "mole";
  nota.textContent =
    "Escolher pasta por pasta pela tela, conectar a conta do GitHub e conectar "
    + "o servidor ficaram para a fatia 2 — as duas últimas guardam segredo de "
    + "terceiro, e o cofre vem antes da gaveta.";
  onde.append(nota);
}

/* ================================================== 5. Computadores ====== */

async function carregarComputadores() {
  let d;
  try { d = await (await fetch("/api/maquinas")).json(); }
  catch { recado("não conseguimos ler a lista de computadores.", true); return; }
  COMPUTADORES = d.maquinas || [];
  COMPUTADORES_LIDO_EM = new Date().toISOString();

  const lista = $("#lista-computadores");
  lista.textContent = "";
  $("#computadores-carimbo").textContent = "lido " + haQuanto(COMPUTADORES_LIDO_EM);

  if (!COMPUTADORES.length) {
    lista.append(vazio(
      "Nenhum computador conectado. O DERVS precisa de um agente rodando no seu "
      + "computador para enxergar contêineres, Git e as portas. Sem ele, só dá "
      + "para ver o que está no GitHub.",
      "Gerar o número", null, () => $("#btn-gerar-numero").click()));
    return;
  }
  for (const m of COMPUTADORES) {
    const li = document.createElement("li");
    const txt = document.createElement("div");
    txt.className = "dizeres";
    const nome = document.createElement("div");
    nome.className = "nome";
    // textContent, nunca innerHTML: o nome vem do OUTRO computador, e quem
    // pareia escolhe o texto.
    nome.textContent = m.nome || "computador sem nome";
    const meta = document.createElement("div");
    meta.className = "carimbo";
    meta.textContent = (m.visto_em ? "deu notícia " + haQuanto(m.visto_em)
                                   : "nunca deu notícia")
                     + " · " + m.projetos + (m.projetos === 1 ? " projeto" : " projetos");
    txt.append(nome, meta);
    const b = document.createElement("button");
    b.className = "botao botao--secundario";
    b.type = "button";
    b.textContent = "Remover";
    b.addEventListener("click", () => confirmar({
      titulo: "Desconectar “" + (m.nome || "este computador") + "”?",
      texto: "Ele para de reportar na hora, e só volta com um número novo. As "
           + "medições que ele já mandou não são apagadas, e os projetos dele "
           + "continuam no painel — parados no último carimbo.",
      sim: "Desconectar", nao: "Manter conectado"
    }, () => removerComputador(m.id)));
    li.append(txt, b);
    lista.append(li);
  }
}

async function removerComputador(id) {
  const r = await escrever("/api/maquinas/remover", { id });
  if (!r.ok) { recado("não conseguimos remover. Tente de novo.", true); return; }
  recado("removido. Ele não reporta mais.");
  carregarComputadores();
}

async function gerarNumero() {
  const r = await escrever("/api/maquinas/parear");
  if (!r.ok) { recado("não conseguimos gerar o número agora.", true); return; }
  const d = await r.json();
  /* O código só aparece pronto; nunca meio código na tela. */
  $("#numero-pareamento").textContent = d.codigo;
  $("#numero-pareamento").classList.remove("vencido");
  $("#numero-prazo").textContent = "vale por " + d.minutos + " minutos, e para "
                                 + "um computador só";
  $("#comando-pareamento").textContent =
    "python -m agente.enviar --alvo " + location.origin + " --codigo " + d.codigo;
  $("#pareamento").hidden = false;
  /* Quando vence, o número fica riscado — não some. Número antigo na tela é
     número que a pessoa digita e não funciona, sem entender por quê. */
  clearTimeout(gerarNumero.t);
  gerarNumero.t = setTimeout(() => {
    $("#numero-pareamento").classList.add("vencido");
    $("#numero-prazo").textContent = "Este código venceu. Gere outro.";
  }, Math.max(1, d.minutos) * 60000);
}

/* ========================================== Formas de entrar ============= */
/* Portado da etapa 9 sem mudar a criptografia: só o vocabulário e o visual. */

function pdBytes(texto) {
  const limpo = texto.replace(/-/g, "+").replace(/_/g, "/");
  const cru = atob(limpo + "===".slice((limpo.length + 3) % 4));
  const saida = new Uint8Array(cru.length);
  for (let i = 0; i < cru.length; i++) saida[i] = cru.charCodeAt(i);
  return saida;
}

function pdTexto(buffer) {
  const bytes = new Uint8Array(buffer);
  let s = "";
  for (let i = 0; i < bytes.length; i++) s += String.fromCharCode(bytes[i]);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function pdQuando(iso) {
  if (!iso) return "nunca usada";
  const d = new Date(iso);
  return isNaN(d) ? "—" : "usada em " + d.toLocaleDateString("pt-BR");
}

/* Zero e uma chave são situações diferentes, e o aviso tem de dizer a verdade
   nas duas. E ele não afirma que formatar o computador tranca a conta: o
   servidor não tem como saber se o navegador guardou a chave num gerenciador
   que sincroniza ou no chip da máquina. */
function pdCobrar(d) {
  const p = $("#pd-cobra");
  const nenhuma = d.chaves.length === 0;
  p.hidden = !d.cobrar_a_segunda || d.restantes > 0;
  p.textContent = nenhuma
    ? "Você ainda não cadastrou nenhuma chave de acesso. Hoje entra pela porta "
      + "do ambiente local, que não existe no servidor. Cadastre a primeira "
      + "abaixo, ou gere os códigos do papel."
    : "Você tem uma forma de entrar só. Se ela se perder, ninguém abre esta "
      + "conta — e não há recuperação por e-mail aqui, de propósito. Cadastre "
      + "uma segunda (o celular serve) ou gere os códigos do papel abaixo.";
}

async function pdCarregar() {
  let d;
  try { d = await (await fetch("/api/chaves")).json(); }
  catch { recado("não conseguimos ler a lista de chaves.", true); return; }

  pdCobrar(d);
  $("#pd-restantes").textContent = d.restantes;
  const lista = $("#pd-lista");
  lista.textContent = "";
  if (!d.chaves.length) {
    const li = document.createElement("li");
    li.className = "mole";
    li.textContent = "Nenhuma chave cadastrada neste momento.";
    lista.append(li);
    return;
  }
  for (const c of d.chaves) {
    const li = document.createElement("li");
    const txt = document.createElement("div");
    txt.className = "dizeres";
    const nome = document.createElement("div");
    nome.className = "nome";
    // textContent, nunca innerHTML: o apelido foi digitado por uma pessoa e
    // volta do banco.
    nome.textContent = c.apelido || "sem apelido";
    const quando = document.createElement("div");
    quando.className = "carimbo";
    quando.textContent = pdQuando(c.usado_em);
    txt.append(nome, quando);
    const tirar = document.createElement("button");
    tirar.className = "botao botao--secundario";
    tirar.type = "button";
    tirar.textContent = "Remover";
    tirar.addEventListener("click", () => confirmar({
      titulo: "Remover “" + (c.apelido || "esta chave") + "”?",
      texto: "Este aparelho deixa de abrir a sua conta. Se ele for a sua única "
           + "forma de entrar, você fica de fora — não há recuperação por "
           + "e-mail aqui.",
      sim: "Remover a chave", nao: "Manter a chave"
    }, () => pdRemover(c.id)));
    li.append(txt, tirar);
    lista.append(li);
  }
}

async function pdRemover(id) {
  const r = await escrever("/api/chaves/remover", { id });
  if (!r.ok) { recado("não conseguimos remover. Tente de novo.", true); return; }
  const d = await r.json();
  recado(d.restam === 0
    ? "removida. Você ficou sem nenhuma chave — cadastre uma agora."
    : "removida.");
  pdCarregar();
}

async function pdCadastrar() {
  const botao = $("#pd-cadastrar");
  if (!window.PublicKeyCredential) {
    recado("este navegador não tem suporte a chave de acesso.", true);
    return;
  }
  botao.disabled = true;
  recado("confirme no aparelho…");
  try {
    const r = await escrever("/api/chaves/desafio");
    if (!r.ok) throw new Error("desafio");
    const d = await r.json();
    const cru = {
      challenge: d.desafio,
      rp: { id: d.rp_id, name: "DERVS" },
      user: { id: d.usuario.id, name: d.usuario.nome,
              displayName: d.usuario.mostrar },
      // -7 é ES256, o único que o servidor sabe conferir. Anunciar mais seria
      // aceitar uma chave que depois não entra.
      pubKeyCredParams: [{ type: "public-key", alg: -7 }],
      excludeCredentials: d.ja_tenho.map(id => ({ type: "public-key", id })),
      authenticatorSelection: {
        residentKey: "required",       // descobrível: entra sem digitar usuário
        userVerification: "required"   // PIN ou digital: é o que faz dois fatores
      },
      timeout: 300000,
      attestation: "none"              // não pedimos a marca do fabricante
    };
    const opcoes = PublicKeyCredential.parseCreationOptionsFromJSON
      ? PublicKeyCredential.parseCreationOptionsFromJSON(cru)
      : Object.assign({}, cru, {
          challenge: pdBytes(d.desafio),
          user: Object.assign({}, cru.user, { id: pdBytes(d.usuario.id) }),
          excludeCredentials: d.ja_tenho.map(
            id => ({ type: "public-key", id: pdBytes(id) }))
        });

    const credencial = await navigator.credentials.create({ publicKey: opcoes });
    if (!credencial) throw new Error("cancelado");
    const g = await escrever("/api/chaves/cadastrar", {
      cliente: pdTexto(credencial.response.clientDataJSON),
      atestado: pdTexto(credencial.response.attestationObject),
      apelido: $("#pd-apelido").value
    });
    if (!g.ok) {
      const erro = await g.json().catch(() => ({}));
      throw new Error(erro.erro || "recusado");
    }
    $("#pd-apelido").value = "";
    recado("cadastrado. Este aparelho já abre a conta.");
    pdCarregar();
  } catch (err) {
    if (err && err.name === "InvalidStateError") {
      recado("este aparelho já está cadastrado.", true);
    } else if (err && (err.name === "NotAllowedError" || err.name === "AbortError")) {
      recado("cancelado.");
    } else {
      recado(err && err.message ? err.message : "não deu.", true);
    }
  } finally {
    botao.disabled = false;
  }
}

function pdGerar() {
  confirmar({
    titulo: "Gerar dez códigos novos?",
    texto: "Os dez anteriores são apagados na hora, e o papel que você tem "
         + "guardado deixa de valer. Os novos aparecem uma vez só.",
    sim: "Gerar os dez novos", nao: "Manter os que tenho"
  },
    async () => {
      const r = await escrever("/api/codigos/gerar");
      if (!r.ok) { recado("não conseguimos gerar.", true); return; }
      const d = await r.json();
      const ol = $("#pd-codigos");
      ol.textContent = "";
      for (const c of d.codigos) {
        const li = document.createElement("li");
        li.textContent = c;
        ol.append(li);
      }
      ol.hidden = false;
      $("#pd-queima").hidden = false;
      recado("anote agora — eles não aparecem de novo.");
      pdCarregar();
    });
}

/* ================================================== confirmação ========== */
/* `confirm()` do navegador trava a página inteira e não obedece aos tokens.
   Este diálogo nomeia o que morre, como manda o desenho. */
let AO_CONFIRMAR = null;
function confirmar({ titulo, texto, sim, nao }, aoConfirmar) {
  $("#conf-titulo").textContent = titulo;
  $("#conf-texto").textContent = texto;
  $("#conf-sim").textContent = sim;
  $("#conf-nao").textContent = nao;
  AO_CONFIRMAR = aoConfirmar;
  $("#dlg-confirmar").showModal();
}

/* ================================================== o tema =============== */
/* Três estados: claro, escuro e "seguir o sistema" (o padrão). O botão percorre
   os três nesta ordem e diz em qual está. A escolha vive no navegador. */
const TEMAS = ["sistema", "light", "dark"];
const NOME_DO_TEMA = { sistema: "Tema: segue o sistema", light: "Tema: claro",
                       dark: "Tema: escuro" };

function aplicarTema(t) {
  if (t === "sistema") document.documentElement.removeAttribute("data-theme");
  else document.documentElement.setAttribute("data-theme", t);
  $("#btn-tema").textContent = NOME_DO_TEMA[t];
  try { localStorage.setItem("dervs-tema", t); } catch {}
}

function temaGuardado() {
  try { return localStorage.getItem("dervs-tema") || "sistema"; }
  catch { return "sistema"; }
}

/* ================================================== o carregamento ======= */

async function carregar() {
  try {
    const r = await fetch("/api/dados");
    if (!r.ok) throw new Error(r.status);
    ESTADO = await r.json();
    $("#aviso-painel").hidden = true;
    document.querySelectorAll("main > section").forEach(
      s => s.classList.remove("envelhecido"));
    return true;
  } catch {
    /* A lista anterior CONTINUA na tela, acinzentada, com a faixa em cima.
       Esvaziar a tela por causa de uma falha de rede é indistinguível de
       "você não tem projetos" — e é a mentira mais fácil de contar aqui. */
    const faixa = $("#aviso-painel");
    faixa.hidden = false;
    faixa.textContent = ESTADO
      ? "Não conseguimos atualizar. Mostrando a medição de "
        + hora(ESTADO.agora) + "."
      : "Não conseguimos falar com o servidor. Recarregue a página.";
    if (ESTADO) $("#tela-painel").classList.add("envelhecido");
    return false;
  }
}

async function inicio() {
  aplicarTema(temaGuardado());
  await carregar();
  navegar();
  /* A tela nunca espera coleta: relê de minuto em minuto e troca o que mudou. */
  setInterval(async () => { if (await carregar()) navegar(); }, 60000);
}

/* ---------------------------------------------------------------- ligações */
window.addEventListener("hashchange", navegar);

$("#btn-tema").addEventListener("click", () => {
  const i = TEMAS.indexOf(temaGuardado());
  aplicarTema(TEMAS[(i + 1) % TEMAS.length]);
});

$("#btn-sair").addEventListener("click", async () => {
  try { await fetch("/sair", { method: "POST" }); } catch {}
  location.reload();
});

$("#btn-gerar-numero").addEventListener("click", gerarNumero);

$("#btn-copiar-comando").addEventListener("click", async () => {
  const texto = $("#comando-pareamento").textContent;
  try { await navigator.clipboard.writeText(texto); recado("comando copiado."); }
  catch { recado("não deu para copiar. Selecione o texto e copie à mão.", true); }
});

$("#arq-confirmar").addEventListener("click", arquivar);
$("#arq-cancelar").addEventListener("click", () => $("#dlg-arquivar").close());

$("#conf-sim").addEventListener("click", () => {
  $("#dlg-confirmar").close();
  const f = AO_CONFIRMAR;
  AO_CONFIRMAR = null;
  if (f) f();
});
$("#conf-nao").addEventListener("click", () => $("#dlg-confirmar").close());

$("#pd-cadastrar").addEventListener("click", pdCadastrar);
$("#pd-gerar").addEventListener("click", pdGerar);

inicio();
