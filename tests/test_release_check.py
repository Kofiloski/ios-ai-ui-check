import copy
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('release_check', SCRIPTS / 'release-check.py')
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class API:
    def __init__(self, names, state=None, completed=()):
        self.refs = [dict(ref='refs/tags/' + name, object=dict(type='commit', sha=sha)) for name, sha in names]
        self.state = state
        self.completed = completed

    def pages(self, path):
        return self.refs

    def get(self, path):
        if path.endswith('/ui-check-state') and self.state:
            return dict(assets=[dict(id=1, name='state-1.json', value=self.state)])
        for tag in self.completed:
            if path.endswith('/' + tag):
                return dict(assets=[dict(id=2, name='report-1.json', value=dict(execution_complete=True))])
        return None

    def asset_json(self, asset):
        return asset['value']


class Publisher:
    def __init__(self):
        self.releases = {}
        self.uploads = []
        self.updates = []

    def get(self, path):
        return self.releases.get(path.rsplit('/', 1)[-1])

    def request(self, path, data, method, content_type=None):
        if method == 'PATCH':
            destination = next(value for value in self.releases.values()
                               if str(value['id']) == path.rsplit('/', 1)[-1])
            destination.update(data)
            self.updates.append(data)
            return destination, ''
        if path.endswith('/releases'):
            value = dict(id=len(self.releases) + 1, body=data['body'], assets=[],
                         upload_url='https://uploads.github.com/' + data['tag_name'] + '{?name}')
            self.releases[data['tag_name']] = value
            return value, ''
        name = release.urllib.parse.parse_qs(release.urllib.parse.urlsplit(path).query)['name'][0]
        self.uploads.append((name, data.read_bytes()))
        destination = self.releases[release.urllib.parse.urlsplit(path).path.lstrip('/')]
        destination['assets'].append(dict(name=name))
        return dict(name=name), ''


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.config = dict(upstream='owner/app', tag_pattern=r'^(\d+)\.(\d+)\.(\d+)$',
                           launch_presets=[dict(action='launch', arguments=['UITEST'])], max_tests=3)
        self.tags = [('1.0.0', '1' * 40), ('1.1.0', '2' * 40), ('1.2.0', '3' * 40)]

    def test_bootstrap_selects_only_latest_pair(self):
        value = release.discover(API(self.tags), self.config, 'me/fork')
        self.assertEqual(value['base']['tag'], '1.1.0')
        self.assertEqual(value['head']['tag'], '1.2.0')
        self.assertEqual(value['state']['pending'], ['1.2.0'])

    def test_hotfix_published_after_higher_version_is_not_lost(self):
        state = dict(seen=dict(self.tags), pending=[])
        value = release.discover(API(self.tags + [('1.1.1', '4' * 40)], state), self.config, 'me/fork')
        self.assertEqual(value['head']['tag'], '1.1.1')
        self.assertEqual(value['base']['tag'], '1.1.0')

    def test_completed_queue_item_does_not_starve_next_release(self):
        state = dict(seen=dict(self.tags), pending=['1.1.0', '1.2.0'])
        key = hashlib.sha256(('owner/app:' + '1' * 40 + ':' + '2' * 40).encode()).hexdigest()[:20]
        value = release.discover(API(self.tags, state, ['ui-check-' + key]), self.config, 'me/fork')
        self.assertTrue(value['run'])
        self.assertEqual(value['head']['tag'], '1.2.0')

    def test_history_reads_json_instead_of_newer_markdown_asset(self):
        api = API(self.tags)
        assets = [dict(id=1, name='report-1.json', value=dict(status='passed')),
                  dict(id=2, name='report-1.md', value='Markdown is not JSON')]
        self.assertEqual(release.latest_asset(api, dict(assets=assets), 'report-'), dict(status='passed'))

    def test_stable_ios_filter_rejects_testflight_and_macos(self):
        config = dict(self.config, tag_pattern=r'^(\d+)\.(\d+)\.(\d+)\+ios$')
        api = API([('7.244.0+ios', '1' * 40), ('7.245.0-1+ios', '2' * 40), ('1.215.0+macos', '3' * 40)])
        self.assertEqual([v['tag'] for v in release.release_tags(api, config)], ['7.244.0+ios'])

    def test_firefox_two_component_versions_are_supported(self):
        config = dict(self.config, tag_pattern=r'^firefox-v(\d+)\.(\d+)(?:\.(\d+))?$')
        self.assertEqual(release.release_tags(API([('firefox-v160.0', '1' * 40)]), config)[0]['version'], (160, 0, 0))

    def test_annotated_tags_are_resolved_lazily(self):
        api = API(self.tags)
        api.refs[-1]['object'] = dict(type='tag', sha='a' * 40)
        original = api.get
        api.get = lambda path: dict(object=dict(type='commit', sha='3' * 40)) if '/git/tags/' in path else original(path)
        result = release.discover(api, self.config, 'me/fork')
        self.assertEqual(result['head']['sha'], '3' * 40)
        self.assertEqual(result['state']['seen']['1.2.0'], 'a' * 40)

    def test_manual_historical_pair_and_force_latest(self):
        state = dict(seen=dict(self.tags), pending=[])
        value = release.discover(API(self.tags, state), self.config, 'me/fork', head_tag='1.1.0', base_tag='1.0.0')
        self.assertEqual(value['head']['sha'], '2' * 40)
        self.assertTrue(release.discover(API(self.tags, state), self.config, 'me/fork', force=True)['run'])
        with self.assertRaises(ValueError):
            release.discover(API(self.tags), self.config, 'me/fork', head_tag='unknown')

    def test_force_latest_does_not_consume_an_older_pending_release(self):
        state = dict(seen=dict(self.tags), pending=['1.1.0'])
        value = release.discover(API(self.tags, state), self.config, 'me/fork', force=True)
        self.assertEqual(value['head']['tag'], '1.2.0')
        self.assertEqual(value['state']['pending'], ['1.1.0'])
        explicit = release.discover(API(self.tags, state), self.config, 'me/fork', force=True, head_tag='1.1.0')
        self.assertEqual(explicit['head']['tag'], '1.1.0')

    def suite(self):
        return dict(tests=[dict(id='changed-setting', claim='Changed setting is exposed', files=['Settings.swift'],
            scenario=dict(name='Changed setting', steps=[dict(action='launch', arguments=['UITEST']),
                dict(action='assertVisible', id='settings.new')]))], uncovered=[])

    def test_suite_binds_real_files_and_reports_unassessed_changes(self):
        value = release.validate_suite(self.suite(), dict(changed_files=['Settings.swift', 'Auth.swift']), self.config, {'settings.new'})
        self.assertEqual(value['uncovered'], [dict(file='Auth.swift', reason='Not assessed by generated tests')])

    def test_observed_runtime_identifier_can_supplement_source_inventory(self):
        release.validate_suite(self.suite(), dict(changed_files=['Settings.swift']), self.config,
                               {'other.source.id'}, {'settings.new'})

    def test_suite_rejects_fabricated_files_launch_state_and_empty_smoke(self):
        for mutate in (
            lambda s: s['tests'][0].update(files=['invented.swift']),
            lambda s: s['tests'][0]['scenario']['steps'][0].update(arguments=['invented']),
            lambda s: s['tests'][0]['scenario'].update(steps=[dict(action='launch', arguments=['UITEST'])]),
            lambda s: s.update(tests=[]),
            lambda s: s['tests'].append(copy.deepcopy(s['tests'][0])),
        ):
            with self.subTest(mutation=mutate):
                value = self.suite()
                mutate(value)
                with self.assertRaises(ValueError):
                    release.validate_suite(value, dict(changed_files=['Settings.swift']), self.config, {'settings.new'})

    def test_incomplete_execution_is_blocked_not_a_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            release.write_json(path / 'suite.json', self.suite())
            selection = dict(base=dict(sha='1' * 40), head=dict(tag='1.1.0', sha='2' * 40))
            value = release.report(selection, path, dict(execute='skipped'))
            self.assertEqual(value['status'], 'blocked')
            self.assertFalse(value['execution_complete'])
            self.assertEqual(value['tests'][0]['status'], 'not-executed')

    def test_native_zero_tests_and_skips_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path / 'Test.xcresult').mkdir()
            for counts in [dict(totalTestCount=0, passedTests=0, failedTests=0, skippedTests=0),
                           dict(totalTestCount=1, passedTests=0, failedTests=0, skippedTests=1),
                           dict(totalTestCount=1, passedTests=1, failedTests=0, skippedTests=0)]:
                with patch.object(release.subprocess, 'check_output', return_value=json.dumps(counts)):
                    value = release.case_result('changed-setting', path)
                self.assertEqual(value['status'], 'passed' if counts['passedTests'] == 1 else 'failed')

    def test_real_provider_transport_writes_diff_bound_scenarios(self):
        raw = self.suite()
        properties = release.PLANNER_SCHEMA['properties']['steps']['items']['properties']
        raw['tests'][0]['scenario']['description'] = None
        raw['tests'][0]['scenario']['steps'] = [dict(dict.fromkeys(properties), **step)
                                               for step in raw['tests'][0]['scenario']['steps']]
        captured = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_POST(self):
                captured.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
                body = json.dumps(dict(choices=[dict(finish_reason='stop', message=dict(content=json.dumps(raw)))])).encode()
                self.send_response(200)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                source = Path(tmp) / 'input'
                (source / 'inspect').mkdir(parents=True)
                context = dict(base_sha='1' * 40, head_sha='2' * 40, diff_sha256='3' * 64,
                               changed_files=['Settings.swift', 'Auth.swift'], diff='+ new setting', release_notes='New setting')
                release.write_json(source / 'change-context.json', context)
                release.write_json(source / 'inventory.json', dict(identifiers=['settings.new'], labels=[]))
                release.write_json(source / 'inspect/before-planning-ui-tree.json', {})
                (source / 'inspect/before-planning-screenshot.png').write_bytes(b'fixture-image')
                env = dict(AI_UI_PLANNER_PROVIDER='openai-compatible', AI_UI_PLANNER_MODEL='fixture-model',
                           AI_UI_PLANNER_BASE_URL=f'http://127.0.0.1:{server.server_port}/v1')
                with patch.dict(os.environ, env, clear=True):
                    result = release.plan(self.config, source, Path(tmp) / 'output')
                self.assertEqual(result['head_sha'], '2' * 40)
                self.assertTrue((Path(tmp) / 'output/scenarios/changed-setting.json').exists())
                self.assertIn('tests', captured[0]['response_format']['json_schema']['schema']['properties'])
                self.assertIn('+ new setting', json.dumps(captured[0]))
                self.assertEqual(result['uncovered'][0]['file'], 'Auth.swift')
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_report_rejects_unknown_results_and_escapes_mentions(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            suite = self.suite()
            suite['tests'][0]['claim'] = '@someone <script> is data'
            release.write_json(path / 'suite.json', suite)
            release.write_json(path / 'case-result.json', dict(id='changed-setting', status='passed',
                counts=dict(totalTestCount=1, passedTests=1, failedTests=0, skippedTests=0)))
            selection = dict(base=dict(sha='1' * 40), head=dict(tag='1.1.0', sha='2' * 40))
            jobs = {job: dict(result='success') for job in ('build-inspect', 'plan', 'execute')}
            self.assertEqual(release.report(selection, path, jobs)['status'], 'passed')
            self.assertEqual(release.report(selection, path, {})['status'], 'blocked')
            markdown = (path / 'report.md').read_text()
            self.assertNotIn('@someone', markdown)
            self.assertNotIn('<script>', markdown)
            release.write_json(path / 'case-result.json', dict(id='invented-case', status='passed'))
            with self.assertRaises(ValueError):
                release.report(selection, path, jobs)

    def test_prepare_compares_exact_head_and_does_not_diff_the_harness(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'repo'
            root.mkdir()
            def git(*args):
                return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()
            git('init', '-q')
            git('config', 'user.name', 'Fixture')
            git('config', 'user.email', 'fixture@example.invalid')
            file = root / 'Settings.swift'
            file.write_text('old setting\n')
            (root / 'Project.pbxproj').write_text('upstream project\n')
            git('add', '.')
            git('commit', '-qm', 'base')
            base = git('rev-parse', 'HEAD')
            file.write_text('new setting\n')
            git('commit', '-qam', 'head')
            head = git('rev-parse', 'HEAD')
            (root / 'runner.sh').write_text('native harness\n')
            (root / 'Project.pbxproj').write_text('snapshot-specific project preparation\n')
            git('add', '.')
            git('commit', '-qm', 'harness')
            config = dict(self.config, source_seed=head, harness_excludes=['Project.pbxproj'])
            selection = dict(base=dict(sha=base), head=dict(sha=head), release_notes='', notes_source='unavailable')
            original = release.git
            with patch.object(release, 'git', side_effect=lambda path, *a, **kw: '' if a[0] == 'fetch' else original(path, *a, **kw)):
                value = release.prepare(root, config, selection, Path(tmp) / 'evidence')
            self.assertEqual(git('rev-parse', 'HEAD'), head)
            self.assertEqual(value['changed_files'], ['Settings.swift'])
            self.assertTrue((root / 'runner.sh').exists())
            self.assertEqual((root / 'Project.pbxproj').read_text(), 'upstream project\n')
            self.assertEqual(value['harness_excludes'], ['Project.pbxproj'])
            self.assertEqual(value['notes_source'], 'unavailable')
            original = release.git
            with patch.object(release, 'git', side_effect=lambda path, *a, **kw: '' if a[0] == 'fetch' else original(path, *a, **kw)):
                release.verify_plan_inputs(root, config, selection, Path(tmp) / 'evidence')
                value['changed_files'] = ['invented.swift']
                release.write_json(Path(tmp) / 'evidence/change-context.json', value)
                with self.assertRaisesRegex(ValueError, 'Changed-file inventory'):
                    release.verify_plan_inputs(root, config, selection, Path(tmp) / 'evidence')
                value['changed_files'] = ['Settings.swift']
                release.write_json(Path(tmp) / 'evidence/change-context.json', value)
                (Path(tmp) / 'evidence/change.diff').write_text('tampered diff')
                with self.assertRaisesRegex(ValueError, 'immutable upstream diff'):
                    release.verify_plan_inputs(root, config, selection, Path(tmp) / 'evidence')

    def test_publish_retains_attempts_and_advances_blocked_queue_after_uploads(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {
            'GITHUB_RUN_ID': '123', 'GITHUB_RUN_ATTEMPT': '2', 'GITHUB_SHA': '4' * 40,
        }):
            path = Path(tmp) / 'history'
            path.mkdir()
            selection = dict(report_tag='ui-check-abc', head=dict(tag='1.1.0'),
                             state=dict(seen=dict(self.tags), pending=['1.1.0', '1.2.0']))
            result = dict(status='blocked', comparison=selection)
            release.write_json(path / 'report.json', result)
            (path / 'report.md').write_text('Blocked, not passed')
            api = Publisher()
            release.publish(api, 'me/fork', result, path)
            self.assertEqual([name for name, _ in api.uploads],
                ['evidence-123-2.tar.gz', 'report-123-2.json', 'report-123-2.md', 'state-123-2.json'])
            self.assertEqual(json.loads(api.uploads[-1][1])['pending'], ['1.2.0'])
            release.publish(api, 'me/fork', result, path)
            self.assertEqual(len(api.uploads), 4, 'An existing attempt must not be overwritten')

    def test_retry_updates_visible_summary_without_overwriting_attempts(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {
            'GITHUB_RUN_ID': '123', 'GITHUB_SHA': '4' * 40,
        }):
            path = Path(tmp) / 'history'
            path.mkdir()
            api = Publisher()
            for attempt, status in enumerate(('blocked', 'passed', 'failed'), 1):
                selection = dict(report_tag='ui-check-abc', head=dict(tag='1.1.0'),
                                 state=dict(seen=dict(self.tags), pending=['1.1.0']))
                result = dict(status=status, comparison=selection)
                release.write_json(path / 'report.json', result)
                (path / 'report.md').write_text('Result: ' + status)
                with patch.dict(os.environ, {'GITHUB_RUN_ATTEMPT': str(attempt)}):
                    release.publish(api, 'me/fork', result, path)
                body = api.releases['ui-check-abc']['body']
                self.assertIn('Result: ' + status, body)
                self.assertIn(f'report-123-{attempt}.json', body)
            names = [name for name, _ in api.uploads]
            self.assertEqual(len(names), len(set(names)))
            self.assertEqual(len([name for name in names if name.startswith('report-')]), 6)

    def test_summary_is_not_refreshed_until_attempt_evidence_is_uploaded(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {
            'GITHUB_RUN_ID': '123', 'GITHUB_RUN_ATTEMPT': '1', 'GITHUB_SHA': '4' * 40,
        }):
            path = Path(tmp) / 'history'
            path.mkdir()
            selection = dict(report_tag='ui-check-abc', head=dict(tag='1.1.0'),
                             state=dict(seen=dict(self.tags), pending=['1.1.0']))
            result = dict(status='passed', comparison=selection)
            release.write_json(path / 'report.json', result)
            (path / 'report.md').write_text('Result: passed')
            api = Publisher()
            api.releases['ui-check-abc'] = dict(id=1, body='Result: blocked', assets=[],
                upload_url='https://uploads.github.com/ui-check-abc{?name}')
            with patch.object(api, 'request', side_effect=OSError('upload failed')):
                with self.assertRaises(OSError):
                    release.publish(api, 'me/fork', result, path)
            self.assertEqual(api.releases['ui-check-abc']['body'], 'Result: blocked')
            self.assertEqual(api.updates, [])
            self.assertEqual(selection['state']['pending'], ['1.1.0'])

    def test_provider_credentials_are_absent_from_native_and_history_jobs(self):
        workflow = (SCRIPTS.parent / '.github/workflows/release-check.yml').read_text()
        for job in ('build-inspect', 'execute', 'history'):
            # Match whole job blocks rather than individual indented steps.
            import re
            section = re.split(r'\n  [a-z][a-z-]*:\n', workflow.split('\n  ' + job + ':\n', 1)[1])[0]
            self.assertNotIn('secrets.', section)
            if job != 'history':
                self.assertNotIn('contents: write', section)

    def test_profile_rejects_unsafe_harness_exclusions(self):
        value = dict(self.config, source_seed='1' * 40, project='App.xcodeproj', runner='scripts/runner.sh')
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'profile.json'
            for invalid in ['not-an-array', ['../outside'], ['/absolute'], ['.'], ['']]:
                release.write_json(path, dict(value, harness_excludes=invalid))
                with self.assertRaisesRegex(ValueError, 'harness_excludes'):
                    release.profile(path)


if __name__ == '__main__':
    unittest.main()
