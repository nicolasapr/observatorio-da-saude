#!/usr/bin/env python3
"""Reproduz os números do estudo temporal usado no artigo RBIC.

Recorte principal: Região Norte, adolescentes, janeiro/2015 a dezembro/2024.
O script:

* calcula Mann-Kendall original, Hamed-Rao, Mann-Kendall sazonal e Sen;
* seleciona SARIMA por AIC apenas no treino 2015--2023;
* valida a previsão em 2024 contra o ingênuo sazonal;
* reajusta o modelo vencedor em 2015--2024 e prevê 2025;
* testa estacionariedade e registra cobertura das pontas da série.

Saídas canônicas:
    analise/estudo-series-temporais.csv
    analise/numeros-do-artigo.json
"""
from __future__ import annotations

import itertools
import json
import os
import sys
import tempfile
import warnings
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from statsmodels.tsa.statespace.sarimax import SARIMAX
from statsmodels.tsa.stattools import adfuller, kpss

BASE = Path(__file__).resolve().parent
RAIZ = BASE.parent
sys.path.insert(0, str(BASE))
sys.path.insert(0, str(RAIZ / 'codigo'))

import mk  # noqa: E402
from scripts.config import SISVAN_MENSAIS_DIR, SISVAN_SERIES_DIR  # noqa: E402


MARCADORES = {
    'ultraprocessados': 'Consumo de Alimentos Ultraprocessados',
    'bebidas_adocadas': 'Consumo de bebidas adoçadas',
    'biscoito_doces': 'Consumo de biscoito recheado doces ou guloseimas',
    'feijao': 'Consumo de feijão',
    'fruta': 'Consumo de fruta',
    'hamburguer_embutidos': 'Consumo de hambúrguer eou embutidos',
    'macarrao_salgadinho': (
        'Consumo de macarrão instantâneo salgadinho de pacote ou biscoito salgado'
    ),
    'verduras_legumes': 'Consumo de verduras e legumes',
    'refeicoes_tv': 'Hábito de realizar as refeições assistindo à televisão',
    'refeicoes_principais': (
        'Hábito de realizar no mínimo as três refeições principais do dia'
    ),
}


def _arredondar(v, casas=4):
    return round(float(v), casas)


def _valor_json(valor):
    """Converte escalares numpy sem alterar textos nem inteiros."""
    if isinstance(valor, (np.bool_, bool)):
        return bool(valor)
    if isinstance(valor, (np.integer, int)):
        return int(valor)
    if isinstance(valor, (np.floating, float)):
        return float(valor)
    return valor


def _json_atomico(obj: dict, destino: Path) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    fd, temporario = tempfile.mkstemp(
        prefix=f'.{destino.stem}.', suffix='.json', dir=destino.parent,
    )
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(obj, f, ensure_ascii=False, indent=2, allow_nan=False)
            f.write('\n')
        os.replace(temporario, destino)
    finally:
        if os.path.exists(temporario):
            os.unlink(temporario)


def _csv_atomico(df: pd.DataFrame, destino: Path) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    fd, temporario = tempfile.mkstemp(
        prefix=f'.{destino.stem}.', suffix='.csv', dir=destino.parent,
    )
    os.close(fd)
    try:
        df.to_csv(temporario, index=False)
        os.replace(temporario, destino)
    finally:
        if os.path.exists(temporario):
            os.unlink(temporario)


def carregar_serie() -> pd.DataFrame:
    caminho = SISVAN_SERIES_DIR / 'serie_mensal_Adolescentes_por_regiao.xlsx'
    df = pd.read_excel(caminho)
    df = df[df['regiao'].eq('NORTE')].sort_values(['ano', 'mes']).reset_index(drop=True)
    esperado = pd.period_range('2015-01', '2024-12', freq='M')
    observado = pd.PeriodIndex(
        pd.to_datetime(dict(year=df['ano'], month=df['mes'], day=1)), freq='M',
    )
    if len(df) != 120 or not observado.equals(esperado):
        raise ValueError('série Norte/Adolescentes não contém os 120 meses consecutivos')
    return df


