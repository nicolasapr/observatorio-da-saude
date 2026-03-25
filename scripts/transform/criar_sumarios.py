# transform/criar_sumarios.py
"""
CriarSumariosTransformer — une os arquivos de hábito de cada mês/faixa
em sumário mensal: sumario_habitos_{faixa}.xlsx

Entrada: dados/sisvan/mensais/{ano}/{mes}/{faixa}/{habito}.csv
Saída:   dados/sisvan/mensais/{ano}/{mes}/sumario_habitos_{faixa}.xlsx
"""
import pandas as pd
from pathlib import Path

from .base import BaseTransformer
from scripts.config import SISVAN_MENSAIS_DIR, COLUNAS_CADASTRAIS

FASES = ['Crianças de 2 a 4 anos', 'Crianças de 5 a 9 anos', 'Adolescentes']


class CriarSumariosTransformer(BaseTransformer):
    """
    Para cada mês de um ano, une os arquivos de hábito por faixa etária
    e salva sumario_habitos_{faixa}.xlsx na pasta do mês.
    """

    def __init__(self):
        super().__init__(SISVAN_MENSAIS_DIR)

    def transform(self, ano: int) -> None:
        pasta_ano = self.data_dir / str(ano)
        if not pasta_ano.exists():
            self._warn("Pasta %s não encontrada — pulando.", pasta_ano)
            return

        for pasta_mes in sorted(pasta_ano.iterdir()):
            if not pasta_mes.is_dir():
                continue
            for pasta_faixa in pasta_mes.iterdir():
                if pasta_faixa.is_dir():
                    self._processar_faixa(pasta_mes, pasta_faixa)

    # ------------------------------------------------------------------

    def _processar_faixa(self, pasta_mes: Path, pasta_faixa: Path) -> None:
        arquivos = sorted(
            f for f in pasta_faixa.iterdir()
            if f.suffix in ('.xlsx', '.xls', '.csv') and 'sumario' not in f.name.lower()
        )
        if not arquivos:
            return

        faixa_nome = pasta_faixa.name
        self._info("%s / %s — %d hábitos", pasta_mes.name, faixa_nome, len(arquivos))

        df_acumulado = None
        for arquivo in arquivos:
            habito = arquivo.stem
            try:
                df = self._ler_arquivo(arquivo, habito)
                if df is None:
                    continue
                df_acumulado = df if df_acumulado is None else pd.merge(
                    df_acumulado, df, on=COLUNAS_CADASTRAIS, how='outer'
                )
            except Exception as e:
                self._error("Erro em %s: %s", arquivo.name, e)

        if df_acumulado is not None:
            faixa_slug = faixa_nome.replace(' ', '_')
            caminho = pasta_mes / f'sumario_habitos_{faixa_slug}.xlsx'
            df_acumulado.to_excel(caminho, index=False)
            self._info("Salvo: %s", caminho.name)

    def _ler_arquivo(self, arquivo: Path, habito: str) -> pd.DataFrame | None:
        if arquivo.suffix in ('.xlsx', '.xls'):
            tabelas = pd.read_html(str(arquivo))
            df = tabelas[0]
        else:
            df = pd.read_csv(arquivo, encoding='latin1', sep=None, engine='python')

        if len(df.columns) < 8:
            self._warn("%s tem %d colunas — esperado 8, pulando.", arquivo.name, len(df.columns))
            return None

        df.columns = [
            'regiao', 'codigo_UF', 'UF', 'codigo_IBGE', 'municipio',
            f'total_que_{habito}',
            f'percentual_que_{habito}',
            f'total_all_{habito}',
            *[f'col_extra_{i}' for i in range(len(df.columns) - 8)],
        ]
        df = df[~df['regiao'].astype(str).str.contains('TOTAL', na=False)]
        return df
