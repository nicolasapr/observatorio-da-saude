# load/extractor.py
"""
Aba "Extração / Transformação": dispara downloaders e transformers com log em tempo real.

Os scripts são invocados via `python -m` para que o Python resolva os imports
corretamente independente do diretório de trabalho.
"""
from __future__ import annotations

import subprocess
import sys
import threading
from pathlib import Path
from queue import Empty, Queue

import streamlit as st

# Raiz do projeto (projeto/) — usada como cwd nos subprocessos
_PROJETO_DIR = Path(__file__).resolve().parent.parent.parent  # load/ → scripts/ → projeto/

FONTES_EXTRACT = {
    "SISVAN":       "sisvan",
    "IBGE":         "ibge",
    "MEC / INEP":   "mec",
    "PNAES (FNDE)": "pnaes",   # placeholder — URL pendente
}

FONTES_TRANSFORM = {
    "Sumários SISVAN":            "criar_sumarios",
    "Sumários Anuais":            "sumarios_anuais",
    "Sumários Totais":            "sumarios_totais",
    "PNAES Redes → Valores":      "pnaes_redes",
    "PNAES 2a4 (Final)":          "pnaes_2a4",
    "PNAES 5a9 (Final)":          "pnaes_5a9",
    "PNAES Adolescentes (Final)": "pnaes_adolescentes",
}


def _enqueue_output(stream, queue: Queue) -> None:
    for line in iter(stream.readline, ""):
        queue.put(line)
    stream.close()


def _run_module(
    module: str,
    args: list[str],
    log_placeholder,
) -> int:
    """Executa um módulo Python com `python -m` e exibe output em tempo real."""
    cmd = [sys.executable, "-m", module] + args
    log_placeholder.code(" ".join(cmd), language="bash")

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=str(_PROJETO_DIR),
    )

    q: Queue = Queue()
    t = threading.Thread(target=_enqueue_output, args=(proc.stdout, q), daemon=True)
    t.start()

    lines: list[str] = []
    log_area = log_placeholder.empty()

    while proc.poll() is None or not q.empty():
        try:
            line = q.get(timeout=0.1)
            lines.append(line.rstrip())
            log_area.code("\n".join(lines[-60:]), language="bash")
        except Empty:
            pass

    return proc.returncode


def render() -> None:
    st.subheader("Gerenciar Extração e Transformação")

    anos_disp = list(range(2015, 2026))

    # ── Extract ───────────────────────────────────────────────────────────
    with st.expander("▶ Extract — baixar dados brutos", expanded=True):
        c1, c2 = st.columns(2)
        anos_sel   = c1.multiselect("Anos",   anos_disp, default=[anos_disp[-1]], key="ext_anos")
        fontes_sel = c2.multiselect(
            "Fontes", list(FONTES_EXTRACT.keys()),
            default=["SISVAN", "IBGE", "MEC / INEP"],
            key="ext_fontes",
        )

        if st.button("▶ Extrair", key="btn_extract", type="primary"):
            if not anos_sel:
                st.warning("Selecione ao menos um ano.")
            elif not fontes_sel:
                st.warning("Selecione ao menos uma fonte.")
            else:
                log = st.empty()
                for ano in anos_sel:
                    for fonte in fontes_sel:
                        if fonte == "PNAES (FNDE)":
                            st.info("PNAES: URL não configurada — download manual necessário.")
                            continue
                        args = ["--ano", str(ano), "--only", FONTES_EXTRACT[fonte]]
                        st.markdown(f"**{fonte} {ano}**")
                        rc = _run_module("scripts.extract.run_all", args, log)
                        if rc == 0:
                            st.success(f"{fonte} {ano} concluído.")
                        else:
                            st.error(f"{fonte} {ano} falhou (código {rc}).")

    # ── Transform ─────────────────────────────────────────────────────────
    with st.expander("⚙️ Transform — processar arquivos", expanded=False):
        c1, c2 = st.columns(2)
        anos_t     = c1.multiselect("Anos",    anos_disp, default=[anos_disp[-1]], key="tf_anos")
        steps_sel  = c2.multiselect(
            "Etapas", list(FONTES_TRANSFORM.keys()),
            default=list(FONTES_TRANSFORM.keys())[:3],
            key="tf_steps",
        )

        if st.button("⚙️ Transformar", key="btn_transform", type="primary"):
            if not anos_t or not steps_sel:
                st.warning("Selecione anos e etapas.")
            else:
                log = st.empty()
                for ano in anos_t:
                    steps_flags = [FONTES_TRANSFORM[s] for s in steps_sel]
                    args = ["--ano", str(ano), "--only", *steps_flags]
                    st.markdown(f"**Transform {ano}**")
                    rc = _run_module("scripts.transform.run_all", args, log)
                    if rc == 0:
                        st.success(f"Transform {ano} concluído.")
                    else:
                        st.error(f"Transform {ano} falhou (código {rc}).")

        st.caption("Após transformar, volte à aba Catálogo para ver os arquivos atualizados.")

    # ── Repair ────────────────────────────────────────────────────────────
    with st.expander("🔧 Reparar percentuais / separadores", expanded=False):
        st.markdown(
            "Recalcula `percentual_que_*` e corrige separadores de milhar BR "
            "em todos os arquivos PNAES e SISVAN."
        )
        if st.button("🔧 Reparar", key="btn_repair"):
            log = st.empty()
            rc = _run_module("scripts.transform.repair_percentuais", [], log)
            if rc == 0:
                st.success("Reparo concluído.")
            else:
                st.error(f"Reparo falhou (código {rc}).")
