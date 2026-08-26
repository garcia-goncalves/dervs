"""Recalcula o contraste da paleta do DERVS (design.md).

MOTIVO: numero de contraste escrito a mao em documento de design envelhece
em silencio. Aqui a conta e a WCAG 2.2 e a paleta e a mesma do design.md:
mudou a cor la, roda isto e veja o que quebrou.

Minimo: 4.5 para texto, 3.0 para contorno que carrega significado.
Uso: python docs/esteira/dervs/contraste.py
"""
def lum(h):
    h = h.lstrip('#')
    c = [int(h[i:i+2], 16)/255 for i in (0, 2, 4)]
    c = [v/12.92 if v <= 0.03928 else ((v+0.055)/1.055)**2.4 for v in c]
    return 0.2126*c[0] + 0.7152*c[1] + 0.0722*c[2]

def r(a, b):
    la, lb = lum(a), lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi+0.05)/(lo+0.05)

CLARO = dict(fundo='#FFFFFF', elevado='#F1F2F0', texto='#101210', suave='#5B605A',
             borda='#D9DBD8', borda_forte='#8A8F89', acao='#111310', acao_texto='#FFFFFF',
             saudavel='#146B45', atencao='#8A5A00', quebrado='#B3261E', sem_dados='#666B65')
ESCURO = dict(fundo='#0B0C0B', elevado='#161816', texto='#F2F3F1', suave='#9BA098',
              borda='#2B2D2A', borda_forte='#676C65', acao='#F2F3F1', acao_texto='#101210',
              saudavel='#34C77E', atencao='#E8A93D', quebrado='#FF6B5E', sem_dados='#8F948D')

for nome, P in (('CLARO', CLARO), ('ESCURO', ESCURO)):
    print('==', nome)
    for k in ('texto', 'suave', 'saudavel', 'atencao', 'quebrado', 'sem_dados'):
        a, b = r(P[k], P['fundo']), r(P[k], P['elevado'])
        flag = 'OK ' if min(a, b) >= 4.5 else 'FALHA'
        print('  %-10s fundo %5.2f  elevado %5.2f  %s' % (k, a, b, flag))
    print('  %-10s %5.2f  %s' % ('acao/texto', r(P['acao'], P['acao_texto']), 'OK'))
    print('  %-10s %5.2f  (decorativa, sem exigencia)' % ('borda', r(P['borda'], P['fundo'])))
    b = r(P['borda_forte'], P['fundo'])
    print('  %-10s %5.2f  %s (min 3.0)' % ('borda-forte', b, 'OK ' if b >= 3.0 else 'FALHA'))
