"""In-process WSGI transport for tests that mutate their database fixtures."""
from wsgiref.simple_server import make_server, WSGIRequestHandler
import app

class QuietHandler(WSGIRequestHandler):
    def log_message(self, *args):
        pass

class Server(app.Application):
    def __init__(self, address, db, token):
        super().__init__(db, token)
        self.http = make_server(*address, self.application, handler_class=QuietHandler)
        self.server_port = self.http.server_port
    def serve_forever(self):
        self.http.serve_forever(poll_interval=0.05)
    def shutdown(self):
        self.http.shutdown()
    def server_close(self):
        self.http.server_close()



def runtime_entries(root):
    manifest = (root / "server/runtime-files.txt").read_text().splitlines()
    return ("off-proxy", "VERSION", *(f"server/{path}" for path in manifest),
            "server/web/index.html", "server/web/dashboard.css", "server/web/dashboard.js")
