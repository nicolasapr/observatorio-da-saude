# transform/pnaes.py
"""
Transformers PNAES — calculam o TOTAL de repasse por município para cada faixa etária.

Classes:
    PNAES2a4Transformer          — PNACN * CR + PNAPN(4) * PE
    PNAES5a9Transformer          — PNAPN(5) * PN + PNAFN(6-9) * FN
    PNAESAdolescentesTransformer — merge MEC + percentuais + TOTAL_EF

Entrada: dados/pnaes/valores/{faixa}/PNAES_valores_{faixa}_{ano}.xlsx
         dados/mec/microdados/microdados_ed_basica_{ano}.csv  (Adolescentes)
Saída:   dados/pnaes/finais/{faixa}/PNAES_valores_{faixa}_{ano}_ajustado.xlsx
"""
import pandas as pd

from .base import BaseTransformer
from scripts.config import PNAES_VALORES_DIR, PNAES_FINAIS_DIR, MEC_MICRODADOS_DIR


# ---------------------------------------------------------------------------
# Helper compartilhado
# ---------------------------------------------------------------------------

def _converter_numericas(df: pd.DataFrame, colunas: list[str]) -> pd.DataFrame:
    df = df.copy()
    for col in colunas:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    return df


# ---------------------------------------------------------------------------
# 2a4
# ---------------------------------------------------------------------------

class PNAES2a4Transformer(BaseTransformer):
    """
    Entrada:  dados/pnaes/valores/2a4/PNAES_valores_2a4_{ano}.xlsx
    Saída:    dados/pnaes/finais/2a4/PNAES_valores_2a4_{ano}_ajustado.xlsx

    Adiciona coluna TOTAL = PNACN * valor_pago_CR + PNAPN(4) * valor_pago_PE
    """

    def __init__(self):
        super().__init__(PNAES_VALORES_DIR, PNAES_FINAIS_DIR)

    def transform(self, ano: int) -> None:
        entrada = self.data_dir / '2a4' / f'PNAES_valores_2a4_{ano}.xlsx'
        if not entrada.exists():
            self._warn("Arquivo não encontrado: %s", entrada)
            return

        df = pd.read_excel(entrada)
        df = _converter_numericas(df, ['PNACN', 'PNAPN(4)', 'valor_pago_CR', 'valor_pago_PE'])
        df['TOTAL'] = (
            df['PNACN'] * df['valor_pago_CR'] + df['PNAPN(4)'] * df['valor_pago_PE']
        ).fillna(0)

        saida = self.output_dir / '2a4'
        saida.mkdir(parents=True, exist_ok=True)
        caminho = saida / f'PNAES_valores_2a4_{ano}_ajustado.xlsx'
        df.to_excel(caminho, index=False)
        self._info("Salvo: %s (%d municípios)", caminho.name, len(df))


# ---------------------------------------------------------------------------
# 5a9
# ---------------------------------------------------------------------------

class PNAES5a9Transformer(BaseTransformer):
    """
    Entrada:  dados/pnaes/valores/5a9/PNAES_valores_5a9_{ano}.xlsx
    Saída:    dados/pnaes/finais/5a9/PNAES_valores_5a9_{ano}_ajustado.xlsx

    Adiciona coluna TOTAL = PNAPN(5) * valor_pago_PN + PNAFN(6-9) * valor_pago_FN
    """

    def __init__(self):
        super().__init__(PNAES_VALORES_DIR, PNAES_FINAIS_DIR)

    def transform(self, ano: int) -> None:
        entrada = self.data_dir / '5a9' / f'PNAES_valores_5a9_{ano}.xlsx'
        if not entrada.exists():
            self._warn("Arquivo não encontrado: %s", entrada)
            return

        df = pd.read_excel(entrada)
        df = _converter_numericas(df, ['PNAPN(5)', 'PNAFN(6-9)', 'valor_pago_PN', 'valor_pago_FN'])
        df['TOTAL'] = (
            df['PNAPN(5)'] * df['valor_pago_PN'] + df['PNAFN(6-9)'] * df['valor_pago_FN']
        ).fillna(0)

        saida = self.output_dir / '5a9'
        saida.mkdir(parents=True, exist_ok=True)
        caminho = saida / f'PNAES_valores_5a9_{ano}_ajustado.xlsx'
        df.to_excel(caminho, index=False)
        self._info("Salvo: %s (%d municípios)", caminho.name, len(df))


