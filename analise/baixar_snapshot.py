"""Baixa o snapshot versionado do repositório e verifica todos os arquivos."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import tarfile
import tempfile

import requests

REPOSITORIO = 'nicolasapr/observatorio-da-saude'
TAG = 'dados-2015-2024-20261018'


def sha256(caminho):
    h = hashlib.sha256()
    with Path(caminho).open('rb') as f:
        for bloco in iter(lambda: f.read(1024 * 1024), b''):
            h.update(bloco)
    return h.hexdigest()


def conferir(dados: Path, manifesto):
    vistos = set()
    for item in manifesto['arquivos']:
        nome = PurePosixPath(item['caminho'])
        if not nome.parts or nome.is_absolute() or '..' in nome.parts or str(nome) in vistos:
            raise ValueError('caminho inválido no manifesto')
        vistos.add(str(nome))
        p = dados.joinpath(*nome.parts)
        if not p.is_file() or p.is_symlink() or p.stat().st_size != item['bytes'] or sha256(p) != item['sha256']:
            raise ValueError(f'integridade divergente: {nome}')
    return len(manifesto['arquivos'])


def instalar(pacote: Path, destino: Path):
    destino = destino.resolve()
    if destino.exists() and any(p.is_symlink() or (p.is_file() and p.name != '.gitkeep') for p in destino.rglob('*')):
        raise FileExistsError(f'{destino} já contém dados; use uma pasta vazia')
    destino.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.snapshot-', dir=destino.parent) as temp:
        area = Path(temp)
        with tarfile.open(pacote, 'r:gz') as tar:
            vistos = set()
            for membro in tar:
                nome = PurePosixPath(membro.name)
                if not nome.parts or not membro.isfile() or nome.is_absolute() or '..' in nome.parts or str(nome) in vistos or not (nome.parts[0] == 'dados' or membro.name == 'MANIFESTO.json'):
                    raise ValueError(f'entrada inválida no pacote: {membro.name}')
                vistos.add(str(nome))
                tar.extract(membro, area, filter='data')
        manifesto = json.loads((area/'MANIFESTO.json').read_text(encoding='utf-8'))
        esperados = {'MANIFESTO.json'} | {f"dados/{item['caminho']}" for item in manifesto['arquivos']}
        if vistos != esperados:
            raise ValueError('o conteúdo do pacote difere do manifesto')
        quantidade = conferir(area/'dados', manifesto)
        (area/'dados'/'.snapshot-manifest.json').write_text(json.dumps(manifesto, ensure_ascii=False, indent=2), encoding='utf-8')
        anterior = area/'estrutura-anterior'
        if destino.exists():
            os.replace(destino, anterior)
        try:
            os.replace(area/'dados', destino)
        except BaseException:
            if anterior.exists():
                os.replace(anterior, destino)
            raise
    return quantidade


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destino', type=Path, default=Path(__file__).resolve().parents[1]/'dados')
    parser.add_argument('--verificar', action='store_true', help='confere o snapshot instalado sem baixar')
    args = parser.parse_args()
    if args.verificar:
        manifesto = json.loads((args.destino/'.snapshot-manifest.json').read_text(encoding='utf-8'))
        print(f'{conferir(args.destino, manifesto)} arquivos conferidos')
        return
    if args.destino.exists() and any(p.is_file() and p.name != '.gitkeep' for p in args.destino.rglob('*')):
        parser.error('o destino já contém dados; escolha outra pasta')
    url = f'https://api.github.com/repos/{REPOSITORIO}/releases/tags/{TAG}'
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    assets = {a['name']: a['browser_download_url'] for a in r.json()['assets']}
    nomes = [n for n in assets if n.endswith('.tar.gz')]
    if len(nomes) != 1 or 'SHA256SUMS' not in assets:
        raise ValueError('Release não contém pacote e verificações inequívocos')
    r = requests.get(assets['SHA256SUMS'], timeout=30)
    r.raise_for_status()
    checks = {linha.split(maxsplit=1)[1].strip(): linha.split()[0] for linha in r.text.splitlines() if linha.strip()}
    nome = nomes[0]
    with tempfile.TemporaryDirectory(prefix='observatorio-download-') as temp:
        pacote = Path(temp)/'dados.tar.gz'
        with requests.get(assets[nome], stream=True, timeout=(30, 180)) as resposta:
            resposta.raise_for_status()
            with pacote.open('wb') as f:
                for bloco in resposta.iter_content(chunk_size=1024 * 1024):
                    f.write(bloco)
        if sha256(pacote) != checks[nome]:
            raise ValueError('SHA-256 do pacote divergente; nada foi instalado')
        quantidade = instalar(pacote, args.destino)
    print(f'{quantidade} arquivos instalados e verificados em {args.destino.resolve()}')


if __name__ == '__main__':
    main()
