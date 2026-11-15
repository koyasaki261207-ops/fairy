"""
TẦNG 2: WINDOWS UI AUTOMATION (TỰ ĐỘNG HÓA GIAO DIỆN CHUẨN XÁC 100%)
Sử dụng Windows Accessibility API để tương tác trực tiếp với các Button, Input, Menu...
Không phụ thuộc vào việc thay đổi kích thước cửa sổ hay độ phân giải màn hình.
"""

import time
try:
    import pythoncom
    pythoncom.CoInitialize()
except Exception:
    pass
import uiautomation as auto
from core.safety import safety
from config import config

# Thiết lập timeout tìm kiếm của uiautomation để không bị treo
auto.SetGlobalSearchTimeout(1.5)


class UIAutomator:
    def __init__(self):
        pass

    def get_active_window_elements(self, max_elements: int = 40) -> list[dict]:
        """
        Quét và trích xuất danh sách các phần tử tương tác được trên cửa sổ đang mở.
        Bao gồm: Button, Edit (ô nhập), MenuItem, TabItem, CheckBox, ComboBox, Hyperlink.
        """
        elements = []
        try:
            top_control = auto.GetForegroundControl()
            if not top_control:
                return []

            # Tập hợp các loại control cần lấy
            target_types = {
                auto.ControlType.ButtonControl: "Button",
                auto.ControlType.EditControl: "Edit",
                auto.ControlType.MenuItemControl: "MenuItem",
                auto.ControlType.TabItemControl: "TabItem",
                auto.ControlType.CheckBoxControl: "CheckBox",
                auto.ControlType.ComboBoxControl: "ComboBox",
                auto.ControlType.HyperlinkControl: "Link",
                auto.ControlType.ListItemControl: "ListItem",
                auto.ControlType.TextControl: "Text"
            }

            def walk(control, depth=0):
                if len(elements) >= max_elements or depth > 4:
                    return

                try:
                    c_type = control.ControlType
                    name = control.Name.strip() if control.Name else ""
                    rect = control.BoundingRectangle

                    # Chỉ lấy các control có tên rõ ràng và có kích thước hợp lệ
                    if name and c_type in target_types and rect.width() > 5 and rect.height() > 5:
                        center_x = (rect.left + rect.right) // 2
                        center_y = (rect.top + rect.bottom) // 2
                        elements.append({
                            "name": name,
                            "type": target_types[c_type],
                            "x": center_x,
                            "y": center_y,
                            "width": rect.width(),
                            "height": rect.height()
                        })

                    for child in control.GetChildren():
                        walk(child, depth + 1)
                except Exception:
                    pass

            walk(top_control, 0)
        except Exception:
            pass

        return elements

    def click_element_by_name(self, name: str, control_type: str = "") -> dict:
        """
        Tìm và click vào phần tử giao diện theo tên (không phân biệt hoa thường).
        Ví dụ: name='Save' hoặc name='Lưu' hoặc name='Search'.
        """
        if safety.is_stopped():
            return {"success": False, "error": safety.get_stop_reason()}

        name_lower = name.lower()
        try:
            top = auto.GetForegroundControl()
            if not top:
                top = auto.GetRootControl()

            # Quét tìm kiếm element
            matched = None
            for child in top.GetChildren():
                if child.Name and name_lower in child.Name.lower():
                    matched = child
                    break

            # Nếu chưa thấy, tìm kiếm sâu hơn
            if not matched:
                def search_deep(ctrl, depth=0):
                    nonlocal matched
                    if matched or depth > 4:
                        return
                    for c in ctrl.GetChildren():
                        if c.Name and name_lower in c.Name.lower():
                            matched = c
                            return
                        search_deep(c, depth + 1)

                search_deep(top)

            if matched:
                # Thực hiện click
                rect = matched.BoundingRectangle
                center_x = (rect.left + rect.right) // 2
                center_y = (rect.top + rect.bottom) // 2

                # Thử gọi click trực tiếp của pattern
                try:
                    invoke_pat = matched.GetInvokePattern()
                    if invoke_pat:
                        invoke_pat.Invoke()
                        time.sleep(config.action_delay)
                        return {
                            "success": True,
                            "action": f"Đã kích hoạt Invoke Pattern trên '{matched.Name}' ({matched.ControlTypeName})"
                        }
                except Exception:
                    pass

                # Fallback: Click vật lý vào tâm phần tử
                matched.Click(simulateMove=False)
                time.sleep(config.action_delay)
                return {
                    "success": True,
                    "action": f"Đã click vào '{matched.Name}' tại ({center_x}, {center_y})"
                }
            else:
                return {
                    "success": False,
                    "error": f"Không tìm thấy phần tử nào có tên chứa '{name}' trên cửa sổ hiện tại."
                }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def type_into_element(self, name: str, text: str) -> dict:
        """
        Tìm ô nhập liệu theo tên hoặc nhãn và điền văn bản vào.
        """
        if safety.is_stopped():
            return {"success": False, "error": safety.get_stop_reason()}

        name_lower = name.lower()
        try:
            top = auto.GetForegroundControl() or auto.GetRootControl()
            matched = None

            def search_edit(ctrl, depth=0):
                nonlocal matched
                if matched or depth > 4:
                    return
                for c in ctrl.GetChildren():
                    if (c.ControlType == auto.ControlType.EditControl or "edit" in c.ControlTypeName.lower()):
                        if not name or (c.Name and name_lower in c.Name.lower()):
                            matched = c
                            return
                    search_edit(c, depth + 1)

            search_edit(top)

            if matched:
                # Thử dùng ValuePattern để set trực tiếp
                try:
                    val_pat = matched.GetValuePattern()
                    if val_pat and not val_pat.IsReadOnly:
                        val_pat.SetValue(text)
                        time.sleep(config.action_delay)
                        return {"success": True, "action": f"Đã nhập trực tiếp vào ô '{matched.Name}'"}
                except Exception:
                    pass

                # Fallback: Focus vào ô rồi paste
                matched.SetFocus()
                time.sleep(0.1)
                import pyperclip
                import pyautogui
                pyperclip.copy(text)
                pyautogui.hotkey("ctrl", "a")
                pyautogui.hotkey("ctrl", "v")
                time.sleep(config.action_delay)
                return {"success": True, "action": f"Đã paste văn bản vào ô '{matched.Name}'"}
            else:
                return {"success": False, "error": f"Không tìm thấy ô nhập liệu nào có tên '{name}'"}
        except Exception as e:
            return {"success": False, "error": str(e)}


uiauto = UIAutomator()
