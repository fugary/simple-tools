import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import functional as f


class FunctionalTests(unittest.TestCase):
    def test_success_requires_exact_challenge_and_route(self):
        for code, stdout, hosts, passed in [(0, 'CHECK\n', ['aicode.googleapis.com'], True),
                                            (0, 'CHECK', [], False),
                                            (3, 'CHECK', ['aicode.googleapis.com'], False),
                                            (0, 'OK', ['aicode.googleapis.com'], False)]:
            self.assertEqual(f.classify(code, stdout, '', 'CHECK', hosts)['passed'], passed)

    def test_route_attempts_and_non_model_hosts_do_not_count(self):
        self.assertEqual(f.route_hosts('level=warning [TCP] --> aicode.googleapis.com:443 using DETECT'), [])
        self.assertEqual(f.route_hosts('[TCP] --> www.googleapis.com:443 using DETECT'), [])
        self.assertEqual(f.route_hosts('[TCP] --> aicode.googleapis.com:443 using DIRECT'), [])
        self.assertEqual(f.route_hosts('level=info msg="[TCP] 127.0.0.1:123 --> aicode.googleapis.com:443 match Match using DETECT"'), ['aicode.googleapis.com'])

    def test_location_error_is_not_passed(self):
        r = f.classify(3, '', '400 User location is not supported for the API use.', 'CHECK', ['aicode.googleapis.com'])
        self.assertEqual(r['reason'], 'location_restricted')
        self.assertFalse(r['passed'])
        error = 'AGY_ERROR: ' + json.dumps({'error_code': 400, 'error_id': 'abc-123', 'short_error': 'secret@example.com token=secret'})
        r = f.classify(3, '', error, 'CHECK', [])
        self.assertEqual(r['http_status'], 400)
        self.assertEqual(r['error_id'], 'abc-123')
        self.assertNotIn('secret', json.dumps(r))

    def test_full_names_and_passing_filter_survive_report(self):
        name = '[新用户试用][精品]美国-洛杉矶-B3-36|长名字'
        base = dict(name=name, protocol='vless', model='test-model', exit_ip='1.2.3.4', country='US',
                    generation_verified=True, api_hosts=['aicode.googleapis.com'], elapsed_ms=1500,
                    passed=True, reason='passed')
        report = dict(state='complete', created_at='now', total=2, nodes=[base, dict(base, name='失败节点', passed=False)])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            f.write_reports(report, path)
            passed = json.loads((path / 'passed.json').read_text())
            self.assertEqual([n['name'] for n in passed], [name])
            self.assertIn(name.replace('|', '\\|'), (path / 'report.md').read_text())

    def test_cli_timeout_reaps_child(self):
        import subprocess
        with self.assertRaises(subprocess.TimeoutExpired):
            f.run_cli([sys.executable, '-c', 'import time; time.sleep(30)'], f.d.clean_env(), .1)
        code, stdout, _ = f.run_cli([sys.executable, '-c', 'print("CHALLENGE")'], f.d.clean_env(), 5)
        self.assertEqual((code, stdout.strip()), (0, 'CHALLENGE'))


if __name__ == '__main__':
    unittest.main()
