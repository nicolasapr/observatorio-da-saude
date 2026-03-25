# transform/repair_percentuais.py
"""
Utilitário de reparo — recalcula colunas percentual_que_* e corrige separadores
de milhar brasileiros mal interpretados nos arquivos PNAES e SISVAN.

Execução:
    python -m scripts.transform.repair_percentuais
"""
import sys
import logging
from pathlib import Path

import pandas as pd

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
# Funções de reparo
# ---------------------------------------------------------------------------

def _fix_br_thousands(val) -> float:
    """Converte valores com separador de milhar BR mal lido como decimal.

    Exemplo: 22.647 (lido como float) → 22647 (inteiro correto).
    Só corrige se val * 1000 for inteiro e ≥ 1000 (evita falsos positivos).
    """
    if pd.isna(val):
        return val
    f = float(val)
    if f == int(f):
        return int(f)
    scaled = f * 1000
    if abs(scaled - round(scaled)) < 0.5 and round(scaled) >= 1000:
        return round(scaled)
    return f


def _corrigir_totais(df: pd.DataFrame) -> int:
    """Corrige colunas total_que_* e total_all_* com separador BR mal interpretado."""
    colunas = [c for c in df.columns
               if c.startswith('total_que_') or c.startswith('total_all_')]
    corrigidas = 0
    for col in colunas:
        series = pd.to_numeric(df[col], errors='coerce')
        fixed  = series.apply(_fix_br_thousands)
        if not fixed.equals(series):
            df[col] = fixed
            corrigidas += 1
    return corrigidas


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


def _reparar_arquivo(path: Path) -> str:
    try:
        df = pd.read_excel(path)
        n_tot      = _corrigir_totais(df)
        df, n_perc = _recalcular_percentuais(df)
        if n_perc == 0 and n_tot == 0:
            return f'  SKIP  {path.name}  (sem colunas para reparar)'
        df.to_excel(path, index=False)
        return f'  OK    {path.name}  (totais={n_tot} cols, percentuais={n_perc} cols)'
    except Exception as e:
        return f'  ERRO  {path.name}: {e}'


def _reparar_pasta(pasta: Path) -> tuple[int, int]:
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
        msg = _reparar_arquivo(arq)
        logging.info(msg)
        if 'OK'   in msg: total_ok  += 1
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
    total_ok = total_err = 0

    for pasta in _pastas_pnaes() + _pastas_sisvan():
        ok, err = _reparar_pasta(pasta)
        total_ok  += ok
        total_err += err

    logging.info('=' * 60)
    logging.info('  Concluído: %d reparados, %d com erro', total_ok, total_err)
    logging.info('=' * 60)


if __name__ == '__main__':
    main()
