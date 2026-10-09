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
/* A última leitura de `/api/maquinas` falhou. Só vale enquanto não houve
   leitura nenhuma: "não consegui ler" e "ainda não li" não são a mesma coisa. */
let COMPUTADORES_FALHOU = false;

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

/* Verdadeiro depois que `escrever` viu um 403 de página velha. Enquanto a
   faixa do alto estiver aberta, o recado de ERRO de quem clicou ("Tente de
   novo") mentiria: tentar de novo falharia de novo. */
let PAGINA_VELHA = false;

function recado(texto, ruim) {
  const el = $("#recado");
  el.textContent = ruim && PAGINA_VELHA
    ? "Não foi feito. Veja o aviso no alto da página."
    : texto;
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
  /* `#/conectar?autorizar=K7M4-2QXP`: o que vem depois do `?` é parâmetro, e
     não parte do nome da tela (antes, a tela virava "conectar?autorizar=X" e
     caía no painel). O valor sai CRU: quem o usa o valida (`codigoDeAutorizar`). */
  const bruto = (location.hash || "#/painel").slice(2);
  const corte = bruto.indexOf("?");
  const caminho = corte < 0 ? bruto : bruto.slice(0, corte);
  const busca = corte < 0 ? "" : bruto.slice(corte + 1);
  const cru = caminho.split("/");
  return { tela: cru[0] || "painel", alvo: decodeURIComponent(cru[1] || ""),
           autorizar: new URLSearchParams(busca).get("autorizar") || "" };
}

/* O menu tem QUATRO lugares (Painel, Consertar, Conectar, Conta), mas as telas
   continuam sendo as de sempre: cada uma vive sob o lugar certo. Esta tabela
   diz qual item do menu fica marcado para cada tela. Tela que não está aqui
   (projeto, alerta) não marca nenhum, como antes. */
const MENU_DE = {
  painel: "painel",
  trabalho: "trabalho", auditoria: "trabalho",
  conectar: "conectar",
  consumo: "conta", entrada: "conta"
};

/* Os endereços que existiam antes do menu enxuto. Continuam abrindo a mesma
   coisa: o endereço é reescrito para o novo (sem empilhar histórico), e a tela
   certa abre. Quem guardou o link nos favoritos não percebe a troca. */
const ROTAS_ANTIGAS = {
  computadores: "#/conectar",
  consumo: "#/conta",
  entrada: "#/conta/entrada"
};

/* `abas` diz qual aba do seletor da tela fica marcada (Tarefas | Auditoria,
   Consumo | Formas de entrar). `tambem` são telas que aparecem juntas. */
function mostrar(tela, { aba = "", tambem = [] } = {}) {
  const abertas = new Set([tela, ...tambem]);
  for (const s of document.querySelectorAll("main > section")) {
    s.hidden = !abertas.has(s.id.replace(/^tela-/, ""));
  }
  const item = MENU_DE[tela];
  for (const a of document.querySelectorAll("nav.mapa a")) {
    if (a.dataset.tela === item) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  }
  for (const a of document.querySelectorAll(".abas a")) {
    if (a.dataset.aba === aba) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  }
}

