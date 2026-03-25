# extract/mec.py
"""
MECDownloader — baixa microdados do Censo Escolar (INEP).
Fonte: https://download.inep.gov.br/microdados/

Saída: dados/mec/microdados/microdados_ed_basica_{ano}.csv
"""
import io
import shutil
import zipfile

import requests

from .base import BaseDownloader
from scripts.config import MEC_MICRODADOS_DIR

INEP_URL = "https://download.inep.gov.br/microdados/microdados_ed_basica_{ano}.zip"


class MECDownloader(BaseDownloader):
    """Baixa e extrai microdados do Censo Escolar para um ano."""

    def __init__(self, output_dir=None):
        super().__init__(output_dir or MEC_MICRODADOS_DIR)

    def download(self, ano: int) -> None:
        """Saída: {output_dir}/microdados_ed_basica_{ano}.csv"""
        caminho_csv = self.output_dir / f"microdados_ed_basica_{ano}.csv"
        if caminho_csv.exists():
            self._info("Já existe %s — pulando.", caminho_csv.name)
            return

        url = INEP_URL.format(ano=ano)
        self._info("GET %s", url)

        with requests.get(url, stream=True, timeout=300) as resp:
            resp.raise_for_status()
            conteudo = b"".join(resp.iter_content(chunk_size=8192))

        self._info("Download completo (%d MB) — extraindo ZIP...", len(conteudo) // 1_000_000)

        with zipfile.ZipFile(io.BytesIO(conteudo)) as z:
            nomes = z.namelist()
            csv_alvo = next(
                (n for n in nomes if n.lower().endswith(".csv") and "basica" in n.lower()),
                None,
            )
            if csv_alvo is None:
                raise FileNotFoundError(
                    f"CSV de educação básica não encontrado no ZIP. Arquivos: {nomes}"
                )
            with z.open(csv_alvo) as origem, open(caminho_csv, "wb") as destino:
                shutil.copyfileobj(origem, destino)

        self._info("Salvo: %s", caminho_csv.name)