def tabela_tendencias(df: pd.DataFrame) -> pd.DataFrame:
    t = np.arange(len(df), dtype=float)
    meses = df['mes'].to_numpy()
    pre = df['ano'].le(2021).to_numpy()
    linhas = []
    for slug, nome in MARCADORES.items():
        x = 100 * pd.to_numeric(df[f'percentual_que_{nome}']).to_numpy(float)
        original = mk.original(t, x)
        hr = mk.hamed_rao(t, x)
        sazonal = mk.sazonal(meses, x, t)
        classe_o = mk.classificar(original['p'], original['z'])
        classe_hr = mk.classificar(hr['p'], hr['z'])
        classe_sz = mk.classificar(sazonal['p'], sazonal['z'])
        linhas.append({
            'marcador': slug,
            'n': len(x),
            'media': x.mean(),
            'dp': x.std(ddof=1),
            'inicio12': x[:12].mean(),
            'fim12': x[-12:].mean(),
            'tau': original['tau'],
            'mk_z': original['z'],
            'mk_p': original['p'],
            'sen_pp_ano': original['sen'] * 12,
            'mk': classe_o,
            'hr_z': hr['z'],
            'hr_p': hr['p'],
            'hr': classe_hr,
            'sz_z': sazonal['z'],
            'sz_p': sazonal['p'],
            'sz_sen_pp_ano': sazonal['sen'] * 12,
            'sz': classe_sz,
            'salto_2022_pp': x[~pre].mean() - x[pre].mean(),
            'robusta': (
                original['p'] < .05 and hr['p'] < .05 and sazonal['p'] < .05
                and classe_o == classe_sz
            ),
        })
    return pd.DataFrame(linhas)


def ajustar_sarima(y: np.ndarray) -> dict:
    treino, teste = y[:108], y[108:]
    candidatos = []
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        for p, q, P, Q in itertools.product(range(3), range(3), range(2), range(2)):
            ordem = (p, 1, q)
            sazonal = (P, 1, Q, 12)
            try:
                ajuste = SARIMAX(
                    treino,
                    order=ordem,
                    seasonal_order=sazonal,
                    enforce_stationarity=False,
                    enforce_invertibility=False,
                ).fit(disp=False, maxiter=300)
            except Exception:
                continue
            if np.isfinite(ajuste.aic):
                candidatos.append((float(ajuste.aic), ordem, sazonal, ajuste))
    if not candidatos:
        raise RuntimeError('nenhum candidato SARIMA convergiu')
    aic, ordem, sazonal, ajuste_treino = min(candidatos, key=lambda item: item[0])
    previsao_teste = np.asarray(ajuste_treino.get_forecast(12).predicted_mean)
    baseline = treino[-12:]
    rmse = float(np.sqrt(np.mean((teste - previsao_teste) ** 2)))
    mae = float(np.mean(np.abs(teste - previsao_teste)))
    baseline_rmse = float(np.sqrt(np.mean((teste - baseline) ** 2)))

    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        ajuste_final = SARIMAX(
            y,
            order=ordem,
            seasonal_order=sazonal,
            enforce_stationarity=False,
            enforce_invertibility=False,
        ).fit(disp=False, maxiter=300)
    futuro = ajuste_final.get_forecast(12)
    media = np.asarray(futuro.predicted_mean)
    ic = np.asarray(futuro.conf_int(alpha=.05))
    # O diagnóstico do próprio modelo usa erros padronizados de previsão e
    # descarta corretamente a inicialização difusa do filtro de Kalman. Aplicar
    # Ljung-Box ao vetor ``resid`` bruto inclui esses resíduos artificiais.
    ljung_p = float(
        ajuste_final.test_serial_correlation(method='ljungbox', lags=[12])[0, 1, 0]
    )
    return {
        'selecao': 'menor AIC entre 36 candidatos, treino 2015-2023',
        'espaco_busca': 'p,q=0..2; d=1; P,Q=0..1; D=1; s=12',
        'ordem': f'{ordem}{sazonal[:3]}[12]',
        'aic_treino': _arredondar(aic, 2),
        'rmse_2024': _arredondar(rmse, 3),
        'mae_2024': _arredondar(mae, 3),
        'baseline': 'ingênuo sazonal: repete os 12 meses de 2023',
        'baseline_rmse': _arredondar(baseline_rmse, 3),
        'ganho_pct': _arredondar(100 * (1 - rmse / baseline_rmse), 1),
        'ljung_box_12_p': _arredondar(ljung_p, 4),
        'ljung_box_residuo': 'erros padronizados de previsão após inicialização',
        'aic_final_2015_2024': _arredondar(ajuste_final.aic, 2),
        'previsao_2025_media': _arredondar(media.mean(), 2),
        'ic95_mensal_medio': [_arredondar(ic[:, 0].mean(), 2), _arredondar(ic[:, 1].mean(), 2)],
        'observado_2024': _arredondar(teste.mean(), 2),
        'nota_vazamento': (
            'seleção e ajuste em 2015-2023, validação em 2024; reajuste em '
            '2015-2024 somente antes de prever 2025'
        ),
    }


