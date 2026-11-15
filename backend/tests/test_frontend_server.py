"""Exercise the static handler in memory: secrets must never become site assets."""
from io import BytesIO
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location('frontend_server', Path(__file__).resolve().parents[2]/'serve_frontend.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class Socket:
    def __init__(self, path):
        self.input = BytesIO(f'GET {path} HTTP/1.0\r\n\r\n'.encode())
        self.output = bytearray()

    def makefile(self, *args):
        return self.input

    def sendall(self, data):
        self.output.extend(data)


class Handler(module.FrontendHandler):
    def log_message(self, *args):
        pass


def response(path):
    socket = Socket(path)
    Handler(socket, ('127.0.0.1', 1), None)
    return bytes(socket.output)


def test_private_files_and_directory_listings_are_blocked():
    for path in ['/backend/.env','/backend/app.py','/.venv/pyvenv.cfg','/backend/data/experiments/PSI-25.json',
                 '/backend/%2eenv','/js/','/js/../backend/.env','/data/PSI-99/metadata.txt']:
        assert b'404' in response(path).split(b'\r\n',1)[0]


def test_public_assets_and_default_page_are_served():
    for path in ['/','/assistant.html','/js/views/assistant.js','/css/base.css',
                 '/combustion-safety-console/investigations.html']:
        assert b'200' in response(path).split(b'\r\n',1)[0]
