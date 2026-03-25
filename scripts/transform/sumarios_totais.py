# transform/sumarios_totais.py
"""
SumariosTotaisTransformer — agrega os sumários anuais de TODOS os anos
em um único sumário histórico por faixa etária.

Entrada: dados/sisvan/anuais/{ano}/sumario_anual_habitos_{faixa}.xlsx
Saída:   dados/sisvan/historico/sumario_total_habitos_{faixa}.xlsx

O parâmetro `ano` é ignorado — todos os anos disponíveis são processados.
"""
import pandas as pd

from .base import BaseTransformer
from scripts.config import SISVAN_ANUAIS_DIR, SISVAN_HISTORICO_DIR, COLUNAS_CADASTRAIS, FASES_SLUGS


class SumariosTotaisTransformer(BaseTransformer):
    """
    Concatena sumários anuais de todos os anos e agrupa por município.
    O parâmetro `ano` é ignorado — todos os anos disponíveis são processados.
    """

    def __init__(self):
        super().__init__(SISVAN_ANUAIS_DIR, SISVAN_HISTORICO_DIR)

    def transform(self, ano: int = 0) -> None:
        anos = self._anos_disponiveis()
        if not anos:
            self._warn("Nenhum ano encontrado em %s", self.data_dir)
            return
        self._info("Processando anos: %s", anos)

        for faixa_slug in FASES_SLUGS:
            self._processar_faixa_total(faixa_slug, anos)

    # ------------------------------------------------------------------

    def _processar_faixa_total(self, faixa_slug: str, anos: list[int]) -> None:
        nome_arquivo = f'sumario_anual_habitos_{faixa_slug}.xlsx'
        frames = []

        for ano in anos:
            caminho = self.data_dir / str(ano) / nome_arquivo
            if not caminho.exists():
                self._warn("  Sumário anual não encontrado: %s", caminho)
                continue
            df = pd.read_excel(caminho)
            frames.append(df)
            self._info("  Ano %s — %d municípios", ano, len(df))

        if not frames:
            self._warn("Nenhum dado encontrado para %s", faixa_slug)
            return

        df_total = pd.concat(frames, ignore_index=True)

        # Colunas de hábito derivadas dinamicamente — excluindo cadastrais
        colunas_habitos = [c for c in df_total.columns if c not in COLUNAS_CADASTRAIS]
        df_total[colunas_habitos] = df_total[colunas_habitos].apply(
            pd.to_numeric, errors='coerce'
        )

        df_historico = df_total.groupby(COLUNAS_CADASTRAIS, as_index=False)[colunas_habitos].sum()

        caminho_saida = self.output_dir / f'sumario_total_habitos_{faixa_slug}.xlsx'
        df_historico.to_excel(caminho_saida, index=False)
        self._info("Total salvo: %s (%d municípios)", caminho_saida.name, len(df_historico))
