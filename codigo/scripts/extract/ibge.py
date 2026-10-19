# extract/ibge.py
"""
IBGEDownloader — baixa estimativas populacionais da API SIDRA do IBGE.
Tabela 6579, variável 9324, nível município (N6).

Saída: dados/referencia/ibge/ibge_pop_{ano}.csv
"""
import requests
import pandas as pd
from pathlib import Path
import os
import tempfile

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
            existente = pd.read_csv(caminho)
            obrigatorias = {'ano', 'codigo_ibge', 'municipio', 'populacao'}
            if not obrigatorias <= set(existente) or existente.empty:
                raise ValueError(f'Cache SIDRA inválido: {caminho}')
            if not existente['ano'].astype(str).eq(str(ano)).all() or existente['codigo_ibge'].duplicated().any():
                raise ValueError(f'Ano ou códigos inválidos no cache SIDRA: {caminho}')
            self._info("Já existe %s — pulando.", caminho.name)
            return

        url = SIDRA_URL.format(ano=ano)
        self._info("GET %s", url)

        resp = requests.get(url, timeout=60)
        resp.raise_for_status()
        dados = resp.json()
        if not isinstance(dados, list) or not dados or 'resultados' not in dados[0]:
            raise ValueError(f'Resposta SIDRA inválida para {ano}')

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
        if df.empty or not df['ano'].astype(str).eq(str(ano)).all():
            raise ValueError(f'SIDRA não contém estimativas municipais de {ano}')
        df['populacao_fonte'] = df['populacao']
        df['populacao'] = pd.to_numeric(df['populacao'], errors='coerce')
        ausentes = int(df['populacao'].isna().sum())
        if ausentes:
            self._warn('%d localidades com população não numérica; texto original preservado, sem substituir por zero', ausentes)
        if df['codigo_ibge'].duplicated().any() or not df['populacao'].dropna().gt(0).all() or not df['populacao'].notna().any():
            raise ValueError(f'Estimativas SIDRA inválidas para {ano}')
        tmp = None
        try:
            with tempfile.NamedTemporaryFile(dir=self.output_dir, prefix='.ibge-', suffix='.csv', delete=False) as arquivo:
                tmp = Path(arquivo.name)
            df.to_csv(tmp, index=False, encoding="utf-8-sig")
            os.replace(tmp, caminho)
        finally:
            if tmp is not None:
                tmp.unlink(missing_ok=True)
        self._info("Salvo: %s (%d linhas)", caminho.name, len(df))
