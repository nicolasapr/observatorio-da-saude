#!/usr/bin/env python3
"""Auditoria independente: bruto -> sumário municipal -> séries agregadas.

Além dos números, valida ano, mês, faixa e marcador gravados no conteúdo do
relatório SISVAN. Compara cada município dos brutos preservados e, para todos os
360 sumários, recompõe contagens nacionais, regionais e por UF.
"""
import sys
import unicodedata
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent / 'codigo'
sys.path.insert(0, str(RAIZ))
from scripts.config import SISVAN_MENSAIS_DIR, SISVAN_SERIES_DIR  # noqa: E402
from scripts.extract.sisvan import validar_relatorio  # noqa: E402
from scripts.transform.normalizacao import normalizar_col, normalizar_df  # noqa: E402

MESES = {
    'JANEIRO': 1, 'FEVEREIRO': 2, 'MARÇO': 3, 'ABRIL': 4, 'MAIO': 5,
    'JUNHO': 6, 'JULHO': 7, 'AGOSTO': 8, 'SETEMBRO': 9, 'OUTUBRO': 10,
    'NOVEMBRO': 11, 'DEZEMBRO': 12,
}


def ler_bruto(caminho: Path) -> pd.DataFrame:
    d = pd.read_html(str(caminho), thousands='.', decimal=',')[0]
    if len(d.columns) < 8:
        raise ValueError(f'{len(d.columns)} colunas; esperado ao menos 8')
    d = d.iloc[:, :8].copy()
    d.columns = ['regiao', 'codigo_UF', 'UF', 'codigo_IBGE',
                 'municipio', 'que', 'pct', 'all']
    d['codigo_IBGE'] = pd.to_numeric(d['codigo_IBGE'], errors='coerce')
    d = d.dropna(subset=['codigo_IBGE']).copy()
    d['codigo_IBGE'] = d['codigo_IBGE'].astype('int64')
    for c in ('que', 'all'):
        d[c] = pd.to_numeric(d[c], errors='coerce')
    return d.groupby('codigo_IBGE', as_index=False).agg({'que': 'sum', 'all': 'sum'})


def comparar_brutos(anos: set[int]) -> tuple[int, list[str]]:
    erros = []
    comparados = 0
    for bruto in sorted(SISVAN_MENSAIS_DIR.glob('*/*/*/*.xls')):
        ano = int(bruto.parents[2].name)
        if ano not in anos:
            continue
        mes = unicodedata.normalize('NFC', bruto.parents[1].name)
        faixa = unicodedata.normalize('NFC', bruto.parent.name)
        habito = unicodedata.normalize('NFC', bruto.stem)
        rotulo = f'{ano}/{mes}/{faixa}/{habito[:35]}'
        try:
            validar_relatorio(
                bruto.read_bytes(), ano=ano, mes=mes,
                fase=faixa.replace('_', ' '), habito=habito,
            )
            d = ler_bruto(bruto).rename(columns={'que': 'que_bruto', 'all': 'all_bruto'})
            sumario = bruto.parents[1] / f'sumario_habitos_{faixa}.xlsx'
            sm = normalizar_df(pd.read_excel(sumario))
            sm['codigo_IBGE'] = pd.to_numeric(sm['codigo_IBGE'], errors='coerce').astype('Int64')
            suf = normalizar_col(f'total_que_{habito}').removeprefix('total_que_')
            cq, ca = f'total_que_{suf}', f'total_all_{suf}'
            if cq not in sm or ca not in sm:
                raise ValueError(f'colunas {cq!r}/{ca!r} ausentes')
            s = sm[['codigo_IBGE', cq, ca]].rename(
                columns={cq: 'que_sumario', ca: 'all_sumario'}
            )
            # O sumário é a união dos municípios de dez marcadores; é normal
            # haver uma linha cadastral cuja combinação específica esteja vazia.
            s = s.dropna(subset=['que_sumario', 'all_sumario'], how='all')
            j = d.merge(s, on='codigo_IBGE', how='outer', indicator=True)
            numericas = ['que_bruto', 'all_bruto', 'que_sumario', 'all_sumario']
            j[numericas] = j[numericas].apply(pd.to_numeric, errors='coerce')
            divergente = (
                j['_merge'].ne('both')
                | j['que_bruto'].ne(j['que_sumario'])
                | j['all_bruto'].ne(j['all_sumario'])
            )
            if divergente.any():
                amostra = j[divergente].head(3).to_dict('records')
                raise ValueError(f'{int(divergente.sum())} municípios divergentes: {amostra}')
            comparados += 1
        except Exception as exc:
            erros.append(f'{rotulo}: {exc}')
    return comparados, erros


