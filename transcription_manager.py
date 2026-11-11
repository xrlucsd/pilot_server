import os
import re
import subprocess
import tempfile
import threading
import time
import wave
from pathlib import Path

import _pywhispercpp
import numpy as np
from pywhispercpp.model import Model
from pywhispercpp.utils import download_model
from scipy.signal import resample_poly

ROOT = Path(__file__).parent
MODELS_DIR = ROOT / "models"
HINTS_FILE = ROOT / "hints.txt"
SAMPLE_RATE = 16000     # whisper.cpp expects 16 kHz mono float32
MIN_AUDIO_SECONDS = 0.25

FAST_MODEL = "base.en"      # MAT answers: must return quickly
LONG_MODEL = "medium.en"    # PRS, Room Observation, and SER responses: Process Audio only

# whisper.cpp does not validate model files: a partial download loads without
# error and then segfaults the whole server on first use. Compare against the
# published size of each model (a model missing from this table is not checked).
MODEL_SIZES = {
    "base.en": 147964211,
    "medium.en": 1533774781,
}

DIGIT_WORDS = {
    "zero": 0, "oh": 0, "o": 0,
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9,
}
TEEN_WORDS = {
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
}
TENS_WORDS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}
SCALE_WORDS = ("hundred", "thousand")
NUMBER_WORDS = {**DIGIT_WORDS, **TEEN_WORDS, **TENS_WORDS}


WHISPER_WARNING_LEVELS = (3, 4)  # ggml's warning and error log levels


def log_whisper_message(level, message):
    """Keep whisper.cpp's routine logs out of the server output, but not its problems."""
    if level in WHISPER_WARNING_LEVELS:
        print(f"whisper.cpp: {message.strip()}")


def normalize_digits(text):
    """
    Reduce a spoken MAT answer to a plain digit string, dropping whitespace,
    punctuation, and any other non-number text.

    Digits said one at a time are joined ("Four, one. 3-5" -> "4135"), and
    compound numbers keep their value ("nine hundred ninety-six" -> "996",
    "nine ninety six" -> "996", "one thousand and forty-two" -> "1042").
    """
    tokens = [
        token for token in re.findall(r"[a-z]+|\d+", text.lower())
        if token.isdigit() or token in NUMBER_WORDS or token in SCALE_WORDS
    ]

    if any(token in SCALE_WORDS for token in tokens):
        total = 0
        current = 0
        for token in tokens:
            if token == "hundred":
                current = max(current, 1) * 100
            elif token == "thousand":
                total += max(current, 1) * 1000
                current = 0
            else:
                current += int(token) if token.isdigit() else NUMBER_WORDS[token]
        return str(total + current)

    digits = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        index += 1
        if token in TENS_WORDS:
            value = TENS_WORDS[token]
            # "ninety six" is one number, unlike "nine six".
            if index < len(tokens):
                next_value = DIGIT_WORDS.get(tokens[index], tokens[index])
                if str(next_value) in "123456789" and len(str(next_value)) == 1:
                    value += int(next_value)
                    index += 1
            digits.append(str(value))
        elif token.isdigit():
            digits.append(token)
        else:
            digits.append(str(NUMBER_WORDS[token]))
    return "".join(digits)


def read_hints():
    """
    Join the non-comment lines of hints.txt into Whisper's initial prompt.
    Read on every call so edits apply without restarting the server.
    """
    if not HINTS_FILE.exists():
        return ""
    lines = HINTS_FILE.read_text(encoding="utf-8").splitlines()
    return " ".join(line.strip() for line in lines if line.strip() and not line.lstrip().startswith("#"))


