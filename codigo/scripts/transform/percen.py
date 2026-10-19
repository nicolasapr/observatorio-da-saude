"""
PercenTransformer — junta o sumário anual do SISVAN às razões de rateio etário.

Substitui um passo que antes era feito à mão. A versão manual unia as tabelas por
NOME de município, o que duplicava linhas em homônimos e atribuía o rateio errado.
Aqui a junção é pelo código IBGE de 6 dígitos, um-para-um.

Entrada: dados/sisvan/anuais/{ano}/sumario_anual_habitos_{faixa}.xlsx
         dados/referencia/quant_idades/quant_idades.xlsx
Saída:   dados/pnaes/percen/{faixa}/PNAES_Percen_{faixa}_{ano}.xlsx
"""
import pandas as pd

from .base import BaseTransformer
from .io_seguro import salvar_excel
from scripts.config import SISVAN_ANUAIS_DIR, PNAES_PERCEN_DIR, REFERENCIA_QUANT_DIR

# faixa -> (slug do sumário anual, colunas de rateio)
_FAIXAS = {
    '2a4':          ('Crianças_de_2_a_4_anos', ['PNACN', 'PNAPN(4)']),
    '5a9':          ('Crianças_de_5_a_9_anos', ['PNAPN(5)', 'PNAFN(6-9)']),
    'Adolescentes': ('Adolescentes',           ['PNAFN(10-15)']),
}


class PercenTransformer(BaseTransformer):
    def __init__(self):
        super().__init__(SISVAN_ANUAIS_DIR, PNAES_PERCEN_DIR)
        self.quant = REFERENCIA_QUANT_DIR / 'quant_idades.xlsx'

    def _rateio(self) -> pd.DataFrame:
        q = pd.read_excel(self.quant)
        q['codigo_IBGE'] = pd.to_numeric(
            q['Município'].astype(str).str.extract(r'^(\d{6})')[0], errors='coerce'
        )
        q = q.dropna(subset=['codigo_IBGE'])
        q['codigo_IBGE'] = q['codigo_IBGE'].astype(int)
        cols = ['codigo_IBGE'] + [c for _, (_, r) in _FAIXAS.items() for c in r]
        q = q[list(dict.fromkeys(cols))]
        dup = int(q.codigo_IBGE.duplicated().sum())
        if dup:
            self._warn('quant_idades tem %d códigos IBGE repetidos — mantendo o primeiro', dup)
            q = q.drop_duplicates('codigo_IBGE', keep='first')
        return q

    def transform(self, ano: int) -> None:
        anos = self._anos_disponiveis() if ano == 0 else [ano]
        rateio = self._rateio()
        for a in anos:
            for faixa, (slug, cols) in _FAIXAS.items():
                entrada = self.data_dir / str(a) / f'sumario_anual_habitos_{slug}.xlsx'
                if not entrada.exists():
                    raise FileNotFoundError(entrada)
                df = pd.read_excel(entrada)
                antes = len(df)
                df['codigo_IBGE'] = pd.to_numeric(df['codigo_IBGE'], errors='coerce').astype('Int64')
                out = df.merge(rateio[['codigo_IBGE'] + cols], on='codigo_IBGE',
                               how='left', validate='one_to_one')
                if len(out) != antes:
                    self._error('[%s %d] merge alterou o nº de linhas: %d -> %d',
                                faixa, a, antes, len(out)); continue
                falta = int(out[cols[0]].isna().sum())
                dest = self.output_dir / faixa
                dest.mkdir(parents=True, exist_ok=True)
                salvar_excel(out, dest / f'PNAES_Percen_{faixa}_{a}.xlsx')
                self._info('[%s %d] %d municípios, %d sem rateio', faixa, a, len(out), falta)
