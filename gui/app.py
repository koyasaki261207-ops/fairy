"""
GIAO DIỆN ĐIỀU KHIỂN HIỆN ĐẠI (CUSTOMTKINTER) - GEMINI AUTOPILOT
Hỗ trợ chế độ cửa sổ chuẩn, chế độ thanh nổi Compact ghim trên màn hình,
nhật ký trực tiếp thời gian thực và phím nóng dừng khẩn cấp F8.
"""

import threading
import queue
import time
import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk

from config import config
from core.safety import safety
from core.brain import GeminiBrain

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


class GeminiAutoPilotApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("🤖 Gemini AutoPilot - Trợ lý Điều khiển Máy tính Thông minh")
        self.geometry("980x700")
        self.minsize(800, 600)

        # Trạng thái
        self.is_running = False
        self.is_compact = False
        self.log_queue = queue.Queue()
        self.worker_thread = None

        # Khởi tạo não bộ Gemini & Claude
        self.brain = GeminiBrain(
            log_callback=self._enqueue_log,
            status_callback=self._enqueue_status
        )
        try:
            from core.claude_brain import ClaudeBrain
            self.claude_brain = ClaudeBrain(
                log_callback=self._enqueue_log,
                status_callback=self._enqueue_status
            )
        except Exception:
            self.claude_brain = None

        # Đăng ký callback dừng khẩn cấp từ safety
        safety.register_stop_callback(self._on_safety_stop)

        # Xây dựng giao diện
        self._build_ui()

        # Vòng lặp kiểm tra hàng đợi log để cập nhật UI an toàn từ background thread
        self.after(50, self._process_log_queue)

        # Lắng nghe phím nóng toàn cục
        safety.start_hotkey_listener()

    def _build_ui(self):
        # ---------------------------------------------------------
        # TOP HEADER: Tiêu đề + Trạng thái + Cài đặt + Chế độ nổi
        # ---------------------------------------------------------
        self.header_frame = ctk.CTkFrame(self, corner_radius=10, fg_color="#1a1d24")
        self.header_frame.pack(fill="x", padx=15, pady=(15, 10))

        # Tiêu đề & Logo
        title_box = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        title_box.pack(side="left", padx=15, pady=12)

        self.lbl_title = ctk.CTkLabel(
            title_box,
            text="⚡ GEMINI AUTOPILOT",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color="#38bdf8"
        )
        self.lbl_title.pack(anchor="w")

        self.lbl_subtitle = ctk.CTkLabel(
            title_box,
            text="Tự động hóa máy tính Windows đa tầng • ReAct Engine",
            font=ctk.CTkFont(size=12),
            text_color="#94a3b8"
        )
        self.lbl_subtitle.pack(anchor="w")

        # Nút chức năng bên phải
        right_box = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        right_box.pack(side="right", padx=15, pady=12)

        # Badge trạng thái
        self.status_badge = ctk.CTkLabel(
            right_box,
            text="● Sẵn sàng",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#10b981",
            fg_color="#064e3b",
            corner_radius=8,
            padx=12,
            pady=4
        )
        self.status_badge.pack(side="left", padx=8)

        # Nút Compact Mode
        self.btn_compact = ctk.CTkButton(
            right_box,
            text="📌 Ghim Nổi",
            width=90,
            command=self.toggle_compact_mode,
            fg_color="#334155",
            hover_color="#475569"
        )
        self.btn_compact.pack(side="left", padx=6)

        # Nút Cài đặt
        self.btn_settings = ctk.CTkButton(
            right_box,
            text="⚙ Cấu hình",
            width=90,
            command=self.open_settings_dialog,
            fg_color="#334155",
            hover_color="#475569"
        )
        self.btn_settings.pack(side="left", padx=6)

        # ---------------------------------------------------------
        # KHUNG NHẬP NHIỆM VỤ (MISSION INPUT)
        # ---------------------------------------------------------
        self.input_card = ctk.CTkFrame(self, corner_radius=10, fg_color="#1e222b")
        self.input_card.pack(fill="x", padx=15, pady=5)

        lbl_input = ctk.CTkLabel(
            self.input_card,
            text="Giao nhiệm vụ cho trợ lý AI (nhập tiếng Việt tự nhiên):",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#e2e8f0"
        )
        lbl_input.pack(anchor="w", padx=15, pady=(10, 4))

        self.txt_goal = ctk.CTkTextbox(
            self.input_card,
            height=70,
            font=ctk.CTkFont(size=13),
            fg_color="#0f172a",
            border_width=1,
            border_color="#334155"
        )
        self.txt_goal.pack(fill="x", padx=15, pady=5)
        self.txt_goal.insert("1.0", "Mở Notepad và viết danh sách 3 mục tiêu phát triển bản thân, sau đó lưu ra Desktop.")

        # Hàng nút tác vụ mẫu nhanh
        quick_frame = ctk.CTkFrame(self.input_card, fg_color="transparent")
        quick_frame.pack(fill="x", padx=15, pady=(2, 8))

        lbl_quick = ctk.CTkLabel(quick_frame, text="Mẫu gợi ý:", font=ctk.CTkFont(size=11), text_color="#64748b")
        lbl_quick.pack(side="left", padx=(0, 6))

        presets = [
            ("📝 Mở Notepad & Ghi chép", "Mở ứng dụng Notepad, viết bài thơ ngắn chúc một ngày làm việc hiệu quả và lưu lại."),
            ("🌐 Mở Trình duyệt tìm AI", "Mở trình duyệt Google Chrome và tìm kiếm tin tức công nghệ AI mới nhất."),
            ("📁 Dọn dẹp thư mục", "Mở PowerShell kiểm tra các tệp tin trong thư mục Documents và thống kê số lượng.")
        ]
        for label, prompt in presets:
            btn = ctk.CTkButton(
                quick_frame,
                text=label,
                font=ctk.CTkFont(size=11),
                height=24,
                fg_color="#1e293b",
                hover_color="#334155",
                command=lambda p=prompt: self._set_goal(p)
            )
            btn.pack(side="left", padx=4)

        # Hàng nút điều khiển chính: BẮT ĐẦU & DỪNG KHẨN CẤP
        action_bar = ctk.CTkFrame(self.input_card, fg_color="transparent")
        action_bar.pack(fill="x", padx=15, pady=(5, 12))

        self.btn_start = ctk.CTkButton(
            action_bar,
            text="▶ BẮT ĐẦU THỰC HIỆN",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=38,
            fg_color="#0284c7",
            hover_color="#0369a1",
            command=self.start_task
        )
        self.btn_start.pack(side="left", fill="x", expand=True, padx=(0, 10))

        self.btn_stop = ctk.CTkButton(
            action_bar,
            text="⏹ DỪNG KHẨN CẤP (F8)",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=38,
            width=220,
            fg_color="#dc2626",
            hover_color="#b91c1c",
            command=self.stop_task
        )
        self.btn_stop.pack(side="right")

        # ---------------------------------------------------------
        # KHUNG NHẬT KÝ HOẠT ĐỘNG THỜI GIAN THỰC (LIVE TIMELINE LOG)
        # ---------------------------------------------------------
        self.log_card = ctk.CTkFrame(self, corner_radius=10, fg_color="#1a1d24")
        self.log_card.pack(fill="both", expand=True, padx=15, pady=(5, 15))

        log_header = ctk.CTkFrame(self.log_card, fg_color="transparent")
        log_header.pack(fill="x", padx=15, pady=(10, 4))

        lbl_log = ctk.CTkLabel(
            log_header,
            text="📋 Nhật Ký Thao Tác Trực Tiếp (ReAct Loop):",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#e2e8f0"
        )
        lbl_log.pack(side="left")

        btn_clear = ctk.CTkButton(
            log_header,
            text="Xóa nhật ký",
            width=80,
            height=22,
            font=ctk.CTkFont(size=11),
            fg_color="#334155",
            hover_color="#475569",
            command=self.clear_logs
        )
        btn_clear.pack(side="right")

        self.txt_log = ctk.CTkTextbox(
            self.log_card,
            font=ctk.CTkFont(family="Consolas", size=12),
            fg_color="#0b0f17",
            border_width=1,
            border_color="#1e293b",
            text_color="#e2e8f0"
        )
        self.txt_log.pack(fill="both", expand=True, padx=15, pady=(4, 12))

        # Khởi tạo lời chào ban đầu
        self._append_log("INFO", "Hệ thống Gemini AutoPilot đã sẵn sàng.")
        self._append_log("INFO", f"Phím tắt dừng khẩn cấp: Nhấn phím [F8] hoặc tổ hợp [Ctrl+Shift+Q].")
        if not config.gemini_api_key:
            self._append_log("WARN", "Chưa nhập GEMINI_API_KEY! Hãy nhấn nút [⚙ Cấu hình] để nhập API key miễn phí.")

    def _set_goal(self, text: str):
        self.txt_goal.delete("1.0", "end")
        self.txt_goal.insert("1.0", text)

    def _enqueue_log(self, tag: str, msg: str):
        self.log_queue.put(("log", tag, msg))

    def _enqueue_status(self, status: str):
        self.log_queue.put(("status", status, None))

    def _process_log_queue(self):
        try:
            while not self.log_queue.empty():
                item = self.log_queue.get_nowait()
                if item[0] == "log":
                    _, tag, msg = item
                    self._append_log(tag, msg)
                elif item[0] == "status":
                    _, status, _ = item
                    self._update_status_ui(status)
        except Exception:
            pass
        self.after(50, self._process_log_queue)

    def _update_status_ui(self, status: str):
        self.status_badge.configure(text=f"● {status}")
        if "Lỗi" in status or "dừng" in status.lower():
            self.status_badge.configure(text_color="#ef4444", fg_color="#450a0a")
        elif "thực thi" in status.lower() or "suy luận" in status.lower() or "bước" in status.lower():
            self.status_badge.configure(text_color="#38bdf8", fg_color="#082f49")
        elif "hoàn thành" in status.lower():
            self.status_badge.configure(text_color="#10b981", fg_color="#064e3b")
        else:
            self.status_badge.configure(text_color="#10b981", fg_color="#064e3b")

    def _append_log(self, tag: str, msg: str):
        t = time.strftime("%H:%M:%S")
        icons = {
            "INFO": "ℹ️ ",
            "THOUGHT": "🧠 ",
            "ACTION": "⚡ ",
            "OBSERVATION": "👁️ ",
            "STEP": "📌 ",
            "SUCCESS": "🎉 ",
            "WARN": "⚠️ ",
            "ERROR": "❌ ",
            "STOP": "🛑 "
        }
        icon = icons.get(tag, "• ")
        log_line = f"[{t}] {icon}{msg}\n"

        self.txt_log.insert("end", log_line)
        self.txt_log.see("end")

    def clear_logs(self):
        self.txt_log.delete("1.0", "end")

    def start_task(self):
        if self.is_running:
            return

        goal = self.txt_goal.get("1.0", "end").strip()
        if not goal:
            messagebox.showwarning("Cảnh báo", "Vui lòng nhập nội dung nhiệm vụ cần thực hiện!")
            return

        provider = getattr(config, "ai_provider", "gemini")
        if provider == "claude":
            if not getattr(config, "anthropic_api_key", ""):
                messagebox.showinfo(
                    "Yêu cầu Claude API Key",
                    "Bạn đã chọn Provider Claude nhưng chưa nhập ANTHROPIC_API_KEY!\n\n"
                    "Vui lòng nhấn nút [⚙ Cấu hình] để nhập API Key Claude (lấy tại console.anthropic.com)."
                )
                self.open_settings_dialog()
                return
            active_brain = self.claude_brain or self.brain
        else:
            if not config.gemini_api_key:
                messagebox.showinfo(
                    "Yêu cầu API Key",
                    "Bạn chưa nhập khóa Gemini API Key!\n\n"
                    "Vui lòng nhấn nút [⚙ Cấu hình] để nhập API Key (lấy miễn phí tại aistudio.google.com)."
                )
                self.open_settings_dialog()
                return
            active_brain = self.brain

        self.is_running = True
        self.btn_start.configure(state="disabled", fg_color="#475569")
        self.btn_stop.configure(state="normal", fg_color="#dc2626")

        def run_thread():
            try:
                try:
                    import pythoncom
                    pythoncom.CoInitialize()
                except Exception:
                    pass
                res = active_brain.run_task(goal)
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
        self.btn_start.configure(state="normal", fg_color="#0284c7")

    def stop_task(self):
        safety.stop("Người dùng bấm nút Dừng Khẩn Cấp trên giao diện.")
        self._enqueue_status("Đã dừng")

    def _on_safety_stop(self, reason: str):
        self._enqueue_log("STOP", f"Dừng khẩn cấp: {reason}")
        self._enqueue_status("Đã dừng")

    def toggle_compact_mode(self):
        """Chuyển đổi giữa chế độ cửa sổ đầy đủ và thanh nổi thu nhỏ (Compact Bar)"""
        if not self.is_compact:
            self.geometry("450x180+20+20")
            self.attributes("-topmost", True)
            self.log_card.pack_forget()
            self.btn_compact.configure(text="🗖 Mở Rộng", fg_color="#0284c7")
            self.is_compact = True
        else:
            self.geometry("980x700")
            self.attributes("-topmost", False)
            self.log_card.pack(fill="both", expand=True, padx=15, pady=(5, 15))
            self.btn_compact.configure(text="📌 Ghim Nổi", fg_color="#334155")
            self.is_compact = False

    def open_settings_dialog(self):
        """Mở cửa sổ cấu hình cài đặt API Key, Model, Timeout..."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("⚙ Cài Đặt Gemini & Claude AutoPilot")
        dialog.geometry("540x620")
        dialog.resizable(False, False)
        dialog.attributes("-topmost", True)
        dialog.grab_set()

        # Tiêu đề
        lbl_head = ctk.CTkLabel(
            dialog,
            text="Cấu Hình Hệ Thống (Gemini & Claude)",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="#38bdf8"
        )
        lbl_head.pack(padx=20, pady=(15, 10), anchor="w")

        # Chọn AI Provider
        lbl_prov = ctk.CTkLabel(dialog, text="Nhà cung cấp AI (AI Provider):", font=ctk.CTkFont(size=12, weight="bold"))
        lbl_prov.pack(padx=20, anchor="w", pady=(2, 2))

        provider_map = {"Gemini (Google)": "gemini", "Claude (Anthropic)": "claude"}
        reverse_prov = {"gemini": "Gemini (Google)", "claude": "Claude (Anthropic)"}
        combo_provider = ctk.CTkComboBox(dialog, values=["Gemini (Google)", "Claude (Anthropic)"], width=500)
        combo_provider.pack(padx=20, pady=4)
        combo_provider.set(reverse_prov.get(getattr(config, "ai_provider", "gemini"), "Gemini (Google)"))

        # Ô nhập GEMINI_API_KEY
        lbl_api = ctk.CTkLabel(dialog, text="Google Gemini API Key:", font=ctk.CTkFont(size=12, weight="bold"))
        lbl_api.pack(padx=20, anchor="w", pady=(8, 2))

        entry_api = ctk.CTkEntry(
            dialog,
            width=500,
            placeholder_text="AIzaSy... (hỗ trợ nhiều key cách nhau bằng dấu phẩy)",
            show="•"
        )
        entry_api.pack(padx=20, pady=4)
        if getattr(config, "gemini_api_key_raw", None):
            entry_api.insert(0, config.gemini_api_key_raw)
        elif config.gemini_api_key:
            entry_api.insert(0, config.gemini_api_key)

        # Chọn mô hình Gemini
        lbl_model = ctk.CTkLabel(dialog, text="Mô hình Gemini:", font=ctk.CTkFont(size=12, weight="bold"))
        lbl_model.pack(padx=20, anchor="w", pady=(5, 2))

        gemini_models = ["gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-3.8-flash", "gemini-3.1-flash-lite"]
        combo_model = ctk.CTkComboBox(dialog, values=gemini_models, width=500)
        combo_model.pack(padx=20, pady=4)
        if config.gemini_model in gemini_models:
            combo_model.set(config.gemini_model)
        else:
            combo_model.set("gemini-3.5-flash")

        # Ô nhập ANTHROPIC_API_KEY
        lbl_claude_api = ctk.CTkLabel(dialog, text="Anthropic Claude API Key:", font=ctk.CTkFont(size=12, weight="bold"))
        lbl_claude_api.pack(padx=20, anchor="w", pady=(8, 2))

        entry_claude_api = ctk.CTkEntry(
            dialog,
            width=500,
            placeholder_text="sk-ant-api03-... (lấy tại console.anthropic.com)",
            show="•"
        )
        entry_claude_api.pack(padx=20, pady=4)
        if getattr(config, "anthropic_api_key", None):
            entry_claude_api.insert(0, config.anthropic_api_key)

        # Chọn mô hình Claude
        lbl_claude_model = ctk.CTkLabel(dialog, text="Mô hình Claude:", font=ctk.CTkFont(size=12, weight="bold"))
        lbl_claude_model.pack(padx=20, anchor="w", pady=(5, 2))

        claude_models = [
            "claude-sonnet-5-5",
            "claude-haiku-5-5",
            "claude-opus-5-5",
            "claude-sonnet-5",
            "claude-opus-5",
            "claude-sonnet-4-6",
            "claude-3-7-sonnet-20250219",
            "claude-3-5-sonnet-20241022"
        ]
        combo_claude_model = ctk.CTkComboBox(dialog, values=claude_models, width=500)
        combo_claude_model.pack(padx=20, pady=4)
        cur_claude_m = getattr(config, "claude_model", "claude-sonnet-5-5")
        if cur_claude_m in claude_models:
            combo_claude_model.set(cur_claude_m)
        else:
            combo_claude_model.set("claude-sonnet-5-5")

        # Độ trễ giữa các hành động (Action Delay)
        delay_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        delay_frame.pack(fill="x", padx=20, pady=5)

        lbl_delay = ctk.CTkLabel(delay_frame, text="Độ trễ quan sát (s):", font=ctk.CTkFont(size=12, weight="bold"))
        lbl_delay.pack(side="left")
        entry_delay = ctk.CTkEntry(delay_frame, width=80)
        entry_delay.pack(side="left", padx=(10, 20))
        entry_delay.insert(0, str(config.action_delay))

        lbl_steps = ctk.CTkLabel(delay_frame, text="Số bước tối đa:", font=ctk.CTkFont(size=12, weight="bold"))
        lbl_steps.pack(side="left")
        entry_steps = ctk.CTkEntry(delay_frame, width=80)
        entry_steps.pack(side="left", padx=10)
        entry_steps.insert(0, str(config.max_steps))

        # Nút Lưu cấu hình
        def save_and_close():
            chosen_prov = provider_map.get(combo_provider.get().strip(), "gemini")
            new_key = entry_api.get().strip()
            new_model = combo_model.get().strip()
            new_claude_key = entry_claude_api.get().strip()
            new_claude_model = combo_claude_model.get().strip()

            try:
                new_delay = float(entry_delay.get().strip())
                new_steps = int(entry_steps.get().strip())
            except ValueError:
                messagebox.showerror("Lỗi", "Độ trễ hoặc số bước phải là số hợp lệ!")
                return

            config.save(
                ai_provider=chosen_prov,
                gemini_api_key=new_key,
                gemini_model=new_model,
                anthropic_api_key=new_claude_key,
                claude_model=new_claude_model,
                action_delay=new_delay,
                max_steps=new_steps
            )
            self._append_log("INFO", f"Đã lưu cấu hình. Provider hiện tại: {chosen_prov.upper()}")
            dialog.destroy()

        btn_save = ctk.CTkButton(
            dialog,
            text="LƯU CẤU HÌNH",
            font=ctk.CTkFont(size=13, weight="bold"),
            height=36,
            fg_color="#10b981",
            hover_color="#059669",
            command=save_and_close
        )
        btn_save.pack(padx=20, pady=20, fill="x")


def run_gui():
    app = GeminiAutoPilotApp()
    app.mainloop()


if __name__ == "__main__":
    run_gui()
