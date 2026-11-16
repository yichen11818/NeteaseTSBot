"""Generate a single Compose project containing independent TeamSpeak bots."""
import argparse
import json
import os
from pathlib import Path
import secrets
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.multi_server_config import Deployment, public_catalog, read_deployment
from scripts.multi_server_render import render_compose, render_nginx


KEY_BYTES = 32
GENERATED_DIRECTORY = ".multi-server"
COMPOSE_FILE = "docker-compose.multi.json"


def prepare_instances(root: Path, deployment: Deployment, initialize: bool) -> None:
    paths = tuple(root / "instances" / server.id for server in deployment.servers)
    missing = tuple(path / "tsbot.env" for path in paths if not (path / "tsbot.env").is_file())
    if missing and not initialize:
        raise FileNotFoundError("Missing instance env files; use --init-env to create them: " + ", ".join(map(str, missing)))
    template = (root / "tsbot.env.example").read_text(encoding="utf-8") if missing else ""
    for path in paths:
        for folder in (path, path / "logs", path / "data"):
            folder.mkdir(parents=True, exist_ok=True)
    for path in missing:
        content = template.replace("replace_with_a_long_random_key", secrets.token_hex(KEY_BYTES))
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            os.chmod(path, 0o600)
            handle.write(content)


def write_generated(path: Path, content: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def generate(root: Path, deployment: Deployment, *, initialize: bool = False) -> None:
    prepare_instances(root, deployment, initialize)
    directory = root / GENERATED_DIRECTORY
    directory.mkdir(exist_ok=True)
    write_generated(directory / "servers.json", json.dumps(public_catalog(deployment), ensure_ascii=False, indent=2) + "\n")
    write_generated(directory / "nginx.conf", render_nginx(deployment))
    write_generated(root / COMPOSE_FILE, json.dumps(render_compose(deployment), ensure_ascii=False, indent=2) + "\n")


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=root / "servers.json", help="Server catalog (JSON)")
    parser.add_argument("--init-env", action="store_true", help="Create missing env files with unique keys; never overwrite existing files")
    args = parser.parse_args()
    try:
        deployment = read_deployment(args.config)
        generate(root, deployment, initialize=args.init_env)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Cannot generate multi-server deployment: {exc}\n")
    print(f"Generated {COMPOSE_FILE} for {len(deployment.servers)} independent servers.")
    print(f"Validate: docker compose -f {COMPOSE_FILE} config --quiet")
    print(f"Start:    docker compose -f {COMPOSE_FILE} up -d --build")
    print("After changing the server catalog, recreate the Web gateway: docker compose -f " + COMPOSE_FILE + " up -d --force-recreate web")


if __name__ == "__main__":
    main()
