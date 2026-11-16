"""Validated, non-secret configuration for one multi-server deployment."""
from dataclasses import dataclass
import json
from pathlib import Path
import re


DEFAULT_WEB_PORT = 8080
MAX_PORT = 65535
MAX_DNS_LABEL = 63
SERVICE_PREFIX = "backend-"
SERVER_ID = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")


@dataclass(frozen=True)
class Server:
    id: str
    name: str


@dataclass(frozen=True)
class Deployment:
    servers: tuple[Server, ...]
    web_port: int = DEFAULT_WEB_PORT


def read_server(value: object) -> Server:
    if not isinstance(value, dict) or set(value) != {"id", "name"}:
        raise ValueError("Each server must contain only id and name")
    identifier, name = value["id"], value["name"]
    if not isinstance(identifier, str) or not SERVER_ID.fullmatch(identifier):
        raise ValueError("Server id must use lowercase letters, digits and single hyphens; start with a letter")
    if len(SERVICE_PREFIX + identifier) > MAX_DNS_LABEL:
        raise ValueError("Server id is too long for a Docker DNS label")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Server name must be a non-empty string")
    return Server(identifier, name.strip())


def read_deployment(path: Path) -> Deployment:
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(raw, dict) or set(raw) - {"servers", "web_port"}:
        raise ValueError("Configuration accepts only servers and web_port")
    port = raw.get("web_port", DEFAULT_WEB_PORT)
    if type(port) is not int or not 1 <= port <= MAX_PORT:
        raise ValueError("web_port must be an integer between 1 and 65535")
    values = raw.get("servers")
    if not isinstance(values, list) or not values:
        raise ValueError("At least one server is required")
    servers = tuple(read_server(value) for value in values)
    if len({server.id for server in servers}) != len(servers):
        raise ValueError("Server ids must be unique")
    return Deployment(servers, port)


def public_catalog(deployment: Deployment) -> dict:
    return {"servers": [{"id": server.id, "name": server.name} for server in deployment.servers]}
