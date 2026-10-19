#!/usr/bin/env python3
"""reaplicar_brutos — reescreve no sumário os marcadores cujo .xls original está
guardado, tomando o relatório como fonte da verdade.

Usado depois que a auditoria de ponta a ponta acusou totais inflados: a fusão de
duplicatas somava linhas que eram cópia parcial da mesma linha. Reaplicar do
bruto zera qualquer resíduo nas colunas que têm relatório em disco.

Uso: python3 ../analise/reaplicar_brutos.py [ano ...]
"""
import sys
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent / 'codigo'
sys.path.insert(0, str(RAIZ))
from scripts.config import SISVAN_MENSAIS_DIR                       # noqa: E402
from scripts.transform.aplicar_recuperado import aplicar            # noqa: E402
from scripts.extract.sisvan import HABITOS                          # noqa: E402

anos = [int(a) for a in sys.argv[1:]] or list(range(2015, 2025))
ok = falha = 0
for ano in anos:
    base = SISVAN_MENSAIS_DIR / str(ano)
    if not base.exists():
        continue
    for bruto in sorted(base.glob('*/*/*.xls')):
        mes = unicodedata.normalize('NFC', bruto.parent.parent.name)
        faixa = unicodedata.normalize('NFC', bruto.parent.name)
        stem = unicodedata.normalize('NFC', bruto.stem)
        habito = next((h for h in HABITOS
                       if unicodedata.normalize('NFC', h[:60].replace('/', '_')) == stem), None)
        if habito is None:
            print(f'  sem mapeamento: {bruto}')
            falha += 1
            continue
        try:
            aplicar(ano, mes, faixa, habito)
            ok += 1
        except Exception as e:
            print(f'  ERRO {ano}/{mes}/{faixa}/{stem[:30]}: {e}')
            falha += 1
print(f'{ok} marcador(es) reaplicado(s) do bruto · {falha} falha(s)')
