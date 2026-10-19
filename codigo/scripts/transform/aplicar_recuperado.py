"""
aplicar_recuperado — enxerta um marcador recuperado no sumário mensal existente.

Rodar criar_sumarios numa pasta de mês onde só existe UM arquivo bruto apagaria
os outros nove marcadores. Este módulo faz o oposto: lê o relatório recém-baixado
e substitui apenas as três colunas daquele marcador no sumário já consolidado,
acrescentando municípios que ainda não estavam lá.

Uso:
    from scripts.transform.aplicar_recuperado import aplicar
    aplicar(2022, 'AGOSTO', 'Adolescentes', 'Consumo de Alimentos Ultraprocessados')
"""
import pandas as pd

from scripts.config import SISVAN_MENSAIS_DIR, COLUNAS_CADASTRAIS
from scripts.extract.sisvan import validar_relatorio
from .io_seguro import salvar_excel
from .normalizacao import normalizar_col

_COLS_BRUTO = ['regiao', 'codigo_UF', 'UF', 'codigo_IBGE', 'municipio',
               'total_que', 'percentual', 'total_all']


def ler_relatorio(caminho) -> pd.DataFrame:
    """Lê o .xls do SISVAN respeitando a notação numérica brasileira."""
    df = pd.read_html(str(caminho), thousands='.', decimal=',')[0]
    if len(df.columns) < len(_COLS_BRUTO):
        raise ValueError(f'{caminho}: esperava ao menos {len(_COLS_BRUTO)} colunas, veio {len(df.columns)}')
    df = df.iloc[:, :len(_COLS_BRUTO)].copy()
    df.columns = _COLS_BRUTO
    df = df[pd.to_numeric(df['codigo_IBGE'], errors='coerce').notna()].copy()
    df['codigo_IBGE'] = pd.to_numeric(df['codigo_IBGE'], errors='coerce').astype('Int64')
    for c in ('total_que', 'total_all'):
        df[c] = pd.to_numeric(df[c], errors='coerce')
    return df


def aplicar(ano: int, mes: str, faixa_slug: str, habito: str) -> dict:
    pasta = SISVAN_MENSAIS_DIR / str(ano) / mes
    bruto = pasta / faixa_slug / f"{habito[:60].replace('/', '_')}.xls"
    sumario = pasta / f'sumario_habitos_{faixa_slug}.xlsx'
    if not bruto.exists():
        raise FileNotFoundError(bruto)
    if not sumario.exists():
        raise FileNotFoundError(sumario)

    validar_relatorio(
        bruto.read_bytes(), ano=ano, mes=mes,
        fase=faixa_slug.replace('_', ' '), habito=habito,
    )

    novo = ler_relatorio(bruto)
    sm = pd.read_excel(sumario)
    sm.columns = [normalizar_col(c) for c in sm.columns]
    sm['codigo_IBGE'] = pd.to_numeric(sm['codigo_IBGE'], errors='coerce').astype('Int64')

    suf = normalizar_col(f'total_que_{habito}')[len('total_que_'):]
    cq, cp, ca = f'total_que_{suf}', f'percentual_que_{suf}', f'total_all_{suf}'

    antes_mun = len(sm)
    antes_val = float(pd.to_numeric(sm[ca], errors='coerce').sum()) if ca in sm else 0.0

    # municípios do relatório que ainda não constam no sumário
    faltantes = novo[~novo.codigo_IBGE.isin(set(sm.codigo_IBGE.dropna()))]
    if len(faltantes):
        linhas = faltantes[COLUNAS_CADASTRAIS].copy()
        sm = pd.concat([sm, linhas], ignore_index=True)

    mapa_q = dict(zip(novo.codigo_IBGE, novo.total_que))
    mapa_a = dict(zip(novo.codigo_IBGE, novo.total_all))
    sm[cq] = sm.codigo_IBGE.map(mapa_q)
    sm[ca] = sm.codigo_IBGE.map(mapa_a)
    sm[cp] = sm[cq] / sm[ca].replace(0, pd.NA)

    ordem = list(COLUNAS_CADASTRAIS) + [c for c in sm.columns if c not in COLUNAS_CADASTRAIS]
    sm = sm[ordem]
    salvar_excel(sm, sumario)
    return {'municipios_antes': antes_mun, 'municipios_depois': len(sm),
            'acrescentados': len(faltantes),
            'validas_antes': antes_val,
            'validas_depois': float(pd.to_numeric(sm[ca], errors='coerce').sum())}
