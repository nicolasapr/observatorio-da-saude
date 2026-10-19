#!/usr/bin/env python3
"""
verificar_comportamento.py — exercita o comportamento de cada módulo do pipeline
contra os dados reais, verificando invariantes. Não inspeciona arquivos de saída
antigos: roda as funções.

Uso (a partir de codigo/):  python3 ../analise/verificar_comportamento.py [grupo]
Grupos: normalizacao transform extract load dados  (vazio = todos)
"""
import sys, warnings, glob, os
from pathlib import Path
os.chdir(Path(__file__).resolve().parents[1])
warnings.filterwarnings('ignore')
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'codigo'))
import pandas as pd

OK = FALHA = 0
def checa(nome, cond, detalhe=''):
    global OK, FALHA
    if cond: OK += 1;    print(f'  [ok]    {nome}' + (f'  {detalhe}' if detalhe else ''))
    else:    FALHA += 1; print(f'  [FALHA] {nome}  {detalhe}')

grupo = sys.argv[1] if len(sys.argv) > 1 else 'todos'
def roda(g): return grupo in ('todos', g)

# ─────────────────────────────────────────────────────────── normalizacao
if roda('normalizacao'):
    print('\n== transform/normalizacao ==')
    from scripts.transform.normalizacao import normalizar_col, normalizar_df
    alvo_h = 'total_que_Consumo de hambúrguer eou embutidos'
    checa('variante e_ou converge',
          normalizar_col('total_que_Consumo de hambúrguer e_ou embutidos') == alvo_h)
    checa('variante com vírgula converge',
          normalizar_col('total_que_Consumo de biscoito recheado, doces ou guloseimas')
          == 'total_que_Consumo de biscoito recheado doces ou guloseimas')
    checa('truncado 60 car expande (macarrão)',
          normalizar_col('total_que_Consumo de macarrão instantâneo, salgadinho de pacote ou bis')
          .endswith('biscoito salgado'))
    checa('truncado 60 car expande (refeições)',
          normalizar_col('total_que_Hábito de realizar no mínimo as três refeições principais do')
          .endswith('principais do dia'))
    checa('nome já normalizado é idempotente', normalizar_col(alvo_h) == alvo_h)
    d = pd.DataFrame({'total_que_Consumo de hambúrguer e_ou embutidos':[10,20],
                      'total_que_Consumo de hambúrguer eou embutidos':[1,2],
                      'municipio':['A','B']})
    r = normalizar_df(d)
    checa('colisão funde em 1 coluna', list(r.columns).count(alvo_h) == 1)
    checa('colisão SOMA os contadores', list(r[alvo_h]) == [11,22], f'obtido {list(r[alvo_h])}')

