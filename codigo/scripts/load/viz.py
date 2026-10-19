# load/viz.py
"""
Aba "Mapa": mapas coropléticos do Brasil — PNAES (valores) e SISVAN (hábitos).

Dois sub-tabs:
  💰 PNAES (R$)  — valores totais por estado/município
  🍎 SISVAN      — percentuais de hábitos alimentares

Drill-down: visão inicial por estados → selecionar estado → municípios.

Dependências extras:
    pip install folium streamlit-folium
"""
from __future__ import annotations

import copy
import json
import urllib.request
from pathlib import Path

import pandas as pd
import streamlit as st

from scripts.config import PNAES_FINAIS_DIR, REFERENCIA_IBGE_DIR, UF_NOMES

# ── Constantes ────────────────────────────────────────────────────────────

FAIXAS = ["2a4", "5a9", "Adolescentes"]
ANOS   = list(range(2015, 2026))

_BRASIL_BOUNDS = [[-33.75, -73.99], [5.27, -34.79]]

GEOJSON_UF_URL = (
    "https://servicodados.ibge.gov.br/api/v3/malhas/paises/BR"
    "?formato=application/vnd.geo+json&resolucao=2&intrarregiao=UF"
)
_GEOJSON_UF_MUNIC_URL = (
    "https://servicodados.ibge.gov.br/api/v3/malhas/estados/{uf_code}"
    "?formato=application/vnd.geo+json&resolucao=2&intrarregiao=municipio"
)

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


# ── Helpers — I/O ────────────────────────────────────────────────────────

def _baixar_geojson(url: str, dest: Path) -> str:
    """Baixa GeoJSON, descomprime gzip se necessário, salva como JSON plano."""
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


@st.cache_data(show_spinner="Carregando mapa de estados...")
def _carregar_geojson_uf() -> tuple[dict | None, str]:
    dest = GEODATA_DIR / "estados.json"
    if not dest.exists():
        err = _baixar_geojson(GEOJSON_UF_URL, dest)
        if err:
            return None, err
    with open(dest, encoding="utf-8") as f:
        return json.load(f), ""


@st.cache_data(show_spinner="Carregando mapa de municípios do estado...")
def _carregar_geojson_municipios_uf(uf_code: int) -> tuple[dict | None, str]:
    """Carrega GeoJSON de municípios de um estado específico."""
    dest = GEODATA_DIR / f"municipios_uf_{uf_code}.json"
    if not dest.exists():
        url = _GEOJSON_UF_MUNIC_URL.format(uf_code=uf_code)
        err = _baixar_geojson(url, dest)
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


# ── Helpers — dados ──────────────────────────────────────────────────────

def _converter_pct(s: pd.Series) -> pd.Series:
    """Converte coluna de percentual ('45.3%' ou 0.453) para float."""
    if s.dtype == object:
        return pd.to_numeric(s.astype(str).str.rstrip("%"), errors="coerce")
    return pd.to_numeric(s, errors="coerce")


def _agregar_estado(df: pd.DataFrame, col_valor: str, agg: str = "mean") -> pd.DataFrame:
    grp = df.groupby(["codigo_UF", "UF"], as_index=False)[col_valor]
    df_mapa = (
        (grp.sum() if agg == "sum" else grp.mean())
        .rename(columns={col_valor: "valor"})
    )
    df_mapa["codigo"] = df_mapa["codigo_UF"].astype(int).astype(str)
    return df_mapa


def _agregar_estado_ponderado(df: pd.DataFrame, col_pct: str) -> pd.DataFrame:
    """Agrega percentual por estado com média ponderada (soma_que / soma_all)."""
    sufixo = col_pct[len("percentual_que_"):]
    col_que = f"total_que_{sufixo}"
    col_all = f"total_all_{sufixo}"
    if col_que not in df.columns or col_all not in df.columns:
        return _agregar_estado(df, col_pct)
    grp = df.groupby(["codigo_UF", "UF"], as_index=False).agg(
        soma_que=(col_que, "sum"),
        soma_all=(col_all, "sum"),
    )
    grp["valor"] = grp.apply(
        lambda r: r["soma_que"] / r["soma_all"] * 100 if r["soma_all"] > 0 else None,
        axis=1,
    ).clip(0, 100)
    grp["codigo"] = grp["codigo_UF"].astype(int).astype(str)
    return grp[["codigo_UF", "UF", "codigo", "valor"]]


