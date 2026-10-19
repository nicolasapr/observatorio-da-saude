"""Regressões do ETL com fontes simuladas e execução isolada da CLI completa.

Os registros artificiais abaixo não são observações do estudo.
Execute: uv run python -m unittest discover -s tests -v
"""
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile

import pandas as pd
import requests

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / 'codigo'))

from scripts.extract.sisvan import HABITOS, FASES, MESES, SISVANDownloader
from scripts.extract.pnaes import PNAESDownloader
from scripts.extract.mec import MECDownloader
from scripts.extract.ibge import IBGEDownloader
from scripts.transform import run_all


def relatorio(mes='JANEIRO', fase='Adolescentes', habito='Consumo de fruta'):
    return (
        f'<html><meta charset="utf-8"><p>Ano: 2024 - Mês: {mes} '
        f'Fase da Vida: ADOLESCENTE Sexo: TODOS</p><p>{habito}</p>'
        f'<p>Total de {fase} acompanhados</p><table><tr>'
        + ''.join(f'<th>C{i}</th>' for i in range(8))
        + '</tr><tr><td>SUL</td><td>41</td><td>PR</td><td>410690</td>'
        '<td>CURITIBA</td><td>1.000</td><td>50%</td><td>2.000</td></tr>'
        '<tr><td>SUL</td><td>41</td><td>PR</td><td>410140</td>'
        '<td>APUCARANA</td><td>10</td><td>10%</td><td>100</td></tr></table></html>'
    ).encode('utf-8')


def excel_bytes():
    arq = io.BytesIO()
    pd.DataFrame({'UF': ['PR'], 'ACAO': ['PNAFN'], 'ENTIDADE_RESP': ['PREFEITURA DE CURITIBA'], 'VALOR_PAGO': [100]}).to_excel(arq, index=False)
    return arq.getvalue()


