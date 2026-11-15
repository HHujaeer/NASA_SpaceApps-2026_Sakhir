"""Serve public frontend assets only. Backend code, credentials and raw data stay private."""
import argparse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parent


class FrontendHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def send_head(self):
        path = unquote(urlsplit(self.path).path)
        parts = Path(path).parts
        if '..' in parts or any(p.startswith('.') for p in parts):
            self.send_error(404)
            return None
        relative = path.lstrip('/') or 'overview.html'
        target = (ROOT / relative).resolve()
        if not target.is_relative_to(ROOT) or not target.is_file():
            self.send_error(404)
            return None
        public = ('css/', 'js/', 'combustion-safety-console/css/', 'combustion-safety-console/js/')
        if not (relative.startswith(public) and target.suffix in ('.css', '.js', '.map')) and not (
            target.suffix == '.html' and target.parent in (ROOT, ROOT / 'combustion-safety-console')
        ):
            self.send_error(404)
            return None
        if path == '/':
            self.path = '/overview.html'
        return super().send_head()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    ThreadingHTTPServer(('127.0.0.1', args.port), FrontendHandler).serve_forever()
