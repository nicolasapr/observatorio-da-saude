"""
io_seguro — gravação atômica de planilhas.

`DataFrame.to_excel` escreve direto no arquivo de destino. Se o processo morrer
no meio — timeout, Ctrl-C, a VM cortando o processo — o que sobra é um .xlsx
truncado ou de zero byte, e o dado original se perde.

Aconteceu duas vezes neste projeto (2016/MAIO Crianças 5-9 ficou com 0 byte e
2016/MARÇO Crianças 2-4 truncou em 40 KB). Ambos foram reconstruídos a partir
dos relatórios brutos, mas só porque os brutos existiam.

`salvar_excel` grava num arquivo vizinho e só então renomeia. `os.replace` é
atômico: ou o destino é o arquivo antigo íntegro, ou é o novo completo.
"""
import os
from pathlib import Path

import pandas as pd


def salvar_excel(df: pd.DataFrame, caminho, **kwargs) -> None:
    caminho = Path(caminho)
    kwargs.setdefault('index', False)
    # A extensão final precisa continuar sendo .xlsx: pandas < 3 escolhe o
    # engine pela última extensão e rejeita ``arquivo.xlsx.escrevendo``.
    tmp = caminho.with_name(f'.{caminho.stem}.escrevendo{caminho.suffix}')
    try:
        df.to_excel(tmp, **kwargs)
        os.replace(tmp, caminho)
    finally:
        if tmp.exists():
            tmp.unlink()
