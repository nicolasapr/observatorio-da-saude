# transform/run_all.py
"""
Orquestrador CLI da camada Transform.

Ordem de execução (cada step depende do anterior):
  1. criar_sumarios      — habit files → sumário mensal
  2. sumarios_anuais     — sumário mensal → sumário anual
  3. sumarios_totais     — sumários anuais → histórico total  (ignora --ano)
  4. pnaes_redes         — Redes FNDE + Percen_PNAES → Valores_PNAES_*
  5. pnaes_2a4           — calcula TOTAL para faixa 2-4 anos
  6. pnaes_5a9           — calcula TOTAL para faixa 5-9 anos
  7. pnaes_adolescentes  — merge MEC + cálculos para adolescentes

Uso:
    python -m scripts.transform.run_all --ano 2024
    python -m scripts.transform.run_all --ano 2024 --only criar_sumarios sumarios_anuais
    python -m scripts.transform.run_all --totais       # apenas sumarios_totais
    python -m scripts.transform.run_all --ano 0 --only pnaes_redes  # todos os anos
"""
import argparse
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)],
)

STEP_NAMES = [
    'criar_sumarios',
    'sumarios_anuais',
    'sumarios_totais',
    'pnaes_redes',
    'pnaes_2a4',
    'pnaes_5a9',
    'pnaes_adolescentes',
]

# Steps que processam todos os anos internamente (ignoram --ano)
_ALL_YEARS_STEPS = {'sumarios_totais', 'pnaes_redes'}


def build_steps(only: list[str]) -> dict:
    from scripts.transform.criar_sumarios  import CriarSumariosTransformer
    from scripts.transform.sumarios_anuais import SumariosAnuaisTransformer
    from scripts.transform.sumarios_totais import SumariosTotaisTransformer
    from scripts.transform.pnaes_redes     import PNAESRedesTransformer
    from scripts.transform.pnaes import (
        PNAES2a4Transformer,
        PNAES5a9Transformer,
        PNAESAdolescentesTransformer,
    )

    all_steps = {
        'criar_sumarios':      CriarSumariosTransformer(),
        'sumarios_anuais':     SumariosAnuaisTransformer(),
        'sumarios_totais':     SumariosTotaisTransformer(),
        'pnaes_redes':         PNAESRedesTransformer(),
        'pnaes_2a4':           PNAES2a4Transformer(),
        'pnaes_5a9':           PNAES5a9Transformer(),
        'pnaes_adolescentes':  PNAESAdolescentesTransformer(),
    }
    if only:
        return {k: all_steps[k] for k in only if k in all_steps}
    return all_steps


def main() -> int:
    parser = argparse.ArgumentParser(description='Pipeline Transform — Observatório da Saúde')
    parser.add_argument('--ano',   type=int, default=0,       help='Ano a processar (0 = todos, para steps que suportam)')
    parser.add_argument('--only',  nargs='+', choices=STEP_NAMES, help='Rodar apenas estes steps')
    parser.add_argument('--totais', action='store_true',       help='Atalho: apenas sumarios_totais')
    args = parser.parse_args()

    if args.totais:
        args.only = ['sumarios_totais']

    only_set = set(args.only or [])
    needs_ano = not args.totais and not (only_set and only_set.issubset(_ALL_YEARS_STEPS))
    if needs_ano and args.ano == 0:
        parser.error('--ano é obrigatório para os steps selecionados (use --totais ou --only pnaes_redes para processar todos os anos)')

    logging.info('=== Transform iniciado | ano=%s ===', args.ano)

    steps = build_steps(args.only or [])
    erros = []

    for nome, transformer in steps.items():
        try:
            transformer.transform(args.ano)
            logging.info('✔ %s concluído', nome)
        except Exception as e:
            logging.error('✘ %s falhou: %s', nome, e)
            erros.append(nome)

    if erros:
        logging.error('=== Transform finalizado com erros: %s ===', erros)
        return 1
    logging.info('=== Transform finalizado com sucesso ===')
    return 0


if __name__ == '__main__':
    sys.exit(main())
