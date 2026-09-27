import threading
import time
import unittest

from transcription_manager import TranscriptionManager


class FakeModel:
    def __init__(self, stalled=False, error=None):
        self.stalled = stalled
        self.error = error
        self.entered = threading.Event()
        self.release = threading.Event()
        self.calls = 0
        self.concurrent_calls = 0
        self.max_concurrent_calls = 0
        self.state_lock = threading.Lock()

    def transcribe(self, *_args, **_kwargs):
        with self.state_lock:
            self.calls += 1
            self.concurrent_calls += 1
            self.max_concurrent_calls = max(
                self.max_concurrent_calls,
                self.concurrent_calls,
            )

        self.entered.set()
        try:
            if self.stalled:
                self.release.wait()
            if self.error:
                raise self.error
            return {"text": "one two"}
        finally:
            with self.state_lock:
                self.concurrent_calls -= 1


def manager_with_model(model):
    manager = TranscriptionManager.__new__(TranscriptionManager)
    manager.model = model
    manager.result = None
    manager.lock = threading.Lock()
    manager.operation_lock = threading.Lock()
    manager.active_operation = None
    return manager


class TranscriptionManagerTests(unittest.TestCase):
    def test_stalled_transcription_does_not_block_reset_or_spawn_more_workers(self):
        model = FakeModel(stalled=True)
        manager = manager_with_model(model)

        started = time.monotonic()
        self.assertIsNone(manager.transcribe("mat-1.wav", timeout_seconds=0.02))
        self.assertLess(time.monotonic() - started, 0.5)
        self.assertTrue(model.entered.wait(0.5))

        started = time.monotonic()
        self.assertFalse(manager.reset(lock_timeout=0.02))
        self.assertLess(time.monotonic() - started, 0.5)

        self.assertIsNone(manager.transcribe("mat-2.wav", timeout_seconds=0.02))
        self.assertEqual(model.calls, 1)
        self.assertEqual(model.max_concurrent_calls, 1)

        model.release.set()
        manager.active_operation["thread"].join(0.5)
        self.assertFalse(manager.active_operation["thread"].is_alive())

        self.assertEqual(
            manager.transcribe("mat-2.wav", timeout_seconds=0.5),
            "one two",
        )
        self.assertEqual(model.calls, 2)
        self.assertEqual(model.max_concurrent_calls, 1)

    def test_failed_transcription_does_not_prevent_the_next_attempt(self):
        model = FakeModel(error=RuntimeError("fake Whisper failure"))
        manager = manager_with_model(model)

        self.assertIsNone(manager.transcribe("mat-1.wav", timeout_seconds=0.5))
        model.error = None

        self.assertEqual(
            manager.transcribe("mat-2.wav", timeout_seconds=0.5),
            "one two",
        )
        self.assertEqual(model.calls, 2)
        self.assertEqual(model.max_concurrent_calls, 1)


if __name__ == "__main__":
    unittest.main()
