# load/viz.py
"""
Aba "Mapa": mapa coroplético do Brasil por município ou estado.

Dependências extras:
    pip install folium streamlit-folium
"""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

import pandas as pd
import streamlit as st

from scripts.config import PNAES_FINAIS_DIR, REFERENCIA_IBGE_DIR

# ── Constantes ────────────────────────────────────────────────────────────

FAIXAS = ["2a4", "5a9", "Adolescentes"]
ANOS   = list(range(2015, 2026))

# GeoJSON IBGE — municípios (~5 570 feições) e estados (27 UFs)
GEOJSON_URL = (
    "https://servicodados.ibge.gov.br/api/v3/malhas/paises/BR"
    "?formato=application/vnd.geo+json&resolucao=2&intrarregiao=municipio"
)
GEOJSON_UF_URL = (
    "https://servicodados.ibge.gov.br/api/v3/malhas/paises/BR"
    "?formato=application/vnd.geo+json&resolucao=2&intrarregiao=UF"
)

# Cache de GeoJSON em dados/referencia/ibge/ (não versionado pelo git)
GEODATA_DIR = REFERENCIA_IBGE_DIR / "geodata"

HABITOS = [
    "Hábito de realizar no mínimo as três refeições principais do dia",
    "Hábito de realizar as refeições assistindo à televisão",
    "Consumo de feijão",
    "Consumo de fruta",
    "Consumo de verduras e legumes",
    "Consumo de Alimentos Ultraprocessados",
    "Consumo de hambúrguer eou embutidos",
    "Consumo de bebidas adoçadas",
    "Consumo de macarrão instantâneo salgadinho de pacote ou biscoito salgado",
    "Consumo de biscoito recheado doces ou guloseimas",
]


# ── Helpers ───────────────────────────────────────────────────────────────

