"""
BẢNG ĐIỀU KHIỂN AUTOPILOT (CUSTOMTKINTER) - THIẾT KẾ THEO NGÔN NGỮ APPLE
- Nội dung là trung tâm: nhiệm vụ ở trên, nhật ký hoạt động chiếm phần còn lại.
- Một màu nhấn duy nhất (xanh) cho hành động chính; đỏ chỉ dành cho "Dừng".
- Thẻ nổi trên nền grouped, bo góc đồng tâm, nút capsule, chữ hệ thống.
- Tự theo giao diện Sáng/Tối của Windows.
- Nhật ký tô màu theo loại (suy nghĩ / hành động / kết quả...), cập nhật theo lô để luôn mượt.
"""

import re
import threading
import queue
import time
import tkinter as tk
import tkinter.font as tkfont
from tkinter import messagebox
import customtkinter as ctk

from config import config
from core.safety import safety
from core.context import truncate_text

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

# Giới hạn hiển thị để khung nhật ký luôn mượt
LOG_MSG_MAX_CHARS = 1200      # mỗi dòng log (kết quả công cụ dài sẽ được rút gọn khi hiển thị)
LOG_MAX_LINES = 3000          # tổng số dòng giữ trong khung nhật ký
LOG_BATCH_PER_TICK = 200      # số bản ghi xử lý mỗi nhịp cập nhật UI
STATUS_MAX_CHARS = 34

# ---------------------------------------------------------------------
# TOKEN MÀU (sáng, tối) - xấp xỉ màu hệ thống Apple, đã kiểm tra tương phản
# ---------------------------------------------------------------------
BG          = ("#f2f2f7", "#000000")   # nền grouped
CARD        = ("#ffffff", "#1c1c1e")   # thẻ nổi
FIELD       = ("#f2f2f7", "#2c2c2e")   # ô nhập "lõm" trong thẻ
CHIP        = ("#ececf0", "#2c2c2e")
CHIP_HOVER  = ("#e0e0e6", "#3a3a3c")
LABEL       = ("#1d1d1f", "#f5f5f7")
LABEL2      = ("#6e6e73", "#a1a1a6")
SEPARATOR   = ("#d1d1d6", "#38383a")
TINT        = ("#0071e3", "#0a84ff")   # nền nút chính (chữ trắng)
TINT_HOVER  = ("#0062c4", "#2b95ff")
TINT_TEXT   = ("#0066cc", "#2997ff")   # chữ/icon tương tác
TINT_SOFT   = ("#e5f1fc", "#0a2540")
RED_TEXT    = ("#d70015", "#ff6961")
RED_SOFT    = ("#fde8ea", "#3a0d12")
RED_HOVER   = ("#f9d4d8", "#4d1219")
GREEN_TEXT  = ("#1e7b34", "#30d158")
GREEN_SOFT  = ("#e3f4e7", "#0c2a14")
ORANGE_TEXT = ("#c93400", "#ff9f0a")
SEG_SELECTED = ("#ffffff", "#636366")
DISABLED_BG = ("#e5e5ea", "#2c2c2e")
DISABLED_FG = ("#a1a1a6", "#636366")

PROVIDER_LABELS = {
    "hybrid": "Kết hợp — Claude lập kế hoạch, Gemini thực thi",
    "gemini": "Gemini",
    "claude": "Claude",
}
MODE_HINTS = {
    "hybrid": "Claude chỉ đọc mục tiêu và báo cáo ngắn để quyết định; Gemini làm mọi thao tác và xem ảnh. "
              "Tiết kiệm token Claude nhất.",
    "gemini": "Gemini vừa suy nghĩ vừa thao tác.",
    "claude": "Claude vừa suy nghĩ vừa thao tác (tốn token Claude nhất).",
}

RADIUS_CARD = 20
RADIUS_FIELD = 14
RADIUS_CAPSULE = 22  # = nửa chiều cao nút 44px


def _pick(preferred: list[str], fallback: str) -> str:
    try:
        fams = set(tkfont.families())
    except Exception:
        fams = set()
    for name in preferred:
        if name in fams:
            return name
    return fallback


