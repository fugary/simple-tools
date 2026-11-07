#!/usr/bin/env python3
"""Antigravity CLI generation checks; never exports login tokens or raw logs."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import subprocess
import tempfile
import time

import detector as d

API_HOSTS = {'aicode.googleapis.com', 'daily-cloudcode-pa.googleapis.com', 'cloudcode-pa.googleapis.com'}


def route_hosts(log):
    # Error/dial attempt lines are not routing evidence. Mihomo info TCP routing
    # lines indicate selection of DETECT, not Google's perception of the exit IP.
    return sorted({host for line in log.splitlines()
                   if '[TCP]' in line and re.search(r'\busing\b.*\bDETECT\b', line)
                   and 'level=warning' not in line and 'level=error' not in line
                   for host in re.findall(r'--> ([a-zA-Z0-9.-]+):443\b', line)
                   if host in API_HOSTS})


def run_cli(command, env, timeout, cwd=None):
    options = {'start_new_session': True} if os.name != 'nt' else {
        'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP | d.CREATE_FLAGS}
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               env=env, cwd=cwd, **options)
    try:
        stdout, stderr = process.communicate(timeout=timeout)
        return process.returncode, stdout.decode('utf-8', 'replace'), stderr.decode('utf-8', 'replace')
    finally:
        # Also stop CLI-created language servers, including after timeout/interrupt.
        if os.name != 'nt':
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        elif process.poll() is None:
            subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if process.poll() is None:
            process.kill()
        process.communicate()


def classify(code, stdout, stderr, expected, hosts):
    generated = code == 0 and stdout.strip() == expected
    text = (stdout + '\n' + stderr).lower()
    if generated:
        reason = 'passed' if hosts else 'route_unconfirmed'
    elif 'user location is not supported' in text:
        reason = 'location_restricted'
    elif '429' in text or 'resource_exhausted' in text:
        reason = 'rate_limited'
    elif 'not logged' in text or 'not authenticated' in text or 'unauthenticated' in text:
        reason = 'authentication_required'
    else:
        reason = 'generation_failed'
    details = {}
    for line in (stdout + '\n' + stderr).splitlines():
        if line.startswith('AGY_ERROR: '):
            try:
                error = json.loads(line[len('AGY_ERROR: '):])
                if isinstance(error.get('error_code'), int):
                    details['http_status'] = error['error_code']
                identifier = error.get('error_id', '')
                if isinstance(identifier, str) and re.fullmatch(r'[a-fA-F0-9-]{1,80}', identifier):
                    details['error_id'] = identifier
            except (ValueError, TypeError, AttributeError):
                pass
    return {**details, 'passed': generated and bool(hosts), 'generation_verified': generated,
            'reason': reason, 'route_observed': bool(hosts), 'api_hosts': hosts,
            'returncode': code}


def probe(kernel, node, cli, model, timeout):
    start = time.monotonic()
    result = {'name': str(node.get('name', 'unnamed')), 'protocol': node.get('type'),
              'model': model, 'passed': False, 'generation_verified': False,
              'route_observed': False, 'api_hosts': [], 'exit_ip': None, 'country': None,
              'validation_level': 'antigravity_cli_generation', 'reason': None,
              'checked_at': datetime.now(timezone.utc).isoformat()}
    try:
        session = d.KernelSession(kernel, node, capture_route=True)
        with session as socks:
            trace = d.request('https://www.cloudflare.com/cdn-cgi/trace', proxy=socks, timeout=15)
            values = dict(line.split('=', 1) for line in trace.get('body', '').splitlines() if '=' in line)
            if trace['status'] == 200 and trace['host'] == 'www.cloudflare.com':
                try:
                    result['exit_ip'] = str(ipaddress.ip_address(values.get('ip', '')))
                    result['country'] = values.get('loc')
                except ValueError:
                    pass
            result['exit_probe_verified'] = result['exit_ip'] is not None
            env = d.clean_env()
            # Explicit authenticated mixed-port proxy; no system settings changed.
            proxy = socks.replace('socks5h://', 'http://', 1)
            env.update({key: proxy for key in ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY',
                                              'http_proxy', 'https_proxy', 'all_proxy')})
            env['NO_PROXY'] = env['no_proxy'] = 'localhost,127.0.0.1,::1'
            with tempfile.TemporaryDirectory(prefix='flight-cli-') as folder:
                expected = 'FLIGHT_OK_' + secrets.token_hex(8)
                command = [cli, '--model', model, '--disable-slash-commands',
                           '--print-timeout', f'{timeout}s', '--log-file', str(Path(folder) / 'cli.log'),
                           '--print', f'Reply with exactly {expected}. Do not use tools, read files, or change anything.']
                # Empty working directory avoids supplying project contents.
                previous = time.monotonic()
                command_result = run_cli(command, env, timeout + 10, cwd=folder)
                result['generation_elapsed_ms'] = round((time.monotonic() - previous) * 1000)
                hosts = route_hosts(session.route_log.read_text(encoding='utf-8', errors='replace'))
                result.update(classify(*command_result, expected, hosts))
    except subprocess.TimeoutExpired:
        result['reason'] = 'timeout'
    except d.DetectorError as exc:
        result['reason'] = str(exc)
    except OSError:
        result['reason'] = 'local_io_or_process_error'
    result['elapsed_ms'] = round((time.monotonic() - start) * 1000)
    return result


def write_reports(report, destination):
    destination.mkdir(parents=True, exist_ok=True)
    def save(name, data):
        temporary = destination / (name + '.tmp')
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        temporary.replace(destination / name)
    save('results.json', report)
    passed = [node for node in report['nodes'] if node['passed']]
    save('passed.json', passed)
    def cell(value):
        return str(value if value is not None else '—').replace('|', '\\|').replace('\n', ' ').replace('\r', ' ')
    rows = ['# Antigravity 实际生成验证', '',
            f"状态：{report['state']}；时间：{report['created_at']}；完成：{len(report['nodes'])}/{report['total']}；通过：{len(passed)}", '',
            '现有 CLI 登录、指定模型、单次生成；不代表 IDE 会话或独立 Gemini API Key 可用。',
            '路径证据是独立 Mihomo 的 API 连接路由记录；不证明所有流量无旁路，也不代表 Google 认定的出口地区。',
            '出口地区由 Cloudflare 查询，与 Google 地区识别可能不同。原始 CLI 输出、认证信息及内核日志不写入报告。', '',
            '## 通过的节点（完整名称）', '']
    rows += [f"- {cell(n['name'])}" for n in passed] or ['无。']
    rows += ['', '## 全部结果', '', '| 节点全名 | 协议 | 模型 | 出口 IP | 地区 | 生成成功 | API 路由证据 | 判定 | HTTP / 错误 ID | 生成耗时 ms | 总耗时 ms |',
             '| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |']
    for n in report['nodes']:
        rows.append('| ' + ' | '.join(cell(x) for x in [n['name'], n['protocol'], n['model'], n['exit_ip'], n['country'],
                    n['generation_verified'], ', '.join(n['api_hosts']), n['reason'],
                    str(n.get('http_status', '—')) + ' / ' + n.get('error_id', '—'),
                    n.get('generation_elapsed_ms'), n['elapsed_ms']]) + ' |')
    (destination / 'report.md').write_text('\n'.join(rows) + '\n', encoding='utf-8')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--input')
    source.add_argument('--input-env')
    parser.add_argument('--kernel')
    parser.add_argument('--cli', help='已安装并登录的 agy 路径；不自动获取账号凭据')
    parser.add_argument('--model', required=True, help='先用 agy models 查询，不固定过时模型')
    parser.add_argument('--region', choices=d.REGIONS, type=str.upper)
    parser.add_argument('--include')
    parser.add_argument('--exclude')
    parser.add_argument('--node', action='append')
    parser.add_argument('--limit', type=int, default=0)
    parser.add_argument('--workers', type=int, default=1)
    parser.add_argument('--timeout', type=int, default=60)
    parser.add_argument('--download-proxy')
    parser.add_argument('--allow-direct-download', action='store_true')
    parser.add_argument('--output', type=Path, default=d.ROOT / 'reports' / datetime.now().strftime('%Y%m%d-%H%M%S-functional'))
    args = parser.parse_args(argv)
    if args.limit < 0 or args.timeout < 1 or not 1 <= args.workers <= 4:
        parser.error('limit >= 0，timeout > 0，workers 为 1..4')
    try:
        cli = args.cli or shutil.which('agy')
        if not cli:
            candidate = Path.home() / '.gemini' / 'bin' / ('agy.exe' if os.name == 'nt' else 'agy')
            cli = str(candidate) if candidate.is_file() else None
        if not cli:
            raise d.DetectorError('未找到 Antigravity CLI；请提供 --cli，不会读取或导出账号令牌。')
        source = os.environ.get(args.input_env, '') if args.input_env else args.input
        if not source:
            raise d.DetectorError('订阅环境变量为空。')
        nodes = d.select_nodes(d.load_nodes(source, args.download_proxy, args.allow_direct_download),
                               region=args.region, include=args.include, exclude=args.exclude,
                               names=args.node, limit=args.limit)
        kernel, version = d.discover_kernel(args.kernel)
        report = {'schema_version': 2, 'state': 'running', 'created_at': datetime.now(timezone.utc).isoformat(),
                  'model': args.model, 'kernel_version': version, 'total': len(nodes), 'nodes': []}
        pool = ThreadPoolExecutor(max_workers=args.workers)
        try:
            futures = [pool.submit(probe, kernel, node, cli, args.model, args.timeout) for node in nodes]
            for future in as_completed(futures):
                result = future.result()
                report['nodes'].append(result)
                write_reports(report, args.output)
                print(json.dumps({'completed': len(report['nodes']), 'total': len(nodes),
                                  'name': result['name'], 'passed': result['passed'], 'reason': result['reason']}, ensure_ascii=False), flush=True)
            report['state'] = 'complete'
        except KeyboardInterrupt:
            report['state'] = 'cancelled'
        finally:
            pool.shutdown(wait=True, cancel_futures=True)
            write_reports(report, args.output)
        return 130 if report['state'] == 'cancelled' else 0
    except (d.DetectorError, OSError):
        print('输入、CLI 或内核无法使用；请检查配置，未输出敏感原始错误。', file=__import__('sys').stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
