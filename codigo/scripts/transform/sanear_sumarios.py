"""
sanear_sumarios — remove do sumário mensal as linhas que não representam um
município e funde eventuais duplicatas de codigo_IBGE.

Duas anomalias aparecem nos sumários desde antes da recuperação de 2026-08-21
(estão em ~5% dos arquivos, inclusive em meses nunca reprocessados):

  * linhas sem codigo_IBGE ou com código que não tem seis dígitos — sobra da linha "TOTAL ESTADO ..." do relatório
    bruto, que não é um município e não deve entrar em nenhuma agregação;
  * o mesmo codigo_IBGE em duas linhas do mesmo mês, uma delas quase vazia.

Numericamente o efeito é pequeno (as linhas afetadas carregam 1 ou 2 respostas),
mas `sumarios_anuais` agrega POR codigo_IBGE: uma duplicata dentro do mês vira
dupla contagem daquele município, e uma linha sem código é agregada como se
fosse um município fantasma. Melhor eliminar na origem.

A fusão toma o MÁXIMO de cada contador e RECALCULA o percentual — percentual
nunca é somado nem promediado, é sempre soma/soma.

Somar seria o certo se as duas linhas fossem registros distintos do mesmo
município. Não são: o relatório bruto do SISVAN não repete município (conferido),
então a linha extra é uma cópia parcial da mesma linha, e somar infla o total.
A auditoria de ponta a ponta pegou exatamente isso: 2019-12 Adolescentes ficou
com total_all 20.861 contra 20.860 no relatório original. O máximo recupera o
valor da linha completa sem contar duas vezes.
"""
import sys
from pathlib import Path

import pandas as pd

from scripts.config import SISVAN_MENSAIS_DIR, COLUNAS_CADASTRAIS
from .base import BaseTransformer
from .io_seguro import salvar_excel
from .normalizacao import normalizar_col


def sanear(caminho: Path) -> dict:
    df = pd.read_excel(caminho)
    df.columns = [normalizar_col(c) for c in df.columns]
    n0 = len(df)

    ibge = pd.to_numeric(df['codigo_IBGE'], errors='coerce')
    valido = ibge.notna() & ibge.between(100000, 999999)
    sem_codigo = int(ibge.isna().sum())
    codigo_invalido = int((ibge.notna() & ~ibge.between(100000, 999999)).sum())
    df = df[valido].copy()
    df['codigo_IBGE'] = ibge[valido].astype('int64')

    dup = int(df['codigo_IBGE'].duplicated().sum())
    if dup:
        contadores = [c for c in df.columns
                      if c.startswith(('total_que_', 'total_all_'))]
        cadastrais = [c for c in COLUNAS_CADASTRAIS if c != 'codigo_IBGE']
        agg = {c: 'max' for c in contadores}
        agg.update({c: 'first' for c in cadastrais})
        df = (df.groupby('codigo_IBGE', as_index=False)
                .agg(agg))
        for c in contadores:
            if c.startswith('total_que_'):
                suf = c[len('total_que_'):]
                ca, cp = f'total_all_{suf}', f'percentual_que_{suf}'
                if ca in df.columns:
                    df[cp] = df[c] / df[ca].replace(0, pd.NA)

    ordem = list(COLUNAS_CADASTRAIS) + [c for c in df.columns
                                        if c not in COLUNAS_CADASTRAIS]
    df = df[[c for c in ordem if c in df.columns]]
    if sem_codigo or codigo_invalido or dup:
        salvar_excel(df, caminho)
    return {'linhas_antes': n0, 'linhas_depois': len(df),
            'sem_codigo': sem_codigo, 'codigo_invalido': codigo_invalido,
            'duplicatas': dup}


def sanear_todos(anos=None) -> dict:
    anos = anos or range(2015, 2025)
    tot = {'arquivos': 0, 'alterados': 0, 'sem_codigo': 0,
           'codigo_invalido': 0, 'duplicatas': 0}
    for ano in anos:
        base = SISVAN_MENSAIS_DIR / str(ano)
        if not base.exists():
            continue
        for p in sorted(base.rglob('sumario_habitos_*.xlsx')):
            r = sanear(p)
            tot['arquivos'] += 1
            if r['sem_codigo'] or r['codigo_invalido'] or r['duplicatas']:
                tot['alterados'] += 1
                tot['sem_codigo'] += r['sem_codigo']
                tot['codigo_invalido'] += r['codigo_invalido']
                tot['duplicatas'] += r['duplicatas']
                print(f"  {p.relative_to(SISVAN_MENSAIS_DIR)}: "
                      f"-{r['sem_codigo']} sem código, -{r['codigo_invalido']} código(s) inválido(s), "
                      f"-{r['duplicatas']} duplicata(s) "
                      f"({r['linhas_antes']}→{r['linhas_depois']})", flush=True)
    return tot


class SanearSumariosTransformer(BaseTransformer):
    """Higieniza os sumários mensais antes de qualquer agregação."""

    def __init__(self, data_dir=None, output_dir=None):
        super().__init__(data_dir or SISVAN_MENSAIS_DIR, output_dir)

    def transform(self, ano: int) -> None:
        anos = [ano] if ano else self._anos_disponiveis()
        t = sanear_todos(anos)
        self._info('%d sumários · %d alterados · %d sem código · %d código(s) inválido(s) · %d duplicata(s)',
                   t['arquivos'], t['alterados'], t['sem_codigo'],
                   t['codigo_invalido'], t['duplicatas'])


if __name__ == '__main__':
    anos = [int(a) for a in sys.argv[1:]] or None
    t = sanear_todos(anos)
    print(f"\n{t['arquivos']} sumários · {t['alterados']} alterados · "
          f"{t['sem_codigo']} sem código · {t['codigo_invalido']} código(s) inválido(s) · "
          f"{t['duplicatas']} duplicata(s)")
