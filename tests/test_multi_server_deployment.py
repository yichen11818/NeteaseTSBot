import json
from pathlib import Path
import tempfile
import unittest

from scripts.multi_server import generate
from scripts.multi_server_config import Deployment, Server, public_catalog, read_deployment
from scripts.multi_server_render import render_compose, render_nginx


ROOT = Path(__file__).resolve().parents[1]
PAIR = Deployment((Server("home", "主服务器"), Server("friends", "朋友的服务器")))


class MultiServerDeploymentTests(unittest.TestCase):
    def test_only_web_publishes_a_port_and_each_bot_has_its_own_network(self):
        compose = render_compose(PAIR)
        services = compose["services"]
        self.assertEqual(["8080:8080"], services["web"]["ports"])
        self.assertEqual(3, sum("build" in service for service in services.values()))
        for identifier in ("home", "friends"):
            with self.subTest(server=identifier):
                backend = services[f"backend-{identifier}"]
                voice = services[f"voice-{identifier}"]
                self.assertNotIn("ports", backend)
                self.assertNotIn("ports", voice)
                self.assertEqual([f"server-{identifier}"], backend["networks"])
                self.assertEqual(backend["networks"], voice["networks"])
                self.assertEqual(backend["volumes"], voice["volumes"])
                self.assertEqual(f"voice-{identifier}:50051", backend["environment"]["TSBOT_VOICE_GRPC_ADDR"])
        self.assertTrue(set(services["backend-home"]["volumes"]).isdisjoint(services["backend-friends"]["volumes"]))
        self.assertNotEqual(services["backend-home"]["env_file"], services["backend-friends"]["env_file"])
        self.assertEqual({"server-home", "server-friends"}, set(compose["networks"]))

    def test_gateway_scopes_login_cookies_and_does_not_route_unknown_servers(self):
        nginx = render_nginx(PAIR)
        for server in PAIR.servers:
            self.assertIn(f"location /api/servers/{server.id}/", nginx)
            self.assertIn(f"proxy_cookie_path / /api/servers/{server.id}/;", nginx)
            self.assertIn(f"server backend-{server.id}:8009 resolve;", nginx)
        self.assertIn("location /api/ { return 404; }", nginx)
        self.assertIn('Cache-Control "no-store"', nginx)
        services = render_compose(PAIR)["services"]
        self.assertNotEqual(services["backend-home"]["environment"]["TSBOT_SESSION_COOKIE_NAME"],
                            services["backend-friends"]["environment"]["TSBOT_SESSION_COOKIE_NAME"])

    def test_generated_catalog_contains_only_public_ids_and_labels(self):
        self.assertEqual({"servers": [{"id": "home", "name": "主服务器"},
                                      {"id": "friends", "name": "朋友的服务器"}]}, public_catalog(PAIR))

    def test_example_is_valid(self):
        self.assertEqual(PAIR, read_deployment(ROOT / "servers.example.json"))

    def test_invalid_input_is_rejected_before_generating_any_files(self):
        invalid = (
            {"servers": []}, {"servers": [{"id": "../escape", "name": "X"}]},
            {"servers": [{"id": "home", "name": "X", "password": "example"}]},
            {"servers": [{"id": "home", "name": " "}]},
            {"servers": [{"id": "a", "name": "X"}, {"id": "a", "name": "Y"}]},
            {"servers": [{"id": "a", "name": "X"}], "web_port": True},
            {"servers": [{"id": "a", "name": "X"}], "web_port": 65536},
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "servers.json"
            for config in invalid:
                with self.subTest(config=config):
                    path.write_text(json.dumps(config), encoding="utf-8")
                    with self.assertRaises(ValueError):
                        read_deployment(path)

    def test_generation_preserves_credentials_and_persistent_data(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "tsbot.env.example").write_text('TSBOT_COOKIE_KEY="replace_with_a_long_random_key"\n', encoding="utf-8")
            generate(root, PAIR, initialize=True)
            first = root / "instances/home/tsbot.env"
            second = root / "instances/friends/tsbot.env"
            original = first.read_bytes()
            self.assertNotEqual(original, second.read_bytes())
            self.assertNotIn(b"replace_with", original)
            data = root / "instances/home/data/keep.txt"
            data.write_text("keep", encoding="utf-8")
            generate(root, PAIR, initialize=True)
            self.assertEqual(original, first.read_bytes())
            self.assertEqual("keep", data.read_text(encoding="utf-8"))
            self.assertEqual(render_compose(PAIR), json.loads((root / "docker-compose.multi.json").read_text(encoding="utf-8")))
            generate(root, Deployment((Server("friends", "Renamed"),)))
            self.assertEqual(original, first.read_bytes())  # Removing a profile never deletes data.

    def test_missing_env_is_an_explicit_error_without_partial_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(FileNotFoundError):
                generate(root, PAIR)
            self.assertEqual([], list(root.iterdir()))


if __name__ == "__main__":
    unittest.main()
