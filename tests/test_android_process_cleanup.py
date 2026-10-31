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
                    process = Mock(pid=123456, stdout=io.BytesIO(), stderr=io.BytesIO())
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
        self.assertEqual(process.wait.call_args_list, [call(timeout=2)] * 3)

    def test_post_spawn_errors_stop_and_reap_before_propagating(self):
        spec = importlib.util.spec_from_file_location("android_process_failure_fixture", SOURCE)
        api = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(api)
        for boundary in ("selector-create", "selector-enter", "register", "read", "wait"):
            with self.subTest(boundary=boundary):
                capture = boundary != "wait"
                error = ValueError("synthetic selector entry") if boundary == "selector-enter" else OSError("synthetic I/O failure")
                process = Mock(pid=123456, returncode=0)
                streams = (io.BytesIO(), io.BytesIO()) if capture else (None, None)
                process.stdout, process.stderr = streams
                process.wait.side_effect = [error, 0, 0, 0] if boundary == "wait" else None
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
                self.assertEqual(lifecycle.mock_calls[-5:], [call.killpg(123456, signal.SIGTERM),
                                 call.wait(timeout=2), call.killpg(123456, signal.SIGKILL),
                                 call.wait(timeout=2), call.wait(timeout=2)])
                if capture:
                    self.assertTrue(all(stream.closed for stream in streams))


if __name__ == "__main__":
    unittest.main()
