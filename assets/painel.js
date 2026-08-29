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
    case "trabalho":     mostrar("trabalho"); pintarTrabalho(alvo); break;
    case "consumo":      mostrar("consumo"); pintarConsumo(); break;
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

async function autorizarComputador(id, ligado) {
  const r = await escrever("/api/maquinas/autorizar", { id, ligado });
  if (!r.ok) { recado("não deu para mudar esse computador.", true); return; }
  recado(ligado
    ? "pronto. Esse computador pode consertar sozinho o que estiver verde."
    : "pronto. Esse computador volta a só medir.");
  await carregarComputadores();
}

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

    /* A AUTORIZACAO PARA TRABALHAR, e ela e separada de estar conectado.
       Parear um computador nunca deu a ele o direito de rodar codigo; a coluna
       do banco nasce desligada, e este e o segundo sim, explicito. */
    const trabalha = document.createElement("div");
    trabalha.className = "carimbo";
    trabalha.textContent = m.executa
      ? "Pode consertar sozinho neste computador."
      : "Só mede. Não roda nada neste computador.";
    txt.append(trabalha);

    const aut = document.createElement("button");
    aut.className = "botao botao--secundario";
    aut.type = "button";
    aut.textContent = m.executa ? "Deixar só medindo" : "Deixar consertar aqui";
    aut.addEventListener("click", () => {
      if (m.executa) { autorizarComputador(m.id, false); return; }
      confirmar({
        titulo: "Deixar o DERVS consertar em “" + (m.nome || "este computador") + "”?",
        texto: "Ele vai abrir uma cópia isolada do projeto, trabalhar nela e "
             + "devolver um ramo com as mudanças. Nada é enviado ao GitHub, e "
             + "nada é publicado. Tarefas vermelhas continuam esperando o seu "
             + "clique; só as verdes andam sozinhas.",
        sim: "Pode consertar", nao: "Deixar só medindo"
      }, () => autorizarComputador(m.id, true));
    });

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
    li.append(txt, aut, b);
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
    ? "Você ainda não cadastrou nenhuma chave de acesso: esta conta depende "
      + "só da porta pela qual você acabou de entrar. Cadastre a primeira "
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
/* ================================================== 6. Trabalho ==========
   O semáforo, o ao vivo, o freio e o diff em português.

   Três decisões que não são detalhe:

   1. NUNCA AFIRMAR QUE PAROU antes de o computador confirmar. O pedido viaja
      no próximo aviso dele (até cinco segundos), e `parar()` devolve falso
      quando não confirmou a morte do programa. Escrever "parado" antes disso
      é exatamente o número errado com cara de certo.

   2. O FLUXO AO VIVO CAI DE PÉ. Se a conexão do ao vivo morrer, o relógio de
      um minuto volta sozinho. A tela nunca fica muda.

   3. COR NUNCA SOZINHA. A cor da regra aparece com os quatro sinais que o
      desenho exige do selo — cor, forma, glifo e rótulo escrito. Cor sozinha
      não é informação para quem não distingue cores.
   ========================================================================= */

let TAREFAS = null;         // último /api/tarefas
let TAREFA_ABERTA = null;   // o id da tarefa aberta, ou null
let FLUXO = null;           // o EventSource, quando ligado
let PARADA_PEDIDA = new Set();

const CORES = {
  verde:    { rotulo: "anda sozinho", glifo: "▶", frase:
              "Esta regra anda sozinha e avisa depois." },
  vermelho: { rotulo: "espera o clique", glifo: "■", frase:
              "Esta regra para e espera você aprovar." }
};

const ANDAMENTO = {
  esperando:            "na fila",
  aguardando_aprovacao: "esperando o seu clique",
  rodando:              "trabalhando agora",
  ok:                   "pronto",
  falha:                "não deu certo"
};

/* A tarefa viva, se houver. É o que decide a barra do freio. */
function tarefaViva() {
  for (const t of (TAREFAS?.tarefas || [])) {
    if (t.estado === "rodando") return t;
  }
  return null;
}