def _agregar_municipio(
    df: pd.DataFrame, col_valor: str, uf_code: int | None = None,
) -> pd.DataFrame:
    if uf_code is not None:
        df = df[df["codigo_UF"].astype(int) == uf_code]
    df_mapa = (
        df.groupby(["codigo_IBGE", "municipio", "UF"], as_index=False)[col_valor]
        .mean()
        .rename(columns={col_valor: "valor"})
    )
    df_mapa["codigo"] = df_mapa["codigo_IBGE"].apply(
        lambda x: str(int(float(x))) if pd.notna(x) else ""
    )
    return df_mapa


def _enriquecer_geojson(
    geojson: dict, df_mapa: pd.DataFrame, nivel: str,
) -> dict:
    """Injeta nome, UF e valor nas properties do GeoJSON para tooltip."""
    geo = copy.deepcopy(geojson)
    lookup: dict[str, dict] = {}
    for _, row in df_mapa.iterrows():
        cod = str(row["codigo"])
        if nivel == "estado":
            lookup[cod] = {
                "nome": UF_NOMES.get(row["UF"], row["UF"]),
                "uf": row["UF"],
                "valor": f"{row['valor']:,.2f}",
            }
        else:
            lookup[cod] = {
                "nome": row.get("municipio", ""),
                "uf": row.get("UF", ""),
                "valor": f"{row['valor']:,.2f}",
            }
    for feat in geo["features"]:
        codarea = feat["properties"].get("codarea", "")
        info = lookup.get(codarea, {})
        feat["properties"]["nome"] = info.get("nome", "")
        feat["properties"]["uf"] = info.get("uf", "")
        feat["properties"]["valor"] = info.get("valor", "N/D")
    return geo


def _bounds_geojson(geojson: dict) -> list[list[float]]:
    """Calcula [[lat_min, lng_min], [lat_max, lng_max]] do GeoJSON."""
    lats: list[float] = []
    lngs: list[float] = []

    def _coletar(coords):  # type: ignore[no-untyped-def]
        if isinstance(coords[0], (int, float)):
            lngs.append(coords[0])
            lats.append(coords[1])
        else:
            for c in coords:
                _coletar(c)

    for feat in geojson["features"]:
        _coletar(feat["geometry"]["coordinates"])
    if not lats:
        return _BRASIL_BOUNDS
    return [[min(lats), min(lngs)], [max(lats), max(lngs)]]


# ── Helpers — renderização ───────────────────────────────────────────────

def _render_estatisticas(df_mapa: pd.DataFrame) -> None:
    mc1, mc2, mc3, mc4 = st.columns(4)
    mc1.metric("Localidades", f"{len(df_mapa):,}")
    mc2.metric("Mínimo",  f"{df_mapa['valor'].min():,.2f}")
    mc3.metric("Mediana", f"{df_mapa['valor'].median():,.2f}")
    mc4.metric("Máximo",  f"{df_mapa['valor'].max():,.2f}")


def _render_mapa_folium(
    folium_mod,
    st_folium_func,
    df_mapa: pd.DataFrame,
    geojson: dict,
    label_val: str,
    nivel: str,
    prefix: str,
    bounds: list | None = None,
) -> None:
    """Renderiza mapa Folium com choropleth e tooltips enriquecidos."""
    geo_tooltip = _enriquecer_geojson(geojson, df_mapa, nivel)

    target_bounds = bounds or _BRASIL_BOUNDS
    m = folium_mod.Map(
        location=[-14.2, -51.9],
        zoom_start=4,
        tiles=None,
        max_bounds=True,
        min_zoom=3,
        max_zoom=14,
        min_lat=target_bounds[0][0] - 2,
        max_lat=target_bounds[1][0] + 2,
        min_lon=target_bounds[0][1] - 2,
        max_lon=target_bounds[1][1] + 2,
    )
    m.fit_bounds(target_bounds)
    # Fundo branco — sem tiles de mapa-múndi
    from branca.element import Element
    m.get_root().html.add_child(Element(
        "<style>.leaflet-container { background: #fff !important; }</style>"
    ))

    folium_mod.Choropleth(
        geo_data=geojson,
        data=df_mapa,
        columns=["codigo", "valor"],
        key_on="properties.codarea",
        fill_color="YlOrRd",
        fill_opacity=0.75,
        line_opacity=0.2,
        nan_fill_color="lightgray",
        legend_name=label_val,
        name=label_val,
    ).add_to(m)

    if nivel == "estado":
        tt_fields  = ["uf", "nome", "valor"]
        tt_aliases = ["UF:", "Estado:", f"{label_val}:"]
    else:
        tt_fields  = ["nome", "uf", "valor"]
        tt_aliases = ["Município:", "UF:", f"{label_val}:"]

    folium_mod.GeoJson(
        geo_tooltip,
        style_function=lambda _x: {"fillOpacity": 0, "weight": 0},
        highlight_function=lambda _x: {"weight": 3, "fillOpacity": 0.1},
        tooltip=folium_mod.GeoJsonTooltip(
            fields=tt_fields,
            aliases=tt_aliases,
            localize=True,
        ),
        name="tooltip",
    ).add_to(m)

    folium_mod.LayerControl().add_to(m)
    st_folium_func(m, width="100%", height=520, returned_objects=[], key=f"map_{prefix}")


