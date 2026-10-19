"""
mk — Mann-Kendall (original, Hamed-Rao e sazonal) e declividade de Sen.

Implementado em numpy puro porque a VM onde o pipeline roda não tem scipy nem
pymannkendall e não tem rede para instalá-los. Os resultados são conferidos
contra o pymannkendall em `analise/conferir_mk.py`.

Dois cuidados que a implementação de prateleira NÃO tem e que já produziram
erro neste projeto:

  * a declividade de Sen precisa do Δt REAL entre observações. pymannkendall
    usa np.arange(n) — posição, não tempo. Com meses faltando, isso comprime a
    inclinação. Aqui o tempo entra em meses de calendário.
  * o teste sazonal precisa agrupar por mês de calendário. Aplicar period=12
    sobre um vetor já sem os faltantes desalinha os meses depois da primeira
    lacuna. Aqui o agrupamento é pelo mês real.
"""
import math
from collections import defaultdict
from statistics import NormalDist

import numpy as np


def _phi(z):
    """Cauda da normal padrão."""
    return 0.5 * math.erfc(z / math.sqrt(2))


def _S_e_var(x):
    """Estatística S de Kendall e sua variância com correção de empates."""
    n = len(x)
    S = 0
    for i in range(n - 1):
        S += np.sign(x[i + 1:] - x[i]).sum()
    _, cont = np.unique(x, return_counts=True)
    emp = sum(t * (t - 1) * (2 * t + 5) for t in cont if t > 1)
    var = (n * (n - 1) * (2 * n + 5) - emp) / 18.0
    return float(S), float(var)


def _z_p(S, var):
    if var <= 0:
        return 0.0, 1.0
    if S > 0:
        z = (S - 1) / math.sqrt(var)
    elif S < 0:
        z = (S + 1) / math.sqrt(var)
    else:
        z = 0.0
    return z, 2 * _phi(abs(z))


def _tau_b(x, S):
    """Tau-b: corrige o denominador pelos empates."""
    n = len(x)
    _, cont = np.unique(x, return_counts=True)
    n0 = n * (n - 1) / 2
    n1 = sum(t * (t - 1) / 2 for t in cont if t > 1)
    den = math.sqrt((n0 - n1) * n0)
    return S / den if den else 0.0


def sen(t, x):
    """Declividade de Sen usando o tempo real t (mesma unidade da saída)."""
    n = len(x)
    decl = [(x[j] - x[i]) / (t[j] - t[i])
            for i in range(n - 1) for j in range(i + 1, n) if t[j] != t[i]]
    return float(np.median(decl)) if decl else float('nan')


def _postos_medios(x):
    """Equivalente a scipy.stats.rankdata(method='average'), em numpy puro."""
    x = np.asarray(x, float)
    ordem = np.argsort(x, kind='mergesort')
    postos = np.empty(len(x), float)
    inicio = 0
    while inicio < len(x):
        fim = inicio + 1
        while fim < len(x) and x[ordem[fim]] == x[ordem[inicio]]:
            fim += 1
        # postos são 1..n; empates recebem a média das posições inclusivas.
        postos[ordem[inicio:fim]] = ((inicio + 1) + fim) / 2.0
        inicio = fim
    return postos


def original(t, x):
    x = np.asarray(x, float)
    S, var = _S_e_var(x)
    z, p = _z_p(S, var)
    return {'n': len(x), 'S': S, 'z': z, 'p': p, 'tau': _tau_b(x, S),
            'sen': sen(np.asarray(t, float), x)}


def hamed_rao(t, x, alpha=0.05):
    """Variância de S corrigida pela autocorrelação da série destendenciada.

    Segue Hamed & Rao (1998): destendencia pela declividade de Sen, calcula a
    autocorrelação dos POSTOS do resíduo, mantém apenas as significativas e
    infla a variância pelo fator n/n*.
    """
    x = np.asarray(x, float)
    t = np.asarray(t, float)
    n = len(x)
    S, var = _S_e_var(x)
    b = sen(t, x)
    # +1 mantém a mesma origem numérica da implementação de referência. A
    # constante não altera postos em aritmética exata, mas evita que empates
    # matemáticos sejam quebrados por arredondamento de ponto flutuante.
    res = x - b * (t - t[0] + 1)
    postos = _postos_medios(res)
    postos -= postos.mean()
    denom = (postos ** 2).sum()

    soma = 0.0
    limite_rho = NormalDist().inv_cdf(1 - alpha / 2) / math.sqrt(n)
    for i in range(1, n):
        rho = float((postos[:n - i] * postos[i:]).sum() / denom) if denom else 0.0
        # filtro de significância bicaudal para rho (Hamed & Rao)
        if abs(rho) <= limite_rho:
            continue
        soma += (n - i) * (n - i - 1) * (n - i - 2) * rho
    fator = 1 + (2.0 / (n * (n - 1) * (n - 2))) * soma if n > 2 else 1.0
    if fator <= 0:
        raise ValueError(
            f'fator de correção de Hamed-Rao não positivo ({fator:.6g}); '
            'a estatística não é definida para esta série'
        )
    var_c = var * fator
    z, p = _z_p(S, var_c)
    return {'n': n, 'z': z, 'p': p, 'fator_var': fator, 'sen': b}


def sazonal(meses, x, t=None):
    """Mann-Kendall sazonal de Hirsch-Slack-Smith agrupando por mês REAL."""
    x = np.asarray(x, float)
    grupos = defaultdict(list)
    for m, v in zip(meses, x):
        grupos[int(m)].append(v)
    S = var = 0.0
    for m, vals in grupos.items():
        if len(vals) < 2:
            continue
        s, v = _S_e_var(np.asarray(vals, float))
        S += s
        var += v
    z, p = _z_p(S, var)
    out = {'n': len(x), 'estacoes': len(grupos), 'S': S, 'z': z, 'p': p}
    if t is not None:
        # declividade sazonal: mediana das declividades DENTRO de cada mês
        decl = []
        tt = np.asarray(t, float)
        for m in grupos:
            idx = [k for k, mm in enumerate(meses) if int(mm) == m]
            for a in range(len(idx) - 1):
                for b_ in range(a + 1, len(idx)):
                    i, j = idx[a], idx[b_]
                    if tt[j] != tt[i]:
                        decl.append((x[j] - x[i]) / (tt[j] - tt[i]))
        out['sen'] = float(np.median(decl)) if decl else float('nan')
    return out


def classificar(p, z, alpha=0.05):
    if p >= alpha:
        return 'sem tendência'
    return 'crescente' if z > 0 else 'decrescente'
