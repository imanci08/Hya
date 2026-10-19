"""Optional KDE public-API blur bridge; no compositor hacks or screenshot blur."""
import ctypes
from runtime_paths import asset
from PySide6.QtWidgets import QApplication
from shiboken6 import getCppPointer

_bridge=None


def request_blur(widget):
    global _bridge
    if QApplication.platformName() not in ('wayland','xcb'):return False
    window=widget.windowHandle()
    path=asset('native/libhya-effects.so')
    if window is None or not path.is_file():return False
    try:
        if _bridge is None:
            _bridge=ctypes.CDLL(str(path))
            _bridge.hya_blur.argtypes=(ctypes.c_void_p,ctypes.c_int,ctypes.c_int)
            _bridge.hya_blur.restype=None
        _bridge.hya_blur(getCppPointer(window)[0],widget.width(),widget.height())
        return True  # Request sent, not proof that the compositor applied it.
    except (OSError,AttributeError,RuntimeError):
        return False
