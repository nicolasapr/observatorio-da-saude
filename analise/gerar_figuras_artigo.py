#!/usr/bin/env python3
"""Gera as quatro figuras do artigo RBIC a partir da série auditada."""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from statsmodels.tsa.seasonal import seasonal_decompose
from statsmodels.tsa.statespace.sarimax import SARIMAX

BASE = Path(__file__).resolve().parent
RAIZ = BASE.parent
SAIDA = BASE / 'figuras_artigo'
sys.path.insert(0, str(BASE))
import mk  # noqa: E402

COR = '#16697A'
COR_DESTAQUE = '#D1495B'
COR_CLARA = '#82C0CC'


def _estilo() -> None:
    plt.rcParams.update({
        'font.family': 'DejaVu Sans',
        'font.size': 10,
        'axes.titlesize': 12,
        'axes.labelsize': 10,
        'axes.spines.top': False,
        'axes.spines.right': False,
        'figure.facecolor': 'white',
        'axes.facecolor': 'white',
        'savefig.facecolor': 'white',
    })


def _salvar(fig, nome: str) -> None:
    SAIDA.mkdir(parents=True, exist_ok=True)
    fig.savefig(SAIDA / nome, dpi=220, bbox_inches='tight')
    plt.close(fig)


def carregar() -> tuple[pd.DataFrame, pd.Series]:
    caminho = RAIZ / 'dados/sisvan/series/serie_mensal_Adolescentes_por_regiao.xlsx'
    df = pd.read_excel(caminho)
    df = df[df['regiao'].eq('NORTE')].sort_values(['ano', 'mes']).copy()
    df['data'] = pd.to_datetime(dict(year=df['ano'], month=df['mes'], day=1))
    nome = 'percentual_que_Consumo de Alimentos Ultraprocessados'
    y = pd.Series(100 * df[nome].to_numpy(float), index=df['data'], name='Prevalência')
    if len(y) != 120 or y.isna().any():
        raise ValueError('a série do artigo deve conter 120 meses sem ausências')
    return df, y


def grafico_cobertura(df: pd.DataFrame) -> None:
    col = 'total_all_Consumo de Alimentos Ultraprocessados'
    anual = df.groupby('ano')[col].sum()
    # Proporções iguais às caixas nativas do Google Docs, evitando recorte no
    # replaceImage (432 × 176,4 pt).
    fig, ax = plt.subplots(figsize=(9.0, 3.67))
    barras = ax.bar(anual.index.astype(str), anual.values, color=COR)
    ax.bar_label(barras, labels=[f'{v:,.0f}'.replace(',', '.') for v in anual],
                 padding=3, fontsize=8, rotation=35)
    ax.set_ylabel('Respostas válidas')
    ax.set_xlabel('Ano')
    ax.grid(axis='y', alpha=.2)
    ax.set_ylim(0, anual.max() * 1.22)
    fig.tight_layout()
    _salvar(fig, 'grafico_01_cobertura.png')


def grafico_sen(y: pd.Series) -> None:
    t = np.arange(len(y), dtype=float)
    incl = mk.sen(t, y.to_numpy())
    intercepto = float(np.median(y.to_numpy() - incl * t))
    ajustada = intercepto + incl * t
    fig, ax = plt.subplots(figsize=(8.2, 4.04))
    ax.plot(y.index, y.values, color=COR, linewidth=1.5, label='Prevalência mensal')
    ax.plot(y.index, ajustada, color=COR_DESTAQUE, linewidth=2,
            label=f'Tendência de Sen ({incl * 12:.2f} p.p./ano)')
    ax.set_ylabel('Prevalência (%)')
    ax.set_xlabel('Ano')
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
    ax.grid(alpha=.2)
    ax.legend(frameon=False, loc='best')
    fig.autofmt_xdate(rotation=0)
    fig.tight_layout()
    _salvar(fig, 'grafico_02_serie_sen.png')


def grafico_decomposicao(y: pd.Series) -> None:
    dec = seasonal_decompose(y, model='additive', period=12, extrapolate_trend='freq')
    fig, eixos = plt.subplots(4, 1, figsize=(8.2, 7.0), sharex=True)
    itens = [
        (y, 'Observada'), (dec.trend, 'Tendência'),
        (dec.seasonal, 'Sazonal'), (dec.resid, 'Resíduo'),
    ]
    for ax, (serie, rotulo) in zip(eixos, itens):
        ax.plot(serie.index, serie.values, color=COR, linewidth=1.2)
        ax.set_ylabel(rotulo)
        ax.grid(alpha=.18)
    eixos[-1].xaxis.set_major_locator(mdates.YearLocator())
    eixos[-1].xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
    eixos[-1].set_xlabel('Ano')
    fig.tight_layout()
    _salvar(fig, 'grafico_03_decomposicao.png')


def grafico_previsao(y: pd.Series) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        modelo = SARIMAX(
            y.to_numpy(), order=(0, 1, 2), seasonal_order=(1, 1, 1, 12),
            enforce_stationarity=False, enforce_invertibility=False,
        ).fit(disp=False, maxiter=300)
    futuro = modelo.get_forecast(12)
    datas = pd.date_range('2025-01-01', periods=12, freq='MS')
    media = np.asarray(futuro.predicted_mean)
    ic = np.asarray(futuro.conf_int(alpha=.05))
    recorte = y.loc['2022-01-01':]
    fig, ax = plt.subplots(figsize=(8.2, 4.05))
    ax.plot(recorte.index, recorte.values, color=COR, linewidth=1.5,
            label='Observado')
    ax.plot(datas, media, color=COR_DESTAQUE, linewidth=2, label='Previsão 2025')
    ax.fill_between(datas, ic[:, 0], ic[:, 1], color=COR_CLARA, alpha=.35,
                    label='Intervalo de 95%')
    ax.axvline(pd.Timestamp('2024-12-15'), color='#666666', linestyle='--', linewidth=1)
    ax.set_ylabel('Prevalência (%)')
    ax.set_xlabel('Ano')
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
    ax.grid(alpha=.2)
    ax.legend(frameon=False, loc='best')
    fig.tight_layout()
    _salvar(fig, 'grafico_04_previsao.png')


def main() -> None:
    _estilo()
    df, y = carregar()
    grafico_cobertura(df)
    grafico_sen(y)
    grafico_decomposicao(y)
    grafico_previsao(y)
    for caminho in sorted(SAIDA.glob('*.png')):
        print(caminho)


if __name__ == '__main__':
    main()
