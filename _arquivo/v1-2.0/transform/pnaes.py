# transform/pnaes.py
"""
Transformers PNAES — calculam o TOTAL de repasse por município para cada faixa etária.

Classes:
    PNAESRedesTransformer        — Redes*.xlsx → Valores_PNAES_* (pivot + merge Percen)
    PNAES2a4Transformer         — PNACN * CR + PNAPN(4) * PE
    PNAES5a9Transformer         — PNAPN(5) * PN + PNAFN(6-9) * FN
    PNAESAdolescentesTransformer — merge MEC + percentuais + TOTAL_EF

Entradas e saídas por classe estão documentadas em cada `transform()`.
"""
import pandas as pd
from pathlib import Path
from .base import BaseTransformer


# ---------------------------------------------------------------------------
# 2a4
# ---------------------------------------------------------------------------

class PNAES2a4Transformer(BaseTransformer):
    """
    Entrada:  {data_dir}/Valores_PNAES_2a4/PNAES_valores_2a4_{ano}.xlsx
    Saída:    {output_dir}/Finais/2a4/PNAES_valores_2a4_{ano}_ajustado.xlsx

    Adiciona coluna TOTAL = PNACN * valor_pago_CR + PNAPN(4) * valor_pago_PE
    """

    def transform(self, ano: int) -> None:
        entrada = self.data_dir / 'Valores_PNAES_2a4' / f'PNAES_valores_2a4_{ano}.xlsx'
        if not entrada.exists():
            self._warn("Arquivo não encontrado: %s", entrada)
            return

        df = pd.read_excel(entrada)
        df = self._converter_numericas(df, ['PNACN', 'PNAPN(4)', 'valor_pago_CR', 'valor_pago_PE'])
        df['TOTAL'] = (df['PNACN'] * df['valor_pago_CR'] + df['PNAPN(4)'] * df['valor_pago_PE']).fillna(0)

        saida = self.output_dir / 'Finais' / '2a4'
        saida.mkdir(parents=True, exist_ok=True)
        caminho = saida / f'PNAES_valores_2a4_{ano}_ajustado.xlsx'
        df.to_excel(caminho, index=False)
        self._info("Salvo: %s (%d municípios)", caminho, len(df))

    @staticmethod
    def _converter_numericas(df: pd.DataFrame, colunas: list[str]) -> pd.DataFrame:
        df = df.copy()
        for col in colunas:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        return df


# ---------------------------------------------------------------------------
# 5a9
# ---------------------------------------------------------------------------

class PNAES5a9Transformer(BaseTransformer):
    """
    Entrada:  {data_dir}/Valores_PNAES_5a9/PNAES_valores_5a9_{ano}.xlsx
    Saída:    {output_dir}/Finais/5a9/PNAES_valores_5a9_{ano}_ajustado.xlsx

    Adiciona coluna TOTAL = PNAPN(5) * valor_pago_PN + PNAFN(6-9) * valor_pago_FN
    """

    def transform(self, ano: int) -> None:
        entrada = self.data_dir / 'Valores_PNAES_5a9' / f'PNAES_valores_5a9_{ano}.xlsx'
        if not entrada.exists():
            self._warn("Arquivo não encontrado: %s", entrada)
            return

        df = pd.read_excel(entrada)
        df = self._converter_numericas(df, ['PNAPN(5)', 'PNAFN(6-9)', 'valor_pago_PN', 'valor_pago_FN'])
        df['TOTAL'] = (df['PNAPN(5)'] * df['valor_pago_PN'] + df['PNAFN(6-9)'] * df['valor_pago_FN']).fillna(0)

        saida = self.output_dir / 'Finais' / '5a9'
        saida.mkdir(parents=True, exist_ok=True)
        caminho = saida / f'PNAES_valores_5a9_{ano}_ajustado.xlsx'
        df.to_excel(caminho, index=False)
        self._info("Salvo: %s (%d municípios)", caminho, len(df))

    @staticmethod
    def _converter_numericas(df: pd.DataFrame, colunas: list[str]) -> pd.DataFrame:
        df = df.copy()
        for col in colunas:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        return df


# ---------------------------------------------------------------------------
# Adolescentes
# ---------------------------------------------------------------------------

