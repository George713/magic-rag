"""Start the local API and SvelteKit together, with one Ctrl+C to stop both."""
import argparse
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend-port", type=int, default=8000)
    parser.add_argument("--frontend-port", type=int, default=5173)
    args = parser.parse_args()
    if not all(1 <= port <= 65535 for port in (args.backend_port, args.frontend_port)) or args.backend_port == args.frontend_port:
        parser.error("Choose two different ports between 1 and 65535.")

    root = Path(__file__).resolve().parents[2]
    vite = root / "web" / "node_modules" / "vite" / "bin" / "vite.js"
    node = shutil.which("node")
    if not node or not vite.exists():
        parser.exit(1, "Install Node.js 22+, then run npm.cmd ci in the web folder.\n")
    for port in (args.backend_port, args.frontend_port):
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                parser.exit(1, f"Port {port} is already in use. Stop the existing server or choose another port.\n")

    stopped = threading.Event()
    signals = [signal.SIGINT] + ([signal.SIGBREAK] if os.name == "nt" else [])
    previous_handlers = {kind: signal.signal(kind, lambda *_: stopped.set()) for kind in signals}
    children = []
    api_url = f"http://127.0.0.1:{args.backend_port}"
    web_url = f"http://127.0.0.1:{args.frontend_port}"
    opener = build_opener(ProxyHandler({}))
    try:
        children.append(subprocess.Popen([sys.executable, "-m", "magic_rag", "serve", "--port", str(args.backend_port)], cwd=root))
        children.append(subprocess.Popen([node, str(vite), "--host", "127.0.0.1", "--port", str(args.frontend_port), "--strictPort"],
                                         cwd=root / "web", env={**os.environ, "MAGIC_RAG_API":api_url}))
        print("Starting backend and frontend. Press Ctrl+C to stop both.", flush=True)
        pending = {api_url + "/api/health", web_url}
        deadline = time.monotonic() + 60
        while pending and not stopped.is_set():
            for child in children:
                if child.poll() is not None:
                    raise RuntimeError("A server exited during startup; see its output above.")
            if time.monotonic() >= deadline:
                raise RuntimeError("Servers did not become ready within 60 seconds; see their output above.")
            for url in list(pending):
                try:
                    with opener.open(url, timeout=1) as response:
                        if response.status == 200:
                            pending.remove(url)
                except (OSError, URLError):
                    pass
            stopped.wait(0.2)
        if not stopped.is_set():
            print(f"\nReady: {web_url}\nBackend: {api_url}\n", flush=True)
        while not stopped.wait(0.2):
            if any(child.poll() is not None for child in children):
                # Child processes can observe the console interrupt first.
                if stopped.wait(0.3):
                    break
                raise RuntimeError("A server exited; stopping the other server too.")
        return 0
    except (OSError, RuntimeError) as exc:
        if stopped.is_set():
            return 0
        print(f"Startup failed: {exc}", file=sys.stderr, flush=True)
        return 1
    finally:
        # Console Ctrl+C also reaches both child processes. Give them time to
        # close gracefully, then clean up only the process trees we started.
        deadline = time.monotonic() + (3 if stopped.is_set() else 0)
        while any(child.poll() is None for child in children) and time.monotonic() < deadline:
            time.sleep(0.1)
        for child in reversed(children):
            if child.poll() is None:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(child.pid), "/T", "/F"], capture_output=True)
                else:
                    child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
        for kind, handler in previous_handlers.items():
            signal.signal(kind, handler)
        print("Both servers stopped.", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
