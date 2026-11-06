#!/usr/bin/env python3
"""Isolated Mihomo probes. No system proxy changes and no direct fallback."""
from __future__ import annotations

import argparse
from html.parser import HTMLParser
import copy
import ipaddress
import json
import os
import re
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit

import yaml

ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 5 * 1024 * 1024
SERVICES = {
    "google": "https://www.google.com/",
    "gemini": "https://gemini.google.com/app",
    "grok": "https://grok.com/",
    "antigravity": "https://antigravity.google/",
}
NODE_TYPES = {"ss", "ssr", "vmess", "vless", "trojan", "hysteria", "hysteria2",
              "tuic", "http", "socks5", "anytls"}
REGIONS = {
    "US": r"美国|美國|🇺🇸|United\s*States|(?<![A-Za-z])USA?(?![A-Za-z])|洛杉矶|洛杉磯|纽约|紐約|西雅图|西雅圖|硅谷|矽谷|圣何塞|聖何塞|Los\s*Angeles|New\s*York|Seattle|San\s*Jose",
    "JP": r"日本|🇯🇵|Japan|(?<![A-Za-z])JP(?![A-Za-z])|东京|東京|大阪",
    "SG": r"新加坡|狮城|獅城|🇸🇬|Singapore|(?<![A-Za-z])SG(?![A-Za-z])",
    "HK": r"香港|🇭🇰|Hong\s*Kong|(?<![A-Za-z])HK(?![A-Za-z])",
    "TW": r"台湾|台灣|🇹🇼|Taiwan|(?<![A-Za-z])TW(?![A-Za-z])",
}
CREATE_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class DetectorError(Exception):
    pass


def clean_env():
    return {k: v for k, v in os.environ.items()
            if k.lower() not in {"http_proxy", "https_proxy", "all_proxy", "no_proxy"}}


def curl_path():
    value = shutil.which("curl.exe" if os.name == "nt" else "curl")
    if not value:
        raise DetectorError("未找到 curl；请安装 curl 并加入 PATH。")
    return value


def request(url, *, proxy=None, allow_direct=False, timeout=20, subscription=False):
    """Do not expose stderr/URLs: they may contain subscription credentials."""
    if urlsplit(url).scheme not in {"http", "https"}:
        raise DetectorError("仅支持 HTTP/HTTPS 地址。")
    if not proxy and not allow_direct:
        raise DetectorError("未指定下载代理；如允许直连下载订阅，请添加 --allow-direct-download。")
    with tempfile.TemporaryDirectory(prefix="flight-http-") as folder:
        body = Path(folder) / "body"
        args = [curl_path(), "--disable", "--silent", "--show-error", "--location",
                "--max-redirs", "5", "--proto", "=http,https", "--proto-redir", "=http,https",
                "--connect-timeout", str(min(timeout, 10)), "--max-time", str(timeout),
                "--max-filesize", str(MAX_BYTES), "--output", str(body),
                "--write-out", "%{http_code}\n%{url_effective}\n%{time_total}",
                "--user-agent", "clash.meta" if subscription else "ai-flight-detector/0.1"]
        if proxy:
            if urlsplit(proxy).scheme not in {"http", "https", "socks5h"}:
                raise DetectorError("代理地址须使用 http://、https:// 或 socks5h://。")
            args += ["--proxy", proxy, "--noproxy", ""]
        else:
            args += ["--proxy", "", "--noproxy", "*"]
        args += ["--url", url]
        try:
            result = subprocess.run(args, capture_output=True, env=clean_env(),
                                    timeout=timeout + 5, creationflags=CREATE_FLAGS)
        except subprocess.TimeoutExpired:
            return {"status": 0, "error": "timeout", "body": "", "host": "", "path": ""}
        if result.returncode:
            return {"status": 0, "error": f"curl_exit_{result.returncode}",
                    "body": "", "host": "", "path": ""}
        lines = result.stdout.decode("utf-8", "replace").splitlines()
        if len(lines) != 3:
            raise DetectorError("curl 返回了无法识别的结果。")
        final = urlsplit(lines[1])
        data = body.read_bytes() if body.exists() else b""
        if len(data) > MAX_BYTES:
            raise DetectorError("响应超过 5 MiB 限制。")
        return {"status": int(lines[0]), "host": final.hostname or "",
                "path": final.path, "elapsed_ms": round(float(lines[2]) * 1000),
                "body": data.decode("utf-8-sig", "replace"), "error": ""}


