import argparse
from getpass import getpass
import json
import logging
import os
from pathlib import Path
import threading
from urllib.parse import urlsplit

from .auth import create_credentials
from .server import RemoteServer
from .tunnel import TunnelManager
from .runtime import write_state, STATE_DIR, stop_requested


def setup(config_path):
    existing = json.loads(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
    username = input("Login (3-64 characters): ").strip()
    password = getpass("Password (at least 12 characters): ")
    repeated = getpass("Repeat password: ")
    if password != repeated:
        raise ValueError("Passwords do not match")
    credentials = create_credentials(username, password)
    folder = str(Path(existing.get("files", "remote_files")).resolve())
    config = {"account": credentials, "files": folder}
    temporary = config_path.with_name(config_path.name + ".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(config, output, indent=2, ensure_ascii=False)
        os.replace(temporary, config_path)
        os.chmod(config_path, 0o600)
    finally:
        temporary.unlink(missing_ok=True)
    Path(folder).mkdir(parents=True, exist_ok=True)
    print("Account saved. Password is not stored as plaintext.")
    print("Start with: python -m pc_remote --public")


def main():
    parser = argparse.ArgumentParser(description="PC Helper: login/password access over HTTPS")
    parser.add_argument("--setup", action="store_true", help="Set or replace local login/password; preserve shared folder")
    parser.add_argument("--config", type=Path, default=Path(".pc-remote.json"))
    parser.add_argument("--port", type=int, default=8765)
    access = parser.add_mutually_exclusive_group()
    access.add_argument("--public", action="store_true", help="Start a temporary HTTPS Cloudflare tunnel (no domain/VPN)")
    access.add_argument("--origin", help="Existing HTTPS origin for a separately managed tunnel")
    args = parser.parse_args()
    if args.setup:
        try:
            setup(args.config)
        except (ValueError, OSError) as exc:
            parser.error(str(exc))
        return
    if not args.config.exists():
        parser.error("Run python -m pc_remote --setup first")
    if args.origin:
        origin = urlsplit(args.origin)
        if origin.scheme != "https" or not origin.hostname or origin.username or origin.password or origin.path not in ("", "/") or origin.query or origin.fragment:
            parser.error("--origin must be an HTTPS origin without a path, e.g. https://pc.example.com")
    config = json.loads(args.config.read_text(encoding="utf-8"))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        server = RemoteServer(("127.0.0.1", args.port), config.get("account"), config["files"],
                              public_origin=args.origin.rstrip("/") if args.origin else None)
    except ValueError as exc:
        parser.error(str(exc))
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    tunnel = TunnelManager(server) if args.public else None
    server.tunnel_manager = tunnel
    try:
        if tunnel:
            print("Local agent remains available while HTTPS reconnects.", flush=True)
            tunnel.start()
        elif args.origin:
            print("Open on Android:", args.origin, flush=True)
        else:
            print(f"Local: http://127.0.0.1:{args.port} (for internet access add --public)", flush=True)
        while worker.is_alive() and not stop_requested():
            state = tunnel.snapshot() if tunnel else {'state':'configured' if args.origin else 'local', 'url':args.origin, 'retry_in':0}
            write_state(STATE_DIR/'connection.json', {'pid':os.getpid(), **state})
            worker.join(timeout=1)
    except KeyboardInterrupt:
        pass
    except RuntimeError as exc:
        parser.error(str(exc))
    finally:
        if tunnel:
            tunnel.stop()
        server.shutdown()
        server.server_close()
        worker.join(timeout=3)
        write_state(STATE_DIR/'connection.json', {'pid':os.getpid(), 'state':'stopped', 'url':None})


if __name__ == "__main__":
    main()
