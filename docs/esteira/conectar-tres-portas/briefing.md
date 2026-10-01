# Briefing — Conectar em três portas

> Fase 1 da esteira. Escrito em 29/08/2026.

## pedido_original

> Em COMPUTADOR, estou achando muito dificil a conexão com o código gerado
> automaticamente. Acho que o usuário vai ter trabalho pra fazer isso (entrar no cmd,
> ir até a pasta do repo local source/repos etc)... acho que o melhor era termoa algo
> coo 3 botões, para conectar "Local / Github / Servidor(es)"... com integração
> facilitada. Quero suas ideias... mas não quero que dificulte as coisas. Eu sei que
> DEVS são inteligentes, mas quero facilidade.

> Sim, pode começar e fazer suas sugestões. Quero a opção A, mas também quero a opção C
> (manter do jeito que está e somente corrigir o caminho). Vamos deixar as 2 opções. Mas
> e se o usuário quer abrir uma pasta de projetos que não é o source/repos? Como ele
> fará? Por isso eu queria facilitar, colocando um botão que o usuário aperta e abre uma
> janela (igual do VS studio) levando até a pasta dos projtos), seria algo assim. Mas
> sei que vc fará o melhor e com mais cara de DERVS! Bora! Faça tudo o que tiver que
> fazer. Não se esqueça de ativar e indexar o CBM pra te ajudar ainda mais. Ative todos
> os seus agentes possíveis. Quero força total nisso, agora! Quero que o DERVS tenha
> tudo que um DEV precisa. E que resolva/desenvolva tudo! Obrigado.

## entendimento

A tela "Conectar projeto" deixa de ser um aviso de que falta um computador e passa a ter
três portas de verdade — **o seu computador**, **a sua conta do GitHub** e **os seus
servidores** — cada uma conectável sem editar arquivo. A porta do computador ganha um
conectador que se baixa e se abre com dois cliques, e é ele quem mostra a **janela nativa
de escolher pasta**, matando o caminho `C:\Users\Desktop\source\repos` que hoje está
escrito dentro do `coletar.py`. Quem prefere terminal continua tendo uma linha — mas uma
que roda de qualquer pasta.

## usuario_alvo

**É desenvolvedor — a lente DX do Analista está ligada.** Mas é o desenvolvedor no pior
momento possível: o primeiro minuto, numa máquina onde o DERVS ainda não existe, sem o
repositório clonado, muitas vezes num computador que não é o dele. Hoje esse minuto
falha: o comando `python -m agente.enviar` exige estar dentro da pasta do repositório, e
o dono deste projeto levou `No module named 'agente'` **três vezes** por colá-lo de
`C:\WINDOWS\system32`. O segundo público é o próprio dono, que decide o produto e não
opera terminal.

## criterio_de_aceitacao

**Porta 1 — o seu computador**

- [ ] Baixar o conectador pela tela e dar dois cliques nele pareia a máquina, **sem digitar nada e sem terminal**. Provado clicando, com o número real gerado pelo painel.
- [ ] O conectador abre a janela nativa de escolher pasta antes de parear, já sugerindo `%USERPROFILE%\source\repos` quando ela existe. A pasta escolhida é a que o agente varre — provado apontando para uma pasta que **não** é `source\repos` e vendo os projetos dela aparecerem no painel.
- [ ] O conectador usa **só a biblioteca padrão** (`tkinter` incluído) e é **um arquivo só**. `test_conectador.py` reprova se ele importar qualquer coisa de fora.
- [ ] Fechar a janela de escolha sem escolher **não pareia e não deixa lixo** — nem token, nem tarefa agendada. Falha fechada.
- [ ] A máquina continua reportando depois que a janela fecha: o conectador registra a tarefa agendada. `test_conectador.py` prova o comando montado; a checagem no relógio é do roteiro de verificação.
- [ ] A linha para quem prefere terminal roda **de qualquer pasta**, inclusive de `C:\WINDOWS\system32`, e é **uma linha só**. Provado rodando de lá.
- [ ] `coletar.RAIZ` deixa de ser caminho fixo: vira lista lida da configuração do agente, com o valor de hoje só como último recurso. `test_coletar.py` prova as duas raízes e a ausência de qualquer caminho absoluto desta máquina no arquivo.
- [ ] Trocar a pasta depois, pela tela, sem baixar nada de novo: o painel navega as pastas da máquina **pelo canal de sondagem que já existe**. O agente continua sem escutar porta — `test_agente.py` prova que nenhum socket é aberto para escuta.

**Porta 2 — a sua conta do GitHub**

- [ ] Um botão leva à instalação do aplicativo do GitHub e volta ao painel com a conta ligada, sem o dono ver, copiar ou colar segredo nenhum.
- [ ] O número da instalação passa a ser **por usuário**, não a linha global de hoje. `test_banco.py` prova que duas contas guardam instalações diferentes e que uma não lê a da outra.
- [ ] Desconectar a conta pela tela apaga a instalação daquele usuário e só dela.
- [ ] Nenhum segredo aparece em log, resposta HTTP ou mensagem de erro. `secret-scan.sh` passa.

