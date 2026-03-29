import platform
from dataclasses import dataclass
from logger import print_log


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
                print_log(f"[WindowDetector] ewmh 初始化失敗: {e}")
            try:
                from Xlib import display
                self._xdisplay = display.Display()
                self._x11_offset_x, self._x11_offset_y = self._calc_x11_offset()
                print_log(f"[WindowDetector] X11 偏移: ({self._x11_offset_x}, {self._x11_offset_y})")
            except Exception as e:
                print_log(f"[WindowDetector] Xlib 初始化失敗: {e}")
                self._x11_offset_x = 0
                self._x11_offset_y = 0
    def _calc_x11_offset(self) -> tuple[int, int]:
        """計算 X11 座標系跟 Qt 虛擬桌面座標系的偏移"""
        try:
            from PyQt6.QtWidgets import QApplication
            screens = QApplication.screens()
            qt_min_x = min(s.geometry().x() for s in screens)
            qt_min_y = min(s.geometry().y() for s in screens)

            # X11 root 的左上角在 Qt 座標系的位置
            root = self._xdisplay.screen().root
            geom = root.get_geometry()
            # X11 的 (0,0) 對應到 Qt 的 (qt_min_x, qt_min_y)
            return qt_min_x, qt_min_y
        except Exception:
            return 0, 0
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
                return Rect(self._x11_offset_x, self._x11_offset_y, screen_w, wa_y)
            elif wa_y + wa_h < screen_h:
                return Rect(self._x11_offset_x, self._x11_offset_y + wa_y + wa_h, 
                            screen_w, screen_h - (wa_y + wa_h))
            elif wa_x > 0:
                return Rect(self._x11_offset_x, self._x11_offset_y, wa_x, screen_h)
            elif wa_x + wa_w < screen_w:
                return Rect(self._x11_offset_x + wa_x + wa_w, self._x11_offset_y,
                            screen_w - (wa_x + wa_w), screen_h)
            return None
        except Exception as e:
            print_log(f"[WindowDetector] 工作欄偵測失敗: {e}")
            return None

    def _get_windows_linux(self, own_title: str) -> list[Rect]:
        if self._ewmh is None:
            return []
        try:
            result = []
            client_list = self._ewmh.getClientList()
            if not client_list:
                return result
                
            for win in client_list[:50]:  # 限制處理視窗數量，避免過度負載
                try:
                    # 快速檢查視窗是否仍然有效
                    try:
                        geom = win.get_geometry()
                        if geom.width < 10 or geom.height < 10:
                            continue
                    except:
                        continue  # 視窗無效，跳過
                    
                    title = self._ewmh.getWmName(win) or ""
                    if isinstance(title, bytes):
                        title = title.decode("utf-8", errors="ignore")
                    if own_title in title:
                        continue

                    # 取得視窗類型
                    win_type = self._ewmh.getWmWindowType(win, str=True) or []
                    wm_state = self._ewmh.getWmState(win, str=True) or []
                    if "_NET_WM_STATE_HIDDEN" in wm_state:
                        continue
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
                        "_NET_WM_WINDOW_TYPE_DOCK",
                        "_NET_WM_WINDOW_TYPE_TOOLBAR",
                        "_NET_WM_WINDOW_TYPE_UTILITY",
                        "_NET_WM_WINDOW_TYPE_POPUP",
                        "_NET_WM_WINDOW_TYPE_POPUP_MENU",
                        "_NET_WM_WINDOW_TYPE_APPLET",
                    ]
                    if win_type and not any(t in wall_types for t in win_type):
                        continue

                    try:
                        import subprocess
                        proc = subprocess.run(
                            ["xdotool", "getwindowgeometry", "--shell", str(win.id)],
                            capture_output=True, text=True, timeout=0.1
                        )
                        geo_vars = {}
                        for line in proc.stdout.strip().split('\n'):
                            if '=' in line:
                                k, v = line.split('=', 1)
                                geo_vars[k] = int(v)
                        x = geo_vars.get('X', 0)
                        y = geo_vars.get('Y', 0)
                        w = geo_vars.get('WIDTH', geom.width)
                        h = geo_vars.get('HEIGHT', geom.height)
                    except Exception:
                        translated = win.translate_coords(geom.root, 0, 0)
                        x = translated.x
                        y = translated.y
                        w, h = geom.width, geom.height

                    # 嘗試獲取框架裝飾信息
                    decoration_margin = 0
                    try:
                        if self._xdisplay:
                            win_xlib = self._xdisplay.create_resource_object("window", win.id)
                            extents_atom = self._xdisplay.get_atom("_NET_FRAME_EXTENTS")
                            extents = win_xlib.get_property(extents_atom, 0, 0, 4)
                            if extents and extents.value:
                                values = list(extents.value)
                                if len(values) == 4:
                                    left, right, top, bottom = map(int, values)
                                    print_log(f"[WindowDetector] 窗口 '{title[:20]}' 裝飾: 左{left} 右{right} 上{top} 下{bottom}")
                                    x -= left
                                    y -= top
                                    w += left + right
                                    h += top + bottom
                                    decoration_margin = 0  # 已使用實際裝飾
                    except:
                        pass

                    if decoration_margin > 0:
                        # 如果沒有獲取到裝飾信息，使用經驗值
                        x -= decoration_margin
                        y -= decoration_margin
                        w += decoration_margin * 2
                        h += decoration_margin * 2

                    if w > 10 and h > 10 and x >= -5000 and y >= -5000 and x < 5000 and y < 5000:
                        result.append(Rect(x, y, w, h))
                        print_log(f"[WindowDetector] 添加窗口: ({x},{y}) {w}x{h} '{title[:15]}'")
                except Exception as e:
                    # 打印失败详情便于调试
                    print_log(f"[WindowDetector] 单个窗口检测失败: {e}")
                    continue
            return result
        except Exception as e:
            print_log(f"[WindowDetector] Linux 視窗偵測失敗: {e}")
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
            
            # 支持四个方向的任务栏
            if wa.bottom < sm_h:
                # 下方任务栏
                return Rect(0, wa.bottom, sm_w, sm_h - wa.bottom)
            elif wa.top > 0:
                # 上方任务栏
                return Rect(0, 0, sm_w, wa.top)
            elif wa.left > 0:
                # 左侧任务栏
                return Rect(0, 0, wa.left, sm_h)
            elif wa.right < sm_w:
                # 右侧任务栏
                return Rect(wa.right, 0, sm_w - wa.right, sm_h)
            return None
        except Exception as e:
            print_log(f"[WindowDetector] Windows 工作欄偵測失敗: {e}")
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
            print_log(f"[WindowDetector] Windows 視窗偵測失敗: {e}")
            return []
