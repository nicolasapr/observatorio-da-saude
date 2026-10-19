# transform/criar_sumarios.py
"""
CriarSumariosTransformer — une os arquivos de hábito de cada mês/faixa
em sumário mensal: sumario_habitos_{faixa}.xlsx

Entrada: dados/sisvan/mensais/{ano}/{mes}/{faixa}/{habito}.xls
Saída:   dados/sisvan/mensais/{ano}/{mes}/sumario_habitos_{faixa}.xlsx

Segurança: a pasta organizada preserva apenas parte dos relatórios brutos.
Por isso, esta etapa só regrava um sumário quando encontra e valida os dez
marcadores de uma mesma combinação ano/mês/faixa. Com menos arquivos, mantém
o sumário existente intacto; para incorporar um relatório isolado, use
``aplicar_recuperado.py`` ou ``rotear_downloads.py``.
"""
import pandas as pd
from pathlib import Path

from .base import BaseTransformer
from .io_seguro import salvar_excel
from .normalizacao import normalizar_col
from scripts.config import SISVAN_MENSAIS_DIR, COLUNAS_CADASTRAIS
from scripts.extract.sisvan import HABITOS, validar_relatorio

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
            raise FileNotFoundError(pasta_ano)

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

        # O nome no disco pode ser truncado ou sanitizado, portanto a identidade
        # do marcador vem do cabeçalho validado do próprio relatório.
        relatorios: dict[str, tuple[Path, pd.DataFrame]] = {}
        erros: list[str] = []
        for arquivo in arquivos:
            try:
                meta, df = self._ler_arquivo(arquivo)
                marcador = meta['habito']
                if marcador in relatorios:
                    erros.append(
                        f'{marcador!r} aparece em {relatorios[marcador][0].name!r} '
                        f'e {arquivo.name!r}'
                    )
                else:
                    relatorios[marcador] = (arquivo, df)
            except Exception as e:
                erros.append(f'{arquivo.name}: {e}')

        esperados = set(HABITOS)
        encontrados = set(relatorios)
        faltantes = [h for h in HABITOS if h not in encontrados]
        inesperados = sorted(encontrados - esperados)
        faixa_slug = faixa_nome.replace(' ', '_')
        caminho = pasta_mes / f'sumario_habitos_{faixa_slug}.xlsx'

        # Não produzir um artefato parcial. O processamento anterior gerava um
        # .xlsx com uma ou poucas colunas e substituía silenciosamente o sumário
        # completo que já existia. Esse era o principal risco do acervo bruto
        # parcial e agora vira uma interrupção segura, sem escrita alguma.
        if erros or faltantes or inesperados:
            detalhe = []
            if erros:
                detalhe.append(f'{len(erros)} arquivo(s) inválido(s)/duplicado(s)')
            if faltantes:
                detalhe.append(f'{len(faltantes)} marcador(es) ausente(s)')
            if inesperados:
                detalhe.append(f'{len(inesperados)} marcador(es) não reconhecido(s)')
            self._warn(
                'Sumário preservado em %s: conjunto bruto incompleto (%s).',
                caminho.name, '; '.join(detalhe),
            )
            for erro in erros[:3]:
                self._warn('  %s', erro)
            if not caminho.exists():
                raise ValueError(f'Brutos incompletos e nenhum sumário prévio para {caminho}')
            return

        df_acumulado = None
        # A ordem canônica torna a saída determinística e mantém as colunas
        # alinhadas com as demais etapas do pipeline.
        for marcador in HABITOS:
            df = relatorios[marcador][1]
            if df_acumulado is None:
                df_acumulado = df.copy()
                continue

            # A chave de uma cidade é o código IBGE. Nome, UF e região são
            # atributos descritivos e não podem participar da junção: uma
            # variação de grafia entre dois relatórios do mesmo mês criaria
            # duas linhas para a mesma cidade. Neste ponto, uma divergência de
            # cadastro é tratada como erro da fonte, não "corrigida" por uma
            # escolha silenciosa; assim o sumário completo já existente fica
            # preservado para inspeção.
            cadastro_novo = df[COLUNAS_CADASTRAIS]
            comum = df_acumulado[COLUNAS_CADASTRAIS].merge(
                cadastro_novo,
                on='codigo_IBGE', how='inner', suffixes=('_atual', '_novo'),
                validate='one_to_one',
            )
            conflitos = []
            for coluna in (c for c in COLUNAS_CADASTRAIS if c != 'codigo_IBGE'):
                atual = comum[f'{coluna}_atual'].fillna('').astype(str).str.strip()
                novo = comum[f'{coluna}_novo'].fillna('').astype(str).str.strip()
                if (atual.ne('') & novo.ne('') & atual.ne(novo)).any():
                    conflitos.append(coluna)
            if conflitos:
                raise ValueError(
                    f'{marcador!r}: cadastro divergente para código(s) IBGE '
                    f'nas colunas {", ".join(conflitos)}'
                )

            # Uma cidade que só apareça neste marcador é mantida. As colunas
            # dos marcadores anteriores ficam nulas, o que preserva a ausência
            # real sem inventar zero.
            novos = df.loc[~df['codigo_IBGE'].isin(df_acumulado['codigo_IBGE']),
                            COLUNAS_CADASTRAIS]
            if not novos.empty:
                df_acumulado = pd.concat([df_acumulado, novos], ignore_index=True)

            for coluna in (c for c in df.columns if c not in COLUNAS_CADASTRAIS):
                valores = df.set_index('codigo_IBGE')[coluna]
                df_acumulado[coluna] = df_acumulado['codigo_IBGE'].map(valores)

        salvar_excel(df_acumulado, caminho)
        self._info('Salvo: %s (10 marcadores validados)', caminho.name)

    def _ler_arquivo(self, arquivo: Path) -> tuple[dict, pd.DataFrame]:
        # A combinação solicitada é inferida do caminho, mas validada contra o
        # conteúdo. Foi exatamente a ausência desta checagem que permitiu usar
        # um relatório de adolescentes em Crianças de 5 a 9 anos/2021-02.
        ano = int(arquivo.parents[2].name)
        mes = arquivo.parents[1].name
        fase = arquivo.parent.name.replace('_', ' ')
        habito_arquivo = arquivo.stem
        meta = validar_relatorio(
            arquivo.read_bytes(), ano=ano, mes=mes, fase=fase, habito=habito_arquivo,
        )
        # O nome do arquivo é limitado pelo sistema e pode vir em NFD no macOS.
        # O conteúdo validado entrega o marcador completo e canônico; é ele que
        # define o nome das colunas que seguirão para os agregados.
        habito = meta['habito']

        # O SISVAN entrega números em notação BR: '.' separa milhar e ',' separa
        # decimal. Sem informar isso, o pandas lê '1.022' como 1,022 e todo
        # município com mil ou mais respostas fica mil vezes menor — o que também
        # produz total_que > total_all. Verificado em 21/08/2026 sobre o relatório
        # de ago/2022: 5.028 respostas válidas perdidas em um único arquivo.
        if arquivo.suffix in ('.xlsx', '.xls'):
            tabelas = pd.read_html(str(arquivo), thousands='.', decimal=',')
            df = tabelas[0]
        else:
            df = pd.read_csv(arquivo, encoding='latin1', sep=None, engine='python',
                             thousands='.', decimal=',')

        if len(df.columns) < 8:
            raise ValueError(f'{len(df.columns)} colunas; esperado ao menos 8')

        # pandas 3 interpreta uma célula HTML vazia à direita como nona coluna;
        # pandas 2.3 retorna as oito colunas lógicas. As oito primeiras são o
        # esquema oficial e a coluna extra é sempre descartada.
        df = df.iloc[:, :8].copy()

        df.columns = [
            'regiao', 'codigo_UF', 'UF', 'codigo_IBGE', 'municipio',
            normalizar_col(f'total_que_{habito}'),
            normalizar_col(f'percentual_que_{habito}'),
            normalizar_col(f'total_all_{habito}'),
        ]
        df = df[~df['regiao'].astype(str).str.contains('TOTAL', na=False)]
        codigo = pd.to_numeric(df['codigo_IBGE'], errors='coerce')
        invalido = codigo.isna() | ~codigo.between(100000, 999999)
        if invalido.any():
            raise ValueError(f'{int(invalido.sum())} código(s) IBGE inválido(s)')
        df['codigo_IBGE'] = codigo.astype('int64')
        if df['codigo_IBGE'].duplicated().any():
            raise ValueError('código IBGE repetido dentro do relatório bruto')
        col_que = normalizar_col(f'total_que_{habito}')
        col_perc = normalizar_col(f'percentual_que_{habito}')
        col_all = normalizar_col(f'total_all_{habito}')
        df[col_que] = pd.to_numeric(df[col_que], errors='coerce')
        df[col_all] = pd.to_numeric(df[col_all], errors='coerce')
        # Percentuais do portal vêm arredondados e, em alguns anos, formatados
        # como texto com '%'. A coluna processada é derivada dos contadores, sem
        # depender dessa apresentação e sem acumular erro de arredondamento.
        df[col_perc] = df[col_que] / df[col_all].replace(0, pd.NA)
        return meta, df
