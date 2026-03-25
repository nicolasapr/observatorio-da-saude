# extract/base.py
"""
Contrato base para todos os downloaders do pipeline Extract.
Toda nova fonte de dados deve herdar BaseDownloader e implementar download().
"""
from abc import ABC, abstractmethod
from pathlib import Path
import logging


class BaseDownloader(ABC):
    """
    Interface comum para downloaders.

    Parâmetros:
        output_dir — pasta onde os arquivos serão salvos (criada se não existir)

    Uso:
        class MinhaFonte(BaseDownloader):
            def download(self, ano: int) -> None:
                ...
    """

    def __init__(self, output_dir: str | Path) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    @abstractmethod
    def download(self, ano: int) -> None:
        """Baixa dados para `ano` e salva em self.output_dir."""

    @property
    def name(self) -> str:
        return self.__class__.__name__

    def _info(self, msg: str, *args) -> None:
        logging.info("[%s] %s", self.name, msg % args if args else msg)

    def _warn(self, msg: str, *args) -> None:
        logging.warning("[%s] %s", self.name, msg % args if args else msg)

    def _error(self, msg: str, *args) -> None:
        logging.error("[%s] %s", self.name, msg % args if args else msg)
