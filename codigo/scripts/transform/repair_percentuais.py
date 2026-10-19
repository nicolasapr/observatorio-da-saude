# transform/repair_percentuais.py
"""Verificador de percentuais derivados e contadores do pipeline.

Por padrão, este módulo é somente leitura. Ele confere se cada
``percentual_que_*`` corresponde a ``total_que_* / total_all_*`` e se os
contadores são inteiros. A opção explícita ``--aplicar-percentuais`` apenas
recalcula as colunas percentuais; nunca altera contadores.

Não existe uma regra segura que permita inferir, a partir de um número como
``2,5``, se ele significa dois vírgula cinco ou dois mil e quinhentos. A antiga
heurística multiplicava alguns decimais por mil e foi removida. Contagens que
pareçam mal interpretadas devem ser refeitas a partir do relatório SISVAN/FNDE
de origem, nunca por conversão automática.
"""
import argparse
import sys
import logging
from pathlib import Path

import pandas as pd

from .io_seguro import salvar_excel
from scripts.config import (
    PNAES_PERCEN_DIR,
    PNAES_FINAIS_DIR,
    SISVAN_MENSAIS_DIR,
    SISVAN_ANUAIS_DIR,
    SISVAN_HISTORICO_DIR,
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)],
)


# ---------------------------------------------------------------------------
# Funções de verificação e recálculo seguro
# ---------------------------------------------------------------------------

def _contar_contadores_nao_inteiros(df: pd.DataFrame) -> int:
    """Conta valores não inteiros sem tentar adivinhar sua origem."""
    colunas = [c for c in df.columns
               if c.startswith('total_que_') or c.startswith('total_all_')]
    encontrados = 0
    for col in colunas:
        series = pd.to_numeric(df[col], errors='coerce')
        encontrados += int((series.notna() & (series % 1 != 0)).sum())
    return encontrados


def _contar_percentuais_incoerentes(df: pd.DataFrame) -> int:
    """Conta percentuais que divergem dos contadores que os determinam."""
    incoerentes = 0
    for col_perc in [c for c in df.columns if c.startswith('percentual_que_')]:
        habito = col_perc.removeprefix('percentual_que_')
        col_num, col_den = f'total_que_{habito}', f'total_all_{habito}'
        if col_num not in df.columns or col_den not in df.columns:
            continue
        num = pd.to_numeric(df[col_num], errors='coerce')
        den = pd.to_numeric(df[col_den], errors='coerce')
        esperado = num / den.replace(0, pd.NA)
        atual = pd.to_numeric(df[col_perc], errors='coerce')
        diferentes = ~(atual.isna() & esperado.isna()) & ~atual.sub(esperado).abs().le(1e-12)
        incoerentes += int(diferentes.sum())
    return incoerentes


def _recalcular_percentuais(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Recalcula percentual_que_* = total_que_* / total_all_*."""
    colunas_perc = [c for c in df.columns if c.startswith('percentual_que_')]
    corrigidas = 0
    for col_perc in colunas_perc:
        habito  = col_perc.removeprefix('percentual_que_')
        col_num = f'total_que_{habito}'
        col_den = f'total_all_{habito}'
        if col_num in df.columns and col_den in df.columns:
            num = pd.to_numeric(df[col_num], errors='coerce')
            den = pd.to_numeric(df[col_den], errors='coerce').replace(0, pd.NA)
            df[col_perc] = num / den
            corrigidas += 1
    return df, corrigidas


def _verificar_arquivo(path: Path, aplicar_percentuais: bool = False) -> str:
    try:
        df = pd.read_excel(path)
        n_contadores = _contar_contadores_nao_inteiros(df)
        n_percentuais = _contar_percentuais_incoerentes(df)
        if aplicar_percentuais and n_percentuais:
            df, n_recalculados = _recalcular_percentuais(df)
            salvar_excel(df, path)
            return (f'  APLICADO  {path.name}  '
                    f'(percentuais_recalculados={n_recalculados}; '
                    f'contadores_nao_inteiros={n_contadores})')
        return (f'  VERIFICADO  {path.name}  '
                f'(percentuais_incoerentes={n_percentuais}; '
                f'contadores_nao_inteiros={n_contadores})')
    except Exception as e:
        return f'  ERRO  {path.name}: {e}'


def _verificar_pasta(pasta: Path, aplicar_percentuais: bool = False) -> tuple[int, int]:
    if not pasta.exists():
        logging.info('[SKIP] %s  (não existe)', pasta)
        return 0, 0
    arquivos = sorted(pasta.glob('*.xlsx'))
    if not arquivos:
        logging.info('[SKIP] %s  (vazia)', pasta)
        return 0, 0

    logging.info('=' * 60)
    logging.info('  %s', pasta)
    logging.info('=' * 60)

    total_ok = total_err = 0
    for arq in arquivos:
        msg = _verificar_arquivo(arq, aplicar_percentuais)
        logging.info(msg)
        if 'VERIFICADO' in msg or 'APLICADO' in msg: total_ok += 1
        if 'ERRO' in msg: total_err += 1
    return total_ok, total_err


# ---------------------------------------------------------------------------
# Pastas a reparar
# ---------------------------------------------------------------------------

def _pastas_pnaes() -> list[Path]:
    pastas = []
    for faixa in ['2a4', '5a9', 'Adolescentes']:
        pastas.append(PNAES_PERCEN_DIR / faixa)
        pastas.append(PNAES_FINAIS_DIR / faixa)
    return pastas


def _pastas_sisvan() -> list[Path]:
    """Retorna todas as pastas de sumários mensais, anuais e histórico."""
    pastas = []
    # mensais: mensais/{ano}/{mes}/
    if SISVAN_MENSAIS_DIR.exists():
        for pasta_ano in sorted(SISVAN_MENSAIS_DIR.iterdir()):
            if pasta_ano.is_dir():
                for pasta_mes in sorted(pasta_ano.iterdir()):
                    if pasta_mes.is_dir():
                        pastas.append(pasta_mes)
    # anuais: anuais/{ano}/
    if SISVAN_ANUAIS_DIR.exists():
        for pasta_ano in sorted(SISVAN_ANUAIS_DIR.iterdir()):
            if pasta_ano.is_dir():
                pastas.append(pasta_ano)
    # histórico: historico/
    pastas.append(SISVAN_HISTORICO_DIR)
    return pastas


def main() -> None:
    parser = argparse.ArgumentParser(description='Verifica percentuais derivados sem alterar contadores.')
    parser.add_argument(
        '--aplicar-percentuais', action='store_true',
        help='recalcula somente percentual_que_*; por padrão, não escreve arquivos',
    )
    args = parser.parse_args()
    total_ok = total_err = 0

    for pasta in _pastas_pnaes() + _pastas_sisvan():
        ok, err = _verificar_pasta(pasta, args.aplicar_percentuais)
        total_ok  += ok
        total_err += err

    logging.info('=' * 60)
    modo = 'percentuais recalculados' if args.aplicar_percentuais else 'arquivos verificados sem escrita'
    logging.info('  Concluído: %d %s, %d com erro', total_ok, modo, total_err)
    logging.info('=' * 60)


if __name__ == '__main__':
    main()
