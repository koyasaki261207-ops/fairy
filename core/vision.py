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
from config import config

SCREENSHOTS_DIR = Path(__file__).resolve().parent.parent / "logs" / "screenshots"


class VisionManager:
    def __init__(self):
        self._sct = None
        self.screen_width, self.screen_height = pyautogui.size()

    def get_screen_size(self) -> tuple[int, int]:
        """Cập nhật và lấy kích thước màn hình hiện tại"""
        self.screen_width, self.screen_height = pyautogui.size()
        return self.screen_width, self.screen_height

    def _grab(self) -> Image.Image:
        """Chụp màn hình chính bằng MSS siêu tốc (fallback ImageGrab, cuối cùng là ảnh báo lỗi)."""
        if HAS_MSS:
            try:
                factory = getattr(mss, "MSS", None) or mss.mss
                with factory() as sct:
                    # Monitor 1 thường là màn hình chính
                    monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
                    sct_img = sct.grab(monitor)
                    return Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
            except Exception:
                pass
        try:
            from PIL import ImageGrab
            return ImageGrab.grab()
        except Exception as e:
            # Môi trường không có GUI display (headless): tạo ảnh thông báo lỗi để không sập luồng
            img = Image.new("RGB", (self.screen_width, self.screen_height), color=(30, 30, 30))
            ImageDraw.Draw(img).text((50, 50), f"Không thể chụp màn hình: {e}", fill=(255, 100, 100))
            return img

    @staticmethod
    def _downscale(img: Image.Image, max_dimension: int) -> Image.Image:
        w, h = img.size
        if max(w, h) <= max_dimension:
            return img
        scale = max_dimension / max(w, h)
        return img.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)

    def capture_screen(self, max_dimension: int = 1600, quality: int = 80) -> tuple[Image.Image, Path | None]:
        """Chụp màn hình (ảnh gốc) và lưu bản thu nhỏ vào logs/screenshots."""
        self.get_screen_size()
        pil_img = self._grab()
        save_path = SCREENSHOTS_DIR / f"screen_{time.strftime('%Y%m%d_%H%M%S')}.jpg"
        try:
            SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
            self._downscale(pil_img, max_dimension).save(save_path, "JPEG", quality=quality)
        except Exception:
            save_path = None
        return pil_img, save_path

    def capture_screen_bytes(self, max_dimension: int | None = None, quality: int | None = None) -> tuple[bytes, int, int]:
        """
        Chụp màn hình và trả về JPEG đã THU NHỎ (cạnh dài <= max_dimension) để gửi lên AI,
        kèm kích thước thực của màn hình. Ảnh nhỏ hơn = ít token hơn + upload nhanh hơn.
        Tọa độ dùng thang chuẩn hóa 0-1000 nên việc thu nhỏ không làm lệch thao tác chuột.
        """
        max_dimension = max_dimension or config.screenshot_max_dim
        quality = quality or config.screenshot_quality
        w, h = self.get_screen_size()
        img = self._downscale(self._grab(), max_dimension)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        data = buf.getvalue()

        if config.save_screenshots:
            try:
                SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
                (SCREENSHOTS_DIR / f"screen_{time.strftime('%Y%m%d_%H%M%S')}.jpg").write_bytes(data)
            except Exception:
                pass
        return data, w, h

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
