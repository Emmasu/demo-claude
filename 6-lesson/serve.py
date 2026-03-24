import http.server
import socketserver
import webbrowser
import os

PORT = 3000
DIR = os.path.dirname(os.path.abspath(__file__))

os.chdir(DIR)

handler = http.server.SimpleHTTPRequestHandler

with socketserver.TCPServer(("", PORT), handler) as httpd:
    url = f"http://localhost:{PORT}"
    print(f"Serving at {url}")
    webbrowser.open(url)
    httpd.serve_forever()