def estacionariedade(y: np.ndarray) -> dict:
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        adf_p = adfuller(y, autolag='AIC')[1]
        kpss_p = kpss(y, regression='c', nlags='auto')[1]
        adf_d1 = adfuller(np.diff(y), autolag='AIC')[1]
        kpss_d1 = kpss(np.diff(y), regression='c', nlags='auto')[1]
    return {
        'adf_nivel_p': float(adf_p),
        'kpss_nivel_p': float(kpss_p),
        'adf_primeira_diferenca_p': float(adf_d1),
        'kpss_primeira_diferenca_p': float(kpss_d1),
        'nota_kpss': 'statsmodels limita os p-valores reportados ao intervalo [0,01; 0,10]',
    }


def cobertura(ano: int, mes_nome: str) -> dict:
    caminho = (
        SISVAN_MENSAIS_DIR / str(ano) / mes_nome
        / 'sumario_habitos_Adolescentes.xlsx'
    )
    df = pd.read_excel(caminho)
    nome = MARCADORES['ultraprocessados']
    all_ = pd.to_numeric(df[f'total_all_{nome}'], errors='coerce').fillna(0)
    norte = df['regiao'].eq('NORTE') & all_.gt(0)
    return {
        'municipios_com_resposta': int(norte.sum()),
        'respostas_validas': int(all_[norte].sum()),
    }


def main() -> None:
    serie = carregar_serie()
    tabela = tabela_tendencias(serie)
    _csv_atomico(tabela, BASE / 'estudo-series-temporais.csv')

    ultra = tabela.set_index('marcador').loc['ultraprocessados']
    nome_ultra = MARCADORES['ultraprocessados']
    y = 100 * serie[f'percentual_que_{nome_ultra}'].to_numpy(float)
    tabela_json = {}
    for linha in tabela.to_dict(orient='records'):
        slug = linha.pop('marcador')
        tabela_json[slug] = {
            chave: _valor_json(valor)
            for chave, valor in linha.items()
        }

    afetadas = None
    triagem = BASE / 'triagem_series.csv'
    if triagem.exists():
        geral = pd.read_csv(triagem)
        afetadas = int(geral['salto_2022'].abs().gt(10).sum())

    resultado = {
        'gerado_em': date.today().isoformat(),
        'fonte_serie': str(
            SISVAN_SERIES_DIR / 'serie_mensal_Adolescentes_por_regiao.xlsx'
        ),
        'recorte': 'Região Norte · Adolescentes · 2015-01 a 2024-12',
        'n_meses': 120,
        'imputacao': 'nenhuma — todos os 120 meses estão presentes',
        'unidade': 'pontos percentuais',
        'tabela01': tabela_json,
        'sarima_ultraprocessados': ajustar_sarima(y),
        'estacionariedade_ultraprocessados': estacionariedade(y),
        'quebra_estrutural_2022': {
            'criterio_triagem': '|média 2022-2024 - média 2015-2021| > 10 p.p.',
            'refeicoes_principais_salto_pp': _arredondar(
                tabela.set_index('marcador').loc['refeicoes_principais', 'salto_2022_pp'], 2,
            ),
            'series_afetadas_entre_180': afetadas,
            'consequencia': (
                'refeicoes_principais não deve ser interpretado como série '
                'contínua de comportamento em 2015-2024'
            ),
        },
        'cobertura_norte_adolescentes': {
            '2015-01': cobertura(2015, 'JANEIRO'),
            '2024-12': cobertura(2024, 'DEZEMBRO'),
            'nota': 'municípios com total_all de ultraprocessados maior que zero',
        },
        'controle': {
            'mk_referencia': 'pymannkendall 1.4.3; conferir_mk.py: 180 séries, 0 divergências',
            'serie_ultraprocessados_robusta': bool(ultra['robusta']),
        },
    }
    _json_atomico(resultado, BASE / 'numeros-do-artigo.json')
    print('10 marcadores recalculados; SARIMA selecionado sem usar 2024')
    print(f"modelo: {resultado['sarima_ultraprocessados']['ordem']}")
    print(f"saídas: {BASE / 'estudo-series-temporais.csv'}")
    print(f"        {BASE / 'numeros-do-artigo.json'}")


if __name__ == '__main__':
    main()
