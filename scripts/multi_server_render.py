"""Render isolated services and a single Web gateway. No credentials in output."""
from .multi_server_config import Deployment, Server


BACKEND_PORT = 8009
VOICE_PORT = 50051
WEB_PORT = 8080
DOCKER_DNS = "127.0.0.11"
DNS_TTL_SECONDS = 10
UPSTREAM_ZONE_SIZE = "64k"
UPLOAD_LIMIT = "6m"  # Includes the existing 5 MiB managed-asset limit.
LOG_OPTIONS = {"max-size": "10m", "max-file": "3"}


def instance_service(server: Server, role: str, *, build: bool) -> dict:
    image_role = "voice-service" if role == "voice" else role
    return {
        "image": f"tsbot-multi-{image_role}:local",
        **({"build": {"context": ".", "dockerfile": f"Dockerfile.{image_role}"}} if build else {}),
        "pull_policy": "never",
        "env_file": [f"./instances/{server.id}/tsbot.env"],
        "networks": [f"server-{server.id}"],
        "restart": "unless-stopped",
        "logging": {"driver": "json-file", "options": LOG_OPTIONS},
        "volumes": [
            f"./instances/{server.id}/logs:/app/logs",
            f"./instances/{server.id}/data:/app/data",
            f"voicetmp-{server.id}:/app/tmp",
        ],
    }


def instance_services(server: Server, *, build: bool) -> dict:
    common_env = {
        "TSBOT_VOICE_CONFIG_FILE": "/app/logs/voice-service.json",
        "TSBOT_VOICE_STATE_FILE": "/app/logs/voice_state.json",
        "TSBOT_TS3_IDENTITY_FILE": "/app/logs/identity.json",
    }
    backend_env = {
        **common_env,
        "TSBOT_HOST": "0.0.0.0", "TSBOT_PORT": str(BACKEND_PORT),
        "TSBOT_VOICE_GRPC_ADDR": f"voice-{server.id}:{VOICE_PORT}",
        "DATABASE_URL": "sqlite:////app/data/tsbot.db",
        "TSBOT_ASSET_DIR": "/app/data/uploads",
        "TSBOT_LEVELS_DB": "/app/data/levels.db",
        "TSBOT_LOG_FILE": "/app/logs/backend.log",
        "TSBOT_INITIAL_PASSWORD_FILE": "/app/logs/initial-admin-password.txt",
        "TSBOT_SESSION_COOKIE_NAME": f"tsbot_admin_{server.id}",
    }
    return {
        f"backend-{server.id}": {
            **instance_service(server, "backend", build=build), "environment": backend_env,
            "healthcheck": {
                "test": [
                    "CMD",
                    "python",
                    "-c",
                    f"import socket; socket.create_connection(('127.0.0.1', {BACKEND_PORT}), 2).close()",
                ],
                "interval": "15s",
                "timeout": "5s",
                "retries": 10,
                "start_period": "30s",
            },
        },
        f"voice-{server.id}": {
            **instance_service(server, "voice", build=build),
            "environment": common_env,
            "healthcheck": {
                "test": ["CMD-SHELL", f"timeout 2 bash -c '</dev/tcp/127.0.0.1/{VOICE_PORT}'"],
                "interval": "15s",
                "timeout": "5s",
                "retries": 10,
                "start_period": "30s",
            },
        },
    }


def render_compose(deployment: Deployment) -> dict:
    instances = {key: value for index, server in enumerate(deployment.servers)
                 for key, value in instance_services(server, build=index == 0).items()}
    web = {
        "image": "tsbot-multi-web:local",
        "build": {"context": ".", "dockerfile": "Dockerfile.web"},
        "ports": [f"{deployment.web_port}:{WEB_PORT}"],
        # Dynamic DNS lets the shared gateway start even when an instance is down.
        "networks": [f"server-{server.id}" for server in deployment.servers],
        # Mount the directory so regenerated files remain visible after atomic replacement.
        "volumes": ["./.multi-server:/etc/tsbot-multi:ro"],
        "command": ["nginx", "-c", "/etc/tsbot-multi/nginx.conf", "-g", "daemon off;"],
        "restart": "unless-stopped",
        "healthcheck": {
            "test": ["CMD-SHELL", f"wget -q -O /dev/null http://127.0.0.1:{WEB_PORT}/"],
            "interval": "20s",
            "timeout": "5s",
            "retries": 5,
            "start_period": "20s",
        },
        "logging": {"driver": "json-file", "options": LOG_OPTIONS},
    }
    return {
        "name": "tsbot-multi",
        "services": {**instances, "web": web},
        "volumes": {f"voicetmp-{server.id}": {} for server in deployment.servers},
        "networks": {f"server-{server.id}": {} for server in deployment.servers},
    }


def upstream(server: Server) -> str:
    name = server.id.replace("-", "_")
    return f"""    upstream backend_{name} {{
        zone backend_{name} {UPSTREAM_ZONE_SIZE};
        server backend-{server.id}:{BACKEND_PORT} resolve;
    }}"""


def proxy_location(server: Server) -> str:
    name = server.id.replace("-", "_")
    return f"""        location /api/servers/{server.id}/ {{
            proxy_pass http://backend_{name}/;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_cookie_path / /api/servers/{server.id}/;
        }}"""


def render_nginx(deployment: Deployment) -> str:
    upstreams = "\n".join(upstream(server) for server in deployment.servers)
    locations = "\n".join(proxy_location(server) for server in deployment.servers)
    return f"""# Generated by scripts/multi_server.py. Edit servers.json, then regenerate.
events {{}}
error_log /dev/stderr warn;
pid /var/run/nginx.pid;
http {{
    access_log /dev/stdout;
    include /etc/nginx/mime.types;
    default_type application/octet-stream;
    resolver {DOCKER_DNS} valid={DNS_TTL_SECONDS}s ipv6=off;
{upstreams}
    server {{
        listen {WEB_PORT};
        server_name _;
        root /usr/share/nginx/html;
        index index.html;
        client_max_body_size {UPLOAD_LIMIT};
        location = /servers.json {{
            alias /etc/tsbot-multi/servers.json;
            add_header Cache-Control "no-store";
        }}
{locations}
        location /api/ {{ return 404; }}
        location / {{ try_files $uri $uri/ /index.html; }}
    }}
}}
"""
