# load/series.py
"""
Aba "Séries Temporais": gráficos de linha mensais dos hábitos alimentares SISVAN.

Três níveis de agregação: Nacional, Por Região, Por Estado.
Inclui decomposição sazonal (tendência + sazonalidade + resíduo).

Lê os arquivos pré-computados por SeriesMensaisTransformer:
    dados/sisvan/series/serie_mensal_{faixa}.xlsx
    dados/sisvan/series/serie_mensal_{faixa}_por_regiao.xlsx
    dados/sisvan/series/serie_mensal_{faixa}_por_uf.xlsx
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from scripts.config import SISVAN_SERIES_DIR, UF_NOMES, REGIOES

FAIXAS_SLUGS = [
    'Adolescentes',
    'Crianças_de_5_a_9_anos',
    'Crianças_de_2_a_4_anos',
]

FAIXAS_LABEL = {
    'Adolescentes':            'Adolescentes',
    'Crianças_de_5_a_9_anos': 'Crianças de 5 a 9 anos',
    'Crianças_de_2_a_4_anos': 'Crianças de 2 a 4 anos',
}

_HABITO_CURTO: list[tuple[str, str]] = [
    ('Hábito de realizar no mínimo as três refeições', '3 Refeições/dia'),
    ('Hábito de realizar as refeições assistindo',     'Refeição + TV'),
    ('Consumo de feijão',                              'Feijão'),
    ('Consumo de fruta',                               'Fruta'),
    ('Consumo de verduras e legumes',                  'Verduras/Legumes'),
    ('Consumo de Alimentos Ultraprocessados',          'Ultraprocessados'),
    ('Consumo de hambúrguer',                          'Hambúrguer/Embutidos'),
    ('Consumo de bebidas adoçadas',                    'Bebidas Adoçadas'),
    ('Consumo de macarrão instantâneo',                'Macarrão inst./Salgadinho'),
    ('Consumo de biscoito recheado',                   'Biscoito/Doces'),
]

_LAYOUT_BASE = dict(
    yaxis=dict(ticksuffix='%', range=[0, 105], gridcolor='rgba(200,200,200,0.3)'),
    xaxis=dict(tickformat='%b %Y', tickangle=-30),
    legend=dict(orientation='h', yanchor='top', y=-0.25, xanchor='left', x=0),
    height=560,
    hovermode='x unified',
    plot_bgcolor='rgba(0,0,0,0)',
    paper_bgcolor='rgba(0,0,0,0)',
    margin=dict(b=160),
)


def _nome_curto(col: str) -> str:
    sufixo = col[len('percentual_que_'):]
    for prefixo, curto in _HABITO_CURTO:
        if sufixo.startswith(prefixo):
            return curto
    return sufixo[:40]


# ── Carregamento ─────────────────────────────────────────────────────────

@st.cache_data(ttl=120)
def _carregar_serie(faixa_slug: str) -> pd.DataFrame | None:
    caminho = SISVAN_SERIES_DIR / f'serie_mensal_{faixa_slug}.xlsx'
    if not caminho.exists():
        return None
    df = pd.read_excel(caminho, parse_dates=['data'])
    df['data'] = pd.to_datetime(df['data'])
    return df


@st.cache_data(ttl=120)
def _carregar_serie_regiao(faixa_slug: str) -> pd.DataFrame | None:
    caminho = SISVAN_SERIES_DIR / f'serie_mensal_{faixa_slug}_por_regiao.xlsx'
    if not caminho.exists():
        return None
    df = pd.read_excel(caminho, parse_dates=['data'])
    df['data'] = pd.to_datetime(df['data'])
    return df


@st.cache_data(ttl=120)
def _carregar_serie_uf(faixa_slug: str) -> pd.DataFrame | None:
    caminho = SISVAN_SERIES_DIR / f'serie_mensal_{faixa_slug}_por_uf.xlsx'
    if not caminho.exists():
        return None
    df = pd.read_excel(caminho, parse_dates=['data'])
    df['data'] = pd.to_datetime(df['data'])
    return df


# ── Gráficos ─────────────────────────────────────────────────────────────

def _grafico_nacional(
    px, df_fil: pd.DataFrame, habitos_sel: list[str],
    nomes: dict, titulo: str,
) -> None:
    """Gráfico de linhas: múltiplos hábitos, agregação nacional."""
    df_long = (
        df_fil[['data'] + habitos_sel]
        .melt(id_vars='data', value_vars=habitos_sel, var_name='col', value_name='perc')
        .dropna(subset=['perc'])
    )
    df_long['Hábito'] = df_long['col'].map(nomes)
    df_long['Prevalência (%)'] = (df_long['perc'] * 100).round(1)

    fig = px.line(
        df_long, x='data', y='Prevalência (%)', color='Hábito',
        markers=True, labels={'data': 'Mês'}, title=titulo,
    )
    fig.update_layout(**_LAYOUT_BASE)
    fig.update_traces(line=dict(width=2), marker=dict(size=5))
    st.plotly_chart(fig, use_container_width=True)


def _grafico_comparar_grupos(
    px, df_fil: pd.DataFrame, col_pct: str,
    grupo_col: str, titulo: str,
) -> None:
    """Gráfico de linhas: 1 hábito, múltiplas regiões ou UFs."""
    df_plot = df_fil[['data', grupo_col, col_pct]].dropna(subset=[col_pct]).copy()
    df_plot['Prevalência (%)'] = (df_plot[col_pct] * 100).round(1)

    fig = px.line(
        df_plot, x='data', y='Prevalência (%)', color=grupo_col,
        markers=True, labels={'data': 'Mês'}, title=titulo,
    )
    fig.update_layout(**_LAYOUT_BASE)
    fig.update_traces(line=dict(width=2), marker=dict(size=5))
    st.plotly_chart(fig, use_container_width=True)


def _grafico_habitos_grupo(
    px, df_fil: pd.DataFrame, habitos_sel: list[str],
    nomes: dict, titulo: str,
) -> None:
    """Gráfico de linhas: múltiplos hábitos para um grupo filtrado."""
    _grafico_nacional(px, df_fil, habitos_sel, nomes, titulo)


# ── Decomposição sazonal ─────────────────────────────────────────────────

def _render_decomposicao(
    df_fil: pd.DataFrame, cols_pct: list[str], nomes: dict,
) -> None:
    """Expander com decomposição tendência + sazonalidade + resíduo."""
    with st.expander('Decomposição: Tendência + Sazonalidade'):
        try:
            from statsmodels.tsa.seasonal import seasonal_decompose
            from plotly.subplots import make_subplots
            import plotly.graph_objects as go
        except ImportError:
            st.error('Instale statsmodels: `pip install statsmodels`')
            return

        n_pontos = len(df_fil)
        if n_pontos < 24:
            st.warning(
                f'São necessários ao menos 24 meses para decomposição sazonal. '
                f'Período atual tem {n_pontos} meses.'
            )
            return

        col_decomp = st.selectbox(
            'Hábito para decompor',
            options=cols_pct,
            format_func=lambda c: nomes[c],
            key='serie_decomp_habito',
        )

        serie = (
            df_fil.set_index('data')[col_decomp]
            .dropna()
            .astype(float) * 100
        )
        serie = serie.asfreq('MS')
        serie = serie.interpolate(method='linear')

        if len(serie.dropna()) < 24:
            st.warning('Dados insuficientes após limpeza para decomposição.')
            return

        result = seasonal_decompose(serie, model='additive', period=12)

        fig = make_subplots(
            rows=3, cols=1, shared_xaxes=True,
            subplot_titles=['Tendência', 'Sazonalidade', 'Resíduo'],
            vertical_spacing=0.08,
        )

        fig.add_trace(
            go.Scatter(x=result.trend.index, y=result.trend.values,
                       mode='lines', name='Tendência',
                       line=dict(color='#1f77b4', width=2)),
            row=1, col=1,
        )
        fig.add_trace(
            go.Scatter(x=result.seasonal.index, y=result.seasonal.values,
                       mode='lines', name='Sazonalidade',
                       line=dict(color='#ff7f0e', width=2)),
            row=2, col=1,
        )
        fig.add_trace(
            go.Scatter(x=result.resid.index, y=result.resid.values,
                       mode='markers', name='Resíduo',
                       marker=dict(color='#2ca02c', size=4)),
            row=3, col=1,
        )

        fig.update_layout(
            height=650,
            showlegend=False,
            title_text=f'Decomposição — {nomes[col_decomp]}',
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
        )
        for i in range(1, 4):
            fig.update_yaxes(
                ticksuffix='%', gridcolor='rgba(200,200,200,0.3)', row=i, col=1,
            )
        fig.update_xaxes(tickformat='%b %Y', row=3, col=1)

        st.plotly_chart(fig, use_container_width=True)


# ── Tabela de dados ──────────────────────────────────────────────────────

def _render_tabela(
    df_fil: pd.DataFrame, habitos_sel: list[str], nomes: dict,
    extra_cols: list[str] | None = None,
) -> None:
    with st.expander('Dados tabulares'):
        id_cols = ['data'] + (extra_cols or [])
        df_tab = df_fil[id_cols + habitos_sel].copy()
        df_tab['Mês'] = df_tab['data'].dt.strftime('%Y-%m')
        df_tab = df_tab.drop(columns=['data'])
        df_tab[habitos_sel] = (df_tab[habitos_sel] * 100).round(1)
        df_tab = df_tab.rename(columns={c: nomes[c] for c in habitos_sel})
        pct_cols = [nomes[c] for c in habitos_sel]
        cols_order = ['Mês'] + (extra_cols or []) + pct_cols
        st.dataframe(df_tab[cols_order], width="stretch", hide_index=True)


# ── Renderização principal ───────────────────────────────────────────────

def render() -> None:
    st.subheader('Séries Temporais — Hábitos Alimentares SISVAN')

    try:
        import plotly.express as px
    except ImportError:
        st.error('Instale plotly: `pip install plotly`')
        return

    # ── Faixa etária ──────────────────────────────────────────────────
    faixa_slug = st.selectbox(
        'Faixa etária',
        FAIXAS_SLUGS,
        format_func=lambda s: FAIXAS_LABEL[s],
        key='serie_faixa',
    )

    # ── Nível de agregação ────────────────────────────────────────────
    nivel = st.radio(
        'Agregação',
        ['Nacional', 'Por Região', 'Por Estado'],
        horizontal=True,
        key='serie_nivel',
    )

    # ── Carrega dados ─────────────────────────────────────────────────
    if nivel == 'Nacional':
        df = _carregar_serie(faixa_slug)
    elif nivel == 'Por Região':
        df = _carregar_serie_regiao(faixa_slug)
    else:
        df = _carregar_serie_uf(faixa_slug)

    if df is None or df.empty:
        st.info(
            'Dados de série temporal não encontrados para esta faixa/agregação. '
            'Execute **Transform → Séries Mensais** na aba Extração / Transformação.'
        )
        return

    cols_pct = [c for c in df.columns if c.startswith('percentual_que_')]
    nomes = {c: _nome_curto(c) for c in cols_pct}

    # ── Período ───────────────────────────────────────────────────────
    anos_disp = sorted(df['ano'].unique().tolist())
    c1, c2 = st.columns(2)
    ano_ini = c1.selectbox(
        'Ano inicial', anos_disp, index=0, key='serie_ano_ini',
    )
    ano_fim = c2.selectbox(
        'Ano final', anos_disp, index=len(anos_disp) - 1, key='serie_ano_fim',
    )

    if ano_ini > ano_fim:
        st.warning('Ano inicial deve ser menor ou igual ao ano final.')
        return

    df_fil = df[(df['ano'] >= ano_ini) & (df['ano'] <= ano_fim)].copy()

    n_pontos = df_fil['data'].nunique() if 'data' in df_fil.columns else len(df_fil)
    st.caption(f'{n_pontos} ponto{"s" if n_pontos != 1 else ""} no período selecionado.')

    # ── Nacional ──────────────────────────────────────────────────────
    if nivel == 'Nacional':
        habitos_sel = st.multiselect(
            'Hábitos a exibir', options=cols_pct, default=cols_pct,
            format_func=lambda c: nomes[c], key='serie_habitos',
        )
        if not habitos_sel:
            st.warning('Selecione ao menos um hábito.')
            return

        titulo = f'{FAIXAS_LABEL[faixa_slug]} — {ano_ini} a {ano_fim}'
        _grafico_nacional(px, df_fil, habitos_sel, nomes, titulo)
        _render_tabela(df_fil, habitos_sel, nomes)
        _render_decomposicao(df_fil, cols_pct, nomes)
        return

    # ── Por Região ou Por Estado ──────────────────────────────────────
    if nivel == 'Por Região':
        grupo_col = 'regiao'
        grupos_disp = sorted(df_fil[grupo_col].dropna().unique().tolist())
        formato = lambda x: x  # noqa: E731
    else:
        grupo_col = 'UF'
        grupos_disp = sorted(df_fil[grupo_col].dropna().unique().tolist())
        formato = lambda x: f'{x} — {UF_NOMES.get(x, x)}'  # noqa: E731

    modo = st.radio(
        'Modo de visualização',
        ['Comparar regiões/estados', 'Comparar hábitos'],
        horizontal=True,
        key='serie_modo',
    )

    if modo == 'Comparar regiões/estados':
        # 1 hábito, múltiplas regiões/UFs
        habito_unico = st.selectbox(
            'Hábito', options=cols_pct,
            format_func=lambda c: nomes[c], key='serie_hab_unico',
        )
        grupos_sel = st.multiselect(
            f'{"Regiões" if nivel == "Por Região" else "Estados"} a exibir',
            options=grupos_disp,
            default=grupos_disp[:5],
            format_func=formato,
            key='serie_grupos',
        )
        if not grupos_sel:
            st.warning('Selecione ao menos um grupo.')
            return

        df_plot = df_fil[df_fil[grupo_col].isin(grupos_sel)]
        titulo = f'{nomes[habito_unico]} — {ano_ini} a {ano_fim}'
        _grafico_comparar_grupos(px, df_plot, habito_unico, grupo_col, titulo)
        _render_tabela(df_plot, [habito_unico], nomes, extra_cols=[grupo_col])

    else:
        # 1 região/UF, múltiplos hábitos
        grupo_unico = st.selectbox(
            'Região' if nivel == 'Por Região' else 'Estado',
            options=grupos_disp,
            format_func=formato,
            key='serie_grupo_unico',
        )
        habitos_sel = st.multiselect(
            'Hábitos a exibir', options=cols_pct, default=cols_pct,
            format_func=lambda c: nomes[c], key='serie_habitos_grupo',
        )
        if not habitos_sel:
            st.warning('Selecione ao menos um hábito.')
            return

        df_plot = df_fil[df_fil[grupo_col] == grupo_unico]
        label_grupo = formato(grupo_unico)
        titulo = f'{label_grupo} — {ano_ini} a {ano_fim}'
        _grafico_habitos_grupo(px, df_plot, habitos_sel, nomes, titulo)
        _render_tabela(df_plot, habitos_sel, nomes, extra_cols=[grupo_col])

        # Decomposição disponível para série filtrada de 1 grupo
        _render_decomposicao(df_plot, cols_pct, nomes)