# Loại log -> (nhãn hiển thị, tag nhãn, tag nội dung)
LOG_KINDS = {
    "THOUGHT":     ("Suy nghĩ",   "lbl_thought", "msg_thought"),
    "ACTION":      ("Hành động",  "lbl_action",  "msg_action"),
    "OBSERVATION": ("Kết quả",    "lbl_obs",     "msg_obs"),
    "INFO":        ("",           "lbl_info",    "msg_info"),
    "WARN":        ("Cảnh báo",   "lbl_warn",    "msg_warn"),
    "ERROR":       ("Lỗi",        "lbl_error",   "msg_error"),
    "STOP":        ("Dừng",       "lbl_error",   "msg_error"),
    "SUCCESS":     ("Hoàn thành", "lbl_ok",      "msg_ok"),
}

# Biểu tượng emoji do bộ não thêm vào đầu dòng -> loại bỏ khỏi UI (giữ nhật ký sạch)
_EMOJI_PREFIX = "⚡👁🔄🗜📊🎉🤔🧠ℹ⚠❌🛑📌•️ ️"
_STEP_RE = re.compile(r"Bước\s+(\d+)\s*/\s*(\d+)")


def _clean(msg: str) -> str:
    return msg.lstrip(_EMOJI_PREFIX).strip() if msg else ""


class GeminiAutoPilotApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("AutoPilot")
        self.geometry("900x720")
        self.minsize(720, 540)
        self.configure(fg_color=BG)

        self.ff = _pick(["SF Pro Text", "Segoe UI Variable Text", "Segoe UI", "Helvetica Neue"], "Segoe UI")
        self.ff_display = _pick(["SF Pro Display", "Segoe UI Variable Display", "Segoe UI Semibold", "Segoe UI"], self.ff)
        self.ff_mono = _pick(["SF Mono", "Cascadia Mono", "Consolas"], "Consolas")

        # Trạng thái
        self.is_running = False
        self.is_compact = False
        self.log_queue = queue.Queue()
        self.worker_thread = None
        self._log_has_content = False
        self._tag_fonts = []
        self._applied_mode = None

        # Não bộ Gemini & Claude được nạp lười (lazy) khi cần -> khởi động nhanh,
        # và không bắt buộc cài SDK của provider không dùng tới.
        self._brains = {}
        # Nạp sẵn SDK ở luồng nền để lần bấm "Bắt đầu" đầu tiên không bị khựng
        threading.Thread(target=self._preload_sdks, daemon=True).start()

        # Đăng ký callback dừng khẩn cấp từ safety
        safety.register_stop_callback(self._on_safety_stop)

        self._build_ui()
        self._apply_log_tag_styles()

        # Vòng lặp kiểm tra hàng đợi log để cập nhật UI an toàn từ background thread
        self.after(50, self._process_log_queue)

        # Lắng nghe phím nóng toàn cục
        safety.start_hotkey_listener()

    # =================================================================
    # TIỆN ÍCH GIAO DIỆN
    # =================================================================
    def _font(self, size: int, weight: str = "normal", family: str | None = None) -> ctk.CTkFont:
        return ctk.CTkFont(family=family or self.ff, size=size, weight=weight)

    def _ghost_button(self, parent, text, command, width=0):
        """Nút chữ tint, không nền (cấp 3 - tác vụ phụ)."""
        return ctk.CTkButton(
            parent, text=text, command=command, width=width, height=32,
            corner_radius=16, font=self._font(14),
            fg_color="transparent", hover_color=CHIP,
            text_color=TINT_TEXT, border_width=0,
        )

    # =================================================================
    # XÂY DỰNG GIAO DIỆN
    # =================================================================
    def _build_ui(self):
        pad = 24

        # ------------------ HEADER: tiêu đề lớn + trạng thái + tác vụ phụ ------------------
        self.header = ctk.CTkFrame(self, fg_color="transparent")
        self.header.pack(fill="x", padx=pad, pady=(22, 14))

        title_box = ctk.CTkFrame(self.header, fg_color="transparent")
        title_box.pack(side="left")
        ctk.CTkLabel(
            title_box, text="AutoPilot", anchor="w",
            font=self._font(28, "bold", self.ff_display), text_color=LABEL,
        ).pack(anchor="w")
        self.lbl_subtitle = ctk.CTkLabel(
            title_box, text="Trợ lý điều khiển máy tính Windows", anchor="w",
            font=self._font(13), text_color=LABEL2,
        )
        self.lbl_subtitle.pack(anchor="w")

        right_box = ctk.CTkFrame(self.header, fg_color="transparent")
        right_box.pack(side="right")

        self.btn_settings = self._ghost_button(right_box, "Cài đặt", self.open_settings_dialog)
        self.btn_settings.pack(side="right", padx=(2, 0))
        self.btn_compact = self._ghost_button(right_box, "Thu gọn", self.toggle_compact_mode)
        self.btn_compact.pack(side="right", padx=2)

        # Viên trạng thái (capsule): chấm màu + chữ
        self.status_pill = ctk.CTkFrame(right_box, height=30, corner_radius=15, fg_color=CHIP)
        self.status_pill.pack(side="right", padx=(0, 10))
        self.status_dot = ctk.CTkLabel(
            self.status_pill, text="●", width=14, font=self._font(11), text_color=GREEN_TEXT
        )
        self.status_dot.pack(side="left", padx=(12, 0), pady=4)
        self.status_text = ctk.CTkLabel(
            self.status_pill, text="Sẵn sàng", font=self._font(13, "bold"), text_color=LABEL, anchor="w"
        )
        self.status_text.pack(side="left", padx=(4, 14), pady=4)

        # ------------------ THẺ NHIỆM VỤ ------------------
        self.input_card = ctk.CTkFrame(self, corner_radius=RADIUS_CARD, fg_color=CARD)
        self.input_card.pack(fill="x", padx=pad, pady=(0, 14))

        ctk.CTkLabel(
            self.input_card, text="Nhiệm vụ", anchor="w",
            font=self._font(15, "bold"), text_color=LABEL,
        ).pack(fill="x", padx=20, pady=(16, 8))

        self.txt_goal = ctk.CTkTextbox(
            self.input_card, height=84, corner_radius=RADIUS_FIELD,
            font=self._font(15), fg_color=FIELD, text_color=LABEL,
            border_width=0, wrap="word",
        )
        self.txt_goal.pack(fill="x", padx=20)
        self.txt_goal.insert("1.0", "Mở Notepad và viết danh sách 3 mục tiêu phát triển bản thân, sau đó lưu ra Desktop.")

        # Gợi ý nhanh (chip capsule)
        self.chips_frame = ctk.CTkFrame(self.input_card, fg_color="transparent")
        self.chips_frame.pack(fill="x", padx=20, pady=(10, 0))
        presets = [
            ("Ghi chú trong Notepad", "Mở ứng dụng Notepad, viết bài thơ ngắn chúc một ngày làm việc hiệu quả và lưu lại."),
            ("Tìm tin AI mới nhất", "Mở trình duyệt Google Chrome và tìm kiếm tin tức công nghệ AI mới nhất."),
            ("Thống kê thư mục", "Dùng PowerShell kiểm tra các tệp tin trong thư mục Documents và thống kê số lượng."),
        ]
        for label, prompt in presets:
            ctk.CTkButton(
                self.chips_frame, text=label, height=30, corner_radius=15,
                font=self._font(13), fg_color=CHIP, hover_color=CHIP_HOVER,
                text_color=LABEL, border_width=0,
                command=lambda p=prompt: self._set_goal(p),
            ).pack(side="left", padx=(0, 8))

        # Thanh tiến độ mảnh (luôn chiếm chỗ để bố cục không nhảy)
        self.progress = ctk.CTkProgressBar(
            self.input_card, height=4, corner_radius=2,
            fg_color=FIELD, progress_color=TINT,
        )
        self.progress.pack(fill="x", padx=20, pady=(16, 0))
        self.progress.set(0)

        # Hành động: BẮT ĐẦU (chính, đầy) + DỪNG (phụ, đỏ nhạt)
        action_bar = ctk.CTkFrame(self.input_card, fg_color="transparent")
        action_bar.pack(fill="x", padx=20, pady=(14, 18))

        self.btn_start = ctk.CTkButton(
            action_bar, text="Bắt đầu thực hiện", height=44, corner_radius=RADIUS_CAPSULE,
            font=self._font(15, "bold"),
            fg_color=TINT, hover_color=TINT_HOVER, text_color="#ffffff",
            text_color_disabled=DISABLED_FG, border_width=0,
            command=self.start_task,
        )
        self.btn_start.pack(side="left", fill="x", expand=True, padx=(0, 10))

        self.btn_stop = ctk.CTkButton(
            action_bar, text="Dừng  (F8)", width=140, height=44, corner_radius=RADIUS_CAPSULE,
            font=self._font(15, "bold"),
            fg_color=DISABLED_BG, hover_color=RED_HOVER, text_color=DISABLED_FG,
            text_color_disabled=DISABLED_FG, border_width=0, state="disabled",
            command=self.stop_task,
        )
        self.btn_stop.pack(side="right")

        # ------------------ THẺ NHẬT KÝ HOẠT ĐỘNG ------------------
        self.log_card = ctk.CTkFrame(self, corner_radius=RADIUS_CARD, fg_color=CARD)
        self.log_card.pack(fill="both", expand=True, padx=pad, pady=(0, pad))

        log_header = ctk.CTkFrame(self.log_card, fg_color="transparent")
        log_header.pack(fill="x", padx=20, pady=(14, 0))
        ctk.CTkLabel(
            log_header, text="Hoạt động", anchor="w",
            font=self._font(15, "bold"), text_color=LABEL,
        ).pack(side="left")
        self._ghost_button(log_header, "Xóa", self.clear_logs).pack(side="right")

        ctk.CTkFrame(self.log_card, height=1, fg_color=SEPARATOR, corner_radius=0).pack(
            fill="x", padx=20, pady=(8, 0)
        )

        self.txt_log = ctk.CTkTextbox(
            self.log_card, font=self._font(12, family=self.ff_mono),
            fg_color="transparent", text_color=LABEL, border_width=0,
            corner_radius=RADIUS_FIELD, wrap="word", spacing1=1, spacing3=2,
        )
        self.txt_log.pack(fill="both", expand=True, padx=12, pady=(6, 12))
        self.txt_log.configure(state="disabled")

        # Lời chào ban đầu
        self._append_log("INFO", "Sẵn sàng. Nhấn F8 hoặc Ctrl+Shift+Q bất cứ lúc nào để dừng khẩn cấp.")
        provider = getattr(config, "ai_provider", "gemini")
        self._append_log("INFO", f"Chế độ: {PROVIDER_LABELS.get(provider, provider)}.")
        missing = self._missing_key(provider)
        if missing:
            self._append_log("WARN", f"{missing} Mở Cài đặt để thêm khóa.")

    @staticmethod
    def _missing_key(provider: str) -> str:
        """Trả về thông báo nếu thiếu khóa API cần cho chế độ đang chọn."""
        need_claude = provider in ("claude", "hybrid")
        need_gemini = provider in ("gemini", "hybrid")
        if need_claude and not getattr(config, "anthropic_api_key", ""):
            return "Chưa có ANTHROPIC_API_KEY (lấy tại console.anthropic.com)."
        if need_gemini and not config.gemini_api_key:
            return "Chưa có GEMINI_API_KEY (miễn phí tại aistudio.google.com)."
        return ""

    # =================================================================
    # NHẬT KÝ
    # =================================================================
    def _palette_index(self) -> int:
        return 1 if ctk.get_appearance_mode() == "Dark" else 0

    def _apply_log_tag_styles(self):
        """Gán màu/kiểu chữ cho các tag của nhật ký theo giao diện Sáng/Tối hiện tại."""
        i = self._palette_index()
        self._applied_mode = i
        try:
            scale = self._get_window_scaling()
        except Exception:
            scale = 1.0

        def font(size, bold=False):
            f = tkfont.Font(family=self.ff_mono, size=-max(1, round(size * scale)), weight="bold" if bold else "normal")
            self._tag_fonts.append(f)
            return f

        self._tag_fonts.clear()
        tb = self.txt_log._textbox
        styles = {
            "time":        (LABEL2[i], font(11), 0),
            "step":        (LABEL2[i], font(11, True), 0),
            "lbl_thought": (LABEL2[i], font(12, True), 0),
            "msg_thought": (LABEL[i], font(12), 0),
            "lbl_action":  (TINT_TEXT[i], font(12, True), 0),
            "msg_action":  (TINT_TEXT[i], font(12), 0),
            "lbl_obs":     (LABEL2[i], font(12, True), 0),
            "msg_obs":     (LABEL2[i], font(12), 0),
            "lbl_info":    (LABEL2[i], font(12), 0),
            "msg_info":    (LABEL2[i], font(12), 0),
            "lbl_warn":    (ORANGE_TEXT[i], font(12, True), 0),
            "msg_warn":    (ORANGE_TEXT[i], font(12), 0),
            "lbl_error":   (RED_TEXT[i], font(12, True), 0),
            "msg_error":   (RED_TEXT[i], font(12), 0),
            "lbl_ok":      (GREEN_TEXT[i], font(12, True), 0),
            "msg_ok":      (GREEN_TEXT[i], font(12, True), 0),
        }
        for name, (color, fnt, _) in styles.items():
            tb.tag_config(name, foreground=color, font=fnt)
        tb.tag_config("step", spacing1=14, spacing3=4)

    def _log_segments(self, tag: str, msg: str) -> list[tuple[str, str]]:
        """Chuyển 1 bản ghi log thành danh sách (văn bản, tag) để chèn vào Textbox."""
        msg = truncate_text(_clean(msg), LOG_MSG_MAX_CHARS)
        if tag == "STEP":
            title = msg.strip("= ").capitalize()
            self._log_has_content = True
            return [(f"{title}\n", "step")]

        label, lbl_tag, msg_tag = LOG_KINDS.get(tag, ("", "lbl_info", "msg_info"))
        if tag == "OBSERVATION":
            msg = re.sub(r"^Kết quả:\s*", "", msg)
        segs = [(time.strftime("%H:%M:%S") + "  ", "time")]
        if label:
            segs.append((label + "  ", lbl_tag))
        segs.append((msg + "\n", msg_tag))
        self._log_has_content = True
        return segs

    def _append_log(self, tag: str, msg: str):
        self._insert_log_segments(self._log_segments(tag, msg))

    def _insert_log_segments(self, segs: list[tuple[str, str]]):
        tb = self.txt_log._textbox
        at_bottom = tb.yview()[1] >= 0.98
        self.txt_log.configure(state="normal")
        for text, tag in segs:
            tb.insert("end", text, tag)
        # Cắt bớt các dòng cũ để Textbox không phình to làm chậm UI
        try:
            total_lines = int(tb.index("end-1c").split(".")[0])
            if total_lines > LOG_MAX_LINES:
                tb.delete("1.0", f"{total_lines - LOG_MAX_LINES + 1}.0")
        except Exception:
            pass
        self.txt_log.configure(state="disabled")
        if at_bottom:
            tb.see("end")

    def clear_logs(self):
        self.txt_log.configure(state="normal")
        self.txt_log.delete("1.0", "end")
        self.txt_log.configure(state="disabled")
        self._log_has_content = False

    def _enqueue_log(self, tag: str, msg: str):
        self.log_queue.put(("log", tag, msg))

    def _enqueue_status(self, status: str):
        self.log_queue.put(("status", status, None))

    def _process_log_queue(self):
        segs = []
        last_status = None
        try:
            for _ in range(LOG_BATCH_PER_TICK):
                item = self.log_queue.get_nowait()
                if item[0] == "log":
                    segs.extend(self._log_segments(item[1], item[2]))
                elif item[0] == "status":
                    last_status = item[1]
        except queue.Empty:
            pass
        except Exception:
            pass

        # Đổi giao diện Sáng/Tối của Windows -> cập nhật màu nhật ký
        if self._palette_index() != self._applied_mode:
            self._apply_log_tag_styles()
        if segs:
            self._insert_log_segments(segs)
        if last_status is not None:
            self._update_status_ui(last_status)
        self.after(50 if segs else 100, self._process_log_queue)

    # =================================================================
    # TRẠNG THÁI
    # =================================================================
    def _update_status_ui(self, status: str):
        low = status.lower()
        if "lỗi" in low or "dừng" in low or "hết" in low or "từ chối" in low:
            kind = "error"
        elif "hoàn thành" in low:
            kind = "ok"
        elif any(k in low for k in ("bước", "thực thi", "suy luận", "khởi động")):
            kind = "busy"
        else:
            kind = "idle"

        pill_fg, dot_fg = {
            "error": (RED_SOFT, RED_TEXT),
            "ok":    (GREEN_SOFT, GREEN_TEXT),
            "busy":  (TINT_SOFT, TINT_TEXT),
            "idle":  (CHIP, GREEN_TEXT),
        }[kind]
        self.status_pill.configure(fg_color=pill_fg)
        self.status_dot.configure(text_color=dot_fg)
        short = " ".join(status.split())
        if len(short) > STATUS_MAX_CHARS:
            short = short[: STATUS_MAX_CHARS - 1].rstrip() + "…"
        self.status_text.configure(text=short)

        m = _STEP_RE.search(status)
        if m:
            cur, total = int(m.group(1)), max(1, int(m.group(2)))
            self.progress.set(min(1.0, cur / total))
        elif kind == "ok":
            self.progress.set(1.0)

    def _set_goal(self, text: str):
        self.txt_goal.delete("1.0", "end")
        self.txt_goal.insert("1.0", text)

    def _set_running_ui(self, running: bool):
        if running:
            self.btn_start.configure(state="disabled", fg_color=DISABLED_BG)
            self.btn_stop.configure(state="normal", fg_color=RED_SOFT, text_color=RED_TEXT)
            self.progress.set(0)
        else:
            self.btn_start.configure(state="normal", fg_color=TINT)
            self.btn_stop.configure(state="disabled", fg_color=DISABLED_BG, text_color=DISABLED_FG)

    # =================================================================
    # ĐIỀU PHỐI NHIỆM VỤ
    # =================================================================
    @staticmethod
    def _preload_sdks():
        for mod in ("google.genai", "anthropic", "pypdf", "docx"):
            try:
                __import__(mod)
            except Exception:
                pass

    def _get_brain(self, provider: str):
        """Nạp và cache bộ não theo provider ('gemini' | 'claude' | 'hybrid')."""
        if provider not in self._brains:
            from core.factory import make_brain   # bọc Router -> Recipe -> AI
            self._brains[provider] = make_brain(
                provider,
                log_callback=self._enqueue_log,
                status_callback=self._enqueue_status
            )
        return self._brains[provider]

    def start_task(self):
        if self.is_running:
            return

        goal = self.txt_goal.get("1.0", "end").strip()
        if not goal:
            messagebox.showwarning("Thiếu nhiệm vụ", "Hãy nhập nội dung nhiệm vụ cần thực hiện.")
            return

        provider = getattr(config, "ai_provider", "gemini")
        missing = self._missing_key(provider)
        if missing:
            messagebox.showinfo("Cần khóa API", f"{missing}\n\nMở Cài đặt để nhập khóa.")
            self.open_settings_dialog()
            return

        try:
            active_brain = self._get_brain(provider)
        except Exception as e:
            messagebox.showerror(
                "Thiếu thư viện",
                f"Không thể khởi tạo bộ não '{provider}': {e}\n\nHãy chạy: pip install -r requirements.txt"
            )
            return

        self.is_running = True
        self._set_running_ui(True)

        def run_thread():
            try:
                try:
                    import pythoncom
                    pythoncom.CoInitialize()
                except Exception:
                    pass
                active_brain.run_task(goal)
            except Exception as e:
                self._enqueue_log("ERROR", f"Lỗi không mong muốn: {e}")
                self._enqueue_status("Lỗi hệ thống")
            finally:
                try:
                    import pythoncom
                    pythoncom.CoUninitialize()
                except Exception:
                    pass
                self.is_running = False
                self.after(0, self._on_task_finished)

        self.worker_thread = threading.Thread(target=run_thread, daemon=True)
        self.worker_thread.start()

    def _on_task_finished(self):
        self.is_running = False
        self._set_running_ui(False)

    def stop_task(self):
        if not self.is_running:
            return
        safety.stop("Người dùng bấm nút Dừng trên giao diện.")
        self._enqueue_status("Đã dừng")

    def _on_safety_stop(self, reason: str):
        self._enqueue_log("STOP", f"Dừng khẩn cấp: {reason}")
        self._enqueue_status("Đã dừng")

    # =================================================================
    # CHẾ ĐỘ THU GỌN
    # =================================================================
    def toggle_compact_mode(self):
        """Chuyển giữa cửa sổ đầy đủ và thanh nổi thu gọn luôn ở trên cùng."""
        if not self.is_compact:
            self.log_card.pack_forget()
            self.chips_frame.pack_forget()
            self.lbl_subtitle.pack_forget()
            self.txt_goal.configure(height=56)
            self.geometry("700x330+24+24")
            self.minsize(640, 300)
            self.attributes("-topmost", True)
            self.btn_compact.configure(text="Mở rộng")
            self.is_compact = True
        else:
            self.lbl_subtitle.pack(anchor="w")
            self.chips_frame.pack(fill="x", padx=20, pady=(10, 0), after=self.txt_goal)
            self.txt_goal.configure(height=84)
            self.log_card.pack(fill="both", expand=True, padx=24, pady=(0, 24))
            self.minsize(720, 540)
            self.geometry("900x720")
            self.attributes("-topmost", False)
            self.btn_compact.configure(text="Thu gọn")
            self.is_compact = False

    # =================================================================
    # CÀI ĐẶT
    # =================================================================
    def open_settings_dialog(self):
        """Mở cửa sổ cài đặt: nhà cung cấp AI, khóa API, mô hình và hiệu năng."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Cài đặt")
        dialog.geometry("560x640")
        dialog.resizable(False, False)
        dialog.configure(fg_color=BG)
        dialog.attributes("-topmost", True)
        dialog.after(150, lambda: dialog.winfo_exists() and dialog.grab_set())

        ctk.CTkLabel(
            dialog, text="Cài đặt", anchor="w",
            font=self._font(28, "bold", self.ff_display), text_color=LABEL,
        ).pack(fill="x", padx=24, pady=(22, 12))

        def section(title: str):
            """Nhóm cài đặt: nhãn nhỏ phía trên + thẻ bo lớn. Trả về (khung_ngoài, thẻ)."""
            outer = ctk.CTkFrame(dialog, fg_color="transparent")
            ctk.CTkLabel(
                outer, text=title, anchor="w", font=self._font(13), text_color=LABEL2,
            ).pack(fill="x", padx=30, pady=(8, 4))
            card = ctk.CTkFrame(outer, corner_radius=RADIUS_CARD, fg_color=CARD)
            card.pack(fill="x", padx=24)
            return outer, card

        def field(card, label: str, last: bool = False):
            """Một hàng trong thẻ: nhãn bên trái, ô nhập bên phải."""
            row = ctk.CTkFrame(card, fg_color="transparent")
            row.pack(fill="x", padx=16, pady=(10, 10))
            ctk.CTkLabel(row, text=label, anchor="w", width=130, font=self._font(14), text_color=LABEL).pack(side="left")
            holder = ctk.CTkFrame(row, fg_color="transparent")
            holder.pack(side="left", fill="x", expand=True)
            if not last:
                ctk.CTkFrame(card, height=1, fg_color=SEPARATOR, corner_radius=0).pack(fill="x", padx=16)
            return holder

        def entry(parent, show=None, placeholder="", width=0):
            return ctk.CTkEntry(
                parent, height=34, corner_radius=10, border_width=0, show=show,
                fg_color=FIELD, text_color=LABEL, placeholder_text=placeholder,
                placeholder_text_color=LABEL2, font=self._font(14),
                **({"width": width} if width else {}),
            )

        def combo(parent, values):
            return ctk.CTkComboBox(
                parent, values=values, height=34, corner_radius=10, border_width=0,
                fg_color=FIELD, button_color=CHIP, button_hover_color=CHIP_HOVER,
                text_color=LABEL, dropdown_fg_color=CARD, dropdown_text_color=LABEL,
                dropdown_hover_color=CHIP, font=self._font(14), dropdown_font=self._font(14),
            )

        # ---- Nhà cung cấp ----
        provider_map = {"Kết hợp": "hybrid", "Gemini": "gemini", "Claude": "claude"}
        reverse_prov = {v: k for k, v in provider_map.items()}
        prov_outer, c = section("Nhà cung cấp AI")
        prov_outer.pack(fill="x")
        row = ctk.CTkFrame(c, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=14)
        seg_provider = ctk.CTkSegmentedButton(
            row, values=list(provider_map), height=34, corner_radius=17, font=self._font(14, "bold"),
            fg_color=CHIP, selected_color=SEG_SELECTED, selected_hover_color=SEG_SELECTED,
            unselected_color=CHIP, unselected_hover_color=CHIP_HOVER,
            text_color=LABEL, border_width=3,
            command=lambda _v=None: show_provider(),
        )
        seg_provider.pack(fill="x")
        seg_provider.set(reverse_prov.get(getattr(config, "ai_provider", "gemini"), "Gemini"))
        lbl_mode_hint = ctk.CTkLabel(
            c, text="", anchor="w", justify="left", wraplength=470,
            font=self._font(12), text_color=LABEL2,
        )
        lbl_mode_hint.pack(fill="x", padx=18, pady=(0, 12))

        # ---- Gemini ----
        gemini_outer, gemini_card = section("Gemini · tay chân (thực thi, nhìn màn hình)")
        entry_api = entry(field(gemini_card, "Khóa API"), show="•", placeholder="AIzaSy… (nhiều khóa cách nhau bằng dấu phẩy)")
        entry_api.pack(fill="x")
        entry_api.insert(0, getattr(config, "gemini_api_key_raw", None) or config.gemini_api_key or "")
        gemini_models = ["gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-3.8-flash", "gemini-3.1-flash-lite"]
        combo_model = combo(field(gemini_card, "Mô hình", last=True), gemini_models)
        combo_model.pack(fill="x")
        combo_model.set(config.gemini_model if config.gemini_model in gemini_models else "gemini-3.5-flash")

        # ---- Claude ----
        claude_outer, claude_card = section("Claude · bộ não (lập kế hoạch, ra quyết định)")
        entry_claude_api = entry(field(claude_card, "Khóa API"), show="•", placeholder="sk-ant-api03-…")
        entry_claude_api.pack(fill="x")
        entry_claude_api.insert(0, getattr(config, "anthropic_api_key", "") or "")
        claude_models = [
            "claude-sonnet-5-5", "claude-haiku-5-5", "claude-opus-5-5",
            "claude-sonnet-5", "claude-opus-5", "claude-sonnet-4-6",
        ]
        combo_claude_model = combo(field(claude_card, "Mô hình", last=True), claude_models)
        combo_claude_model.pack(fill="x")
        cur_claude = getattr(config, "claude_model", "claude-sonnet-5-5")
        combo_claude_model.set(cur_claude if cur_claude in claude_models else "claude-sonnet-5-5")

        # ---- Hiệu năng ----
        perf_outer, perf_card = section("Thực thi và tiết kiệm token")
        perf_outer.pack(fill="x")

        def show_provider():
            """Chỉ hiện phần cài đặt cần cho chế độ đang chọn."""
            mode = provider_map.get(seg_provider.get(), "gemini")
            gemini_outer.pack_forget()
            claude_outer.pack_forget()
            if mode in ("claude", "hybrid"):
                claude_outer.pack(fill="x", before=perf_outer)
            if mode in ("gemini", "hybrid"):
                gemini_outer.pack(fill="x", before=perf_outer)
            lbl_mode_hint.configure(text=MODE_HINTS[mode])
            dialog.geometry("560x860" if mode == "hybrid" else "560x700")

        show_provider()
        entry_delay = entry(field(perf_card, "Độ trễ (giây)"), width=90)
        entry_delay.pack(anchor="w")
        entry_delay.insert(0, str(config.action_delay))
        entry_steps = entry(field(perf_card, "Số bước tối đa"), width=90)
        entry_steps.pack(anchor="w")
        entry_steps.insert(0, str(config.max_steps))
        entry_shots = entry(field(perf_card, "Ảnh giữ lại", last=True), width=90)
        entry_shots.pack(anchor="w")
        entry_shots.insert(0, str(config.keep_screenshots))

        def save_and_close():
            chosen_prov = provider_map.get(seg_provider.get(), "gemini")
            try:
                new_delay = float(entry_delay.get().strip())
                new_steps = int(entry_steps.get().strip())
                new_shots = int(entry_shots.get().strip())
                if new_delay < 0 or new_steps < 1 or new_shots < 0:
                    raise ValueError
            except ValueError:
                messagebox.showerror("Giá trị không hợp lệ", "Độ trễ, số bước và số ảnh giữ lại phải là số hợp lệ.", parent=dialog)
                return

            config.save(
                ai_provider=chosen_prov,
                gemini_api_key=entry_api.get().strip(),
                gemini_model=combo_model.get().strip(),
                anthropic_api_key=entry_claude_api.get().strip(),
                claude_model=combo_claude_model.get().strip(),
                action_delay=new_delay,
                max_steps=new_steps,
                keep_screenshots=new_shots,
            )
            self._append_log("INFO", f"Đã lưu cài đặt. Chế độ: {PROVIDER_LABELS.get(chosen_prov, chosen_prov)}.")
            dialog.destroy()

        footer = ctk.CTkFrame(dialog, fg_color="transparent")
        footer.pack(fill="x", padx=24, pady=(18, 20), side="bottom")
        ctk.CTkButton(
            footer, text="Lưu", height=44, corner_radius=RADIUS_CAPSULE,
            font=self._font(15, "bold"), fg_color=TINT, hover_color=TINT_HOVER,
            text_color="#ffffff", command=save_and_close,
        ).pack(side="right", fill="x", expand=True, padx=(10, 0))
        ctk.CTkButton(
            footer, text="Hủy", width=110, height=44, corner_radius=RADIUS_CAPSULE,
            font=self._font(15, "bold"), fg_color=CHIP, hover_color=CHIP_HOVER,
            text_color=LABEL, command=dialog.destroy,
        ).pack(side="right")


def run_gui():
    app = GeminiAutoPilotApp()
    app.mainloop()


if __name__ == "__main__":
    run_gui()
