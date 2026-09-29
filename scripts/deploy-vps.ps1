# Publica este projeto na VPS (Windows). Chamado pela tarefa "Deploy para a VPS" do VS Code.
#   deploy-vps.ps1            publica o commit atual (precisa estar no GitHub)
#   deploy-vps.ps1 -Voltar    volta o site para a versao anterior
# Configuracao no arquivo .deploy-vps na raiz do projeto.
param([switch]$Voltar)
$ErrorActionPreference = 'Continue'   # erros de programas externos sao conferidos via $LASTEXITCODE

function Parar($msg) { Write-Host "`nNAO PUBLICADO: $msg`n" -ForegroundColor Red; exit 1 }

$raiz = (git rev-parse --show-toplevel 2>$null)
if (-not $raiz) { Parar "esta pasta nao e um repositorio git" }
Set-Location $raiz

$cfg = @{}
if (-not (Test-Path .deploy-vps)) { Parar "falta o arquivo .deploy-vps na raiz do projeto" }
Get-Content .deploy-vps | Where-Object { $_ -match '^\s*([a-z]+)\s*=\s*(.+?)\s*$' } | ForEach-Object { $cfg[$Matches[1]] = $Matches[2] }
$projeto  = $cfg['projeto']
$servidor = if ($cfg['servidor']) { $cfg['servidor'] } else { 'vps-ovh' }
$ramo     = if ($cfg['ramo']) { $cfg['ramo'] } else { 'main' }
if (-not $projeto) { Parar "defina projeto=<nome> no .deploy-vps" }

if ($Voltar) {
  Write-Host "Voltando '$projeto' para a versao anterior..." -ForegroundColor Yellow
  ssh -t $servidor "sudo deploy $projeto --voltar"
  exit $LASTEXITCODE
}

# 1. Tudo salvo e enviado ao GitHub? (o GitHub tem que ter exatamente o que vai para o ar)
if (git status --porcelain) { Parar "ha alteracoes sem commit. Faca o commit e o push antes." }
$atual = git branch --show-current
if ($atual -ne $ramo) { Parar "voce esta no ramo '$atual'; so se publica o ramo '$ramo'." }
Write-Host "Conferindo o GitHub..."
git fetch -q origin $ramo 2>$null
if ($LASTEXITCODE -ne 0) {
  git ls-remote --exit-code origin 2>$null | Out-Null
  if ($LASTEXITCODE -ne 0) { Parar "nao consegui falar com o GitHub (git fetch)." }
  Parar "o ramo '$ramo' ainda nao existe no GitHub. Faca 'git push' antes."
}
$local  = git rev-parse HEAD
$remoto = git rev-parse "origin/$ramo"
if ($local -ne $remoto) { Parar "o commit atual nao e o mesmo do GitHub. Faca 'git push' (ou 'git pull') antes." }
$commit = git rev-parse --short HEAD

# 2. Empacota so o que esta no commit, sempre com fim de linha do Linux.
$arquivo = "$projeto-$commit.tar.gz"
$tmp = Join-Path $env:TEMP $arquivo
git -c core.autocrlf=false -c core.eol=lf archive --format=tar.gz -o $tmp HEAD
if ($LASTEXITCODE -ne 0) { Parar "falha ao empacotar o codigo." }

# 3. Envia e publica.
Write-Host "Enviando $commit para o servidor..."
ssh $servidor "mkdir -p ~/.deploy-envios"
if ($LASTEXITCODE -ne 0) { Remove-Item $tmp; Parar "nao consegui conectar no servidor '$servidor' (veja o ~/.ssh/config)." }
scp -q $tmp "${servidor}:.deploy-envios/$arquivo"
$ok = $LASTEXITCODE
Remove-Item $tmp
if ($ok -ne 0) { Parar "falha ao enviar o arquivo." }
ssh -t $servidor "sudo deploy $projeto ~/.deploy-envios/$arquivo $commit"
exit $LASTEXITCODE
