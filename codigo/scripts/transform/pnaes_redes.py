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
from .io_seguro import salvar_excel
from scripts.config import (
    PNAES_REDES_DIR,
    PNAES_PERCEN_DIR,
    PNAES_VALORES_DIR,
    REFERENCIA_QUANT_DIR,
    localizar_redes,
)


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
    r'^(?:PREF(?:EITURA)?\.?\s*(?:(?:MUNIC(?:IPAL)?|MUN)\.?\s*)?(?:(?:DE|DA|DO)\s*)?'
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


def _chave_municipio(nome: str) -> str:
    """Chave só alfanumérica para pontuação/espaçamento não apagarem repasses."""
    return re.sub(r'[^A-Z0-9]', '', _normalizar_municipio(nome))


_KWS_SEC = (
    'SECRETARIA', 'SECR ', 'SEDUC', 'SEDU ', 'SEED ',
    'GOVERNO DO ESTADO', 'ESTADO DO',
)


def _is_secretaria(entidade: str) -> bool:
    """Retorna True se a entidade é uma secretaria estadual (não prefeitura municipal)."""
    u = str(entidade).upper()
    return any(kw in u for kw in _KWS_SEC)


# Prefixo de seis dígitos do código municipal -> UF. A fonte quant_idades traz
# código e nome, mas não a sigla; esta dimensão permite mapear todas as 5.570
# prefeituras antes de restringir aos municípios observados pelo SISVAN.
_CODIGO_UF_SIGLA = {
    11: 'RO', 12: 'AC', 13: 'AM', 14: 'RR', 15: 'PA', 16: 'AP', 17: 'TO',
    21: 'MA', 22: 'PI', 23: 'CE', 24: 'RN', 25: 'PB', 26: 'PE', 27: 'AL',
    28: 'SE', 29: 'BA', 31: 'MG', 32: 'ES', 33: 'RJ', 35: 'SP', 41: 'PR',
    42: 'SC', 43: 'RS', 50: 'MS', 51: 'MT', 52: 'GO', 53: 'DF',
}

