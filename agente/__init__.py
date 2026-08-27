# -*- coding: utf-8 -*-
"""O agente local do DERVS.

Ele roda na maquina do dono, mede o que ha ali (git, Docker, portas, chaves de
`.env`) e MANDA para um DERVS remoto. Duas frases que definem o desenho:

**Ele nao escuta porta nenhuma.** So sai conexao daqui. Um agente que aceitasse
conexao seria uma porta nova na maquina de casa, atras do roteador, sem ninguem
olhando — e o que ele executaria do outro lado e justamente o que a etapa 7
amputou do servidor.

**O envio de dado e o sinal de vida.** Nao ha "estou vivo" separado. Maquina que
parou de medir tem de parecer parada; um sinal proprio a deixaria parecer viva
com a medicao congelada, e o painel ficaria verde exatamente quando parou de
olhar.

A medicao em si nao mora aqui: e `coletar.medir()`, a mesma funcao que alimenta
o `hub.db` local. Duas copias do que mede projeto virariam duas versoes no dia
em que uma fosse corrigida, e a errada passaria calada.
"""
