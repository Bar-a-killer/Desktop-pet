import platform


class WindowDetector:
    def __init__(self):
        self.system = platform.system()
        self._ewmh = None

        if self.system == "Linux":
            try:
                import ewmh
                self._ewmh = ewmh.EWMH()
            except Exception as e:
                print(f"[WindowDetector] ewmh 初始化失敗: {e}")

    def get_windows(self, own_title: str = "desktop_pet") -> list[tuple[int, int, int, int]]:
        if self.system == "Windows":
            return self._get_windows_win(own_title)
        return self._get_windows_linux(own_title)

    def _get_windows_win(self, own_title: str) -> list[tuple[int, int, int, int]]:
        try:
            import pygetwindow as gw
            result = []
            for w in gw.getAllWindows():
                if not w.visible or w.width <= 0 or w.height <= 0:
                    continue
                if own_title in (w.title or ""):
                    continue
                result.append((w.left, w.top, w.width, w.height))
            return result
        except Exception as e:
            print(f"[WindowDetector] Windows 偵測失敗: {e}")
            return []

    def _get_windows_linux(self, own_title: str) -> list[tuple[int, int, int, int]]:
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

                    geom = win.get_geometry()
                    # 轉換成螢幕絕對座標
                    translated = win.translate_coords(geom.root, 0, 0)
                    x, y = translated.x, translated.y
                    w, h = geom.width, geom.height

                    if w > 10 and h > 10:
                        result.append((x, y, w, h))
                except Exception:
                    continue
            return result
        except Exception as e:
            print(f"[WindowDetector] Linux 偵測失敗: {e}")
            return []
