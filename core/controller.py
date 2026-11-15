"""
Bộ điều khiển hệ thống, chuột, bàn phím và cửa sổ Windows
Cung cấp khả năng thao tác siêu tốc và xử lý gõ tiếng Việt hoàn hảo.
"""

import subprocess
import time
import win32gui
import win32con
import win32process
import pyautogui
import pyperclip
from core.safety import safety
from config import config

# Thiết lập pyautogui an toàn
pyautogui.PAUSE = 0.05
pyautogui.FAILSAFE = True


class SystemController:
    def __init__(self):
        pass

    # ----------------------------------------------------
    # TẦNG 1: THỰC THI HỆ THỐNG SIÊU TỐC (POWERSHELL / CLI)
    # ----------------------------------------------------
    def run_powershell(self, command: str, timeout: int = 30) -> dict:
        """
        Chạy một lệnh PowerShell trực tiếp trên hệ thống Windows.
        Tốc độ siêu nhanh (vài mili-giây), dùng để mở app, tạo/đọc/xóa file, chạy script.
        """
        if safety.is_stopped():
            return {"success": False, "error": safety.get_stop_reason()}

        if config.safe_mode:
            is_safe, reason = safety.check_command_safety(command)
            if not is_safe:
                return {"success": False, "error": reason}

        try:
            # Dùng powershell.exe chạy lệnh
            process = subprocess.Popen(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", command],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace"
            )
            stdout, stderr = process.communicate(timeout=timeout)
            ret_code = process.returncode

            # Giới hạn độ dài output để tránh quá tải token
            if len(stdout) > 2500:
                stdout = stdout[:2500] + "\n...[Nội dung còn lại đã được cắt ngắn]"

            return {
                "success": ret_code == 0,
                "returncode": ret_code,
                "stdout": stdout.strip(),
                "stderr": stderr.strip()
            }
        except subprocess.TimeoutExpired:
            process.kill()
            return {"success": False, "error": f"Lệnh bị timeout sau {timeout} giây."}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ----------------------------------------------------
    # QUẢN LÝ CỬA SỔ & TIẾN TRÌNH WINDOWS
    # ----------------------------------------------------
    def list_visible_windows(self) -> list[dict]:
        """Lấy danh sách các cửa sổ đang hiển thị trên màn hình"""
        windows = []

        def enum_handler(hwnd, extra):
            if win32gui.IsWindowVisible(hwnd) and not win32gui.IsIconic(hwnd):
                title = win32gui.GetWindowText(hwnd).strip()
                if title:
                    rect = win32gui.GetWindowRect(hwnd)
                    # Bỏ qua các cửa sổ kích thước rỗng
                    if rect[2] - rect[0] > 10 and rect[3] - rect[1] > 10:
                        windows.append({
                            "hwnd": hwnd,
                            "title": title,
                            "rect": {"left": rect[0], "top": rect[1], "right": rect[2], "bottom": rect[3]}
                        })
            return True

        try:
            win32gui.EnumWindows(enum_handler, None)
        except Exception:
            pass
        return windows

    def get_foreground_window(self) -> dict:
        """Lấy thông tin cửa sổ đang được active (focus) hiện tại"""
        try:
            hwnd = win32gui.GetForegroundWindow()
            title = win32gui.GetWindowText(hwnd).strip()
            rect = win32gui.GetWindowRect(hwnd)
            return {
                "hwnd": hwnd,
                "title": title,
                "rect": {"left": rect[0], "top": rect[1], "right": rect[2], "bottom": rect[3]}
            }
        except Exception as e:
            return {"title": "Unknown", "error": str(e)}

    def focus_window_by_title(self, keyword: str) -> bool:
        """Tìm và kích hoạt cửa sổ có tiêu đề chứa keyword lên trên cùng"""
        windows = self.list_visible_windows()
        keyword_lower = keyword.lower()
        for w in windows:
            if keyword_lower in w["title"].lower():
                hwnd = w["hwnd"]
                try:
                    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                    win32gui.SetForegroundWindow(hwnd)
                    time.sleep(0.2)
                    return True
                except Exception:
                    # Đôi khi Windows chặn SetForegroundWindow, dùng trick gửi phím Alt
                    try:
                        pyautogui.press("alt")
                        win32gui.SetForegroundWindow(hwnd)
                        return True
                    except Exception:
                        return False
        return False

    # ----------------------------------------------------
    # ĐIỀU KHIỂN CHUỘT (MOUSE)
    # ----------------------------------------------------
    def mouse_click(self, x: int, y: int, button: str = "left", clicks: int = 1) -> bool:
        """Di chuyển chuột và click tại tọa độ (x, y)"""
        if safety.is_stopped():
            return False
        try:
            pyautogui.moveTo(x, y, duration=0.15)
            pyautogui.click(x=x, y=y, button=button, clicks=clicks)
            time.sleep(config.action_delay)
            return True
        except pyautogui.FailSafeException:
            safety.stop("Kích hoạt FailSafe do di chuột vào góc màn hình!")
            return False
        except Exception:
            return False

    def mouse_double_click(self, x: int, y: int) -> bool:
        """Nhấp đúp chuột (Double Click) tại tọa độ (x, y) để mở tệp hoặc kích hoạt thao tác kép"""
        if safety.is_stopped():
            return False
        try:
            pyautogui.moveTo(x, y, duration=0.15)
            pyautogui.doubleClick(x=x, y=y)
            time.sleep(config.action_delay)
            return True
        except pyautogui.FailSafeException:
            safety.stop("Kích hoạt FailSafe do di chuột vào góc màn hình!")
            return False
        except Exception:
            return False

    def mouse_right_click(self, x: int, y: int) -> bool:
        """Nhấp chuột phải (Right Click) tại tọa độ (x, y) để mở Context Menu"""
        if safety.is_stopped():
            return False
        try:
            pyautogui.moveTo(x, y, duration=0.15)
            pyautogui.rightClick(x=x, y=y)
            time.sleep(config.action_delay)
            return True
        except pyautogui.FailSafeException:
            safety.stop("Kích hoạt FailSafe do di chuột vào góc màn hình!")
            return False
        except Exception:
            return False

    def mouse_move(self, x: int, y: int) -> bool:
        """Di chuyển chuột đến tọa độ (x, y) (Hover chuột để xem tooltip hoặc mở menu ẩn)"""
        if safety.is_stopped():
            return False
        try:
            pyautogui.moveTo(x, y, duration=0.15)
            return True
        except Exception:
            return False

    def mouse_drag(self, start_x: int, start_y: int, end_x: int, end_y: int, duration: float = 0.5) -> bool:
        """Kéo thả chuột từ (start_x, start_y) tới (end_x, end_y) mượt mà chuẩn xác cho game và đồ họa"""
        if safety.is_stopped():
            return False
        try:
            # 1. Kích hoạt cửa sổ và chọn đối tượng nguồn (Click tại nguồn)
            pyautogui.moveTo(start_x, start_y, duration=0.15)
            pyautogui.click(start_x, start_y)
            time.sleep(0.12)

            # 2. Nhấn giữ chuột trái và kéo mượt mà tới đích
            pyautogui.mouseDown(start_x, start_y, button="left")
            time.sleep(0.12)
            pyautogui.moveTo(end_x, end_y, duration=max(0.35, duration))
            time.sleep(0.18)
            pyautogui.mouseUp(end_x, end_y, button="left")
            time.sleep(0.12)

            # 3. Click tại đích để kích hoạt cơ chế Tap-to-Move (trong trường hợp game chỉ nhận click-click)
            pyautogui.click(end_x, end_y)
            time.sleep(config.action_delay)
            return True
        except pyautogui.FailSafeException:
            safety.stop("Kích hoạt FailSafe do di chuột vào góc màn hình!")
            return False
        except Exception:
            return False

    def mouse_scroll(self, clicks: int) -> bool:
        """Cuộn trang: clicks > 0 cuộn lên, clicks < 0 cuộn xuống"""
        if safety.is_stopped():
            return False
        try:
            pyautogui.scroll(clicks)
            time.sleep(config.action_delay)
            return True
        except Exception:
            return False

    # ----------------------------------------------------
    # ĐIỀU KHIỂN BÀN PHÍM (KEYBOARD & TIẾNG VIỆT CHUẨN)
    # ----------------------------------------------------
    def type_text(self, text: str, paste_mode: bool = True) -> bool:
        """
        Nhập văn bản.
        Mặc định sử dụng Clipboard + Ctrl+V:
        -> Chuẩn 100% tiếng Việt có dấu, emoji, ký tự đặc biệt,
        -> Không bao giờ bị Unikey/EVKey làm nhảy chữ hay lỗi dấu!
        """
        if safety.is_stopped():
            return False
        try:
            if paste_mode:
                # Lưu clipboard cũ
                old_clipboard = pyperclip.paste()
                pyperclip.copy(text)
                time.sleep(0.05)
                pyautogui.hotkey("ctrl", "v")
                time.sleep(0.05)
            else:
                pyautogui.write(text, interval=0.02)
            time.sleep(config.action_delay)
            return True
        except Exception:
            return False

    def press_key(self, key: str) -> bool:
        """Nhấn một phím đơn (enter, esc, backspace, tab, space, up, down...)"""
        if safety.is_stopped():
            return False
        try:
            pyautogui.press(key)
            time.sleep(config.action_delay)
            return True
        except Exception:
            return False

    def hotkey(self, *keys) -> bool:
        """Nhấn tổ hợp phím (ví dụ: 'ctrl', 'c' hoặc 'alt', 'tab' hoặc 'win', 'r')"""
        if safety.is_stopped():
            return False
        try:
            pyautogui.hotkey(*keys)
            time.sleep(config.action_delay)
            return True
        except Exception:
            return False


controller = SystemController()
