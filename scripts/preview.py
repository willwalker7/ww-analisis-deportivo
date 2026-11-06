"""Vista previa local de la web: junta site/ y data/ en _site/ y lo sirve.

Uso (desde la raíz del repositorio):
    py scripts\\preview.py            -> abre http://localhost:8000
    py scripts\\preview.py --demo     -> usa demo_data/ (generado con py -m src.update --demo)
"""
import argparse
import functools
import http.server
import shutil
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def build(data_dir="data", out="_site"):
    out = ROOT / out
    shutil.rmtree(out, ignore_errors=True)
    shutil.copytree(ROOT / "site", out)
    shutil.copytree(ROOT / data_dir, out / "data")
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    out = build("demo_data" if args.demo else "data")
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(out))
    url = f"http://localhost:{args.port}"
    print(f"Sirviendo {out} en {url} (Ctrl+C para parar)")
    webbrowser.open(url)
    http.server.ThreadingHTTPServer(("127.0.0.1", args.port), handler).serve_forever()


if __name__ == "__main__":
    main()