def read_source(source, download_proxy=None, allow_direct=False):
    if source.startswith(("https://", "http://")):
        response = request(source, proxy=download_proxy, allow_direct=allow_direct, subscription=True)
        if response["status"] != 200:
            raise DetectorError(f"订阅下载失败：HTTP {response['status']} {response['error']}")
        return response["body"], None
    path = Path(source).expanduser().resolve()
    if path.stat().st_size > MAX_BYTES:
        raise DetectorError("配置超过 5 MiB 限制。")
    return path.read_text(encoding="utf-8-sig"), path.parent


def parse_yaml(text):
    # Subscription YAML has no reason to use anchors; refusing aliases also bounds expansion.
    try:
        for event in yaml.parse(text):
            if isinstance(event, yaml.events.AliasEvent):
                raise DetectorError("配置包含 YAML 别名；请导出不使用锚点/别名的节点列表。")
        doc = yaml.safe_load(text)
    except (yaml.YAMLError, RecursionError):
        raise DetectorError("配置不是有效的 YAML。请使用 Clash/Mihomo 格式订阅。") from None
    if not isinstance(doc, dict):
        raise DetectorError("需要 Clash/Mihomo YAML；暂不转换 Base64、URI 列表或 sing-box JSON。")
    return doc


def load_nodes(source, download_proxy=None, allow_direct=False):
    text, base = read_source(source, download_proxy, allow_direct)
    doc = parse_yaml(text)
    nodes = doc.get("proxies", [])
    if not isinstance(nodes, list):
        raise DetectorError("proxies 必须是节点列表。")
    nodes = list(nodes)
    providers = doc.get("proxy-providers", {})
    if not isinstance(providers, dict):
        raise DetectorError("proxy-providers 必须是映射。")
    for provider in providers.values():
        if not isinstance(provider, dict):
            raise DetectorError("无效的 proxy-provider。")
        # Transformations cannot silently change the meaning of the source nodes.
        unsupported = {"override", "filter", "exclude-filter", "exclude-type", "header"} & provider.keys()
        if unsupported:
            raise DetectorError("provider 含暂不支持的过滤/覆盖/请求头；请导出展开后的 proxies。")
        kind = provider.get("type")
        if kind == "inline":
            extra = provider.get("payload", [])
        elif kind in {"http", "file"}:
            if kind == "http":
                target = provider.get("url", "")
                if not isinstance(target, str) or not target.startswith(("https://", "http://")):
                    raise DetectorError("HTTP provider 缺少有效 URL。")
            else:
                if base is None:
                    raise DetectorError("远程订阅不得引用本地文件 provider。")
                target = (base / str(provider.get("path", ""))).resolve()
                if not target.is_relative_to(base):
                    raise DetectorError("文件 provider 必须位于输入配置目录内。")
                target = str(target)
            raw, _ = read_source(target, download_proxy, allow_direct)
            nested = parse_yaml(raw)
            if nested.get("proxy-providers"):
                raise DetectorError("暂不支持嵌套 provider。")
            extra = nested.get("proxies", [])
        else:
            raise DetectorError("仅支持 http/file/inline provider。")
        if not isinstance(extra, list):
            raise DetectorError("provider 中的 proxies/payload 必须是列表。")
        nodes.extend(extra)
    if not nodes:
        raise DetectorError("未找到节点；请提供含 proxies 或 proxy-providers 的 Clash/Mihomo YAML。")
    unique, seen = [], set()
    for node in nodes:
        if not isinstance(node, dict):
            raise DetectorError("节点必须是 YAML 对象。")
        fingerprint = json.dumps({k: v for k, v in node.items() if k != "name"}, sort_keys=True, default=str)
        if fingerprint not in seen:
            unique.append(node)
            seen.add(fingerprint)
    return unique


def candidate_paths(explicit=None):
    if explicit:
        yield Path(explicit).expanduser()
        return
    if os.environ.get("MIHOMO_PATH"):
        yield Path(os.environ["MIHOMO_PATH"])
    names = ("mihomo", "clash-meta", "clash-verge-mihomo")
    for name in names:
        found = shutil.which(name)
        if found:
            yield Path(found)
    for folder in (ROOT / "kernels", Path.home() / ".local/bin", Path("/opt/homebrew/bin"), Path("/usr/local/bin")):
        for name in names:
            yield folder / (name + (".exe" if os.name == "nt" else ""))
    if os.name == "nt":
        roots = [Path(os.environ.get("LOCALAPPDATA", "")) / "Programs",
                 Path(os.environ.get("PROGRAMFILES", "C:/Program Files"))]
        for root in roots:
            for app in ("Clash Verge", "Clash Verge Rev", "Clash Nyanpasu", "v2rayN"):
                folder = root / app
                if folder.is_dir():
                    yield from folder.glob("**/*mihomo*.exe")
                    yield from folder.glob("**/clash-meta.exe")
    else:
        for root in (Path("/Applications"), Path.home() / "Applications"):
            for app in ("Clash Verge.app", "Clash Nyanpasu.app"):
                folder = root / app / "Contents"
                if folder.is_dir():
                    yield from folder.glob("**/*mihomo*")