function pintarFreio() {
  const viva = tarefaViva();
  const barra = $("#freio");
  if (!viva) { barra.hidden = true; return; }
  barra.hidden = false;
  const parando = PARADA_PEDIDA.has(viva.id) || viva.parada_pedida_em;
  $("#freio-texto").textContent = parando
    ? "Pedido de parada enviado. Esperando o computador confirmar — "
      + "isso leva alguns segundos."
    : (viva.frase || "Trabalhando em " + viva.projeto + ".");
  $("#freio-ver").href = "#/trabalho/" + encodeURIComponent(viva.id);
  $("#freio-parar").disabled = !!parando;
}

async function carregarTarefas() {
  try {
    const r = await fetch("/api/tarefas");
    if (!r.ok) throw new Error(String(r.status));
    TAREFAS = await r.json();
    $("#aviso-trabalho").hidden = true;
    return true;
  } catch {
    /* A lista anterior CONTINUA na tela. Esvaziar por causa de uma falha de
       rede é indistinguível de "não há tarefa nenhuma". */
    const faixa = $("#aviso-trabalho");
    faixa.hidden = false;
    faixa.textContent = TAREFAS
      ? "Não conseguimos atualizar. Mostrando o que veio às "
        + hora(TAREFAS.medido_em) + "."
      : "Não conseguimos falar com o servidor. Recarregue a página.";
    return false;
  }
}

async function pintarTrabalho(alvo) {
  await carregarTarefas();
  pintarFreio();
  if (alvo) { abrirTarefa(alvo); return; }
  TAREFA_ABERTA = null;
  fecharFluxo();
  $("#tarefa-detalhe").hidden = true;
  $("#tarefa-lista-caixa").hidden = false;

  const lista = $("#lista-tarefas");
  lista.textContent = "";
  const tarefas = TAREFAS?.tarefas || [];
  if (!tarefas.length) {
    lista.append(vazio(
      "Nada por aqui ainda. Quando o DERVS encontrar algo que sabe consertar, "
      + "a tarefa aparece aqui — vermelha, esperando o seu clique.",
      "Ver o painel", "#/painel"));
  }
  for (const t of tarefas) lista.append(linhaDeTarefa(t));
  $("#tarefas-carimbo").textContent = TAREFAS
    ? "Lido às " + hora(TAREFAS.medido_em) + "."
    : "Ainda não consegui ler.";

  pintarCores();
}

function linhaDeTarefa(t) {
  const li = document.createElement("li");
  li.className = "linha";

  const abrir = document.createElement("button");
  abrir.type = "button";
  abrir.className = "linha__nome";
  abrir.textContent = t.projeto + " — " + t.regra;
  abrir.addEventListener("click",
    () => irPara("#/trabalho/" + encodeURIComponent(t.id)));
  li.append(abrir);

  const estado = document.createElement("span");
  estado.className = "linha__motivo";
  estado.textContent = ANDAMENTO[t.estado] || t.estado;
  li.append(estado);

  li.append(marcaDeCor(t.cor));

  if (t.estado === "aguardando_aprovacao" || (t.cor === "vermelho"
      && t.estado === "esperando" && !t.aprovado_em)) {
    const ok = document.createElement("button");
    ok.type = "button";
    ok.className = "botao";
    ok.textContent = "Pode fazer";
    ok.addEventListener("click", () => aprovarTarefa(t.id));
    li.append(ok);
  }

  const quando = document.createElement("span");
  quando.className = "carimbo";
  quando.textContent = haQuanto(t.terminado_em || t.iniciado_em || t.criado_em);
  li.append(quando);
  return li;
}

