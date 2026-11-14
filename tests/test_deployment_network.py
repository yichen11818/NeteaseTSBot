from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
BASE_COMPOSE_FILES = (
    "docker-compose.yml", "docker-compose.prebuilt.yml", "docker-compose.portable.yml",
)


class DeploymentNetworkTests(unittest.TestCase):
    def test_default_deployments_keep_voice_internal_and_backend_connected(self):
        for name in BASE_COMPOSE_FILES:
            with self.subTest(compose=name):
                services = yaml.safe_load((ROOT / name).read_text(encoding="utf-8"))["services"]
                self.assertNotIn("ports", services["voice-service"])
                self.assertNotIn("network_mode", services["voice-service"])
                self.assertEqual("voice-service:50051",
                    services["backend"]["environment"]["TSBOT_VOICE_GRPC_ADDR"])

    def test_opt_in_debugging_only_binds_loopback(self):
        config = yaml.safe_load((ROOT / "docker-compose.voice-debug.yml").read_text(encoding="utf-8"))
        self.assertEqual(["127.0.0.1:50051:50051"], config["services"]["voice-service"]["ports"])
