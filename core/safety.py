"""
Module Bảo vệ & Dừng khẩn cấp (Emergency Killswitch) cho Gemini AutoPilot
Giúp người dùng luôn kiểm soát 100% máy tính, ngắt AI ngay tức khắc khi cần.
"""

import threading
import time
import re
import pyautogui
from pynput import keyboard

# Kích hoạt tính năng dừng khẩn cấp khi di chuột vào góc màn hình (0, 0)
pyautogui.FAILSAFE = True

# Danh sách từ khóa lệnh nhạy cảm bị chặn trong chế độ an toàn
DANGEROUS_PATTERNS = [
    r"format\s+[a-zA-Z]:",
    r"remove-item\s+.*-(recurse|force).*c:\\",
    r"del\s+.*\/s.*\/q.*c:\\",
    r"rmdir\s+.*\/s.*\/q.*c:\\",
    r"diskpart",
    r"bcdedit",
    r"reg\s+delete\s+hklm",
    r"shutdown(\.exe)?\s+[\/\-]s",
    r":(){ :|:& };:",  # fork bomb
]


class SafetyManager:
    def __init__(self):
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._stop_reason = ""
        self._listener = None
        self._callbacks = []

    def register_stop_callback(self, cb):
        """Đăng ký hàm gọi lại khi dừng khẩn cấp được kích hoạt (cập nhật UI)"""
        self._callbacks.append(cb)

    def is_stopped(self) -> bool:
        return self._stop_event.is_set()

    def is_paused(self) -> bool:
        return self._pause_event.is_set()

    def stop(self, reason: str = "Người dùng yêu cầu dừng khẩn cấp"):
        self._stop_reason = reason
        self._stop_event.set()
        for cb in self._callbacks:
            try:
                cb(reason)
            except Exception:
                pass

    def pause(self):
        self._pause_event.set()

    def resume(self):
        self._pause_event.clear()

    def reset(self):
        self._stop_event.clear()
        self._pause_event.clear()
        self._stop_reason = ""

    def get_stop_reason(self) -> str:
        return self._stop_reason

    def check_command_safety(self, command: str) -> tuple[bool, str]:
        """Kiểm tra lệnh có an toàn để thực thi không"""
        cmd_lower = command.lower()
        for pattern in DANGEROUS_PATTERNS:
            if re.search(pattern, cmd_lower):
                return False, f"Lệnh bị chặn bởi cơ chế Safe Mode vì có nguy cơ gây hại hệ thống: {command}"
        return True, "An toàn"

    def start_hotkey_listener(self):
        """Khởi động lắng nghe phím nóng F8 hoặc Ctrl+Shift+Q toàn cục"""
        if self._listener is not None and self._listener.is_alive():
            return

        current_keys = set()

        def on_press(key):
            try:
                current_keys.add(key)
                # Phím F8 đơn giản
                if key == keyboard.Key.f8:
                    self.stop("Dừng khẩn cấp bằng phím F8")
                    return

                # Phím nóng Ctrl + Shift + Q
                is_ctrl = any(k in current_keys for k in [keyboard.Key.ctrl_l, keyboard.Key.ctrl_r])
                is_shift = any(k in current_keys for k in [keyboard.Key.shift, keyboard.Key.shift_r])
                is_q = hasattr(key, 'char') and key.char in ('q', 'Q')

                if is_ctrl and is_shift and is_q:
                    self.stop("Dừng khẩn cấp bằng tổ hợp Ctrl+Shift+Q")
            except Exception:
                pass

        def on_release(key):
            try:
                current_keys.discard(key)
            except Exception:
                pass

        self._listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        self._listener.daemon = True
        self._listener.start()


safety = SafetyManager()
