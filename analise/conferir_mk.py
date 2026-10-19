#!/usr/bin/env python3
"""Confere a implementação local de MK contra pymannkendall em 180 séries.

Executa as três faixas em nível nacional e regional. Como as séries correntes
têm 120 meses completos, a referência posicional e o calendário real coincidem.
O script termina com erro se Z/p do original, Hamed-Rao ou sazonal divergirem.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pymannkendall as pmk

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'codigo'))
import mk  # noqa: E402
from scripts.config import SISVAN_SERIES_DIR  # noqa: E402

FAIXAS = ['Adolescentes', 'Crianças_de_2_a_4_anos', 'Crianças_de_5_a_9_anos']
TOL_Z = 1e-10
TOL_P = 1e-10


def comparar(nome, local, referencia, erros):
    for campo in ('z', 'p'):
        a = float(local[campo])
        b = float(getattr(referencia, campo))
        tol = TOL_Z if campo == 'z' else TOL_P
        if not np.isclose(a, b, rtol=0, atol=tol):
            erros.append(f'{nome} {campo}: local={a:.12g}, referência={b:.12g}')


def main() -> int:
    erros = []
    testadas = 0
    for faixa in FAIXAS:
        for sufixo, grupo_col in [('', None), ('_por_regiao', 'regiao')]:
            df = pd.read_excel(
                SISVAN_SERIES_DIR / f'serie_mensal_{faixa}{sufixo}.xlsx'
            )
            grupos = [('BRASIL', df)] if grupo_col is None else df.groupby(grupo_col)
            for grupo, serie in grupos:
                serie = serie.sort_values(['ano', 'mes'])
                t = ((serie.ano - 2015) * 12 + serie.mes - 1).to_numpy(float)
                meses = serie.mes.to_numpy()
                for coluna in [c for c in serie if c.startswith('percentual_que_')]:
                    x = serie[coluna].to_numpy(float) * 100
                    nome = f'{faixa}/{grupo}/{coluna.removeprefix("percentual_que_")}'
                    comparar(nome + '/original', mk.original(t, x), pmk.original_test(x), erros)
                    comparar(
                        nome + '/hamed-rao',
                        mk.hamed_rao(t, x),
                        pmk.hamed_rao_modification_test(x),
                        erros,
                    )
                    comparar(
                        nome + '/sazonal',
                        mk.sazonal(meses, x, t),
                        pmk.seasonal_test(x, period=12),
                        erros,
                    )
                    testadas += 1

    print(f'{testadas} séries conferidas contra pymannkendall')
    if erros:
        print(f'{len(erros)} divergência(s):')
        for erro in erros[:30]:
            print(' ', erro)
        return 1
    print('0 divergências')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