def select_nodes(nodes, *, region=None, include=None, exclude=None, names=None, limit=0):
    try:
        include_re = re.compile(include, re.I) if include else None
        exclude_re = re.compile(exclude, re.I) if exclude else None
    except re.error:
        raise DetectorError("节点名称筛选表达式无效。") from None
    selected = []
    for node in nodes:
        name = str(node.get("name", ""))
        if region and not re.search(REGIONS[region], name, re.I):
            continue
        if names and name not in names:
            continue
        if include_re and not include_re.search(name):
            continue
        if exclude_re and exclude_re.search(name):
            continue
        selected.append(node)
    if not selected:
        raise DetectorError("没有匹配筛选条件的节点；未扩大检测范围。")
    return selected[:limit] if limit else selected


def discover_kernel(explicit=None):
    seen = set()
    for candidate in candidate_paths(explicit):
        if not candidate.is_file() or str(candidate) in seen:
            continue
        seen.add(str(candidate))
        try:
            result = subprocess.run([str(candidate), "-v"], capture_output=True, timeout=5,
                                    env=clean_env(), creationflags=CREATE_FLAGS)
            version = (result.stdout + result.stderr).decode("utf-8", "replace").strip()
            if result.returncode == 0 and ("mihomo" in version.lower() or "clash meta" in version.lower()):
                return candidate.resolve(), version.splitlines()[0][:200]
        except (OSError, subprocess.TimeoutExpired):
            continue
    raise DetectorError("未找到可运行的 Mihomo/Clash.Meta；将其加入 PATH、放入项目 kernels，或指定 --kernel。")


def isolated_config(node, port, password):
    node = copy.deepcopy(node)
    if node.get("type") not in NODE_TYPES:
        raise DetectorError("unsupported_protocol")
    if not node.get("server") or not node.get("port"):
        raise DetectorError("missing_server_or_port")
    if any(key in node for key in ("dialer-proxy", "interface-name", "routing-mark", "ip-version")):
        raise DetectorError("unsupported_node_routing_override")
    def inspect(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if str(key).endswith(("-path", "-file")) or key in {"certificate", "private-key"}:
                    raise DetectorError("unsupported_external_certificate_or_file")
                if key == "skip-cert-verify" and child:
                    raise DetectorError("insecure_tls_node")
                inspect(child)
        elif isinstance(value, list):
            for child in value:
                inspect(child)
    inspect(node)
    node["name"] = "DETECT"
    return {
        "mixed-port": port, "bind-address": "127.0.0.1", "allow-lan": False,
        "authentication": [f"flight:{password}"], "skip-auth-prefixes": [],
        "mode": "rule", "log-level": "silent", "ipv6": False,
        "find-process-mode": "off", "geo-auto-update": False,
        "tun": {"enable": False}, "profile": {"store-selected": False, "store-fake-ip": False},
        "dns": {"enable": True, "ipv6": False, "enhanced-mode": "redir-host",
                "use-hosts": False, "use-system-hosts": False,
                "nameserver": ["https://1.1.1.1/dns-query#DETECT"],
                "proxy-server-nameserver": ["system"]},
        "proxies": [node], "rules": ["MATCH,DETECT"],
    }


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class KernelSession:
    def __init__(self, kernel, node, startup_timeout=15):
        self.kernel, self.node, self.startup_timeout = kernel, node, startup_timeout
        self.process = self.folder = None

    def __enter__(self):
        try:
            self.folder = tempfile.TemporaryDirectory(prefix="ai-flight-")
            directory = Path(self.folder.name)
            port, password = free_port(), secrets.token_hex(16)
            config = isolated_config(self.node, port, password)
            path = directory / "config.yaml"
            path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")
            if os.name != "nt":
                path.chmod(0o600)
            command = [str(self.kernel), "-d", str(directory), "-f", str(path)]
            checked = subprocess.run(command + ["-t"], stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL, timeout=self.startup_timeout,
                                     env=clean_env(), creationflags=CREATE_FLAGS)
            if checked.returncode:
                raise DetectorError("kernel_config_rejected")
            self.process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                            env=clean_env(), creationflags=CREATE_FLAGS)
            deadline = time.monotonic() + self.startup_timeout
            while time.monotonic() < deadline:
                if self.process.poll() is not None:
                    raise DetectorError("kernel_exited")
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                        # Per-run authentication prevents a port race from using another proxy.
                        return f"socks5h://flight:{password}@127.0.0.1:{port}"
                except OSError:
                    time.sleep(0.1)
            raise DetectorError("kernel_start_timeout")
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *_):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        if self.folder:
            self.folder.cleanup()


