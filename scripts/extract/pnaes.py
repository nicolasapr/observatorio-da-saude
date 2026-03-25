# extract/pnaes.py
"""
PNAESDownloader — placeholder para download dos arquivos Redes FNDE.

Os arquivos Redes*.xlsx do FNDE não têm URL pública estável automatizável.
Download manual:
  1. Acesse https://www.fnde.gov.br/index.php/programas/pnae/pnae-consultas/pnae-dados-abertos
  2. Baixe o arquivo "Redes" do ano desejado
  3. Salve em: dados/pnaes/redes/{ano}/{ano}Redes.xlsx

Quando a URL estiver disponível, implemente download() herdando BaseDownloader.
"""
from .base import BaseDownloader
from scripts.config import PNAES_REDES_DIR


class PNAESDownloader(BaseDownloader):
    """Placeholder — download manual necessário (ver docstring do módulo)."""

    def __init__(self, output_dir=None):
        super().__init__(output_dir or PNAES_REDES_DIR)

    def download(self, ano: int) -> None:
        raise NotImplementedError(
            f"Download automático do PNAES não implementado.\n"
            f"Salve o arquivo manualmente em: {self.output_dir / str(ano)}"
        )
