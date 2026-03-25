# transform/pnaes_redes.py
"""
PNAESRedesTransformer — lê os arquivos brutos Redes<ano>.xlsx (FNDE) e gera
PNAES_valores_{faixa}_{ano}.xlsx fazendo merge com PNAES_Percen_{faixa}/.

Entrada redes:  dados/pnaes/redes/{ano}/*EDES*.xlsx
Entrada percen: dados/pnaes/percen/{faixa}/PNAES_Percen_{faixa}_{ano}.xlsx
Saída:          dados/pnaes/valores/{faixa}/PNAES_valores_{faixa}_{ano}.xlsx

Variações tratadas automaticamente:
  - 2015–2022: 4 colunas, VALOR_PAGO em formato BR string ("54.000,00")
  - 2015–2018: ação PN+FN legada → mapeada para PNAFN
  - 2023:      5 colunas (+ QTDE_ALUNO), VALOR_PAGO numérico
  - 2024+:     5 colunas, VALOR_PREVISTO em formato BR string (fallback com aviso)
"""
from __future__ import annotations

import re
import unicodedata

import pandas as pd

from .base import BaseTransformer
from scripts.config import PNAES_REDES_DIR, PNAES_PERCEN_DIR, PNAES_VALORES_DIR


# ---------------------------------------------------------------------------
# Helpers de parsing
# ---------------------------------------------------------------------------

def _parse_valor(v) -> float:
    """Converte string BR '54.000,00' ou numérico para float."""
    if pd.isna(v):
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace('.', '').replace(',', '.')
    try:
        return float(s)
    except ValueError:
        return 0.0


_PREFIXOS_PREF = re.compile(
    r'^(?:PREF(?:EITURA)?\.?\s*(?:MUN(?:ICIPAL)?\.?\s*)?(?:DE\s*)?'
    r'|MUNICIPIO\s+DE\s+'
    r'|MUNICIPIO\s+)',
    flags=re.IGNORECASE,
)


def _normalizar_municipio(nome: str) -> str:
    """Remove prefixo de prefeitura e normaliza: maiúsculas + sem acento."""
    if pd.isna(nome):
        return ''
    s = _PREFIXOS_PREF.sub('', str(nome).strip()).strip()
    s = unicodedata.normalize('NFKD', s.upper()).encode('ascii', errors='ignore').decode('utf-8')
    return s.strip()


_KWS_SEC = ('SECRETARIA', 'SEDUC', 'SEDU ', 'SEED ', 'GOVERNO DO ESTADO', 'ESTADO DO')


def _is_secretaria(entidade: str) -> bool:
    """Retorna True se a entidade é uma secretaria estadual (não prefeitura municipal)."""
    u = str(entidade).upper()
    return any(kw in u for kw in _KWS_SEC)


# ---------------------------------------------------------------------------
# Transformer principal
# ---------------------------------------------------------------------------

