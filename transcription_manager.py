import whisper
import warnings
import threading
import re

class TranscriptionManager:
    def __init__(self):
        """
        Initializes the TranscriptionManager class.

        This constructor performs the following actions:
        - Suppresses specific warnings related to future changes and FP16 support on CPU.
        - Loads a Whisper model with the "base" configuration.
        - Converts the model to use 32-bit floating point precision.
        - Moves the model to the CPU.
        - Initializes the result attribute to None.
        - Creates a threading lock for managing concurrent access.

        Attributes:
            model (whisper.Model): The Whisper model used for transcription.
            result (None): Placeholder for the transcription result.
            lock (threading.Lock): A lock to ensure thread-safe operations.
        """

        warnings.filterwarnings("ignore", category=FutureWarning)
        warnings.filterwarnings("ignore", message="FP16 is not supported on CPU; using FP32 instead")

        self.model = whisper.load_model("base")
        self.model = self.model.float()
        self.model = self.model.to("cpu")
        self.result = None
        self.lock = threading.Lock()
        self.operation_lock = threading.Lock()
        self.active_operation = None

    def switch_model(self, model_name):
        try:
            model = whisper.load_model(model_name)
            model = model.float()
            model = model.to("cpu")
            with self.lock:
                self.model = model
            print(f"Model switched to {model_name}.")

        except FileNotFoundError:
            print(f"Model {model_name} not found. Please ensure that the model is in the correct directory and that the model name is correct.")

    def reset(self, lock_timeout=0.1):
        """
        Clear the last result without waiting indefinitely for active inference.

        Returns False when Whisper is busy so callers can continue without
        accessing or replacing the shared model during transcription.
        """
        acquired = self.lock.acquire(timeout=lock_timeout)
        if not acquired:
            print("Whisper model is still busy; skipping reset.")
            return False

        try:
            self.result = None
            return True
        finally:
            self.lock.release()

    def transcribe(self, audio_file, timeout_seconds=15):
        """
        Starts the transcription process for the given audio file.
        This method creates a new thread to handle the transcription of the provided
        audio file. It waits for the transcription to complete and then returns the result.
        Args:
            audio_file (str): The path to the audio file to be transcribed.
        Returns:
            str: The transcription result of the audio file, or None if filtered out.
        """
        with self.operation_lock:
            if self.active_operation and self.active_operation["thread"].is_alive():
                print("Whisper model is still processing a previous transcription.")
                return None

            operation = {"done": threading.Event(), "result": None}
            operation["thread"] = threading.Thread(
                target=self._run_transcription,
                args=(audio_file, operation),
                daemon=True,
            )
            self.active_operation = operation
            operation["thread"].start()

        if not operation["done"].wait(timeout_seconds):
            print(f"Transcription timed out after {timeout_seconds} seconds for file: {audio_file}")
            return None

        return operation["result"]

    def _run_transcription(self, audio_file, operation):
        try:
            with self.lock:
                result = self.model.transcribe(
                    audio_file,
                    language="en",
                    no_speech_threshold=0.6,
                    logprob_threshold=-1.0,
                    condition_on_previous_text=False,
                )

            text = result["text"].strip()
            if text and not self._is_likely_invalid(text):
                operation["result"] = text
        except Exception as e:
            print(f"Transcription error: {e}")
        finally:
            operation["done"].set()

    def _is_likely_invalid(self, text):
        """
        Filter out likely hallucinations and non-English content using only built-in libraries
        """
        import re
        
        # 1. Check for excessive repetition (common hallucination pattern)
        words = text.lower().split()
        if len(words) > 2:
            word_counts = {}
            for word in words:
                word_counts[word] = word_counts.get(word, 0) + 1
            max_repetitions = max(word_counts.values())
            # If more than 60% of words are the same word, likely hallucination
            if max_repetitions / len(words) > 0.6:
                return True
        
        # 2. Check character composition
        total_chars = len(text)
        if total_chars == 0:
            return True
        
        # Count different character types
        alpha_chars = len(re.findall(r'[a-zA-Z]', text))
        digit_chars = len(re.findall(r'[0-9]', text))
        space_chars = len(re.findall(r'\s', text))
        punct_chars = len(re.findall(r'[.,!?;:\'"()-]', text))
        
        # Text should be mostly alphabetic, digits, spaces, and basic punctuation
        normal_chars = alpha_chars + digit_chars + space_chars + punct_chars
        normal_ratio = normal_chars / total_chars
        
        # If less than 80% normal characters, likely gibberish
        if normal_ratio < 0.8:
            return True
        
        # 3. Basic English likelihood check using common letter patterns
        # English text should have reasonable vowel distribution
        vowels = len(re.findall(r'[aeiouAEIOU]', text))
        if alpha_chars > 0:
            vowel_ratio = vowels / alpha_chars
            # English typically has 35-45% vowels, but we'll be lenient
            if vowel_ratio < 0.15 or vowel_ratio > 0.7:
                return True
        
        # 4. Check for common non-English character patterns
        # These often appear in Whisper hallucinations
        non_english_patterns = [
            r'[àáâãäåæçèéêëìíîïðñòóôõöøùúûüýþÿ]',  # Romance language accents
            r'[αβγδεζηθικλμνξοπρστυφχψω]',  # Greek
            r'[абвгдежзийклмнопрстуфхцчшщъыьэюя]',  # Cyrillic
            r'[äöüß]',  # German
            r'[\u4e00-\u9fff]',  # Chinese
            r'[\u3040-\u309f\u30a0-\u30ff]',  # Japanese
        ]
        
        for pattern in non_english_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        
        # 5. Check for excessive punctuation or special characters
        special_chars = len(re.findall(r'[^\w\s.,!?;:\'"()-]', text))
        if special_chars / total_chars > 0.2:  # More than 20% special characters
            return True
        
        # 6. Check for very long words (often hallucination artifacts)
        long_words = [word for word in words if len(word) > 20]
        if len(long_words) > 0:
            return True
        
        # 7. Common English word check (lightweight version)
        # Very basic check for at least some common English elements
        common_english_elements = [
            'the', 'and', 'to', 'of', 'a', 'in', 'is', 'it', 'you', 'that',
            'he', 'was', 'for', 'on', 'are', 'as', 'with', 'his', 'they',
            'i', 'at', 'be', 'this', 'have', 'from', 'or', 'one', 'had',
            'by', 'but', 'not', 'what', 'all', 'were', 'we', 'when', 'your',
            'can', 'said', 'there', 'each', 'do', 'if', 'will', 'up', 'out',
            'so', 'about', 'who', 'get', 'which', 'go', 'me', 'when', 'make',
            'can', 'like', 'time', 'no', 'just', 'him', 'know', 'take',
            'people', 'into', 'year', 'your', 'good', 'some', 'could', 'them',
            'see', 'other', 'than', 'then', 'now', 'look', 'only', 'come',
            'its', 'over', 'think', 'also', 'back', 'after', 'use', 'two',
            'how', 'our', 'work', 'first', 'well', 'way', 'even', 'new',
            'want', 'because', 'any', 'these', 'give', 'day', 'most', 'us'
        ]
        
        # For longer text, expect at least some common English words
        if len(words) > 5:
            english_word_count = sum(1 for word in words if word.lower() in common_english_elements)
            english_ratio = english_word_count / len(words)
            # For longer responses, expect at least 20% common English words
            if english_ratio < 0.2:
                return True
        
        return False
                
