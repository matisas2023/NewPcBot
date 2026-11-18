import argparse
import json
import logging
import os
from pathlib import Path
import secrets

from .server import RemoteServer


def main():
    parser = argparse.ArgumentParser(description="PC Helper mobile agent (Tailscale Serve)")
    parser.add_argument("--setup", action="store_true", help="Create local access key and shared folder")
    parser.add_argument("--config", type=Path, default=Path(".pc-remote.json"))
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if args.setup:
        if args.config.exists():
            parser.error("Config already exists; keep it or rename it before generating a new key")
        config = {"token": secrets.token_urlsafe(32), "files": str(Path("remote_files").resolve())}
        with args.config.open("x", encoding="utf-8") as output:
            json.dump(config, output, indent=2)
        os.chmod(args.config, 0o600)
        Path(config["files"]).mkdir(exist_ok=True)
        print("Access key (enter on your phone; do not share):", config["token"])
        print("Shared folder:", config["files"])
        print("Run: python -m pc_remote")
        return
    if not args.config.exists():
        parser.error("Run python -m pc_remote --setup first")
    config = json.loads(args.config.read_text(encoding="utf-8"))
    token = os.environ.get("PC_REMOTE_TOKEN") or config["token"]
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    server = RemoteServer(("127.0.0.1", args.port), token, config["files"])
    print(f"PC Helper: http://127.0.0.1:{args.port}")
    print(f"For Android: tailscale serve --bg http://127.0.0.1:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
