import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("detector", ROOT / "scripts/detector.py")
d = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(d)
NODE = {"name": "test", "type": "socks5", "server": "192.0.2.1", "port": 1080, "password": "secret"}


class DetectorTests(unittest.TestCase):
    def test_config_has_single_node_no_fallback_and_remote_dns(self):
        config = d.isolated_config(NODE, 12345, "token")
        self.assertEqual(config["rules"], ["MATCH,DETECT"])
        self.assertEqual(len(config["proxies"]), 1)
        self.assertEqual(config["authentication"], ["flight:token"])
        self.assertEqual(config["dns"]["nameserver"], ["https://1.1.1.1/dns-query#DETECT"])
        self.assertFalse(config["tun"]["enable"])
        self.assertNotIn("external-controller", config)
        self.assertEqual(NODE["name"], "test")

    def test_direct_and_routing_override_rejected(self):
        for extra in ({"type": "direct"}, {"dialer-proxy": "DIRECT"}, {"skip-cert-verify": True},
                      {"tls": {"certificate-path": "private.txt"}}):
            with self.subTest(extra=extra), self.assertRaises(d.DetectorError):
                d.isolated_config({**NODE, **extra}, 12345, "token")

    def test_provider_and_dedup(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            (base / "nodes.yaml").write_text(d.yaml.safe_dump({"proxies": [NODE]}), encoding="utf-8")
            (base / "config.yaml").write_text(d.yaml.safe_dump({"proxies": [{**NODE, "name": "alias"}],
                "proxy-providers": {"a": {"type": "file", "path": "nodes.yaml"}}}), encoding="utf-8")
            self.assertEqual(len(d.load_nodes(str(base / "config.yaml"))), 1)

    def test_provider_cannot_escape_or_load_local_from_remote(self):
        doc = d.yaml.safe_dump({"proxy-providers": {"a": {"type": "file", "path": "../secret.yaml"}}})
        for base in (None, Path(tempfile.gettempdir()) / "scope"):
            with patch.object(d, "read_source", return_value=(doc, base)), self.assertRaises(d.DetectorError):
                d.load_nodes("source")

    def test_provider_does_not_silently_ignore_overrides(self):
        doc = d.yaml.safe_dump({"proxy-providers": {"a": {"type": "inline", "payload": [NODE], "override": {"skip-cert-verify": True}}}})
        with patch.object(d, "read_source", return_value=(doc, None)), self.assertRaises(d.DetectorError):
            d.load_nodes("source")

    def test_yaml_alias_and_uri_inputs_fail_cleanly(self):
        for value in ("proxies: &x [*x]", "dmxlc3M6Ly90ZXN0", "vless://private-value"):
            with self.subTest(value=value), self.assertRaises(d.DetectorError):
                d.parse_yaml(value)

    def test_classifications_do_not_claim_blacklist(self):
        for status, body, host, expected in [
            (200, "hello", "www.google.com.hk", "reachable"),
            (403, "Just a moment... cf_chl_opt", "grok.com", "challenge"),
            (403, "Sorry, you have been blocked", "grok.com", "suspected_block"),
            (403, "", "grok.com", "restricted"),
            (429, "", "grok.com", "rate_limited"),
            (200, "", "accounts.google.com", "auth_required"),
            (503, "", "grok.com", "unknown"),
        ]:
            with self.subTest(status=status, expected=expected):
                result = d.classify({"status": status, "body": body, "host": host, "path": "/"})
                self.assertEqual(result["verdict"], expected)

    def test_clean_environment(self):
        with patch.dict(os.environ, {"ALL_PROXY": "secret", "no_proxy": "*", "HTTP_PROXY": "secret"}):
            self.assertFalse({k.lower() for k in d.clean_env()} & {"all_proxy", "no_proxy", "http_proxy"})

    def test_http_200_restriction_and_localized_html(self):
        for body in ("<h1>Gemini isn't available in your country</h1>",
                     "<p>Your account is not eligible</p>",
                     "<p>在您所在的国家/地区尚不可用</p>",
                     "<p>Not available in <b>your region</b></p>"):
            with self.subTest(body=body):
                result = d.classify({"status": 200, "body": body}, "gemini")
                self.assertEqual(result["verdict"], "restricted")
                self.assertFalse(result["functional_verified"])

    def test_translation_bundle_is_not_restriction_evidence(self):
        body = '<script>{"error":"not available in your country"}</script><p>Welcome</p>'
        result = d.classify({"status": 200, "body": body}, "gemini")
        self.assertEqual(result["verdict"], "reachable")

    def test_antigravity_landing_page_never_proves_functionality(self):
        self.assertIn("antigravity", d.SERVICES)
        result = d.classify({"status": 200, "body": "Welcome"}, "antigravity")
        self.assertEqual(result["verdict"], "unknown")
        self.assertEqual(result["validation_level"], "unauthenticated_http")
        self.assertFalse(result["functional_verified"])

    def test_download_requires_explicit_route(self):
        with self.assertRaises(d.DetectorError):
            d.request("https://example.com/sub?token=secret")

    def test_kernel_start_failure_cleans_temp(self):
        paths = []
        def validate(command, **kwargs):
            paths.append(Path(command[command.index("-d") + 1]))
            return Mock(returncode=1)
        with patch.object(d.subprocess, "run", side_effect=validate), self.assertRaises(d.DetectorError):
            with d.KernelSession("dummy", NODE):
                self.fail("must not start")
        self.assertTrue(paths)
        self.assertFalse(paths[0].exists())

    def test_kernel_session_kills_owned_process_on_interrupt(self):
        process = Mock()
        process.poll.return_value = None
        process.wait.side_effect = [subprocess.TimeoutExpired("dummy", 5), 0]
        with patch.object(d.subprocess, "run", return_value=Mock(returncode=0)), \
             patch.object(d.subprocess, "Popen", return_value=process), \
             patch.object(d.socket, "create_connection", return_value=socket.socket()):
            session = d.KernelSession("dummy", NODE)
            with self.assertRaises(KeyboardInterrupt):
                with session as proxy:
                    self.assertTrue(proxy.startswith("socks5h://flight:"))
                    raise KeyboardInterrupt()
            self.assertFalse(Path(session.folder.name).exists())
        process.terminate.assert_called_once()
        process.kill.assert_called_once()

    def test_report_has_no_node_password_or_source(self):
        with tempfile.TemporaryDirectory() as folder:
            result = {"name": "node", "protocol": "ss", "exit_ip": None, "country": None,
                      "services": {"grok": d.classify({"status": 403, "body": "private-body", "host": "grok.com"})}, "error": None}
            d.write_reports({"created_at": "now", "state": "complete", "nodes": [result]}, Path(folder))
            text = (Path(folder) / "results.json").read_text(encoding="utf-8")
            self.assertNotIn("private-body", text)
            self.assertEqual(json.loads(text)["state"], "complete")


@unittest.skipUnless(d.shutil.which("curl.exe" if os.name == "nt" else "curl"), "curl required")
class TransportTests(unittest.TestCase):
    def test_closed_proxy_never_reaches_target_despite_no_proxy(self):
        hits = []
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                hits.append(self.path)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"proxies: []")
            def log_message(self, *_):
                pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            url = f"http://127.0.0.1:{server.server_port}/"
            closed_port = d.free_port()
            with patch.dict(os.environ, {"NO_PROXY": "*", "ALL_PROXY": "http://127.0.0.1:1"}):
                failed = d.request(url, proxy=f"socks5h://127.0.0.1:{closed_port}", timeout=2)
                self.assertEqual(failed["status"], 0)
                self.assertEqual(hits, [])
                success = d.request(url, allow_direct=True, timeout=2)
                self.assertEqual(success["status"], 200)
                self.assertEqual(hits, ["/"])
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=2)

    def test_socks_transmits_hostname_not_local_dns(self):
        # A local SOCKS stub receives the unresolvable hostname, then refuses.
        received = []
        errors = []
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        listener.settimeout(5)
        def exact(conn, count):
            data = b""
            while len(data) < count:
                part = conn.recv(count - len(data))
                if not part:
                    raise RuntimeError("unexpected EOF")
                data += part
            return data
        def handle():
            try:
                conn, _ = listener.accept()
                with conn:
                    conn.settimeout(5)
                    hello = exact(conn, 2)
                    exact(conn, hello[1])
                    conn.sendall(b"\x05\x00")
                    header = exact(conn, 4)
                    received.append(header[3])
                    if header[3] == 3:
                        size = exact(conn, 1)[0]
                        received.append(exact(conn, size).decode())
                    exact(conn, 2)
                    conn.sendall(b"\x05\x05\x00\x01\x00\x00\x00\x00\x00\x00")
            except Exception as exc:
                errors.append(type(exc).__name__)
        worker = threading.Thread(target=handle, daemon=True)
        worker.start()
        try:
            response = d.request("https://flight-detector-test.invalid/", proxy=f"socks5h://127.0.0.1:{listener.getsockname()[1]}", timeout=3)
            worker.join(timeout=5)
            self.assertEqual(errors, [])
            self.assertEqual(received, [3, "flight-detector-test.invalid"])
            self.assertEqual(response["status"], 0)
        finally:
            listener.close()


