#!/usr/bin/env python3
"""fila_download — monta a lista de (ano, mês, faixa, marcador) que ainda
precisam ser baixados, a partir de analise/cobertura.csv.

Critério: dentro de um mesmo (ano, mês, faixa) os dez marcadores vêm do MESMO
questionário, logo a cobertura municipal deve ser praticamente idêntica entre
eles. Um marcador abaixo de 90% da mediana dos outros nove é falha de coleta.
Quando a célula inteira está vazia (mediana zero), faltam os dez.

Imprime JSON no formato consumido pelo motor de download no navegador.
"""
import json, sys
from pathlib import Path
import pandas as pd

FAIXA_VAL = {'Crianças_de_2_a_4_anos': '1', 'Crianças_de_5_a_9_anos': '2',
             'Adolescentes': '3'}
SLUG_VAL = {'refeicoes_principais':'1','refeicoes_tv':'2','feijao':'3','fruta':'4',
            'verduras_legumes':'5','hamburguer_embutidos':'6','bebidas_adocadas':'7',
            'macarrao_salgadinho':'8','biscoito_doces':'9','ultraprocessados':'10'}
LIMIAR = 0.90

c = pd.read_csv(Path(__file__).parent / 'cobertura.csv')
c = c.drop_duplicates(subset=['ano', 'mes', 'faixa', 'slug'], keep='last')
c['mediana'] = c.groupby(['ano', 'mes', 'faixa'])['municipios'].transform('median')
c['razao'] = c['municipios'] / c['mediana'].replace(0, pd.NA)

falta = c[(c['mediana'] == 0) | (c['razao'] < LIMIAR)]
falta = falta.sort_values(['faixa', 'ano', 'mes', 'slug'])

fila = [{'ano': int(r.ano), 'mes': f'{int(r.mes):02d}',
         'fase': FAIXA_VAL[r.faixa], 'hab': SLUG_VAL[r.slug],
         'name': f'{int(r.ano)}-{int(r.mes):02d}_{r.faixa}_{r.slug}'
                 .replace('ç', 'c').replace('Ç', 'C').replace('ã', 'a')}
        for r in falta.itertuples()]

# CSV no formato consumido por baixar_paralelo.py e recuperar_sisvan.py
INV_FAIXA = {v: k for k, v in FAIXA_VAL.items()}
INV_SLUG = {v: k for k, v in SLUG_VAL.items()}
import csv
with open(Path(__file__).parent / 'lacunas_v2.csv', 'w', newline='') as fh:
    w = csv.writer(fh)
    w.writerow(['faixa', 'ano', 'mes', 'slug'])
    for r in falta.itertuples():
        w.writerow([{'Crianças_de_2_a_4_anos': '2 a 4 anos',
                     'Crianças_de_5_a_9_anos': '5 a 9 anos',
                     'Adolescentes': 'Adolescentes'}[r.faixa],
                    int(r.ano), int(r.mes), r.slug])

print(f'# {len(fila)} combinações a baixar '
      f'({int((falta.mediana == 0).sum())} de células inteiramente vazias)',
      file=sys.stderr)
print(json.dumps(fila, ensure_ascii=False, separators=(',', ':')))
