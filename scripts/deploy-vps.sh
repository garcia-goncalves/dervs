#!/usr/bin/env bash
# Publica este projeto na VPS (Linux/Mac). Chamado pela tarefa "Deploy para a VPS" do VS Code.
#   deploy-vps.sh            publica o commit atual (precisa estar no GitHub)
#   deploy-vps.sh --voltar   volta o site para a versao anterior
# Configuracao no arquivo .deploy-vps na raiz do projeto.
set -euo pipefail
parar() { printf '\n\033[31mNAO PUBLICADO: %s\033[0m\n\n' "$1"; exit 1; }

raiz=$(git rev-parse --show-toplevel 2>/dev/null) || parar "esta pasta nao e um repositorio git"
cd "$raiz"
[ -f .deploy-vps ] || parar "falta o arquivo .deploy-vps na raiz do projeto"
cfg() { sed -n "s/^[[:space:]]*$1[[:space:]]*=[[:space:]]*\(.*[^[:space:]]\)[[:space:]]*$/\1/p" .deploy-vps | tail -1; }
projeto=$(cfg projeto); servidor=$(cfg servidor); ramo=$(cfg ramo)
servidor=${servidor:-vps-ovh}; ramo=${ramo:-main}
[ -n "$projeto" ] || parar "defina projeto=<nome> no .deploy-vps"

if [ "${1:-}" = "--voltar" ]; then
  echo "Voltando '$projeto' para a versao anterior..."
  exec ssh -t "$servidor" "sudo deploy $projeto --voltar"
fi

# 1. Tudo salvo e enviado ao GitHub? (o GitHub tem que ter exatamente o que vai para o ar)
[ -z "$(git status --porcelain)" ] || parar "ha alteracoes sem commit. Faca o commit e o push antes."
atual=$(git branch --show-current)
[ "$atual" = "$ramo" ] || parar "voce esta no ramo '$atual'; so se publica o ramo '$ramo'."
echo "Conferindo o GitHub..."
if ! git fetch -q origin "$ramo" 2>/dev/null; then
  git ls-remote --exit-code origin >/dev/null 2>&1 || parar "nao consegui falar com o GitHub (git fetch)."
  parar "o ramo '$ramo' ainda nao existe no GitHub. Faca 'git push' antes."
fi
[ "$(git rev-parse HEAD)" = "$(git rev-parse "origin/$ramo")" ] ||
  parar "o commit atual nao e o mesmo do GitHub. Faca 'git push' (ou 'git pull') antes."
commit=$(git rev-parse --short HEAD)

# 2. Empacota so o que esta no commit, sempre com fim de linha do Linux.
arquivo="$projeto-$commit.tar.gz"
tmp=$(mktemp -d)/$arquivo
trap 'rm -rf "$(dirname "$tmp")"' EXIT
git -c core.autocrlf=false -c core.eol=lf archive --format=tar.gz -o "$tmp" HEAD

# 3. Envia e publica.
echo "Enviando $commit para o servidor..."
ssh "$servidor" "mkdir -p ~/.deploy-envios" || parar "nao consegui conectar no servidor '$servidor' (veja o ~/.ssh/config)."
scp -q "$tmp" "$servidor:.deploy-envios/$arquivo" || parar "falha ao enviar o arquivo."
ssh -t "$servidor" "sudo deploy $projeto ~/.deploy-envios/$arquivo $commit"
