"""
TẦNG 2+: VERCEL AGENT-DESKTOP ADAPTER
Điều khiển và quan sát ứng dụng Windows thông qua Accessibility Tree (UI Automation)
Không dựa vào việc đoán tọa độ ảnh màn hình, không tốn token gửi ảnh, click chuẩn xác 100% bằng @ref ID.
"""

import json
import subprocess
from pathlib import Path
from core.safety import safety

AGENT_DESKTOP_EXE = Path(__file__).resolve().parent.parent / "bin" / "agent-desktop.exe"


class AgentDesktopManager:
    def __init__(self, exe_path: Path = AGENT_DESKTOP_EXE):
        self.exe_path = exe_path

    def is_available(self) -> bool:
        return self.exe_path.exists() and self.exe_path.is_file()

    def run_raw(self, args: list[str], timeout: int = 15) -> dict:
        """Thực thi lệnh agent-desktop.exe và phân tích JSON output"""
        if not self.is_available():
            return {
                "ok": False,
                "error": f"Không tìm thấy agent-desktop.exe tại '{self.exe_path}'."
            }

        cmd = [str(self.exe_path)] + args
        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout
            )
            stdout = res.stdout.strip()
            stderr = res.stderr.strip()

            if stdout:
                try:
                    return json.loads(stdout)
                except json.JSONDecodeError:
                    return {"ok": res.returncode == 0, "raw_stdout": stdout, "raw_stderr": stderr}

            return {
                "ok": res.returncode == 0,
                "error": stderr or "Không nhận được phản hồi từ agent-desktop."
            }
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": f"Lệnh agent-desktop bị timeout sau {timeout}s."}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def get_status(self) -> dict:
        return self.run_raw(["status"])

    def snapshot(self, app: str = "", interactive_only: bool = True, compact: bool = True,
                 bounds: bool = True) -> dict:
        """
        Chụp cây Accessibility. Không chỉ định app -> cửa sổ đang focus (--surface focused).
        Nếu nhiều cửa sổ cùng khớp (AMBIGUOUS_TARGET) tự chọn cửa sổ đang focus/hiển thị rồi thử lại.
        """
        args = ["snapshot"]
        if app:
            args.extend(["--app", app])
        else:
            args.extend(["--surface", "focused"])
        if interactive_only:
            args.append("-i")
        if compact:
            args.append("--compact")
        if bounds:
            args.append("--include-bounds")
        res = self.run_raw(args)

        err = res.get("error")
        if not res.get("ok") and isinstance(err, dict) and err.get("code") == "AMBIGUOUS_TARGET":
            cands = (err.get("details") or {}).get("candidates") or []
            pick = next((c for c in cands if c.get("is_focused")), None) \
                or next((c for c in cands if c.get("visible")), None) or (cands[0] if cands else None)
            if pick and pick.get("id"):
                res = self.run_raw(args + ["--window-id", pick["id"]])
        return res

    def find_elements(self, app: str, query: str = "", role: str = "") -> dict:
        args = ["find", "--app", app]
        if query:
            args.extend(["--text", query])
        if role:
            args.extend(["--role", role])
        return self.run_raw(args)

    def click(self, ref_id: str, headed: bool = False) -> dict:
        if safety.is_stopped():
            return {"ok": False, "error": safety.get_stop_reason()}
        args = ["click", ref_id]
        if headed:
            args.append("--headed")
        return self.run_raw(args)

    def double_click(self, ref_id: str) -> dict:
        if safety.is_stopped():
            return {"ok": False, "error": safety.get_stop_reason()}
        return self.run_raw(["double-click", ref_id, "--headed"])

    def type_text(self, ref_id: str, text: str) -> dict:
        if safety.is_stopped():
            return {"ok": False, "error": safety.get_stop_reason()}
        return self.run_raw(["type", ref_id, text])

    def focus_window(self, app: str) -> dict:
        return self.run_raw(["focus-window", "--app", app])

    def list_apps(self) -> dict:
        return self.run_raw(["list-apps"])

    def list_windows(self, app: str = "") -> dict:
        args = ["list-windows"]
        if app:
            args.extend(["--app", app])
        return self.run_raw(args)


agent_desktop = AgentDesktopManager()