class PNAESRedesTransformer(BaseTransformer):
    """
    Lê Redes<ano>.xlsx (FNDE) e produz:
        dados/pnaes/valores/2a4/PNAES_valores_2a4_{ano}.xlsx
        dados/pnaes/valores/5a9/PNAES_valores_5a9_{ano}.xlsx
        dados/pnaes/valores/Adolescentes/PNAES_valores_Adolescentes_{ano}.xlsx

    Uso:
        t = PNAESRedesTransformer()
        t.transform(2023)   # ano específico
        t.transform(0)      # todos os anos disponíveis
    """

    # Mapeamento: faixa → {ACAO: nome_coluna_destino}
    _ACAO_MAP: dict[str, dict[str, str]] = {
        '2a4':          {'PNACN': 'valor_pago_CR', 'PNAPN': 'valor_pago_PE'},
        '5a9':          {'PNAPN': 'valor_pago_PN', 'PNAFN': 'valor_pago_FN'},
        'Adolescentes': {'PNAFN': 'valor_pago_FN'},
    }

    def __init__(self):
        # data_dir = redes files; output_dir = valores output
        super().__init__(PNAES_REDES_DIR, PNAES_VALORES_DIR)
        self.percen_dir = PNAES_PERCEN_DIR

    def transform(self, ano: int) -> None:
        if ano == 0:
            for a in self._anos_disponiveis():
                self._transform_ano(a)
        else:
            self._transform_ano(ano)

    # ------------------------------------------------------------------

    def _transform_ano(self, ano: int) -> None:
        redes = self._carregar_redes(ano)
        if redes is None:
            return
        for faixa in ['2a4', '5a9', 'Adolescentes']:
            self._processar_faixa(redes, faixa, ano)

    def _carregar_redes(self, ano: int) -> pd.DataFrame | None:
        """Localiza, carrega e normaliza o arquivo Redes do ano."""
        pasta = self.data_dir / str(ano)
        matches = (
            [p for p in pasta.glob('*EDES*') if not p.name.startswith('.~lock.')]
            if pasta.exists() else []
        )
        if not matches:
            self._warn("Arquivo Redes não encontrado para %d", ano)
            return None

        path = matches[0]
        self._info("Carregando %s", path.name)

        # Detecta linha de header
        raw = pd.read_excel(path, header=None, nrows=10)
        header_row = None
        for i, row in raw.iterrows():
            vals = {str(v).strip().upper() for v in row if pd.notna(v)}
            if 'UF' in vals and 'ACAO' in vals:
                header_row = i
                break
        if header_row is None:
            self._error("Header não encontrado em %s", path.name)
            return None

        df = pd.read_excel(path, header=header_row)

        # Detecta coluna de valor: prefere VALOR_PAGO (executado)
        valor_col = next(
            (c for c in df.columns if str(c).strip().upper() == 'VALOR_PAGO'), None
        ) or next(
            (c for c in df.columns if 'VALOR' in str(c).upper()), None
        )
        if valor_col is None:
            self._error("Coluna VALOR não encontrada em %s", path.name)
            return None
        if 'PREVISTO' in str(valor_col).upper():
            self._warn(
                "%d: usando VALOR_PREVISTO (dado orçado) — VALOR_PAGO não disponível. "
                "Os valores podem diferir do repasse efetivamente executado.",
                ano,
            )

        df = df[['UF', 'ENTIDADE_RESP', 'ACAO', valor_col]].copy()
        df.columns = ['UF', 'ENTIDADE_RESP', 'ACAO', 'VALOR']
        df = df.dropna(subset=['ACAO', 'ENTIDADE_RESP'])
        df['ACAO']  = df['ACAO'].astype(str).str.strip().str.upper()
        df['UF']    = df['UF'].astype(str).str.strip().str.upper()
        df['VALOR'] = df['VALOR'].apply(_parse_valor)

        # PN+FN (programa combinado legado, 2015–2018) → PNAFN
        df['ACAO'] = df['ACAO'].replace('PN+FN', 'PNAFN')

        df['_is_sec']   = df['ENTIDADE_RESP'].apply(_is_secretaria)
        df['municipio'] = df.apply(
            lambda r: '' if r['_is_sec'] else _normalizar_municipio(r['ENTIDADE_RESP']),
            axis=1,
        )

        return df

    def _processar_faixa(self, redes: pd.DataFrame, faixa: str, ano: int) -> None:
        percen_path = self.percen_dir / faixa / f'PNAES_Percen_{faixa}_{ano}.xlsx'
        if not percen_path.exists():
            self._warn("[%s %d] Percen não encontrado: %s", faixa, ano, percen_path)
            return

        percen   = pd.read_excel(percen_path)
        acao_map = self._ACAO_MAP[faixa]

        # Pivot: prefeituras → (UF, municipio, ACAO) → valor
        pref_redes = redes[~redes['_is_sec'] & redes['ACAO'].isin(acao_map.keys())].copy()
        pivot = (
            pref_redes
            .groupby(['UF', 'municipio', 'ACAO'])['VALOR']
            .sum()
            .unstack(fill_value=0)
            .reset_index()
        )
        pivot.rename(columns=acao_map, inplace=True)
        for col in acao_map.values():
            if col not in pivot.columns:
                pivot[col] = 0.0

        resultado = percen.merge(
            pivot[['UF', 'municipio'] + list(acao_map.values())],
            on=['UF', 'municipio'],
            how='left',
        )
        for col in acao_map.values():
            resultado[col] = resultado[col].fillna(0)

        if faixa == 'Adolescentes':
            resultado = self._adicionar_pnamn(redes, resultado)

        out_dir = self.output_dir / faixa
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f'PNAES_valores_{faixa}_{ano}.xlsx'
        resultado.to_excel(out_path, index=False)
        self._info("[%s %d] Salvo: %s (%d linhas)", faixa, ano, out_path.name, len(resultado))

    def _adicionar_pnamn(self, redes: pd.DataFrame, resultado: pd.DataFrame) -> pd.DataFrame:
        """Adiciona valor_pago_secretarias_EM e valor_pago_prefeituras_EM (PNAMN/PNAMI/PN+MN)."""
        _ACOES_EM = {'PNAMN', 'PNAMI', 'PN+MN'}
        pnamn = redes[redes['ACAO'].isin(_ACOES_EM)].copy()

        sec = (
            pnamn[pnamn['_is_sec']]
            .groupby('UF')['VALOR'].sum().reset_index()
            .rename(columns={'VALOR': 'valor_pago_secretarias_EM'})
        )
        pref = (
            pnamn[~pnamn['_is_sec']]
            .groupby(['UF', 'municipio'])['VALOR'].sum().reset_index()
            .rename(columns={'VALOR': 'valor_pago_prefeituras_EM'})
        )

        resultado = resultado.merge(sec,  on='UF',               how='left')
        resultado = resultado.merge(pref, on=['UF', 'municipio'], how='left')
        resultado['valor_pago_secretarias_EM'] = resultado['valor_pago_secretarias_EM'].fillna(0)
        resultado['valor_pago_prefeituras_EM'] = resultado['valor_pago_prefeituras_EM'].fillna(0)
        return resultado
