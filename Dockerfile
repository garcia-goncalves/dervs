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

FROM python:3.12-slim

# Usuário sem privilégio: o processo do servidor não precisa ser root.
RUN useradd --create-home --shell /usr/sbin/nologin dervs
WORKDIR /app

# ---------------------------------------------------------------------------
# Cópia explícita, arquivo por arquivo. Sem curinga, sem `COPY . .`.
# Nada de test_*.py, nada de docs/, nada de vivo/.
# ---------------------------------------------------------------------------
COPY banco.py         /app/
COPY barreira.py      /app/
COPY coletar.py       /app/
COPY coletar_github.py /app/
COPY coletar_pesado.py /app/
COPY execucao.py      /app/
COPY fila.py          /app/
COPY memoria.py       /app/
COPY regras.py        /app/
COPY servir.py        /app/

COPY index.html            /app/
COPY casos.json            /app/
COPY painel-projetos.svg   /app/
COPY painel-projetos.png   /app/
COPY painel-projetos.ico   /app/

RUN chown -R dervs:dervs /app
USER dervs

EXPOSE 4777

# O código não tem uma única dependência fora da biblioteca padrão do Python.
# Não há `pip install` aqui, e isso é de propósito: sem árvore de dependência,
# não há superfície de ataque por pacote de terceiro.
CMD ["python", "servir.py"]
