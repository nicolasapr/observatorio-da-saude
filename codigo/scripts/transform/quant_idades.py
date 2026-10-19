"""Regenera e verifica os rateios etários usados no PNAE.

Entrada canônica: dados/referencia/quant_idades/quant_idades.csv
Saída: dados/referencia/quant_idades/quant_idades.xlsx

Os rateios são proporções demográficas fixas da estimativa municipal de 2019;
não são matrículas do Censo Escolar. O arredondamento histórico é decimal,
metade para cima, com três casas.
"""
import argparse
from decimal import Decimal, ROUND_HALF_UP

import pandas as pd

from .io_seguro import salvar_excel
from scripts.config import REFERENCIA_QUANT_DIR


def _r3(numerador, denominador):
    if not denominador:
        return pd.NA
    return float(
        (Decimal(int(numerador)) / Decimal(int(denominador)))
        .quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)
    )


def gerar_dataframe() -> pd.DataFrame:
    origem = REFERENCIA_QUANT_DIR / 'quant_idades.csv'
    df = pd.read_csv(origem, sep=';', encoding='latin-1', decimal=',')
    primeira = df.columns[0]
    if primeira != 'Município':
        df = df.rename(columns={primeira: 'Município'})
    # O CSV preserva, depois da tabela, Total e notas de fonte do DATASUS.
    df = df[df['Município'].astype(str).str.match(r'^\d{6}\s+')].copy()
    if len(df) != 5570:
        raise ValueError(f'esperados 5570 municípios; encontrados {len(df)}')
    idades = {idade: f'{idade}  anos' if idade < 10 else f'{idade} anos'
              for idade in range(1, 19)}
    idades[1] = '1  ano'
    faltantes = [c for c in idades.values() if c not in df]
    if faltantes:
        raise ValueError(f'colunas de idade ausentes: {faltantes}')
    for c in idades.values():
        df[c] = pd.to_numeric(df[c], errors='raise').astype('int64')

    pnacn = []
    pnapn4 = []
    pnafn69 = []
    for _, r in df.iterrows():
        a1, a2, a3 = (r[idades[i]] for i in (1, 2, 3))
        a4, a5 = (r[idades[i]] for i in (4, 5))
        f69 = sum(r[idades[i]] for i in range(6, 10))
        f615 = sum(r[idades[i]] for i in range(6, 16))
        pnacn.append(_r3(a2 + a3, a1 + a2 + a3))
        pnapn4.append(_r3(a4, a4 + a5))
        pnafn69.append(_r3(f69, f615))
    df['PNACN'] = pnacn
    df['PNAPN(4)'] = pnapn4
    df['PNAPN(5)'] = [round(1 - x, 3) for x in pnapn4]
    df['PNAFN(6-9)'] = pnafn69
    df['PNAFN(10-15)'] = [round(1 - x, 3) for x in pnafn69]
    return df


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true', help='compara sem sobrescrever')
    args = parser.parse_args()
    novo = gerar_dataframe()
    destino = REFERENCIA_QUANT_DIR / 'quant_idades.xlsx'
    if args.check:
        atual = pd.read_excel(destino)
        if list(atual.columns) != list(novo.columns) or atual.shape != novo.shape:
            print('estrutura divergente')
            return 1
        colunas = ['PNACN', 'PNAPN(4)', 'PNAPN(5)', 'PNAFN(6-9)', 'PNAFN(10-15)']
        maior = max(
            float((pd.to_numeric(atual[c]) - pd.to_numeric(novo[c])).abs().max())
            for c in colunas
        )
        print(f'{len(novo)} municípios; maior diferença nos rateios: {maior:.3g}')
        return 1 if maior else 0
    salvar_excel(novo, destino)
    print(f'{destino}: {len(novo)} municípios')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
