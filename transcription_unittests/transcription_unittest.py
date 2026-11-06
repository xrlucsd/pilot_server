import csv
import json
import os
import sys
import threading
import time
import wave
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from recording_manager import RecordingManager
from subject_manager_2 import SubjectManager
from test_manager import TestManager as MatTestManager
from transcription_manager import TranscriptionManager, normalize_digits


def mat_questions():
    for task_file in ("task_0_data.json", "task_1_data.json", "task_2_data.json"):
        yield from json.loads((ROOT / "test_files" / task_file).read_text())


@pytest.mark.parametrize("question", mat_questions(), ids=lambda question: question["question"])
def test_every_accepted_spoken_form_scores_correct(question):
    """Whisper may return any listed form; cleanup must not turn a correct answer wrong."""
    numeric_answer = question["answer"][0]
    for spoken_form in question["answer"]:
        digits = normalize_digits(spoken_form)
        # "nine five" is listed for 905, but as digits it can only mean 95.
        if digits == numeric_answer.replace("0", ""):
            continue
        assert digits == numeric_answer
        assert MatTestManager.check_answer(MatTestManager.__new__(MatTestManager), digits, question["answer"])


@pytest.mark.parametrize("raw, expected", [
    ("Four, one. 3-5", "4135"),
    ("  9 9 6. ", "996"),
    ("1,042", "1042"),
    ("um, nine hundred and six", "906"),
    ("twelve oh five", "1205"),
    ("a thousand", "1000"),
    ("I don't know", ""),
    ("", ""),
])
def test_normalize_digits(raw, expected):
    assert normalize_digits(raw) == expected


def read_rows(path):
    with open(path, newline="", encoding="utf-8") as csv_file:
        return list(csv.reader(csv_file))


def make_subject_csv(tmp_path, name):
    manager = SubjectManager()
    manager.csv_file_path = str(tmp_path / name)
    manager.experiment_name = "synthetic"
    manager.trial_name = "synthetic"
    manager.create_csv(manager.csv_file_path)
    return manager


def test_late_transcription_reaches_the_participant_who_recorded_it(tmp_path):
    manager = make_subject_csv(tmp_path, "first.csv")
    first_csv = manager.csv_file_path
    manager.append_data({"Timestamp": "t1", "Event_Marker": "prs_1_q1", "Condition": "A", "Audio_File": "a.wav"})
    manager.append_data({"Timestamp": "t2", "Event_Marker": "prs_1_q2", "Condition": "A", "Audio_File": "b.wav"})
    before = read_rows(first_csv)

    # The next participant starts before the queued transcription finishes.
    manager.csv_file_path = str(tmp_path / "second.csv")
    manager.create_csv(manager.csv_file_path)
    manager.update_transcription(first_csv, "a.wav", 'She said, "quiet"\nand left')

    after = read_rows(first_csv)
    assert after[:7] == before[:7]
    assert after[7][:5] == before[7][:5]
    assert after[7][5] == 'She said, "quiet"\nand left'
    assert after[8] == before[8]
    assert len(read_rows(manager.csv_file_path)) == 7
    assert not os.path.exists(f"{first_csv}.tmp")


def test_unknown_audio_file_leaves_the_csv_unchanged(tmp_path):
    manager = make_subject_csv(tmp_path, "subject.csv")
    manager.append_data({"Timestamp": "t1", "Audio_File": "a.wav"})
    before = read_rows(manager.csv_file_path)

    manager.update_transcription(manager.csv_file_path, "missing.wav", "text")

    assert read_rows(manager.csv_file_path) == before


class FakeStream:
    def __init__(self, manager, frames_to_read, rate_change):
        self.manager = manager
        self.frames_to_read = frames_to_read
        self.rate_change = rate_change

    def read(self, chunk_size):
        # A device change during a recording must not relabel that recording.
        if self.rate_change:
            self.manager.sample_rate = self.rate_change
        self.frames_to_read -= 1
        if self.frames_to_read == 0:
            self.manager.stop_event.set()
        return b"\x00\x00" * chunk_size

    def stop_stream(self):
        pass

    def close(self):
        pass


class FakeAudio:
    def __init__(self, stream):
        self.stream = stream
        self.opened_rate = None

    def open(self, **kwargs):
        self.opened_rate = kwargs["rate"]
        return self.stream

    def get_sample_size(self, audio_format):
        return 2


