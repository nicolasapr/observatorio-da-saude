# extract/pnaes.py
"""
PNAESDownloader — download direto dos arquivos XLSX do FNDE.

Os arquivos estão disponíveis como links estáticos na página:
https://www.gov.br/fnde/pt-br/acesso-a-informacao/acoes-e-programas/programas/pnae/
consultas/repasses-financeiros-por-entidade-executora/pnae-repasses-financeiros

Dois tipos de arquivo:
  - redes: Dados financeiros Redes Estadual, Distrital e Municipal
  - federal: Dados orçamentários e financeiros Rede Federal

Uso:
    downloader = PNAESDownloader()
    downloader.download_all()          # baixa todos os anos disponíveis
    downloader.download(2024)          # baixa um ano específico (redes)
    downloader.download(2024, "federal")  # baixa rede federal
"""
import time
import io
import os
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
import pandas as pd
from bs4 import BeautifulSoup

from .base import BaseDownloader
from scripts.config import PNAES_REDES_DIR

_BASE = (
    "https://www.gov.br/fnde/pt-br/acesso-a-informacao/acoes-e-programas/"
    "programas/pnae/consultas/repasses-financeiros-por-entidade-executora/"
)

# URLs mapeadas explicitamente — os nomes mudam a cada ano no FNDE
_URLS_REDES: dict[int, str] = {
    2024: _BASE + "DadosFinanceirosdoPNAE_RedesEstadual_Distrital_Municipal_PorEntidadeExecutora_2024.xlsx",
    2023: _BASE + "2023RedesEstadualDistritaleMunicipal.xlsx",
    2022: _BASE + "PrevisodeRepasseporAo2022.xlsx",
    2021: _BASE + "PrevisodeRepasseporAo2021.xlsx",
    2020: _BASE + "PrevisodeRepasseporAo2020.xlsx",
    2019: _BASE + "PrevisodeRepasseporAo2019.xlsx",
    2018: _BASE + "2018REDESESTADUALDISTRITALEMUNICIPAL.xlsx",
    2017: _BASE + "2017REDESESTADULADISTRITALEMUNICIPAL.xlsx",
    2016: _BASE + "2016REDESESTADUALDISTRITALEMUNICIPAL.xlsx",
    2015: _BASE + "2015REDESESTADUALDISTRITALEMUNICIPAL.xlsx",
    2014: _BASE + "2014REDESESTADUALDISTRITALEMUNICIPAL.xlsx",
    2013: _BASE + "2013REDESESTADUALDISTRITALEMUNICIPAL.xlsx",
    2012: _BASE + "2012REDEESTADUALDISTRITALEMUNICIPAL.xlsx",
    2011: _BASE + "2011REDESESTADUALDISTRITALEMUNICIPAL.xlsx",
    2010: _BASE + "2010REDESESTADUALDISTRITALEMUNICIPAL.xlsx",
}

_URLS_FEDERAL: dict[int, str] = {
    2024: _BASE + "DadosOrcamentarioseFinanceirosdoPNAE_RedeFederal_PorEntidadeExecutora_2024.xlsx",
    2023: _BASE + "2023RedeFederal.xlsx",
    2022: _BASE + "EscolasFederais2022.xlsx",
    2021: _BASE + "2021RedeFederal.xlsx",
    2020: _BASE + "2020RedeFederal.xlsx",
    2019: _BASE + "2019RedeFederal.xlsx",
    2018: _BASE + "2018RedeFederal.xlsx",
    2017: _BASE + "2017RedeFederal.xlsx",
    2016: _BASE + "2016RedeFederal.xlsx",
    2015: _BASE + "2015RedeFederal.xlsx",
    # 2014 está em caminho diferente no site do FNDE
    2014: (
        "https://www.gov.br/fnde/pt-br/acesso-a-informacao/acoes-e-programas/"
        "programas/pnae/consultas/2014RedeFederal.xlsx"
    ),
    2013: _BASE + "2013RedeFederal.xlsx",
    2012: _BASE + "2012RedeFederal.xlsx",
    2011: _BASE + "2011RedeFederal.xlsx",
    2010: _BASE + "2010RedeFedral.xlsx",  # typo original do FNDE: "Fedral"
}

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    )
}


