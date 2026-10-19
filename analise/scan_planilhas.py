#!/usr/bin/env python3
"""Varredura estrutural de todas as planilhas de dados/. Resumível."""
import sys, json, re, hashlib, warnings
from pathlib import Path
import pandas as pd
warnings.filterwarnings('ignore')

RAIZ  = Path(__file__).resolve().parent.parent
DADOS = RAIZ / 'dados'
OUT   = Path(__file__).resolve().parent / 'scan_planilhas.jsonl'
LIMITE_SEG = float(sys.argv[1]) if len(sys.argv) > 1 else 33.0

import time
t0 = time.time()

feitos = set()
if OUT.exists():
    for ln in OUT.open():
        try: feitos.add(json.loads(ln)['path'])
        except Exception: pass

todos = sorted(p for p in DADOS.rglob('*.xlsx') if not p.name.startswith('~$'))
pend  = [p for p in todos if str(p.relative_to(DADOS)) not in feitos]
print(f'total={len(todos)}  feitos={len(feitos)}  pendentes={len(pend)}')

CAD = ['regiao','codigo_UF','UF','codigo_IBGE','municipio']

def familia(rel):
    s = re.sub(r'20\d\d', '{ano}', rel)
    s = re.sub(r'\{ano\}_\{ano\}', '{ano}', s)
    s = re.sub(r'/(JANEIRO|FEVEREIRO|MAR.O|ABRIL|MAIO|JUNHO|JULHO|AGOSTO|SETEMBRO|OUTUBRO|NOVEMBRO|DEZEMBRO)/', '/{MES}/', s)
    return s

n = 0
with OUT.open('a') as fo:
    for p in pend:
        if time.time() - t0 > LIMITE_SEG: break
        rel = str(p.relative_to(DADOS))
        r = {'path': rel, 'familia': familia(rel), 'bytes': p.stat().st_size}
        try:
            df = pd.read_excel(p)
            r['linhas'], r['colunas'] = len(df), len(df.columns)
            cols = list(df.columns)
            r['col_hash'] = hashlib.md5('|'.join(map(str, cols)).encode()).hexdigest()[:10]
            r['cadastrais_ok'] = all(c in cols for c in CAD)
            hab = sorted({c[len('total_que_'):] for c in cols if str(c).startswith('total_que_')})
            r['n_marcadores'] = len(hab)
            r['extras'] = [c for c in cols if not str(c).startswith(('total_que_','total_all_','percentual_que_')) and c not in CAD]
            if 'codigo_IBGE' in cols:
                k = df['codigo_IBGE'].dropna()
                r['municipios'] = int(k.nunique()); r['dup_codigo_IBGE'] = int(len(k) - k.nunique())
            viol = zerados = 0
            for h in hab:
                q, a = f'total_que_{h}', f'total_all_{h}'
                if q in cols and a in cols:
                    Q = pd.to_numeric(df[q], errors='coerce'); A = pd.to_numeric(df[a], errors='coerce')
                    viol += int((Q > A).sum())
                    if (A.fillna(0) == 0).all(): zerados += 1
            r['linhas_que_maior_all'] = viol
            r['marcadores_zerados'] = zerados
            r['ok'] = True
        except Exception as e:
            r['ok'] = False; r['erro'] = f'{type(e).__name__}: {e}'[:160]
        fo.write(json.dumps(r, ensure_ascii=False) + '\n'); fo.flush(); n += 1
print(f'processados nesta rodada: {n}  | restam: {len(pend)-n}')
