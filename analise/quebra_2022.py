#!/usr/bin/env python3
"""quebra_2022 — evidência de que o degrau de janeiro/2022 é de REGISTRO.

Mede, por mês, quantos municípios reportam ZERO num marcador tendo total_all
normal — isto é, o município enviou a ficha mas aquele item veio vazio.

O marcador "três refeições principais" fica entre 57% e 80% de municípios com
zero de 2016 a 2021 e cai para ~5% em janeiro de 2022, patamar dos outros nove.
"Consumo de Alimentos Ultraprocessados" serve de controle: fica entre 2% e 7%
nos dez anos inteiros. Prevalência que vai de 11,8% para 85,2% em um mês não é
mudança de hábito — é o item passando a ser registrado.

Uso: python3 ../analise/quebra_2022.py [faixa]   (padrão: Adolescentes)
"""
import sys
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent / 'codigo'
sys.path.insert(0, str(RAIZ))
from scripts.config import SISVAN_MENSAIS_DIR                    # noqa: E402
from scripts.transform.normalizacao import normalizar_col        # noqa: E402

MESES = ['JANEIRO', 'FEVEREIRO', 'MARÇO', 'ABRIL', 'MAIO', 'JUNHO', 'JULHO',
         'AGOSTO', 'SETEMBRO', 'OUTUBRO', 'NOVEMBRO', 'DEZEMBRO']
MARCADORES = {
    'refeicoes': 'Hábito de realizar no mínimo as três refeições principais do dia',
    'feijao':    'Consumo de feijão',
    'fruta':     'Consumo de fruta',
    'ultra':     'Consumo de Alimentos Ultraprocessados',   # controle
}

faixa = sys.argv[1] if len(sys.argv) > 1 else 'Adolescentes'
linhas = []
for ano in range(2015, 2025):
    for mi, mes in enumerate(MESES, 1):
        p = SISVAN_MENSAIS_DIR / str(ano) / mes / f'sumario_habitos_{faixa}.xlsx'
        if not p.exists():
            continue
        d = pd.read_excel(p)
        d.columns = [normalizar_col(c) for c in d.columns]
        r = {'ano': ano, 'mes': mi}
        for tag, nome in MARCADORES.items():
            q = pd.to_numeric(d[f'total_que_{nome}'], errors='coerce')
            a = pd.to_numeric(d[f'total_all_{nome}'], errors='coerce')
            m = a > 0
            r[f'{tag}_zeros'] = 100 * float(((q == 0) & m).sum()) / max(int(m.sum()), 1)
            r[f'{tag}_prev'] = 100 * float(q[m].sum()) / max(float(a[m].sum()), 1)
        linhas.append(r)

df = pd.DataFrame(linhas)
df.to_csv(Path(__file__).resolve().parent / f'quebra_2022_{faixa}.csv', index=False)
print(f'{faixa} · média por ano\n')
cols = [f'{t}_zeros' for t in MARCADORES] + ['refeicoes_prev', 'ultra_prev']
print(df.groupby('ano')[cols].mean().round(1).to_string())
print('\ntransição mês a mês, 2021-09 a 2022-03:')
jan = df[((df.ano == 2021) & (df.mes >= 9)) | ((df.ano == 2022) & (df.mes <= 3))]
print(jan[['ano', 'mes'] + cols].round(1).to_string(index=False))
