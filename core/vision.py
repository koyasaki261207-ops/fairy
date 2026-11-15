"""
TẦNG 3: MẮT THỊ GIÁC AI (VISION & SCREENSHOT CAPTURE)
Chụp màn hình siêu tốc bằng MSS, tối ưu kích thước ảnh và chuẩn hóa tọa độ cho Gemini.
"""

import io
import time
from pathlib import Path
from PIL import Image, ImageDraw
import pyautogui

try:
    import mss
    HAS_MSS = True
except ImportError:
    HAS_MSS = False

from core.safety import safety

SCREENSHOTS_DIR = Path(__file__).resolve().parent.parent / "logs" / "screenshots"
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)


class VisionManager:
    def __init__(self):
        self._sct = None
        self.screen_width, self.screen_height = pyautogui.size()

    def get_screen_size(self) -> tuple[int, int]:
        """Cập nhật và lấy kích thước màn hình hiện tại"""
        self.screen_width, self.screen_height = pyautogui.size()
        return self.screen_width, self.screen_height

    def capture_screen(self, max_dimension: int = 1600, quality: int = 80) -> tuple[Image.Image, Path | None]:
        """
        Chụp màn hình chính bằng MSS siêu tốc (hoặc fallback ImageGrab).
        Tự động nén để gửi lên Gemini API nhanh nhất và tiết kiệm băng thông.
        """
        pil_img = None
        self.get_screen_size()

        # Thử chụp bằng MSS (nhanh gấp 5-10 lần)
        if HAS_MSS:
            try:
                with mss.MSS() as sct:
                    # Monitor 1 thường là màn hình chính
                    monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
                    sct_img = sct.grab(monitor)
                    pil_img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
            except Exception:
                pil_img = None

        # Fallback bằng PIL ImageGrab nếu MSS lỗi
        if pil_img is None:
            try:
                from PIL import ImageGrab
                pil_img = ImageGrab.grab()
            except Exception as e:
                # Nếu chạy ở môi trường không có GUI display (headless)
                # Tạo một ảnh thông báo lỗi để không làm sập luồng
                pil_img = Image.new("RGB", (self.screen_width, self.screen_height), color=(30, 30, 30))
                draw = ImageDraw.Draw(pil_img)
                draw.text((50, 50), f"Không thể chụp màn hình: {e}", fill=(255, 100, 100))

        # Lưu ảnh tạm thời vào thư mục logs
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        save_path = SCREENSHOTS_DIR / f"screen_{timestamp}.jpg"

        # Tối ưu kích thước nếu màn hình quá lớn (ví dụ 4K)
        w, h = pil_img.size
        if max(w, h) > max_dimension:
            scale = max_dimension / max(w, h)
            new_size = (int(w * scale), int(h * scale))
            img_to_save = pil_img.resize(new_size, Image.Resampling.LANCZOS)
        else:
            img_to_save = pil_img

        try:
            img_to_save.save(save_path, "JPEG", quality=quality)
        except Exception:
            save_path = None

        return pil_img, save_path

    def capture_screen_bytes(self, max_dimension: int = 1280, quality: int = 75) -> tuple[bytes, int, int]:
        """
        Chụp màn hình và trả về dữ liệu ảnh dạng bytes (JPEG) tối ưu,
        kèm kích thước thực tế (width, height) để gửi thẳng cho Gemini Vision.
        """
        pil_img, _ = self.capture_screen(max_dimension=max_dimension, quality=quality)
        w, h = self.get_screen_size()
        buf = io.BytesIO()
        pil_img.save(buf, format="JPEG", quality=quality)
        return buf.getvalue(), w, h

    def denormalize_coordinates(self, x_norm: float, y_norm: float) -> tuple[int, int]:
        """
        Chuyển đổi tọa độ từ thang chuẩn hóa của Gemini (0 đến 1000) về tọa độ pixel thực tế.
        """
        self.get_screen_size()
        actual_x = int((x_norm / 1000.0) * self.screen_width)
        actual_y = int((y_norm / 1000.0) * self.screen_height)
        # Giới hạn trong khung hình
        actual_x = max(0, min(self.screen_width - 1, actual_x))
        actual_y = max(0, min(self.screen_height - 1, actual_y))
        return actual_x, actual_y

    def draw_click_marker(self, image: Image.Image, x: int, y: int) -> Image.Image:
        """Vẽ điểm đỏ đánh dấu vị trí AI vừa click để xem lại nhật ký trực quan"""
        img_copy = image.copy()
        draw = ImageDraw.Draw(img_copy)
        r = 15
        draw.ellipse((x - r, y - r, x + r, y + r), outline="red", width=3)
        draw.line((x - r - 5, y, x + r + 5, y), fill="red", width=2)
        draw.line((x, y - r - 5, x, y + r + 5), fill="red", width=2)
        return img_copy


vision = VisionManager()