def load_audio(audio_file):
    """Read a 16-bit PCM WAV file as 16 kHz mono float32 samples."""
    with wave.open(str(audio_file), "rb") as wav_file:
        if wav_file.getsampwidth() != 2:
            raise ValueError(f"Expected 16-bit audio: {audio_file}")
        channels = wav_file.getnchannels()
        sample_rate = wav_file.getframerate()
        frames = wav_file.readframes(wav_file.getnframes())

    audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)
    if sample_rate != SAMPLE_RATE and audio.size:
        divisor = np.gcd(sample_rate, SAMPLE_RATE)
        audio = resample_poly(audio, SAMPLE_RATE // divisor, sample_rate // divisor).astype(np.float32)
    return audio


def performance_core_count():
    """whisper.cpp slows down on efficiency cores, so only count performance cores."""
    try:
        output = subprocess.run(
            ["sysctl", "-n", "hw.perflevel0.physicalcpu"],
            capture_output=True, text=True, check=True, timeout=5,
        ).stdout
        return max(1, int(output.strip()))
    except (OSError, ValueError, subprocess.SubprocessError):
        return min(4, os.cpu_count() or 4)


def ensure_model_file(model_name):
    """
    Download a model if it is missing or incomplete. The file only reaches
    models/ once complete, so an interrupted download cannot crash a later run.
    """
    expected_size = MODEL_SIZES.get(model_name)
    target = MODELS_DIR / f"ggml-{model_name}.bin"
    if target.exists() and expected_size in (None, target.stat().st_size):
        return

    MODELS_DIR.mkdir(exist_ok=True)
    print(f"Downloading Whisper model {model_name}...")
    with tempfile.TemporaryDirectory(dir=MODELS_DIR) as download_dir:
        downloaded = Path(download_model(model_name, download_dir=download_dir))
        if expected_size not in (None, downloaded.stat().st_size):
            raise RuntimeError(f"Download of {model_name} is incomplete.")
        os.replace(downloaded, target)


class TranscriptionManager:
    def __init__(self):
        """
        Initializes the TranscriptionManager class.

        Two whisper.cpp models load in a background thread so the server can
        start right away; status() reports when they are ready.

        - The fast model transcribes MAT answers and the audio check while the
          participant waits. transcribe() returns the result directly.
        - The long model transcribes longer responses once the experimenter
          clicks Process Audio. Nothing else runs during the experiment.

        whisper.cpp contexts are not thread-safe, so each model only runs one
        transcription at a time.
        """
        self.model_params = {
            "n_threads": performance_core_count(),
            "language": "en",
            "print_progress": False,
            "print_realtime": False,
            # False leaves stderr alone. pywhispercpp's redirect covers the whole
            # process, which would hide Flask's output while a model loads.
            "redirect_whispercpp_logs_to": False,
            "context_params": {"use_gpu": True, "flash_attn": True},
        }
        self.models = {FAST_MODEL: None, LONG_MODEL: None}
        self.model_status = {FAST_MODEL: "loading", LONG_MODEL: "loading"}
        self.model_errors = {}
        # Set when loading has finished for that model, whether or not it worked.
        self.model_settled = {FAST_MODEL: threading.Event(), LONG_MODEL: threading.Event()}
        self.operation_lock = threading.Lock()
        self.active_operation = None
        self.long_lock = threading.Lock()

        _pywhispercpp.whisper_log_set(log_whisper_message)
        threading.Thread(target=self._load_models, daemon=True).start()

    def status(self):
        """Report per-model load state for the experiment dashboard."""
        statuses = dict(self.model_status)
        return {
            "models": statuses,
            "ready": all(state == "ready" for state in statuses.values()),
            "failed": any(state == "failed" for state in statuses.values()),
            "errors": dict(self.model_errors),
        }

    def _load_models(self):
        for model_name in (FAST_MODEL, LONG_MODEL):
            try:
                ensure_model_file(model_name)
                start = time.perf_counter()
                model = Model(model_name, models_dir=str(MODELS_DIR), **self.model_params)
                # The first inference compiles GPU shaders; do that before a participant waits on it.
                model.transcribe(np.zeros(SAMPLE_RATE, dtype=np.float32), initial_prompt="")
                self.models[model_name] = model
                self.model_status[model_name] = "ready"
                print(f"Whisper model {model_name} ready in {time.perf_counter() - start:.1f} seconds.")
            except Exception as e:
                self.model_status[model_name] = "failed"
                self.model_errors[model_name] = str(e)
                print(f"Whisper model {model_name} failed to load: {e}")
            finally:
                self.model_settled[model_name].set()

    def _decode(self, model_name, audio, initial_prompt=""):
        """
        Run one model and return its text without bracketed non-speech labels
        such as [BLANK_AUDIO] or (dramatic music).
        """
        self.model_settled[model_name].wait()
        model = self.models[model_name]
        if model is None:
            raise RuntimeError(f"Whisper model {model_name} is not available.")

        # Always pass initial_prompt: pywhispercpp keeps params between calls,
        # so an empty string is what clears the hints.
        segments = model.transcribe(audio, initial_prompt=initial_prompt)
        text = " ".join(segment.text.strip() for segment in segments)
        return re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", text).strip()

    def transcribe(self, audio_file, timeout_seconds=15, digits_only=True):
        """
        Transcribes a short recording with the fast model and waits for the result.
        Args:
            audio_file (str): The path to the audio file to be transcribed.
            timeout_seconds (int): How long to wait before giving up.
            digits_only (bool): True for MAT answers, which use the hints and
                return a plain digit string. False returns ordinary text.
        Returns:
            str: The transcription result of the audio file, or None if nothing usable was heard.
        """
        with self.operation_lock:
            if self.active_operation and self.active_operation["thread"].is_alive():
                print("Whisper model is still processing a previous transcription.")
                return None

            operation = {"done": threading.Event(), "result": None}
            operation["thread"] = threading.Thread(
                target=self._run_transcription,
                args=(audio_file, digits_only, operation),
                daemon=True,
            )
            self.active_operation = operation
            operation["thread"].start()

        if not operation["done"].wait(timeout_seconds):
            print(f"Transcription timed out after {timeout_seconds} seconds for file: {audio_file}")
            return None

        return operation["result"]

    def _run_transcription(self, audio_file, digits_only, operation):
        try:
            start = time.perf_counter()
            audio = load_audio(audio_file)
            if audio.size >= SAMPLE_RATE * MIN_AUDIO_SECONDS:
                if digits_only:
                    operation["result"] = self._transcribe_digits(audio)
                else:
                    operation["result"] = self._decode(FAST_MODEL, audio) or None
            print(f"Fast transcription took {time.perf_counter() - start:.2f} seconds: {operation['result']}")
        except Exception as e:
            print(f"Transcription error: {e}")
        finally:
            operation["done"].set()

    def _transcribe_digits(self, audio):
        # With the hints loaded, Whisper answers silence and background noise
        # with digits (usually "3"). Without them it does not, so only accept a
        # hinted result when the unhinted pass also heard a number.
        unhinted_text = self._decode(FAST_MODEL, audio)
        if not normalize_digits(unhinted_text):
            print(f"No number heard in MAT response: '{unhinted_text}'")
            return None

        hinted_text = self._decode(FAST_MODEL, audio, read_hints())
        print(f"Whisper output: '{hinted_text}'")
        return normalize_digits(hinted_text) or None

    def transcribe_long(self, audio_file):
        """
        Transcribes a longer recording with the long model and waits for the result.
        Args:
            audio_file (str): The path to the audio file to be transcribed.
        Returns:
            str: The transcription result of the audio file, or None if nothing usable was heard.
        """
        with self.long_lock:
            try:
                start = time.perf_counter()
                audio = load_audio(audio_file)
                result = None
                if audio.size >= SAMPLE_RATE * MIN_AUDIO_SECONDS:
                    result = self._decode(LONG_MODEL, audio) or None
                print(f"Long transcription took {time.perf_counter() - start:.1f} seconds: {audio_file}")
                return result
            except Exception as e:
                print(f"Transcription error for {audio_file}: {e}")
                return None
