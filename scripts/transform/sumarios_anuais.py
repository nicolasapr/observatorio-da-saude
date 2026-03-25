# transform/sumarios_anuais.py
"""
SumariosAnuaisTransformer — agrega os sumários mensais de um ano em um
único sumário anual por faixa etária.

Entrada: dados/sisvan/mensais/{ano}/{mes}/sumario_habitos_{faixa}.xlsx
Saída:   dados/sisvan/anuais/{ano}/sumario_anual_habitos_{faixa}.xlsx
"""
import pandas as pd
from pathlib import Path

from .base import BaseTransformer
from scripts.config import SISVAN_MENSAIS_DIR, SISVAN_ANUAIS_DIR, COLUNAS_CADASTRAIS, FASES_SLUGS


class SumariosAnuaisTransformer(BaseTransformer):
    """
    Para cada faixa etária, concatena todos os sumários mensais de um ano
    e agrupa por município, somando os valores de hábito.
    """

    def __init__(self):
        super().__init__(SISVAN_MENSAIS_DIR, SISVAN_ANUAIS_DIR)

    def transform(self, ano: int) -> None:
        pasta_ano = self.data_dir / str(ano)
        if not pasta_ano.exists():
            self._warn("Pasta %s não encontrada — pulando.", pasta_ano)
            return

        pasta_saida = self.output_dir / str(ano)
        pasta_saida.mkdir(parents=True, exist_ok=True)

        for faixa_slug in FASES_SLUGS:
            self._processar_faixa_anual(pasta_ano, pasta_saida, faixa_slug)

    # ------------------------------------------------------------------

    def _processar_faixa_anual(self, pasta_ano: Path, pasta_saida: Path, faixa_slug: str) -> None:
        nome_arquivo = f'sumario_habitos_{faixa_slug}.xlsx'
        frames = []

        for pasta_mes in sorted(pasta_ano.iterdir()):
            if not pasta_mes.is_dir():
                continue
            caminho = pasta_mes / nome_arquivo
            if not caminho.exists():
                continue
            df = pd.read_excel(caminho)
            frames.append(df)
            self._info("  %s / %s — %d linhas", pasta_ano.name, pasta_mes.name, len(df))

        if not frames:
            self._warn("Nenhum sumário mensal para %s em %s", faixa_slug, pasta_ano.name)
            return

        df_total = pd.concat(frames, ignore_index=True)

        # total_que_* e total_all_* são somáveis;
        # percentual_que_* são recalculados a partir dos totais — nunca somados.
        colunas_somaveis = [
            c for c in df_total.columns
            if c not in COLUNAS_CADASTRAIS and not c.startswith('percentual_que_')
        ]
        colunas_perc = [c for c in df_total.columns if c.startswith('percentual_que_')]

        df_total[colunas_somaveis] = df_total[colunas_somaveis].apply(
            pd.to_numeric, errors='coerce'
        )

        df_anual = df_total.groupby(COLUNAS_CADASTRAIS, as_index=False)[colunas_somaveis].sum()

        # Recalcula percentuais a partir dos totais somados
        for col_perc in colunas_perc:
            habito = col_perc.removeprefix('percentual_que_')
            col_num = f'total_que_{habito}'
            col_den = f'total_all_{habito}'
            if col_num in df_anual.columns and col_den in df_anual.columns:
                df_anual[col_perc] = df_anual[col_num] / df_anual[col_den].replace(0, pd.NA)
            else:
                df_anual[col_perc] = pd.NA

        # Reordena colunas: cadastrais + (total_que, percentual_que, total_all) por hábito
        cols_ordenadas = list(COLUNAS_CADASTRAIS)
        for col_perc in colunas_perc:
            habito = col_perc.removeprefix('percentual_que_')
            for prefix in ('total_que_', 'percentual_que_', 'total_all_'):
                c = f'{prefix}{habito}'
                if c in df_anual.columns:
                    cols_ordenadas.append(c)
        df_anual = df_anual[cols_ordenadas]

        caminho_saida = pasta_saida / f'sumario_anual_habitos_{faixa_slug}.xlsx'
        df_anual.to_excel(caminho_saida, index=False)
        self._info("Anual salvo: %s (%d municípios)", caminho_saida.name, len(df_anual))
