#!/usr/bin/env python3
"""triagem_series — Mann-Kendall em todas as séries mensais 2015-01..2024-12.

Roda o teste original, o de Hamed-Rao (autocorrelação) e o sazonal de
Hirsch-Slack-Smith, mais a declividade de Sen em pontos percentuais por ano.

Também mede a QUEBRA ESTRUTURAL entre 2015-2021 e 2022-2024: o SISVAN mudou o
formulário de marcadores de consumo alimentar na virada de 2021 para 2022, e em
alguns marcadores isso desloca o nível da série. Uma tendência estimada por cima
da quebra mede a mudança de instrumento, não a de comportamento.

Saída: analise/triagem_series.csv
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'codigo'))
import mk                                                        # noqa: E402
from scripts.config import SISVAN_SERIES_DIR                     # noqa: E402

FAIXAS = ['Adolescentes', 'Crianças_de_2_a_4_anos', 'Crianças_de_5_a_9_anos']
COD = {'Consumo de Alimentos Ultraprocessados': 'ultraprocessados',
       'Consumo de bebidas adoçadas': 'bebidas_adocadas',
       'Consumo de biscoito recheado doces ou guloseimas': 'biscoito_doces',
       'Consumo de feijão': 'feijao',
       'Consumo de fruta': 'fruta',
       'Consumo de hambúrguer eou embutidos': 'hamburguer_embutidos',
       'Consumo de macarrão instantâneo salgadinho de pacote ou biscoito salgado': 'macarrao_salgadinho',
       'Consumo de verduras e legumes': 'verduras_legumes',
       'Hábito de realizar as refeições assistindo à televisão': 'refeicoes_tv',
       'Hábito de realizar no mínimo as três refeições principais do dia': 'refeicoes_principais'}


def analisar(df, faixa, nivel, grupo):
    df = df.sort_values(['ano', 'mes'])
    t = ((df.ano - 2015) * 12 + (df.mes - 1)).values.astype(float)
    meses = df.mes.values
    pre = df.ano <= 2021
    linhas = []
    for nome, slug in COD.items():
        col = f'percentual_que_{nome}'
        if col not in df.columns:
            continue
        x = (df[col] * 100).values.astype(float)
        if np.isnan(x).any() or len(x) < 60:
            continue
        o = mk.original(t, x)
        h = mk.hamed_rao(t, x)
        s = mk.sazonal(meses, x, t)
        salto = float(x[~pre.values].mean() - x[pre.values].mean())
        linhas.append({
            'nivel': nivel, 'grupo': grupo, 'faixa': faixa, 'marcador': slug,
            'n': o['n'], 'media': x.mean(), 'dp': x.std(ddof=1),
            'inicio12': x[:12].mean(), 'fim12': x[-12:].mean(),
            'tau': o['tau'], 'mk_z': o['z'], 'mk_p': o['p'],
            'sen_ano': o['sen'] * 12, 'mk_classe': mk.classificar(o['p'], o['z']),
            'hr_z': h['z'], 'hr_p': h['p'], 'hr_classe': mk.classificar(h['p'], h['z']),
            'sz_z': s['z'], 'sz_p': s['p'], 'sz_sen_ano': s['sen'] * 12,
            'sz_classe': mk.classificar(s['p'], s['z']),
            'salto_2022': salto,
            'robusta': (o['p'] < .05 and h['p'] < .05 and s['p'] < .05
                        and mk.classificar(o['p'], o['z']) == mk.classificar(s['p'], s['z'])),
        })
    return linhas


todas = []
for faixa in FAIXAS:
    nac = pd.read_excel(SISVAN_SERIES_DIR / f'serie_mensal_{faixa}.xlsx')
    todas += analisar(nac, faixa, 'nacional', 'BRASIL')
    reg = pd.read_excel(SISVAN_SERIES_DIR / f'serie_mensal_{faixa}_por_regiao.xlsx')
    for g, sub in reg.groupby('regiao'):
        todas += analisar(sub, faixa, 'regiao', g)

res = pd.DataFrame(todas)
res.to_csv(Path(__file__).resolve().parent / 'triagem_series.csv', index=False)
print(f'{len(res)} séries testadas')
print(f"robustas (MK, Hamed-Rao e sazonal concordando, p<0,05): {int(res.robusta.sum())}")
print('\nquebra 2022 — marcadores com |salto| > 10 p.p.:')
q = res[res.salto_2022.abs() > 10]
print(q.groupby('marcador')['salto_2022'].agg(['count', 'mean']).round(1).to_string())
