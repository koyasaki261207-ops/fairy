"""
Test hệ thống tự động hóa Gemini AutoPilot
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from core.safety import safety
from core.controller import controller
from core.uiauto import uiauto
from core.vision import vision
import core.tools as tools
import core.brain as brain

print("1. Kiểm tra import module: OK")

# Test powershell execution
res = controller.run_powershell("Write-Output 'Powershell Test OK'")
print("2. Kiểm tra thực thi PowerShell:", res)
assert res["success"] is True
assert "Powershell Test OK" in res["stdout"]

# Test safety check
safe, reason = safety.check_command_safety("format C:")
print("3. Kiểm tra cơ chế Safe Mode chặn lệnh nguy hiểm:", safe, "->", reason)
assert safe is False

safe, _ = safety.check_command_safety("Get-ChildItem")
assert safe is True

# Test Code Interpreter (run_python_code)
py_res = tools.run_python_code("import math; print('CALC_TEST:', math.factorial(5))")
print("4. Kiểm tra Code Interpreter (run_python_code):", py_res.strip())
assert "120" in py_res

# Test Skill Repository
skills_list = tools.list_skills()
print("5. Kiểm tra Danh mục Kỹ năng:", skills_list.strip())
assert "solitaire_rules" in skills_list

skill_content = tools.load_skill("solitaire_rules")
print("6. Kiểm tra Nạp kỹ năng solitaire_rules: OK (độ dài", len(skill_content), "ký tự)")
assert "SOLITAIRE" in skill_content

# Test Card Move Validator
test_val_fail = tools.validate_card_move("J Tép", "10 Bích")
print("6.1 Kiểm tra chặn nước đi phạm luật (J lên 10):", "BỊ TỪ CHỐI" if "❌" in test_val_fail else "LỖI")
assert "❌" in test_val_fail

test_val_ok = tools.validate_card_move("7 Rô", "8 Tép")
print("6.2 Kiểm tra duyệt nước đi hợp lệ (7 Rô lên 8 Tép):", "HỢP LỆ" if "✅" in test_val_ok else "LỖI")
assert "✅" in test_val_ok

# Test blocking raw pyautogui inside run_python_code
block_pyautogui = tools.run_python_code("import pyautogui; pyautogui.moveTo(100, 100)")
print("6.3 Kiểm tra chặn pyautogui bừa bãi trong Code Interpreter:", "CHẶN THÀNH CÔNG" if "Lỗi: Không được gọi" in block_pyautogui else "THẤT BẠI")
assert "Lỗi: Không được gọi" in block_pyautogui

# Test Vercel agent-desktop adapter
from core.agent_desktop import agent_desktop
print("6.4 Kiểm tra Vercel agent-desktop engine:", "SẴN SÀNG" if agent_desktop.is_available() else "CHƯA CÓ")
assert agent_desktop.is_available() is True
status_info = agent_desktop.get_status()
assert status_info.get("ok") is True
print(f"    -> Platform: {status_info['data']['platform']}, Version: {status_info['data']['version']}")

# Test Claude Brain Tool Schema
from core.claude_brain import CLAUDE_TOOLS_SCHEMA
print(f"6.5 Kiểm tra Claude Brain Schema: OK (Đã ánh xạ {len(CLAUDE_TOOLS_SCHEMA)} công cụ sang Anthropic format)")
assert len(CLAUDE_TOOLS_SCHEMA) == len(tools.ALL_TOOLS)

# Test tool list
print(f"\n7. Danh sách công cụ khả dụng ({len(tools.ALL_TOOLS)} công cụ):")
for t in tools.ALL_TOOLS:
    print(f"   - {t.__name__}")

print("\n🎉 TOÀN BỘ CÁC MODULE HOẠT ĐỘNG HOÀN HẢO!")
