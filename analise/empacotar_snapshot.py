"""Empacota toda a pasta de dados e registra SHA-256 de cada arquivo.

Não modifica os insumos. O pacote deve ficar fora da pasta de origem.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import tarfile
import unicodedata


def sha256(caminho):
    h = hashlib.sha256()
    with Path(caminho).open('rb') as f:
        for bloco in iter(lambda: f.read(1024 * 1024), b''):
            h.update(bloco)
    return h.hexdigest()


def empacotar(origem: Path, pacote: Path):
    origem, pacote = origem.resolve(), pacote.resolve()
    if origem == pacote or origem in pacote.parents:
        raise ValueError('o pacote deve ficar fora da pasta de dados')
    if pacote.exists():
        raise FileExistsError(pacote)
    arquivos = sorted(p for p in origem.rglob('*') if p.is_file())
    if not arquivos:
        raise ValueError('a origem não contém arquivos')
    if any(p.is_symlink() for p in origem.rglob('*')):
        raise ValueError('a pasta de dados contém links simbólicos; confira o escopo')
    nomes = [unicodedata.normalize('NFC', p.relative_to(origem).as_posix()) for p in arquivos]
    if len(nomes) != len(set(nomes)):
        raise ValueError('nomes colidem após normalização Unicode')
    pacote.parent.mkdir(parents=True, exist_ok=True)
    registros = []
    class Leitor:
        def __init__(self, stream):
            self.stream, self.hash = stream, hashlib.sha256()
        def read(self, tamanho=-1):
            bloco = self.stream.read(tamanho)
            self.hash.update(bloco)
            return bloco
    try:
        with tarfile.open(pacote, 'w:gz', compresslevel=3) as tar:
            for p, nome in zip(arquivos, nomes, strict=True):
                antes = p.stat()
                info = tar.gettarinfo(str(p), arcname='dados/'+nome)
                info.uid = info.gid = 0
                info.uname = info.gname = ''
                with p.open('rb') as f:
                    leitor = Leitor(f)
                    tar.addfile(info, leitor)
                depois = p.stat()
                if (antes.st_size, antes.st_mtime_ns) != (depois.st_size, depois.st_mtime_ns):
                    raise RuntimeError(f'arquivo mudou durante a leitura: {p}')
                registros.append({'caminho': nome, 'bytes': antes.st_size, 'sha256': leitor.hash.hexdigest()})
            manifesto = {'versao': 1, 'escopo': 'todos os arquivos da pasta dados preservada, incluindo auxiliares', 'arquivos': registros, 'quantidade': len(registros), 'bytes_descompactados': sum(x['bytes'] for x in registros)}
            blob = json.dumps(manifesto, ensure_ascii=False, indent=2).encode('utf-8')
            info = tarfile.TarInfo('MANIFESTO.json')
            info.size = len(blob)
            tar.addfile(info, io.BytesIO(blob))
    except BaseException:
        pacote.unlink(missing_ok=True)
        raise
    manifesto_path = pacote.parent/'MANIFESTO.json'
    manifesto_path.write_bytes(blob)
    checksum = sha256(pacote)
    (pacote.parent/'SHA256SUMS').write_text(f'{checksum}  {pacote.name}\n{sha256(manifesto_path)}  MANIFESTO.json\n', encoding='utf-8')
    return {'arquivo': pacote.name, 'bytes': pacote.stat().st_size, 'sha256': checksum, 'quantidade_arquivos': len(registros), 'bytes_descompactados': manifesto['bytes_descompactados']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--origem', type=Path, default=Path(__file__).resolve().parents[1]/'dados')
    parser.add_argument('--pacote', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(empacotar(args.origem, args.pacote), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