def _render_ranking(
    df_mapa: pd.DataFrame, label_val: str, nivel: str,
) -> None:
    st.markdown("#### Ranking")

    if nivel == "estado":
        ranking = df_mapa[["UF", "valor"]].copy()
        ranking["Estado"] = ranking["UF"].map(UF_NOMES)
        ranking = (
            ranking[["UF", "Estado", "valor"]]
            .sort_values("valor", ascending=False)
            .reset_index(drop=True)
        )
        ranking.index += 1
        ranking.columns = ["UF", "Estado", label_val]
    else:
        ranking = df_mapa[["municipio", "UF", "valor"]].copy()
        ranking["Estado"] = ranking["UF"].map(UF_NOMES)
        ranking = (
            ranking[["municipio", "UF", "Estado", "valor"]]
            .sort_values("valor", ascending=False)
            .reset_index(drop=True)
        )
        ranking.index += 1
        ranking.columns = ["Município", "UF", "Estado", label_val]

    c_top, c_bot = st.columns(2)
    c_top.markdown("**Top 10 maiores**")
    c_top.dataframe(ranking.head(10), width="stretch", hide_index=False)
    c_bot.markdown("**Top 10 menores**")
    c_bot.dataframe(ranking.tail(10)[::-1], width="stretch", hide_index=False)


def _render_csv_export(
    df_mapa: pd.DataFrame, tipo: str, faixa: str, ano: int,
) -> None:
    csv_bytes = df_mapa.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="Exportar CSV",
        data=csv_bytes,
        file_name=f"mapa_{tipo}_{faixa}_{ano}.csv",
        mime="text/csv",
    )


# ── Tab genérica de mapa (com drill-down) ────────────────────────────────

