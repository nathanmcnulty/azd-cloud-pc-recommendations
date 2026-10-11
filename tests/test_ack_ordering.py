"""Captured health ordering and exact acknowledgement readback over the real SDK."""
from contextlib import redirect_stdout
from copy import deepcopy
from datetime import timedelta
from io import StringIO
import json
import unittest
from unittest.mock import patch
from urllib.parse import unquote

from tests import test_table_acknowledgements as table_fixture
from tests.test_table_acknowledgements import Response
from tests.test_acknowledgements import NOW, REQUEST, TENANT, Session, activate, acknowledge
from cloudpc_monitor.acknowledgements import StateError, identity
from cloudpc_monitor.ack_cli import main
from cloudpc_monitor.config import Settings
from cloudpc_monitor.notifications import TeamsNotifier
from cloudpc_monitor.rules import evaluate_alerts


class OrderingWireTests(unittest.TestCase):
    setUp = table_fixture.TableAcknowledgementTests.setUp

    def notifier(self):
        self.session = Session()
        return TeamsNotifier(Settings.from_environment({'DRY_RUN': 'false',
            'TEAMS_WEBHOOK_URL': 'https://fixture.invalid/notify'}), session=self.session)

    def test_old_resolution_cas_cannot_resolve_new_observation_and_ack(self):
        before = identity(self.store.get_alert(self.fp))
        def newer():
            activate(self.store, NOW + timedelta(minutes=2))
            acknowledge(self.store, self.fp, now=NOW + timedelta(minutes=2))
        commit = self.store._commit_alert
        once = []
        def interleave(*args):
            if not once:
                once.append(True); newer()
            return commit(*args)
        with patch.object(self.store, '_commit_alert', side_effect=interleave):
            evaluate_alerts([], Settings.from_environment({}).rules, self.store,
                            now=NOW + timedelta(minutes=1))
        row = self.store.get_alert(self.fp)
        self.assertTrue(row['active']); self.assertTrue(row['acknowledged'])
        self.assertEqual(row['episode'], before['episode'])
        current = activate(self.store, NOW + timedelta(minutes=3))
        self.assertEqual(self.store.get_alert(self.fp)['episode'], before['episode'])
        self.assertEqual([e['kind'] for e in self.store.history(self.fp)['events']], ['acknowledged'])
        notifier = self.notifier()
        self.assertEqual(notifier.deliver(current, self.store, now=NOW + timedelta(minutes=3))['sentCount'], 0)
        self.assertEqual(self.session.calls, [])

    def test_old_active_cas_after_new_resolution_cannot_reopen_or_dispatch(self):
        self.wire.interleave = lambda: evaluate_alerts([], Settings.from_environment({}).rules,
            self.store, now=NOW + timedelta(minutes=2))
        stale = activate(self.store, NOW + timedelta(minutes=1))
        self.assertEqual(stale, []); self.assertFalse(self.store.get_alert(self.fp)['active'])
        notifier = self.notifier()
        self.assertEqual(notifier.deliver(self.alerts, self.store, now=NOW + timedelta(minutes=3))['sentCount'], 0)
        self.assertEqual(self.session.calls, [])
        old_episode = self.store.get_alert(self.fp)['episode']
        current = activate(self.store, NOW + timedelta(minutes=3))
        row = self.store.get_alert(self.fp)
        self.assertNotEqual(row['episode'], old_episode)
        self.assertLess(row['resolvedAt'], row['detectedAt'])
        self.assertEqual(len(current), 1)

    def test_old_active_cas_after_new_active_filters_old_payload(self):
        self.wire.interleave = lambda: activate(self.store, NOW + timedelta(minutes=2))
        self.assertEqual(activate(self.store, NOW + timedelta(minutes=1)), [])
        notifier = self.notifier()
        self.assertEqual(notifier.deliver(self.alerts, self.store, now=NOW + timedelta(minutes=3))['sentCount'], 0)
        self.assertEqual(self.session.calls, [])
        self.assertEqual(self.store.get_alert(self.fp)['detectedAt'], '2026-10-11T12:02:00Z')

    def test_dispatch_recheck_refuses_resolution_between_checks(self):
        notifier = self.notifier(); original = notifier._is_due; count = []
        def check(*args):
            count.append(True)
            if len(count) == 2:
                evaluate_alerts([], Settings.from_environment({}).rules, self.store,
                                now=NOW + timedelta(minutes=1))
            return original(*args)
        with patch.object(notifier, '_is_due', side_effect=check):
            result = notifier.deliver(self.alerts, self.store, now=NOW + timedelta(minutes=2))
        self.assertEqual(result['status'], 'none'); self.assertEqual(self.session.calls, [])
        self.assertEqual(self.store.get_alert(self.fp)['notificationCount'], 0)

    def test_equal_time_conflicting_resolution_and_reactivation_refused(self):
        before = deepcopy(self.store.get_alert(self.fp))
        evaluate_alerts([], Settings.from_environment({}).rules, self.store, now=NOW)
        self.assertEqual(before, self.store.get_alert(self.fp))
        self.assertEqual(len(activate(self.store, NOW)), 1)
        evaluate_alerts([], Settings.from_environment({}).rules, self.store, now=NOW + timedelta(minutes=1))
        resolved = deepcopy(self.store.get_alert(self.fp))
        self.assertEqual(activate(self.store, NOW + timedelta(minutes=1)), [])
        self.assertEqual(resolved, self.store.get_alert(self.fp))

    def test_captured_episode_cannot_resolve_reactivated_episode(self):
        original = self.store.mark_alert_inactive
        def interleave(fp, stamp, **kwargs):
            original(fp, '2026-10-11T12:01:00Z')
            activate(self.store, NOW + timedelta(minutes=2))
            acknowledge(self.store, fp, now=NOW + timedelta(minutes=2))
            return original(fp, stamp, **kwargs)
        with patch.object(self.store, 'mark_alert_inactive', side_effect=interleave):
            evaluate_alerts([], Settings.from_environment({}).rules, self.store,
                            now=NOW + timedelta(minutes=3))
        row = self.store.get_alert(self.fp)
        self.assertTrue(row['active']); self.assertTrue(row['acknowledged'])
        self.assertEqual(row['detectedAt'], '2026-10-11T12:02:00Z')

    def test_deleted_grace_observation_cannot_delay_active_acknowledged_episode(self):
        from cloudpc_monitor.graph_client import GraphSnapshot
        from cloudpc_monitor.rules import normalize_records
        records = normalize_records(GraphSnapshot(cloud_pcs=[{'id': 'grace-pc', 'status': 'failed'}]))
        rules = Settings.from_environment({}).rules
        self.assertEqual(evaluate_alerts(records, rules, self.store, now=NOW), [])
        active = evaluate_alerts(records, rules, self.store, now=NOW + timedelta(hours=2))
        fp = active[0].fingerprint; acknowledge(self.store, fp, now=NOW + timedelta(hours=2),
                                              expires_at=NOW + timedelta(hours=4))
        # Actual older empty evaluation deletes the observation but cannot resolve the newer alert.
        evaluate_alerts([], rules, self.store, now=NOW + timedelta(hours=1))
        current = evaluate_alerts(records, rules, self.store, now=NOW + timedelta(hours=2, minutes=1))
        self.assertEqual(len(current), 1); self.assertEqual(current[0].episode, active[0].episode)
        self.assertEqual(current[0].first_seen_at, active[0].first_seen_at)
        notifier = self.notifier()
        self.assertEqual(notifier.deliver(current, self.store, now=NOW + timedelta(hours=2, minutes=1))['sentCount'], 0)
        self.assertEqual(self.session.calls, [])

    def test_old_grace_observation_cannot_skip_post_resolution_grace(self):
        from cloudpc_monitor.graph_client import GraphSnapshot
        from cloudpc_monitor.rules import normalize_records
        records = normalize_records(GraphSnapshot(cloud_pcs=[{'id': 'grace-pc', 'status': 'failed'}]))
        rules = Settings.from_environment({}).rules
        evaluate_alerts(records, rules, self.store, now=NOW)
        active = evaluate_alerts(records, rules, self.store, now=NOW + timedelta(hours=2))
        evaluate_alerts([], rules, self.store, now=NOW + timedelta(hours=3))
        # A stale observation transport write is retained by the legacy observation store.
        self.store.record_observation('provisioning-failure:grace-pc', NOW)
        self.assertEqual(evaluate_alerts(records, rules, self.store, now=NOW + timedelta(hours=3, minutes=1)), [])
        current = evaluate_alerts(records, rules, self.store, now=NOW + timedelta(hours=5))
        self.assertEqual(len(current), 1); self.assertNotEqual(current[0].episode, active[0].episode)
        self.assertEqual(current[0].first_seen_at, NOW + timedelta(hours=3, minutes=1))

    def test_old_active_observation_write_after_resolution_cannot_reopen_early(self):
        from cloudpc_monitor.graph_client import GraphSnapshot
        from cloudpc_monitor.rules import normalize_records
        records = normalize_records(GraphSnapshot(cloud_pcs=[{'id': 'grace-pc', 'status': 'failed'}]))
        rules = Settings.from_environment({}).rules
        evaluate_alerts(records, rules, self.store, now=NOW)
        active = evaluate_alerts(records, rules, self.store, now=NOW + timedelta(hours=2))
        record = self.store.record_observation; once = []
        def old_write(key, time, **kwargs):
            if not once:
                once.append(True)
                evaluate_alerts([], rules, self.store, now=NOW + timedelta(hours=3))
            return record(key, time, **kwargs)
        with patch.object(self.store, 'record_observation', side_effect=old_write):
            self.assertEqual(evaluate_alerts(records, rules, self.store,
                now=NOW + timedelta(hours=2, minutes=1)), [])
        fp = active[0].fingerprint
        self.assertFalse(self.store.get_alert(fp)['active'])
        self.assertEqual(evaluate_alerts(records, rules, self.store,
            now=NOW + timedelta(hours=3, minutes=1)), [])
        current = evaluate_alerts(records, rules, self.store, now=NOW + timedelta(hours=5))
        self.assertEqual(len(current), 1)
        self.assertEqual(current[0].first_seen_at, NOW + timedelta(hours=3, minutes=1))
        self.assertNotEqual(current[0].episode, active[0].episode)

    def test_deleted_grace_observation_does_not_delay_current_unacknowledged_alert(self):
        from cloudpc_monitor.graph_client import GraphSnapshot
        from cloudpc_monitor.rules import normalize_records
        records = normalize_records(GraphSnapshot(cloud_pcs=[{'id': 'grace-pc', 'status': 'failed'}]))
        rules = Settings.from_environment({}).rules
        evaluate_alerts(records, rules, self.store, now=NOW)
        active = evaluate_alerts(records, rules, self.store, now=NOW + timedelta(hours=2))
        evaluate_alerts([], rules, self.store, now=NOW + timedelta(hours=1))
        current = evaluate_alerts(records, rules, self.store, now=NOW + timedelta(hours=2, minutes=1))
        self.assertEqual(len(current), 1); self.assertEqual(current[0].episode, active[0].episode)
        notifier = self.notifier()
        self.assertEqual(notifier.deliver(current, self.store,
            now=NOW + timedelta(hours=2, minutes=1))['sentCount'], 1)
        self.assertEqual(len(self.session.calls), 1)

    def test_missing_legacy_health_clock_refuses_without_alert_write_or_dispatch(self):
        entity, _ = self.wire.rows['alert', self.fp]
        payload = json.loads(entity['payload']); payload.pop('detectedAt')
        self.wire._put({**entity, 'payload': json.dumps(payload)})
        start = len(self.wire.calls)
        with self.assertRaisesRegex(StateError, 'invalid_state'):
            activate(self.store, NOW + timedelta(minutes=1))
        self.assertTrue(all(call.method == 'GET' for call in self.wire.calls[start:]))

    def test_newer_nested_success_before_older_completion_preserves_latest_timestamp(self):
        settings = Settings.from_environment({'DRY_RUN': 'false',
            'TEAMS_WEBHOOK_URL': 'https://fixture.invalid/notify', 'NOTIFICATION_RENOTIFY_HOURS': '24'})
        outer_case = self
        class InterleavingSession:
            def __init__(self): self.calls = 0
            def post(self, *args, **kwargs):
                self.calls += 1
                if self.calls == 1:
                    current = activate(outer_case.store, NOW + timedelta(minutes=2))
                    nested = notifier.deliver(current, outer_case.store, now=NOW + timedelta(minutes=2))
                    outer_case.assertEqual(nested['sentCount'], 1)
                return type('Response', (), {'status_code': 200, 'headers': {}})()
        session = InterleavingSession(); notifier = TeamsNotifier(settings, session=session)
        self.assertEqual(notifier.deliver(self.alerts, self.store, now=NOW)['sentCount'], 1)
        row = self.store.get_alert(self.fp)
        self.assertEqual(session.calls, 2); self.assertEqual(row['notificationCount'], 2)
        self.assertEqual(row['lastNotifiedAt'], '2026-10-11T12:02:00Z')
        current = activate(self.store, NOW + timedelta(days=1, minutes=1))
        self.assertEqual(notifier.deliver(current, self.store,
            now=NOW + timedelta(days=1, minutes=1))['sentCount'], 0)
        self.assertEqual(session.calls, 2)

    def test_older_success_before_newer_completion_keeps_both_counts(self):
        session = Session()
        notifier = TeamsNotifier(Settings.from_environment({'DRY_RUN': 'false',
            'TEAMS_WEBHOOK_URL': 'https://fixture.invalid/notify', 'NOTIFICATION_RENOTIFY_HOURS': '0'}),
            session=session)
        self.assertEqual(notifier.deliver(self.alerts, self.store, now=NOW)['sentCount'], 1)
        current = activate(self.store, NOW + timedelta(minutes=2))
        self.assertEqual(notifier.deliver(current, self.store, now=NOW + timedelta(minutes=2))['sentCount'], 1)
        self.assertEqual(len(session.calls), 2)
        self.assertEqual(self.store.get_alert(self.fp)['notificationCount'], 2)
        self.assertEqual(self.store.get_alert(self.fp)['lastNotifiedAt'], '2026-10-11T12:02:00Z')

    def test_old_success_after_resolution_and_reactivation_cannot_update_new_episode(self):
        case = self; original_episode = self.store.get_alert(self.fp)['episode']
        class ReopeningSession:
            def post(self, *args, **kwargs):
                evaluate_alerts([], Settings.from_environment({}).rules, case.store,
                                now=NOW + timedelta(minutes=1))
                activate(case.store, NOW + timedelta(minutes=2))
                acknowledge(case.store, case.fp, now=NOW + timedelta(minutes=2))
                return type('Response', (), {'status_code': 200, 'headers': {}})()
        notifier = TeamsNotifier(Settings.from_environment({'DRY_RUN': 'false',
            'TEAMS_WEBHOOK_URL': 'https://fixture.invalid/notify'}), session=ReopeningSession())
        self.assertEqual(notifier.deliver(self.alerts, self.store, now=NOW)['sentCount'], 1)
        row = self.store.get_alert(self.fp)
        self.assertNotEqual(row['episode'], original_episode); self.assertTrue(row['acknowledged'])
        self.assertEqual(row['notificationCount'], 0); self.assertIsNone(row['lastNotifiedAt'])

    def test_notification_timestamp_utc_normalization_counts_equal_and_older_success(self):
        episode = self.store.get_alert(self.fp)['episode']
        for time in ('2026-10-11T14:02:00+02:00', '2026-10-11T05:00:00-07:00',
                     '2026-10-11T12:02:00Z'):
            self.store.mark_notified(self.fp, time, episode=episode)
        row = self.store.get_alert(self.fp)
        self.assertEqual(row['lastNotifiedAt'], '2026-10-11T12:02:00Z')
        self.assertEqual(row['notificationCount'], 3)

    def test_malformed_success_timestamp_refused_before_sdk_dispatch(self):
        before = deepcopy(self.wire.rows)
        for time in (None, [], True, 'CANARY-token-url', '2026-10-11T12:00:00'):
            with self.subTest(time=time):
                start = len(self.wire.calls)
                code = 'invalid_request' if time == '2026-10-11T12:00:00' else 'invalid_state'
                with self.assertRaisesRegex(StateError, '^' + code + '$'):
                    self.store.mark_notified(self.fp, time, episode=self.alerts[0].episode)
                self.assertEqual(len(self.wire.calls), start)
                self.assertEqual(self.wire.rows, before)

    def test_malformed_recorded_timestamp_refused_without_sdk_write(self):
        for time in ([], True, 'CANARY-token-url', '2026-10-11T12:00:00'):
            with self.subTest(time=time):
                self.setUp()
                entity, _ = self.wire.rows['alert', self.fp]
                payload = json.loads(entity['payload']); payload['lastNotifiedAt'] = time
                self.wire._put({**entity, 'payload': json.dumps(payload)})
                before = deepcopy(self.wire.rows); start = len(self.wire.calls)
                code = 'invalid_request' if time == '2026-10-11T12:00:00' else 'invalid_state'
                with self.assertRaisesRegex(StateError, '^' + code + '$'):
                    self.store.mark_notified(self.fp, '2026-10-11T12:02:00Z', episode=self.alerts[0].episode)
                self.assertTrue(all(call.method == 'GET' for call in self.wire.calls[start:]))
                self.assertEqual(self.wire.rows, before)

    def test_successful_transaction_requires_exact_wire_audit_readback(self):
        for variant in ('missing', 'malformed', 'wrong_actor', 'wrong_recordedAt', 'wrong_episode', 'wrong_request'):
            with self.subTest(variant=variant):
                self.setUp(); original = self.wire.send
                def wire(request, **kwargs):
                    response = original(request, **kwargs)
                    if request.method == 'GET' and 'audit:' in unquote(request.url) and response.status_code == 200:
                        if variant == 'missing': return Response(request, 404)
                        entity = json.loads(response.body()); event = json.loads(entity['payload'])
                        if variant == 'malformed': event['revision'] = True
                        elif variant == 'wrong_actor': event['request']['actor'] = 'other-op'
                        elif variant == 'wrong_recordedAt': event['recordedAt'] = '2026-10-11T12:01:00Z'
                        elif variant == 'wrong_episode': event['episode'] = 'b' * 64
                        elif variant == 'wrong_request': event['request']['requestId'] = 'f1d795f2-2e58-4088-8d7a-7fc59458e104'
                        entity['payload'] = json.dumps(event)
                        return Response(request, 200, entity, response.headers['ETag'])
                    return response
                argv = ['--account-name', 'fixtureaccount', '--tenant-id', TENANT, '--table', 'CloudPcState',
                    'acknowledge', '--fingerprint', self.fp, '--episode', self.store.get_alert(self.fp)['episode'],
                    '--revision', '0', '--request-id', REQUEST, '--actor', 'fixture-operator',
                    '--expires-at', '2026-10-11T13:00:00Z']
                with patch.object(self.wire, 'send', side_effect=wire), redirect_stdout(StringIO()) as output:
                    self.assertEqual(main(argv, store_factory=lambda _: self.store, clock=lambda: NOW), 1)
                result = json.loads(output.getvalue())
                self.assertEqual(result['status'], 'failed'); self.assertNotIn('result', result)
                self.assertNotIn('CANARY', output.getvalue())
                self.assertEqual(len([call for call in self.wire.calls if call.url.endswith('/$batch')]), 1)
                self.assertTrue(self.store.get_alert(self.fp)['acknowledged'])