@unittest.skipUnless(os.environ.get("MIHOMO_TEST_PATH"), "set MIHOMO_TEST_PATH for real-core integration")
class RealKernelTests(unittest.TestCase):
    def test_real_kernel_routes_to_node_and_cleans_up(self):
        upstream = socket.socket()
        upstream.bind(("127.0.0.1", 0))
        upstream.listen(1)
        upstream.settimeout(15)
        received, errors = [], []
        def exact(conn, size):
            value = b""
            while len(value) < size:
                part = conn.recv(size - len(value))
                if not part:
                    raise RuntimeError("EOF")
                value += part
            return value
        def serve():
            try:
                conn, _ = upstream.accept()
                with conn:
                    conn.settimeout(10)
                    hello = exact(conn, 2)
                    exact(conn, hello[1])
                    conn.sendall(b"\x05\x00")
                    header = exact(conn, 4)
                    if header[3] == 1:
                        received.append(socket.inet_ntoa(exact(conn, 4)))
                    elif header[3] == 3:
                        received.append(exact(conn, exact(conn, 1)[0]).decode())
                    else:
                        raise RuntimeError("unexpected address type")
                    exact(conn, 2)
                    conn.sendall(b"\x05\x00\x00\x01\x7f\x00\x00\x01\x00\x50")
                    request = b""
                    while b"\r\n\r\n" not in request:
                        request += exact(conn, 1)
                    payload = b"through-selected-node"
                    conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: " + str(len(payload)).encode() + b"\r\nConnection: close\r\n\r\n" + payload)
            except Exception as exc:
                errors.append(type(exc).__name__)
        worker = threading.Thread(target=serve, daemon=True)
        worker.start()
        kernel, version = d.discover_kernel(os.environ["MIHOMO_TEST_PATH"])
        node = {"name": "local-fixture", "type": "socks5", "server": "127.0.0.1", "port": upstream.getsockname()[1]}
        session = d.KernelSession(kernel, node)
        try:
            with session as proxy:
                response = d.request("http://198.51.100.2/", proxy=proxy, timeout=5)
                self.assertEqual(response["status"], 200, response)
                self.assertEqual(response["body"], "through-selected-node")
            worker.join(timeout=5)
            self.assertEqual(received, ["198.51.100.2"])
            self.assertEqual(errors, [])
            self.assertIsNotNone(session.process.poll())
            self.assertFalse(Path(session.folder.name).exists())
        finally:
            upstream.close()


if __name__ == "__main__":
    unittest.main()