def _baixar_geojson(url: str, dest: Path) -> str:
    """Baixa GeoJSON, descomprime gzip se necessário, salva como JSON plano.

    Retorna string vazia em caso de sucesso, ou mensagem de erro.
    Sem chamadas st.* — pode ser chamado dentro de @st.cache_data.
    """
    import gzip as _gzip
    try:
        GEODATA_DIR.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(url, headers={"Accept-Encoding": "identity"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()
        if data[:2] == b"\x1f\x8b":
            data = _gzip.decompress(data)
        dest.write_bytes(data)
        return ""
    except Exception as e:
        return str(e)


@st.cache_data(show_spinner="Carregando mapa de municípios...")
def _carregar_geojson_municipios() -> tuple[dict | None, str]:
    """Retorna (geojson_dict, erro). erro='' em caso de sucesso."""
    dest = GEODATA_DIR / "municipios.json"
    if not dest.exists():
        err = _baixar_geojson(GEOJSON_URL, dest)
        if err:
            return None, err
    with open(dest, encoding="utf-8") as f:
        return json.load(f), ""


@st.cache_data(show_spinner="Carregando mapa de estados...")
def _carregar_geojson_uf() -> tuple[dict | None, str]:
    """Retorna (geojson_dict, erro). erro='' em caso de sucesso."""
    dest = GEODATA_DIR / "estados.json"
    if not dest.exists():
        err = _baixar_geojson(GEOJSON_UF_URL, dest)
        if err:
            return None, err
    with open(dest, encoding="utf-8") as f:
        return json.load(f), ""


@st.cache_data(ttl=60)
def _carregar_finais(faixa: str, ano: int) -> pd.DataFrame | None:
    path = PNAES_FINAIS_DIR / faixa / f"PNAES_valores_{faixa}_{ano}_ajustado.xlsx"
    if not path.exists():
        return None
    return pd.read_excel(path)


def _col_habito(df: pd.DataFrame, habito: str, tipo: str) -> str | None:
    col = f"{tipo}_{habito}"
    if col in df.columns:
        return col
    matches = [c for c in df.columns if c.startswith(tipo) and habito[:30] in c]
    return matches[0] if matches else None


# ── Renderização principal ────────────────────────────────────────────────

def render() -> None:
    try:
        import folium
        from streamlit_folium import st_folium
    except ImportError:
        st.error(
            "Pacotes necessários não instalados.\n\n"
            "Execute: `pip install folium streamlit-folium`"
        )
        return

    st.subheader("Mapa do Brasil — Hábitos Alimentares e PNAES")

    # ── Filtros ───────────────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns([1, 1, 2, 1])
    ano_sel   = c1.selectbox("Ano",   ANOS,   index=len(ANOS) - 2, key="viz_ano")
    faixa_sel = c2.selectbox("Faixa", FAIXAS, key="viz_faixa")

    INDICADORES = ["TOTAL PNAES (R$)"] + [f"% {h[:40]}" for h in HABITOS]
    indic_sel = c3.selectbox("Indicador", INDICADORES, key="viz_indic")
    nivel_sel = c4.radio("Nível", ["Município", "Estado"], key="viz_nivel", horizontal=True)

    # ── Carrega dados ─────────────────────────────────────────────────────
    df = _carregar_finais(faixa_sel, ano_sel)
    if df is None:
        st.warning(f"Arquivo Final não encontrado para {faixa_sel} / {ano_sel}.")
        return

    if indic_sel == "TOTAL PNAES (R$)":
        col_valor = "TOTAL" if "TOTAL" in df.columns else "TOTAL_EF"
        label_val = "TOTAL PNAES (R$)"
    else:
        habito = indic_sel[2:]  # remove "% "
        habito_full = next((h for h in HABITOS if h[:40] == habito), None)
        col_valor = _col_habito(df, habito_full or habito, "percentual_que") if habito_full else None
        label_val = indic_sel

    if col_valor is None or col_valor not in df.columns:
        st.warning(f"Coluna `{col_valor}` não encontrada para {faixa_sel} / {ano_sel}.")
        return

    df[col_valor] = pd.to_numeric(df[col_valor], errors="coerce")

    # ── Agrega por município ou estado ────────────────────────────────────
    if nivel_sel == "Estado":
        df_mapa = (
            df.groupby(["codigo_UF", "UF"], as_index=False)[col_valor]
            .mean()
            .rename(columns={col_valor: "valor"})
        )
        df_mapa["codigo"] = df_mapa["codigo_UF"].astype(int).astype(str)
        geojson, geo_err = _carregar_geojson_uf()
        key_geojson = "properties.codarea"
    else:
        df_mapa = (
            df.groupby(["codigo_IBGE", "municipio", "UF"], as_index=False)[col_valor]
            .mean()
            .rename(columns={col_valor: "valor"})
        )
        df_mapa["codigo"] = df_mapa["codigo_IBGE"].apply(
            lambda x: str(int(float(x))) if pd.notna(x) else ""
        )
        geojson, geo_err = _carregar_geojson_municipios()
        key_geojson = "properties.codarea"

    if geojson is None:
        st.error(
            "GeoJSON não disponível — verifique sua conexão para o download inicial.\n\n"
            + (f"Detalhe: {geo_err}" if geo_err else "")
        )
        return

    df_mapa = df_mapa.dropna(subset=["valor"])

    # ── Estatísticas rápidas ──────────────────────────────────────────────
    mc1, mc2, mc3, mc4 = st.columns(4)
    mc1.metric("Localidades", f"{len(df_mapa):,}")
    mc2.metric("Mínimo",  f"{df_mapa['valor'].min():,.2f}")
    mc3.metric("Mediana", f"{df_mapa['valor'].median():,.2f}")
    mc4.metric("Máximo",  f"{df_mapa['valor'].max():,.2f}")

    # ── Mapa Folium ───────────────────────────────────────────────────────
    m = folium.Map(location=[-14.2, -51.9], zoom_start=4, tiles="CartoDB positron")

    folium.Choropleth(
        geo_data=geojson,
        data=df_mapa,
        columns=["codigo", "valor"],
        key_on=key_geojson,
        fill_color="YlOrRd",
        fill_opacity=0.75,
        line_opacity=0.2,
        nan_fill_color="lightgray",
        legend_name=label_val,
        name=label_val,
    ).add_to(m)

    folium.GeoJson(
        geojson,
        style_function=lambda x: {"fillOpacity": 0, "weight": 0},
        tooltip=folium.GeoJsonTooltip(
            fields=[key_geojson.split(".")[-1]],
            aliases=["Código:"],
            localize=True,
        ),
        name="tooltip",
    ).add_to(m)

    folium.LayerControl().add_to(m)
    st_folium(m, width="100%", height=520, returned_objects=[])

    # ── Ranking ───────────────────────────────────────────────────────────
    st.divider()
    st.markdown("#### Ranking")
    col_nome = "municipio" if nivel_sel == "Município" else "UF"

    ranking = (
        df_mapa[["codigo", col_nome, "valor"]]
        .sort_values("valor", ascending=False)
        .reset_index(drop=True)
    )
    ranking.index += 1
    ranking.columns = ["Código", "Localidade", label_val]

    c_top, c_bot = st.columns(2)
    c_top.markdown("**Top 10 maiores**")
    c_top.dataframe(ranking.head(10), use_container_width=True, hide_index=False)
    c_bot.markdown("**Top 10 menores**")
    c_bot.dataframe(ranking.tail(10)[::-1], use_container_width=True, hide_index=False)
