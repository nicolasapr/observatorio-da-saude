# transform/series_mensais.py
"""
SeriesMensaisTransformer — agrega sumários mensais em séries temporais.

Entrada: dados/sisvan/mensais/{ano}/{MES}/sumario_habitos_{faixa}.xlsx
Saídas:
    dados/sisvan/series/serie_mensal_{faixa}.xlsx              (nacional)
    dados/sisvan/series/serie_mensal_{faixa}_por_regiao.xlsx   (por região)
    dados/sisvan/series/serie_mensal_{faixa}_por_uf.xlsx       (por UF)

Percentuais calculados como soma(total_que_*) / soma(total_all_*)
— nunca média de percentuais.

Ignora o argumento --ano: sempre processa todos os anos disponíveis.
"""
import datetime
import unicodedata

import pandas as pd

from .base import BaseTransformer
from .io_seguro import salvar_excel
from .normalizacao import normalizar_df
from scripts.config import SISVAN_MENSAIS_DIR, SISVAN_SERIES_DIR

MESES_ORDEM = {
    'JANEIRO': 1, 'FEVEREIRO': 2, 'MARÇO': 3, 'ABRIL': 4,
    'MAIO': 5, 'JUNHO': 6, 'JULHO': 7, 'AGOSTO': 8,
    'SETEMBRO': 9, 'OUTUBRO': 10, 'NOVEMBRO': 11, 'DEZEMBRO': 12,
}

FAIXAS_SLUGS = [
    'Crianças_de_2_a_4_anos',
    'Crianças_de_5_a_9_anos',
    'Adolescentes',
]

def _somar_habitos(df_grupo: pd.DataFrame, cols_que: list[str]) -> dict:
    """Soma total_que_* e total_all_*, recalcula percentual para um grupo."""
    resultado: dict = {}
    for col_que in cols_que:
        sufixo = col_que[len('total_que_'):]
        col_all = f'total_all_{sufixo}'

        soma_que = pd.to_numeric(df_grupo[col_que], errors='coerce').sum()
        soma_all = pd.to_numeric(
            df_grupo[col_all] if col_all in df_grupo.columns else pd.Series(dtype=float),
            errors='coerce',
        ).sum()

        resultado[f'total_que_{sufixo}'] = int(soma_que) if pd.notna(soma_que) else 0
        resultado[f'total_all_{sufixo}'] = int(soma_all) if pd.notna(soma_all) else 0
        resultado[f'percentual_que_{sufixo}'] = (
            round(float(soma_que) / float(soma_all), 4) if soma_all > 0 else None
        )
    return resultado


