#!/usr/bin/env python3
"""Standalone HTTP server to download CAN log files and routes via browser."""
import os
import http.server

LOG_DIR = "/data/media/0/realdata"
PORT = 8082

HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>CAN Logs</title>
<style>
body{font-family:monospace;background:#111;color:#0f0;padding:20px}
h1{color:#0f0}
a{color:#0ff;text-decoration:none;font-size:18px}
a:hover{color:#fff}
li{margin:8px 0}
small{color:#666}
</style></head><body>
<h1>CAN Dump Files</h1><ul>
{FILES}
</ul></body></html>"""


class Handler(http.server.SimpleHTTPRequestHandler):
  def __init__(self, *args, **kwargs):
    super().__init__(*args, directory=LOG_DIR, **kwargs)

  def do_GET(self):
    if self.path == "/":
      self._list_files()
    else:
      super().do_GET()

  def _list_files(self):
    try:
      files = sorted(os.listdir(LOG_DIR), reverse=True)
      rows = []
      for f in files:
        path = os.path.join(LOG_DIR, f)
        if os.path.isfile(path):
          size = os.path.getsize(path)
          rows.append(f'<li><a href="/{f}">{f}</a> <small>({size:,} bytes)</small></li>')
      html = HTML.replace("{FILES}", "\n".join(rows) if rows else "<li>no files</li>")
      self.send_response(200)
      self.send_header("Content-type", "text/html; charset=utf-8")
      self.end_headers()
      self.wfile.write(html.encode())
    except Exception:
      self.send_error(500)

  def log_message(self, format, *args):
    pass


if __name__ == "__main__":
  print(f"Serving {LOG_DIR} on http://0.0.0.0:{PORT}")
  http.server.HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
