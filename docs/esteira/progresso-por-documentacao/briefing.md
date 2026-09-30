# Briefing — o DERVS mede quanto cada projeto está desenvolvido, pela documentação, e desenvolve a partir dela

Aprovado em: 2026-09-30

## pedido_original

"Quero que consiga analisar e consertar tudo. E também desenvolver coisas. As documentações serão usadas como base para o DERVS saber quantos % a aplicação está desenvolvida e quanto falta para desenvolver. Sempre que eu precisar implementar e desenvolver mais coisas, teremos que documentar tudo primeiro e depois começamos o desenvolvimento... sim, quero sim te dar permissão para vc desenvolver sozinho (deixar consertar aqui e tudo mais o que precisar). Quero ver a aplicação funcionando (analisando e consertando)... e também quero ver desenvolvendo..."

## entendimento

Toda coisa nova nasce documentada: uma lista de critérios de aceitação marcáveis, escrita e aprovada antes do código. O DERVS lê essa documentação em cada projeto e mostra, por projeto, quantos por cento dos critérios já estão cumpridos e o que falta. Um critério só conta como cumprido quando a prova dele roda e passa; sem prova rodada ele aparece como "não verificado", nunca como feito. Quando há critério documentado e aprovado, o dono pode mandar o DERVS desenvolvê-lo: uma tarefa de desenvolvimento vermelha (sempre espera o "Pode fazer"), executada pelo computador dele numa cópia isolada, devolvendo um ramo.

## usuario_alvo

Dono e desenvolvedores (Thiago e André) que descrevem a intenção e querem ver, num número honesto, o quanto falta. É desenvolvedor: a lente DX vale.

## criterio_de_aceitacao

- [ ] O formato está escrito em um só lugar (`docs/A-DOCUMENTACAO-QUE-O-DERVS-LE.md`): cada critério é uma linha de checklist dentro de `## criterio_de_aceitacao` de um `docs/esteira/<slug>/briefing.md`, com linha opcional `Prova:` logo abaixo. O leitor tem testes com exemplos válidos e quebrados.
Prova: python test_documentos.py
- [ ] O percentual de um projeto é critérios com prova rodada e verde, dividido pelo total. Critério sem prova, ou com prova não rodada, conta como "não verificado" e aparece separado. Projeto sem documentação aparece como "sem documentação": nunca 0% e nunca 100% (Lei 2 do painel).
Prova: python test_documentos.py
- [ ] O painel mostra, por projeto, a barra de progresso com o número, os critérios que faltam e os não verificados, em português, e não muda a cor do selo de saúde por causa disso. Também conferido por clique real no navegador.
Prova: python test_progresso_tela.py
- [ ] Provas declaradas em documentação são dado de fora e nunca executam qualquer comando. Só rodam comandos de uma lista fechada (`python test_<nome>.py`, `python -m pytest <arquivo>`, `npm test`), só no computador com "Pode consertar aqui" ligado, sem shell, com prazo, e nunca em projeto bloqueado ou do André.
Prova: python test_documentos.py
- [ ] O botão "Desenvolver isto" só existe para critério de documento já aprovado; cria tarefa `desenvolver`, sempre vermelha, que nunca anda sozinha; o servidor recusa o que não vier de documento aprovado. Conferido cruzando duas contas e com regra fora da lista.
Prova: python test_desenvolver.py
- [ ] O DERVS usa a própria documentação: o percentual do DERVS, calculado de `docs/esteira/*/briefing.md` deste repositório, aparece na tela com os critérios que faltam. Conferido por clique real e por conta feita por extenso.
- [ ] As suítes existentes continuam verdes, todo `test_*.py` novo entra no `ci.yml`, e a documentação do projeto reflete a mudança no mesmo commit.

## fora_de_escopo

- Publicar ou enviar ao GitHub qualquer resultado de desenvolvimento automático; o dono revisa o ramo.
- Desenvolver em projetos bloqueados, do André (`Nexa`, `aninha-site`), nos cinco da TineHost, ou qualquer critério de segurança e de dado de paciente.
- Estimar prazo ou esforço: só mede o que está cumprido, não prevê.
- Escrever a documentação sozinho sem o dono aprovar o conteúdo.
- Migrar os briefings antigos que não têm checklist: aparecem como "sem documentação" até alguém os converter.

## riscos

O DERVS passa a rodar comando vindo de documentação e a escrever código em repositório de projeto. Mitigação: lista fechada de comandos, só no computador autorizado, tarefa sempre vermelha, cópia isolada, teto de gasto diário já existente e o "Pode fazer" do dono. Sem migration destrutiva prevista; se aparecer, volta ao portão de risco. Sem dado de paciente.

## plano_de_voo

Modo enxuto. Fase 2: um Explore lê `coletar.py`, `regras.py` e o formato dos briefings existentes em `docs/esteira/`. Fase 3: só a seção de progresso, reaproveitando tokens e componentes. Fase 4: plano por mim. Fase 5: 2 executores em worktrees (leitor e contas no servidor; tela e documentação). Fase 6: revisores python e security e clique real. Despachos previstos: cerca de 7.