def _comparar_grupo(
    sm: pd.DataFrame,
    serie: pd.DataFrame,
    ano: int,
    mes: int,
    grupo_col: str | None,
    rotulo: str,
    erros: list[str],
) -> None:
    chaves = [] if grupo_col is None else [grupo_col]
    grupos = [(None, sm)] if grupo_col is None else sm.groupby(grupo_col)
    esperado = []
    cols_que = [c for c in sm if c.startswith('total_que_')]
    for chave, bloco in grupos:
        linha = {'ano': ano, 'mes': mes}
        if grupo_col is not None:
            linha[grupo_col] = chave
        for cq in cols_que:
            suf = cq.removeprefix('total_que_')
            ca = f'total_all_{suf}'
            linha[cq] = pd.to_numeric(bloco[cq], errors='coerce').sum()
            linha[ca] = pd.to_numeric(bloco[ca], errors='coerce').sum()
        esperado.append(linha)
    e = pd.DataFrame(esperado)
    o = serie[(serie.ano == ano) & (serie.mes == mes)].copy()
    merge_keys = ['ano', 'mes'] + chaves
    j = e.merge(o, on=merge_keys, how='outer', suffixes=('_esp', '_out'), indicator=True)
    if j['_merge'].ne('both').any():
        erros.append(f'{rotulo}: chaves ausentes/excedentes na série')
        return
    for c in [c for c in e if c.startswith(('total_que_', 'total_all_'))]:
        a = pd.to_numeric(j[f'{c}_esp'], errors='coerce')
        b = pd.to_numeric(j[f'{c}_out'], errors='coerce')
        # ``Series.equals`` também exige dtype idêntico (3897.0 != 3897),
        # embora aqui se comparem valores de contagem. Exige igualdade numérica
        # exata e trata apenas dois ausentes na mesma posição como equivalentes.
        iguais = a.eq(b) | (a.isna() & b.isna())
        if not bool(iguais.all()):
            erros.append(f'{rotulo}: contagem divergente em {c}')
            return


def comparar_series(anos: set[int]) -> tuple[int, list[str]]:
    erros = []
    comparados = 0
    cache = {}
    for caminho in sorted(SISVAN_MENSAIS_DIR.glob('*/*/sumario_habitos_*.xlsx')):
        ano = int(caminho.parent.parent.name)
        if ano not in anos:
            continue
        mes_nome = unicodedata.normalize('NFC', caminho.parent.name.upper())
        mes = MESES.get(mes_nome)
        if mes is None:
            erros.append(f'{caminho}: mês desconhecido')
            continue
        faixa = unicodedata.normalize(
            'NFC', caminho.stem.removeprefix('sumario_habitos_')
        )
        sm = normalizar_df(pd.read_excel(caminho))
        for sufixo, grupo in [('', None), ('_por_regiao', 'regiao'), ('_por_uf', 'UF')]:
            chave = (faixa, sufixo)
            if chave not in cache:
                cache[chave] = pd.read_excel(
                    SISVAN_SERIES_DIR / f'serie_mensal_{faixa}{sufixo}.xlsx'
                )
            _comparar_grupo(
                sm, cache[chave], ano, mes, grupo,
                f'{ano}-{mes:02d}/{faixa}{sufixo}', erros,
            )
        comparados += 1
    return comparados, erros


def main() -> int:
    anos = {int(a) for a in sys.argv[1:]} or set(range(2015, 2025))
    n_brutos, erros_brutos = comparar_brutos(anos)
    n_sumarios, erros_series = comparar_series(anos)
    erros = erros_brutos + erros_series
    print(f'{n_brutos} brutos validados e comparados município a município')
    print(f'{n_sumarios} sumários recompostos nos níveis nacional, região e UF')
    print(f'{len(erros)} divergência(s)')
    for erro in erros[:50]:
        print(' ', erro)
    return 1 if erros else 0


if __name__ == '__main__':
    raise SystemExit(main())
