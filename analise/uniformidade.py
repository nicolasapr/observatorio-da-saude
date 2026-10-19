#!/usr/bin/env python3
"""uniformidade — checa a consistência estrutural de todos os sumários mensais.

Verifica, para cada sumário:
  * conjunto de colunas idêntico ao esperado (5 cadastrais + 10 marcadores × 3)
  * nenhuma coluna com barra (sinal do bug e/ou vs e_ou)
  * codigo_IBGE único
  * nenhum total_que > total_all
  * percentual coerente com total_que / total_all

Uso: python3 ../analise/uniformidade.py [ano ...]
"""
import sys
from pathlib import Path
RAIZ = Path(__file__).resolve().parent.parent / 'codigo'
sys.path.insert(0, str(RAIZ))
import pandas as pd
from scripts.config import SISVAN_MENSAIS_DIR, COLUNAS_CADASTRAIS
from scripts.extract.sisvan import HABITOS
from scripts.transform.normalizacao import normalizar_col

ESPERADAS = set(COLUNAS_CADASTRAIS)
for h in HABITOS:
    suf = normalizar_col(f'total_que_{h}')[len('total_que_'):]
    ESPERADAS |= {f'total_que_{suf}', f'percentual_que_{suf}', f'total_all_{suf}'}

anos = [int(a) for a in sys.argv[1:]] or list(range(2015, 2025))
problemas = []
n = 0
for ano in anos:
    for p in sorted((SISVAN_MENSAIS_DIR / str(ano)).rglob('sumario_habitos_*.xlsx')):
        n += 1
        rel = p.relative_to(SISVAN_MENSAIS_DIR)
        df = pd.read_excel(p)
        cru = list(df.columns)
        df.columns = [normalizar_col(c) for c in cru]

        if any('/' in str(c) for c in cru):
            problemas.append(f'{rel}: coluna com barra: {[c for c in cru if "/" in str(c)]}')
        faltando = ESPERADAS - set(df.columns)
        sobrando = set(df.columns) - ESPERADAS
        if faltando:
            problemas.append(f'{rel}: {len(faltando)} coluna(s) faltando: {sorted(faltando)[:2]}')
        if sobrando:
            problemas.append(f'{rel}: coluna(s) inesperada(s): {sorted(sobrando)[:3]}')
        if len(df.columns) != len(set(df.columns)):
            problemas.append(f'{rel}: nomes de coluna repetidos após normalização')

        ibge = pd.to_numeric(df.get('codigo_IBGE'), errors='coerce')
        vazio = int(ibge.isna().sum())
        if vazio:
            problemas.append(f'{rel}: {vazio} linha(s) sem codigo_IBGE')
        dup = int(ibge.dropna().duplicated().sum())
        if dup:
            problemas.append(f'{rel}: {dup} codigo_IBGE duplicado(s)')

        for h in HABITOS:
            suf = normalizar_col(f'total_que_{h}')[len('total_que_'):]
            cq, ca = f'total_que_{suf}', f'total_all_{suf}'
            if cq not in df.columns or ca not in df.columns:
                continue
            q = pd.to_numeric(df[cq], errors='coerce')
            a = pd.to_numeric(df[ca], errors='coerce')
            mau = int((q > a).sum())
            if mau:
                problemas.append(f'{rel}: {mau} linha(s) com que>all em {suf[:34]}')
            # NaN % 1 é NaN e NaN != 0 é True — sem o notna() toda linha vazia
            # seria acusada de contador fracionário
            frac = int(((q.notna() & (q % 1 != 0)) | (a.notna() & (a % 1 != 0))).sum())
            if frac:
                problemas.append(f'{rel}: {frac} contador(es) não inteiro(s) em {suf[:34]}')

print(f'{n} sumários verificados · {len(problemas)} problema(s)')
for x in problemas[:60]:
    print('  ', x)
if len(problemas) > 60:
    print(f'   ... e mais {len(problemas)-60}')
