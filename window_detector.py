import platform
from dataclasses import dataclass


@dataclass
class Rect:
    x: int
    y: int
    w: int
    h: int


class WindowDetector:
    def __init__(self):
        self.system = platform.system()
        self._ewmh = None
        self._xdisplay = None

        if self.system == "Linux":
            try:
                import ewmh as ewmh_mod
                self._ewmh = ewmh_mod.EWMH()
            except Exception as e:
                print(f"[WindowDetector] ewmh 初始化失敗: {e}")
            try:
                from Xlib import display
                self._xdisplay = display.Display()
            except Exception as e:
                print(f"[WindowDetector] Xlib 初始化失敗: {e}")

    def get_taskbar(self) -> Rect | None:
        if self.system == "Linux":
            return self._get_taskbar_linux()
        elif self.system == "Windows":
            return self._get_taskbar_win()
        return None

    def get_windows(self, own_title: str = "desktop_pet") -> list[Rect]:
        if self.system == "Windows":
            return self._get_windows_win(own_title)
        return self._get_windows_linux(own_title)

    def _get_taskbar_linux(self) -> Rect | None:
        if self._ewmh is None or self._xdisplay is None:
            return None
        try:
            root = self._xdisplay.screen().root
            geom = root.get_geometry()
            screen_w = geom.width
            screen_h = geom.height

            workarea = self._ewmh.getWorkArea()
            if not workarea:
                return None

            wa_x  = workarea[0]
            wa_y  = workarea[1]
            wa_w  = workarea[2]
            wa_h  = workarea[3]

            if wa_y > 0:
                return Rect(0, 0, screen_w, wa_y)
            elif wa_y + wa_h < screen_h:
                return Rect(0, wa_y + wa_h, screen_w, screen_h - (wa_y + wa_h))
            elif wa_x > 0:
                return Rect(0, 0, wa_x, screen_h)
            elif wa_x + wa_w < screen_w:
                return Rect(wa_x + wa_w, 0, screen_w - (wa_x + wa_w), screen_h)
            return None
        except Exception as e:
            print(f"[WindowDetector] 工作欄偵測失敗: {e}")
            return None

    def _get_windows_linux(self, own_title: str) -> list[Rect]:
        if self._ewmh is None:
            return []
        try:
            result = []
            for win in self._ewmh.getClientList():
                try:
                    title = self._ewmh.getWmName(win) or ""
                    if isinstance(title, bytes):
                        title = title.decode("utf-8", errors="ignore")
                    if own_title in title:
                        continue

                    # 取得視窗類型
                    win_type = self._ewmh.getWmWindowType(win, str=True) or []

                    # 跳過桌面本身
                    skip_types = [
                        "_NET_WM_WINDOW_TYPE_DESKTOP",
                        "_NET_WM_WINDOW_TYPE_SPLASH",
                    ]
                    if any(t in skip_types for t in win_type):
                        continue

                    # Plasma 元件也加入牆壁
                    wall_types = [
                        "_NET_WM_WINDOW_TYPE_NORMAL",
                        "_NET_WM_WINDOW_TYPE_DIALOG",
                        "_NET_WM_WINDOW_TYPE_DOCK",      # panel
                        "_NET_WM_WINDOW_TYPE_TOOLBAR",
                        "_NET_WM_WINDOW_TYPE_UTILITY",
                    ]
                    if not any(t in wall_types for t in win_type):
                        continue

                    geom = win.get_geometry()
                    translated = win.translate_coords(geom.root, 0, 0)
                    x, y = translated.x, translated.y
                    w, h = geom.width, geom.height

                    if w > 10 and h > 10:
                        result.append(Rect(x, y, w, h))
                except Exception:
                    continue
            return result
        except Exception as e:
            print(f"[WindowDetector] Linux 視窗偵測失敗: {e}")
            return []

    def _get_taskbar_win(self) -> Rect | None:
        try:
            import ctypes
            SPI_GETWORKAREA = 0x0030
            class RECT(ctypes.Structure):
                _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                             ("right", ctypes.c_long), ("bottom", ctypes.c_long)]
            wa = RECT()
            ctypes.windll.user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(wa), 0)
            sm_w = ctypes.windll.user32.GetSystemMetrics(0)
            sm_h = ctypes.windll.user32.GetSystemMetrics(1)
            if wa.bottom < sm_h:
                return Rect(0, wa.bottom, sm_w, sm_h - wa.bottom)
            elif wa.top > 0:
                return Rect(0, 0, sm_w, wa.top)
            return None
        except Exception as e:
            print(f"[WindowDetector] Windows 工作欄偵測失敗: {e}")
            return None

    def _get_windows_win(self, own_title: str) -> list[Rect]:
        try:
            import pygetwindow as gw
            result = []
            for w in gw.getAllWindows():
                if not w.visible or w.width <= 0 or w.height <= 0:
                    continue
                if own_title in (w.title or ""):
                    continue
                result.append(Rect(w.left, w.top, w.width, w.height))
            return result
        except Exception as e:
            print(f"[WindowDetector] Windows 視窗偵測失敗: {e}")
            return []
