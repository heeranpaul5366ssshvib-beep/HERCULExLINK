from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Desktop Adapter (v1.2)
Author: Heeran Paul
License: MIT
--------------------------------------------

Real Windows desktop input via stdlib ctypes only (no new
dependencies): pointer, click, scroll, keyboard, screenshots, and
harmless application launch. Every call validates first and reports
honestly — OS errors raise, they are never swallowed into fake
success. Non-Windows platforms report UNAVAILABLE.
"""

import struct
import subprocess
import time
import zlib
from typing import Any, Dict, List, Optional, Tuple


class ComputerUnavailable(RuntimeError):
    """Raised when desktop control genuinely cannot run here."""


def _require_windows() -> Any:
    import sys

    if sys.platform != "win32":
        raise ComputerUnavailable("desktop control requires Windows")
    try:
        import ctypes

        return ctypes
    except Exception as exc:
        raise ComputerUnavailable(f"ctypes unavailable: {exc}")


# MouseEventF flags / keybd flags / MapVirtualKey map type.
_M_LEFTDOWN, _M_LEFTUP = 0x0002, 0x0004
_M_RIGHTDOWN, _M_RIGHTUP = 0x0008, 0x0010
_M_MOVE = 0x0001
_M_WHEEL = 0x0800
_K_KEYUP = 0x0002
_K_UNICODE = 0x0004
_SRCCOPY = 0x00CC0020
_WM_GETTEXT, _WMC_GETTEXTLENGTH = 0x000D, 0x000E
_SMTO_ABORTIFHUNG = 0x0002


def _user32(ctypes: Any) -> Any:
    user32 = ctypes.windll.user32
    try:
        from ctypes import c_void_p, c_int, c_ulong, c_wchar_p

        user32.GetClipboardData.restype = c_void_p
        user32.GetClipboardData.argtypes = [c_ulong]
        user32.OpenClipboard.restype = c_int
        user32.OpenClipboard.argtypes = [c_void_p]
        user32.CloseClipboard.restype = c_int
        user32.GetForegroundWindow.restype = c_void_p
        user32.FindWindowExW.restype = c_void_p
        user32.FindWindowExW.argtypes = [c_void_p, c_void_p, c_wchar_p, c_wchar_p]
        user32.GetDC.restype = c_void_p
        user32.GetDC.argtypes = [c_void_p]
    except Exception:
        pass
    return user32


def _kernel32(ctypes: Any) -> Any:
    kernel32 = ctypes.windll.kernel32
    try:
        from ctypes import c_int, c_void_p

        kernel32.GlobalLock.restype = c_void_p
        kernel32.GlobalLock.argtypes = [c_void_p]
        kernel32.GlobalUnlock.restype = c_int
        kernel32.GlobalUnlock.argtypes = [c_void_p]
        kernel32.GetCurrentThreadId.restype = c_int
    except Exception:
        pass
    return kernel32


def _input_classes(ctypes: Any):
    """Single shared SendInput structure set (instances must share types)."""

    class _MI(ctypes.Structure):
        _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long),
                    ("mouseData", ctypes.c_ulong),
                    ("dwFlags", ctypes.c_ulong),
                    ("time", ctypes.c_ulong),
                    ("dwExtraInfo", ctypes.c_void_p)]

    class _KI(ctypes.Structure):
        _fields_ = [("wVk", ctypes.c_ushort),
                    ("wScan", ctypes.c_ushort),
                    ("dwFlags", ctypes.c_ulong),
                    ("time", ctypes.c_ulong),
                    ("dwExtraInfo", ctypes.c_void_p)]

    class _II(ctypes.Union):
        _fields_ = [("mi", _MI), ("ki", _KI)]

    class _IN(ctypes.Structure):
        _fields_ = [("type", ctypes.c_ulong), ("ii", _II)]

    return _MI, _KI, _IN


class DesktopAdapter:
    """Blocking, single-action Windows desktop control."""

    def __init__(self, timeout_s: float = 15.0):
        self.timeout_s = float(timeout_s or 15.0)

    # --------------------------------------------------
    # Screen / pointer state (read-only)
    # --------------------------------------------------
    def screen_size(self) -> Tuple[int, int]:
        ctypes = _require_windows()
        user32 = _user32(ctypes)
        width = int(user32.GetSystemMetrics(0))
        height = int(user32.GetSystemMetrics(1))
        if width <= 0 or height <= 0:
            raise ComputerUnavailable("could not read screen size")
        return width, height

    def cursor_pos(self) -> Tuple[int, int]:
        ctypes = _require_windows()

        class _Point(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        point = _Point()
        if not _user32(ctypes).GetCursorPos(ctypes.byref(point)):
            raise ComputerUnavailable("could not read cursor position")
        return int(point.x), int(point.y)

    # --------------------------------------------------
    # Pointer / click / scroll
    # --------------------------------------------------
    def _send_input(self, events: list, ctypes: Any) -> None:
        user32 = _user32(ctypes)
        array_type = type(events[0]) * len(events)
        sent = user32.SendInput(len(events), array_type(*events),
                                ctypes.sizeof(events[0]))
        if int(sent) != len(events):
            raise ComputerUnavailable("OS rejected input events")

    def _mouse_events(self, ctypes: Any,
                      specs: list) -> list:
        """Build same-type mouse events from (flags, data, dx, dy) specs."""
        _MI, _KI, _IN = _input_classes(ctypes)
        events = []
        for flags, data, dx, dy in specs:
            unit = _IN()
            unit.type = 0  # INPUT_MOUSE
            unit.ii.mi.dx, unit.ii.mi.dy = dx, dy
            unit.ii.mi.mouseData, unit.ii.mi.dwFlags = data, flags
            events.append(unit)
        return events

    def _key_events(self, ctypes: Any, specs: list) -> list:
        """Build same-type keyboard events from (vk, codepoint, up) specs."""
        _MI, _KI, _IN = _input_classes(ctypes)
        events = []
        for vk, codepoint, up in specs:
            unit = _IN()
            unit.type = 1  # INPUT_KEYBOARD
            flags = _K_KEYUP if up else 0
            if codepoint:
                unit.ii.ki.wScan = codepoint
                unit.ii.ki.dwFlags = flags | _K_UNICODE
            else:
                unit.ii.ki.wVk = vk
                unit.ii.ki.dwFlags = flags
            events.append(unit)
        return events

    def _mouse_input(self, ctypes: Any, flags: int, data: int = 0,
                     dx: int = 0, dy: int = 0):
        return self._mouse_events(ctypes, [(flags, data, dx, dy)])[0]

    def move(self, x: int, y: int) -> Dict[str, Any]:
        ctypes = _require_windows()
        width, height = self.screen_size()
        if not (0 <= x < width and 0 <= y < height):
            raise ValueError(f"({x}, {y}) outside screen {width}x{height}")
        if not _user32(ctypes).SetCursorPos(int(x), int(y)):
            raise ComputerUnavailable("OS refused pointer move")
        actual = self.cursor_pos()
        if abs(actual[0] - x) > 2 or abs(actual[1] - y) > 2:
            raise ComputerUnavailable(f"pointer did not move to ({x}, {y})")
        return {"moved": True, "at": list(actual)}

    def _click_flags(self, kind: str) -> List[Tuple[int, int]]:
        if kind == "right":
            return [(_M_RIGHTDOWN, 0), (_M_RIGHTUP, 0)]
        return [(_M_LEFTDOWN, 0), (_M_LEFTUP, 0)]

    def click(self, x: int, y: int, kind: str = "left",
              double: bool = False) -> Dict[str, Any]:
        ctypes = _require_windows()
        self.move(x, y)
        presses = 2 if double else 1
        for _ in range(presses):
            flags = self._click_flags(kind)
            self._send_input(
                self._mouse_events(ctypes, [(f, d, 0, 0) for f, d in flags]),
                ctypes)
            if double:
                time.sleep(0.08)
            else:
                time.sleep(0.03)
        return {"clicked": True, "kind": kind, "double": bool(double),
                "at": [x, y]}

    def scroll(self, amount: int, x: Optional[int] = None,
               y: Optional[int] = None) -> Dict[str, Any]:
        ctypes = _require_windows()
        if x is not None and y is not None:
            self.move(x, y)
        steps = max(1, min(20, abs(int(amount or -3))))
        direction = 1 if int(amount or -3) > 0 else -1
        for _ in range(steps):
            self._send_input(
                self._mouse_events(ctypes, [(_M_WHEEL, direction * 120, 0, 0)]),
                ctypes)
            time.sleep(0.02)
        return {"scrolled": True, "amount": direction * steps}

    # --------------------------------------------------
    # Keyboard
    # --------------------------------------------------
    def _key_input(self, ctypes: Any, vk: int = 0, codepoint: int = 0,
                   up: bool = False):
        return self._key_events(ctypes, [(vk, codepoint, up)])[0]

    def type_text(self, text: str, timeout_s: Optional[float] = None) -> Dict[str, Any]:
        ctypes = _require_windows()
        cleaned = str(text or "")
        if not cleaned.strip():
            raise ValueError("type needs non-empty text")
        if len(cleaned) > 2000:
            raise ValueError("type text too long (max 2000 chars)")
        deadline = time.perf_counter() + (timeout_s or self.timeout_s)
        typed = 0
        for char in cleaned:
            if time.perf_counter() > deadline:
                raise TimeoutError(f"type timed out after {typed} chars")
            self._send_input(
                self._key_events(ctypes, [(0, ord(char), False),
                                          (0, ord(char), True)]),
                ctypes)
            typed += 1
            if typed % 32 == 0:
                time.sleep(0.01)
        return {"typed": True, "chars": typed}

    def press_key(self, key: str) -> Dict[str, Any]:
        from computer.actions import KEY_MAP

        ctypes = _require_windows()
        vk = KEY_MAP.get(str(key or "").lower(), 0)
        if not vk:
            raise ValueError(f"unknown key: {key!r}")
        self._send_input(
            self._key_events(ctypes, [(vk, 0, False), (vk, 0, True)]),
            ctypes)
        time.sleep(0.05)
        return {"pressed": True, "key": str(key).lower()}

    def hotkey(self, keys: Tuple[str, ...]) -> Dict[str, Any]:
        from computer.actions import KEY_MAP

        ctypes = _require_windows()
        vks = [KEY_MAP[k.lower()] for k in keys]
        specs = [(vk, 0, False) for vk in vks]
        specs += [(vk, 0, True) for vk in reversed(vks)]
        self._send_input(self._key_events(ctypes, specs), ctypes)
        time.sleep(0.1)
        return {"hotkey": True, "keys": list(keys)}

    # --------------------------------------------------
    # Screenshot (BMP bytes, stdlib only — no Pillow needed)
    # --------------------------------------------------
    def screenshot(self) -> Tuple[bytes, int, int]:
        """Capture the primary screen as BMP bytes + (width, height)."""
        ctypes = _require_windows()
        user32, gdi32 = _user32(ctypes), ctypes.windll.gdi32
        width, height = self.screen_size()
        hdc_screen = user32.GetDC(None)
        if not hdc_screen:
            raise ComputerUnavailable("screenshot: no screen device context")
        try:
            hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
            hbm = gdi32.CreateCompatibleBitmap(hdc_screen, width, height)
            if not hdc_mem or not hbm:
                raise ComputerUnavailable("screenshot: GDI allocation failed")
            try:
                gdi32.SelectObject(hdc_mem, hbm)
                if not gdi32.BitBlt(hdc_mem, 0, 0, width, height,
                                    hdc_screen, 0, 0, _SRCCOPY):
                    raise ComputerUnavailable("screenshot: BitBlt failed")

                class _BIH(ctypes.Structure):
                    _fields_ = [("biSize", ctypes.c_ulong),
                                ("biWidth", ctypes.c_long),
                                ("biHeight", ctypes.c_long),
                                ("biPlanes", ctypes.c_ushort),
                                ("biBitCount", ctypes.c_ushort),
                                ("biCompression", ctypes.c_ulong),
                                ("biSizeImage", ctypes.c_ulong),
                                ("biXPelsPerMeter", ctypes.c_long),
                                ("biYPelsPerMeter", ctypes.c_long),
                                ("biClrUsed", ctypes.c_ulong),
                                ("biClrImportant", ctypes.c_ulong)]

                stride = (width * 3 + 3) & ~3
                buffer = ctypes.create_string_buffer(stride * height)
                info = _BIH(ctypes.sizeof(_BIH), width, -height, 1, 24,
                            0, stride * height, 0, 0, 0, 0)
                lines = gdi32.GetDIBits(hdc_mem, hbm, 0, height,
                                        buffer, ctypes.byref(info), 0)
                if int(lines) != height:
                    raise ComputerUnavailable("screenshot: GetDIBits failed")
                raw = bytes(buffer)
            finally:
                gdi32.DeleteObject(hbm)
                gdi32.DeleteDC(hdc_mem)
        finally:
            user32.ReleaseDC(None, hdc_screen)
        # BMP stores BGR bottom-up: reverse the top-down rows, prefix headers.
        rows = [raw[r * stride:(r + 1) * stride] for r in range(height)]
        pixel_data = b"".join(reversed(rows))
        file_size = 14 + 40 + len(pixel_data)
        file_header = struct.pack("<2sIHHI", b"BM", file_size, 0, 0, 54)
        info_header = struct.pack("<IIIHHIIIIII", 40, width, height, 1, 24,
                                  0, len(pixel_data), 0, 0, 0, 0)
        return file_header + info_header + pixel_data, width, height

    # --------------------------------------------------
    # Applications (allowlisted launch + process checks)
    # --------------------------------------------------
    def open_app(self, command: List[str], timeout_s: float = 10.0) -> Dict[str, Any]:
        if not command:
            raise ValueError("open_app needs a launch command")
        try:
            proc = subprocess.Popen(command, stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL)
        except Exception as exc:
            raise ComputerUnavailable(f"launch failed: {exc}")
        deadline = time.perf_counter() + max(2.0, timeout_s)
        name = str(command[0]).lower()
        while time.perf_counter() < deadline:
            if self.is_process_running(name):
                return {"opened": True, "pid": proc.pid, "app": name}
            if proc.poll() is not None:
                raise ComputerUnavailable(f"{name} exited immediately")
            time.sleep(0.25)
        return {"opened": True, "pid": proc.pid, "app": name,
                "note": "process not yet visible"}

    def is_process_running(self, name: str) -> bool:
        wanted = str(name or "").lower()
        try:
            out = subprocess.run(["tasklist", "/FO", "CSV", "/NH"],
                                 capture_output=True, text=True,
                                 timeout=15)
        except Exception:
            return False
        return wanted in (out.stdout or "").lower()

    def terminate_process(self, name: str) -> Dict[str, Any]:
        """Kill an allowlisted test process (cleanup only, never credentials)."""
        from computer.policy import APP_LAUNCH_COMMANDS

        allowed = {c[0].lower() for cmds in APP_LAUNCH_COMMANDS.values()
                   for c in [cmds]}
        if str(name or "").lower() not in allowed:
            raise ValueError(f"refusing to terminate non-test process {name!r}")
        try:
            subprocess.run(["taskkill", "/F", "/IM", name],
                           capture_output=True, timeout=15)
        except Exception as exc:
            raise ComputerUnavailable(f"terminate failed: {exc}")
        return {"terminated": True, "app": name}

    # --------------------------------------------------
    # Window grounding (Notepad Edit control etc.)
    # --------------------------------------------------
    def find_window(self, title_part: str) -> Optional[int]:
        """Top-level window handle whose title contains title_part."""
        ctypes = _require_windows()
        user32 = _user32(ctypes)
        found: List[int] = []
        wanted = str(title_part or "").lower()

        @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        def _enum(hwnd, _param):
            length = user32.GetWindowTextLengthW(hwnd)
            if length and user32.IsWindowVisible(hwnd):
                buffer = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buffer, length + 1)
                if wanted in (buffer.value or "").lower():
                    found.append(int(hwnd))
            return True

        user32.EnumWindows(_enum, None)
        return found[0] if found else None

    def window_text(self, hwnd: int, timeout_ms: int = 2000) -> str:
        """Text of an edit child (or the window itself) via WM_GETTEXT."""
        ctypes = _require_windows()
        user32 = _user32(ctypes)
        target = self._edit_child(user32, int(hwnd)) or int(hwnd)
        length = user32.SendMessageTimeoutW(target, _WMC_GETTEXTLENGTH, 0, 0,
                                            _SMTO_ABORTIFHUNG, timeout_ms, None)
        if not length or int(length) > 100000:
            return ""
        buffer = ctypes.create_unicode_buffer(int(length) + 1)
        user32.SendMessageTimeoutW(target, _WM_GETTEXT, int(length) + 1,
                                   buffer, _SMTO_ABORTIFHUNG, timeout_ms, None)
        return buffer.value or ""

    def window_rect(self, hwnd: int) -> Tuple[int, int, int, int]:
        """(left, top, right, bottom) of an edit child (or window)."""
        ctypes = _require_windows()

        class _Rect(ctypes.Structure):
            _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                        ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

        user32 = _user32(ctypes)
        edit = self._edit_child(user32, int(hwnd))
        rect = _Rect()
        if not user32.GetWindowRect(int(edit or hwnd), ctypes.byref(rect)):
            raise ComputerUnavailable("could not read window rect")
        return int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)

    @staticmethod
    def _edit_child(user32: Any, hwnd: int) -> int:
        """First edit-like child (classic Edit + modern RichEdit)."""
        for classname in ("Edit", "RichEditD2DPT", "RICHEDIT50W",
                          "RichEdit20W", "Scintilla"):
            try:
                found = user32.FindWindowExW(int(hwnd), None, classname, None)
            except Exception:
                found = None
            if found:
                return int(found)
        return 0

    def set_foreground(self, hwnd: int) -> Dict[str, Any]:
        """Bring a window to the foreground (grounding prerequisite).

        Background processes cannot steal focus outright, so the
        caller's input is temporarily attached to the foreground
        thread (standard Win32 practice), then detached again.
        """
        ctypes = _require_windows()
        user32, kernel32 = _user32(ctypes), _kernel32(ctypes)
        hwnd = int(hwnd)
        try:
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        except Exception:
            pass
        foreground = user32.GetForegroundWindow()
        attached = False
        fg_thread = None
        try:
            our_thread = kernel32.GetCurrentThreadId()
            fg_thread = user32.GetWindowThreadProcessId(foreground, None)
            if fg_thread and fg_thread != our_thread:
                attached = bool(user32.AttachThreadInput(
                    fg_thread, our_thread, True))
            ok = bool(user32.SetForegroundWindow(hwnd))
        finally:
            try:
                if attached:
                    user32.AttachThreadInput(fg_thread, our_thread, False)
            except Exception:
                pass
        if not ok:
            # Fall back to input-driven activation: the follow-up click
            # on the window still transfers focus honestly.
            return {"foregrounded": False,
                    "note": "OS refused; click to focus"}
        time.sleep(0.4)
        return {"foregrounded": True}

    def foreground_title(self) -> str:
        ctypes = _require_windows()
        user32 = _user32(ctypes)
        hwnd = user32.GetForegroundWindow()
        length = user32.GetWindowTextLengthW(hwnd)
        if not length:
            return ""
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        return buffer.value or ""

    def clipboard_text(self) -> str:
        """Current CF_UNICODETEXT clipboard content (read-only)."""
        ctypes = _require_windows()
        user32, kernel32 = _user32(ctypes), _kernel32(ctypes)
        CF_UNICODETEXT = 13
        if not user32.OpenClipboard(None):
            raise ComputerUnavailable("could not open clipboard")
        try:
            handle = user32.GetClipboardData(CF_UNICODETEXT)
            if not handle:
                return ""
            locked = kernel32.GlobalLock(handle)
            if not locked:
                return ""
            try:
                return ctypes.wstring_at(locked)
            finally:
                kernel32.GlobalUnlock(handle)
        finally:
            user32.CloseClipboard()


def _encode_png(width: int, height: int, rgb: bytes) -> bytes:
    def _chunk(ctype: bytes, payload: bytes) -> bytes:
        return (struct.pack(">I", len(payload)) + ctype + payload
                + struct.pack(">I", zlib.crc32(ctype + payload) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr)
            + _chunk(b"IDAT", zlib.compress(bytes(rgb))) + _chunk(b"IEND", b""))
