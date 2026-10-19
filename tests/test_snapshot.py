"""Integridade e proteção da restauração de dados, sem acessar a rede."""
import io
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analise.empacotar_snapshot import empacotar
from analise.baixar_snapshot import instalar, conferir
import json


class SnapshotTest(unittest.TestCase):
    def test_ida_e_volta_unicode_e_deteccao_de_alteracao(self):
        with tempfile.TemporaryDirectory() as pasta:
            raiz = Path(pasta)
            origem = raiz/'origem'
            origem.mkdir()
            (origem/'matrículas.csv').write_text('cidade,valor\nCuritiba,42\n')
            pacote = raiz/'pacotes/dados.tar.gz'
            resultado = empacotar(origem, pacote)
            self.assertEqual(resultado['quantidade_arquivos'], 1)
            destino = raiz/'instalado'
            self.assertEqual(instalar(pacote, destino), 1)
            manifesto = json.loads((destino/'.snapshot-manifest.json').read_text())
            self.assertEqual(conferir(destino, manifesto), 1)
            with self.assertRaises(FileExistsError):
                instalar(pacote, destino)
            (destino/'matrículas.csv').write_text('alterado')
            with self.assertRaises(ValueError):
                conferir(destino, manifesto)

    def test_rejeita_travessia_de_diretorio(self):
        with tempfile.TemporaryDirectory() as pasta:
            raiz = Path(pasta)
            pacote = raiz/'invalido.tar.gz'
            with tarfile.open(pacote, 'w:gz') as tar:
                info = tarfile.TarInfo('../fora.txt')
                info.size = 1
                tar.addfile(info, io.BytesIO(b'x'))
            with self.assertRaises(ValueError):
                instalar(pacote, raiz/'destino')
            self.assertFalse((raiz/'fora.txt').exists())
            self.assertFalse((raiz/'destino').exists())

    def test_destino_arquivo_existente_e_preservado(self):
        with tempfile.TemporaryDirectory() as pasta:
            raiz = Path(pasta)
            destino = raiz/'nao-e-pasta'
            destino.write_text('preservar')
            with self.assertRaises(FileExistsError):
                instalar(raiz/'nao-precisa-ser-aberto.tar.gz', destino)
            self.assertEqual(destino.read_text(), 'preservar')


if __name__ == '__main__':
    unittest.main()