/* Cor, forma, glifo e rótulo — os quatro juntos, sempre. */
function marcaDeCor(cor) {
  const c = CORES[cor] ? cor : "vermelho";
  const el = document.createElement("span");
  el.className = "marca";
  el.dataset.cor = c;
  const glifo = document.createElement("span");
  glifo.className = "marca__glifo";
  glifo.setAttribute("aria-hidden", "true");
  glifo.textContent = CORES[c].glifo;
  const rotulo = document.createElement("span");
  rotulo.className = "marca__rotulo";
  rotulo.textContent = CORES[c].rotulo;
  el.append(glifo, rotulo);
  return el;
}

function pintarCores() {
  const lista = $("#lista-cores");
  lista.textContent = "";
  const cores = TAREFAS?.cores || {};
  const nunca = new Set(TAREFAS?.nunca_verde || []);
  const regras = new Set([...Object.keys(cores), ...nunca,
                          ...(TAREFAS?.tarefas || []).map(t => t.regra)]);
  if (!regras.size) {
    lista.append(vazio("Nenhuma regra conhecida ainda.", "", ""));
    return;
  }
  for (const regra of [...regras].sort()) {
    const li = document.createElement("li");
    li.className = "linha";
    const nome = document.createElement("span");
    nome.className = "linha__nome";
    nome.textContent = regra;
    li.append(nome, marcaDeCor(cores[regra] === "verde" ? "verde" : "vermelho"));

    if (nunca.has(regra)) {
      const trava = document.createElement("span");
      trava.className = "linha__motivo";
      trava.textContent = "nunca anda sozinha, e isso não se muda";
      li.append(trava);
    } else {
      const verde = cores[regra] === "verde";
      const b = document.createElement("button");
      b.type = "button";
      b.className = "botao botao--secundario";
      b.textContent = verde ? "Fazer esperar meu clique" : "Deixar andar sozinho";
      b.addEventListener("click",
        () => repintar(regra, verde ? "vermelho" : "verde"));
      li.append(b);
    }
    lista.append(li);
  }
}

async function repintar(regra, cor) {
  const r = await escrever("/api/tarefas/cor", { regra, cor });
  if (!r.ok) {
    let motivo = "não deu para mudar.";
    try { motivo = (await r.json()).erro || motivo; } catch {}
    recado(motivo, true);
    return;
  }
  recado(cor === "verde"
    ? "a regra " + regra + " passa a andar sozinha."
    : "a regra " + regra + " passa a esperar o seu clique.");
  await carregarTarefas();
  pintarCores();
}

async function aprovarTarefa(id) {
  const r = await escrever("/api/tarefas/aprovar", { id });
  if (!r.ok) { recado("essa tarefa já não espera aprovação.", true); return; }
  recado("aprovado. O computador pega a tarefa no próximo aviso dele.");
  await carregarTarefas();
  navegar();
}

async function pararTarefa(id) {
  /* NUNCA dizemos "parou" aqui. Dizemos que o pedido saiu. */
  const r = await escrever("/api/tarefas/parar", { id });
  if (!r.ok) { recado("essa tarefa já não está em andamento.", true); return; }
  PARADA_PEDIDA.add(id);
  pintarFreio();
  recado("pedido de parada enviado. O computador confirma em alguns segundos.");
}

/* ------------------------------------------------------- uma tarefa só */

async function abrirTarefa(id) {
  TAREFA_ABERTA = id;
  $("#tarefa-lista-caixa").hidden = true;
  $("#tarefa-detalhe").hidden = false;
  $("#tarefa-linhas").textContent = "";
  await recarregarTarefa();
  ligarFluxo(id);
}

