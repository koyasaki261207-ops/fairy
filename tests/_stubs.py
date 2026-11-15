"""
Cài module giả cho các thư viện điều khiển hệ thống khi chúng chưa được cài (để chạy test logic thuần trên mọi máy).
Gọi install() TRƯỚC khi import core.tools / core.controller.
"""
import sys
import types as _t


def _missing(name: str) -> bool:
    try:
        __import__(name)
        return False
    except Exception:
        return True


def install():
    if _missing("pyautogui"):
        pg = _t.ModuleType("pyautogui")
        pg.size = lambda: (1920, 1080)
        pg.FAILSAFE = True
        pg.PAUSE = 0

        class FailSafeException(Exception):
            pass

        pg.FailSafeException = FailSafeException
        for n in ["moveTo", "click", "doubleClick", "rightClick", "mouseDown", "mouseUp", "scroll", "hotkey", "press", "write"]:
            setattr(pg, n, lambda *a, **k: None)
        sys.modules["pyautogui"] = pg
    if _missing("pynput"):
        pn, kb = _t.ModuleType("pynput"), _t.ModuleType("pynput.keyboard")

        class Listener:
            def __init__(self, **k):
                self.daemon = False

            def start(self):
                pass

            def is_alive(self):
                return True

        class Key:
            f8 = ctrl_l = ctrl_r = shift = shift_r = object()

        kb.Listener, kb.Key, pn.keyboard = Listener, Key, kb
        sys.modules["pynput"], sys.modules["pynput.keyboard"] = pn, kb
    if _missing("uiautomation"):
        ua = _t.ModuleType("uiautomation")
        ua.SetGlobalSearchTimeout = lambda *a: None
        names = ["ButtonControl", "EditControl", "MenuItemControl", "TabItemControl", "CheckBoxControl",
                 "ComboBoxControl", "HyperlinkControl", "ListItemControl", "TextControl"]
        ua.ControlType = _t.SimpleNamespace(**{n: i for i, n in enumerate(names)})
        ua.GetForegroundControl = lambda: None
        sys.modules["uiautomation"] = ua
    if _missing("pyperclip"):
        pc = _t.ModuleType("pyperclip")
        pc.paste, pc.copy = (lambda: ""), (lambda t: None)
        sys.modules["pyperclip"] = pc
