# extract/ibge.py
"""
IBGEDownloader — baixa estimativas populacionais da API SIDRA do IBGE.
Tabela 6579, variável 9324, nível município (N6).

Saída: dados/referencia/ibge/ibge_pop_{ano}.csv
"""
import requests
import pandas as pd
from pathlib import Path

from .base import BaseDownloader
from scripts.config import REFERENCIA_IBGE_DIR

SIDRA_URL = (
    "https://servicodados.ibge.gov.br/api/v3/agregados/6579"
    "/periodos/{ano}/variaveis/9324"
    "?localidades=N6[all]"
)


class IBGEDownloader(BaseDownloader):
    """Baixa estimativas populacionais por município para um ano."""

    def __init__(self, output_dir=None):
        super().__init__(output_dir or REFERENCIA_IBGE_DIR)

    def download(self, ano: int) -> None:
        """Saída: {output_dir}/ibge_pop_{ano}.csv"""
        caminho = self.output_dir / f"ibge_pop_{ano}.csv"
        if caminho.exists():
            self._info("Já existe %s — pulando.", caminho.name)
            return

        url = SIDRA_URL.format(ano=ano)
        self._info("GET %s", url)

        resp = requests.get(url, timeout=60)
        resp.raise_for_status()
        dados = resp.json()

        registros = []
        for item in dados[0].get("resultados", []):
            for serie in item.get("series", []):
                for periodo, valor in serie["serie"].items():
                    registros.append({
                        "ano":         periodo,
                        "codigo_ibge": serie["localidade"]["id"],
                        "municipio":   serie["localidade"]["nome"],
                        "populacao":   valor,
                    })

        df = pd.DataFrame(registros)
        df.to_csv(caminho, index=False, encoding="utf-8-sig")
        self._info("Salvo: %s (%d linhas)", caminho.name, len(df))