async function recarregarTarefa() {
  if (!TAREFA_ABERTA) return;
  let t = null;
  try {
    const r = await fetch("/api/tarefas?id=" + encodeURIComponent(TAREFA_ABERTA));
    if (r.ok) t = (await r.json()).tarefa;
  } catch {}
  if (!t) {
    $("#tarefa-titulo").textContent = "Não encontrei essa tarefa.";
    $("#tarefa-frase").textContent =
      "Ela pode ter sido apagada, ou o endereço está errado.";
    return;
  }
  $("#tarefa-onde").textContent = t.projeto;
  $("#tarefa-titulo").textContent = t.regra;
  $("#tarefa-selo").textContent = "";
  $("#tarefa-selo").append(marcaDeCor(t.cor));
  $("#tarefa-frase").textContent =
    (ANDAMENTO[t.estado] || t.estado)
    + (t.frase ? " — " + t.frase : "")
    + (t.erro ? " — " + t.erro : "");
  $("#tarefa-numeros").textContent = numerosDaTarefa(t);

  const linhas = $("#tarefa-linhas");
  linhas.textContent = "";
  ULTIMA_LINHA = 0;

  /* SO quando terminou. Enquanto a sessao roda, ainda nao ha diff — e mostrar
     "nada mudou" para uma tarefa em andamento e dizer que ela terminou sem
     fazer nada. Foi o que a tela fez em 29/08/2026, e e a lei 2 sendo
     quebrada pela tela em vez de pelo numero. */
  const terminou = t.estado === "ok" || t.estado === "falha";
  if (terminou) {
    $("#tarefa-mudancas").hidden = false;
    $("#tarefa-ramo").textContent = t.ramo
      ? "As mudanças estão no ramo " + t.ramo
        + ", e não no seu código principal."
      : "A sessão terminou sem criar um ramo.";
    const ul = $("#tarefa-frases");
    ul.textContent = "";
    for (const frase of (t.frases_do_diff || [])) {
      const li = document.createElement("li");
      li.textContent = frase;
      ul.append(li);
    }
    $("#tarefa-diff").textContent = t.diff || "";
  } else {
    $("#tarefa-mudancas").hidden = true;
  }
}

function numerosDaTarefa(t) {
  const partes = [];
  partes.push((t.rodadas || 0) + (t.rodadas === 1 ? " rodada" : " rodadas"));
  if (t.iniciado_em) partes.push("começou " + haQuanto(t.iniciado_em));
  if (t.terminado_em) partes.push("terminou " + haQuanto(t.terminado_em));
  if (t.tentativas) partes.push(t.tentativas
    + (t.tentativas === 1 ? " tentativa" : " tentativas"));
  return partes.join(" · ");
}

/* ---------------------------------------------------------------- ao vivo */

let ULTIMA_LINHA = 0;

function fecharFluxo() {
  if (FLUXO) { FLUXO.close(); FLUXO = null; }
}

function ligarFluxo(id) {
  fecharFluxo();
  if (!("EventSource" in window)) return;   /* o relógio de 1 min continua */
  FLUXO = new EventSource("/api/eventos?id=" + encodeURIComponent(id)
                          + "&desde=" + ULTIMA_LINHA);
  FLUXO.addEventListener("linha", ev => {
    let d; try { d = JSON.parse(ev.data); } catch { return; }
    ULTIMA_LINHA = Math.max(ULTIMA_LINHA, d.n || 0);
    const li = document.createElement("li");
    li.textContent = d.texto;
    $("#tarefa-linhas").append(li);
    $("#tarefa-vivo").textContent = "Ao vivo. Última notícia " + hora(d.quando) + ".";
  });
  FLUXO.addEventListener("estado", ev => {
    let d; try { d = JSON.parse(ev.data); } catch { return; }
    if (d.parada_pedida) PARADA_PEDIDA.add(d.id);
    $("#tarefa-frase").textContent =
      (ANDAMENTO[d.estado] || d.estado) + (d.frase ? " — " + d.frase : "");
    if (d.estado === "ok" || d.estado === "falha") {
      fecharFluxo();
      recarregarTarefa();
      carregarTarefas().then(pintarFreio);
    }
  });
  FLUXO.addEventListener("fim", () => {
    /* O servidor encerra a conexão de tempos em tempos de propósito. Religar é
       o comportamento certo, e não um erro a mostrar. */
    fecharFluxo();
    if (TAREFA_ABERTA === id) setTimeout(() => ligarFluxo(id), 500);
  });
  FLUXO.onerror = () => {
    /* Caiu. O relógio de um minuto continua rodando por baixo, então a tela
       não fica muda — ela só deixa de ser instantânea. */
    $("#tarefa-vivo").textContent =
      "A ligação ao vivo caiu. A tela continua atualizando a cada minuto.";
  };
}