function navegar() {
  const antiga = ROTAS_ANTIGAS[rota().tela];
  if (antiga) history.replaceState(null, "", antiga);
  const { tela, alvo, autorizar } = rota();
  /* Sair da tela encerra a espera da máquina nova. Repintar a MESMA tela não —
     esse caso é tratado por `reencontrarEspera`. */
  if (ESPERA.t && ESPERA.tela !== tela) pararDeEsperar();
  switch (tela) {
    case "projeto":      mostrar("projeto"); pintarProjeto(alvo); break;
    case "alerta":       mostrar("alerta"); pintarAlerta(alvo); break;
    case "trabalho":     mostrar("trabalho", { aba: "trabalho" }); pintarTrabalho(alvo); break;
    case "auditoria":    mostrar("auditoria", { aba: "auditoria" }); pintarAuditoria(alvo); break;
    /* "Conta" tem duas abas. `#/conta` abre o consumo; `#/conta/entrada`, as
       formas de entrar. `#/consumo` e `#/entrada` chegam aqui reescritos por
       `ROTAS_ANTIGAS`. */
    case "conta":
      if (alvo === "entrada") { mostrar("entrada", { aba: "entrada" }); pdCarregar(); }
      else { mostrar("consumo", { aba: "consumo" }); pintarConsumo(); }
      break;
    /* A tela pinta PRIMEIRO, com o que ja se sabe, e depois pergunta. Assim
       ela nao fica em branco esperando a rede -- e "nao deu para conferir"
       fica reservado para a pergunta que falhou, e nao para a que nunca foi
       feita. As duas coisas se parecem na tela e nao sao a mesma. */
    /* A tela dos computadores (parear, "Deixar consertar aqui") mora embaixo
       da de conectar projeto, na mesma página. */
    case "conectar":     mostrar("conectar", { tambem: ["computadores"] });
                         pintarConectar();
                         abrirOuFecharAutorizar(autorizar);
                         olharOsServidores();
                         olharOsEnderecos(); olharOGithub();
                         carregarComputadores(); carregarVoz(); break;
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

/* SERVIDORES MÚLTIPLOS (etapa 6): a lista de sites do projeto, um item por
   servidor onde ele tem endereço gravado.

   `null` = "não sei" (a camada GitHub não foi lida, ou não trouxe nada);
   `[]` = "sei, e é vazio" (nenhum servidor tem esse projeto). As duas coisas
   NUNCA se confundem — é a mesma lei 2 que distingue "não deu para conferir"
   de "não está conectado" em toda porta desta tela.

   PONTE PARA DADO ANTIGO: enquanto `coletar_github` não escrever `sites`
   (lista), a camada `github` ainda carrega `site` (um dicionário só). Ela
   vira uma lista de um item, com `servidor: ""` — e some sozinha na
   primeira coleta que já escrever o formato novo. */
function sitesDoProjeto(gh) {
  if (!gh) return null;
  if (Array.isArray(gh.sites)) return gh.sites;
  if (gh.site) return [Object.assign({ servidor: "" }, gh.site)];
  return [];
}

/* O selo "servidor(es)" do card do projeto e do cabeçalho da tela de
   detalhe: NUNCA um quinto estado — os três de `marcaDaPorta` bastam, e o
   rótulo escrito é quem carrega a contagem ("em 2 servidores"). A saúde de
   cada servidor (respondendo ou não) já é o `piorDe()` de cima; este selo
   responde só "em quantos e quais", nunca "está no ar". */
function seloDeServidores(p) {
  const sites = (p.camadas || {}).github ? sitesDoProjeto(p.github) : null;
  if (sites === null) {
    return { estado: "sem_dados", rotulo: "não deu para conferir" };
  }
  if (!sites.length) {
    return { estado: "desconectado",
             rotulo: "não está em nenhum servidor cadastrado" };
  }
  const n = sites.length;
  return { estado: "conectado",
           rotulo: n === 1 ? "em 1 servidor" : "em " + n + " servidores" };
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
  /* Sem nenhum estado medido a lista fica vazia, e a frase virava ". E 24 não
     foram medidos." — um ponto solto na frente. Nesse caso a frase é só esta. */
  if (!partes.length) {
    return conta.sem_dados === 1 ? "O seu projeto ainda não foi medido."
                                 : "Nenhum dos " + total + " projetos foi medido ainda.";
  }
  let frase = partes.join(", ") + ".";
  if (conta.sem_dados) {
    frase += conta.sem_dados === 1 ? " E 1 não foi medido."
                                   : " E " + conta.sem_dados + " não foram medidos.";
  }
  return frase;
}

/* Projeto escondido some do resumo, e um projeto escondido e quebrado sumiria
   calado. Por isso o painel diz quantos há, com o caminho para trazê-los de
   volta. Servidor antigo (sem `ocultos`) não mostra a linha. */
function pintarOcultos() {
  const lugar = $("#painel-ocultos");
  const n = ((ESTADO && ESTADO.ocultos) || []).length;
  lugar.hidden = !n;
  if (!n) return;
  const a = criar("a", "", "Ver em Conectar");
  a.href = "#/conectar";
  lugar.replaceChildren(n + (n === 1 ? " projeto escondido" : " projetos escondidos")
                        + " do painel. ", a, ".");
}

function pintarPainel() {
  if (!ESTADO) return;
  const projetos = ESTADO.projetos || [];
  const conta = { saudavel: 0, atencao: 0, quebrado: 0, sem_dados: 0 };
  for (const p of projetos) conta[p.selo] = (conta[p.selo] || 0) + 1;

  $("#resumo").textContent = fraseDeResumo(conta, projetos.length);
  pintarRecomendada();
  pintarOcultos();

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

    /* O selo "servidor(es)", AO LADO do selo principal — servidores
       múltiplos, etapa 6. Ele nunca inventa um quinto estado: os três de
       `marcaDaPorta` bastam, e "1 servidor caiu" já é o `piorDe()` de cima
       que resolve, com o nome do servidor na frase do motivo. */
    const infoServ = seloDeServidores(p);
    const marcaServ = marcaDaPorta(infoServ.estado, infoServ.rotulo);
    marcaServ.classList.add("marca--servidores");
    li.append(marcaServ);

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
    abrir.textContent = "Ver detalhes";
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

/* A validade da camada github, em segundos: CÓPIA de regras.VALIDADE["github"],
   a mesma régua que decide `p.camadas.github`. test_servir cobra que as duas
   são iguais — mudar de um lado só reprova. */
const VALIDADE_GITHUB_S = 2 * 3600;

/* O motivo da conta (linha `_github`) para o card de UM projeto, ou `null`
   para a frase genérica. Só vale se a tentativa é fresca pela mesma validade
   do selo, e se não é um motivo parcial de OUTROS repositórios: com
   `sem_alcance` preenchido e o projeto fora dele (sem "e mais N", que pode
   escondê-lo), "medi 50 de 60" no card de um medido seria mentira. */
function motivoDoGithubDaConta(nome) {
  const daConta = ESTADO && ESTADO.github_da_conta;
  if (!daConta || !daConta.motivo) return null;
  const idade = (Date.parse(ESTADO.agora) - Date.parse(daConta.tentado_em)) / 1000;
  if (!(idade <= VALIDADE_GITHUB_S)) return null;
  const fora = Array.isArray(daConta.sem_alcance) ? daConta.sem_alcance : [];
  if (fora.length && !fora.includes(nome)
      && !fora.some(n => typeof n === "string" && n.startsWith("e mais "))) {
    return null;
  }
  return daConta.motivo.charAt(0).toUpperCase() + daConta.motivo.slice(1) + ".";
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
    $("#projeto-progresso").hidden = true;
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
    /* O motivo da conta vem do servidor (frase nossa, nunca texto do GitHub)
       e entra só por textContent, dentro de nada(). */
    const motivo = motivoDoGithubDaConta(p.nome)
      || "A medição do GitHub não foi lida, ou está velha demais "
        + "para afirmar alguma coisa.";
    nogh.append(nada(motivo, c.github));
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
    const dep = gh.deploy || {};
    /* SERVIDORES MÚLTIPLOS (etapa 6): um critério POR SERVIDOR onde o
       projeto tem endereço, cada um com o próprio selo, código e carimbo —
       "um critério que falha não derruba os outros" (design.md, tela 3). */
    const sites = sitesDoProjeto(gh);
    if (!sites || !sites.length) {
      noar.append(criterio(
        "Site respondendo", "sem_dados",
        "Não está em nenhum servidor cadastrado.", marca, ""));
    } else {
      for (const item of sites) {
        const rotuloCriterio = item.servidor
          ? "Site respondendo — " + item.servidor
          : "Site respondendo";
        noar.append(criterio(
          rotuloCriterio,
          item.ok === false ? "quebrado" : item.ok === true ? "saudavel" : "sem_dados",
          item.ok === true ? "responde" : item.ok === false ? "fora do ar" : "não medido",
          item.ok === null || item.ok === undefined
            ? "ainda não medido" : "medido " + haQuanto(item.medido_em),
          (item.url || "") + "\ncódigo: " + (item.codigo ?? "sem resposta")));
      }
    }
    noar.append(criterio(
      "Versão publicada",
      typeof dep.atras === "number" && dep.atras > 0 ? "atencao"
        : typeof dep.atras === "number" ? "saudavel" : "sem_dados",
      typeof dep.atras === "number"
        ? (dep.atras > 0 ? dep.atras + " commit(s) atrás do GitHub" : "em dia")
        : "não medido",
      marca, JSON.stringify(dep, null, 1)));
  }

  pintarProgresso(p);
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
    b.textContent = "Ver detalhes";
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

/* ================================ Progresso pela documentação ============== */
/* Tudo o que vem do servidor aqui (texto de critério, prova, erro de formato,
   nome de documento) nasceu num arquivo de OUTRO repositório: dado hostil. Só
   `textContent`, nunca HTML. O selo de saúde não lê nada disto: progresso é
   outra pergunta ("quanto falta?"), e misturá-la ao selo faria o selo mentir. */
const PROGRESSO_SITUACAO = {
  comprovado:     { rotulo: "Comprovado",     glifo: "✓" },
  prova_falhou:   { rotulo: "Prova falhou",   glifo: "✕" },
  nao_verificado: { rotulo: "Não verificado", glifo: "?" },
  falta:          { rotulo: "Falta",          glifo: "○" }
};
let PROGRESSO_VEZ = 0;        // a cada pintura; resposta atrasada não repinta
const PROGRESSO_CACHE = {};   // nome -> { medido_em, corpo }

/* Inteiro não negativo, ou 0. O `+` é de propósito: test_design toma
   `Number(`/`parseInt(` por "número na tela sem carimbo". */
function inteiroDoProgresso(v) {
  const n = +v;
  return isFinite(n) && n > 0 ? Math.trunc(n) : 0;
}

function linhaDoProgresso(texto, classe) {
  const p = document.createElement("p");
  if (classe) p.className = classe;
  p.textContent = texto;
  return p;
}

/* As quatro faces. O número grande e a barra só existem em "medido": nos
   outros três, o percentual não existe e escrever 0% ou 100% seria inventar. */
function pintarProgresso(p) {
  const sec = $("#projeto-progresso");
  const resumo = $("#progresso-resumo");
  $("#progresso-lista").textContent = "";
  $("#progresso-recado-caixa").hidden = true;
  resumo.textContent = "";
  PROGRESSO_VEZ += 1;
  sec.hidden = false;

  const pr = p && p.progresso ? p.progresso : { estado: "sem_dados" };
  const carimbo = "medido " + haQuanto(pr.medido_em);
  const tem = x => inteiroDoProgresso(pr[x]);
  const lido = pr.estado === "medido" && typeof pr.percentual === "number"
    ? "medido"
    : (pr.estado === "nao_verificado" || pr.estado === "sem_documentacao"
        ? pr.estado : "sem_dados");
  sec.dataset.estado = lido;

  if (lido === "sem_dados") {
    resumo.append(nada("O agente deste computador ainda não lê a documentação do "
                       + "projeto (ou é uma versão antiga). Reinicie o agente.",
                       pr.medido_em));
    return;
  }

  if (lido === "sem_documentacao") {
    const v = document.createElement("div");
    v.className = "vazio";
    v.append(
      linhaDoProgresso("Sem documentação. O projeto não tem critérios de "
                       + "aceitação em docs/esteira, então não há o que medir."),
      linhaDoProgresso("Escreva um briefing com a lista de critérios (veja "
                       + "docs/A-DOCUMENTACAO-QUE-O-DERVS-LE.md) e o número "
                       + "aparece aqui.", "mole"),
      linhaDoProgresso(carimbo, "carimbo"));
    resumo.append(v);
    return;
  }

  const contas = document.createElement("ul");
  contas.className = "progresso__contas";
  const conta = (n, frase) => {
    if (!n) return;
    const li = document.createElement("li");
    li.textContent = n + " " + frase;
    contas.append(li);
  };

  if (lido === "medido") {
    const pct = Math.min(100, inteiroDoProgresso(pr.percentual));
    const grande = document.createElement("p");
    grande.className = "progresso__numero";
    grande.textContent = pct + "%";
    const barra = document.createElement("progress");
    barra.className = "progresso__barra";
    barra.max = 100;
    barra.value = pct;
    barra.setAttribute("aria-label", "Critérios comprovados");
    resumo.append(grande, barra);
    const base = document.createElement("li");
    base.textContent = tem("comprovados") + " de " + tem("total") + " critérios comprovados";
    contas.append(base);
    conta(tem("falhos"), "com a prova falhando");
    conta(tem("nao_verificados"), "não verificados (prova ainda não rodou)");
    conta(tem("faltam"), "faltam");
  } else {
    resumo.append(linhaDoProgresso("Nenhuma prova rodou ainda.", "progresso__destaque"));
    conta(tem("total"), "critérios documentados, nenhum comprovado");
  }
  conta(tem("declarados"), "marcados no documento, sem prova");
  resumo.append(contas);
  if (tem("erros_n")) {
    resumo.append(linhaDoProgresso(
      tem("erros_n") + " erro(s) de formato nos documentos. Eles estão indicados "
      + "abaixo e ficam de fora da conta.", "mole"));
  }
  resumo.append(linhaDoProgresso(
    carimbo + " · " + tem("documentos_n") + " documento(s) lido(s)", "carimbo"));
  if (lido === "medido" && pr.provado_em) {
    resumo.append(linhaDoProgresso("provado " + haQuanto(pr.provado_em), "carimbo"));
  }

  carregarProgresso(p.nome, pr.medido_em);
}

async function carregarProgresso(nome, medidoEm) {
  const vez = PROGRESSO_VEZ;
  const lista = $("#progresso-lista");
  const cache = PROGRESSO_CACHE[nome];
  if (cache && cache.medido_em === medidoEm) { pintarCriterios(cache.corpo); return; }
  lista.textContent = "";
  lista.append(linhaDoProgresso("Carregando os critérios…", "mole"));

  const falhou = (frase) => {
    if (vez !== PROGRESSO_VEZ) return;
    lista.textContent = "";
    const b = document.createElement("button");
    b.type = "button";
    b.className = "botao botao--secundario";
    b.textContent = "Tentar de novo";
    b.addEventListener("click", () => carregarProgresso(nome, medidoEm));
    lista.append(linhaDoProgresso(frase), b);
  };

  let r;
  try {
    r = await fetch("/api/progresso?projeto=" + encodeURIComponent(nome));
  } catch {
    falhou("Não deu para falar com o servidor. Os números acima continuam valendo; a lista de critérios não chegou.");
    return;
  }
  let corpo = null;
  try { corpo = await r.json(); } catch {}
  if (!r.ok) {
    falhou(r.status === 404
      ? "Este projeto não está mais na lista. Volte ao painel."
      : "Não deu para ler os critérios agora (erro " + r.status + ").");
    return;
  }
  if (!corpo || !Array.isArray(corpo.documentos)) {
    falhou("O servidor respondeu de um jeito que não entendi.");
    return;
  }
  if (vez !== PROGRESSO_VEZ) return;
  PROGRESSO_CACHE[nome] = { medido_em: medidoEm, corpo };
  pintarCriterios(corpo);
}

function pintarCriterios(corpo) {
  const lista = $("#progresso-lista");
  lista.textContent = "";
  if (corpo.provavel === true && typeof corpo.projeto === "string") {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "botao botao--secundario";
    b.textContent = "Rodar as provas";
    b.addEventListener("click", () => provarProjeto(corpo.projeto, b));
    lista.append(b);
  }
  for (const d of corpo.documentos) {
    const sec = document.createElement("section");
    sec.className = "progresso__doc";
    const h = document.createElement("h3");
    h.textContent = d.slug || "documento";
    const dia = dataDoDocumento(d.aprovado_em);
    sec.append(h, linhaDoProgresso(
      dia ? "Aprovado em " + dia + "."
          : "Ainda não aprovado: falta a linha «Aprovado em: AAAA-MM-DD» no documento.",
      "metadado"));
    for (const e of (d.erros || [])) {
      sec.append(linhaDoProgresso("Erro de formato: " + e, "progresso__erro"));
    }
    const ul = document.createElement("ul");
    ul.className = "progresso__criterios";
    for (const c of (d.criterios || [])) ul.append(linhaDeCriterio(c));
    sec.append(ul);
    lista.append(sec);
  }
}

function dataDoDocumento(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(typeof iso === "string" ? iso : "");
  return m ? m[3] + "/" + m[2] + "/" + m[1] : "";
}

function linhaDeCriterio(c) {
  const li = document.createElement("li");
  li.className = "progresso__criterio";
  /* Situação desconhecida cai em "não verificado", nunca em "comprovado". */
  const sit = PROGRESSO_SITUACAO[c.situacao] ? c.situacao : "nao_verificado";
  const marca = document.createElement("span");
  marca.className = "progresso__situacao";
  marca.dataset.situacao = sit;
  marca.textContent = PROGRESSO_SITUACAO[sit].glifo + " " + PROGRESSO_SITUACAO[sit].rotulo;
  const texto = document.createElement("span");
  texto.className = "progresso__texto";
  texto.textContent = c.texto;
  li.append(marca, texto);

  if (c.prova) {
    const pv = document.createElement("p");
    pv.className = "metadado progresso__prova";
    const cmd = document.createElement("code");
    cmd.textContent = c.prova;
    pv.append("Prova: ", cmd);
    if (c.prova_aceita !== true) {
      pv.append(" (comando fora da lista permitida: nunca roda)");
    } else if (sit === "nao_verificado") {
      pv.append(" (ainda não rodou)");
    }
    li.append(pv);
  }

  if (c.desenvolvivel === true) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "botao botao--secundario";
    b.textContent = "Desenvolver isto";
    b.setAttribute("aria-label", "Desenvolver isto: " + c.texto);
    b.addEventListener("click", () => desenvolverCriterio(c, b));
    li.append(b);
  } else if (typeof c.motivo === "string" && c.motivo) {
    li.append(linhaDoProgresso(c.motivo, "metadado"));
  }
  return li;
}

/* O que o dono lê quando o pedido não entra. O servidor fala pela própria boca
   só nos quatro 403; o resto é frase nossa. */
function frasePorQueNaoDesenvolveu(status, corpo) {
  const erro = corpo && typeof corpo.erro === "string" ? corpo.erro : "";
  if (status === 401) return "Sua sessão acabou. Recarregue a página e entre de novo.";
  if (status === 403 && erro === "documento nao aprovado") {
    return "O documento deste critério ainda não foi aprovado. Acrescente a linha "
      + "«Aprovado em: AAAA-MM-DD» ao briefing e tente de novo.";
  }
  if (status === 403 && erro === "projeto bloqueado") {
    return "Este projeto não pode ser desenvolvido pelo DERVS.";
  }
  if (status === 403 && erro === "criterio sensivel") {
    return "Este critério trata de segurança, senha, pagamento ou dado de paciente. "
      + "O DERVS não desenvolve isso sozinho.";
  }
  if (status === 403 && erro === "criterio ja marcado") {
    return "Este critério já está marcado como cumprido no documento.";
  }
  if (status === 403) return "Este critério não pode ser desenvolvido por aqui.";
  if (status === 404) return "Este critério não está mais no documento. Recarregue a tela.";
  if (status === 400) return "O pedido saiu incompleto. Recarregue a tela e tente de novo.";
  if (status === 429) return "Você pediu desenvolvimento demais em pouco tempo. Espere um pouco e tente de novo.";
  return "Não deu para pedir o desenvolvimento agora (erro " + status + "). Tente de novo em instantes.";
}

async function desenvolverCriterio(c, botao) {
  const caixa = $("#progresso-recado-caixa");
  const texto = $("#progresso-recado-texto");
  const aviso = $("#progresso-recado-aviso");
  const link = $("#progresso-recado-link");
  aviso.hidden = true;
  aviso.textContent = "";
  botao.disabled = true;

  const mostrarFalha = (frase) => {
    caixa.hidden = false;
    link.hidden = true;
    texto.textContent = frase;
    botao.disabled = false;
  };

  let r;
  try {
    r = await escrever("/api/desenvolver", { criterio: c.id });
  } catch {
    mostrarFalha("Não deu para falar com o servidor. Confira a conexão e tente de novo.");
    return;
  }
  let corpo = null;
  try { corpo = await r.json(); } catch {}

  if (!r.ok) { mostrarFalha(frasePorQueNaoDesenvolveu(r.status, corpo)); return; }
  if (!corpo || corpo.ok !== true) {
    mostrarFalha("O servidor respondeu de um jeito que não entendi. Confira em "
                 + "Consertar se o pedido entrou na fila.");
    link.hidden = false;
    return;
  }

  caixa.hidden = false;
  link.hidden = false;
  const repetido = corpo.pedido === false;
  texto.textContent = repetido
    ? (typeof corpo.aviso === "string" && corpo.aviso
        ? corpo.aviso : "Este desenvolvimento já foi pedido. Veja em Consertar.")
    : "Na fila. Nada roda até você aprovar em Consertar.";
  if (!repetido && typeof corpo.aviso === "string" && corpo.aviso) {
    aviso.hidden = false;
    aviso.textContent = corpo.aviso;
  }
  botao.disabled = true; /* já está na fila: outro clique só repetiria o pedido */
  await carregarTarefas();
}
/* O que o dono lê quando o pedido de prova não entra. Frase nossa: o texto cru
   do servidor nunca vai para a tela. */
function frasePorQueNaoProvou(status) {
  if (status === 401) return "Sua sessão acabou. Recarregue a página e entre de novo.";
  if (status === 403) return "Este projeto não pode ser provado pelo DERVS.";
  if (status === 404) return "Este projeto não está mais na lista. Volte ao painel.";
  if (status === 409) return "Nenhuma prova da documentação está na lista permitida. Não há o que rodar.";
  if (status === 429) return "Você pediu provas demais em pouco tempo. Espere um pouco e tente de novo.";
  return "Não deu para pedir as provas agora (erro " + status + "). Tente de novo em instantes.";
}

async function provarProjeto(nome, botao) {
  const caixa = $("#progresso-recado-caixa");
  const texto = $("#progresso-recado-texto");
  const aviso = $("#progresso-recado-aviso");
  const link = $("#progresso-recado-link");
  aviso.hidden = true;
  aviso.textContent = "";
  botao.disabled = true;

  const mostrarFalha = (frase) => {
    caixa.hidden = false;
    link.hidden = true;
    texto.textContent = frase;
    botao.disabled = false;
  };

  let r;
  try {
    r = await escrever("/api/provar", { projeto: nome });
  } catch {
    mostrarFalha("Não deu para falar com o servidor. Confira a conexão e tente de novo.");
    return;
  }
  let corpo = null;
  try { corpo = await r.json(); } catch {}

  if (!r.ok) { mostrarFalha(frasePorQueNaoProvou(r.status)); return; }
  if (!corpo || corpo.ok !== true) {
    mostrarFalha("O servidor respondeu de um jeito que não entendi. Confira em "
                 + "Consertar se o pedido entrou na fila.");
    link.hidden = false;
    return;
  }

  caixa.hidden = false;
  link.hidden = false;
  if (corpo.pedido === false) {
    texto.textContent = "Já há uma prova deste projeto esperando ou rodando. Veja em Consertar.";
  } else {
    texto.textContent = "Na fila. Nada roda até você aprovar em Consertar.";
    if (typeof corpo.aviso === "string" && corpo.aviso) {
      aviso.hidden = false;
      aviso.textContent = corpo.aviso;
    }
  }
  botao.disabled = true; /* já está na fila: outro clique só repetiria o pedido */
  await carregarTarefas();
}
/* ============================ fim: Progresso pela documentação ============= */

/* ================================================== 6. Alerta ============ */

/* O que o dono lê quando o pedido de conserto não entra. Sempre uma frase
   em português: "nada acontece" ao clicar é o pior dos resultados. O servidor
   fala pela própria boca só nos dois 403 que descrevem algo que o dono entende;
   o resto é frase nossa. */
function frasePorQueNaoConsertou(status, corpo) {
  const erro = corpo && typeof corpo.erro === "string" ? corpo.erro : "";
  if (status === 401) return "Sua sessão acabou. Recarregue a página e entre de novo.";
  if (status === 404) return "Este alerta não está mais na lista. Volte ao painel para ver o que vale agora.";
  if (status === 403 && erro === "projeto bloqueado") {
    return "Este projeto não pode ser consertado pelo DERVS.";
  }
  if (status === 403) return "Este tipo de alerta não é consertado por aqui.";
  if (status === 429) return "Você pediu conserto demais em pouco tempo. Espere um pouco e tente de novo.";
  return "Não deu para pedir o conserto agora (erro " + status + "). Tente de novo em instantes.";
}

async function consertarComIA(p, botao) {
  const caixa = $("#alerta-consertar-resposta");
  const texto = $("#alerta-consertar-texto");
  const aviso = $("#alerta-consertar-aviso");
  const link = $("#alerta-consertar-link");
  aviso.hidden = true;
  aviso.textContent = "";
  botao.disabled = true;

  const mostrarFalha = (frase) => {
    caixa.hidden = false;
    link.hidden = true;
    texto.textContent = frase;
    botao.disabled = false;
  };

  let r;
  try {
    r = await escrever("/api/consertar", { id: p.id });
  } catch {
    mostrarFalha("Não deu para falar com o servidor. Confira a conexão e tente de novo.");
    return;
  }
  let corpo = null;
  try { corpo = await r.json(); } catch {}

  if (!r.ok) { mostrarFalha(frasePorQueNaoConsertou(r.status, corpo)); return; }
  if (!corpo || corpo.ok !== true) {
    mostrarFalha("O servidor respondeu de um jeito que não entendi. Confira em "
                 + "Consertar se o pedido entrou na fila.");
    link.hidden = false;
    return;
  }

  caixa.hidden = false;
  link.hidden = false;
  /* Pedido repetido: quem sabe o estado real da tarefa é o servidor (na fila,
     rodando, feita, falhou), e a frase dele é a única que não mente. */
  const repetido = corpo.pedido === false;
  texto.textContent = repetido
    ? (typeof corpo.aviso === "string" && corpo.aviso
        ? corpo.aviso : "Este conserto já foi pedido. Veja em Consertar.")
    : "Na fila. Aprove em Consertar.";
  /* O aviso é o motivo pelo qual o conserto entrou na fila mas NÃO roda agora
     (nenhum computador, sem autorização, teto do dia). Vem pronto do servidor. */
  if (!repetido && typeof corpo.aviso === "string" && corpo.aviso) {
    aviso.hidden = false;
    aviso.textContent = corpo.aviso;
  }
  botao.disabled = true; /* já está na fila: outro clique só repetiria o pedido */
  await carregarTarefas();
}

function pintarAlerta(id) {
  const p = (ESTADO && ESTADO.pendencias || []).find(x => x.id === id);
  const acoes = $("#alerta-acoes");
  acoes.textContent = "";
  $("#alerta-consertar-resposta").hidden = true;
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

  /* O botão só existe quando o SERVIDOR diz que a regra é consertável
     (`consertavel`). A tela nunca decide sozinha: a lista de regras vive num
     lugar só, no servidor, e ele recusa o pedido de qualquer outra de todo
     jeito. Sem `consertavel`, sem botão. */
  if (p.consertavel) {
    const conserto = document.createElement("button");
    conserto.className = "botao";
    conserto.type = "button";
    conserto.id = "alerta-consertar";
    conserto.textContent = "Consertar com IA";
    conserto.addEventListener("click", () => consertarComIA(p, conserto));
    acoes.prepend(conserto);
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

/* A faixa "Esta página ficou desatualizada". O token anti-falsificação vence
   (outra aba, o DERVS atualizado) e TODA escrita passa a ser recusada com 403 e
   `motivo: "pagina_velha"`. Sem a faixa, cada botão diria o seu "tente de novo"
   e nenhum deles adiantaria. Uma instância só: a segunda recusa não empilha. */
function abrirFaixaPaginaVelha() {
  if (PAGINA_VELHA) return;
  PAGINA_VELHA = true;
  const faixa = document.createElement("div");
  faixa.className = "faixa faixa--pagina-velha";
  faixa.setAttribute("role", "alert");
  const dizeres = document.createElement("div");
  const forte = document.createElement("strong");
  forte.textContent = "Esta página ficou desatualizada.";
  const resto = document.createElement("span");
  resto.textContent = "O que você acabou de clicar não foi feito. Recarregue "
                    + "a página para continuar. O que você estava digitando "
                    + "pode se perder.";
  dizeres.append(forte, " ", resto);
  const botao = document.createElement("button");
  botao.type = "button";
  botao.className = "botao";
  botao.textContent = "Recarregar";
  botao.addEventListener("click", () => location.reload());
  faixa.append(dizeres, botao);
  $("#faixa-pagina-velha").append(faixa);
  /* A página inteira deixou de funcionar até recarregar: aqui mover o foco
     ajuda em vez de atrapalhar. */
  botao.focus();
}

async function escrever(url, corpo) {
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Token": TOKEN },
    body: JSON.stringify(corpo || {})
  });
  if (r.status === 403) {
    /* `clone()`: quem chamou ainda lê o corpo. Só o motivo exato abre a
       faixa; os outros 403 ("entre de novo", "origem nao permitida") seguem
       com o recado de cada chamador. */
    try {
      const j = await r.clone().json();
      if (j && j.motivo === "pagina_velha") abrirFaixaPaginaVelha();
    } catch (_) { /* corpo que não é JSON: não é página velha */ }
  }
  return r;
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

/* AS TRES PORTAS (etapa A5).

   A tela antiga mandava o dono para outra tela e escrevia na cara dele que
   conectar a conta do GitHub e conectar o servidor "ficaram para a fatia 2".
   Agora as tres portas moram aqui, e cada uma diz o estado dela em vez de
   prometer.

   TRES ESTADOS, e o terceiro e de primeira classe: conectado, nao conectado e
   NAO DEU PARA CONFERIR. Zerar o que nao deu para reler apaga um problema
   real, e essa e a lei 2 deste produto. */

const ESTADO_DA_PORTA = {
  conectado:   { cor: "verde",    glifo: "[OK]",  rotulo: "conectado" },
  desconectado:{ cor: "vermelho", glifo: "[X]",   rotulo: "não conectado" },
  sem_dados:   { cor: "neutro",   glifo: "[···]", rotulo: "não deu para conferir" }
};

/* QUATRO SINAIS, como o selo dos projetos: cor (o fundo), forma (a borda),
   glifo (o caractere) e rótulo escrito. Cor sozinha some no preto e branco e
   não existe para quem não distingue verde de vermelho.

   `rotulo` é opcional: por padrão o texto é o de `ESTADO_DA_PORTA[e].rotulo`,
   mas o selo "servidor(es)" do card do projeto (servidores múltiplos, etapa
   6) precisa de um texto que carrega a CONTAGEM — "em 2 servidores" — e não
   um dos três rótulos fixos. Um parâmetro a mais evita a segunda montagem de
   marca que o comentário de `porta()` já avisa que diverge. */
function marcaDaPorta(estado, rotulo) {
  const e = ESTADO_DA_PORTA[estado] ? estado : "sem_dados";
  const d = ESTADO_DA_PORTA[e];
  const span = document.createElement("span");
  span.className = "marca";
  span.dataset.cor = d.cor;
  const g = document.createElement("span");
  g.className = "marca__glifo";
  g.setAttribute("aria-hidden", "true");
  g.textContent = d.glifo;
  const r = document.createElement("span");
  r.textContent = rotulo || d.rotulo;
  span.append(g, r);
  return span;
}

/* ---------------------------------------------------------- pequenos ajudantes
   Um jeito só de montar um elemento com texto. O texto entra SEMPRE por
   `textContent`: nome de computador, de pasta e de projeto vêm de fora. */
function criar(tag, classe, texto) {
  const e = document.createElement(tag);
  if (classe) e.className = classe;
  if (texto) e.textContent = texto;
  return e;
}

/* Um botão dentro de `.acoes`: é lá que mora o `min-height: 44px`. */
function botaoEmAcoes(rotulo, secundario, aoClicar) {
  const acoes = criar("div", "acoes");
  const b = criar("button", "botao" + (secundario ? " botao--secundario" : ""), rotulo);
  b.type = "button";
  b.addEventListener("click", aoClicar);
  acoes.append(b);
  return { acoes, botao: b };
}

/* "mais 8 minutos" / "mais 1 minuto" / "menos de um minuto": o que vai depois
   de "Vale por". Zero minuto nunca é escrito como "0". */
function prazoEmPalavras(n) {
  if (!(n >= 1)) return "menos de um minuto";
  return n === 1 ? "mais 1 minuto" : "mais " + n + " minutos";
}

/* O botão principal do cartão é um LINK com GET, e não um botão que chama
   `escrever`: o navegador baixa na hora, dentro do gesto do clique, e o
   servidor não precisa de pedido de escrita para entregar um arquivo.
   Na marcação: href="/api/conectar.cmd" e download="conectar-dervs.cmd".
   A espera começa AQUI, no clique de baixar — o intervalo entre baixar e
   abrir é justamente onde a pessoa não sabe se deu certo. O clique não é
   cancelado: o download segue. */
function linkDeBaixar(rotulo, secundario) {
  const a = criar("a", "botao" + (secundario ? " botao--secundario" : ""), rotulo);
  a.href = "/api/conectar.cmd";
  a.download = "conectar-dervs.cmd";
  a.addEventListener("click", () => esperarMaquinaNova($("#espera-maquina"), 10));
  return a;
}

/* -------------------------------------------- o bloco "Autorizar este computador"
   O arquivo baixado abre o navegador em `#/conectar?autorizar=<código>`. O
   código vem DE FORA (da barra de endereço): só entra se for do formato exato,
   e nunca é lido como HTML. Aqui o dono confere o nome e o código com a janela
   preta do computador e autoriza — sem o clique, nada é ligado. */
const AUTORIZAR = { codigo: "", dados: null, fase: "", prazo: null,
                    fim: 0, botao: null, focou: false };

/* O formato exato do código curto: oito símbolos de um alfabeto sem 0/O/1/I/L,
   mostrado como XXXX-XXXX. Devolve "" para qualquer outra coisa. */
function codigoDeAutorizar(texto) {
  const limpo = String(texto || "").toUpperCase().replace(/[\s-]/g, "");
  if (!/^[2-9A-HJKMNP-Z]{8}$/.test(limpo)) return "";
  return limpo.slice(0, 4) + "-" + limpo.slice(4);
}

function pintarAutorizar(p) {
  const bloco = $("#conectar-autorizar");
  bloco.hidden = false;
  AUTORIZAR.fase = p.estado;
  AUTORIZAR.prazo = null;
  AUTORIZAR.botao = null;
  bloco.setAttribute("aria-busy", p.estado === "carregando" ? "true" : "false");

  const titulo = criar("h2", "", "Autorizar este computador?");
  titulo.id = "autorizar-titulo";
  titulo.setAttribute("tabindex", "-1");
  const partes = [titulo];

  if (p.estado === "carregando") {
    partes.push(criar("p", "mole", "Conferindo o pedido…"));
  } else if (p.estado === "nao_existe") {
    partes.push(criar("p", "", "Este pedido venceu ou não existe. Baixe o arquivo de novo e abra."));
    partes.push(botaoEmAcoes("Voltar para Conectar", false, fecharAutorizar).acoes);
  } else if (p.estado === "erro_rede") {
    partes.push(criar("p", "", "Não consegui falar com o DERVS agora. Isso não quer dizer que o pedido venceu — quer dizer que não olhei."));
    partes.push(botaoEmAcoes("Tentar de novo", true,
                             () => olharOPedido(AUTORIZAR.codigo)).acoes);
  } else if (p.estado === "autorizado" || p.estado === "conectado") {
    partes.push(criar("p", "", "Este computador já foi autorizado. Veja abaixo se ele apareceu."));
  } else if (p.estado === "sucesso") {
    partes.push(criar("p", "", "Autorizado. Volte à janela preta do computador: ela termina sozinha."));
  } else {
    /* "esperando", "enviando" e "erro_autorizar": o pedido existe e ainda não
       foi autorizado. O botão só existe COM os dados na tela — ninguém
       autoriza às cegas. */
    const corpo = criar("p");
    corpo.append("O computador ", criar("strong", "", p.maquina || "sem nome"),
                 " pediu para se ligar ao seu painel. Confira se o nome e o "
                 + "código abaixo são os mesmos da janela preta no computador.");
    const codigo = String(p.codigo || "");
    const numero = criar("p", "numerao", codigo);
    /* O código é lido letra a letra: "K7M4" falado como palavra não confere
       com nada. */
    numero.setAttribute("aria-label", "Código: " + codigo.replace("-", "").split("").join(", "));
    const prazo = criar("p", "carimbo", "Vale por " + prazoEmPalavras(p.minutos) + ".");
    AUTORIZAR.prazo = prazo;
    partes.push(corpo, criar("p", "carimbo", "Código"), numero, prazo);
    if (p.estado === "erro_autorizar") {
      partes.push(criar("p", "", "Não consegui falar com o DERVS agora. Isso não quer dizer que o pedido venceu — quer dizer que não olhei."));
    }
    const { acoes, botao } = botaoEmAcoes("Autorizar este computador", false, autorizarPedido);
    if (p.estado === "enviando") {
      botao.disabled = true;
      botao.setAttribute("aria-busy", "true");
    }
    AUTORIZAR.botao = botao;
    partes.push(acoes);
    partes.push(criar("p", "mole", "Não reconhece este computador? Não clique em nada: o pedido vence sozinho e nada é ligado."));
  }

  bloco.replaceChildren(...partes);
  /* Ao abrir a página o foco vai para o título (lido: "Autorizar este
     computador?"); depois disso o foco é da pessoa. */
  if (!AUTORIZAR.focou) { AUTORIZAR.focou = true; titulo.focus(); }
  if (p.estado === "erro_autorizar" && AUTORIZAR.botao) AUTORIZAR.botao.focus();
}

/* UMA leitura por página: `GET /api/pedido` tem balcão de 20 por origem em 15
   minutos, e sondá-lo gastaria o balcão do próprio dono. Quem sonda é
   `/api/maquinas`. O prazo que anda a cada minuto é calculado aqui, com o
   relógio, a partir dos minutos que o servidor disse na leitura. */
async function olharOPedido(codigo) {
  pintarAutorizar({ estado: "carregando" });
  let r = null;
  try { r = await fetch("/api/pedido?codigo=" + encodeURIComponent(codigo)); }
  catch (_) { r = null; }
  /* Outra página abriu, ou o dono já clicou, enquanto a resposta viajava. */
  if (codigo !== AUTORIZAR.codigo) return;
  if (AUTORIZAR.fase === "enviando" || AUTORIZAR.fase === "sucesso") return;
  if (r && (r.status === 404 || r.status === 400)) {
    pintarAutorizar({ estado: "nao_existe" });
    return;
  }
  let d = null;
  if (r && r.ok) {
    try { d = await r.json(); } catch (_) { d = null; }
  }
  if (!d) {
    /* "Não olhei" não é "venceu". */
    pintarAutorizar({ estado: "erro_rede" });
    return;
  }
  AUTORIZAR.dados = d;
  AUTORIZAR.fim = Date.now() + Math.max(0, d.minutos || 0) * 60000;
  pintarAutorizar(d);
}

/* Repintar do minuto: só o prazo anda (sem rede); repintar o bloco tiraria o
   foco do botão. */
function andarOPrazoDoPedido() {
  if (!AUTORIZAR.prazo || !AUTORIZAR.fim) return;
  const falta = Math.floor((AUTORIZAR.fim - Date.now()) / 60000);
  AUTORIZAR.prazo.textContent = "Vale por " + prazoEmPalavras(falta) + ".";
}

async function autorizarPedido() {
  const d = AUTORIZAR.dados;
  if (!d || AUTORIZAR.fase === "enviando") return;
  pintarAutorizar(Object.assign({}, d, { estado: "enviando" }));
  let r = null;
  try { r = await escrever("/api/pedido/autorizar", { codigo: d.codigo }); }
  catch (_) { r = null; }
  if (r && r.ok) {
    pintarAutorizar({ estado: "sucesso" });
    esperarMaquinaNova($("#espera-maquina"), 10);
    return;
  }
  if (r && r.status === 404) {
    pintarAutorizar({ estado: "nao_existe" });
    return;
  }
  /* Página velha: a faixa do alto explica, e aqui o botão só volta a ficar
     ativo — sem repetir o erro com outra frase. */
  const velha = PAGINA_VELHA && r && r.status === 403;
  pintarAutorizar(Object.assign({}, d, { estado: velha ? "esperando" : "erro_autorizar" }));
}

function fecharAutorizar() {
  AUTORIZAR.codigo = "";
  AUTORIZAR.dados = null;
  AUTORIZAR.fase = "";
  AUTORIZAR.focou = false;
  $("#conectar-autorizar").hidden = true;
  /* `replaceState` não dispara `hashchange`: a tela não se repinta. */
  history.replaceState(null, "", "#/conectar");
  $("#pc-titulo").focus();
}

/* Quem decide o que o bloco mostra é o endereço. Chamada a cada abertura da
   tela, inclusive no repintar de um minuto: o código igual não recomeça do
   "Conferindo…". */
function abrirOuFecharAutorizar(bruto) {
  if (!bruto) {
    $("#conectar-autorizar").hidden = true;
    AUTORIZAR.codigo = "";
    AUTORIZAR.dados = null;
    AUTORIZAR.fase = "";
    AUTORIZAR.focou = false;
    return;
  }
  const codigo = codigoDeAutorizar(bruto);
  if (!codigo) {
    AUTORIZAR.codigo = "";
    pintarAutorizar({ estado: "nao_existe" });
    return;
  }
  if (codigo !== AUTORIZAR.codigo) {
    AUTORIZAR.codigo = codigo;
    AUTORIZAR.dados = null;
    AUTORIZAR.focou = false;
    olharOPedido(codigo);
    return;
  }
  if (AUTORIZAR.fase === "sucesso" || AUTORIZAR.fase === "enviando") return;
  andarOPrazoDoPedido();
}

/* Quando o computador deu a primeira medição, o bloco se recolhe e o foco vai
   para o cartão do computador, onde agora está "Conectado — achei N projetos". */
function recolherAutorizar() {
  if (AUTORIZAR.fase !== "sucesso") return;
  fecharAutorizar();
}

/* ------------------------------------------------- a espera da máquina nova
   O terceiro dos três acertos que o Tailscale, o runner de verificação e o
   Netdata têm e o DERVS não tinha: CONFIRMAÇÃO IMEDIATA de que o aparelho
   apareceu. Os outros dois — um passo só, e número de curta duração gerado
   pelo painel — já estavam de pé.

   NENHUMA ROTA NOVA. `/api/maquinas` já existe, já exige sessão e já é
   consumida por `carregarComputadores()`. Reusá-la é o que permite esta parte
   existir sem tocar no servidor.

   TRÊS ESTADOS, e o terceiro é de primeira classe:
     apareceu · ainda não apareceu, com o relógio correndo · NÃO DEU PARA
     CONFERIR, quando a consulta falhou. O terceiro nunca se pinta como o
     segundo: "ainda não" é uma afirmação sobre a máquina, "não deu" é uma
     afirmação sobre a consulta.

   E APARECER NÃO É ESTAR NA LISTA. A máquina só apareceu quando ela tem
   `visto_em`: parear sem relatório deixa uma linha na tabela que nunca deu
   notícia, e chamar isso de conectado é o painel mentindo. */

/* Os enderecos de producao gravados por esta conta, e o carimbo de quando
   foram lidos. Vazio NAO e a mesma coisa que "nao li": por isso o carimbo mora
   ao lado, e a porta 3 se pinta de "nao deu para conferir" enquanto ele nao
   existe. */
/* A instalacao do GitHub desta conta, e o carimbo de quando foi lida. `null`
   e "nao li"; string vazia e "li, e nao ha". Sao coisas diferentes. */
let GITHUB = null;
let GITHUB_LIDO_EM = "";

/* SERVIDORES MULTIPLOS (etapa 7): `ENDERECOS` deixou de ser um dicionario
   {projeto: url} — `/api/enderecos` agora devolve a LISTA chata que
   `banco.enderecos_por_servidor` monta, um item por (servidor, projeto). Quem
   quer os enderecos de um servidor filtra por `servidor_id`. */
let ENDERECOS = null;
let ENDERECOS_LIDO_EM = "";

/* Os servidores cadastrados por esta conta, e o carimbo de quando foram
   lidos. `null` e "nao li"; lista vazia e "li, e nao ha nenhum" — as duas
   coisas nao se confundem, a mesma lei 2 de sempre. */
let SERVIDORES = null;
let SERVIDORES_LIDO_EM = "";

/* O resultado da ultima medicao feita pela tela, por (servidor, projeto). A
   chave carrega o servidor porque o MESMO projeto pode ter endereco em mais
   de um servidor ao mesmo tempo — sem o servidor na chave, medir o endereco
   de um sobrescreveria a medicao do outro. Ele NAO vem da leitura:
   `/api/enderecos` diz o que esta gravado, e nao se responde. */
let MEDIDAS = {};
function chaveDaMedida(servidorId, projeto) { return servidorId + "|" + projeto; }

/* SERVIDORES MULTIPLOS (etapa 9): a sugestao de autodeteccao. `pintarConectar`
   e chamada por `olharOsEnderecos`, `olharOsComputadores` E `olharOsServidores`
   — tres disparos por abertura de tela — e cada chamada a `/api/servidores/
   sugerir` custa ate 68s de thread no servidor (ate 3 medicoes de ~22,5s).
   `SERVIDORES_JA_SUGERIDOS` guarda os `servidor_id` ja pedidos NESTA SESSAO:
   sem ele, cada repintura dispararia a mesma medicao de novo. */
const SERVIDORES_JA_SUGERIDOS = new Set();
let SUGESTOES = {};             /* servidor_id -> lista de {projeto, url} */
const SUGESTOES_IGNORADAS = new Set();   /* "servidorId:projeto", nesta sessao */

const ESPERA = {
  t: null,           /* o relógio da sondagem */
  ate: 0,            /* quando o pedido vence, em ms */
  antes: null,       /* os ids que já existiam quando a espera começou; null = ainda não li */
  relatoAntes: 0,    /* o relato mais novo que já existia quando ela começou, em ms */
  onde: null,        /* o elemento que ela pinta */
  caixa: "",         /* o id desse elemento, para reencontrá-lo */
  tela: "",          /* a tela em que ela nasceu */
  modo: "arquivo",   /* "arquivo" (baixou o arquivo) ou "numero" (colou o comando) */
  apareceu: false,   /* o computador já apareceu na lista */
  ultimo: null       /* o último estado pintado, para repintar igual */
};

function pararDeEsperar() {
  clearInterval(ESPERA.t);
  ESPERA.t = null;
  ESPERA.onde = null;
  ESPERA.ultimo = null;
  ESPERA.tela = "";
  ESPERA.apareceu = false;
}

/* O relato mais recente que a lista conhece, em ms (0 = nenhum). */
function maiorRelato(lista) {
  let maior = 0;
  for (const m of (lista || [])) {
    const t = Date.parse(m.relatado_em);
    if (t > maior) maior = t;
  }
  return maior;
}

/* O que a espera enxerga na lista: "esperando", "apareceu" (a linha existe e
   ainda não mandou a primeira medição) ou "medido". Dá "medido" também quando
   um computador que JÁ estava ligado manda uma medição mais nova que a de antes
   — é o caso de quem abre o arquivo de novo num PC já conectado. Compara com o
   relato de ANTES, e não com o relógio deste navegador: o carimbo é do
   servidor, e os dois relógios não precisam concordar. Função pura. */
function situacaoDaEspera(lista, antes, relatoAntes) {
  const l = lista || [];
  if (l.some(m => Date.parse(m.relatado_em) > relatoAntes)) return "medido";
  if (l.some(m => m.visto_em && !antes.has(m.id))) return "apareceu";
  return "esperando";
}

/* A TELA SE REPINTA SOZINHA A CADA MINUTO, e o repintar jogava fora o elemento
   em que a espera escrevia — a confirmação que a pessoa está justamente
   esperando sumia da tela sem aviso, e a espera continuava girando contra um
   elemento órfão. Conferido clicando, não lendo: a contagem subia de 2 para 3
   e o bloco desaparecia.

   Agora a espera se reencontra pelo id, e repinta o último estado. Quem a
   encerra é a saída da tela, e só ela. */
function reencontrarEspera() {
  if (!ESPERA.t || rota().tela !== ESPERA.tela) return;
  const caixa = document.getElementById(ESPERA.caixa);
  if (!caixa) return;
  ESPERA.onde = caixa;
  if (ESPERA.ultimo) pintarEspera(ESPERA.ultimo);
}

function esperarMaquinaNova(onde, minutos, modo) {
  pararDeEsperar();
  if (!onde) return;
  ESPERA.onde = onde;
  ESPERA.caixa = onde.id;
  ESPERA.tela = rota().tela;
  ESPERA.modo = modo || "arquivo";
  ESPERA.ate = Date.now() + Math.max(1, minutos || 10) * 60000;
  /* Sem a lista lida, a foto de "antes" ainda não existe: a primeira leitura
     da sondagem a tira. Sem isso todo computador antigo pareceria novo. */
  ESPERA.antes = COMPUTADORES
    ? new Set(COMPUTADORES.filter(m => m.visto_em).map(m => m.id)) : null;
  ESPERA.relatoAntes = maiorRelato(COMPUTADORES);
  pintarEspera({ estado: "esperando" });
  ESPERA.t = setInterval(sondarMaquinaNova, 5000);
  sondarMaquinaNova();
}

async function sondarMaquinaNova() {
  /* A sondagem PARA quando o pedido vence ou quando a tela sai. Relógio
     girando para sempre numa aba esquecida é pedido de graça para o servidor,
     e ninguém está lendo o resultado. */
  if (rota().tela !== ESPERA.tela) return pararDeEsperar();
  if (!ESPERA.onde || !ESPERA.onde.isConnected) reencontrarEspera();
  if (!ESPERA.onde) return;
  if (Date.now() > ESPERA.ate) {
    /* Se o computador apareceu e ainda não mediu, "venceu e ninguém apareceu"
       seria falso: o cartão já diz o que está acontecendo. */
    if (!ESPERA.apareceu) pintarEspera({ estado: "vencido" });
    return pararDeEsperar();
  }
  let d;
  try {
    const r = await fetch("/api/maquinas");
    if (!r.ok) throw new Error("recusado");
    d = await r.json();
  } catch {
    /* NÃO é "ainda não apareceu". É "não olhei". */
    pintarEspera({ estado: "sem_dados" });
    return;
  }
  COMPUTADORES = d.maquinas || [];
  COMPUTADORES_LIDO_EM = new Date().toISOString();
  if (ESPERA.antes === null) {
    ESPERA.antes = new Set(COMPUTADORES.filter(m => m.visto_em).map(m => m.id));
    ESPERA.relatoAntes = maiorRelato(COMPUTADORES);
    pintarEsteComputador();
    pintarEspera({ estado: "esperando" });
    return;
  }
  const s = situacaoDaEspera(COMPUTADORES, ESPERA.antes, ESPERA.relatoAntes);
  pintarEsteComputador();
  if (s === "medido") {
    pintarEspera({ estado: "medido" });
    pararDeEsperar();
    recolherAutorizar();
    return;
  }
  if (s === "apareceu") {
    /* A espera NÃO para no primeiro sim, e este foi um número errado com cara
       de certo, pego clicando: a máquina nasce no pareamento e a primeira
       medição chega alguns segundos depois. Quem parasse aqui escreveria "com
       0 projetos" para uma máquina que tinha acabado de mandar três. O cartão
       diz "ainda não mandou a primeira medição" até ela chegar. */
    ESPERA.apareceu = true;
    pintarEspera({ estado: "apareceu" });
    return;
  }
  pintarEspera({ estado: "esperando" });
}

function pintarEspera({ estado }) {
  const onde = ESPERA.onde;
  if (!onde) return;
  /* Guardado para o repintar da tela — ver `reencontrarEspera`. */
  ESPERA.ultimo = { estado };
  onde.textContent = "";
  onde.dataset.estado = estado;

  /* O computador apareceu: quem fala dele, daqui em diante, é o cartão. */
  if (estado === "apareceu" || estado === "medido") return;

  const linha = document.createElement("p");
  linha.className = "espera__linha";

  if (estado === "sem_dados") {
    linha.append(marcaDaPorta("sem_dados"));
    const txt = document.createElement("span");
    txt.textContent = "Não consegui perguntar ao painel agora. Isso não quer "
                    + "dizer que o computador não apareceu — quer dizer que "
                    + "não olhei. Vou tentar de novo em segundos.";
    linha.append(txt);
    onde.append(linha);
    return;
  }

  if (estado === "vencido") {
    linha.append(marcaDaPorta("desconectado"));
    const txt = document.createElement("span");
    txt.textContent = ESPERA.modo === "numero"
      ? "O número venceu e nenhum computador apareceu. Gere outro e tente de novo."
      : "O pedido venceu e nenhum computador apareceu. Baixe o arquivo de novo.";
    linha.append(txt);
    onde.append(linha);
    if (ESPERA.modo !== "numero") {
      const acoes = criar("div", "acoes");
      acoes.append(linkDeBaixar("Baixar de novo", false));
      onde.append(acoes);
    }
    return;
  }

  const ponto = document.createElement("span");
  ponto.className = "freio__ponto";
  ponto.setAttribute("aria-hidden", "true");
  linha.append(ponto);
  const txt = document.createElement("span");
  const faltam = Math.max(0, Math.round((ESPERA.ate - Date.now()) / 60000));
  txt.textContent = "Esperando o computador dar a primeira notícia. "
                  + (ESPERA.modo === "numero" ? "O número" : "O pedido")
                  + " vale por " + prazoEmPalavras(faltam) + ".";
  linha.append(txt);
  onde.setAttribute("aria-live", "polite");
  onde.append(linha);
}

/* Perguntar `/api/maquinas` sem depender da tela de Computadores estar
   aberta. `carregarComputadores()` nao serve aqui: ela pinta a lista e o
   carimbo daquela outra tela, e chama-la daqui escreveria numa tela que
   ninguem esta vendo. */
async function olharOGithub() {
  try {
    const r = await fetch("/api/github");
    if (!r.ok) throw new Error("recusado");
    GITHUB = await r.json();
    GITHUB_LIDO_EM = new Date().toISOString();
  } catch {
    return;                 /* sem carimbo: o cartão dirá que não olhou */
  }
  if (rota().tela === "conectar") {
    pintarConectar();
    procurarContasUmaVez();
  }
}

async function ligarOGithub() {
  const r = await escrever("/api/github/instalar");
  if (!r.ok) {
    recado("não conseguimos abrir o GitHub agora. Tente de novo.", true);
    return;
  }
  const d = await r.json();
  /* Salto de página inteiro, e não uma aba nova: a volta do GitHub cai numa
     rota nossa que precisa do cookie da cortina, e aba nova aberta por script
     é o que os navegadores bloqueiam primeiro. */
  location.href = d.url;
}

/* A PROCURA É SOZINHA. Não há botão de procurar: o servidor
   pergunta ao GitHub quais instalações do aplicativo existem e liga as que são
   desta conta, uma vez por carga da tela (a volta do GitHub com `?github=` é
   uma carga). Quem instalou direto no GitHub e nunca voltou aqui vê a conta
   aparecer sozinha.

   Procura que NÃO achou nada não escreve nada: silêncio não é erro nem
   sucesso. Um 429 também fica calado — é o nosso automatismo batendo no
   próprio teto, e a pessoa não fez nada de errado. */
let PROCUROU_GITHUB = false;
let GITHUB_PROCURA = { fase: "", achou: "" };   /* fase: "" | "procurando" | "erro" */

function procurarContasUmaVez() {
  if (PROCUROU_GITHUB || !GITHUB || !GITHUB.da_para_instalar) return;
  procurarContasDoGithub();
}

function repintarGithub() {
  if (rota().tela === "conectar") pintarConectar();
}

async function procurarContasDoGithub() {
  PROCUROU_GITHUB = true;
  GITHUB_PROCURA = { fase: "procurando", achou: "" };
  repintarGithub();
  const antes = new Set(((GITHUB && GITHUB.instalacoes) || []).map(c => c.conta_login));
  let r = null;
  try { r = await escrever("/api/github/procurar"); } catch (_) { r = null; }
  /* 429: calado. 403 de página velha: a faixa do alto explica, o cartão não
     repete. */
  if (r && (r.status === 429 || (r.status === 403 && PAGINA_VELHA))) {
    GITHUB_PROCURA = { fase: "", achou: "" };
    repintarGithub();
    return;
  }
  let d = null;
  if (r && r.ok) {
    try { d = await r.json(); } catch (_) { d = null; }
  }
  if (!d || !d.ok) {
    GITHUB_PROCURA = { fase: "erro", achou: "" };
    repintarGithub();
    return;
  }
  await olharOGithub();
  const novas = ((GITHUB && GITHUB.instalacoes) || [])
    .filter(c => c.conta_login && !antes.has(c.conta_login))
    .map(c => c.conta_login);
  GITHUB_PROCURA = {
    fase: "",
    achou: !novas.length ? ""
      : novas.length === 1 ? "Achei e liguei a conta " + novas[0] + "."
      : "Achei e liguei as contas " + novas.join(", ") + "."
  };
  repintarGithub();
}

async function olharOsEnderecos() {
  try {
    const r = await fetch("/api/enderecos");
    if (!r.ok) throw new Error("recusado");
    const d = await r.json();
    ENDERECOS = d.enderecos || [];
    ENDERECOS_LIDO_EM = new Date().toISOString();
  } catch {
    return;                 /* sem carimbo: a porta 3 dirá que não olhou */
  }
  if (rota().tela === "conectar") pintarConectar();
}

/* Molde exato de `olharOsEnderecos()`: o `catch` VOLTA SEM CARIMBO, porque é
   o carimbo ausente que faz o selo "Seus servidores" dizer "não olhei" em
   vez de "nenhum servidor cadastrado". */
async function olharOsServidores() {
  try {
    const r = await fetch("/api/servidores");
    if (!r.ok) throw new Error("recusado");
    const d = await r.json();
    SERVIDORES = d.servidores || [];
    SERVIDORES_LIDO_EM = new Date().toISOString();
  } catch {
    return;                 /* sem carimbo: a porta 3 dirá que não olhou */
  }
  if (rota().tela === "conectar") pintarConectar();
}

async function guardarServidor(nome, padrao) {
  const r = await escrever("/api/servidores/guardar",
                           { nome, padrao_subdominio: padrao });
  let d = {};
  try { d = await r.json(); } catch { d = {}; }
  if (!r.ok) {
    recado(d.erro || "não conseguimos cadastrar esse servidor.", true);
    return;
  }
  recado("servidor cadastrado.");
  await olharOsServidores();
  if (rota().tela === "conectar") pintarConectar();
}

/* Pede a sugestao de autodeteccao PARA AQUELE SERVIDOR — uma vez por sessao,
   garantido por `SERVIDORES_JA_SUGERIDOS` (o `Set` e marcado ANTES do
   `await`, entao duas chamadas de `blocoDeServidor` no mesmo repinte nunca
   disparam a mesma medicao duas vezes). Nao grava nada: so propoe. */
async function pedirSugestao(servidorId) {
  SERVIDORES_JA_SUGERIDOS.add(servidorId);
  try {
    const r = await escrever("/api/servidores/sugerir", { servidor_id: servidorId });
    if (!r.ok) return;
    const d = await r.json();
    SUGESTOES[servidorId] = d.sugestoes || [];
  } catch {
    return;
  }
  if (rota().tela === "conectar") pintarConectar();
}

async function apagarServidor(id) {
  const r = await escrever("/api/servidores/remover", { id });
  if (!r.ok) { recado("não conseguimos apagar esse servidor.", true); return; }
  recado("servidor apagado. Os endereços gravados nele saem do DERVS.");
  await olharOsServidores();
  await olharOsEnderecos();
  if (rota().tela === "conectar") pintarConectar();
}

async function guardarEndereco(servidorId, projeto, url) {
  const r = await escrever("/api/enderecos/guardar",
                           { servidor_id: servidorId, projeto, url });
  let d = {};
  try { d = await r.json(); } catch { d = {}; }
  if (!r.ok) {
    /* A RECUSA DA PENEIRA NÃO É UM DEFEITO, e a tela não a pinta como um:
       endereço interno recusado é o comportamento certo, e a frase que o
       servidor manda já explica por quê, em português. */
    recado(d.erro || "não conseguimos guardar esse endereço.", true);
    return;
  }
  const chave = chaveDaMedida(servidorId, projeto);
  if (!url) {
    delete MEDIDAS[chave];
    recado("endereço apagado. Esse projeto volta a não ter site medido.");
  } else {
    MEDIDAS[chave] = { ok: d.ok, codigo: d.codigo, erro: d.erro,
                       medido_em: d.medido_em };
    recado("endereço guardado.");
  }
  await olharOsEnderecos();
  if (rota().tela === "conectar") pintarConectar();
}

/* A PORTA 1 NÃO PODE DIZER "conectado" SÓ PORQUE HÁ LINHAS NA LISTA.
   Em 29/09/2026 a tela mostrava "[OK] conectado" para dois computadores que
   não davam notícia havia 26 dias — o painel inteiro "sem dados" e a porta
   verde. Uma máquina calada não é uma máquina conectada: quem manda é o
   `visto_em` MAIS RECENTE da lista, e o limite é largo de propósito (o agente
   manda a cada 10 min no máximo; duas horas de silêncio já é queda, não
   atraso). Função pura, sem DOM: `test_menu.py` a executa de verdade. */
const COMPUTADOR_CALADO_APOS_MS = 2 * 60 * 60 * 1000;
function estadoDosComputadores(lista, agoraMs) {
  const n = lista ? lista.length : 0;
  if (!n) return { estado: "desconectado", vistoEm: "", calado: false };
  const tempos = lista.map(m => Date.parse(m.visto_em)).filter(t => !isNaN(t));
  if (!tempos.length) {
    return { estado: "desconectado", vistoEm: "", calado: true };
  }
  const ultimo = Math.max(...tempos);
  const calado = agoraMs - ultimo > COMPUTADOR_CALADO_APOS_MS;
  return { estado: calado ? "desconectado" : "conectado",
           vistoEm: new Date(ultimo).toISOString(), calado };
}

/* O que o cartão "Este computador" diz, a partir da lista. Função pura, sem
   DOM: `test_conectar_tela.py` a executa de verdade.

   Seis situações, e a ordem importa:
     vazio         olhou e não há nenhum computador;
     mudo          há, mas nenhum deu notícia há mais de duas horas — "não deu
                   para conferir", e nada é apagado;
     pendente      apareceu e AINDA NÃO mandou a primeira medição — nunca "0";
     zero          mediu, olhou a pasta e não achou nenhum projeto;
     com_projetos  mediu e achou.
   "0 projetos" só existe depois de uma medição que olhou e não achou. */
function situacaoDoComputador(lista, agoraMs) {
  if (!lista || !lista.length) return { tipo: "vazio", estado: "desconectado" };
  const vida = estadoDosComputadores(lista, agoraMs);
  let recente = lista[0];
  for (const m of lista) {
    if (Date.parse(m.visto_em) > Date.parse(recente.visto_em) || !recente.visto_em) recente = m;
  }
  if (vida.calado) {
    return { tipo: "mudo", estado: "sem_dados", nome: recente.nome,
             vistoEm: recente.visto_em };
  }
  const medidos = lista.filter(m => m.relatado_em);
  if (!medidos.length) {
    return { tipo: "pendente", estado: "conectado", nome: recente.nome,
             vistoEm: recente.visto_em };
  }
  let total = 0;
  for (const m of medidos) total += m.projetos || 0;
  return { tipo: total > 0 ? "com_projetos" : "zero", estado: "conectado",
           projetos: total, nome: recente.nome, vistoEm: recente.visto_em };
}

/* Preenche os vãos do cartão "Este computador" (o esqueleto está no
   index.html, e por isso a espera e o resto sobrevivem ao repintar). */
function pintarEsteComputador() {
  const leu = !!COMPUTADORES_LIDO_EM;
  const lista = COMPUTADORES || [];
  let estado = "sem_dados", rotulo = "", resumo = "", carimbo = "";
  let baixarDeNovo = false, tentarDeNovo = false;
  const s = leu ? situacaoDoComputador(lista, Date.now()) : null;

  if (!leu && COMPUTADORES_FALHOU) {
    resumo = "Não consegui ler os computadores desta conta. Isso não quer dizer "
           + "que nenhum esteja ligado — quer dizer que não olhei.";
    tentarDeNovo = true;
  } else if (!leu) {
    resumo = "Olhando os computadores desta conta…";
  } else if (s.tipo === "vazio") {
    estado = "desconectado";
    resumo = "Nenhum computador está ligado ao DERVS ainda. Sem um, o painel só "
           + "enxerga o que está no GitHub.";
  } else if (s.tipo === "mudo") {
    const quando = haQuanto(s.vistoEm);
    resumo = "O " + (s.nome || "computador") + " não dá notícia "
           + (quando.startsWith("em ") ? "desde " + quando.slice(3) : quando)
           + ". Os projetos dele continuam no painel, parados no último "
           + "carimbo. Veja se o computador está ligado.";
  } else {
    estado = "conectado";
    carimbo = (s.nome || "O computador") + " deu notícia " + haQuanto(s.vistoEm) + ".";
    if (s.tipo === "pendente") {
      resumo = "O computador apareceu e ainda não mandou a primeira medição. "
             + "Isso leva menos de um minuto.";
    } else if (s.tipo === "zero") {
      resumo = "Olhei a pasta que você escolheu e não achei nenhum projeto com "
             + "histórico de versões. Para escolher outra pasta, baixe o "
             + "arquivo de novo e abra.";
      baixarDeNovo = true;
    } else {
      rotulo = "Conectado — achei " + s.projetos
             + (s.projetos === 1 ? " projeto" : " projetos");
    }
  }

  $("#cartao-computador").setAttribute("aria-busy", leu || COMPUTADORES_FALHOU ? "false" : "true");
  $("#pc-marca").replaceChildren(marcaDaPorta(estado, rotulo));
  $("#pc-resumo").textContent = resumo;
  $("#pc-resumo").hidden = !resumo;
  $("#pc-carimbo").textContent = carimbo;

  /* O botão principal é o próximo passo. Com computador ligado ele continua
     existindo (conectar mais um), mas recua: o principal passa a ser a lista. */
  const temComputador = leu && s.tipo !== "vazio";
  const botoes = [];
  if (baixarDeNovo) botoes.push(linkDeBaixar("Baixar de novo", false));
  else botoes.push(temComputador
    ? linkDeBaixar("Conectar outro computador", true)
    : linkDeBaixar("Conectar este computador", false));
  if (tentarDeNovo) {
    const b = criar("button", "botao botao--secundario", "Tentar de novo");
    b.type = "button";
    b.addEventListener("click", () => {
      COMPUTADORES_FALHOU = false;
      pintarEsteComputador();
      carregarComputadores();
    });
    botoes.push(b);
  }
  $("#pc-acoes").replaceChildren(...botoes);

  const nenhum = !lista.length;
  $("#pc-lista").hidden = nenhum;
  $("#lista-computadores").replaceChildren(...lista.map(linhaDeComputador));
  if (leu) {
    $("#computadores-carimbo").textContent = "lido " + haQuanto(COMPUTADORES_LIDO_EM);
  }
}

/* ---------------------------------------- a chave "Mostrar no painel"
   Uma linha de projeto com a chave. Serve à lista dos achados de um
   computador E à lista de repositórios de uma conta do GitHub: uma montagem só,
   porque duas divergem, e a que divergir é a que esquece o rótulo escrito.

   A chave NUNCA muda de posição por conta própria: ela vai para onde o servidor
   disse que foi. Enquanto o pedido viaja ela fica desligada para o clique; se
   o servidor recusa, volta para onde estava e a linha diz isso. O foco fica na
   chave nos dois casos. Esconder não apaga nada: a linha continua na lista, em
   cinza, porque sem ela não haveria como voltar. */
function linhaComChave(projeto, caminho, oculto, aoMudar) {
  const li = criar("li", "visto" + (oculto ? " visto--oculto" : ""));
  const dizeres = criar("div", "dizeres");
  dizeres.append(criar("div", "nome", projeto));
  if (caminho) dizeres.append(criar("div", "caminho", caminho));
  const erro = criar("p", "mole");
  erro.setAttribute("role", "status");
  erro.hidden = true;
  dizeres.append(erro);

  const rotulo = criar("label", "chave");
  const entrada = document.createElement("input");
  entrada.type = "checkbox";
  entrada.setAttribute("role", "switch");
  entrada.setAttribute("aria-label", "Mostrar no painel: " + projeto);
  entrada.checked = !oculto;
  const trilho = criar("span", "chave__trilho");
  trilho.setAttribute("aria-hidden", "true");
  const texto = criar("span", "chave__texto", oculto ? "Escondido do painel" : "Aparece no painel");
  rotulo.append(entrada, trilho, texto);

  entrada.addEventListener("change", async () => {
    const quer = entrada.checked;
    entrada.disabled = true;
    entrada.setAttribute("aria-busy", "true");
    erro.hidden = true;
    let ok = false;
    try {
      const r = await escrever("/api/projetos/mostrar", { projeto, mostrar: quer });
      ok = r.ok;
    } catch (_) { ok = false; }
    entrada.disabled = false;
    entrada.removeAttribute("aria-busy");
    if (ok) {
      texto.textContent = quer ? "Aparece no painel" : "Escondido do painel";
      li.className = "visto" + (quer ? "" : " visto--oculto");
      if (aoMudar) aoMudar(!quer);
      await carregar();
    } else {
      entrada.checked = !quer;
      erro.textContent = "Não consegui mudar agora. A chave voltou para onde estava.";
      erro.hidden = false;
    }
    entrada.focus();
  });

  li.append(dizeres, rotulo);
  return li;
}

/* Um projeto achado num computador (`projetos_vistos` de /api/maquinas). */
function linhaDeProjetoVisto(a) {
  return linhaComChave(a.projeto, a.caminho, a.oculto, (v) => { a.oculto = v; });
}

/* O bloco "Projetos que achei neste computador", dentro da linha dele. Mais de
   20: a lista rola dentro de uma caixa (com foco e nome), para o cartão não
   empurrar os outros dois para fora da tela. */
function blocoDeProjetosVistos(m) {
  const vistos = m.projetos_vistos || [];
  if (!vistos.length) return null;
  const bloco = criar("div", "projetos-vistos");
  bloco.append(criar("h4", "", "Projetos que achei neste computador"));
  bloco.append(criar("p", "mole",
    "Esconder um projeto tira ele do painel, mas não apaga nada. Ele continua "
    + "aqui na lista e volta quando você ligar a chave. A escolha vale só para "
    + "a sua conta."));
  const ul = criar("ul", "lista");
  for (const a of vistos) ul.append(linhaDeProjetoVisto(a));
  const muitos = vistos.length > 20;
  if (muitos) {
    ul.className = "lista lista--rolavel";
    ul.setAttribute("tabindex", "0");
    ul.setAttribute("aria-label", "Projetos que achei neste computador");
  }
  bloco.append(ul);
  return bloco;
}

/* Uma linha da lista de computadores. Nome, quando deu notícia e o que ele
   pode fazer. Tudo que é do outro computador entra por `textContent`. */
function linhaDeComputador(m) {
  const li = document.createElement("li");
  const txt = criar("div", "dizeres");
  txt.append(criar("div", "nome", m.nome || "computador sem nome"));

  const meta = criar("div", "carimbo");
  /* "Mandou a primeira medição" é `relatado_em`; `visto_em` já existe desde o
     pareamento. Sem a diferença, "17 projetos" apareceria para quem nunca mediu. */
  meta.textContent = !m.visto_em ? "nunca deu notícia"
    : m.relatado_em
      ? "deu notícia " + haQuanto(m.visto_em) + " · " + m.projetos
        + (m.projetos === 1 ? " projeto" : " projetos")
      : "ligou " + haQuanto(m.visto_em) + " · ainda não mandou a primeira medição";
  txt.append(meta);

  /* A AUTORIZAÇÃO PARA TRABALHAR é separada de estar conectado. Parear nunca
     deu o direito de rodar código; a coluna do banco nasce desligada.

     Etiqueta, e não `.carimbo`: em 29/08/2026 este era o fato mais grave da
     linha escrito no mesmo cinza mudo do horário. */
  const trabalha = criar("div", "permissao");
  trabalha.dataset.permissao = m.executa ? "executa" : "mede";
  trabalha.textContent = m.executa ? "Pode consertar aqui" : "Só mede";
  txt.append(trabalha);

  const acoes = criar("div", "acoes");
  if (m.so_mede) {
    /* Ligado pelo arquivo: o programa dele não leva o braço que executa, e o
       servidor recusaria. Botão que o servidor sempre recusa é botão que mente. */
    txt.append(criar("p", "mole",
      "Este computador só acompanha os projetos. Ele não faz alterações."));
  } else {
    const aut = criar("button", "botao botao--secundario",
                      m.executa ? "Deixar só medindo" : "Deixar consertar aqui");
    aut.type = "button";
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
    acoes.append(aut);
  }

  /* `botao--remover` é só o freio visual: ver o porquê em painel.css. */
  const b = criar("button", "botao botao--secundario botao--remover", "Remover");
  b.type = "button";
  b.addEventListener("click", () => confirmar({
    titulo: "Desconectar “" + (m.nome || "este computador") + "”?",
    texto: "Ele para de acompanhar na hora, e só volta se você baixar o "
         + "arquivo de novo e abrir. As medições que ele já mandou não são "
         + "apagadas, e os projetos dele continuam no painel — parados no "
         + "último carimbo.",
    sim: "Desconectar", nao: "Manter conectado"
  }, () => removerComputador(m.id)));
  acoes.append(b);

  li.append(txt, acoes);
  const vistos = blocoDeProjetosVistos(m);
  if (vistos) li.append(vistos);
  return li;
}


/* Os <details> que o repintar do minuto não pode fechar: a escolha da pessoa
   vive aqui, e não no elemento (que é recriado). */
const DETALHES_ABERTOS = new Set();
function detalhes(chave, resumo) {
  const d = criar("details", "ajuda");
  d.open = DETALHES_ABERTOS.has(chave);
  d.append(criar("summary", "", resumo));
  d.addEventListener("toggle", () => {
    if (d.open) DETALHES_ABERTOS.add(chave); else DETALHES_ABERTOS.delete(chave);
  });
  return d;
}

/* A cabeça de um cartão de ligação: título e a marca de estado, uma montagem só
   (duas divergem, e a que divergir é a que esquece o rótulo escrito). */
function cartaoDeLigacao(titulo, estado, rotulo) {
  const cartao = criar("div", "cartao porta");
  const cabeca = criar("div", "porta__cabeca");
  cabeca.append(criar("h2", "", titulo), marcaDaPorta(estado, rotulo));
  cartao.append(cabeca);
  return cartao;
}

/* Um repositório da lista de uma conta. É um projeto que o painel já conhece,
   por isso tem a mesma chave "Mostrar no painel" da lista do computador. */
function linhaDeRepositorio(r) {
  return linhaComChave(r.projeto, (r.slug || "") + (r.medido ? "" : " · ainda não medido"),
                       r.oculto, (v) => { r.oculto = v; });
}

/* Uma conta do GitHub ligada. O nome e o tipo vêm do GitHub: texto, nunca
   HTML. O link para fora só nasce se o endereço for https do github.com. */
function linhaDeContaDoGithub(c) {
  const li = criar("li", "conta-gh");
  const topo = criar("div", "conta-gh__topo");
  topo.append(criar("strong", "nome", c.conta_login || "Conta ainda sem nome"));
  if (c.conta_login) {
    topo.append(criar("span", "carimbo", c.conta_tipo === "Organization" ? "organização" : "pessoal"));
  }
  li.append(topo);

  const medicao = criar("p", "carimbo");
  if (c.medidos === null || c.medidos === undefined) {
    medicao.append("ainda não mediu repositórios");
  } else {
    medicao.append("mede ", criar("span", "mono", String(c.medidos)),
                   c.medidos === 1 ? " repositório" : " repositórios",
                   " · mediu " + haQuanto(c.medido_em));
  }
  li.append(medicao);

  if (c.gerenciar_url && /^https:\/\/github\.com\//.test(c.gerenciar_url)) {
    const a = criar("a", "", "Escolher repositórios no GitHub");
    a.href = c.gerenciar_url;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    a.append(criar("span", "so-leitor", " (abre o GitHub em outra aba)"));
    li.append(a);
  }

  const repos = c.repositorios || [];
  if (repos.length) {
    const d = detalhes("gh:" + (c.conta_login || ""),
                       repos.length === 1 ? "Ver o repositório" : "Ver os " + repos.length + " repositórios");
    const ul = criar("ul", repos.length > 20 ? "lista lista--rolavel" : "lista");
    if (repos.length > 20) {
      ul.setAttribute("tabindex", "0");
      ul.setAttribute("aria-label", "Repositórios de " + (c.conta_login || "esta conta"));
    }
    for (const r of repos) ul.append(linhaDeRepositorio(r));
    d.append(ul);
    li.append(d);
  }
  return li;
}

/* O cartão "GitHub": o estado vem de `GITHUB` (a leitura de /api/github) e da
   procura sozinha. Quem não conseguiu ler vê "não olhei", nunca "nenhuma
   conta". */
function cartaoDoGithub() {
  const leu = !!GITHUB_LIDO_EM;
  const contas = leu ? (GITHUB.instalacoes || []) : [];
  const ligado = leu && (contas.length > 0 || !!GITHUB.instalacao);
  const voltou = new URLSearchParams(location.search).get("github");
  const erro = GITHUB_PROCURA.fase === "erro";

  let estado, resumo;
  if (!leu) {
    estado = "sem_dados";
    resumo = "Não consegui ler o estado desta conta. Isso não quer dizer que ela "
           + "não está conectada — quer dizer que não olhei.";
  } else if (ligado) {
    estado = "conectado";
    resumo = (contas.length === 1 ? "Conta ligada: 1. " : "Contas ligadas: " + contas.length + ". ")
           + "O DERVS traz sozinho os pedidos de alteração, a verificação "
           + "automática e os alertas de segurança dos repositórios que você "
           + "liberou em cada conta.";
  } else if (voltou === "nao-deu") {
    estado = "sem_dados";
    resumo = "Não deu para confirmar a conta. Se você fechou a página do GitHub "
           + "no meio, é isso mesmo e não é erro: é só tentar de novo. O DERVS "
           + "só liga a conta depois que o GitHub confirma.";
  } else {
    estado = "desconectado";
    resumo = "Nenhuma conta do GitHub ligada ainda. Ligada, ela traz sozinha os "
           + "pedidos de alteração, a verificação automática e os alertas de "
           + "segurança dos repositórios que você liberar.";
  }
  /* Procura que falhou: "não olhei" vale mais que "nenhuma conta". */
  if (erro) estado = "sem_dados";

  const cartao = cartaoDeLigacao("GitHub", estado);
  cartao.append(criar("p", "", resumo));
  if (leu) cartao.append(criar("p", "carimbo", "estado lido " + haQuanto(GITHUB_LIDO_EM)));

  /* Procurando / achou / erro: dentro de `.espera`, com `aria-live` posto junto
     com o primeiro texto — região viva que nasce vazia não anuncia nada. */
  const fala = criar("div", "espera");
  fala.setAttribute("aria-live", "polite");
  if (GITHUB_PROCURA.fase === "procurando") {
    fala.append(criar("p", "espera__linha", "Procurando suas contas no GitHub…"));
  } else if (erro) {
    fala.append(criar("p", "espera__linha",
      "Não consegui procurar suas contas agora. Isso não quer dizer que não há "
      + "— quer dizer que não olhei."));
  } else if (GITHUB_PROCURA.achou) {
    fala.append(criar("p", "espera__linha", GITHUB_PROCURA.achou));
  }
  cartao.append(fala);

  if (contas.length) {
    const ul = criar("ul", "lista");
    for (const c of contas) ul.append(linhaDeContaDoGithub(c));
    cartao.append(ul);
  }

  const acoes = criar("div", "acoes");
  if (leu && !GITHUB.da_para_instalar) {
    const b = criar("button", "botao", "Conectar conta do GitHub");
    b.type = "button";
    b.disabled = true;
    acoes.append(b);
    cartao.append(acoes);
    cartao.append(criar("p", "mole", "o aplicativo do GitHub ainda não foi registrado neste servidor"));
  } else {
    const b = criar("button", "botao", ligado ? "Conectar outra conta do GitHub" : "Conectar conta do GitHub");
    b.type = "button";
    b.addEventListener("click", ligarOGithub);
    acoes.append(b);
    /* "Tentar de novo" só existe no ESTADO DE ERRO da procura. */
    if (erro) {
      const t = criar("button", "botao botao--secundario", "Tentar de novo");
      t.type = "button";
      t.addEventListener("click", procurarContasDoGithub);
      acoes.append(t);
    }
    cartao.append(acoes);
  }
  cartao.append(criar("p", "mole",
    "Serve para conta pessoal e para organização. Você escolhe no GitHub quais "
    + "repositórios liberar e pode mudar depois. Nenhuma senha nem chave é "
    + "digitada aqui."));
  /* DESCONECTAR ACONTECE NO GITHUB, e a tela DIZ isso: esconder o corte seria
     mentir por omissão. */
  if (ligado) {
    cartao.append(criar("p", "mole",
      "Para desligar uma conta, remova o aplicativo no próprio GitHub, em "
      + "Configurações → Aplicativos. O DERVS não faz isso por aqui de propósito: "
      + "tirar o acesso é decisão de quem deu o acesso."));
  }
  return cartao;
}

/* "O que vai aparecer?" abre sozinho na PRIMEIRA visita e fica fechado nas
   seguintes. Lembrado só neste navegador (`localStorage`); sem armazenamento
   (modo privado, bloqueado) a tela nasce aberta, que é o lado seguro. */
let PASSOS_JA_DECIDIDOS = false;
function abrirPassosNaPrimeiraVisita() {
  if (PASSOS_JA_DECIDIDOS) return;
  PASSOS_JA_DECIDIDOS = true;
  let visto = false;
  try {
    visto = !!localStorage.getItem("dervs-conectar-visto");
    localStorage.setItem("dervs-conectar-visto", "1");
  } catch (_) { visto = false; }
  $("#o-que-vai-aparecer").open = !visto;
}

function pintarConectar() {
  abrirPassosNaPrimeiraVisita();
  const onde = $("#conectar-corpo");
  onde.textContent = "";

  /* PORTA 1 — o seu computador. O cartão tem esqueleto fixo no index.html e
     é preenchido por `pintarEsteComputador`: a espera e os vãos não se
     perdem quando a tela se repinta sozinha. */
  pintarEsteComputador();

  /* PORTA 2 — a conta do GitHub. */
  onde.append(cartaoDoGithub());

  /* PORTA 3 — os seus sites: o campo é fixo no HTML, o resto é daqui. */
  pintarSites();

  reencontrarEspera();
}

/* ================================================= Seus sites (tela E) ======
   Um campo só: cole o endereço, o DERVS CONFERE se ele responde (sem gravar) e
   só então a pessoa guarda. O campo é fixo no index.html — o painel.js só
   monta o que vem em volta. Cinco mentiras possíveis aqui, todas evitadas:

   - "fora do ar" onde a medição simplesmente não aconteceu: `ok: null` é o
     quarto estado, "não deu para conferir", e guarda sem afirmar nada;
   - o resultado do endereço ANTIGO ficar na tela com o endereço NOVO: digitar
     apaga o resultado, e uma resposta atrasada de outra conferência é jogada fora;
   - adivinhar o projeto ou o servidor errado: sem parecido, a escolha fica
     vazia e o botão espera;
   - gravar sem o clique: sugestão propõe e para;
   - texto de fora (erro do servidor remoto, nome do projeto) como HTML. */
const SITE = { seq: 0, timer: null, sugerido: "" };

/* O que a última medição sabe deste site: a feita agora por esta tela, ou a do
   coletor (a camada do projeto). `null` = ainda não medi. */
function medidaDoSite(e) {
  const m = MEDIDAS[chaveDaMedida(e.servidor_id, e.projeto)];
  if (m) return m;
  const p = ((ESTADO && ESTADO.projetos) || []).find(x => x.nome === e.projeto);
  const sites = p && (p.camadas || {}).github ? sitesDoProjeto(p.github) : null;
  const s = (sites || []).find(x => x.url === e.url);
  return s ? { ok: s.ok, codigo: s.codigo, erro: s.erro, medido_em: s.medido_em } : null;
}

/* O projeto cujo nome mais aparece no endereço (loja-da-ana.com.br -> loja-da-ana).
   Sem parecido, "" — nunca um palpite. Função pura. */
function projetoMaisParecido(url, nomes) {
  let host = "";
  try { host = new URL(url).hostname.toLowerCase().replace(/^www\./, ""); } catch (_) { return ""; }
  const limpo = (s) => String(s).toLowerCase().replace(/[^a-z0-9]/g, "");
  const alvo = limpo(host);
  let melhor = "", tamanho = 0;
  for (const nome of nomes) {
    const n = limpo(nome);
    if (n && alvo.includes(n) && n.length > tamanho) { melhor = nome; tamanho = n.length; }
  }
  return melhor;
}

/* As propostas: endereços que o projeto já declara (a camada do coletor, sem
   servidor) e as da autodetecção por padrão de subdomínio. Só PROPÕEM. */
function sugestoesDoSite() {
  const guardados = new Set((ENDERECOS || []).map(e => e.projeto + "|" + e.url));
  const vistas = new Set();
  const saida = [];
  const poe = (projeto, url) => {
    const chave = projeto + "|" + url;
    if (!projeto || !url || guardados.has(chave) || vistas.has(chave)) return;
    if (SUGESTOES_IGNORADAS.has(chave)) return;
    vistas.add(chave);
    saida.push({ projeto, url });
  };
  for (const p of ((ESTADO && ESTADO.projetos) || [])) {
    const sites = (p.camadas || {}).github ? sitesDoProjeto(p.github) : [];
    for (const s of (sites || [])) if (s.servidor_id === 0) poe(p.nome, s.url);
  }
  for (const id of Object.keys(SUGESTOES)) {
    for (const s of SUGESTOES[id]) poe(s.projeto, s.url);
  }
  return saida;
}

/* A sugestão propõe e PARA: "Usar este" só preenche o campo e confere; nada é
   gravado. Contorno `--borda-forte` — nunca cor de estado: é proposta, não
   veredito. */
function linhaDeSugestao(projeto, url) {
  const linha = criar("div", "sugestao");
  linha.append(criar("p", "", "Sugestão: " + projeto + " parece estar em " + url));
  const acoes = criar("div", "acoes");
  const usar = criar("button", "botao", "Usar este");
  usar.type = "button";
  usar.addEventListener("click", () => {
    $("#site-endereco").value = url;
    SITE.sugerido = projeto;
    conferirSite(url, false);
  });
  const ignorar = criar("button", "botao botao--secundario", "Ignorar");
  ignorar.type = "button";
  ignorar.addEventListener("click", () => {
    /* Só some desta sessão — nunca grava, nunca volta a perguntar sozinho. */
    SUGESTOES_IGNORADAS.add(projeto + "|" + url);
    pintarSites();
  });
  acoes.append(usar, ignorar);
  linha.append(acoes);
  return linha;
}

/* Por que o site não respondeu, em português. O texto exato do servidor remoto
   entra entre parênteses, por textContent. */
function motivoDoSite(r) {
  const erro = String(r.erro || "");
  let frase = "Não consegui falar com o site.";
  if (r.codigo >= 500) frase = "O site respondeu com erro do lado dele (código " + r.codigo + ").";
  else if (erro === "nao_resolveu") return "Não achei esse endereço. Confira se você digitou certo.";
  else if (/timeout/i.test(erro)) frase = "O site não respondeu em 10 segundos.";
  else if (/ssl|certificate/i.test(erro)) frase = "O certificado de segurança do site não é válido.";
  else if (/ConnectionRefused/i.test(erro)) frase = "O site recusou a conexão.";
  return erro ? frase + " (" + erro + ")" : frase;
}

/* "0,4 segundo", "2,3 segundos": abaixo de dois, singular. */
function segundosEmPalavras(ms) {
  if (typeof ms !== "number") return "";
  const s = ms / 1000;
  return " em " + s.toFixed(1).replace(".", ",") + (s < 2 ? " segundo" : " segundos");
}

/* Um campo com `<select>`. Sem escolha prévia: o primeiro item é o convite. */
function campoDeEscolha(id, rotulo, itens, escolhido, convite) {
  const campo = criar("div", "campo");
  const l = criar("label", "", rotulo);
  l.setAttribute("for", id);
  const sel = criar("select");
  sel.id = id;
  const vazio = criar("option", "", convite);
  vazio.value = "";
  sel.append(vazio);
  for (const [valor, nome] of itens) {
    const o = criar("option", "", nome);
    o.value = valor;
    sel.append(o);
  }
  sel.value = escolhido || "";
  campo.append(l, sel);
  return { campo, sel };
}

/* Por que ainda não dá para guardar (ou "" se dá). Texto à parte, sem montagem. */
function razaoDeNaoGuardar(nomes, servidores) {
  if (!nomes.length) {
    return "Ainda não há projetos no painel para ligar a este site. Conecte um computador primeiro.";
  }
  if (!servidores) {
    return "Não consegui ler os servidores agora. Isso não quer dizer que não há — quer dizer que não olhei.";
  }
  return "";
}

/* "De qual projeto é este site?" e os botões. Nunca adivinha: sem parecido, ou
   com dois servidores ou mais, a escolha começa vazia e o botão espera. */
function blocoDeGuardar(r) {
  const bloco = criar("div", "site-guardar");
  const nomes = nomesDosProjetos();
  const servidores = SERVIDORES_LIDO_EM ? SERVIDORES : null;
  const razao = razaoDeNaoGuardar(nomes, servidores);

  let projeto = null, servidor = null;
  if (nomes.length) {
    const sugerido = nomes.includes(SITE.sugerido) ? SITE.sugerido : projetoMaisParecido(r.url, nomes);
    projeto = campoDeEscolha("site-projeto", "De qual projeto é este site?",
                             nomes.map(n => [n, n]), sugerido, "Escolha o projeto");
    bloco.append(projeto.campo);
  }
  if (servidores && servidores.length > 1) {
    servidor = campoDeEscolha("site-servidor", "Em qual servidor?",
                              servidores.map(s => [String(s.id), s.nome]), "", "Escolha o servidor");
    bloco.append(servidor.campo);
  }
  if (razao) bloco.append(criar("p", "mole", razao));

  const acoes = criar("div", "acoes");
  const guardar = criar("button", "botao", r.ok === true ? "Guardar este site" : "Guardar mesmo assim");
  guardar.type = "button";
  const pronto = () => !razao && projeto.sel.value !== "" && (!servidor || servidor.sel.value !== "");
  const confere = () => { guardar.disabled = !pronto(); };
  confere();
  if (projeto) projeto.sel.addEventListener("change", confere);
  if (servidor) servidor.sel.addEventListener("change", confere);
  guardar.addEventListener("click", () =>
    guardarSite(r, projeto.sel.value, servidor ? +servidor.sel.value : null));
  acoes.append(guardar);
  if (r.ok !== true && r.ok !== false) {
    const de = criar("button", "botao botao--secundario", "Tentar de novo");
    de.type = "button";
    de.addEventListener("click", () => conferirSite(r.url, false));
    acoes.append(de);
  }
  bloco.append(acoes);
  return bloco;
}

/* O resultado de uma conferência: os quatro desfechos (respondeu, não
   respondeu, não deu para conferir, rede interna) e o endereço mal escrito. */
function pintarResultadoDaMedicao(r) {
  const campo = $("#site-endereco");
  const erro = $("#site-erro");
  const onde = $("#site-resultado");
  campo.removeAttribute("aria-invalid");
  erro.hidden = true;
  onde.setAttribute("aria-busy", "false");

  if (r.motivo === "forma") {
    campo.setAttribute("aria-invalid", "true");
    erro.textContent = "Escreva o endereço completo, começando por https://, "
                     + "por exemplo https://loja-da-ana.com.br.";
    erro.hidden = false;
    onde.replaceChildren();
    return;
  }
  if (r.motivo === "nao_publico") {
    onde.replaceChildren(criar("p", "",
      "Este endereço é de uma rede interna. O painel só confere sites públicos. "
      + "Use o endereço que o público acessa."));
    return;
  }

  const linha = criar("p", "espera__linha");
  if (r.ok === true) {
    linha.append(marcaDaPorta("conectado", "respondeu"),
                 criar("span", "", "O site respondeu (código " + r.codigo + ")"
                                   + segundosEmPalavras(r.ms) + "."));
  } else if (r.ok === false) {
    linha.append(marcaDaPorta("desconectado", "não respondeu"),
                 criar("span", "", motivoDoSite(r)));
  } else {
    linha.append(marcaDaPorta("sem_dados"),
                 criar("span", "", "Não consegui conferir este site agora. Isso "
                                   + "não quer dizer que ele esteja fora do ar — "
                                   + "quer dizer que não olhei."));
  }
  onde.replaceChildren(linha, blocoDeGuardar(r));
}

function limparResultadoDoSite() {
  SITE.seq++;                    /* uma resposta atrasada não pinta mais nada */
  clearTimeout(SITE.timer);
  SITE.sugerido = "";
  const b = $("#site-conferir");
  b.disabled = false;
  b.textContent = "Conferir o site";
  $("#site-endereco").removeAttribute("aria-invalid");
  $("#site-erro").hidden = true;
  $("#site-resultado").replaceChildren();
  $("#site-resultado").setAttribute("aria-busy", "false");
}

async function conferirSite(urlDada, doBotao) {
  const campo = $("#site-endereco");
  const url = (urlDada !== undefined ? urlDada : campo.value).trim();
  limparResultadoDoSite();
  const minha = SITE.seq;
  if (!url) { pintarResultadoDaMedicao({ motivo: "forma", url }); return; }

  const b = $("#site-conferir");
  b.disabled = true;
  b.textContent = "Conferindo…";
  $("#site-resultado").setAttribute("aria-busy", "true");
  /* A medição leva até uns 23 segundos; depois de 8 a tela diz que é normal. */
  SITE.timer = setTimeout(() => {
    if (minha === SITE.seq) {
      $("#site-resultado").replaceChildren(criar("p", "mole", "Ainda conferindo… alguns sites demoram."));
    }
  }, 8000);

  let r = null, d = null;
  try {
    r = await escrever("/api/enderecos/medir", { url });
    d = await r.json();
  } catch (_) { d = null; }
  if (minha !== SITE.seq) return;           /* outra conferência assumiu */
  clearTimeout(SITE.timer);
  b.disabled = false;
  b.textContent = "Conferir o site";
  if (doBotao !== false) b.focus();

  if (r && r.status === 403 && PAGINA_VELHA) {
    $("#site-resultado").replaceChildren();   /* a faixa do alto explica */
    return;
  }
  if (r && r.status === 400 && d && (d.motivo === "forma" || d.motivo === "nao_publico")) {
    pintarResultadoDaMedicao({ motivo: d.motivo, url });
    return;
  }
  /* Recusa por teto (429), rede ou corpo torto: "não deu para conferir". */
  if (!r || !r.ok || !d) { pintarResultadoDaMedicao({ ok: null, url }); return; }
  pintarResultadoDaMedicao(Object.assign({ url }, d));
}

/* Guarda SEM medir de novo (`medir: false`): a medição que a pessoa acabou de
   ver é a que fica no carimbo. Sem servidor cadastrado, cria "Meus sites"; com
   um só, usa ele; com dois ou mais, a escolha já veio da tela. */
async function guardarSite(r, projeto, servidorEscolhido) {
  const aviso = $("#sites-guardado");
  aviso.textContent = "";
  let servidorId = servidorEscolhido;
  if (servidorId === null) {
    if (!SERVIDORES.length) {
      let c = null;
      try { c = await escrever("/api/servidores/guardar", { nome: "Meus sites", padrao_subdominio: "" }); }
      catch (_) { c = null; }
      if (!c || !c.ok) {
        aviso.textContent = "Não consegui guardar agora. O que você digitou continua no campo.";
        return;
      }
      await olharOsServidores();
    }
    servidorId = (SERVIDORES[0] || {}).id;
  }
  let g = null;
  try {
    g = await escrever("/api/enderecos/guardar",
                       { servidor_id: servidorId, projeto, url: r.url, medir: false });
  } catch (_) { g = null; }
  if (!g || !g.ok) {
    aviso.textContent = "Não consegui guardar agora. O que você digitou continua no campo.";
    return;
  }
  /* O que a pessoa viu agora fica como a medição deste endereço. */
  if (r.ok === true || r.ok === false) {
    MEDIDAS[chaveDaMedida(servidorId, projeto)] = {
      ok: r.ok, codigo: r.codigo, erro: r.erro, medido_em: r.medido_em };
  }
  $("#site-endereco").value = "";
  limparResultadoDoSite();
  aviso.textContent = "Guardei " + r.url + " para o projeto " + projeto + ".";
  await olharOsEnderecos();
  $("#site-endereco").focus();
}

/* Uma linha da lista de sites já guardados. */
function linhaDeSite(e) {
  const li = criar("li", "site");
  const dizeres = criar("div", "endereco__dizeres");
  dizeres.append(criar("strong", "", e.projeto), criar("span", "endereco__url", e.url));
  const varios = (SERVIDORES || []).length > 1;
  const dele = varios ? (SERVIDORES || []).find(s => s.id === e.servidor_id) : null;
  if (dele) dizeres.append(criar("span", "carimbo", "servidor: " + dele.nome));

  const m = medidaDoSite(e);
  const ok = m ? m.ok : null;
  dizeres.append(marcaDaPorta(ok === true ? "conectado" : ok === false ? "desconectado" : "sem_dados",
                              ok === true ? "respondeu" : ok === false ? "não respondeu" : "não medi"));
  const carimbo = criar("p", "carimbo");
  carimbo.textContent = ok === true ? "respondeu " + m.codigo + " · medido " + haQuanto(m.medido_em)
    : ok === false ? "não respondeu · medido " + haQuanto(m.medido_em)
    : "ainda não medi";
  dizeres.append(carimbo);

  const tirar = criar("button", "botao botao--secundario", "Tirar");
  tirar.type = "button";
  tirar.addEventListener("click", () => guardarEndereco(e.servidor_id, e.projeto, ""));
  const acoes = criar("div", "acoes");
  acoes.append(tirar);
  li.append(dizeres, acoes);
  return li;
}

/* Preenche o que cerca o campo. NUNCA pinta lista nem "nenhum site" antes da
   leitura responder — é a lei 2: "nenhum site cadastrado" tem de significar
   "olhei, e não há", nunca "ainda não perguntei". */
function pintarSites() {
  const leu = !!ENDERECOS_LIDO_EM;
  const guardados = leu ? ENDERECOS : [];
  const nenhum = leu && !guardados.length;
  const estado = !leu ? "sem_dados" : (nenhum ? "desconectado" : "conectado");
  $("#sites-marca").replaceChildren(marcaDaPorta(estado));
  $("#sites-resumo").hidden = leu && !nenhum;
  $("#sites-resumo").textContent = !leu
    ? "Não consegui ler os sites desta conta. Isso não quer dizer que não há — quer dizer que não olhei."
    : "Nenhum site cadastrado ainda. Cole o endereço acima para o DERVS conferir se ele responde.";

  const propostas = leu ? sugestoesDoSite() : [];
  $("#sites-sugestoes").replaceChildren(...propostas.map(s => linhaDeSugestao(s.projeto, s.url)));
  $("#sites-lista").replaceChildren(...guardados.map(linhaDeSite));

  /* Opções avançadas: cadastrar e apagar servidor, e o padrão de subdomínio. */
  const avancado = [];
  if (SERVIDORES_LIDO_EM) {
    avancado.push(formularioDeServidorNovo());
    for (const item of SERVIDORES) avancado.push(blocoDeServidor(item));
  }
  $("#sites-servidores").replaceChildren(...avancado);
}

/* O texto de ajuda do campo "padrão de subdomínio", palavra por palavra do
   design. Numa função à parte de propósito: `formularioDeServidorNovo` monta
   dado da TELA (nomes de campo), não dado MEDIDO — juntar o texto ali
   confundiria o vigia do item 8 (`test_design.NenhumNumeroSemCarimbo`), que
   cobra carimbo em toda função que mistura dado medido com escrita na
   tela. */
function textoDeAjudaDoPadrao() {
  return "Se os projetos deste servidor seguem um padrão de endereço, o "
       + "DERVS testa sozinho e sugere o preenchimento — você ainda confirma "
       + "antes de qualquer coisa ser gravada.";
}

/* O formulário de cadastrar servidor, acima da lista. Nome obrigatório,
   padrão de subdomínio opcional — é ele que alimenta a autodetecção da
   etapa 8, mas esta tela não a chama ainda. */
function formularioDeServidorNovo() {
  const form = document.createElement("form");
  form.className = "servidor servidor--novo";

  const titulo = document.createElement("h3");
  titulo.textContent = "Cadastrar servidor";
  form.append(titulo);

  const nome = document.createElement("input");
  nome.type = "text";
  nome.required = true;
  nome.placeholder = "OVH";
  nome.setAttribute("aria-label", "Nome do servidor");

  const padrao = document.createElement("input");
  padrao.type = "text";
  padrao.placeholder = "*.tinehost.com.br";
  padrao.setAttribute("aria-label", "Padrão de subdomínio (opcional)");

  const ajuda = document.createElement("p");
  ajuda.className = "mole";
  ajuda.textContent = textoDeAjudaDoPadrao();

  const salvar = document.createElement("button");
  salvar.className = "botao";
  salvar.type = "submit";
  salvar.textContent = "Cadastrar servidor";
  const acoes = document.createElement("div");
  acoes.className = "acoes";
  acoes.append(salvar);

  form.addEventListener("submit", ev => {
    ev.preventDefault();
    guardarServidor(nome.value.trim(), padrao.value.trim());
    nome.value = padrao.value = "";
  });

  form.append(nome, padrao, ajuda, acoes);
  return form;
}

/* Um bloco por servidor cadastrado: nome, padrão (se houver) e o botão Apagar.
   Os endereços não moram mais aqui — a lista de sites é uma só, no cartão. */
function blocoDeServidor(item) {
  const bloco = document.createElement("div");
  bloco.className = "servidor";

  const cabeca = document.createElement("div");
  cabeca.className = "servidor__cabeca";
  const nome = document.createElement("strong");
  nome.className = "servidor__nome";
  nome.textContent = item.nome;
  cabeca.append(nome);
  if (item.padrao_subdominio) {
    const padrao = document.createElement("span");
    padrao.className = "servidor__padrao";
    padrao.textContent = item.padrao_subdominio;
    cabeca.append(padrao);
  }
  bloco.append(cabeca);

  const apagar = document.createElement("button");
  apagar.className = "botao botao--secundario";
  apagar.type = "button";
  apagar.textContent = "Apagar";
  apagar.addEventListener("click", () => confirmar({
    titulo: "Apagar o servidor " + item.nome + "?",
    texto: "Os endereços gravados nele saem do DERVS. O site em si não é "
         + "tocado — só paramos de medir por aqui.",
    sim: "Apagar", nao: "Manter"
  }, () => apagarServidor(item.id)));
  const acoes = document.createElement("div");
  acoes.className = "acoes";
  acoes.append(apagar);
  bloco.append(acoes);

  /* SO servidor COM PADRAO, e SO UMA VEZ por sessao — o `Set` decide, nunca
     o repinte. As propostas aparecem no cartão (`sugestoesDoSite`); aqui só se
     pede. Sem padrao, `/api/servidores/sugerir` devolveria lista vazia
     mesmo assim, e pedir seria rede gasta a toa. */
  if (item.padrao_subdominio && !SERVIDORES_JA_SUGERIDOS.has(item.id)) {
    pedirSugestao(item.id);
  }
  return bloco;
}

/* ================================================== 5. Computadores ====== */

async function autorizarComputador(id, ligado) {
  const r = await escrever("/api/maquinas/autorizar", { id, ligado });
  if (r.status === 409) {
    /* Ligado pelo arquivo: o servidor recusa dar o direito de consertar. */
    recado("este computador só acompanha os projetos. Ele não faz alterações.", true);
    return;
  }
  if (!r.ok) { recado("não deu para mudar esse computador.", true); return; }
  recado(ligado
    ? "pronto. Esse computador pode consertar sozinho o que estiver verde."
    : "pronto. Esse computador volta a só medir.");
  await carregarComputadores();
}

/* Lê `/api/maquinas` e repinta o cartão. Falha NÃO apaga o que já estava na
   tela: só quando nunca houve leitura o cartão diz "não consegui ler". */
async function carregarComputadores() {
  let d;
  try {
    const r = await fetch("/api/maquinas");
    if (!r.ok) throw new Error("recusado");
    d = await r.json();
  } catch {
    COMPUTADORES_FALHOU = true;
    pintarEsteComputador();
    return;
  }
  COMPUTADORES_FALHOU = false;
  COMPUTADORES = d.maquinas || [];
  COMPUTADORES_LIDO_EM = new Date().toISOString();
  pintarEsteComputador();
}

async function removerComputador(id) {
  const r = await escrever("/api/maquinas/remover", { id });
  if (!r.ok) { recado("não conseguimos remover. Tente de novo.", true); return; }
  recado("removido. Ele não acompanha mais.");
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
  /* A LINHA POR CAMINHO DE ARQUIVO, e não mais pelo nome do módulo.
     O `-m` só acha o pacote quando o terminal já está DENTRO da pasta do
     DERVS; colada de `C:\WINDOWS\system32` ela responde `No module named`,
     em inglês, antes de o programa começar — e quem lê acha que o número de
     seis dígitos quebrou. Aconteceu três vezes com o dono em 29/08/2026.
     Rodar o arquivo direto funciona de qualquer pasta porque `enviar.py` põe
     a raiz do repositório no caminho de busca sozinho, antes de importar.

     `<CAMINHO DO DERVS>` fica como espaço reservado de propósito: o painel
     NÃO pode saber onde o repositório está na máquina de quem lê, e inventar
     um caminho seria o painel mentindo. Quem não quer trocar nada usa o
     conectador, que é o outro caminho desta mesma porta.

     BARRA NORMAL, E NÃO A INVERTIDA DO WINDOWS. O Python aceita `/` em caminho
     nos três sistemas, inclusive no Windows; a barra invertida só funciona num.
     Este painel serve a máquina do dono (Windows) E o servidor (Linux), e uma
     linha que só roda num deles é uma linha errada para metade de quem lê.
     Achado pela verificação automática, que roda em Linux — verde na máquina de
     quem escreve não bastava, e não bastou. */
  $("#comando-pareamento").textContent =
    "python \"<CAMINHO DO DERVS>/agente/enviar.py\" --alvo " + location.origin + " --codigo " + d.codigo;
  $("#pareamento").hidden = false;
  /* A MESMA espera da porta 1, aqui. Quem cola a linha de comando merece a
     mesma confirmação de quem usa o conectador — os dois caminhos são iguais,
     e o que os igualava até aqui era só o texto da tela. */
  esperarMaquinaNova($("#espera-pareamento"), d.minutos, "numero");
  /* Quando vence, o número fica riscado — não some. Número antigo na tela é
     número que a pessoa digita e não funciona, sem entender por quê. */
  clearTimeout(gerarNumero.t);
  gerarNumero.t = setTimeout(() => {
    $("#numero-pareamento").classList.add("vencido");
    $("#numero-prazo").textContent = "Este código venceu. Gere outro.";
  }, Math.max(1, d.minutos) * 60000);
}

/* ============================================ Vigília e cérebros ========= */
/* A ponte com o DERVS-VOZ. Regras desta seção, todas de propósito:

   - TUDO que vem de `/api/voz` é dado hostil (o nome do computador, o motivo de
     um cérebro, o resumo de um recado saem do OUTRO computador): entra só por
     `textContent`, nunca por `innerHTML`.
   - A vigília tem dois estados e só um deles é verde. Qualquer valor que não
     seja exatamente "viva" é "sem dados" — falha fechada.
   - Cérebro só aparece como disponível se o VOZ disse isso E a informação é
     fresca. Sem isso, é "sem informação do VOZ", nunca "disponível".
   - Esta tela só manda recado. Nada aqui executa coisa alguma. */

const VOZ_CEREBROS = [
  ["claude_code", "Claude Code", "o cérebro que lê e mexe no código."],
  ["hermes", "Hermes Agent", "cérebro alternativo, atrás do mesmo contrato do Claude Code."],
  ["jev", "JEV", "triagem rápida: decide se algo é urgente; não conversa."]
];

// Tipo que o PAINEL gera sozinho; os do dono aparecem como o servidor os chama.
const VOZ_TIPOS = { avisar: "Aviso do painel" };
const VOZ_ESTADOS = {
  pendente:   "pendente, ainda não chegou ao VOZ",
  entregue:   "entregue ao VOZ",
  feito:      "feito",
  recusado:   "recusado",
  falhou:     "falhou",
  aguardando: "aguardando seu clique no VOZ",
  aguardando_clique: "aguardando seu clique no VOZ"
};

let VOZ = null;   // o último /api/voz inteiro; null = nunca chegou

function vozEl(tag, classe, texto) {
  const e = document.createElement(tag);
  if (classe) e.className = classe;
  if (texto !== undefined) e.textContent = texto;   // textContent: dado hostil
  return e;
}

function vozCartao(m) {
  const cartao = vozEl("div", "cartao voz__maquina");  cartao.append(vozEl("div", "nome", m.nome || "computador sem nome"));

  /* A VIGÍLIA. Três casos e só um é verde. */
  const est = m.estado || null;
  const nunca = !m.visto_em;
  const viva = !nunca && m.vigilia === "viva";
  const linha = vozEl("div", "voz__vigilia");
  linha.append(selo(viva ? "saudavel" : "sem_dados",
    { como: "span", texto: nunca ? "Ainda não mediu" : viva ? "Vigiando" : "Sem dados" }));
  linha.append(vozEl("span", "carimbo",
    nunca ? "este computador ainda não mandou nenhuma medição"
          : "última medição " + haQuanto(m.visto_em)));
  cartao.append(linha);
  if (!nunca && !viva) {
    cartao.append(vozEl("p", "mole",
      "Não recebi medição nos últimos 20 minutos. Isso não quer dizer que está "
      + "tudo bem — quer dizer que não sei. Abra o DERVS-VOZ nesse computador."));
  }

  /* OS CÉREBROS. Só vale o que o VOZ disse E é fresco. */
  const confiavel = !!(est && est.fresco === true && est.cerebros);
  const ul = vozEl("ul", "voz__cerebros");
  for (const [chave, nome, papel] of VOZ_CEREBROS) {
    const li = vozEl("li");
    const c = confiavel ? est.cerebros[chave] : null;
    let situacao, tom;
    if (!c) { situacao = "sem informação do VOZ"; tom = "sem_info"; }
    else if (c.disponivel === true) { situacao = "disponível"; tom = "ok"; }
    else { situacao = "indisponível" + (c.motivo ? ": " + c.motivo : ""); tom = "fora"; }
    li.dataset.cerebro = chave;
    li.dataset.situacao = tom;
    const rotulo = vozEl("strong", null, nome);
    // O VOZ chama o JEV em uso de `jev_triagem`; a chave do cartao e `jev`.
    const ativo = confiavel && (est.cerebro_ativo === chave
      || (chave === "jev" && est.cerebro_ativo === "jev_triagem"));
    li.append(rotulo, vozEl("span", "voz__situacao",
      " — " + situacao + (ativo ? " (em uso)" : "")));
    li.append(vozEl("div", "carimbo", papel));
    ul.append(li);
  }
  cartao.append(ul);
  if (confiavel && typeof est.gasto_dia_usd === "number") {
    cartao.append(vozEl("p", "carimbo",
      "gasto de hoje: US$ " + est.gasto_dia_usd.toLocaleString("pt-BR",
        { minimumFractionDigits: 2, maximumFractionDigits: 4 })));
  }
  return cartao;
}

function vozRecado(r) {
  const li = vozEl("li");
  li.style.display = "block";
  const cab = vozEl("div", "nome",
    (VOZ_TIPOS[r.tipo] || r.tipo || "recado") + (r.alvo ? " — " + r.alvo : ""));
  const est = VOZ_ESTADOS[r.estado] || ("estado: " + (r.estado || "desconhecido"));
  const meta = vozEl("div", "carimbo",
    est + " · " + haQuanto(r.criado_em)
    + (r.cerebro ? " · respondeu: " + r.cerebro : "")
    + (typeof r.custo_usd === "number"
        ? " · US$ " + r.custo_usd.toLocaleString("pt-BR",
            { minimumFractionDigits: 2, maximumFractionDigits: 4 })
        : ""));
  li.dataset.estado = r.estado || "";
  li.append(cab, meta);
  if (r.resumo) li.append(vozEl("p", "voz__resumo", r.resumo));
  return li;
}

function pintarVoz(situacao) {
  const cartoes = $("#voz-computadores");
  const recados = $("#voz-recados");
  const sel = $("#voz-maquina");
  cartoes.textContent = "";
  recados.textContent = "";

  if (situacao === "carregando") {
    cartoes.append(vozEl("p", "mole", "Carregando o que o DERVS-VOZ contou…"));
    recados.append(vozEl("li", "mole", "Carregando…"));
    return;
  }
  if (situacao === "erro" || !VOZ) {
    const aviso = vozEl("div", "vazio");
    aviso.append(vozEl("p", null,
      "Não consegui ler a vigília. Isso não quer dizer que o VOZ está parado — "
      + "quer dizer que não olhei."));
    const b = vozEl("button", "botao", "Tentar de novo");
    b.type = "button";
    b.addEventListener("click", carregarVoz);
    aviso.append(b);
    cartoes.append(aviso);
    recados.append(vozEl("li", "mole", "Não consegui ler os recados."));
    $("#voz-carimbo").textContent = "";
    return;
  }

  const maquinas = VOZ.maquinas || [];
  if (!maquinas.length) {
    cartoes.append(vozEl("p", "mole",
      "Nenhum computador pareado. Gere o número acima e rode o agente; "
      + "depois o DERVS-VOZ aparece aqui."));
  }
  for (const m of maquinas) cartoes.append(vozCartao(m));
  $("#voz-carimbo").textContent = "lido " + haQuanto(new Date().toISOString());

  /* O seletor do formulário acompanha a lista, sem perder a escolha. */
  const antes = sel.value;
  sel.textContent = "";
  for (const m of maquinas) {
    const o = vozEl("option", null, m.nome || "computador sem nome");
    o.value = m.maquina_id;
    sel.append(o);
  }
  // O valor de um <select> e sempre texto; o id que vem do servidor e numero.
  if (antes && maquinas.some(m => String(m.maquina_id) === antes)) sel.value = antes;
  $("#voz-enviar").disabled = !maquinas.length;

  const lista = VOZ.recados || [];
  if (!lista.length) recados.append(vozEl("li", "mole", "Nenhum recado mandado ainda."));
  for (const r of lista) recados.append(vozRecado(r));
}

async function carregarVoz() {
  if (!VOZ) pintarVoz("carregando");
  try {
    const r = await fetch("/api/voz");
    if (!r.ok) throw new Error("status " + r.status);
    VOZ = await r.json();
    pintarVoz();
  } catch {
    VOZ = null;
    pintarVoz("erro");
  }
}

/* Nível `muda_estado` põe o aviso em destaque (contorno forte e negrito, não
   cor: `--estado-*` é do selo de saúde). O aviso existe nos dois níveis. */
function atualizarAvisoVoz() {
  $("#voz-aviso").dataset.forte = $("#voz-nivel").value === "muda_estado" ? "sim" : "nao";
}

async function mandarRecadoVoz(ev) {
  ev.preventDefault();
  const erro = $("#voz-erro");
  erro.hidden = true;
  const botao = $("#voz-enviar");
  botao.disabled = true;
  try {
    const r = await escrever("/api/voz/recado", {
      // O servidor exige numero: um <select> entrega texto, e sem o `+` todo
      // recado da tela voltava 400 (a suite do servidor nao via isso). Nao e
      // `Number(`: o guarda de test_design toma isso por numero de tela.
      maquina_id: +$("#voz-maquina").value,
      tipo: $("#voz-tipo").value,
      alvo: $("#voz-alvo").value.trim(),
      texto: $("#voz-texto").value.trim(),
      nivel: $("#voz-nivel").value,
      cerebro_pedido: $("#voz-cerebro").value
    });
    if (!r.ok) {
      let d = {};
      try { d = await r.json(); } catch { /* corpo não-JSON: cai na frase padrão */ }
      erro.textContent = d.erro || "Não consegui mandar o recado. Tente de novo.";
      erro.hidden = false;
      return;
    }
    $("#voz-texto").value = "";
    recado("recado mandado. Ele chega ao VOZ na próxima vez que ele perguntar.");
    await carregarVoz();
  } catch {
    erro.textContent = "Não consegui falar com o servidor. Tente de novo.";
    erro.hidden = false;
  } finally {
    botao.disabled = !(VOZ && (VOZ.maquinas || []).length);
  }
}

$("#voz-form").addEventListener("submit", mandarRecadoVoz);
$("#voz-nivel").addEventListener("change", atualizarAvisoVoz);

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

  /* O dono clica em "Pode fazer" sem abrir a tarefa: precisa ler o que foi
     pedido. É texto de um documento de outro repositório: só textContent. */
  if (typeof t.detalhe === "string" && t.detalhe) {
    const pedido = document.createElement("span");
    pedido.className = "linha__motivo";
    pedido.textContent = "O que foi pedido: " + t.detalhe;
    li.append(pedido);
    /* O corte do pedido esconde o fim, e o fim é o comando da prova: se não
       coube no pedido, aparece à parte. */
    if (typeof t.prova === "string" && t.prova
        && !t.detalhe.includes(t.prova)) {
      const prova = document.createElement("span");
      prova.className = "linha__motivo";
      prova.textContent = t.prova;
      li.append(prova);
    }
  }

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

  /* O pedido de alteração, quando a sessão abriu um. Só endereço que passa em
     `enderecoSeguro`: o campo vem do desfecho gravado pelo computador. */
  const prLink = $("#tarefa-pr");
  const temPr = !!(t.pr_url && enderecoSeguro(t.pr_url));
  $("#tarefa-pr-caixa").hidden = !temPr;
  prLink.href = temPr ? t.pr_url : "#";

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

/* ================================================== 6.5. Auditoria ======= */
/* A tela mora aqui, e nao em `assets/auditoria.js`: um arquivo novo em
   `assets/` nasceria SEM exigir sessao, porque a lista de estaticos que
   pedem sessao (`servir.ESTATICOS_COM_SESSAO`) casa por caminho EXATO contra
   so `painel.js` e `painel.css`, e nasce lendo a pasta na SUBIDA do
   servidor. Ver CLAUDE.md, "Os arquivos de assets/ sao permissao por
   caminho EXATO". */

/* As cinco categorias e as tres gravidades, rotuladas em portugues. Nao sao
   token de cor novo: a gravidade REUSA os quatro estados do selo -- "grave"
   e o mesmo vermelho de "quebrado", "atencao" e literal, "menor" e o mesmo
   tracejado neutro de "sem dados" -- porque o significado ja e o mesmo:
   "isto quer minha atencao com que urgencia". */
const AUDIT_CATEGORIAS = { seguranca: "Segurança", bug: "Bug", teste: "Teste",
                           doc: "Documentação", estilo: "Estilo" };
const AUDIT_GRAVIDADE_SELO = { alta: "quebrado", media: "atencao", baixa: "sem_dados" };
const AUDIT_GRAVIDADE_ROTULO = { alta: "grave", media: "atenção", baixa: "menor" };

/* So os NOMES saem daqui -- nenhum numero, nenhum estado medido. E' por isso
   que quem escreve as opcoes na tela (abaixo) nao precisa carimbar: um nome
   de projeto nao envelhece do jeito que uma contagem envelhece. */
function nomesDosProjetos() {
  return (ESTADO && ESTADO.projetos || []).map(p => p.nome);
}

function popularSeletorDeAuditoria(alvo) {
  const sel = $("#audit-projeto");
  const nomes = nomesDosProjetos();
  const atual = alvo || sel.value || nomes[0] || "";
  const opcoes = nomes.map(nome => {
    const op = document.createElement("option");
    op.value = nome;
    op.textContent = nome;
    return op;
  });
  sel.replaceChildren(...opcoes);
  if (atual) sel.value = atual;
  return sel.value;
}

function desenharReguaDeAuditoria(achados) {
  const regua = $("#audit-regua");
  regua.textContent = "";
  for (const [chave, rotulo] of Object.entries(AUDIT_CATEGORIAS)) {
    const n = achados.filter(a => a.categoria === chave).length;
    const span = document.createElement("span");
    span.className = "categoria";
    span.textContent = rotulo + ": " + n;
    regua.append(span);
  }
}

/* Zero achados so e um estado valido AQUI -- quando a corrida terminou 'ok'
   com lista vazia. E' a lei 2: um "0" pelado se confundiria com "nao consegui
   medir", entao a frase diz que RODOU e nao achou nada. */
function desenharListaDeAchados(achados) {
  const ul = $("#audit-lista");
  ul.textContent = "";
  if (!achados.length) {
    ul.append(vazio(
      "0 achados. A auditoria rodou até o fim e não encontrou nada que "
      + "merecesse atenção.", null, null));
    return;
  }
  const peso = { alta: 0, media: 1, baixa: 2 };
  const ordenados = [...achados].sort((a, b) =>
    (peso[a.gravidade] ?? 9) - (peso[b.gravidade] ?? 9));
  for (const a of ordenados) {
    const estadoSelo = AUDIT_GRAVIDADE_SELO[a.gravidade] || "sem_dados";
    const rotuloGravidade = AUDIT_GRAVIDADE_ROTULO[a.gravidade] || "menor";
    const categoria = AUDIT_CATEGORIAS[a.categoria] || a.categoria || "—";
    const local = (a.arquivo || "sem arquivo") + (a.linha ? ":" + a.linha : "");
    /* `criterio()` ja escreve cada campo com `.textContent` -- a mesma
       barreira contra o texto do repositorio auditado virar marcacao,
       reusada e nao reescrita. */
    ul.append(criterio(a.frase || "(sem descrição)", estadoSelo, local,
                       rotuloGravidade + " · " + categoria,
                       a.o_que_fazer || a.trecho
                       || "Sem detalhe guardado para este achado."));
  }
}

/* Os TRES estados de dado da corrida (o quarto, "nunca auditado", e tratado
   antes de chegar aqui). As frases sao DIFERENTES de proposito -- a lei 2 --
   para "nao consegui" nunca se confundir com "rodei e nao achei nada". */
async function pintarAuditoria(alvo) {
  const faixa = $("#audit-faixa");
  faixa.hidden = true;
  const nome = popularSeletorDeAuditoria(alvo);
  $("#audit-pedir").disabled = false;
  $("#audit-pedir").textContent = "Auditar agora";

  if (!nome) {
    $("#audit-carimbo").textContent = "";
    $("#audit-regua").textContent = "";
    $("#audit-lista").textContent = "";
    const v = $("#audit-vazio");
    v.textContent = "";
    v.hidden = false;
    v.append(vazio("Você ainda não conectou nenhum projeto.", null, null));
    return;
  }

  let dado = null;
  try {
    /* A rota devolve a camada de TODOS os projetos da conta de uma vez, e a
       tela recorta o dela aqui. E de proposito: um caminho com o nome do
       projeto dentro (`/api/auditoria/<nome>`) obrigaria o servidor a casar
       rota por PREFIXO, e neste servidor a conferencia de acesso casa por
       caminho EXATO -- trocar isso por prefixo e a forma classica de abrir um
       furo sem ninguem perceber. Nao vale a pena por um recorte que o
       navegador faz de graca. */
    const r = await fetch("/api/auditoria");
    if (!r.ok) throw new Error(r.status);
    const todos = await r.json();
    const meu = (todos.projetos || []).find((p) => p.projeto === nome);
    /* Projeto que a rota nao conhece NAO vira "nunca auditado": isso seria
       afirmar sobre um dado que nao veio. `undefined` cai no mesmo caminho de
       "nao deu para perguntar" logo abaixo. */
    if (!meu) throw new Error("projeto ausente na resposta");
    dado = meu.auditoria;
  } catch {
    /* A rota pode ainda nao existir, ou a rede pode ter falhado -- as duas
       coisas se parecem daqui. A tela NAO finge um dos tres estados de dado:
       ela diz que nao deu para perguntar, e nao troca isso por "0 achados"
       nem por "nunca foi auditado", que seriam afirmacoes sobre um dado que
       ela nunca chegou a ler. */
    faixa.hidden = false;
    faixa.textContent =
      "Não conseguimos falar com o servidor para buscar a auditoria.";
    $("#audit-carimbo").textContent = "";
    $("#audit-regua").textContent = "";
    $("#audit-lista").textContent = "";
    $("#audit-vazio").hidden = true;
    return;
  }

  const corrida = dado && dado.corrida;
  const achados = (dado && dado.achados) || [];
  const v = $("#audit-vazio");

  if (!corrida) {
    // Estado "nunca auditado" -- nao e o mesmo que "sem dados": e "ainda nao
    // pedimos", e o texto diz isso com todas as letras.
    v.textContent = "";
    v.hidden = false;
    v.append(vazio(
      "Este projeto ainda não foi auditado. A auditoria lê o código por "
      + "dentro — não só o que está em volta dele — e aponta o que merece "
      + "atenção, agrupado por gravidade.",
      "Auditar agora", null, pedirAuditoria));
    $("#audit-carimbo").textContent = "";
    $("#audit-regua").textContent = "";
    $("#audit-lista").textContent = "";
    return;
  }

  v.hidden = true;

  if (corrida.estado !== "ok") {
    // Estado erro/sem dados: a lista e o carimbo DA ULTIMA CORRIDA BOA
    // continuam na tela -- nunca sao apagados por uma corrida que falhou.
    faixa.hidden = false;
    faixa.textContent =
      "a auditoria falhou: " + (corrida.motivo || "motivo não informado");
  }

  $("#audit-carimbo").textContent = corrida.medido_em
    ? "Última auditoria: " + haQuanto(corrida.medido_em) + ", "
      + (corrida.arquivos_n || 0) + " arquivo(s) lidos, custou US$ "
      + Number(corrida.custo_usd || 0).toFixed(2).replace(".", ",")
    : "";

  desenharReguaDeAuditoria(achados);
  desenharListaDeAchados(achados);
}

async function pedirAuditoria() {
  const nome = $("#audit-projeto").value;
  if (!nome) return;
  const btn = $("#audit-pedir");
  btn.disabled = true;
  btn.textContent = "Pedindo…";
  const faixa = $("#audit-faixa");
  faixa.hidden = false;
  faixa.textContent = "Pedindo a auditoria de " + nome
    + "… Ela só começa depois do seu “Pode fazer”.";
  try {
    const r = await escrever("/api/auditoria/pedir", { projeto: nome });
    if (!r.ok) throw new Error(r.status);
    recado("pedido de auditoria enviado.");
  } catch {
    recado("não conseguimos pedir a auditoria. Tente de novo.", true);
  }
  await pintarAuditoria(nome);
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

/* O pedido de autorizar que a capa guardou (`cortina.js`): entrar pelo GitHub
   ou pela porta local perde o fragmento do endereço, e sem isto o dono veria o
   painel sem o pedido que estava esperando. Revalidado aqui — a chave de
   armazenamento é de fora, como qualquer outra. `replaceState`, e não
   `location.hash`: a navegação é feita uma vez só, ao fim de `inicio`. */
function voltarAoPedidoGuardado() {
  let codigo = "";
  try {
    codigo = codigoDeAutorizar(sessionStorage.getItem("dervs-autorizar"));
    sessionStorage.removeItem("dervs-autorizar");
  } catch (_) { return; }
  if (codigo && !rota().autorizar) {
    history.replaceState(null, "", "#/conectar?autorizar=" + codigo);
  }
}

async function inicio() {
  aplicarTema(temaGuardado());
  voltarAoPedidoGuardado();
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

$("#sites-form").addEventListener("submit", (ev) => { ev.preventDefault(); conferirSite(); });
$("#site-endereco").addEventListener("input", limparResultadoDoSite);

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

$("#audit-projeto").addEventListener("change",
  () => irPara("#/auditoria/" + $("#audit-projeto").value));
$("#audit-pedir").addEventListener("click", pedirAuditoria);

inicio();
