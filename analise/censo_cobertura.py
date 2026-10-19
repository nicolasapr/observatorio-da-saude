#!/usr/bin/env python3
"""censo_cobertura — registra a cobertura de cada célula analítica SISVAN.

Conta, para cada (ano, mês, faixa, marcador), quantos municípios têm
``total_all > 0`` no sumário mensal e gera ``analise/cobertura.csv``.

A variação histórica entre meses de um mesmo ano é apenas um indicador
descritivo: a cobertura do SISVAN cresceu muito ao longo da década. A decisão
operacional de que um relatório está faltando é feita exclusivamente por
``fila_download.py``, que compara os dez marcadores do *mesmo* mês e faixa,
pois eles vêm do mesmo questionário.
"""
import sys
from pathlib import Path
RAIZ = Path(__file__).resolve().parent.parent / 'codigo'
sys.path.insert(0, str(RAIZ))
import pandas as pd
from scripts.config import SISVAN_MENSAIS_DIR
from scripts.transform.normalizacao import normalizar_col

MESES = ['JANEIRO','FEVEREIRO','MARÇO','ABRIL','MAIO','JUNHO','JULHO',
         'AGOSTO','SETEMBRO','OUTUBRO','NOVEMBRO','DEZEMBRO']
FAIXAS = ['Crianças_de_2_a_4_anos','Crianças_de_5_a_9_anos','Adolescentes']
HABITOS = {
 'refeicoes_principais':'Hábito de realizar no mínimo as três refeições principais do dia',
 'refeicoes_tv':'Hábito de realizar as refeições assistindo à televisão',
 'feijao':'Consumo de feijão','fruta':'Consumo de fruta',
 'verduras_legumes':'Consumo de verduras e legumes',
 'ultraprocessados':'Consumo de Alimentos Ultraprocessados',
 'hamburguer_embutidos':'Consumo de hambúrguer e/ou embutidos',
 'bebidas_adocadas':'Consumo de bebidas adoçadas',
 'macarrao_salgadinho':'Consumo de macarrão instantâneo, salgadinho de pacote ou biscoito salgado',
 'biscoito_doces':'Consumo de biscoito recheado, doces ou guloseimas'}

import sys as _s
ANOS = [int(a) for a in _s.argv[1:]] or list(range(2015, 2025))
linhas = []
for ano in ANOS:
    for mi, mes in enumerate(MESES, 1):
        for faixa in FAIXAS:
            p = SISVAN_MENSAIS_DIR / str(ano) / mes / f'sumario_habitos_{faixa}.xlsx'
            if not p.exists():
                for slug in HABITOS:
                    linhas.append(dict(ano=ano, mes=mi, faixa=faixa, slug=slug,
                                       municipios=0, validas=0, existe=0))
                continue
            df = pd.read_excel(p)
            df.columns = [normalizar_col(c) for c in df.columns]
            for slug, hab in HABITOS.items():
                col = normalizar_col(f'total_all_{hab}')
                if col in df.columns:
                    v = pd.to_numeric(df[col], errors='coerce')
                    linhas.append(dict(ano=ano, mes=mi, faixa=faixa, slug=slug,
                                       municipios=int((v > 0).sum()),
                                       validas=int(v.fillna(0).sum()), existe=1))
                else:
                    linhas.append(dict(ano=ano, mes=mi, faixa=faixa, slug=slug,
                                       municipios=0, validas=0, existe=1))

c = pd.DataFrame(linhas)
_out = Path(__file__).parent / 'cobertura.csv'
if len(ANOS) < 10 and _out.exists():
    c = pd.concat([pd.read_csv(_out), c], ignore_index=True)
    c = c.drop_duplicates(subset=['ano','mes','faixa','slug'], keep='last')
c = c.sort_values(['faixa','slug','ano','mes'])
c.to_csv(_out, index=False)
c['mediana_ano'] = c.groupby(['faixa','slug','ano'])['municipios'].transform('median')
c['razao'] = c['municipios'] / c['mediana_ano'].replace(0, pd.NA)
print(f'células: {len(c)}')
print('\ndistribuição de municipios por célula:')
print(c['municipios'].describe().to_string())
print('\ncélulas com razão < 0,5 da mediana do próprio ano (variação histórica de cobertura; não é fila de download):')
sus = c[(c.razao < 0.5) | (c.municipios == 0)]
print(f'{len(sus)} células')
print(sus.groupby('faixa').size().to_string())
print('\npor ano:'); print(sus.groupby('ano').size().to_string())
