# Verificação — entrega B (o ajudante no servidor)

09/10/2026, ramo `feat/conectar-servidor`, PR #39 (empilhado sobre o #38).

## O que os comandos provaram

- Suíte inteira local: `for t in test_*.py; do python "$t" >/dev/null 2>&1 || echo "FALHOU $t"; done`
  → nenhuma linha `FALHOU` (depois de cada mesclagem E2, E1, E3, E4, F, consertos).
- Testes novos: `test_ajudante_servidor.py`, `test_servidor_ligado.py`, `test_servidor_tela.py`,
  `test_servidor_fio.py` (o fio: arquivo baixado numa pasta vazia → pareia → mede → `/api/dados`).
- Cada guarda novo foi sabotado de propósito e reprovou (registrado nos relatórios dos executores).

## O que foi conferido clicando (localhost:4790, `DERVS_AMBIENTE=local`)

- Cartão "Seus servidores": vazio → "Ligar um servidor" → linha com `mktemp`, SHA-256 e
  `python3 -I`, roteiro de 4 passos e "Se der errado".
- Um servidor falso (script com `tipo: servidor`) pediu pareamento; a tela de Autorizar disse
  "Um servidor chamado vps-ovh… precisa de poder de administrador"; autorizado, o cartão mudou
  para "ligado, medido agora" com os 3 sistemas **sem recarregar** (evento `servidor`).
- Painel: "No ar em vps-ovh: versão de 08/10/2026 — não sei qual versão está no ar" (certo:
  o local não tem a ponta do GitHub para comparar).
- "Desligar este servidor" → diálogo → o servidor saiu da lista, e a medição seguinte do
  servidor falso levou **401**.
- 360 px: página com 345 px de largura (sem rolagem lateral), a linha rola dentro do bloco,
  Copiar com largura cheia.

## O que NÃO está provado (F-2, na VPS, mão do dono, depois de publicar)

- Docker e systemd de verdade (só dublês na suíte): `--format` com rótulo ausente,
  `ProtectSystem=strict` e as diretivas novas com o soquete do Docker, reinício do servidor.
- O `historico.log` lido pela ACL do usuário `dervs-ajudante`.
- O teste de fuso do log só roda em Linux (pulado no Windows; a CI só volta em 01/11).
- O veredito "igual / N atrás" com a ponta real do GitHub (só em produção, com o coletor).