# ─────────────────────────────────────────────────────────────── transform
if roda('transform'):
    print('\n== transform/sumarios_anuais — percentual recalculado, não somado ==')
    df = pd.read_excel('dados/sisvan/anuais/2024/sumario_anual_habitos_Adolescentes.xlsx')
    hab = sorted({c[10:] for c in df.columns if c.startswith('total_que_')})
    checa('10 marcadores', len(hab) == 10, f'{len(hab)}')
    piores = []
    for h in hab:
        q = pd.to_numeric(df[f'total_que_{h}'], errors='coerce')
        a = pd.to_numeric(df[f'total_all_{h}'], errors='coerce')
        p = pd.to_numeric(df[f'percentual_que_{h}'], errors='coerce')
        esperado = q / a.replace(0, pd.NA)
        piores.append(float((p - esperado).abs().max()))
    checa('percentual == que/all', max(piores) < 1e-9, f'máx |dif| = {max(piores):.2e}')
    checa('percentual no intervalo [0,1]',
          all(pd.to_numeric(df[f'percentual_que_{h}'], errors='coerce').max() <= 1.0 for h in hab))
    checa('sem código IBGE repetido', len(df) == df.codigo_IBGE.nunique())

    print('\n== transform/sumarios_totais — histórico não soma percentuais ==')
    dh = pd.read_excel('dados/sisvan/historico/sumario_total_habitos_Adolescentes.xlsx')
    hh = sorted({c[10:] for c in dh.columns if c.startswith('total_que_')})
    mx = max(float(pd.to_numeric(dh[f'percentual_que_{h}'], errors='coerce').max()) for h in hh)
    checa('percentual histórico <= 1 (não somado)', mx <= 1.0, f'máx = {mx:.4f}')
    checa('histórico com 10 marcadores', len(hh) == 10, f'{len(hh)}')
    checa('histórico sem IBGE repetido', len(dh) == dh.codigo_IBGE.nunique())

    print('\n== transform/series_mensais — cobertura e razão ==')
    for f in ['Adolescentes','Crianças_de_2_a_4_anos','Crianças_de_5_a_9_anos']:
        s = pd.read_excel(f'dados/sisvan/series/serie_mensal_{f}.xlsx')
        checa(f'{f[:22]:22s} 120 meses', len(s) == 120, f'{len(s)}')
        checa(f'{f[:22]:22s} março presente 10x', int((s.mes == 3).sum()) == 10)
        checa(f'{f[:22]:22s} 12 meses distintos', s.mes.nunique() == 12)
    s = pd.read_excel('dados/sisvan/series/serie_mensal_Adolescentes.xlsx')
    h = 'Consumo de fruta'
    q = pd.to_numeric(s[f'total_que_{h}']); a = pd.to_numeric(s[f'total_all_{h}'])
    p = pd.to_numeric(s[f'percentual_que_{h}'])
    checa('série: percentual == que/all', float((p - q/a).abs().max()) < 1e-3)

    print('\n== transform/percen — junção 1:1 pelo código IBGE ==')
    qi = pd.read_excel('dados/referencia/quant_idades/quant_idades.xlsx')
    qi['codigo_IBGE'] = pd.to_numeric(qi['Município'].astype(str).str.extract(r'^(\d{6})')[0],
                                      errors='coerce')
    for faixa, col in [('2a4','PNACN'), ('5a9','PNAPN(5)'), ('Adolescentes','PNAFN(10-15)')]:
        pc = pd.read_excel(f'dados/pnaes/percen/{faixa}/PNAES_Percen_{faixa}_2024.xlsx')
        checa(f'percen {faixa[:12]:12s} sem IBGE repetido', len(pc) == pc.codigo_IBGE.nunique())
        j = pc[['codigo_IBGE', col]].merge(qi[['codigo_IBGE', col]], on='codigo_IBGE',
                                           suffixes=('_p','_q'))
        d = (pd.to_numeric(j[col+'_p'], errors='coerce')
             - pd.to_numeric(j[col+'_q'], errors='coerce')).abs().max()
        checa(f'percen {faixa[:12]:12s} rateio idêntico à fonte', d < 1e-12, f'máx {d:.2e}')