# ---------------------------------------------------------------------------
# Adolescentes
# ---------------------------------------------------------------------------

class PNAESAdolescentesTransformer(BaseTransformer):
    """
    Entrada:  dados/pnaes/valores/Adolescentes/PNAES_valores_Adolescentes_{ano}.xlsx
              dados/mec/microdados/microdados_ed_basica_{ano}.csv
    Saída:    dados/pnaes/finais/Adolescentes/PNAES_valores_Adolescentes_{ano}_ajustado.xlsx

    Transformações:
    1. Agrega microdados MEC por cidade e por UF
    2. Merge com dados PNAES via nome de município normalizado
    3. Calcula percen_MAT_MED, percen_MAT_FUND, percen_MAT_FUND_AF
    4. Calcula TOTAL_EF = valor_pago_secretarias_EM * percen_MAT_MED
                        + valor_pago_FN * percen_MAT_FUND_AF
    """

    def __init__(self):
        super().__init__(PNAES_VALORES_DIR, PNAES_FINAIS_DIR)
        self.mec_dir = MEC_MICRODADOS_DIR

    def transform(self, ano: int) -> None:
        entrada_pnaes = self.data_dir / 'Adolescentes' / f'PNAES_valores_Adolescentes_{ano}.xlsx'
        entrada_mec   = self.mec_dir / f'microdados_ed_basica_{ano}.csv'

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

        cols_qt = ['QT_MAT_MED', 'QT_MAT_FUND', 'QT_MAT_FUND_AF']
        por_cidade = (
            microdados
            .groupby('NO_MUNICIPIO')
            .agg({'SG_UF': 'first', **{c: 'sum' for c in cols_qt}})
            .reset_index()
        )
        por_cidade['SG_UF'] = por_cidade['SG_UF'].str[:2]

        por_uf = microdados.groupby('SG_UF')[cols_qt].sum().reset_index()

        completo = por_cidade.merge(por_uf, on='SG_UF', suffixes=('_cidade', '_UF'))
        completo = completo[[
            'NO_MUNICIPIO',
            'QT_MAT_MED_cidade', 'QT_MAT_FUND_cidade', 'QT_MAT_FUND_AF_cidade',
            'QT_MAT_MED_UF',     'QT_MAT_FUND_UF',     'QT_MAT_FUND_AF_UF',
        ]]

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
                df[percen_col] = (
                    pd.to_numeric(df[cidade_col], errors='coerce') /
                    pd.to_numeric(df[uf_col],     errors='coerce')
                )

        # ------------------------------------------------------------------
        # 4. TOTAL_EF
        # ------------------------------------------------------------------
        _colunas_total = ['valor_pago_secretarias_EM', 'percen_MAT_MED',
                          'valor_pago_FN', 'percen_MAT_FUND_AF']
        if all(c in df.columns for c in _colunas_total):
            df['TOTAL_EF'] = (
                pd.to_numeric(df['valor_pago_secretarias_EM'], errors='coerce') *
                pd.to_numeric(df['percen_MAT_MED'],            errors='coerce') +
                pd.to_numeric(df['valor_pago_FN'],             errors='coerce') *
                pd.to_numeric(df['percen_MAT_FUND_AF'],        errors='coerce')
            ).fillna(0)

        # ------------------------------------------------------------------
        # 5. Salva
        # ------------------------------------------------------------------
        saida = self.output_dir / 'Adolescentes'
        saida.mkdir(parents=True, exist_ok=True)
        caminho = saida / f'PNAES_valores_Adolescentes_{ano}_ajustado.xlsx'
        df.to_excel(caminho, index=False)
        self._info("Salvo: %s (%d municípios, %d colunas)", caminho.name, len(df), len(df.columns))
