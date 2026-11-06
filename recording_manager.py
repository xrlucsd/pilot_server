import threading
import pyaudio
import wave
import speech_recognition as sr
from timestamp_manager import TimestampManager

class RecordingManager():
    """
    Handles all recording logic and file read/write for audio files. Also handles
    the setting of system audio device. All handling of audio files post recording
    is handled in the app.py file. Audio processing is handled in the 
    audio_processor.py file.
    """
    def __init__(self, recording_file) -> None: 
        self.audio = pyaudio.PyAudio()
        self.sample_rate = int(self.audio.get_default_input_device_info()['defaultSampleRate'])
        print(f"Default Sample Rate: {self.sample_rate}")
        self.stop_event = threading.Event()
        self.recording_started_event = threading.Event()
        self.stream_ready_event = threading.Event()
        self.recording_thread = None
        self._stream_is_active = False
        # True while a Room Observation or PRS window owns the recording.
        self.task_audio_active = False
        self._recording_file = recording_file
        self.device_index = 0
        self.audio_devices = self.fetch_audio_devices()
        self._timestamp = None
        self._end_timestamp = None
        self.timestamp_manager = TimestampManager()
        print("Recording manager initialized...")
        print(f"Recording manager's temporary recording file set to {self.recording_file}")

    ##################################################################
    ## GENERAL METHODS
    ##################################################################
    @property
    def timestamp(self) -> str:
        return self._timestamp
    
    @timestamp.setter
    def timestamp(self, value) -> None:
        self._timestamp = value
    
    @property
    def end_timestamp(self) -> str:
        return self._end_timestamp
    
    @end_timestamp.setter
    def end_timestamp(self, value) -> None:
        self._end_timestamp = value

    @property
    def recording_file(self) -> str:
        return self._recording_file
    
    @recording_file.setter
    def recording_file(self, recording_file) -> None:
        self._recording_file = recording_file

    @property
    def stream_is_active(self) -> bool:
        return self._stream_is_active
    
    @stream_is_active.setter
    def stream_is_active(self, value) -> None:
        self._stream_is_active = value

    def start_recording(self, task_audio=False) -> None:
        # Anything still recording was never submitted, so it must not reach the
        # new recording's file. Every recording writes to the same temporary file.
        self.cancel_recording()
        self.task_audio_active = task_audio
        self.stop_event.clear()
        self.recording_started_event.set()

        self.timestamp = self.timestamp_manager.get_timestamp("iso")

        self.recording_thread = threading.Thread(target=self.record_thread)
        self.recording_thread.start()
        self.stream_ready_event.wait()
        self.stream_is_active = True
        self.recording_started_event.wait()

        print("Recording thread started")   

    def _validate_device_index(self) -> None:
        """Ensure device_index points to a valid input device"""
        if not self.audio_devices:
            print("Warning: No audio input devices found")
            return
            
        valid_indices = [device['index'] for device in self.audio_devices]
        if self.device_index not in valid_indices:
            print(f"Warning: Device index {self.device_index} not valid, using first available device")
            self.device_index = valid_indices[0] if valid_indices else 0

    def cancel_recording(self) -> None:
        """Stop any active recording without writing its audio to the recording file."""
        self.task_audio_active = False
        if not self.recording_thread or not self.recording_thread.is_alive():
            return

        print("Discarding a recording that was still running.")
        # Replacing the event is how the thread knows to discard: see record_thread.
        active_stop_event = self.stop_event
        self.stop_event = threading.Event()
        active_stop_event.set()
        self.recording_thread.join(timeout=5.0)

        self.recording_started_event.clear()
        self.stream_ready_event.clear()
        self.stream_is_active = False

    def stop_recording(self) -> None:
        self.task_audio_active = False
        self.stop_event.set()

        # Prevent hanging.
        if self.recording_thread:
            self.recording_thread.join(timeout=5.0)

        self.recording_started_event.clear()
        self.stream_ready_event.clear()
        self.stream_is_active = False
        self.end_timestamp = self.timestamp_manager.get_timestamp("iso")
        print(f"Recording stopped at {self.end_timestamp}")

    def reset_audio_system(self):
        try:
            if self.audio is not None:
                self.audio.terminate()
            self.audio = pyaudio.PyAudio()
            self.audio_devices = self.fetch_audio_devices()
            print("Audio system reset successfully.")

        except Exception as e:
                    print(f"Error resetting audio system: {e}")

    def record_thread(self) -> None:
        # The WAV header must match the capture rate, even if the device changes mid-recording.
        rate = self.sample_rate
        stop_event = self.stop_event

        # Validate device before attempting to open stream
        try:
            self._validate_device_index()

            stream = self.audio.open(format=pyaudio.paInt16, 
                                channels=1, 
                                rate=rate,
                                input=True, 
                                input_device_index=self.device_index,
                                frames_per_buffer=1024)
        
        except Exception as e:
            print(f"Error opening audio stream: {e}")
            self.stream_ready_event.set() # TODO: CHECK THE VALIDITY OF THIS
            return
        
        self.stream_ready_event.set()

        frames = []

        self.recording_started_event.set()

        while not stop_event.is_set():
            try:
                data = stream.read(1024)
                frames.append(data)
            except Exception as e:
                print(f"Error reading from audio stream: {e}")
                break
        
        try:
            stream.stop_stream()
            stream.close()    
        except Exception as e:
            print(f"Error closing stream: {e}")

        if stop_event is not self.stop_event:
            print("Recording discarded.")
            return

        try:
            with wave.open(self.recording_file, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(self.audio.get_sample_size(pyaudio.paInt16))
                wf.setframerate(rate)
                wf.writeframes(b''.join(frames))
                print(f"Recording stopped, saved to {self.recording_file}")
        except Exception as e:
            print(f"Error writing to wave file: {e}")

    ##################################################################
    ## GETTERS
    ##################################################################
    def get_stop_event(self) -> threading.Event:
        return self.stop_event
    
    def get_audio_devices(self) -> list:
        return self.audio_devices
    
    ## System call to get audio devices
    def fetch_audio_devices(self) -> list:
        if self.audio is None:
            self.audio = pyaudio.PyAudio()
        
        try:
            audio_devices = [{'index': i, 'name': self.audio.get_device_info_by_index(i)['name']}
                            for i in range(self.audio.get_device_count())
                            if self.audio.get_device_info_by_index(i)['maxInputChannels'] > 0]
        except Exception as e:
            print(f"Error fetching audio devices: {e}")
            audio_devices = []

        return audio_devices

    ##################################################################
    ## SETTERS
    ##################################################################
    def set_device(self, index) -> None:
        valid_indices = [device['index'] for device in self.audio_devices]

        if index not in valid_indices:
            print(f"Invalid device index {index}. Valid indices: {valid_indices}")
            return
        
        self.device_index = index
        self.sample_rate = int(self.audio.get_device_info_by_index(index)['defaultSampleRate'])
        print(f"Device Sample Rate: {self.sample_rate}")

        name = None
        
        for device in self.audio_devices:
            if device['index'] == index:
                name = device['name']
                break
        print(f"Device set to {name if name else 'Unknown (index not in audio_devices list)'}")

    ##################################################################