# Grafias históricas/administrativas do FNDE que não coincidem com o nome IBGE.
# As chaves são (UF, _chave_municipio(ENTIDADE_RESP)); os códigos são os seis
# primeiros dígitos do código IBGE de sete dígitos. A lista é fechada e testada:
# qualquer nova entidade não mapeada interrompe o pipeline em vez de virar zero.
_EXCECOES_CODIGO = {
    ('BA', 'LAGEDODOTABOCAL'): 291905,
    ('CE', 'ITAPAJE'): 230630,
    ('ES', 'PINHEIRO'): 320410,
    ('MA', 'TREZIDELADOVALE'): 211223,
    ('MG', 'AMPARODASERRA'): 310250,
    ('MG', 'BRASOPOLIS'): 310890,
    ('MG', 'DONAEUZEBIA'): 312290,
    ('MG', 'PMDECARLOSCHAGAS'): 311370,
    ('MG', 'QUELUZITA'): 315380,
    ('MG', 'SAOTOMEDASLETRAS'): 316520,
    ('PA', 'SANTAISABELDOPARA'): 150650,
    ('PA', 'VIGIADENAZARE'): 150820,
    ('PE', 'IGUARACI'): 260690,
    ('PE', 'LAGOADOITAENGA'): 260850,
    ('PE', 'SAOCAETANO'): 261310,
    ('PR', 'BELAVISTADOCAROBA'): 410275,
    ('RJ', 'ARMACAODEBUZIOS'): 330023,
    ('RN', 'ASSU'): 240020,
    ('RN', 'BOASAUDE'): 240530,
    ('RN', 'CAMPOGRANDE'): 240130,
    ('RN', 'FERNANDOPEDROSA'): 240375,
    ('RR', 'SAOLUIZDOANAUA'): 140060,
    ('RS', 'CHIAPETA'): 430540,
    ('SC', 'PRESIDENTECASTELOBRANCO'): 421390,
    ('SC', 'SAOMIGUELDOESTE'): 421720,
    ('SP', 'ESTANCIACLIMATICADEMORUNGABA'): 353200,
    ('SP', 'ESTANCIA DESERRANEGRA'.replace(' ', '')): 355160,
    ('SP', 'ESTANCIATURISTICADEGUARATINGUETA'): 351840,
    ('SP', 'ESTANCIATURISTICADEHOLAMBRA'): 351905,
    ('SP', 'ESTANCIATURISTICADEPRESIDENTEEPITACEO'): 354130,
    ('SP', 'ESTANCIATURISTICORELIGIOSA'): 350250,
    ('SP', 'FLORINEA'): 351610,
    ('SP', 'SUDMENUCCI'): 355230,
    ('TO', 'COUTODEMAGALHAES'): 170600,
    ('TO', 'SAOVALERIODANATIVIDADE'): 172049,
}


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
        self._municipios = self._carregar_dimensao_municipios()

    @staticmethod
    def _carregar_dimensao_municipios() -> pd.DataFrame:
        caminho = REFERENCIA_QUANT_DIR / 'quant_idades.xlsx'
        q = pd.read_excel(caminho, usecols=['Município'])
        q['codigo_IBGE'] = pd.to_numeric(
            q['Município'].astype(str).str.extract(r'^(\d{6})')[0],
            errors='coerce',
        ).astype('Int64')
        q['municipio_dim'] = q['Município'].astype(str).str.replace(
            r'^\d{6}\s+', '', regex=True,
        )
        q['UF'] = (q['codigo_IBGE'] // 10_000).map(_CODIGO_UF_SIGLA)
        q['_chave_municipio'] = q['municipio_dim'].map(_chave_municipio)
        q = q.dropna(subset=['codigo_IBGE', 'UF'])
        if q.duplicated(['UF', '_chave_municipio']).any():
            raise ValueError('dimensão municipal tem chaves normalizadas duplicadas')
        if len(q) != 5570:
            raise ValueError(f'dimensão municipal incompleta: {len(q)} de 5570')
        return q[['UF', '_chave_municipio', 'codigo_IBGE', 'municipio_dim']]

    def _mapear_prefeituras(
        self,
        redes: pd.DataFrame,
        acoes: set[str],
        ano: int,
    ) -> pd.DataFrame:
        """Converte entidade FNDE em código IBGE e falha se houver perda."""
        pref = redes[~redes['_is_sec'] & redes['ACAO'].isin(acoes)].copy()
        pref['_chave_municipio'] = pref['ENTIDADE_RESP'].map(_chave_municipio)
        pref = pref.merge(
            self._municipios[['UF', '_chave_municipio', 'codigo_IBGE']],
            on=['UF', '_chave_municipio'],
            how='left',
            validate='many_to_one',
        )
        faltantes = pref['codigo_IBGE'].isna()
        if faltantes.any():
            pref.loc[faltantes, 'codigo_IBGE'] = [
                _EXCECOES_CODIGO.get((uf, chave))
                for uf, chave in zip(
                    pref.loc[faltantes, 'UF'],
                    pref.loc[faltantes, '_chave_municipio'],
                )
            ]
        ainda = pref[pref['codigo_IBGE'].isna() & pref['VALOR'].ne(0)]
        if not ainda.empty:
            resumo = (
                ainda.groupby(['UF', 'ENTIDADE_RESP'])['VALOR'].sum()
                .sort_values(ascending=False).head(10)
            )
            raise ValueError(
                f'{ano}: {ainda.ENTIDADE_RESP.nunique()} entidades FNDE sem código IBGE:\n'
                + resumo.to_string()
            )
        pref['codigo_IBGE'] = pref['codigo_IBGE'].astype('Int64')
        return pref

    def transform(self, ano: int) -> None:
        if ano == 0:
            # Os arquivos FNDE ficam diretamente em ``redes/`` (e, em alguns
            # acervos, em ``redes/{ano}/``), portanto a descoberta genérica da
            # classe-base — baseada apenas em subdiretórios anuais — não serve
            # para esta etapa. Usa o localizador específico e só processa anos
            # que têm fonte efetivamente disponível.
            for a in range(2015, 2026):
                if localizar_redes(a):
                    self._transform_ano(a)
        else:
            self._transform_ano(ano)

    # ------------------------------------------------------------------

    def _transform_ano(self, ano: int) -> None:
        redes = self._carregar_redes(ano)
        if redes is None:
            raise FileNotFoundError(f'Arquivo Redes FNDE válido não encontrado para {ano}')
        for faixa in ['2a4', '5a9', 'Adolescentes']:
            self._processar_faixa(redes, faixa, ano)

    def _carregar_redes(self, ano: int) -> pd.DataFrame | None:
        """Localiza, carrega e normaliza o arquivo Redes do ano."""
        candidatos = localizar_redes(ano)
        if not candidatos:
            self._warn("Arquivo Redes não encontrado para %d", ano)
            return None
        if len(candidatos) > 1:
            tamanhos = {p.stat().st_size for p in candidatos}
            nivel = self._warn if len(tamanhos) > 1 else self._info
            nivel("%d arquivos Redes para %d (%s) — usando %s", len(candidatos), ano,
                  "TAMANHOS DIFERENTES" if len(tamanhos) > 1 else "idênticos",
                  candidatos[0].name)

        path = candidatos[0]
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
        tipo_valor = 'previsto' if 'PREVISTO' in str(valor_col).upper() else 'pago'
        if tipo_valor == 'previsto':
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
        df['tipo_valor_fnde'] = tipo_valor

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
            raise FileNotFoundError(percen_path)

        percen   = pd.read_excel(percen_path)
        acao_map = self._ACAO_MAP[faixa]

        # Pivot por CÓDIGO IBGE. O nome é usado apenas para resolver a dimensão
        # oficial; pontuação, grafia histórica ou prefixo administrativo não
        # podem mais transformar um repasse existente em zero.
        pref_redes = self._mapear_prefeituras(redes, set(acao_map), ano)
        pivot = (
            pref_redes
            .groupby(['codigo_IBGE', 'ACAO'])['VALOR']
            .sum()
            .unstack(fill_value=0)
            .reset_index()
        )
        pivot.rename(columns=acao_map, inplace=True)
        for col in acao_map.values():
            if col not in pivot.columns:
                pivot[col] = 0.0

        percen['codigo_IBGE'] = pd.to_numeric(
            percen['codigo_IBGE'], errors='coerce',
        ).astype('Int64')
        resultado = percen.merge(
            pivot[['codigo_IBGE'] + list(acao_map.values())],
            on='codigo_IBGE',
            how='left',
            validate='one_to_one',
        )
        for col in acao_map.values():
            resultado[col] = resultado[col].fillna(0)

        if faixa == 'Adolescentes':
            resultado = self._adicionar_pnamn(redes, resultado, ano)

        resultado['tipo_valor_fnde'] = redes['tipo_valor_fnde'].iloc[0]

        out_dir = self.output_dir / faixa
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f'PNAES_valores_{faixa}_{ano}.xlsx'
        salvar_excel(resultado, out_path)
        self._info("[%s %d] Salvo: %s (%d linhas)", faixa, ano, out_path.name, len(resultado))

    def _adicionar_pnamn(
        self,
        redes: pd.DataFrame,
        resultado: pd.DataFrame,
        ano: int,
    ) -> pd.DataFrame:
        """Adiciona valor_pago_secretarias_EM e valor_pago_prefeituras_EM (PNAMN/PNAMI/PN+MN)."""
        _ACOES_EM = {'PNAMN', 'PNAMI', 'PN+MN'}
        pnamn = redes[redes['ACAO'].isin(_ACOES_EM)].copy()

        sec = (
            pnamn[pnamn['_is_sec']]
            .groupby('UF')['VALOR'].sum().reset_index()
            .rename(columns={'VALOR': 'valor_pago_secretarias_EM'})
        )
        pref_cod = self._mapear_prefeituras(pnamn, _ACOES_EM, ano)
        pref = (
            pref_cod
            .groupby('codigo_IBGE')['VALOR'].sum().reset_index()
            .rename(columns={'VALOR': 'valor_pago_prefeituras_EM'})
        )

        resultado = resultado.merge(sec,  on='UF',               how='left')
        resultado = resultado.merge(pref, on='codigo_IBGE', how='left', validate='one_to_one')
        resultado['valor_pago_secretarias_EM'] = resultado['valor_pago_secretarias_EM'].fillna(0)
        resultado['valor_pago_prefeituras_EM'] = resultado['valor_pago_prefeituras_EM'].fillna(0)
        return resultado