def _render_tab_mapa(
    folium_mod,
    st_folium_func,
    df: pd.DataFrame,
    col_valor: str,
    label_val: str,
    faixa_sel: str,
    ano_sel: int,
    prefix: str,
) -> None:
    """Lógica compartilhada para cada sub-tab (PNAES ou SISVAN)."""
    ufs_disp = sorted(df["UF"].dropna().unique().tolist())

    uf_escolhida = st.selectbox(
        "Selecione um estado para ver seus municípios",
        options=[None] + ufs_disp,
        format_func=lambda x: (
            "Brasil (todos os estados)"
            if x is None
            else f"{x} — {UF_NOMES.get(x, x)}"
        ),
        key=f"sel_uf_{prefix}",
    )

    # ── Visão por estados ─────────────────────────────────────────────
    if uf_escolhida is None:
        if col_valor.startswith("percentual_que_"):
            df_mapa = _agregar_estado_ponderado(df, col_valor).dropna(subset=["valor"])
        elif col_valor in ("TOTAL", "TOTAL_EF"):
            df_mapa = _agregar_estado(df, col_valor, agg="sum").dropna(subset=["valor"])
        else:
            df_mapa = _agregar_estado(df, col_valor).dropna(subset=["valor"])

        geojson, geo_err = _carregar_geojson_uf()
        if geojson is None:
            st.error(f"GeoJSON de estados não disponível. {geo_err}")
            return

        _render_estatisticas(df_mapa)
        _render_mapa_folium(
            folium_mod, st_folium_func, df_mapa, geojson,
            label_val, "estado", prefix,
        )
        st.divider()
        _render_ranking(df_mapa, label_val, "estado")
        _render_csv_export(df_mapa, f"{prefix}_estados", faixa_sel, ano_sel)
        return

    # ── Visão por municípios do estado selecionado ────────────────────
    uf_codes = df.loc[df["UF"] == uf_escolhida, "codigo_UF"].dropna().unique()
    if len(uf_codes) == 0:
        st.warning(f"Dados não encontrados para {uf_escolhida}.")
        return
    uf_code = int(uf_codes[0])

    st.info(
        f"Exibindo municípios de **{uf_escolhida} — "
        f"{UF_NOMES.get(uf_escolhida, '')}**"
    )

    df_mapa = _agregar_municipio(df, col_valor, uf_code).dropna(subset=["valor"])
    if df_mapa.empty:
        st.warning(f"Nenhum dado disponível para municípios de {uf_escolhida}.")
        return

    geojson, geo_err = _carregar_geojson_municipios_uf(uf_code)
    if geojson is None:
        st.error(
            f"GeoJSON de municípios não disponível para {uf_escolhida}. {geo_err}"
        )
        return

    bounds = _bounds_geojson(geojson)

    _render_estatisticas(df_mapa)
    _render_mapa_folium(
        folium_mod, st_folium_func, df_mapa, geojson,
        label_val, "municipio", f"{prefix}_mun", bounds=bounds,
    )
    st.divider()
    _render_ranking(df_mapa, label_val, "municipio")
    _render_csv_export(
        df_mapa, f"{prefix}_munic_{uf_escolhida}", faixa_sel, ano_sel,
    )


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

    # ── Filtros compartilhados ───────────────────────────────────────
    c1, c2 = st.columns(2)
    ano_sel   = c1.selectbox("Ano",   ANOS,   index=len(ANOS) - 2, key="viz_ano")
    faixa_sel = c2.selectbox("Faixa", FAIXAS, key="viz_faixa")

    df = _carregar_finais(faixa_sel, ano_sel)
    if df is None:
        st.warning(f"Arquivo Final não encontrado para {faixa_sel} / {ano_sel}.")
        return

    # ── Filtro SISVAN (hábito) ───────────────────────────────────────
    habito_sel = st.selectbox("Hábito alimentar (SISVAN)", HABITOS, key="viz_habito")

    # ── Dois mapas lado a lado: PNAES e SISVAN ──────────────────────
    col_pnaes, col_sisvan = st.columns(2)

    with col_pnaes:
        st.markdown("### PNAES (R$)")
        col_total = "TOTAL" if "TOTAL" in df.columns else "TOTAL_EF"
        if col_total not in df.columns:
            st.warning(
                f"Coluna TOTAL/TOTAL_EF não encontrada para {faixa_sel}/{ano_sel}."
            )
        else:
            df_p = df.copy()
            df_p[col_total] = pd.to_numeric(df_p[col_total], errors="coerce")
            _render_tab_mapa(
                folium, st_folium, df_p, col_total,
                "TOTAL PNAES (R$)", faixa_sel, ano_sel, "pnaes",
            )

    with col_sisvan:
        st.markdown("### SISVAN (Hábitos)")
        col_hab = _col_habito(df, habito_sel, "percentual_que")
        if col_hab is None or col_hab not in df.columns:
            st.warning(
                f"Coluna de hábito não encontrada para {faixa_sel}/{ano_sel}."
            )
        else:
            df_s = df.copy()
            # percentual_que_* está corrompido (strings concatenadas).
            # Recomputa a partir de total_que / total_all.
            sufixo = col_hab[len("percentual_que_"):]
            col_que = f"total_que_{sufixo}"
            col_all = f"total_all_{sufixo}"
            if col_que in df_s.columns and col_all in df_s.columns:
                df_s[col_que] = pd.to_numeric(df_s[col_que], errors="coerce")
                df_s[col_all] = pd.to_numeric(df_s[col_all], errors="coerce")
                df_s[col_hab] = (
                    (df_s[col_que] / df_s[col_all] * 100).clip(0, 100)
                )
            else:
                df_s[col_hab] = _converter_pct(df_s[col_hab])
            _render_tab_mapa(
                folium, st_folium, df_s, col_hab,
                f"% {habito_sel[:40]}", faixa_sel, ano_sel, "sisvan",
            )
