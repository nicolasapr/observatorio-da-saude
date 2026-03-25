# extract/run_all.py
"""
Orquestrador CLI da camada Extract.

Uso:
    python -m scripts.extract.run_all --ano 2024
    python -m scripts.extract.run_all --ano 2024 --only ibge mec
    python -m scripts.extract.run_all --ano 2024 --test       # SISVAN escopo mínimo
    python -m scripts.extract.run_all --pnaes-all             # baixa todos os anos PNAES
    python -m scripts.extract.run_all --pnaes-all --ano 2024  # PNAES + outros no ano
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
    parser.add_argument("--ano",       type=int, default=None, help="Ano dos dados (ex: 2024)")
    parser.add_argument("--test",      action="store_true",    help="Modo teste: SISVAN escopo mínimo")
    parser.add_argument("--pnaes-all", action="store_true",    help="Baixa todos os anos disponíveis do PNAES")
    parser.add_argument("--only", nargs="+", choices=DOWNLOADER_NAMES,
                        help="Rodar apenas estes downloaders")
    args = parser.parse_args()

    pnaes_all = getattr(args, "pnaes_all", False)

    if args.ano is None and not pnaes_all:
        parser.error("--ano é obrigatório (ou use --pnaes-all para baixar todos os anos do PNAES)")

    logging.info("=== Extract iniciado | ano=%s | pnaes_all=%s ===", args.ano, pnaes_all)

    # PNAES com download_all() — independente dos outros downloaders
    if pnaes_all:
        from scripts.extract.pnaes import PNAESDownloader
        dl_pnaes = PNAESDownloader()
        try:
            baixados = dl_pnaes.download_all()
            logging.info("✔ PNAES (todos os anos): %d arquivos baixados", len(baixados))
        except Exception as e:
            logging.error("✘ PNAES (todos os anos) falhou: %s", e)

        if args.ano is None:
            return 0  # só rodou o PNAES completo

    # Demais downloaders (requerem --ano)
    only = [n for n in (args.only or []) if n != "pnaes"] if pnaes_all else (args.only or [])
    downloaders = build_downloaders(args.test, only)
    # Exclui PNAES se já rodou via --pnaes-all
    if pnaes_all:
        from scripts.extract.pnaes import PNAESDownloader
        downloaders = [d for d in downloaders if not isinstance(d, PNAESDownloader)]

    erros = []
    for dl in downloaders:
        try:
            dl.download(args.ano)
            logging.info("✔ %s concluído", dl.name)
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
