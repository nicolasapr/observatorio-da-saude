# transform/base.py
"""
Contrato base para todos os transformers do pipeline Transform.
Toda transformação deve herdar BaseTransformer e implementar transform().
"""
from abc import ABC, abstractmethod
from pathlib import Path
import logging


class BaseTransformer(ABC):
    """
    Interface comum para transformers.

    Parâmetros:
        data_dir   — pasta raiz dos dados de entrada
        output_dir — pasta de saída (padrão: mesma que data_dir)
    """

    def __init__(self, data_dir: str | Path, output_dir: str | Path | None = None) -> None:
        self.data_dir   = Path(data_dir)
        self.output_dir = Path(output_dir) if output_dir else self.data_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    @abstractmethod
    def transform(self, ano: int) -> None:
        """Executa a transformação para o ano dado."""

    @property
    def name(self) -> str:
        return self.__class__.__name__

    def _info(self, msg: str, *args) -> None:
        logging.info("[%s] %s", self.name, msg % args if args else msg)

    def _warn(self, msg: str, *args) -> None:
        logging.warning("[%s] %s", self.name, msg % args if args else msg)

    def _error(self, msg: str, *args) -> None:
        logging.error("[%s] %s", self.name, msg % args if args else msg)

    def _anos_disponiveis(self) -> list[int]:
        """Lista anos numéricos disponíveis em data_dir."""
        return sorted(
            int(p.name)
            for p in self.data_dir.iterdir()
            if p.is_dir() and p.name.isdigit()
        )
