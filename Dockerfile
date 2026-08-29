# DERVS — imagem de produção.
#
# Duas barreiras independentes impedem que o código de vivo/ chegue ao ar:
#   1. .dockerignore, que tira vivo/ do contexto de build;
#   2. este arquivo, que NUNCA usa `COPY . .` — cada arquivo entra por nome.
#
# A segunda existe porque a primeira não basta: .dockerignore não vale para
# `COPY --from` nem para contexto remoto. Se alguém trocar a cópia explícita
# por `COPY . .`, a barreira 1 sozinha ainda seguraria — mas a prova disso é
# o `ls` dentro do container, não a leitura deste arquivo.
#
# A lista abaixo tem de acompanhar o que `servir.py` de fato importa. Entre a
# etapa 9 e a etapa 14 nasceram sete arquivos de runtime (autenticacao, cortina,
# passkey, p256, index-cortina.html, portas.html, assets/) e nenhum deles estava
# aqui: a imagem morria no primeiro `import autenticacao`, e a CI não pegava
# porque a CI roda os testes, não a imagem. Por isso o passo de conferência da
# publicação sobe o container e bate na porta antes de trocar o que está no ar.

FROM python:3.12-slim

# A etiqueta padrão que diz de qual repositório esta imagem saiu. Ela não é
# enfeite: a limpeza de imagens antigas no servidor filtra por ela, e sem a
# etiqueta a limpeza ou não acha nada, ou apaga imagem dos outros 8 sistemas
# que rodam naquela máquina.
LABEL org.opencontainers.image.source="https://github.com/garcia-goncalves/dervs"
LABEL org.opencontainers.image.title="DERVS"
LABEL org.opencontainers.image.description="O painel que mostra o estado dos projetos de quem programa com o Claude."

# As correções de segurança do sistema base, no momento em que a imagem é
# construída. Sem esta linha a imagem carrega para sempre o que havia de errado
# no dia em que a etiqueta `python:3.12-slim` foi publicada — e como toda
# publicação reconstrói a imagem, o que está corrigido lá fora entra sozinho.
#
# Em 28/08/2026 isto fechava três falhas graves do `openssl`, e o openssl não é
# detalhe aqui: é ele que protege as conversas do painel com a API do GitHub.
#
# `--no-install-recommends` e a limpeza da lista no fim da mesma camada: sem os
# dois, a imagem engorda com pacote que ninguém pediu e com índice do apt que
# não serve para nada depois do build.
# O QUE SOBRA DEPOIS DESTA LINHA, e por que sobra (medido em 28/08/2026):
# quatro falhas do `perl` (duas críticas), e nenhuma delas tem correção
# publicada — o Debian ainda não lançou versão corrigida. O pacote é
# `perl-base`, marcado como ESSENCIAL: remover derruba o `dpkg`. E o painel
# nunca executa perl: o processo é `python servir.py`, não há script de shell
# na imagem e não há `pip install`. Registrado aqui para que a próxima pessoa
# que rodar um verificador de vulnerabilidade não refaça esta investigação.
# Quando o Debian corrigir, a próxima publicação já leva a correção sozinha.
RUN apt-get update \
 && apt-get upgrade -y --no-install-recommends \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

# Usuário sem privilégio: o processo do servidor não precisa ser root.
RUN useradd --create-home --shell /usr/sbin/nologin dervs
WORKDIR /app

# ---------------------------------------------------------------------------
# Cópia explícita, arquivo por arquivo. Sem curinga, sem `COPY . .`.
# Nada de test_*.py, nada de docs/, nada de vivo/.
# ---------------------------------------------------------------------------

# O que `servir.py` importa, direta ou indiretamente.
COPY autenticacao.py  /app/
COPY banco.py         /app/
COPY cortina.py       /app/
COPY memoria.py       /app/
COPY p256.py          /app/
COPY passkey.py       /app/
COPY regras.py        /app/
COPY servir.py        /app/
# O semaforo (Fatia 2). Entra porque `banco.py` e `servir.py` o importam, e
# `test_imagem.py` cobra que todo modulo importado entre — sem ele a imagem
# morre na subida com ImportError, e a CI nao pega: ela roda testes, nao imagem.
COPY tarefas.py       /app/

# Os coletores. `servir.py` os chama como processo separado, por caminho, então
# eles não aparecem como `import` — mas sem eles as três camadas quebram.
# `coletar_github.py` é o que continua fazendo sentido no servidor: ele mede a
# API do GitHub, que responde igual de qualquer lugar. `coletar.py` e
# `coletar_pesado.py` medem a máquina onde rodam, e no servidor ficam
# desligados por `DERVS_COLETA_LOCAL=0` — mas entram na imagem assim mesmo,
# porque uma imagem que quebra quando alguém liga uma variável é uma armadilha.
COPY coletar.py        /app/
COPY coletar_github.py /app/
COPY coletar_pesado.py /app/
COPY github_app.py     /app/

# `execucao.py` e `fila.py` NAO entram. Eles ficam no repositorio de proposito
# (182 testes e a trava de diff de fila.py:229), mas desde a etapa 7 nenhuma
# rota aponta para eles — e a doutrina deste arquivo e que a barreira e a
# imagem, nao a ausencia de rota. Se voltarem a ser usados, voltam por aqui.
#
# `barreira.py` saiu pelo mesmo motivo, na etapa 16: o unico consumidor dele
# era `execucao.py`. Codigo que so os testes importam nao tem o que fazer numa
# imagem exposta a internet.

# As três páginas. `index-cortina.html` é a capa que quem chega sem sessão vê, e
# `portas.html` é o menu de logins injetado nela — os dois são arquivo separado
# de propósito, para que o Ctrl+U de quem não passou pela cortina não mostre o
# que ainda não foi liberado.
COPY index.html            /app/
COPY index-cortina.html    /app/
COPY portas.html           /app/
COPY casos.json            /app/
COPY robots.txt            /app/
COPY painel-projetos.svg   /app/
COPY painel-projetos.png   /app/
COPY painel-projetos.ico   /app/

# A pasta de assets da etapa 13: folha de estilo, marca, glifos dos selos e as
# duas famílias tipográficas. `servir.py` monta a lista de estáticos permitidos
# LENDO ESTA PASTA na subida — sem ela a lista nasce vazia, a página carrega sem
# estilo nenhum e nada no log diz por quê.
COPY assets/ /app/assets/

# ---------------------------------------------------------------------------
# O banco mora FORA da imagem.
# ---------------------------------------------------------------------------
# A imagem é jogada fora e reconstruída a cada publicação. Um `hub.db` dentro
# dela levaria junto toda conta, todo computador pareado e toda medição, em
# silêncio, a cada deploy. `/dados` é ponto de montagem de volume.
RUN mkdir -p /dados && chown -R dervs:dervs /dados /app
VOLUME ["/dados"]
USER dervs

ENV DERVS_BANCO=/dados/hub.db \
    DERVS_ESCUTA=0.0.0.0 \
    DERVS_COLETA_LOCAL=0 \
    PYTHONUNBUFFERED=1

EXPOSE 4777

# Container que subiu não é container que respondeu. O healthcheck bate na porta
# de dentro do próprio container; enquanto ele não passar, o compose não
# considera o serviço de pé e a publicação não segue.
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; \
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:4777/robots.txt', timeout=4).status == 200 else 1)"

# O código não tem uma única dependência fora da biblioteca padrão do Python.
# Não há `pip install` aqui, e isso é de propósito: sem árvore de dependência,
# não há superfície de ataque por pacote de terceiro.
CMD ["python", "servir.py"]
