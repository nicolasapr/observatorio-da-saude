#!/usr/bin/env python3
"""Relê os sumários mensais e imprime as lacunas de lacunas.csv que AINDA faltam.

Saída: JSON pronto para alimentar o downloader paralelo no navegador.
Uma lacuna é considerada resolvida quando o sumário do mês tem a coluna
total_all_{marcador} preenchida para pelo menos 100 municípios.
"""
import csv, json, sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent / 'codigo'
sys.path.insert(0, str(RAIZ))
import pandas as pd
from scripts.config import SISVAN_MENSAIS_DIR
from scripts.transform.normalizacao import normalizar_col

FAIXA_SLUG = {'2 a 4 anos': 'Crianças_de_2_a_4_anos',
              '5 a 9 anos': 'Crianças_de_5_a_9_anos',
              'Adolescentes': 'Adolescentes'}
FAIXA_VAL = {'2 a 4 anos': '1', '5 a 9 anos': '2', 'Adolescentes': '3'}
MES_NOME = {1:'JANEIRO',2:'FEVEREIRO',3:'MARÇO',4:'ABRIL',5:'MAIO',6:'JUNHO',
            7:'JULHO',8:'AGOSTO',9:'SETEMBRO',10:'OUTUBRO',11:'NOVEMBRO',12:'DEZEMBRO'}
SLUG_HABITO = {
 'refeicoes_principais':'Hábito de realizar no mínimo as três refeições principais do dia',
 'refeicoes_tv':'Hábito de realizar as refeições assistindo à televisão',
 'feijao':'Consumo de feijão','fruta':'Consumo de fruta',
 'verduras_legumes':'Consumo de verduras e legumes',
 'ultraprocessados':'Consumo de Alimentos Ultraprocessados',
 'hamburguer_embutidos':'Consumo de hambúrguer e/ou embutidos',
 'bebidas_adocadas':'Consumo de bebidas adoçadas',
 'macarrao_salgadinho':'Consumo de macarrão instantâneo, salgadinho de pacote ou biscoito salgado',
 'biscoito_doces':'Consumo de biscoito recheado, doces ou guloseimas'}
SLUG_VAL = {'refeicoes_principais':'1','refeicoes_tv':'2','feijao':'3','fruta':'4',
            'verduras_legumes':'5','hamburguer_embutidos':'6','bebidas_adocadas':'7',
            'macarrao_salgadinho':'8','biscoito_doces':'9','ultraprocessados':'10'}

MINIMO_MUNICIPIOS = 100
_cache = {}

def sumario(ano, mes_nome, faixa_slug):
    k = (ano, mes_nome, faixa_slug)
    if k not in _cache:
        p = SISVAN_MENSAIS_DIR / str(ano) / mes_nome / f'sumario_habitos_{faixa_slug}.xlsx'
        if not p.exists():
            _cache[k] = None
        else:
            df = pd.read_excel(p)
            df.columns = [normalizar_col(c) for c in df.columns]
            _cache[k] = df
    return _cache[k]

pend, ok = [], 0
for r in csv.DictReader(open(Path(__file__).parent / 'lacunas.csv')):
    ano, mes, faixa, slug = int(r['ano']), int(r['mes']), r['faixa'], r['slug']
    mes_nome, fslug = MES_NOME[mes], FAIXA_SLUG[faixa]
    habito = SLUG_HABITO[slug]
    col = normalizar_col(f'total_all_{habito}')
    df = sumario(ano, mes_nome, fslug)
    preenchidos = 0
    if df is not None and col in df.columns:
        preenchidos = int(pd.to_numeric(df[col], errors='coerce').notna().sum())
    if preenchidos >= MINIMO_MUNICIPIOS:
        ok += 1
        continue
    pend.append({'ano': ano, 'mes': f'{mes:02d}', 'fase': FAIXA_VAL[faixa],
                 'hab': SLUG_VAL[slug],
                 'name': f'{ano}-{mes:02d}_{fslug}_{slug}',
                 'preenchidos': preenchidos})

print(f'# resolvidas: {ok}   pendentes: {len(pend)}', file=sys.stderr)
print(json.dumps(pend, ensure_ascii=False))