# ───────────────────────────────────────────────────────────────── pnae
if roda('pnae'):
    print('\n== transform/pnaes_redes — leitura e mapeamento ==')
    import logging; logging.disable(logging.CRITICAL)
    from scripts.transform.pnaes_redes import (
        PNAESRedesTransformer, _parse_valor, _normalizar_municipio,
        _chave_municipio, _is_secretaria, _EXCECOES_CODIGO,
    )
    checa('_parse_valor BR "54.000,00"', _parse_valor('54.000,00') == 54000.0)
    checa('_parse_valor numérico', _parse_valor(1234.5) == 1234.5)
    checa('_parse_valor vazio -> 0', _parse_valor(None) == 0.0)
    checa('remove prefixo PREFEITURA MUNICIPAL DE',
          _normalizar_municipio('PREFEITURA MUNICIPAL DE SAO PAULO') == 'SAO PAULO')
    checa('remove acento', _normalizar_municipio('Pref. de Belém') == 'BELEM')
    checa('pontuação não altera chave municipal',
          _chave_municipio("SANTA LUZIA D'OESTE") == _chave_municipio('SANTA LUZIA DOESTE'))
    checa('detecta secretaria estadual', _is_secretaria('SECRETARIA DE EDUCACAO DO PARA'))
    checa('detecta abreviação SECR estadual',
          _is_secretaria('SECR DE ESTADO DA EDUCACAO DO RN'))
    checa('prefeitura não é secretaria', not _is_secretaria('PREFEITURA DE BELEM'))
    checa('exceção administrativa de Aparecida documentada',
          _EXCECOES_CODIGO[('SP', 'ESTANCIATURISTICORELIGIOSA')] == 350250)
    t = PNAESRedesTransformer()
    faltando = []
    for a in range(2015, 2025):
        r = t._carregar_redes(a)
        if r is None: faltando.append(a)
    checa('10 anos de Redes carregam', not faltando, f'faltam {faltando}')
    r = t._carregar_redes(2016)
    checa('PN+FN mapeado para PNAFN', 'PN+FN' not in set(r.ACAO))
    checa('coluna municipio criada', 'municipio' in r.columns)
    checa('secretarias com municipio vazio', (r[r._is_sec].municipio == '').all())

    print('\n== transform/pnaes — fórmulas do TOTAL ==')
    for faixa, cols, tot in [('2a4', ['PNACN','valor_pago_CR','PNAPN(4)','valor_pago_PE'], 'TOTAL'),
                             ('5a9', ['PNAPN(5)','valor_pago_PN','PNAFN(6-9)','valor_pago_FN'], 'TOTAL')]:
        d = pd.read_excel(f'dados/pnaes/finais/{faixa}/PNAES_valores_{faixa}_2024_ajustado.xlsx')
        n = lambda c: pd.to_numeric(d[c], errors='coerce')
        esp = (n(cols[0])*n(cols[1]) + n(cols[2])*n(cols[3])).fillna(0)
        checa(f'{faixa}: TOTAL = soma dos produtos',
              float((n(tot)-esp).abs().max()) < 1e-6, f'máx {float((n(tot)-esp).abs().max()):.2e}')
        checa(f'{faixa}: sem IBGE repetido', len(d) == d.codigo_IBGE.nunique())
    for ano in range(2015, 2025):
        d = pd.read_excel(
            f'dados/pnaes/finais/Adolescentes/PNAES_valores_Adolescentes_{ano}_ajustado.xlsx'
        )
        n = lambda c: pd.to_numeric(d[c], errors='coerce')
        em = n('valor_pago_secretarias_EM').fillna(0) * n('percen_MAT_MED').fillna(0)
        ef = n('valor_pago_FN').fillna(0) * n('percen_MAT_FUND_AF').fillna(0)
        municipal = n('componente_EM_prefeituras').fillna(0)
        esp = municipal + em + ef
        checa(
            f'Adolescentes {ano}: TOTAL_EF ponderado por matrícula',
            float((n('TOTAL_EF') - esp).abs().max()) < 1e-6,
        )
        checa(
            f'Adolescentes {ano}: componentes explícitos',
            float((n('componente_EM_secretarias') - em).abs().max()) < 1e-6
            and float((n('componente_EF_anos_finais') - ef).abs().max()) < 1e-6,
        )
        checa(
            f'Adolescentes {ano}: ensino médio municipal incluído diretamente',
            float((municipal - n('valor_pago_prefeituras_EM').fillna(0)).abs().max()) < 1e-6,
        )
    checa('Adolescentes: sem IBGE repetido', len(d) == d.codigo_IBGE.nunique())
    checa('percen_MAT_* dentro de [0,1]',
          all(n(c).dropna().max() <= 1.0 for c in ['percen_MAT_MED','percen_MAT_FUND','percen_MAT_FUND_AF']))
    faltam_tot = [f for f in sorted(glob.glob('dados/pnaes/finais/*/*.xlsx'))
                  if not ({'TOTAL','TOTAL_EF'} & set(pd.read_excel(f, nrows=0).columns))]
    checa('30 finais têm coluna TOTAL', not faltam_tot, f'{len(faltam_tot)} sem')

