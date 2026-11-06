"""Mock-only vendor process failures: no subprocess, signal or SDK fixture."""
import contextlib
import importlib.util
import io
from pathlib import Path
import signal
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, Mock, call, patch


SOURCE = Path(__file__).resolve().parents[1] / "bootstrap/lib/android/android_cli.py"


class AndroidProcessCleanup(unittest.TestCase):
    def setUp(self):
        observe = patch("os.waitid", return_value=SimpleNamespace(si_pid=123456))
        observe.start()
        self.addCleanup(observe.stop)

    def test_group_signals_finish_before_leader_is_reaped(self):
        spec = importlib.util.spec_from_file_location("android_group_lifetime_fixture", SOURCE)
        api = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(api)
        process = Mock(pid=123456, returncode=None)
        events = []
        def reap(**kwargs):
            events.append("reap")
            process.returncode = 0
        def kill(pid, sig):
            events.append((sig, process.returncode))
        process.wait.side_effect = reap
        with patch.object(api.os, "killpg", side_effect=kill), \
             patch.object(api.os, "waitid", return_value=SimpleNamespace(si_pid=123456)) as observe:
            api.stop_group(process)
        self.assertEqual(events, [(signal.SIGTERM, None), (signal.SIGKILL, None), "reap"])
        self.assertTrue(all(c.args == (api.os.P_PID, 123456,
                        api.os.WEXITED | api.os.WNOWAIT | api.os.WNOHANG)
                        for c in observe.call_args_list))

    def test_lost_child_custody_refuses_group_signals(self):
        spec = importlib.util.spec_from_file_location("android_lost_child_fixture", SOURCE)
        api = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(api)
        for already_reaped in (False, True):
            with self.subTest(already_reaped=already_reaped):
                process = Mock(pid=123456, returncode=0 if already_reaped else None)
                with patch.object(api.os, "killpg") as kill, \
                     patch.object(api.os, "waitid", side_effect=ChildProcessError("no owned child")):
                    with self.assertRaises(api.ProcessCleanupError):
                        api.stop_group(process)
                kill.assert_not_called()
                process.wait.assert_not_called()

    def test_selector_exit_after_reap_requires_manual_recovery_without_signaling(self):
        spec = importlib.util.spec_from_file_location("android_after_reap_fixture", SOURCE)
        api = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(api)
        process = Mock(pid=123456, returncode=None)
        def reap(**kwargs):
            process.returncode = 0
        process.wait.side_effect = reap
        selector = MagicMock()
        selector.__exit__.side_effect = OSError("selector close after reap")
        with patch.object(api.subprocess, "Popen", return_value=process), \
             patch.object(api.os, "killpg") as kill, \
             patch.object(api.os, "waitid", return_value=SimpleNamespace(si_pid=123456)), \
             patch.object(api.selectors, "DefaultSelector", return_value=selector), \
             contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(Exception) as caught:
                api.run_command(["/fictional-android"], capture=False)
        self.assertIsInstance(caught.exception, api.ProcessCleanupError)
        kill.assert_not_called()

    def test_pipe_close_after_reap_preserves_manual_recovery_gate(self):
        spec = importlib.util.spec_from_file_location("android_close_after_reap_fixture", SOURCE)
        api = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(api)
        process = Mock(pid=123456, returncode=None, stdout=Mock(), stderr=io.BytesIO())
        process.stdout.close.side_effect = OSError("pipe close after reap")
        def reap(**kwargs):
            process.returncode = 0
        process.wait.side_effect = reap
        selector = MagicMock()
        selector.__enter__.return_value = selector
        selector.get_map.return_value = {}
        with patch.object(api.subprocess, "Popen", return_value=process), \
             patch.object(api.os, "killpg") as kill, \
             patch.object(api.selectors, "DefaultSelector", return_value=selector), \
             contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(Exception) as caught:
                api.run_command(["/fictional-android"])
        self.assertIsInstance(caught.exception, api.ProcessCleanupError)
        kill.assert_not_called()

    def test_term_grace_stays_bounded_without_reaping_running_launcher(self):
        spec = importlib.util.spec_from_file_location("android_bounded_grace_fixture", SOURCE)
        api = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(api)
        process = Mock(pid=123456, returncode=None)
        events = []
        process.wait.side_effect = lambda **kwargs: events.append("reap")
        with patch.object(api.os, "killpg", side_effect=lambda pid, sig: events.append(sig)), \
             patch.object(api.os, "waitid", return_value=None), \
             patch.object(api.time, "monotonic", side_effect=(0, 1, 2)), \
             patch.object(api.time, "sleep", side_effect=lambda delay: events.append(("grace", delay))):
            api.stop_group(process)
        self.assertEqual(events, [signal.SIGTERM, ("grace", 0.05), signal.SIGKILL, "reap"])
        process.wait.assert_called_once_with(timeout=2)

    def test_broken_diagnostic_stream_cannot_mask_unconfirmed_cleanup(self):
        spec = importlib.util.spec_from_file_location("android_broken_diagnostic_fixture", SOURCE)
        api = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(api)
        for target in ("stdout", "stderr"):
            for original, code in ((OSError("read failure"), 1),
                                   (api.subprocess.TimeoutExpired("fictional vendor", 1), 124),
                                   (KeyboardInterrupt(), 130)):
                with self.subTest(stream=target, code=code):
                    created, buffers, reporting = [], [], [False]
                    class TrackedCleanupError(api.ProcessCleanupError):
                        def __init__(self, *args):
                            super().__init__(*args)
                            created.append(self)
                    class BrokenReport(io.StringIO):
                        def write(self, value):
                            if reporting[0]:
                                raise BrokenPipeError("synthetic reporting failure")
                            return super().write(value)
                    process = Mock(pid=123456, returncode=None, stdout=io.BytesIO(), stderr=io.BytesIO())
                    selector = MagicMock()
                    selector.__enter__.return_value = selector
                    selector.register.side_effect = lambda pipe, events, buffer: buffers.append(buffer)
                    selector.get_map.return_value = {"captured": True}
                    selector.select.side_effect = lambda timeout: [(SimpleNamespace(
                        fd=99, data=buffers[0 if target == "stdout" else 1]), 1)]
                    reads = 0
                    def read(fd, limit):
                        nonlocal reads
                        reads += 1
                        if reads == 1:
                            return b"captured diagnostic\n"
                        reporting[0] = True
                        raise original
                    streams = {"stdout": io.StringIO(), "stderr": io.StringIO()}
                    streams[target] = BrokenReport()
                    with patch.object(api, "ProcessCleanupError", TrackedCleanupError), \
                         patch.object(api.subprocess, "Popen", return_value=process), \
                         patch.object(api.os, "read", side_effect=read), \
                         patch.object(api.os, "killpg", side_effect=OSError("cleanup failure")), \
                         patch.object(api.selectors, "DefaultSelector", return_value=selector), \
                         contextlib.redirect_stdout(streams["stdout"]), contextlib.redirect_stderr(streams["stderr"]):
                        with self.assertRaises(Exception) as caught:
                            api.run_command(["/fictional-android"], timeout=1)
                    self.assertEqual(len(created), 1)
                    self.assertIs(caught.exception, created[0])
                    self.assertEqual(caught.exception.code, code)

    def test_cleanup_failure_reports_manual_recovery_instead_of_ordinary_error(self):
        spec = importlib.util.spec_from_file_location("android_uncertain_process_fixture", SOURCE)
        api = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(api)
        for boundary in ("killpg", "wait", "close"):
            with self.subTest(boundary=boundary):
                process = Mock(pid=123456, returncode=None, stdout=io.BytesIO(), stderr=io.BytesIO())
                fault = OSError("synthetic cleanup failure")
                if boundary == "wait":
                    process.wait.side_effect = fault
                if boundary == "close":
                    process.stdout = Mock()
                    process.stdout.close.side_effect = fault
                with patch.object(api.subprocess, "Popen", return_value=process), \
                     patch.object(api.os, "killpg", side_effect=fault if boundary in ("killpg", "close") else None), \
                     patch.object(api.selectors, "DefaultSelector", side_effect=OSError("selector failure")), \
                     contextlib.redirect_stdout(io.StringIO()):
                    with self.assertRaises(Exception) as caught:
                        api.run_command(["/fictional-android"], timeout=1)
                self.assertIsInstance(caught.exception, api.CliError)
                self.assertIn("cleanup unconfirmed", str(caught.exception).lower())
                self.assertIn("manual recovery", str(caught.exception).lower())
                self.assertTrue(process.stderr.closed)
                if boundary == "close":
                    process.stdout.close.assert_called_once_with()
                else:
                    self.assertTrue(process.stdout.closed)

    def test_unreaped_process_after_bounded_waits_requires_manual_recovery(self):
        spec = importlib.util.spec_from_file_location("android_unreaped_process_fixture", SOURCE)
        api = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(api)
        process = Mock(pid=123456, returncode=None)
        process.wait.side_effect = api.subprocess.TimeoutExpired("fictional vendor", 2)
        with patch.object(api.subprocess, "Popen", return_value=process), \
             patch.object(api.os, "killpg"), \
             patch.object(api.selectors, "DefaultSelector", side_effect=OSError("selector failure")), \
             contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(api.ProcessCleanupError, "manual recovery"):
                api.run_command(["/fictional-android"], capture=False, timeout=1)
        self.assertEqual(process.wait.call_args_list, [call(timeout=2)])

    def test_post_spawn_errors_stop_and_reap_before_propagating(self):
        spec = importlib.util.spec_from_file_location("android_process_failure_fixture", SOURCE)
        api = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(api)
        for boundary in ("selector-create", "selector-enter", "register", "read", "wait"):
            with self.subTest(boundary=boundary):
                capture = boundary != "wait"
                error = ValueError("synthetic selector entry") if boundary == "selector-enter" else OSError("synthetic I/O failure")
                process = Mock(pid=123456, returncode=None)
                streams = (io.BytesIO(), io.BytesIO()) if capture else (None, None)
                process.stdout, process.stderr = streams
                process.wait.side_effect = [error, 0] if boundary == "wait" else None
                lifecycle = Mock()
                lifecycle.attach_mock(process.wait, "wait")
                selector = MagicMock()
                selector.__enter__.return_value = selector
                selector.get_map.return_value = {"stdout": True}
                selector.select.return_value = [(SimpleNamespace(fd=99, data=bytearray()), 1)]
                if boundary == "selector-enter":
                    selector.__enter__.side_effect = error
                if boundary == "register":
                    selector.register.side_effect = error
                with patch.object(api.subprocess, "Popen", return_value=process) as launch, \
                     patch.object(api.os, "killpg") as kill, \
                     patch.object(api.os, "read", side_effect=error), \
                     patch.object(api.selectors, "DefaultSelector", return_value=selector) as factory, \
                     contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    lifecycle.attach_mock(kill, "killpg")
                    if boundary == "selector-create":
                        factory.side_effect = error
                    with self.assertRaises(type(error)) as caught:
                        api.run_command(["/fictional-android"], capture=capture, timeout=1)
                self.assertIs(caught.exception, error)
                self.assertIs(launch.call_args.kwargs.get("start_new_session"), True)
                self.assertEqual(kill.call_args_list, [call(123456, signal.SIGTERM),
                                                      call(123456, signal.SIGKILL)])
                self.assertEqual(process.wait.call_args_list[-1], call(timeout=2))
                self.assertEqual(lifecycle.mock_calls[-3:], [call.killpg(123456, signal.SIGTERM),
                                 call.killpg(123456, signal.SIGKILL), call.wait(timeout=2)])
                if capture:
                    self.assertTrue(all(stream.closed for stream in streams))


if __name__ == "__main__":
    unittest.main()