def resposta(conteudo, url='https://www.gov.br/fnde/arquivo.xlsx', tipo='application/octet-stream'):
    r = Mock()
    r.content, r.text, r.url = conteudo, conteudo.decode('utf-8', errors='replace'), url
    r.headers = {'content-type': tipo}
    r.iter_content.return_value = [conteudo]
    r.__enter__ = Mock(return_value=r)
    r.__exit__ = Mock(return_value=False)
    return r


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='observatorio-teste-')
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def test_fnde_resolve_pagina_html_e_valida_excel(self):
        pagina = resposta(b'<a href="/fnde/arquivo.xlsx/@@download/file">Excel</a>')
        with patch('scripts.extract.pnaes.requests.get', side_effect=[pagina, resposta(excel_bytes())]) as get:
            p = PNAESDownloader(self.root).download(2024)
        self.assertEqual(get.call_count, 2)
        self.assertEqual(pd.read_excel(p).iloc[0]['VALOR_PAGO'], 100)

    def test_fnde_rejeita_html_sem_gravar_excel(self):
        with patch('scripts.extract.pnaes.requests.get', return_value=resposta(b'<html>indisponivel</html>')):
            with self.assertRaises(ValueError):
                PNAESDownloader(self.root).download(2024)
        self.assertFalse(list(self.root.glob('*.xlsx')))

    def test_inep_extrai_nome_canonico_e_ignora_csv_auxiliar(self):
        csv = b'SG_UF;CO_MUNICIPIO;TP_DEPENDENCIA;QT_MAT_MED;QT_MAT_FUND;QT_MAT_FUND_AF\nPR;4106902;2;10;30;20\n'
        arq = io.BytesIO()
        with zipfile.ZipFile(arq, 'w') as z:
            z.writestr('dicionario.csv', b'nao;escolar')
            z.writestr('DADOS/microdados_ed_basica_2024.csv', csv)
        sessao = Mock()
        sessao.get.return_value = resposta(arq.getvalue())
        contexto = Mock()
        contexto.__enter__ = Mock(return_value=sessao)
        contexto.__exit__ = Mock(return_value=False)
        with patch.object(MECDownloader, '_descobrir_url', return_value='https://download.inep.gov.br/teste.zip'), patch('scripts.extract.mec.criar_sessao_inep', return_value=contexto):
            p = MECDownloader(self.root).download(2024)
        self.assertEqual(p.name, 'microdados_ed_basica_2024.csv')
        self.assertEqual(pd.read_csv(p, sep=';').iloc[0]['QT_MAT_MED'], 10)

    def test_inep_rejeita_selecao_ambigua(self):
        d = MECDownloader(self.root)
        self.assertIsNone(d._encontrar_csv(['escola_a.csv', 'escola_b.csv'], 2024))

    def test_sisvan_nao_aceita_cache_corrompido(self):
        p = self.root/'2024/JANEIRO/Adolescentes/Consumo de fruta.xls'
        p.parent.mkdir(parents=True)
        p.write_bytes(b'<html>erro</html>')
        with self.assertRaises(ValueError):
            SISVANDownloader(self.root)._baixar_habito(Mock(), 2024, 'JANEIRO', 'Adolescentes', 'Consumo de fruta')

    def test_sisvan_falha_de_rede_nao_vira_sucesso(self):
        sessao = Mock()
        sessao.post.side_effect = requests.ConnectionError('offline')
        with self.assertRaises(RuntimeError):
            SISVANDownloader(self.root)._baixar_habito(sessao, 2024, 'JANEIRO', 'Adolescentes', 'Consumo de fruta')
        self.assertFalse(list(self.root.rglob('*.xls')))

    def test_ibge_rejeita_resposta_vazia(self):
        r = Mock()
        r.json.return_value = [{'resultados': []}]
        with patch('scripts.extract.ibge.requests.get', return_value=r), self.assertRaises(ValueError):
            IBGEDownloader(self.root).download(2024)
        self.assertFalse(list(self.root.glob('*.csv')))

    def test_ibge_preserva_ausencia_da_fonte_sem_criar_populacao_zero(self):
        r = Mock()
        r.json.return_value = [{'resultados': [{'series': [
            {'localidade': {'id': '4106902', 'nome': 'Curitiba'}, 'serie': {'2024': '1000'}},
            {'localidade': {'id': '5101837', 'nome': 'Localidade sem estimativa'}, 'serie': {'2024': '...'}},
        ]}]}]
        with patch('scripts.extract.ibge.requests.get', return_value=r):
            IBGEDownloader(self.root).download(2024)
        d = pd.read_csv(self.root/'ibge_pop_2024.csv')
        self.assertTrue(pd.isna(d.iloc[1]['populacao']))
        self.assertEqual(d.iloc[1]['populacao_fonte'], '...')

    def test_orquestrador_interrompe_apos_falha(self):
        primeiro, segundo = Mock(), Mock()
        primeiro.transform.side_effect = ValueError('entrada inválida')
        with patch.object(run_all, 'build_steps', return_value={'criar_sumarios': primeiro, 'sumarios_anuais': segundo}), patch.object(sys, 'argv', ['transform', '--ano', '2024']):
            self.assertEqual(run_all.main(), 1)
        segundo.transform.assert_not_called()

    def test_transformacao_completa_por_cli(self):
        # 12 meses, 3 faixas, 10 marcadores, dois municípios artificiais.
        for mes in MESES:
            for fase in FASES:
                pasta = self.root/'sisvan/mensais/2024'/mes/fase.replace(' ', '_')
                pasta.mkdir(parents=True)
                for habito in HABITOS:
                    (pasta/f"{habito[:60].replace('/', '_')}.xls").write_bytes(relatorio(mes, fase, habito))
        nomes = {410690: 'CURITIBA', 410140: 'APUCARANA'}
        quant = pd.DataFrame({'Município': [f'{i} {nomes.get(i, f"MUNICIPIO{i}")}' for i in range(410000, 415570)], 'PNACN': .6, 'PNAPN(4)': .4, 'PNAPN(5)': .6, 'PNAFN(6-9)': .4, 'PNAFN(10-15)': .6})
        pasta = self.root/'referencia/quant_idades'
        pasta.mkdir(parents=True)
        quant.to_excel(pasta/'quant_idades.xlsx', index=False)
        pasta = self.root/'mec/microdados'
        pasta.mkdir(parents=True)
        # Nome histórico e extensão maiúscula precisam funcionar em Linux.
        pd.DataFrame({'SG_UF': ['PR', 'PR', 'PR'], 'CO_MUNICIPIO': [4106902, 4101408, 4106902], 'TP_DEPENDENCIA': [2, 2, 3], 'QT_MAT_MED': [10, 30, 1000], 'QT_MAT_FUND': [50, 50, 1000], 'QT_MAT_FUND_AF': [20, 20, 1000]}).to_csv(pasta/'microdados_censo_escolar_2024.CSV', sep=';', index=False)
        pasta = self.root/'pnaes/redes'
        pasta.mkdir(parents=True)
        pd.DataFrame([
            ['PR', 'PREFEITURA DE CURITIBA', 'PNACN', 1000],
            ['PR', 'PREFEITURA DE CURITIBA', 'PNAPN', 2000],
            ['PR', 'PREFEITURA DE CURITIBA', 'PNAFN', 3000],
            ['PR', 'PREFEITURA DE CURITIBA', 'PN+FN', 500],
            ['PR', 'PREFEITURA DE CURITIBA', 'PNAMN', 600],
            ['PR', 'PREFEITURA DE APUCARANA', 'PNAFN', 2000],
            ['PR', 'SECRETARIA DE EDUCACAO DO PARANA', 'PNAMN', 10000],
        ], columns=['UF', 'ENTIDADE_RESP', 'ACAO', 'VALOR_PAGO']).to_excel(pasta/'PNAE_Redes_2024.xlsx', index=False)
        env = dict(os.environ, OBSERVATORIO_DADOS_DIR=str(self.root), PYTHONDONTWRITEBYTECODE='1')
        proc = subprocess.run([sys.executable, '-B', '-m', 'scripts.transform.run_all', '--ano', '2024'], cwd=RAIZ/'codigo', env=env, text=True, capture_output=True, timeout=120)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        teen = pd.read_excel(self.root/'pnaes/finais/Adolescentes/PNAES_valores_Adolescentes_2024_ajustado.xlsx').set_index('codigo_IBGE')
        self.assertAlmostEqual(teen.loc[410690, 'TOTAL_EF'], 4850)
        self.assertAlmostEqual(teen.loc[410140, 'TOTAL_EF'], 8500)
        for faixa, esperado in [('2a4', 1400), ('5a9', 2600)]:
            dados = pd.read_excel(self.root/f'pnaes/finais/{faixa}/PNAES_valores_{faixa}_2024_ajustado.xlsx').set_index('codigo_IBGE')
            self.assertAlmostEqual(dados.loc[410690, 'TOTAL'], esperado)
        serie = pd.read_excel(self.root/'sisvan/series/serie_mensal_Adolescentes.xlsx')
        self.assertEqual(len(serie), 12)
        self.assertAlmostEqual(serie.iloc[0]['percentual_que_Consumo de fruta'], 1010/2100, delta=.00005)


if __name__ == '__main__':
    unittest.main()