class PNAESAdolescentesTransformer(BaseTransformer):
    """
    Entrada:  {data_dir}/Valores_PNAES_Adolescentes/PNAES_valores_Adolescentes_{ano}.xlsx
              {data_dir}/microdados/microdados_ed_basica_{ano}.csv
    Saída:    {output_dir}/Finais/Adolescentes/PNAES_valores_Adolescentes_{ano}_ajustado.xlsx

    Transformações:
    1. Agrega microdados MEC por cidade e por UF
    2. Merge com dados PNAES via nome de município normalizado
    3. Calcula percen_MAT_MED, percen_MAT_FUND, percen_MAT_FUND_AF
    4. Calcula TOTAL_EF = valor_pago_secretarias_EM * percen_MAT_MED + valor_pago_FN * percen_MAT_FUND_AF
    """

    def transform(self, ano: int) -> None:
        entrada_pnaes = (
            self.data_dir
            / 'Valores_PNAES_Adolescentes'
            / f'PNAES_valores_Adolescentes_{ano}.xlsx'
        )
        entrada_mec = (
            self.data_dir / 'microdados' / f'microdados_ed_basica_{ano}.csv'
        )

        if not entrada_pnaes.exists():
            self._warn("PNAES não encontrado: %s", entrada_pnaes)
            return
        if not entrada_mec.exists():
            self._warn("Microdados MEC não encontrado: %s", entrada_mec)
            return

        self._info("Processando ano %s...", ano)

        # ------------------------------------------------------------------
        # 1. Carrega e agrega microdados MEC
        # ------------------------------------------------------------------
        microdados = pd.read_csv(
            entrada_mec,
            encoding='latin-1',
            sep=';',
            on_bad_lines='skip',
            usecols=['SG_UF', 'NO_MUNICIPIO', 'QT_MAT_MED', 'QT_MAT_FUND', 'QT_MAT_FUND_AF'],
        )

        # Agrupamento por cidade — SG_UF é string, usa 'first' (mesmo UF para todas as linhas)
        cols_qt = ['QT_MAT_MED', 'QT_MAT_FUND', 'QT_MAT_FUND_AF']
        por_cidade = (
            microdados
            .groupby('NO_MUNICIPIO')
            .agg({'SG_UF': 'first', **{c: 'sum' for c in cols_qt}})
            .reset_index()
        )
        por_cidade['SG_UF'] = por_cidade['SG_UF'].str[:2]

        # Agrupamento por UF — apenas colunas numéricas
        por_uf = microdados.groupby('SG_UF')[cols_qt].sum().reset_index()

        # Merge cidade × UF para ter ambos os níveis
        completo = por_cidade.merge(por_uf, on='SG_UF', suffixes=('_cidade', '_UF'))
        completo = completo[[
            'NO_MUNICIPIO', 'QT_MAT_MED_cidade', 'QT_MAT_FUND_cidade',
            'QT_MAT_FUND_AF_cidade', 'QT_MAT_MED_UF', 'QT_MAT_FUND_UF', 'QT_MAT_FUND_AF_UF',
        ]]

        # Normaliza nome do município: maiúsculas + remove acentos
        completo['NO_MUNICIPIO'] = (
            completo['NO_MUNICIPIO']
            .str.upper()
            .str.normalize('NFKD')
            .str.encode('ascii', errors='ignore')
            .str.decode('utf-8')
        )

        # ------------------------------------------------------------------
        # 2. Merge com dados PNAES
        # ------------------------------------------------------------------
        pnaes = pd.read_excel(entrada_pnaes)
        df = pnaes.merge(completo, left_on='municipio', right_on='NO_MUNICIPIO', how='left')
        df = df.drop(columns=['NO_MUNICIPIO'], errors='ignore')

        # ------------------------------------------------------------------
        # 3. Percentuais de matrícula (cidade / UF)
        # ------------------------------------------------------------------
        for nivel in ['MED', 'FUND', 'FUND_AF']:
            cidade_col = f'QT_MAT_{nivel}_cidade'
            uf_col     = f'QT_MAT_{nivel}_UF'
            percen_col = f'percen_MAT_{nivel}'
            if cidade_col in df.columns and uf_col in df.columns:
                df[percen_col] = pd.to_numeric(df[cidade_col], errors='coerce') / \
                                 pd.to_numeric(df[uf_col], errors='coerce')

        # ------------------------------------------------------------------
        # 4. TOTAL_EF
        # ------------------------------------------------------------------
        if all(c in df.columns for c in ['valor_pago_secretarias_EM', 'percen_MAT_MED', 'valor_pago_FN', 'percen_MAT_FUND_AF']):
            df['TOTAL_EF'] = (
                pd.to_numeric(df['valor_pago_secretarias_EM'], errors='coerce') *
                pd.to_numeric(df['percen_MAT_MED'],            errors='coerce') +
                pd.to_numeric(df['valor_pago_FN'],             errors='coerce') *
                pd.to_numeric(df['percen_MAT_FUND_AF'],        errors='coerce')
            ).fillna(0)

        # ------------------------------------------------------------------
        # 5. Salva
        # ------------------------------------------------------------------
        saida = self.output_dir / 'Finais' / 'Adolescentes'
        saida.mkdir(parents=True, exist_ok=True)
        caminho = saida / f'PNAES_valores_Adolescentes_{ano}_ajustado.xlsx'
        df.to_excel(caminho, index=False)
        self._info("Salvo: %s (%d municípios, %d colunas)", caminho, len(df), len(df.columns))


# Nota: PNAESRedesTransformer foi movido para pnaes_redes.py (versão canônica).
# Esta classe foi removida para evitar duplicação e confusão de importações.
