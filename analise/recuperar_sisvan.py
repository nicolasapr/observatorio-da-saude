#!/usr/bin/env python3
"""
recuperar_sisvan.py — baixa as 93 combinações (ano, mês, faixa, marcador) cujas
séries ficaram sem dado por falha de coleta.

SUPERADO por analise/baixar_paralelo.py — mantido só como referência.

A conclusão "uma por vez" abaixo estava errada, e a medição de 21/08/2026 que a
sustentava foi refeita no mesmo dia. O lock é da SESSÃO PHP, não do servidor:
três requisições simultâneas compartilhando o mesmo PHPSESSID levaram
120 s / 364 s / >400 s (enfileiraram), enquanto três simultâneas SEM cookie
nenhum levaram 187 s / 182 s / 161 s. Como o relatório é inteiramente
determinado pelo corpo do POST, basta não usar requests.Session() — é isso que
o baixar_paralelo.py faz, e o que reduz as 92 combinações de ~12 h para ~40 min.

Medições que continuam válidas:
  * 120 s a 480 s de resposta por relatório
  * teto de 600 s: acima disso devolve página de erro de ~578 bytes
Por isso: timeout de 900 s e descarte de respostas pequenas.

O REQUEST_TIMEOUT=180 de extract/sisvan.py é menor que o tempo de resposta —
é essa a causa das lacunas. Este script não altera aquele arquivo.

Uso (a partir de codigo/):
    python3 ../analise/recuperar_sisvan.py              # todas as faixas (~12 h)
    python3 ../analise/recuperar_sisvan.py Adolescentes # só o recorte do artigo (~5 h)

É resumível: relança quantas vezes quiser, pula o que já baixou.
Grava direto em dados/sisvan/mensais/{ano}/{MES}/{faixa}/, no lugar certo para
o pipeline. Depois rode criar_sumarios, sumarios_anuais e series_mensais.
"""
import sys, time, csv
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent / 'codigo'
sys.path.insert(0, str(RAIZ))
import requests                                                   # noqa: E402
from scripts.extract.sisvan import (                              # noqa: E402
    _PAYLOAD_FIXO, _FASE_VALOR, _HABITO_VALOR, _MES_VALOR,
    _INDEX_URL, _SUBMIT_URL, _HEADERS,
)
from scripts.config import SISVAN_MENSAIS_DIR                     # noqa: E402

TIMEOUT, PAUSA, MIN_OK = 900, 5, 10_000
LACUNAS = Path(__file__).resolve().parent / 'lacunas.csv'

FAIXA_SLUG = {'2 a 4 anos': 'Crianças_de_2_a_4_anos',
              '5 a 9 anos': 'Crianças_de_5_a_9_anos',
              'Adolescentes': 'Adolescentes'}
MES_NOME = {v: k for k, v in _MES_VALOR.items()}
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

alvo_faixa = sys.argv[1] if len(sys.argv) > 1 else None
tarefas = []
with LACUNAS.open() as f:
    for r in csv.DictReader(f):
        if alvo_faixa and r['faixa'] != alvo_faixa:
            continue
        tarefas.append((int(r['ano']), int(r['mes']), r['faixa'], r['slug']))

print(f'{len(tarefas)} requisições · ~8 min cada · ~{len(tarefas)*8/60:.1f} h')
print('Uma por vez. Pode interromper e relançar.\n')

sess = requests.Session(); sess.headers.update(_HEADERS)
sess.get(_INDEX_URL, timeout=60)
ok = pulados = falhas = 0

for i, (ano, mes, faixa, slug) in enumerate(tarefas, 1):
    fslug, hab = FAIXA_SLUG[faixa], SLUG_HABITO[slug]
    mes_nome = MES_NOME[f'{mes:02d}']
    dest = (SISVAN_MENSAIS_DIR / str(ano) / mes_nome / fslug /
            f"{hab[:60].replace('/', '_')}.xls")
    rot = f'[{i}/{len(tarefas)}] {ano}-{mes:02d} {faixa[:12]:12s} {slug[:22]:22s}'
    if dest.exists() and dest.stat().st_size > MIN_OK:
        print(f'{rot} já existe'); pulados += 1; continue
    dest.parent.mkdir(parents=True, exist_ok=True)
    payload = {**_PAYLOAD_FIXO, 'nuAno': str(ano), 'nuMes[]': f'{mes:02d}',
               'MAIOR_2_ANOS5': _FASE_VALOR[fslug.replace('_', ' ')
                                            if fslug != 'Adolescentes' else 'Adolescentes'],
               'OPCOES_MAIOR_2_ANOS5': _HABITO_VALOR[hab]}
    t0 = time.time()
    try:
        r = sess.post(_SUBMIT_URL, data=payload, timeout=TIMEOUT)
        dt = time.time() - t0
        if len(r.content) < MIN_OK:
            print(f'{rot} ERRO {len(r.content)}B em {dt:.0f}s'); falhas += 1
            sess.get(_INDEX_URL, timeout=60)
        else:
            dest.write_bytes(r.content)
            print(f'{rot} OK {len(r.content)//1024}KB em {dt:.0f}s'); ok += 1
    except Exception as e:
        print(f'{rot} {type(e).__name__}'); falhas += 1
    time.sleep(PAUSA)

print(f'\nbaixados={ok}  já existiam={pulados}  falharam={falhas}')
print('Depois: criar_sumarios -> sumarios_anuais -> series_mensais (e percen)')
