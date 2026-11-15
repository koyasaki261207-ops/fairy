"""
PHIÊN POWERSHELL GIỮ SỐNG (PERSISTENT SHELL)
Một tiến trình powershell.exe duy nhất cho cả lượt chạy: mỗi lệnh sau lệnh đầu không còn tốn
~0.3-0.5s khởi động tiến trình. Biến và thư mục hiện hành được giữ giữa các lệnh.

Giao thức: mỗi lệnh được ghi ra file .ps1 tạm (chịu được lệnh nhiều dòng), shell chạy file đó rồi in
các dòng đánh dấu (marker) kèm id ngẫu nhiên để tách stdout / stderr / mã thoát.
"""

import os
import queue
import subprocess
import tempfile
import threading
import uuid
from pathlib import Path

_INIT = (
    "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8;"
    "$OutputEncoding=[System.Text.Encoding]::UTF8;"
    "$ProgressPreference='SilentlyContinue';$ErrorActionPreference='Continue'"
)


class PersistentShell:
    def __init__(self):
        self._proc: subprocess.Popen | None = None
        self._lines: "queue.Queue[str | None]" = queue.Queue()
        self._lock = threading.Lock()
        self._tmpdir = Path(tempfile.gettempdir()) / "fairy_ps"

    # ---------------- vòng đời ----------------
    def _start(self):
        self._tmpdir.mkdir(parents=True, exist_ok=True)
        self._lines = queue.Queue()
        self._proc = subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-NoLogo", "-NonInteractive", "-ExecutionPolicy", "Bypass",
             "-Command", "-"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        threading.Thread(target=self._reader, args=(self._proc, self._lines), daemon=True).start()
        self._send(_INIT)

    @staticmethod
    def _reader(proc, q):
        try:
            for raw in iter(proc.stdout.readline, b""):
                q.put(raw.decode("utf-8", errors="replace").rstrip("\r\n"))
        except Exception:
            pass
        q.put(None)  # EOF: tiến trình đã chết

    def _send(self, text: str):
        self._proc.stdin.write((text + "\n").encode("utf-8"))
        self._proc.stdin.flush()

    def alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def close(self):
        with self._lock:
            self._kill()

    def _kill(self):
        if self._proc is not None:
            try:
                self._proc.kill()
            except Exception:
                pass
        self._proc = None

    # ---------------- chạy lệnh ----------------
    def run(self, command: str, timeout: int = 30) -> dict:
        """Trả về {success, returncode, stdout, stderr} hoặc {success: False, error} khi hết giờ."""
        with self._lock:
            if not self.alive():
                self._start()
            rid = uuid.uuid4().hex[:10]
            script = self._tmpdir / f"cmd_{rid}.ps1"
            script.write_text(command, encoding="utf-8-sig")
            m_out, m_err, m_end = f"<<<OUT-{rid}>>>", f"<<<ERR-{rid}>>>", f"<<<END-{rid}>>>"
            wrapper = (
                "$global:LASTEXITCODE=0;"
                f"$__r=& '{script}' 2>&1;"
                "$__e=@($__r|Where-Object{$_ -is [System.Management.Automation.ErrorRecord]});"
                "$__o=@($__r|Where-Object{$_ -isnot [System.Management.Automation.ErrorRecord]});"
                f"'{m_out}';($__o|Out-String -Width 4096).TrimEnd();"
                f"'{m_err}';($__e|Out-String -Width 4096).TrimEnd();"
                f"'{m_end} '+$global:LASTEXITCODE+' '+$__e.Count"
            )
            try:
                self._send(wrapper)
                return self._collect(m_out, m_err, m_end, timeout)
            except (BrokenPipeError, OSError) as e:
                self._kill()
                return {"success": False, "error": f"Phiên PowerShell bị ngắt: {e}"}
            finally:
                try:
                    script.unlink()
                except Exception:
                    pass

    def _collect(self, m_out, m_err, m_end, timeout) -> dict:
        out, err, section = [], [], None
        while True:
            try:
                line = self._lines.get(timeout=timeout)
            except queue.Empty:
                self._kill()  # kẹt -> giết và khởi động lại ở lần sau
                return {"success": False, "error": f"Lệnh bị timeout sau {timeout} giây."}
            if line is None:
                self._kill()
                return {"success": False, "error": "Tiến trình PowerShell đã thoát đột ngột."}
            if line == m_out:
                section = out
            elif line == m_err:
                section = err
            elif line.startswith(m_end):
                parts = line[len(m_end):].split()
                code = int(parts[0]) if parts and parts[0].lstrip("-").isdigit() else 0
                n_err = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
                return {
                    "success": code == 0 and n_err == 0,
                    "returncode": code or n_err,
                    "stdout": "\n".join(out).strip(),
                    "stderr": "\n".join(err).strip(),
                }
            elif section is not None:
                section.append(line)


shell = PersistentShell()
