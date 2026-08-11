from http.server import ThreadingHTTPServer
from pathlib import Path

from openpilot.common.params import Params
from openpilot.selfdrive.tesla_web.routes import make_handler


TESLA_WEB_HOST = "0.0.0.0"
TESLA_WEB_PORT = 8090


def create_server(host=TESLA_WEB_HOST, port=TESLA_WEB_PORT, params=None):
  params = params or Params()
  template_root = Path(__file__).with_name("templates")
  server = ThreadingHTTPServer((host, port), make_handler(params, template_root))
  server.daemon_threads = True
  return server


def main():
  server = create_server()
  try:
    server.serve_forever()
  finally:
    server.server_close()


if __name__ == "__main__":
  main()
