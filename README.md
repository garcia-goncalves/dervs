# Painel de Projetos

Visão ao vivo de todos os repositórios em `C:\Users\Desktop\source\repos` — andamento,
prontidão, projeção de entrega, estudo de caso e infraestrutura em execução.

## Rodar

```powershell
python C:\Users\Desktop\source\painel-projetos\servir.py
```

Abre em **http://localhost:4777**. Para outra porta e outro intervalo de coleta:

```powershell
python C:\Users\Desktop\source\painel-projetos\servir.py 4780 30
```

O servidor escuta apenas em `127.0.0.1` — o painel não fica exposto na rede.
`Ctrl+C` encerra.

## Como funciona

| Arquivo | Papel |
|---|---|
| `coletar.py` | Lê git, Docker e portas da máquina; grava `dados.json`. Só lê — nunca escreve num repositório. |
| `servir.py` | Serve a página e `/api/dados`; roda o coletor a cada 60 s. |
| `index.html` | A tela. Relê `/api/dados` a cada 15 s; sem dependência externa, sem build. |
| `casos.json` | **Camada curada, escrita à mão**: caso de uso, público, risco, métrica, portas e containers de cada projeto. |
| `dados.json` | Saída do coletor. Descartável — é regerado a cada coleta. |

Dado quantitativo vem do coletor, ao vivo. Narrativa vem do `casos.json`.
Projeto novo em `source/repos` aparece sozinho na próxima coleta, com os números;
o estudo de caso dele fica vazio até alguém escrever a entrada no `casos.json`.

## Prontidão — 14 pontos

| Critério | Peso |
|---|---|
| README | 1 |
| Árvore limpa e enviada | 1 |
| CI configurada | 2 |
| Testes automatizados | 2 |
| Docker / compose | 1 |
| Exemplo de variáveis de ambiente | 1 |
| Workflow de deploy | 2 |
| Pasta `docs/` | 1 |
| `.gitignore` | 1 |
| Sem arquivo de segredo na raiz | 2 |

A **fase** sai do cruzamento entre prontidão e dias parado:
Operação (≥85% e ativo) · Manutenção (≥85% e parado) · Estabilização (≥60%) ·
Hibernando (parado há mais de 60 dias) · Construção · Rascunho (sem git).

## Projeção — o que ela é e o que não é

Velocidade = commits das últimas 4 semanas ÷ 4, comparada à média das 12 anteriores.
O horizonte assume ~4 commits de trabalho por ponto de prontidão faltante, dividido
pela velocidade atual.

É **extrapolação de ritmo histórico, não estimativa de escopo**. Serve para ordenar
prioridade e enxergar quem parou. Não serve para prometer data a cliente: o modelo não
sabe o que falta construir, só o quanto o checklist de engenharia está fechado.

## Segurança

O coletor nunca abre arquivo de segredo — apenas testa se o nome existe, para
apontar o risco. Nenhum valor de variável de ambiente entra no `dados.json`.
