import argparse
import logging

from .api import create_app

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Run the C CFG Analyzer API (and the built frontend, if present).")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=5000)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO)
    create_app().run(host=args.host, port=args.port, debug=False, threaded=True)