class PageText(HTMLParser):
    """Ignore bundled translations and templates that are not rendered page text.

    This is static HTML inspection, not a browser or a visibility guarantee.
    """
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ignored = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "template"}:
            self.ignored += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style", "template"} and self.ignored:
            self.ignored -= 1

    def handle_data(self, data):
        if not self.ignored:
            self.parts.append(data)


def classify(response, service=None):
    status = response["status"]
    body = response.get("body", "").lower()
    page = PageText()
    page.feed(body)
    text = " ".join(" ".join(page.parts).split()).replace("’", "'")
    host, path = response.get("host", ""), response.get("path", "")
    if response.get("error") or not status:
        verdict, reason = "network_error", response.get("error", "request_failed")
    elif status == 429:
        verdict, reason = "rate_limited", "HTTP 429；可能与共享出口、账号或请求频率有关"
    elif any(x in body for x in ("cf_chl_opt", "challenge-platform", "verify you are human", "just a moment...")):
        verdict, reason = "challenge", "需要浏览器验证，未证明可用或被封禁"
    elif any(x in body for x in ("sorry, you have been blocked", "you are unable to access")):
        verdict, reason = "suspected_block", "响应含访问拦截提示，无法确认是 IP 永久封禁"
    elif any(x in text for x in (
        "not available in your country", "not available in your region",
        "not available in your location", "isn't available in your country",
        "isn't available in your region", "isn't available in your location",
        "your account is not eligible", "your account is ineligible",
        "目前不支持你所在的国家", "目前不支持您所在的国家",
        "在你所在的国家/地区尚不可用", "在您所在的国家/地区尚不可用",
        "你的账号不符合", "您的账号不符合",
    )):
        verdict, reason = "restricted", "静态页面包含地区或账号资格受限提示；需登录确认具体原因"
    elif status in (401, 403):
        verdict, reason = "restricted", f"HTTP {status}；需区分认证、地区、WAF 与出口限制"
    elif "/sorry" in path or "captcha" in path:
        verdict, reason = "challenge", "重定向至验证或异常流量页面"
    elif host == "accounts.google.com" or "/login" in path or "/signin" in path:
        verdict, reason = "auth_required", "需要登录，尚未验证实际服务功能"
    elif 200 <= status < 300 and service == "antigravity":
        verdict, reason = "unknown", "Antigravity 公开页面可达；尚未验证客户端登录、账号资格或模型请求"
    elif 200 <= status < 300:
        verdict, reason = "reachable", "网页可达；不代表登录、模型调用或账号资格通过"
    else:
        verdict, reason = "unknown", f"HTTP {status}；不足以判断"
    if host.endswith("google.com.hk"):
        reason += "；观察到 google.com.hk 跳转，仅记录，不作为封禁证据"
    return {"verdict": verdict, "reason": reason, "http_status": status,
            "final_host": host, "elapsed_ms": response.get("elapsed_ms"),
            "validation_level": "unauthenticated_http", "functional_verified": False}


def probe_node(kernel, node, services, timeout):
    result = {"name": str(node.get("name", "unnamed")), "protocol": node.get("type"),
              "exit_ip": None, "country": None, "services": {}, "error": None}
    try:
        with KernelSession(kernel, node) as proxy:
            trace = request("https://www.cloudflare.com/cdn-cgi/trace", proxy=proxy, timeout=timeout)
            values = dict(line.split("=", 1) for line in trace.get("body", "").splitlines() if "=" in line)
            try:
                if trace["status"] != 200 or trace["host"] != "www.cloudflare.com":
                    raise ValueError()
                result["exit_ip"] = str(ipaddress.ip_address(values.get("ip", "")))
                result["country"] = values.get("loc")
            except ValueError:
                result["error"] = "exit_probe_failed"
            for service in services:
                result["services"][service] = classify(request(SERVICES[service], proxy=proxy, timeout=timeout), service)
    except DetectorError as exc:
        result["error"] = str(exc)
    except subprocess.TimeoutExpired:
        result["error"] = "kernel_validation_timeout"
    except OSError:
        result["error"] = "local_io_or_process_error"
    return result


