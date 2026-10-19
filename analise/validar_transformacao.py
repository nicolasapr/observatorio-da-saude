"""Regenera o ETL histórico numa pasta separada e compara os produtos.

Não baixa fontes nem altera dados canônicos. Requer o snapshot de dados.
Uso: uv run python analise/validar_transformacao.py --destino /tmp/validacao-ic
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unicodedata

import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ/'codigo'))
from scripts.transform.normalizacao import normalizar_df


def copiar(origem, destino):
    destino.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(origem, destino)


def quadro(caminho):
    df = normalizar_df(pd.read_excel(caminho))
    df.columns = [unicodedata.normalize('NFC', str(c)) for c in df.columns]
    # Alguns sumários históricos preservam a apresentação do portal ('79.17%',
    # '-') em vez da razão numérica. Compare esse formato pelos contadores,
    # sem alterar o arquivo de origem nem tolerar textos desconhecidos.
    for c in [c for c in df if c.startswith('percentual_que_') and df[c].dtype == object]:
        textos = df[c].dropna().astype(str)
        if not textos.str.fullmatch(r'(?:-|\d+(?:[.,]\d+)?%)').all():
            continue
        suf = c.removeprefix('percentual_que_')
        q, a = f'total_que_{suf}', f'total_all_{suf}'
        df[c] = pd.to_numeric(df[q], errors='raise') / pd.to_numeric(df[a], errors='raise').replace(0, float('nan'))
    chaves = [c for c in ['ano', 'mes', 'regiao', 'UF', 'codigo_IBGE'] if c in df]
    return df.sort_values(chaves).reset_index(drop=True) if chaves else df


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--origem', type=Path, default=RAIZ/'dados')
    parser.add_argument('--destino', type=Path, required=True)
    args = parser.parse_args()
    origem, destino = args.origem.resolve(), args.destino.resolve()
    if origem == destino or origem in destino.parents or destino in origem.parents:
        parser.error('origem e destino devem ser pastas independentes')
    if destino.exists() and any(destino.iterdir()):
        parser.error('o destino deve ser novo ou estar vazio')
    destino.mkdir(parents=True, exist_ok=True)
    originais = {p: (p.stat().st_size, p.stat().st_mtime_ns) for p in origem.rglob('*') if p.is_file()}
    # Somente os sumários canônicos na hierarquia ano/mês, sem cópias soltas.
    for padrao in ['sisvan/mensais/*/*/sumario_habitos_*.xlsx', 'sisvan/mensais/*/*/*/*.xls', 'pnaes/redes/**/*.xlsx', 'referencia/quant_idades/*.xlsx']:
        for p in origem.glob(padrao):
            copiar(p, destino/p.relative_to(origem))
    mec = destino/'mec/microdados'
    mec.parent.mkdir(parents=True, exist_ok=True)
    mec.symlink_to(origem/'mec/microdados', target_is_directory=True)
    env = dict(os.environ, OBSERVATORIO_DADOS_DIR=str(destino), PYTHONDONTWRITEBYTECODE='1')
    def executar(nome, argumentos):
        print(nome, flush=True)
        with (destino/f'{nome}.log').open('w') as log:
            subprocess.run([sys.executable, '-B', '-m', 'scripts.transform.run_all', *argumentos], cwd=RAIZ/'codigo', env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
    for ano in range(2015, 2025):
        executar(f'mensal-anual-{ano}', ['--ano', str(ano), '--only', 'criar_sumarios', 'sanear_sumarios', 'sumarios_anuais'])
    executar('agregados-rateios-fnde', ['--ano', '0', '--only', 'sumarios_totais', 'series_mensais', 'percen', 'pnaes_redes'])
    for ano in range(2015, 2025):
        executar(f'finais-{ano}', ['--ano', str(ano), '--only', 'pnaes_2a4', 'pnaes_5a9', 'pnaes_adolescentes'])
    comparados, erros = 0, []
    padroes = ['sisvan/mensais/*/*/sumario_habitos_*.xlsx', 'sisvan/anuais/*/*.xlsx', 'sisvan/historico/*.xlsx', 'sisvan/series/*.xlsx', 'pnaes/percen/*/*.xlsx', 'pnaes/valores/*/*.xlsx', 'pnaes/finais/*/*.xlsx']
    for padrao in padroes:
        for esperado in sorted(origem.glob(padrao)):
            relativo = esperado.relative_to(origem)
            try:
                pd.testing.assert_frame_equal(quadro(esperado), quadro(destino/relativo), check_dtype=False, check_like=True, rtol=1e-12, atol=1e-7)
                comparados += 1
            except (AssertionError, FileNotFoundError) as exc:
                erros.append({'arquivo': str(relativo), 'erro': str(exc)[:1500]})
    alterados = [str(p) for p, meta in originais.items() if not p.exists() or (p.stat().st_size, p.stat().st_mtime_ns) != meta]
    resultado = {'escopo': 'snapshot histórico 2015-2024; extração ao vivo não incluída', 'produtos_equivalentes': comparados, 'comparacao': 'nomes históricos normalizados; percentuais textuais legados derivados dos contadores; arquivos de origem preservados', 'divergencias': erros, 'originais_alterados': alterados}
    (destino/'resultado.json').write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(resultado, ensure_ascii=False, indent=2), flush=True)
    return int(bool(erros or alterados))


if __name__ == '__main__':
    raise SystemExit(main())
