# load/utils.py
"""
Inventário de arquivos do pipeline — varre todas as pastas de dados
e retorna um resumo por ano.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass
from pathlib import Path

from scripts.config import (
    ANOS_DISPONIVEIS,
    FASES_SLUGS,
    PNAES_REDES_DIR,
    PNAES_PERCEN_DIR,
    PNAES_VALORES_DIR,
    PNAES_FINAIS_DIR,
    SISVAN_ANUAIS_DIR,
    MEC_MICRODADOS_DIR,
)

ANOS   = ANOS_DISPONIVEIS
FAIXAS = ["2a4", "5a9", "Adolescentes"]

COLUNAS = [
    ("redes",               "Redes FNDE"),
    ("sisvan_2a4",          "SISVAN 2–4a"),
    ("sisvan_5a9",          "SISVAN 5–9a"),
    ("sisvan_adol",         "SISVAN Adol."),
    ("mec",                 "MEC"),
    ("percen_2a4",          "Percen 2a4"),
    ("percen_5a9",          "Percen 5a9"),
    ("percen_Adolescentes", "Percen Adol."),
    ("valores_2a4",         "Valores 2a4"),
    ("valores_5a9",         "Valores 5a9"),
    ("valores_Adolescentes","Valores Adol."),
    ("final_2a4",           "Final 2a4"),
    ("final_5a9",           "Final 5a9"),
    ("final_Adolescentes",  "Final Adol."),
]


@dataclass
class FileInfo:
    path:     Path | None
    exists:   bool
    size_kb:  float = 0.0
    modified: datetime.datetime | None = None
    warning:  str = ""

    @property
    def status(self) -> str:
        if not self.exists:
            return "❌"
        if self.warning:
            return "⚠️"
        return "✅"

    @property
    def label(self) -> str:
        if not self.exists:
            return "❌  ausente"
        ts   = self.modified.strftime("%d/%m/%Y") if self.modified else "?"
        kb   = f"{self.size_kb:.0f} KB"
        warn = f"  {self.warning}" if self.warning else ""
        return f"{self.status}  {kb}  ({ts}){warn}"


def _fi(path: Path, warning: str = "") -> FileInfo:
    if path.exists():
        st = path.stat()
        return FileInfo(
            path, True,
            st.st_size / 1024,
            datetime.datetime.fromtimestamp(st.st_mtime),
            warning,
        )
    return FileInfo(None, False, warning=warning)


def scan_data_dir() -> dict[int, dict[str, FileInfo]]:
    """Varre as pastas de dados e retorna inventário {ano: {chave: FileInfo}}."""
    result: dict[int, dict[str, FileInfo]] = {}

    # Mapeamento: chave inventário → slug faixa SISVAN
    sisvan_map = {
        "sisvan_2a4":  FASES_SLUGS[0],   # Crianças_de_2_a_4_anos
        "sisvan_5a9":  FASES_SLUGS[1],   # Crianças_de_5_a_9_anos
        "sisvan_adol": FASES_SLUGS[2],   # Adolescentes
    }

    for ano in ANOS:
        row: dict[str, FileInfo] = {}

        # Redes FNDE
        pasta_redes = PNAES_REDES_DIR / str(ano)
        redes_files = (
            [f for f in pasta_redes.glob("*EDES*") if not f.name.startswith(".~lock.")]
            if pasta_redes.exists() else []
        )
        if redes_files:
            warn = "VALOR_PREVISTO (orçado)" if ano >= 2024 else ""
            row["redes"] = _fi(redes_files[0], warn)
        else:
            row["redes"] = FileInfo(None, False)

        # SISVAN sumários anuais
        for key, faixa_slug in sisvan_map.items():
            row[key] = _fi(SISVAN_ANUAIS_DIR / str(ano) / f"sumario_anual_habitos_{faixa_slug}.xlsx")

        # MEC microdados
        row["mec"] = _fi(MEC_MICRODADOS_DIR / f"microdados_ed_basica_{ano}.csv")

        # Percen, Valores, Finais
        for faixa in FAIXAS:
            row[f"percen_{faixa}"] = _fi(
                PNAES_PERCEN_DIR / faixa / f"PNAES_Percen_{faixa}_{ano}.xlsx"
            )
            row[f"valores_{faixa}"] = _fi(
                PNAES_VALORES_DIR / faixa / f"PNAES_valores_{faixa}_{ano}.xlsx"
            )
            row[f"final_{faixa}"] = _fi(
                PNAES_FINAIS_DIR / faixa / f"PNAES_valores_{faixa}_{ano}_ajustado.xlsx"
            )

        result[ano] = row

    return result