def write_reports(report, destination):
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / "results.json"
    temporary = destination / "results.json.tmp"
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(target)
    def cell(value):
        return str(value or "—").replace("|", "\\|").replace("\n", " ").replace("\r", " ")
    rows = ["# AI 节点检测报告", "", f"状态：{report['state']}；时间：{report['created_at']}", "",
            "网页可达不等于账号或模型可用；此报告不查询平台内部黑名单。", "",
            "验证层级：未登录 HTTP/静态页面；未执行 JavaScript、登录或模型请求。Antigravity 仅检测公开站点。", "",
            "| 节点 | 出口 IP | 地区 | 检测结果 | 错误 |", "| --- | --- | --- | --- | --- |"]
    for item in report["nodes"]:
        summary = "; ".join(f"{key}: {value['verdict']}" for key, value in item["services"].items())
        rows.append("| " + " | ".join(map(cell, [item["name"], item["exit_ip"], item["country"], summary, item["error"]])) + " |")
    (destination / "report.md").write_text("\n".join(rows) + "\n", encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Windows/macOS 节点检测：Clash YAML → 独立 Mihomo → AI 网页探测")
    parser.add_argument("--input", help="本地 YAML 或订阅 URL")
    parser.add_argument("--input-env", help="保存订阅 URL 的环境变量名，避免 URL 出现在命令行参数中")
    parser.add_argument("--kernel", help="Mihomo 可执行文件路径")
    parser.add_argument("--discover", action="store_true", help="仅定位内核并打印版本")
    parser.add_argument("--inspect", action="store_true", help="只解析输入和检查节点，不启动内核")
    parser.add_argument("--download-proxy", help="仅用于下载订阅/provider 的代理地址")
    parser.add_argument("--allow-direct-download", action="store_true")
    parser.add_argument("--services", nargs="+", choices=SERVICES, default=["gemini", "grok"])
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--region", type=str.upper, choices=REGIONS, help="按节点名称中的地区标记预筛选；不是实际出口国家保证")
    parser.add_argument("--include", help="节点名称包含此正则表达式（忽略大小写）")
    parser.add_argument("--exclude", help="排除名称匹配此正则的节点")
    parser.add_argument("--node", action="append", help="仅检测指定完整节点名称，可重复")
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--output", type=Path, default=ROOT / "reports" / datetime.now().strftime("%Y%m%d-%H%M%S"))
    args = parser.parse_args(argv)
    if args.timeout < 1 or args.limit < 0:
        parser.error("timeout 必须为正数，limit 不能为负数")
    try:
        if args.discover:
            kernel, version = discover_kernel(args.kernel)
            print(json.dumps({"path": str(kernel), "version": version}, ensure_ascii=False))
            return 0
        if args.input and args.input_env:
            raise DetectorError("--input 与 --input-env 只能指定一个。")
        source = os.environ.get(args.input_env, "") if args.input_env else args.input
        if not source:
            raise DetectorError("请指定 --input 或 --input-env。")
        nodes = load_nodes(source, args.download_proxy, args.allow_direct_download)
        nodes = select_nodes(nodes, region=args.region, include=args.include, exclude=args.exclude,
                             names=args.node, limit=args.limit)
        if args.inspect:
            summary = []
            for node in nodes:
                try:
                    isolated_config(node, 12345, "inspection")
                    status = "ready_for_kernel_validation"
                except DetectorError as exc:
                    status = str(exc)
                summary.append({"name": node.get("name"), "type": node.get("type"), "status": status})
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            return 0
        kernel, version = discover_kernel(args.kernel)
        report = {"schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
                  "kernel_version": version, "state": "running", "total": len(nodes), "nodes": []}
        try:
            for index, node in enumerate(nodes, 1):
                result = probe_node(kernel, node, args.services, args.timeout)
                report["nodes"].append(result)
                write_reports(report, args.output)
                print(f"[{index}/{len(nodes)}] " + json.dumps({"name": result["name"], "error": result["error"]}, ensure_ascii=False), flush=True)
            report["state"] = "complete"
        except KeyboardInterrupt:
            report["state"] = "cancelled"
        finally:
            write_reports(report, args.output)
        print(f"Report: {args.output.resolve()}")
        return 130 if report["state"] == "cancelled" else 0
    except (DetectorError, OSError) as exc:
        # OS exception strings may contain sensitive file names or source URLs.
        print(str(exc) if isinstance(exc, DetectorError) else "本地文件或程序访问失败。", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
