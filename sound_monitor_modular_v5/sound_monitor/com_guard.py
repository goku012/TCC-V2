try:
    import pythoncom  # type: ignore
    _PYTHONCOM_AVAILABLE = True
except Exception:
    pythoncom = None  # type: ignore
    _PYTHONCOM_AVAILABLE = False

class ComGuard:
    """Context manager para CoInitialize/CoUninitialize apenas se disponível."""
    def __enter__(self):
        if _PYTHONCOM_AVAILABLE:
            try: pythoncom.CoInitialize()
            except Exception: pass
        return self
    def __exit__(self, exc_type, exc, tb):
        if _PYTHONCOM_AVAILABLE:
            try: pythoncom.CoUninitialize()
            except Exception: pass

def pythoncom_available():
    return _PYTHONCOM_AVAILABLE
