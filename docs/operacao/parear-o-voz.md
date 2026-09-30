# Parear o DERVS-VOZ com o painel

*Escrito em 30/09/2026. O DERVS-VOZ é o programa de voz e de terminal do seu
computador; o que ele é e por que o terminal mora nele está em
`docs/A-APLICACAO.md`, §5.5.*

O VOZ fala com o painel pelo **mesmo pareamento** de qualquer computador: não
existe um segundo jeito, um segundo token nem uma segunda porta. Parear o
computador é parear o VOZ dele.

## Passo a passo

1. Conecte o computador seguindo
   [`conectar-uma-maquina.md`](conectar-uma-maquina.md) — o conectador ou a linha
   de comando, os dois valem. **Onde:** painel, tela **Conectar** → **Gerar o
   número**. O número tem seis dígitos, vale poucos minutos e serve para um
   computador só.
2. Com o computador aparecendo em **Conectados**, desça até **Vigília e
   cérebros**, na mesma tela.
3. Abra o DERVS-VOZ nesse computador. Ele usa o token que o pareamento já
   guardou em `~/.dervs/agente.json`, **fora do repositório** — você não copia
   token nenhum de um lado para o outro.

**Se der certo:** o cartão do computador mostra **Vigiando** e os cérebros com
"disponível" ou o motivo de não estarem.

**Se aparecer "Ainda não mediu":** o computador pareou, mas nenhuma medição
chegou. Rode o agente (`conectar-uma-maquina.md`, "Deixar reportando sozinho").

**Se aparecer "Sem dados":** a última medição tem mais de 20 minutos. Não quer
dizer que está tudo bem — quer dizer que o painel não sabe. Abra o DERVS-VOZ e o
agente nesse computador.

**Se os cérebros dizerem "sem informação do VOZ":** o VOZ não contou nada
recente. O painel não adivinha: abra o VOZ.

## O que o painel nunca faz aqui

- Não abre terminal, shell nem SSH. O terminal SSH mora no DERVS-VOZ, no seu
  computador, com a chave do seu usuário.
- Não executa o recado. Ele só o deixa na fila; o VOZ o busca, e o que muda
  alguma coisa **só acontece depois do seu clique no DERVS-VOZ**.
- Não guarda senha nem chave de nenhum cérebro. A chave do JEV
  (`TYPESAFE_API_KEY`) mora no ambiente do computador, fora do repositório; sem
  ela o JEV fica desligado e o painel diz isso.

## O sinal de vida

Quem diz que o computador está vigiando é a **medição**, não o VOZ contar que
está bem. Ver "O sinal de vida é o dado" em `conectar-uma-maquina.md`.
