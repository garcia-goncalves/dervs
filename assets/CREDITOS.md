# Créditos e licenças dos assets

Regra dura desta casa: **nada com direito autoral de terceiro**, nem em protótipo
descartável. Ou geramos, ou vem de banco gratuito com licença comercial. Nunca
por link para o site de origem — o arquivo mora aqui.

Última conferência: 27/08/2026.

## Fontes

| Arquivo | Família | Autoria | Licença | Origem |
|---|---|---|---|---|
| `fontes/ibm-plex-sans.woff2` | IBM Plex Sans | IBM | [SIL Open Font License 1.1](https://openfontlicense.org/) | Google Fonts, subconjunto latino |
| `fontes/ibm-plex-mono-400.woff2` | IBM Plex Mono, peso 400 | IBM | SIL Open Font License 1.1 | Google Fonts, subconjunto latino |
| `fontes/ibm-plex-mono-600.woff2` | IBM Plex Mono, peso 600 | IBM | SIL Open Font License 1.1 | Google Fonts, subconjunto latino |

A OFL 1.1 permite uso comercial, incorporação e redistribuição. Ela **proíbe**
vender a fonte isolada e exige que um trabalho derivado não use o nome reservado
("IBM Plex") — não fazemos nem um nem outro.

**As fontes são servidas do nosso próprio domínio, não do Google.** Dois motivos:
a página não faz pedido a terceiro (o visitante não é rastreado por tabela), e a
tela não depende de um serviço externo estar de pé.

**O IBM Plex Sans é uma fonte variável:** um único arquivo de 45 KB cobre os pesos
400 a 600. Servir três cópias do mesmo binário custaria 91 KB por visita, à toa.
O Mono não é variável — por isso ele tem dois arquivos.

Total servido: **76 KB**, apenas o subconjunto latino.

## Desenhos

| Arquivo | O que é | Autoria |
|---|---|---|
| `logo.svg` | A marca, monocromática, para usar ao lado do nome | Feito aqui, para este projeto |
| `favicon.svg` | A marca com fundo, para a aba do navegador | Feito aqui |
| `favicon-180.png` | A mesma marca em 180×180, para o iOS, que não lê SVG em `apple-touch-icon` | Feito aqui |
| `selos.svg` | As quatro formas do selo, como sprite | Feito aqui |
| *(inline em `index.html`)* | Desenhos de ajuda da tela Conectar: três esquemas SVG (aviso do Chrome, aviso do Windows, janela de escolher pasta) | Feito aqui — gerados no repositório, sem licença de terceiro |

Os três esquemas são ilustrativos, não capturas de tela: não reproduzem marca nem
interface de terceiros e usam só as cores do sistema (tokens). Ficam dentro do HTML
de propósito — `assets/` só serve os arquivos que existiam quando o servidor subiu.

Nenhum é derivado de biblioteca de ícones de terceiro. Todos são retângulos e
polígonos escritos à mão — não há caminho copiado de lugar nenhum.

**O `favicon-180.png` foi rasterizado com a biblioteca padrão do Python** (`zlib`
e `struct`, com supersampling 3×3), porque a regra 1 deste repositório proíbe
dependência externa e o iOS não lê SVG nesse lugar. O script viveu no scratchpad
da sessão e não foi versionado: o PNG é gerado uma vez e não muda.

## O que a marca quer dizer

Três camadas empilhadas na ordem em que o código anda — **no seu computador, no
GitHub, no ar** — e a do meio fora de alinhamento. Isso é o *drift*: a diferença
entre as três, que é o diferencial confirmado do produto.

A primeira tentativa foi desenhar uma torre de controle, o nome da direção visual.
**Não se lê em 16px** — vira abajur, depois taça. Uma marca abstrata que carrega o
significado certo vence um desenho literal que ninguém reconhece.

**Verde não aparece em nenhum asset de marca**, e isso é regra, não gosto: verde é
o estado saudável do selo. Se virar cor de enfeite, o selo verde para de
significar alguma coisa no dia em que mais importa.

## Foto realista

**Não há nenhuma, e nenhuma é necessária na Fatia 1.** As seis telas são painel de
instrumento: dado, selo e prova. Se a página pública de apresentação vier a pedir
uma, ela virá de Pexels, Pixabay, Unsplash ou Openverse, com licença comercial, e
entra nesta tabela com origem e autoria antes de ser usada.