class PNAESDownloader(BaseDownloader):
    """
    Baixa os arquivos XLSX de repasse financeiro do PNAE/FNDE.

    Parâmetros
    ----------
    output_dir : Path | None
        Diretório de saída. Padrão: PNAES_REDES_DIR (config.py).
    timeout : int
        Timeout HTTP em segundos (padrão: 60).
    delay : float
        Pausa entre downloads em segundos para não sobrecarregar o servidor.
    """

    def __init__(
        self,
        output_dir: Path | None = None,
        timeout: int = 60,
        delay: float = 1.5,
    ):
        super().__init__(output_dir or PNAES_REDES_DIR)
        self.timeout = timeout
        self.delay = delay

    # ------------------------------------------------------------------
    # Interface pública
    # ------------------------------------------------------------------

    def download(self, ano: int, rede: str = "redes") -> Path:
        """
        Baixa o arquivo XLSX de um ano específico.

        Parâmetros
        ----------
        ano  : int  — ano desejado (ex: 2024)
        rede : str  — "redes" (estadual/distrital/municipal) ou "federal"

        Retorna
        -------
        Path do arquivo salvo.
        """
        urls = _URLS_REDES if rede == "redes" else _URLS_FEDERAL
        if rede not in {'redes', 'federal'}:
            raise ValueError(f'Rede inválida: {rede}')
        if ano in urls:
            return self._baixar(ano, urls[ano], rede)

        # Ano não mapeado — tenta descobrir via HEAD nos candidatos conhecidos
        print(f"[PNAES] Ano {ano}/{rede} não mapeado — tentando descoberta automática...")
        url = self._descobrir_url(ano, rede)
        if url is None:
            available = sorted(urls.keys(), reverse=True)
            raise ValueError(
                f"Nenhuma URL encontrada para PNAES {ano}/{rede}. "
                f"Anos mapeados: {available}. "
                f"Adicione a URL manualmente em _URLS_REDES ou _URLS_FEDERAL."
            )
        return self._baixar(ano, url, rede)

    def download_all(
        self,
        redes: tuple[str, ...] = ("redes", "federal"),
        anos: list[int] | None = None,
    ) -> list[Path]:
        """
        Baixa todos os arquivos disponíveis.

        Parâmetros
        ----------
        redes : tuple  — quais redes baixar ("redes", "federal" ou ambas)
        anos  : list   — subset de anos; None = todos disponíveis
        """
        baixados: list[Path] = []
        falhas = []
        for rede in redes:
            urls = _URLS_REDES if rede == "redes" else _URLS_FEDERAL
            anos_alvo = anos if anos else sorted(urls.keys(), reverse=True)
            for ano in anos_alvo:
                if ano not in urls:
                    print(f"[PNAES] Pulando {ano}/{rede} — URL não mapeada")
                    continue
                try:
                    path = self._baixar(ano, urls[ano], rede)
                    baixados.append(path)
                    time.sleep(self.delay)
                except Exception as exc:
                    print(f"[PNAES] ERRO {ano}/{rede}: {exc}")
                    falhas.append(f'{ano}/{rede}: {exc}')
        if falhas:
            raise RuntimeError('Downloads FNDE incompletos: ' + '; '.join(falhas))
        return baixados

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------

    def _candidatos_url(self, ano: int, rede: str) -> list[str]:
        """
        Gera candidatos de URL para um ano não mapeado, do padrão mais
        recente ao mais antigo, baseado nos padrões históricos do FNDE.
        """
        if rede == "redes":
            nomes = [
                f"DadosFinanceirosdoPNAE_RedesEstadual_Distrital_Municipal_PorEntidadeExecutora_{ano}.xlsx",
                f"{ano}RedesEstadualDistritaleMunicipal.xlsx",
                f"{ano}REDESESTADUALDISTRITALEMUNICIPAL.xlsx",
                f"PrevisodeRepasseporAo{ano}.xlsx",
                f"{ano}REDEESTADUALDISTRITALEMUNICIPAL.xlsx",
            ]
        else:
            nomes = [
                f"DadosOrcamentarioseFinanceirosdoPNAE_RedeFederal_PorEntidadeExecutora_{ano}.xlsx",
                f"{ano}RedeFederal.xlsx",
                f"{ano}REDEFEDERAL.xlsx",
                f"EscolasFederais{ano}.xlsx",
                f"{ano}RedeFedral.xlsx",  # typo histórico do FNDE
            ]
        return [_BASE + nome for nome in nomes]

    def _descobrir_url(self, ano: int, rede: str) -> str | None:
        """Testa cada candidato via HEAD e retorna a primeira URL que responder 200."""
        for url in self._candidatos_url(ano, rede):
            try:
                r = requests.head(url, headers=_HEADERS, timeout=15, allow_redirects=True)
                if r.status_code == 200:
                    print(f"[PNAES] URL descoberta para {ano}/{rede}: {url}")
                    return url
                print(f"[PNAES] HEAD {url.split('/')[-1]} → {r.status_code}")
            except Exception as exc:
                print(f"[PNAES] HEAD falhou ({url.split('/')[-1]}): {exc}")
        return None

    def _baixar(self, ano: int, url: str, rede: str) -> Path:
        prefixo = "Redes" if rede == "redes" else "Federal"
        destino = self.output_dir / f"PNAE_{prefixo}_{ano}.xlsx"

        if destino.exists():
            self._validar_planilha(destino.read_bytes(), rede)
            print(f"[PNAES] Já existe arquivo válido: {destino.name}")
            return destino

        print(f"[PNAES] Baixando {ano} ({rede}) ...")
        resp = requests.get(url, headers=_HEADERS, timeout=self.timeout)
        resp.raise_for_status()
        conteudo = resp.content
        if not zipfile.is_zipfile(io.BytesIO(conteudo)):
            soup = BeautifulSoup(resp.text, 'html.parser')
            links = [urljoin(resp.url, a['href']) for a in soup.select('a[href]') if '@@download' in a['href']]
            links = list(dict.fromkeys(u for u in links if urlparse(u).scheme == 'https' and urlparse(u).netloc == urlparse(url).netloc))
            if len(links) != 1:
                raise ValueError(f'FNDE não retornou Excel nem um link de download inequívoco: {url}')
            resp = requests.get(links[0], headers=_HEADERS, timeout=self.timeout)
            resp.raise_for_status()
            conteudo = resp.content
        self._validar_planilha(conteudo, rede)
        temporario = None
        try:
            with tempfile.NamedTemporaryFile(prefix='.fnde-', suffix='.parcial', dir=self.output_dir, delete=False) as arq:
                temporario = Path(arq.name)
                arq.write(conteudo)
            os.replace(temporario, destino)
        finally:
            if temporario is not None:
                temporario.unlink(missing_ok=True)

        tamanho_kb = destino.stat().st_size // 1024
        print(f"[PNAES] Salvo: {destino.name} ({tamanho_kb} KB)")
        return destino

    @staticmethod
    def _validar_planilha(conteudo: bytes, rede: str) -> None:
        try:
            with zipfile.ZipFile(io.BytesIO(conteudo)) as arquivo:
                if not {'[Content_Types].xml', 'xl/workbook.xml'} <= set(arquivo.namelist()):
                    raise ValueError('estrutura XLSX ausente')
            quadro = pd.read_excel(io.BytesIO(conteudo), header=None, nrows=15)
            if quadro.empty:
                raise ValueError('planilha vazia')
            if rede == 'redes' and not any(
                {'UF', 'ACAO'} <= {str(v).strip().upper() for v in row if pd.notna(v)}
                for _, row in quadro.iterrows()
            ):
                raise ValueError('cabeçalho UF/ACAO ausente')
        except Exception as exc:
            raise ValueError(f'Arquivo FNDE inválido: {exc}') from exc
