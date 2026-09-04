from __future__ import annotations

import os
import threading
import webbrowser

import provider_server


def main() -> None:
    host = os.getenv("AXIOMIZE_PROVIDER_HOST", provider_server.HOST)
    port = int(os.getenv("AXIOMIZE_PROVIDER_PORT", str(provider_server.PORT)))
    server = provider_server.ThreadingHTTPServer((host, port), provider_server.ProviderHandler)

    url = f"http://{host}:{port}/"
    print(f"Axiomize hosted prototype listening on {url}")
    threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    server.serve_forever()


if __name__ == "__main__":
    main()
