# extract/run_all.py
"""
Orquestrador CLI da camada Extract.

Uso:
    python -m scripts.extract.run_all --ano 2024
    python -m scripts.extract.run_all --ano 2024 --only ibge mec
    python -m scripts.extract.run_all --ano 2024 --test   # SISVAN escopo mínimo
"""
import argparse
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

DOWNLOADER_NAMES = ["sisvan", "ibge", "mec", "pnaes"]


def build_downloaders(test_mode: bool, only: list[str]):
    from scripts.extract.sisvan import SISVANDownloader
    from scripts.extract.ibge   import IBGEDownloader
    from scripts.extract.mec    import MECDownloader
    from scripts.extract.pnaes  import PNAESDownloader

    sisvan = (
        SISVANDownloader(meses=["JANEIRO"], fases=["Adolescentes"], habitos=["Consumo de fruta"])
        if test_mode
        else SISVANDownloader()
    )

    all_dl = {
        "sisvan": sisvan,
        "ibge":   IBGEDownloader(),
        "mec":    MECDownloader(),
        "pnaes":  PNAESDownloader(),
    }

    if only:
        return [all_dl[n] for n in only if n in all_dl]
    return list(all_dl.values())


def main() -> int:
    parser = argparse.ArgumentParser(description="Pipeline Extract — Observatório da Saúde")
    parser.add_argument("--ano",  type=int, required=True, help="Ano dos dados (ex: 2024)")
    parser.add_argument("--test", action="store_true",     help="Modo teste: SISVAN escopo mínimo")
    parser.add_argument("--only", nargs="+", choices=DOWNLOADER_NAMES,
                        help="Rodar apenas estes downloaders")
    args = parser.parse_args()

    logging.info("=== Extract iniciado | ano=%s | test=%s ===", args.ano, args.test)

    downloaders = build_downloaders(args.test, args.only or [])
    erros = []

    for dl in downloaders:
        try:
            dl.download(args.ano)
            logging.info("✔ %s concluído", dl.name)
        except NotImplementedError as e:
            logging.warning("⚠ %s pulado: %s", dl.name, e)
        except Exception as e:
            logging.error("✘ %s falhou: %s", dl.name, e)
            erros.append(dl.name)

    if erros:
        logging.error("=== Extract finalizado com erros: %s ===", erros)
        return 1
    logging.info("=== Extract finalizado com sucesso ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
