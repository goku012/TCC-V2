import platform, time, threading
from ctypes import POINTER, cast

try:
    from comtypes import CLSCTX_ALL  # type: ignore
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume  # type: ignore
    _PYCAW_IMPORTED = True
except Exception:
    _PYCAW_IMPORTED = False

from .com_guard import ComGuard

class AudioBackend:
    def __init__(self):
        self._audio_volume = None
        if platform.system() == "Windows" and _PYCAW_IMPORTED:
            try:
                devices = AudioUtilities.GetSpeakers()
                interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                self._audio_volume = cast(interface, POINTER(IAudioEndpointVolume))
            except Exception:
                self._audio_volume = None

    def available(self) -> bool:
        return self._audio_volume is not None

    def get_percent(self) -> float:
        if not self.available():
            raise RuntimeError("Sem backend de áudio")
        scalar = self._audio_volume.GetMasterVolumeLevelScalar()
        return float(scalar) * 100.0

    def set_percent(self, pct: float):
        if not self.available():
            raise RuntimeError("Sem backend de áudio")
        pct = max(0.0, min(100.0, float(pct)))
        self._audio_volume.SetMasterVolumeLevelScalar(pct / 100.0, None)

class VolumeEnforcer(threading.Thread):
    """Mantém o volume travado em um alvo retornado por uma função (target_fn)."""
    def __init__(self, backend: AudioBackend, target_fn, stop_event: threading.Event, interval=0.07):
        super().__init__(daemon=True)
        self.backend = backend
        self.target_fn = target_fn
        self.stop_event = stop_event
        self.interval = interval

    def run(self):
        with ComGuard():
            while not self.stop_event.is_set():
                try:
                    if self.backend.available():
                        target = float(self.target_fn())
                        current = self.backend.get_percent()
                        if abs(current - target) > 0.5:
                            self.backend.set_percent(target)
                except Exception:
                    pass
                time.sleep(self.interval)