class SeriesMensaisTransformer(BaseTransformer):
    """
    Consolida sumários mensais em séries temporais com três níveis
    de agregação: nacional, por região e por UF.

    O argumento `ano` é ignorado — sempre processa todos os anos.
    """

    def __init__(self, faixas: list[str] | None = None):
        # faixas=None processa as três; passar uma lista permite rodar em partes
        self.faixas = faixas
        super().__init__(SISVAN_SERIES_DIR)

    def transform(self, ano: int) -> None:  # noqa: ARG002
        SISVAN_SERIES_DIR.mkdir(parents=True, exist_ok=True)
        for faixa_slug in (self.faixas or FAIXAS_SLUGS):
            self._processar_faixa(faixa_slug)

    # ------------------------------------------------------------------

    def _processar_faixa(self, faixa_slug: str) -> None:
        reg_nacional: list[dict] = []
        reg_regiao: list[dict] = []
        reg_uf: list[dict] = []

        anos_dirs = sorted(
            d for d in SISVAN_MENSAIS_DIR.iterdir()
            if d.is_dir() and d.name.isdigit()
        )

        for pasta_ano in anos_dirs:
            ano = int(pasta_ano.name)
            meses_dirs = sorted(
                pasta_ano.iterdir(),
                key=lambda p: MESES_ORDEM.get(p.name.upper(), 99),
            )
            for pasta_mes in meses_dirs:
                if not pasta_mes.is_dir():
                    continue
                # macOS grava nomes de pasta em NFD ('MARC'+cedilha combinante),
                # enquanto a constante do código está em NFC. Sem normalizar,
                # MARÇO não casa e o mês é silenciosamente descartado.
                mes_nome = unicodedata.normalize('NFC', pasta_mes.name).upper()
                mes_num = MESES_ORDEM.get(mes_nome)
                if mes_num is None:
                    continue

                arquivo = pasta_mes / f'sumario_habitos_{faixa_slug}.xlsx'
                if not arquivo.exists():
                    continue

                try:
                    df = normalizar_df(pd.read_excel(arquivo))

                    # Nacional
                    registro = self._agregar_nacional(df, ano, mes_num)
                    if registro:
                        n = registro.pop('_n', 0)
                        reg_nacional.append(registro)
                        self._info(
                            '%s | %d-%02d — %d municípios',
                            faixa_slug, ano, mes_num, n,
                        )

                    # Por região
                    reg_regiao.extend(
                        self._agregar_por_regiao(df, ano, mes_num)
                    )

                    # Por UF
                    reg_uf.extend(
                        self._agregar_por_uf(df, ano, mes_num)
                    )

                except Exception as e:
                    self._error(
                        'Erro em %s/%s/%s: %s',
                        pasta_ano.name, pasta_mes.name, faixa_slug, e,
                    )

        if not reg_nacional:
            self._warn('Nenhum dado encontrado para %s', faixa_slug)
            return

        # Salvar nacional
        self._salvar(reg_nacional, f'serie_mensal_{faixa_slug}.xlsx', ['ano', 'mes'])

        # Salvar por região
        if reg_regiao:
            self._salvar(
                reg_regiao,
                f'serie_mensal_{faixa_slug}_por_regiao.xlsx',
                ['ano', 'mes', 'regiao'],
            )

        # Salvar por UF
        if reg_uf:
            self._salvar(
                reg_uf,
                f'serie_mensal_{faixa_slug}_por_uf.xlsx',
                ['ano', 'mes', 'UF'],
            )

    def _salvar(
        self, registros: list[dict], nome_arquivo: str, sort_cols: list[str],
    ) -> None:
        df_serie = (
            pd.DataFrame(registros)
            .sort_values(sort_cols)
            .reset_index(drop=True)
        )
        caminho = SISVAN_SERIES_DIR / nome_arquivo
        salvar_excel(df_serie, caminho)
        self._info('Salvo: %s (%d linhas)', caminho.name, len(df_serie))

    # ── Agregações ────────────────────────────────────────────────────

    def _agregar_nacional(
        self, df: pd.DataFrame, ano: int, mes: int,
    ) -> dict | None:
        cols_que = [c for c in df.columns if c.startswith('total_que_')]
        if not cols_que:
            return None

        registro = _somar_habitos(df, cols_que)
        registro.update({
            'ano': ano,
            'mes': mes,
            'data': datetime.date(ano, mes, 1),
            '_n': len(df),
        })
        return registro

    def _agregar_por_regiao(
        self, df: pd.DataFrame, ano: int, mes: int,
    ) -> list[dict]:
        cols_que = [c for c in df.columns if c.startswith('total_que_')]
        if not cols_que or 'regiao' not in df.columns:
            return []

        resultados: list[dict] = []
        for regiao, grupo in df.groupby('regiao'):
            registro = _somar_habitos(grupo, cols_que)
            registro.update({
                'ano': ano,
                'mes': mes,
                'data': datetime.date(ano, mes, 1),
                'regiao': regiao,
            })
            resultados.append(registro)
        return resultados

    def _agregar_por_uf(
        self, df: pd.DataFrame, ano: int, mes: int,
    ) -> list[dict]:
        cols_que = [c for c in df.columns if c.startswith('total_que_')]
        if not cols_que or 'UF' not in df.columns:
            return []

        resultados: list[dict] = []
        group_cols = ['codigo_UF', 'UF'] if 'codigo_UF' in df.columns else ['UF']
        for keys, grupo in df.groupby(group_cols):
            registro = _somar_habitos(grupo, cols_que)
            if isinstance(keys, tuple):
                registro['codigo_UF'] = keys[0]
                registro['UF'] = keys[1]
            else:
                registro['UF'] = keys
            registro.update({
                'ano': ano,
                'mes': mes,
                'data': datetime.date(ano, mes, 1),
            })
            resultados.append(registro)
        return resultados