/* ================================================== 7. Consumo ========== */

async function pintarConsumo() {
  let c = null;
  try {
    const r = await fetch("/api/consumo");
    if (r.ok) c = await r.json();
  } catch {}
  const faixa = $("#aviso-consumo");
  if (!c) {
    faixa.hidden = false;
    faixa.textContent = "Não consegui medir o consumo agora.";
    $("#consumo-sessoes").textContent = "—";
    $("#consumo-resumo").textContent = "";
    $("#consumo-carimbo").textContent = "";
    return;
  }
  faixa.hidden = true;
  const t = c.total || {};
  $("#consumo-sessoes").textContent = String(t.sessoes || 0);
  $("#consumo-resumo").textContent = t.sessoes
    ? (t.sessoes === 1 ? "sessão" : "sessões") + " em " + c.dias + " dias · "
      + (t.rodadas || 0) + " rodadas · "
      + t.ok + (t.ok === 1 ? " deu certo, " : " deram certo, ")
      + t.falhas + " não · " + c.custo_em_reais + " de referência"
    : "Nenhuma sessão nesta janela. Isso é zero de verdade, e não falta de "
      + "medição — a leitura foi feita.";
  $("#consumo-carimbo").textContent = "Medido às " + hora(c.medido_em) + ".";

  encherLista("#consumo-dias", c.por_dia, l => l.dia);
  encherLista("#consumo-projetos", c.por_projeto, l => l.projeto);
  encherLista("#consumo-regras", c.por_regra, l => l.regra);
}

function encherLista(onde, linhas, nomeDe) {
  const ul = $(onde);
  ul.textContent = "";
  if (!linhas || !linhas.length) {
    ul.append(vazio("Nada nesta janela.", "", ""));
    return;
  }
  for (const l of linhas) {
    const li = document.createElement("li");
    li.className = "linha";
    const nome = document.createElement("span");
    nome.className = "linha__nome";
    nome.textContent = nomeDe(l);
    const numeros = document.createElement("span");
    numeros.className = "linha__motivo";
    numeros.textContent = l.sessoes + (l.sessoes === 1 ? " sessão" : " sessões")
      + " · " + l.rodadas + " rodadas · " + duracao(l.segundos);
    li.append(nome, numeros);
    ul.append(li);
  }
}

function duracao(segundos) {
  const s = Number(segundos) || 0;
  if (s < 60) return s + (s === 1 ? " segundo" : " segundos");
  const m = Math.round(s / 60);
  if (m < 60) return m + (m === 1 ? " minuto" : " minutos");
  const h = Math.round(m / 6) / 10;
  return String(h).replace(".", ",") + " horas";
}

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
  await carregarTarefas();
  pintarFreio();
  navegar();
  /* O relógio de um minuto CONTINUA, e não é redundância com o ao vivo: o ao
     vivo mostra UMA tarefa em detalhe, e este mantém o resto da tela — e a
     barra do freio — em dia mesmo quando o fluxo não está ligado ou caiu. */
  setInterval(async () => {
    if (await carregar()) navegar();
    if (await carregarTarefas()) pintarFreio();
  }, 60000);
  /* A barra do freio olha mais de perto: ela é o freio principal, e uma barra
     que demora um minuto para aparecer não freia nada. */
  setInterval(async () => {
    if (await carregarTarefas()) pintarFreio();
  }, 5000);
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

$("#freio-parar").addEventListener("click", () => {
  const viva = tarefaViva();
  if (viva) pararTarefa(viva.id);
});

$("#tarefa-voltar").addEventListener("click", () => irPara("#/trabalho"));

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