# ────────────────────────────────────────────────────────────── extract
if roda('extract'):
    print('\n== extract — configuração e destino (sem rede) ==')
    from scripts.extract.sisvan import (_PAYLOAD_FIXO, _FASE_VALOR, _HABITO_VALOR,
                                        _MES_VALOR, HABITOS, MESES, FASES, REQUEST_TIMEOUT,
                                        identificar_relatorio, validar_relatorio)
    checa('12 meses mapeados', len(_MES_VALOR) == 12)
    checa('3 fases mapeadas', len(_FASE_VALOR) == 3)
    checa('10 hábitos mapeados', len(_HABITO_VALOR) == 10)
    checa('todo HABITO tem valor', all(h in _HABITO_VALOR for h in HABITOS))
    checa('todo MES tem valor', all(m in _MES_VALOR for m in MESES))
    checa('toda FASE tem valor', all(f in _FASE_VALOR for f in FASES))
    checa('valores de hábito são 1..10',
          sorted(int(v) for v in _HABITO_VALOR.values()) == list(range(1, 11)))
    checa('payload agrupa por município', _PAYLOAD_FIXO.get('tpFiltro') == 'M')
    checa('payload UF = TODOS', _PAYLOAD_FIXO.get('coUfIbge') == '99')
    checa('REQUEST_TIMEOUT >= 900 (servidor responde em ~480s)',
          REQUEST_TIMEOUT >= 900, f'atual = {REQUEST_TIMEOUT}')
    amostra = next(Path('dados/sisvan/mensais').glob('*/*/*/*.xls'))
    meta = identificar_relatorio(amostra.read_bytes())
    checa('metadados são lidos do conteúdo do relatório',
          {'ano', 'mes', 'fase', 'habito'} <= set(meta))
    rejeitou = False
    try:
        validar_relatorio(amostra.read_bytes(), ano=meta['ano'], mes=meta['mes'],
                          fase=('Adolescentes' if meta['fase'] != 'Adolescentes'
                                else 'Crianças de 5 a 9 anos'), habito=meta['habito'])
    except ValueError:
        rejeitou = True
    checa('relatório de faixa divergente é rejeitado', rejeitou)
    from scripts.extract.pnaes import _URLS_REDES, _URLS_FEDERAL
    faltam = [a for a in range(2015, 2025) if a not in _URLS_REDES]
    checa('URLs de Redes cobrem 2015-2024', not faltam, f'faltam {faltam}')
    checa('URLs Federal cobrem 2015-2024',
          not [a for a in range(2015, 2025) if a not in _URLS_FEDERAL])
    from scripts.extract.ibge import SIDRA_URL
    checa('SIDRA usa tabela 6579 var 9324',
          '6579' in SIDRA_URL and '9324' in SIDRA_URL and 'N6' in SIDRA_URL)
    from scripts.extract.mec import _URL_PATTERNS, _CSV_KEYWORDS
    checa('MEC tem padrões de URL', len(_URL_PATTERNS) >= 1)
    checa('padrões MEC têm placeholder de ano',
          all('{ano}' in u for u in _URL_PATTERNS))
    checa('MEC procura CSV por palavra-chave', 'basica' in _CSV_KEYWORDS)

# ────────────────────────────────────────────────────────────────── load
if roda('load'):
    print('\n== load/utils — catálogo ==')
    from scripts.load.utils import scan_data_dir, COLUNAS, ANOS
    inv = scan_data_dir()
    checa('catálogo cobre os anos de config', set(inv) == set(ANOS))
    com_dado = [a for a in ANOS if a <= 2024]
    aus = {lbl: [a for a in com_dado if not inv[a][k].exists] for k, lbl in COLUNAS}
    ruins = {k: v for k, v in aus.items() if v}
    checa('nada ausente em 2015-2024', not ruins, f'{ruins}')
    from scripts.config import localizar_redes
    checa('localizar_redes acha os 10 anos',
          all(localizar_redes(a) for a in range(2015, 2025)))

print(f'\n{"="*60}\nOK={OK}  FALHAS={FALHA}')
sys.exit(1 if FALHA else 0)