**Porta 3 — os seus servidores**

- [ ] Um botão aceita a URL de um servidor, confere por HTTPS que ela responde e a guarda — **sem chave SSH em lugar nenhum**, como manda a fonte única §5.1c.
- [ ] A URL substitui o `url_prod` escrito à mão no `casos.json` para aquele projeto, e a coluna "No ar" passa a sair dela.
- [ ] Endereço interno é recusado: `localhost`, `127.0.0.0/8`, `10/8`, `172.16/12`, `192.168/16`, `169.254/16` e `::1`. A recusa vale **depois** de resolver o nome, e vale em todo redirecionamento. `test_servir.py` prova cada faixa e prova o redirecionamento que sai de um endereço público para um interno.

**Vale para as três**

- [ ] A tela cabe em 360px sem rolagem lateral, com alvo de toque de 44px.
- [ ] Nenhum estado mente: cada porta mostra "conectado", "não conectado" ou **"não deu para conferir"**, nunca um zero inventado — a lei nº 2 deste repositório.
- [ ] Toda a suíte verde na CI, não só nesta máquina.

## fora_de_escopo

- Instalador `.exe` assinado, e qualquer coisa que peça certificado de assinatura de
  código.
- Chave SSH para o servidor, agora e sempre — a fonte única §5.1c fecha essa porta por
  desenho.
- `irm ... | iex` como caminho recomendado: ensina o hábito de executar o que se baixa da
  internet sem ler. Fica de fora até haver caso que não se resolva de outro jeito.
- Descoberta automática de máquinas na rede: o agente não escuta porta, por desenho.
- Conectar GitLab, Bitbucket ou qualquer outra forja.
- macOS e Linux no conectador de dois cliques. O `.py` roda nos três, mas só o Windows é
  verificado agora — é a máquina do dono.
- Reescrever as capacidades em Python (a "fusão" do §11 da fonte única). Continua sendo
  outra esteira.

## riscos

**Quatro, e três deles pedem revisor de segurança.**

1. **Migration no banco.** Instalação do GitHub por usuário, raízes por máquina e URL de
   servidor por projeto. Três tabelas/colunas novas, num banco que já sofreu uma migration
   de verdade (`executescript` não abre transação — está registrado em memória).
2. **SSRF na porta do servidor.** O painel passa a buscar uma URL que o usuário digitou.
   É a superfície clássica de pedir ao servidor que bata em endereço interno. A peneira já
   existe em `coletar_github.py` e **precisa ser reusada, não reescrita** — quando ela foi
   escrita, matou o drift em silêncio com 926 testes verdes.
3. **Segredo de terceiro.** A instalação do GitHub por usuário mexe no caminho de
   autenticação. Vale a lei nº 3: falha fechada, devolve `None`/`False`, nunca levanta.
4. **Primitivo novo de leitura na máquina do dev.** Navegar pastas pela tela é uma
   capacidade nova de ler a máquina de fora. Escopo: **só nomes de pasta, nunca conteúdo
   de arquivo**, e só para a conta a que aquela máquina está pareada.

Não há dado de paciente e não há pagamento. Não há mudança em configuração de deploy.

## plano_de_voo

**Fases 1 a 7, com a fase 3 ligada** (há tela nova). **Modo completo na descoberta** — as
quatro lentes em paralelo, porque o escopo atravessa banco, autenticação, rede e um
programa novo que roda fora do servidor, e nenhuma lente sozinha enxerga isso.

**Sem portão visual (portão 3).** A direção "Torre de Controle" está aprovada em
`docs/esteira/dervs/design.md` e não se refaz; a fase 3 aqui é aplicar a direção que já
existe a uma tela nova, não escolher entre direções.

**Com portão de risco (portão 4)**, uma pergunta de sim ou não, por causa da migration e
do segredo de terceiro.

**Entrega em três blocos ordenados, cada um fechando sozinho.** A porta 1 primeiro — é a
que dói hoje, e é a única de que as outras duas dependem para ter o que mostrar.

| Bloco | Porta | Por que nesta ordem |
|---|---|---|
| 1 | O seu computador | é a dor relatada, e destrava a `RAIZ` fixa que segura todo o resto |
| 2 | Os seus servidores | menor superfície nova; a peneira anti-SSRF já existe |
| 3 | A sua conta do GitHub | mexe em autenticação e segredo de terceiro — vai por último, com a suíte já verde |

**Modelos por papel:** Interrogador `opus` · descoberta `sonnet` ×4 · síntese `opus` ·
design `sonnet` · plano `opus` (neguin-planner) · execução `sonnet` (neguin-executor em
worktree) · revisores `sonnet` (python, security, design, conteudo) · verificador técnico
`haiku` · Cronista `sonnet`.

**Despachos previstos: 18.**
