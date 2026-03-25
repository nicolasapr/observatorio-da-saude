# load/catalog.py
"""
Aba "Catálogo de Dados": matriz ano × fonte com status e detalhes.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from .utils import ANOS, COLUNAS, FileInfo, scan_data_dir


@st.cache_data(ttl=30, show_spinner=False)
def _inventario() -> dict:
    return scan_data_dir()


def render() -> None:
    st.subheader("Catálogo de Dados")
    st.caption("Atualizado a cada 30 s — caminhos definidos em `scripts/config.py`")

    with st.spinner("Escaneando arquivos..."):
        inv = _inventario()

    # ── Matriz de status ──────────────────────────────────────────────────
    status_rows = []
    for ano in ANOS:
        row = {"Ano": ano}
        for key, label in COLUNAS:
            fi: FileInfo = inv[ano].get(key, FileInfo(None, False))
            row[label] = fi.status
        status_rows.append(row)

    df_status = pd.DataFrame(status_rows).set_index("Ano")

    def _color(val: str) -> str:
        if val == "✅":
            return "background-color: #d4edda; color: #155724"
        if val == "⚠️":
            return "background-color: #fff3cd; color: #856404"
        return "background-color: #f8d7da; color: #721c24"

    # pandas ≥ 2.1 renomeou applymap → map no Styler
    _style_fn = getattr(df_status.style, "map", None) or df_status.style.applymap
    styled = _style_fn(_color)
    st.dataframe(styled, use_container_width=True, height=380)

    # ── Resumo de cobertura ───────────────────────────────────────────────
    total = len(ANOS) * len(COLUNAS)
    ok = sum(
        1
        for ano in ANOS
        for key, _ in COLUNAS
        if inv[ano].get(key, FileInfo(None, False)).exists
    )
    st.progress(ok / total, text=f"{ok}/{total} arquivos presentes ({100 * ok // total}%)")

    # ── Detalhe de um arquivo ─────────────────────────────────────────────
    st.divider()
    st.markdown("#### Inspecionar arquivo")

    col1, col2 = st.columns(2)
    ano_sel   = col1.selectbox("Ano",   ANOS, index=len(ANOS) - 1)
    fonte_sel = col2.selectbox("Fonte", [label for _, label in COLUNAS])

    key_sel = next(k for k, lbl in COLUNAS if lbl == fonte_sel)
    fi: FileInfo = inv[ano_sel].get(key_sel, FileInfo(None, False))

    if not fi.exists:
        st.warning(f"Arquivo ausente para {fonte_sel} / {ano_sel}.")
    else:
        c1, c2, c3 = st.columns(3)
        c1.metric("Tamanho",   f"{fi.size_kb:.0f} KB")
        c2.metric("Modificado", fi.modified.strftime("%d/%m/%Y %H:%M") if fi.modified else "?")
        c3.metric("Aviso",      fi.warning if fi.warning else "—")
        st.code(str(fi.path), language=None)

        if fi.path and fi.path.suffix in {".xlsx", ".xls", ".csv"}:
            if st.button("Pré-visualizar primeiras linhas"):
                try:
                    if fi.path.suffix == ".csv":
                        df = pd.read_csv(fi.path, nrows=10, encoding="latin1")
                    else:
                        df = pd.read_excel(fi.path, nrows=10)
                    st.dataframe(df, use_container_width=True)
                except Exception as e:
                    st.error(f"Erro ao ler: {e}")
