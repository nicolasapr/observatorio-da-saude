# load/app.py
"""
Entry point do dashboard Observatório da Saúde.

Execução (a partir da pasta projeto/):
    streamlit run scripts/load/app.py

O diretório projeto/ precisa estar no PYTHONPATH para que os imports
`scripts.*` funcionem. O bloco abaixo garante isso automaticamente.
"""
import sys
from pathlib import Path

# Garante que projeto/ está no sys.path (necessário para `scripts.*` imports)
_PROJETO_DIR = Path(__file__).resolve().parent.parent.parent
if str(_PROJETO_DIR) not in sys.path:
    sys.path.insert(0, str(_PROJETO_DIR))

import streamlit as st  # noqa: E402

st.set_page_config(
    page_title="Observatório da Saúde",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Importações após set_page_config e ajuste de sys.path
from scripts.load import catalog, extractor, viz  # noqa: E402

# ── Cabeçalho ─────────────────────────────────────────────────────────────
st.title("🏥 Observatório da Saúde")
st.caption("Pipeline ETL — SISVAN · IBGE · MEC · PNAES (FNDE)")

# ── Abas ──────────────────────────────────────────────────────────────────
aba_catalogo, aba_extracao, aba_viz = st.tabs([
    "📂 Catálogo de Dados",
    "⬇️ Extração / Transformação",
    "🗺️ Mapa",
])

with aba_catalogo:
    catalog.render()

with aba_extracao:
    extractor.render()

with aba_viz:
    viz.render()
