# extract/sisvan.py
"""
SISVANDownloader — baixa hábitos alimentares via Selenium.

Saída: dados/sisvan/mensais/{ano}/{MES}/{faixa}/{habito}.csv

Dependências:
    pip install selenium
    ChromeDriver compatível com o Chrome instalado
"""
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select, WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from time import sleep
import os
import shutil
from pathlib import Path

from .base import BaseDownloader
from scripts.config import SISVAN_MENSAIS_DIR

SITE = "https://sisaps.saude.gov.br/sisvan/relatoriopublico/index"

MESES = [
    'JANEIRO', 'FEVEREIRO', 'MARÇO', 'ABRIL', 'MAIO', 'JUNHO',
    'JULHO', 'AGOSTO', 'SETEMBRO', 'OUTUBRO', 'NOVEMBRO', 'DEZEMBRO',
]
FASES = ['Crianças de 2 a 4 anos', 'Crianças de 5 a 9 anos', 'Adolescentes']
HABITOS = [
    'Hábito de realizar no mínimo as três refeições principais do dia',
    'Hábito de realizar as refeições assistindo à televisão',
    'Consumo de feijão',
    'Consumo de fruta',
    'Consumo de verduras e legumes',
    'Consumo de Alimentos Ultraprocessados',
    'Consumo de hambúrguer e/ou embutidos',
    'Consumo de bebidas adoçadas',
    'Consumo de macarrão instantâneo, salgadinho de pacote ou biscoito salgado',
    'Consumo de biscoito recheado, doces ou guloseimas',
]

AGRUP            = 'MUNICÍPIO'
ESTAD            = 'TODOS'
MUNICIP          = 'TODOS'
FX_ET            = 3
DOWNLOAD_TIMEOUT = 60  # segundos


class SISVANDownloader(BaseDownloader):
    """
    Baixa dados do SISVAN para um ano.
    Aceita escopo reduzido (meses/fases/habitos) para testes rápidos.

    output_dir padrão: dados/sisvan/mensais/
    """

    def __init__(self, output_dir=None, meses=None, fases=None, habitos=None):
        super().__init__(output_dir or SISVAN_MENSAIS_DIR)
        self.meses   = meses   or MESES
        self.fases   = fases   or FASES
        self.habitos = habitos or HABITOS

    def download(self, ano: int) -> None:
        """Baixa output_dir/{ano}/{MES}/{fase}/{habito}.csv para o ano dado."""
        pasta_transito = Path(os.path.expanduser("~")) / "Downloads_Selenium_Staging"
        pasta_transito.mkdir(parents=True, exist_ok=True)

        opcoes = Options()
        opcoes.add_experimental_option("prefs", {
            "download.default_directory": str(pasta_transito),
            "download.prompt_for_download": False,
        })

        driver = webdriver.Chrome(options=opcoes)
        driver.get(SITE)
        driver.maximize_window()
        wait = WebDriverWait(driver, 20)

        try:
            for mes in self.meses:
                for fase in self.fases:
                    for habito in self.habitos:
                        self._baixar_habito(driver, wait, ano, mes, fase, habito, pasta_transito)
        finally:
            driver.quit()

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------

    def _baixar_habito(self, driver, wait, ano, mes, fase, habito, pasta_transito):
        destino = (
            self.output_dir
            / str(ano)
            / mes
            / fase.replace(" ", "_").replace("/", "_")
            / f"{habito[:60].replace('/', '_')}.csv"
        )
        if destino.exists():
            self._info("Já existe: %s/%s/%s — pulando.", mes, fase, habito[:40])
            return

        destino.parent.mkdir(parents=True, exist_ok=True)

        try:
            wait.until(EC.element_to_be_clickable((By.ID, "abrirFiltro"))).click()
            Select(wait.until(EC.presence_of_element_located((By.ID, "cbAno")))).select_by_value(str(ano))
            Select(driver.find_element(By.ID, "cbMes")).select_by_visible_text(mes)
            Select(driver.find_element(By.ID, "cbFaseVida")).select_by_visible_text(fase)
            Select(driver.find_element(By.ID, "cbHabito")).select_by_visible_text(habito)
            Select(driver.find_element(By.ID, "cbAgrupamento")).select_by_visible_text(AGRUP)
            Select(driver.find_element(By.ID, "cbEstado")).select_by_visible_text(ESTAD)
            Select(driver.find_element(By.ID, "cbMunicipio")).select_by_visible_text(MUNICIP)
            driver.find_element(By.ID, "btnPesquisar").click()
            sleep(2)
            driver.find_element(By.XPATH, "//a[contains(@href,'exportarCSV')]").click()

            nome = self._aguardar_download(pasta_transito)
            if nome:
                shutil.move(str(pasta_transito / nome), str(destino))
                self._info("Salvo: %s", destino.relative_to(self.output_dir))
            else:
                self._warn("Timeout no download: %s/%s/%s", mes, fase, habito[:40])
        except Exception as e:
            self._error("Erro em %s/%s/%s: %s", mes, fase, habito[:40], e)

    @staticmethod
    def _aguardar_download(pasta: Path, timeout: int = DOWNLOAD_TIMEOUT) -> str | None:
        for _ in range(timeout):
            arquivos = [f for f in os.listdir(pasta) if not f.endswith('.crdownload')]
            if arquivos:
                return arquivos[0]
            sleep(1)
        return None
