# voice_manager.py

import queue
import json
import sounddevice as sd
from vosk import Model, KaldiRecognizer
from PyQt5.QtCore import QThread, pyqtSignal

class VoiceManager(QThread):
    """
    Runs Vosk STT on the mic once triggered.
    Emits `commandRecognized` with the final text.
    """
    commandRecognized = pyqtSignal(str)

    def __init__(self,
                 model_path: str = "models/vosk-model-small-en-us-0.15"):
        super().__init__()
        self.q = queue.Queue()
        try:
            self.model = Model(model_path)
            self.rec = KaldiRecognizer(self.model, 16000)
            self.running = False
        except Exception as e:
            print(f"⚠️ VoiceManager init failed: {e}")
            self.rec = None
            self.running = False

    def start_listening(self):
        if not self.rec:
            return
        self.running = True
        self.start()

    def run(self):
        def callback(indata, frames, time, status):
            self.q.put(bytes(indata))

        with sd.RawInputStream(
            samplerate=16000, blocksize=8000,
            dtype='int16', channels=1,
            callback=callback
        ):
            while self.running:
                data = self.q.get()
                if self.rec.AcceptWaveform(data):
                    res = json.loads(self.rec.Result())
                    text = res.get("text","").strip()
                    if text:
                        self.commandRecognized.emit(text)
                        break
        self.running = False

    def stop(self):
        self.running = False
        self.wait()
