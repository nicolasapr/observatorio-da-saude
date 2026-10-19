# transform/pnaes.py
"""
Transformers PNAES — calculam o TOTAL de repasse por município para cada faixa etária.

Classes:
    PNAES2a4Transformer          — PNACN * CR + PNAPN(4) * PE
    PNAES5a9Transformer          — PNAPN(5) * PN + PNAFN(6-9) * FN
    PNAESAdolescentesTransformer — merge MEC + pesos de matrícula + total adolescente

Entrada: dados/pnaes/valores/{faixa}/PNAES_valores_{faixa}_{ano}.xlsx
         dados/mec/microdados/microdados_ed_basica_{ano}.csv  (Adolescentes)
Saída:   dados/pnaes/finais/{faixa}/PNAES_valores_{faixa}_{ano}_ajustado.xlsx
"""
import pandas as pd

from .base import BaseTransformer
from .io_seguro import salvar_excel
from scripts.config import PNAES_VALORES_DIR, PNAES_FINAIS_DIR, MEC_MICRODADOS_DIR, localizar_microdados


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
            raise FileNotFoundError(entrada)

        df = pd.read_excel(entrada)
        df = _converter_numericas(df, ['PNACN', 'PNAPN(4)', 'valor_pago_CR', 'valor_pago_PE'])
        df['TOTAL'] = (
            df['PNACN'] * df['valor_pago_CR'] + df['PNAPN(4)'] * df['valor_pago_PE']
        ).fillna(0)

        saida = self.output_dir / '2a4'
        saida.mkdir(parents=True, exist_ok=True)
        caminho = saida / f'PNAES_valores_2a4_{ano}_ajustado.xlsx'
        df['metodo_calculo_total'] = 'PNACN*CR + PNAPN(4)*PE'
        salvar_excel(df, caminho)
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
            raise FileNotFoundError(entrada)

        df = pd.read_excel(entrada)
        df = _converter_numericas(df, ['PNAPN(5)', 'PNAFN(6-9)', 'valor_pago_PN', 'valor_pago_FN'])
        df['TOTAL'] = (
            df['PNAPN(5)'] * df['valor_pago_PN'] + df['PNAFN(6-9)'] * df['valor_pago_FN']
        ).fillna(0)

        saida = self.output_dir / '5a9'
        saida.mkdir(parents=True, exist_ok=True)
        caminho = saida / f'PNAES_valores_5a9_{ano}_ajustado.xlsx'
        df['metodo_calculo_total'] = 'PNAPN(5)*PN + PNAFN(6-9)*FN'
        salvar_excel(df, caminho)
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
    1. Filtra escolas estaduais (TP_DEPENDENCIA=2) e agrega MEC por código/UF
    2. Merge com dados PNAES via código IBGE
    3. Calcula percen_MAT_MED, percen_MAT_FUND, percen_MAT_FUND_AF
    4. Calcula e explicita os três componentes do total adolescente:
       - Ensino Médio municipal: valor_pago_prefeituras_EM
       - Ensino Médio estadual: valor_pago_secretarias_EM * percen_MAT_MED
       - Fundamental, anos finais: valor_pago_FN * percen_MAT_FUND_AF

    Os pesos do Censo seguem a implementação operacional de referência em
    _arquivo/v1-2.0/transform/pnaes.py. O repasse municipal de Ensino Médio
    entra diretamente, pois o FNDE já o identifica por município. Uma cópia
    mais antiga do notebook ``ajustes.ipynb`` calculava os pesos, mas os
    omitira de TOTAL_EF; ela não é a referência operacional deste pipeline.
    """

    def __init__(self):
        super().__init__(PNAES_VALORES_DIR, PNAES_FINAIS_DIR)
        self.mec_dir = MEC_MICRODADOS_DIR

    def transform(self, ano: int) -> None:
        entrada_pnaes = self.data_dir / 'Adolescentes' / f'PNAES_valores_Adolescentes_{ano}.xlsx'
        entrada_mec = localizar_microdados(ano)

        if not entrada_pnaes.exists():
            raise FileNotFoundError(entrada_pnaes)
        if not entrada_mec.exists():
            self._warn("Microdados MEC não encontrado: %s", entrada_mec)
            return

        self._info("Processando ano %s...", ano)

        # ------------------------------------------------------------------
        # 1. Carrega e agrega microdados MEC
        # ------------------------------------------------------------------
        # Junção pelo CÓDIGO do município, não pelo nome: há homônimos entre UFs
        # (p.ex. Bom Jesus existe em sete estados) e o merge por nome duplicava
        # linhas e atribuía matrículas da cidade errada.
        microdados = pd.read_csv(
            entrada_mec,
            encoding='latin-1',
            sep=';',
            on_bad_lines='error',
            usecols=[
                'SG_UF', 'CO_MUNICIPIO', 'TP_DEPENDENCIA',
                'QT_MAT_MED', 'QT_MAT_FUND', 'QT_MAT_FUND_AF',
            ],
        )

        cols_qt = ['QT_MAT_MED', 'QT_MAT_FUND', 'QT_MAT_FUND_AF']
        microdados['TP_DEPENDENCIA'] = pd.to_numeric(
            microdados['TP_DEPENDENCIA'], errors='coerce',
        )
        microdados = microdados[microdados['TP_DEPENDENCIA'].eq(2)].copy()
        for col in cols_qt:
            microdados[col] = pd.to_numeric(microdados[col], errors='coerce').fillna(0)
        # CO_MUNICIPIO tem 7 dígitos (com dígito verificador); codigo_IBGE tem 6.
        microdados['codigo_IBGE'] = (
            pd.to_numeric(microdados['CO_MUNICIPIO'], errors='coerce') // 10
        ).astype('Int64')
        microdados = microdados.dropna(subset=['codigo_IBGE'])

        por_cidade = (
            microdados
            .groupby('codigo_IBGE')
            .agg({'SG_UF': 'first', **{c: 'sum' for c in cols_qt}})
            .reset_index()
        )

        por_uf = microdados.groupby('SG_UF')[cols_qt].sum().reset_index()

        completo = por_cidade.merge(por_uf, on='SG_UF', suffixes=('_cidade', '_UF'))
        completo = completo[[
            'codigo_IBGE',
            'QT_MAT_MED_cidade', 'QT_MAT_FUND_cidade', 'QT_MAT_FUND_AF_cidade',
            'QT_MAT_MED_UF',     'QT_MAT_FUND_UF',     'QT_MAT_FUND_AF_UF',
        ]]

        # ------------------------------------------------------------------
        # 2. Merge com dados PNAES
        # ------------------------------------------------------------------
        pnaes = pd.read_excel(entrada_pnaes)
        pnaes['codigo_IBGE'] = pd.to_numeric(pnaes['codigo_IBGE'], errors='coerce').astype('Int64')
        antes = len(pnaes)
        df = pnaes.merge(completo, on='codigo_IBGE', how='left', validate='one_to_one')
        if len(df) != antes:
            self._error('merge com o MEC alterou o nº de linhas: %d -> %d', antes, len(df))
            return

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
        _colunas_total = [
            'valor_pago_prefeituras_EM',
            'valor_pago_secretarias_EM', 'percen_MAT_MED',
            'valor_pago_FN', 'percen_MAT_FUND_AF',
        ]
        faltantes = [c for c in _colunas_total if c not in df.columns]
        if faltantes:
            raise ValueError(f'colunas ausentes para TOTAL_EF: {faltantes}')

        # A ausência de matrícula estadual equivale a participação zero nas
        # parcelas que dependem do peso do Censo. Ela é preservada nas colunas
        # percen_MAT_* como NA para auditoria, mas não pode invalidar o repasse
        # municipal direto nem o outro componente válido da cidade.
        peso_med = pd.to_numeric(df['percen_MAT_MED'], errors='coerce').fillna(0)
        peso_fund_af = pd.to_numeric(
            df['percen_MAT_FUND_AF'], errors='coerce',
        ).fillna(0)
        valor_pref_em = pd.to_numeric(
            df['valor_pago_prefeituras_EM'], errors='coerce',
        ).fillna(0)
        valor_sec_em = pd.to_numeric(
            df['valor_pago_secretarias_EM'], errors='coerce',
        ).fillna(0)
        valor_fn = pd.to_numeric(df['valor_pago_FN'], errors='coerce').fillna(0)

        # O repasse da prefeitura já é identificado para o município no FNDE;
        # portanto, entra integralmente. Apenas os valores agregados por UF
        # são distribuídos pela razão município / UF das matrículas estaduais.
        df['componente_EM_prefeituras'] = valor_pref_em
        df['componente_EM_secretarias'] = valor_sec_em * peso_med
        df['componente_EF_anos_finais'] = valor_fn * peso_fund_af
        df['TOTAL_EF'] = (
            df['componente_EM_prefeituras']
            + df['componente_EM_secretarias']
            + df['componente_EF_anos_finais']
        )
        df['metodo_calculo_total'] = (
            'valor_pago_prefeituras_EM + '
            'valor_pago_secretarias_EM*percen_MAT_MED + '
            'valor_pago_FN*percen_MAT_FUND_AF'
        )
        df['filtro_matriculas_mec'] = (
            'TP_DEPENDENCIA=2 (rede estadual; pesos de EM estadual e EF anos finais)'
        )

        # ------------------------------------------------------------------
        # 5. Salva
        # ------------------------------------------------------------------
        saida = self.output_dir / 'Adolescentes'
        saida.mkdir(parents=True, exist_ok=True)
        caminho = saida / f'PNAES_valores_Adolescentes_{ano}_ajustado.xlsx'
        salvar_excel(df, caminho)
        self._info("Salvo: %s (%d municípios, %d colunas)", caminho.name, len(df), len(df.columns))