def record_with_fake_device(tmp_path, device_rate, rate_change=None):
    manager = RecordingManager.__new__(RecordingManager)
    manager.sample_rate = device_rate
    manager.stop_event = threading.Event()
    manager.recording_started_event = threading.Event()
    manager.stream_ready_event = threading.Event()
    manager.audio_devices = []
    manager.device_index = 0
    manager._recording_file = str(tmp_path / "recording.wav")
    manager.audio = FakeAudio(FakeStream(manager, device_rate // 1024, rate_change))
    manager.record_thread()
    with wave.open(manager.recording_file, "rb") as wav_file:
        return manager.audio.opened_rate, wav_file.getframerate(), wav_file.getnframes() / wav_file.getframerate()


@pytest.mark.parametrize("device_rate", [16000, 24000, 44100, 48000])
def test_recording_header_matches_the_capture_rate(tmp_path, device_rate):
    opened_rate, header_rate, seconds = record_with_fake_device(tmp_path, device_rate)
    assert opened_rate == header_rate == device_rate
    assert seconds == pytest.approx(1, abs=0.1)


def test_device_change_during_recording_keeps_the_capture_rate(tmp_path):
    opened_rate, header_rate, _ = record_with_fake_device(tmp_path, 48000, rate_change=16000)
    assert opened_rate == header_rate == 48000


def short_transcription(tmp_path, whisper_text, digits_only):
    audio_file = tmp_path / "recording.wav"
    with wave.open(str(audio_file), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(16000)
        wav_file.writeframes(b"\x00\x00" * 16000)

    manager = TranscriptionManager.__new__(TranscriptionManager)
    manager._decode = lambda model_name, audio, initial_prompt="": whisper_text
    operation = {"done": threading.Event(), "result": None}
    manager._run_transcription(str(audio_file), digits_only, operation)
    return operation["result"]


def test_audio_check_shows_a_misheard_phrase(tmp_path):
    misheard = "She cells seashells buy the seashore"
    assert short_transcription(tmp_path, misheard, digits_only=False) == misheard


def test_audio_check_reports_when_nothing_was_heard(tmp_path):
    assert short_transcription(tmp_path, "", digits_only=False) is None


@pytest.mark.parametrize("whisper_text", [
    "I I I I I um um the the the room",
    "The cafe, or caf\u00e9, felt na\u00efve to me.",
    "Supercalifragilisticexpialidocious.",
])
def test_long_responses_keep_stutters_and_unusual_words(tmp_path, whisper_text):
    audio_file = tmp_path / "response.wav"
    with wave.open(str(audio_file), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(16000)
        wav_file.writeframes(b"\x00\x00" * 16000)

    manager = TranscriptionManager.__new__(TranscriptionManager)
    manager._decode = lambda model_name, audio, initial_prompt="": whisper_text
    manager.long_lock = threading.Lock()

    assert manager.transcribe_long(str(audio_file)) == whisper_text


class TaggedStream:
    """Stands in for a microphone: every sample holds this recording's tag."""

    def __init__(self, tag):
        self.tag = tag

    def read(self, chunk_size):
        time.sleep(0.001)
        return int(self.tag).to_bytes(2, "little", signed=True) * chunk_size

    def stop_stream(self):
        pass

    def close(self):
        pass


class TaggedAudio:
    def __init__(self):
        self.opened = 0

    def open(self, **kwargs):
        self.opened += 1
        return TaggedStream(self.opened)

    def get_sample_size(self, audio_format):
        return 2


class FixedTimestamp:
    def get_timestamp(self, timestamp_format):
        return "2026-01-01T00:00:00"


def make_recorder(tmp_path):
    manager = RecordingManager.__new__(RecordingManager)
    manager.sample_rate = 48000
    manager.stop_event = threading.Event()
    manager.recording_started_event = threading.Event()
    manager.stream_ready_event = threading.Event()
    manager.recording_thread = None
    manager.task_audio_active = False
    manager._stream_is_active = False
    manager._timestamp = None
    manager._end_timestamp = None
    manager.audio_devices = []
    manager.device_index = 0
    manager.timestamp_manager = FixedTimestamp()
    manager._recording_file = str(tmp_path / "recording.wav")
    manager.audio = TaggedAudio()
    return manager


def recorded_tags(path):
    with wave.open(path, "rb") as wav_file:
        samples = wav_file.readframes(wav_file.getnframes())
    return {int.from_bytes(samples[i:i + 2], "little", signed=True) for i in range(0, len(samples), 2)}


def test_new_recording_contains_no_audio_from_one_left_running(tmp_path):
    manager = make_recorder(tmp_path)
    manager.start_recording()
    abandoned_thread = manager.recording_thread
    time.sleep(0.05)

    manager.start_recording(task_audio=True)
    time.sleep(0.01)
    assert not abandoned_thread.is_alive()
    assert manager.task_audio_active
    manager.stop_recording()

    assert recorded_tags(manager.recording_file) == {2}
    assert not manager.task_audio_active


def test_cancelled_recording_writes_nothing_and_turns_the_stream_off(tmp_path):
    manager = make_recorder(tmp_path)
    manager.start_recording()
    active_thread = manager.recording_thread
    time.sleep(0.01)

    manager.cancel_recording()

    assert not active_thread.is_alive()
    assert not manager.stream_is_active
    assert not os.path.exists(manager.recording_file)


def test_recording_after_a_stopped_recording_still_saves(tmp_path):
    manager = make_recorder(tmp_path)
    manager.start_recording()
    time.sleep(0.01)
    manager.stop_recording()
    assert recorded_tags(manager.recording_file) == {1}

    manager.start_recording()
    time.sleep(0.01)
    manager.stop_recording()
    assert recorded_tags(manager.recording_file) == {2}
