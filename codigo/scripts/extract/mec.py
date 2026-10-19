# extract/mec.py
"""
MECDownloader — baixa microdados do Censo Escolar (INEP).
Fonte: https://download.inep.gov.br/dados_abertos/

Saída: dados/mec/microdados/microdados_ed_basica_{ano}.csv

O INEP muda o nome/caminho do arquivo periodicamente. O downloader tenta
cada padrão de URL via HEAD antes de fazer o download, do mais recente
ao mais antigo.
"""
import os
import shutil
import tempfile
import zipfile

import pandas as pd

from .base import BaseDownloader
from .http import criar_sessao_inep
from scripts.config import MEC_MICRODADOS_DIR

# Padrões de URL em ordem de preferência (mais recente primeiro).
# Adicione novos padrões no topo quando o INEP mudar o caminho.
_URL_PATTERNS = [
    "https://download.inep.gov.br/dados_abertos/microdados_censo_escolar_{ano}.zip",
    "https://download.inep.gov.br/microdados/microdados_censo_escolar_{ano}.zip",
    "https://download.inep.gov.br/microdados/microdados_ed_basica_{ano}.zip",
]

# Termos aceitos no nome do CSV dentro do ZIP (ordem: mais específico → genérico)
_CSV_KEYWORDS = ["basica", "escola", "censo"]

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    )
}


class MECDownloader(BaseDownloader):
    """Baixa e extrai microdados do Censo Escolar para um ano."""

    def __init__(self, output_dir=None):
        super().__init__(output_dir or MEC_MICRODADOS_DIR)

    def download(self, ano: int) -> None:
        """Valida e salva o CSV escolar no nome canônico ed_basica."""
        caminho_csv = self.output_dir / f"microdados_ed_basica_{ano}.csv"
        nomes = {f'microdados_ed_basica_{ano}.csv', f'microdados_censo_escolar_{ano}.csv'}
        for existente in sorted(self.output_dir.iterdir()):
            if existente.name.lower() in nomes:
                self._validar_csv(existente)
                self._info("Já existe microdado válido: %s", existente.name)
                return existente

        url = self._descobrir_url(ano)
        if url is None:
            candidatos = [p.format(ano=ano) for p in _URL_PATTERNS]
            raise FileNotFoundError(
                f"Nenhuma URL válida encontrada para MEC {ano}. "
                f"Tentados: {candidatos}"
            )

        self._info("GET %s", url)
        with tempfile.TemporaryDirectory(prefix='.inep-', dir=self.output_dir) as temporaria:
            from pathlib import Path
            zip_path = Path(temporaria) / 'microdados.zip'
            csv_path = Path(temporaria) / 'microdados.csv'
            with criar_sessao_inep() as sessao:
                with sessao.get(url, headers=_HEADERS, stream=True, timeout=300) as resp:
                    resp.raise_for_status()
                    with zip_path.open('wb') as destino:
                        for bloco in resp.iter_content(chunk_size=1024 * 1024):
                            destino.write(bloco)
            with zipfile.ZipFile(zip_path) as z:
                csv_alvo = self._encontrar_csv(z.namelist(), ano)
                if csv_alvo is None:
                    raise FileNotFoundError(f'CSV escolar de {ano} não encontrado no ZIP')
                with z.open(csv_alvo) as origem, csv_path.open('wb') as destino:
                    shutil.copyfileobj(origem, destino)
            self._validar_csv(csv_path)
            os.replace(csv_path, caminho_csv)
        self._info("Salvo e validado: %s", caminho_csv.name)
        return caminho_csv

    @staticmethod
    def _validar_csv(caminho):
        colunas = set(pd.read_csv(caminho, sep=';', encoding='latin-1', nrows=0).columns)
        obrigatorias = {'CO_MUNICIPIO', 'TP_DEPENDENCIA', 'QT_MAT_MED', 'QT_MAT_FUND', 'QT_MAT_FUND_AF'}
        if not obrigatorias <= colunas:
            raise ValueError(f'Microdado escolar inválido em {caminho}: faltam {sorted(obrigatorias - colunas)}')
        if pd.read_csv(caminho, sep=';', encoding='latin-1', nrows=1).empty:
            raise ValueError(f'Microdado escolar sem registros em {caminho}')

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------

    def _descobrir_url(self, ano: int) -> str | None:
        """Testa cada padrão via HEAD e retorna a primeira URL que responder 200."""
        for padrao in _URL_PATTERNS:
            url = padrao.format(ano=ano)
            try:
                with criar_sessao_inep() as sessao:
                    r = sessao.head(url, headers=_HEADERS, timeout=15, allow_redirects=True)
                if r.status_code == 200:
                    self._info("URL encontrada: %s", url)
                    return url
                self._info("HEAD %s → %d (pulando)", url, r.status_code)
            except Exception as exc:
                self._warn("HEAD %s falhou: %s", url, exc)
        return None

    def _encontrar_csv(self, nomes: list[str], ano: int | None = None) -> str | None:
        """Retorna o CSV principal do ZIP, tolerando variações de nome."""
        from pathlib import PurePosixPath
        if ano is not None:
            for nome in [f'microdados_ed_basica_{ano}.csv', f'microdados_censo_escolar_{ano}.csv']:
                candidatos = [n for n in nomes if PurePosixPath(n).name.lower() == nome]
                if len(candidatos) == 1:
                    return candidatos[0]
        for kw in _CSV_KEYWORDS:
            alvos = [n for n in nomes if n.lower().endswith('.csv') and kw in PurePosixPath(n).name.lower()]
            if len(alvos) == 1:
                return alvos[0]
        return None
