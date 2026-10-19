#!/usr/bin/env python3
"""reconstruir_mes — refaz um sumário mensal do zero a partir dos dez relatórios
brutos daquele mês.

Só deve rodar quando os dez marcadores existem em disco: com menos que isso, o
sumário reconstruído fica pior que o anterior. Foi escrito para recuperar dois
arquivos corrompidos por processo interrompido no meio da gravação.

Uso: python3 ../analise/reconstruir_mes.py 2016 MAIO Crianças_de_5_a_9_anos
"""
import sys
import unicodedata
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent / 'codigo'
sys.path.insert(0, str(RAIZ))
from scripts.config import SISVAN_MENSAIS_DIR, COLUNAS_CADASTRAIS   # noqa: E402
from scripts.extract.sisvan import HABITOS                          # noqa: E402
from scripts.transform.io_seguro import salvar_excel                # noqa: E402
from scripts.transform.normalizacao import normalizar_col           # noqa: E402

_COLS = ['regiao', 'codigo_UF', 'UF', 'codigo_IBGE', 'municipio',
         'total_que', 'percentual', 'total_all']


def ler(caminho):
    d = pd.read_html(str(caminho), thousands='.', decimal=',')[0]
    d.columns = _COLS
    d = d[pd.to_numeric(d['codigo_IBGE'], errors='coerce').notna()].copy()
    d['codigo_IBGE'] = pd.to_numeric(d['codigo_IBGE'], errors='coerce').astype('int64')
    for c in ('total_que', 'total_all'):
        d[c] = pd.to_numeric(d[c], errors='coerce')
    return d


def reconstruir(ano: int, mes: str, faixa: str) -> dict:
    pasta = SISVAN_MENSAIS_DIR / str(ano) / mes / faixa
    brutos = {}
    for h in HABITOS:
        alvo = unicodedata.normalize('NFC', h[:60].replace('/', '_')) + '.xls'
        achado = next((p for p in pasta.glob('*.xls')
                       if unicodedata.normalize('NFC', p.name) == alvo), None)
        if achado is None:
            raise FileNotFoundError(f'falta o bruto de "{h[:40]}" em {pasta}')
        brutos[h] = ler(achado)

    base = pd.concat([d[list(COLUNAS_CADASTRAIS)] for d in brutos.values()])
    sm = base.drop_duplicates(subset=['codigo_IBGE']).sort_values('codigo_IBGE').reset_index(drop=True)
    for h, d in brutos.items():
        suf = normalizar_col(f'total_que_{h}')[len('total_que_'):]
        sm[f'total_que_{suf}'] = sm.codigo_IBGE.map(dict(zip(d.codigo_IBGE, d.total_que)))
        sm[f'total_all_{suf}'] = sm.codigo_IBGE.map(dict(zip(d.codigo_IBGE, d.total_all)))
        sm[f'percentual_que_{suf}'] = (sm[f'total_que_{suf}']
                                       / sm[f'total_all_{suf}'].replace(0, pd.NA))
    destino = SISVAN_MENSAIS_DIR / str(ano) / mes / f'sumario_habitos_{faixa}.xlsx'
    salvar_excel(sm, destino)
    return {'municipios': len(sm), 'marcadores': len(brutos), 'destino': str(destino)}


if __name__ == '__main__':
    ano, mes, faixa = int(sys.argv[1]), sys.argv[2], sys.argv[3]
    print(reconstruir(ano, unicodedata.normalize('NFC', mes), unicodedata.normalize('NFC', faixa)))
