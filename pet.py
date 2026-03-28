import sys
import time
import platform
import pymunk
from threading import Lock

from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPainter, QColor, QBrush
import config
from physics import WallManager
from window_detector import WindowDetector
from input_handler import InputHandler


class ScreenWindow(QWidget):
    """每個螢幕一個視窗，負責渲染球"""

    def __init__(self, screen, pet: "Pet"):
        super().__init__()
        self._pet = pet
        g = screen.geometry()
        self.sx = g.x()
        self.sy = g.y()
        self.sw = g.width()
        self.sh = g.height()

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool |
            Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setGeometry(g)
        self.show()

        if platform.system() == "Linux":
            self._set_click_through()

    def _set_click_through(self) -> None:
        try:
            import subprocess
            from Xlib import display, X
            from Xlib.ext import shape

            wid = int(self.winId())
            subprocess.run(["xprop", "-id", str(wid),
                "-f", "_NET_WM_WINDOW_TYPE", "32a",
                "-set", "_NET_WM_WINDOW_TYPE", "_NET_WM_WINDOW_TYPE_NOTIFICATION"],
                capture_output=True)
            subprocess.run(["xprop", "-id", str(wid),
                "-f", "_NET_WM_STATE", "32a",
                "-set", "_NET_WM_STATE", "_NET_WM_STATE_ABOVE"],
                capture_output=True)

            d = display.Display()
            win = d.create_resource_object("window", wid)
            shape.rectangles(win, shape.SO.Set, shape.SK.Input,
                X.Unsorted, 0, 0, [])
            d.flush()
        except Exception as e:
            print(f"[ScreenWindow] click-through 失敗: {e}")

    def paintEvent(self, event) -> None:
        x, y = self._pet.body.position

        # 球在這個螢幕範圍內才畫
        if not (self.sx - 50 <= x <= self.sx + self.sw + 50 and
                self.sy - 50 <= y <= self.sy + self.sh + 50):
            return

        # 物理座標 → 視窗內部座標
        draw_x = x - self.sx
        draw_y = y - self.sy

        t = self._pet._charge / self._pet.MAX_CHARGE
        r = int(100 + 155 * t)
        g = int(200 - 200 * t)
        b = int(255 - 255 * t)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QBrush(QColor(r, g, b, 220)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(
            int(draw_x - self._pet.PET_RADIUS),
            int(draw_y - self._pet.PET_RADIUS),
            self._pet.PET_RADIUS * 2,
            self._pet.PET_RADIUS * 2,
        )


class Pet:
    """主控制器，管理物理、輸入、計時器"""

    def __init__(self):
        self._load_config()
        self._setup_screens()
        self._setup_physics()
        self._setup_input()
        self._setup_timers()

    # ── 設定載入 ──────────────────────────────────────

    def _load_config(self) -> None:
        p  = config.physics()
        pt = config.pet()
        lc = config.launch()
        tm = config.timers()
        self.BASE_CHARGE    = lc["base_charge"]
        self.GRAVITY        = p["gravity"]
        self.ELASTICITY     = p["elasticity"]
        self.FRICTION       = p["friction"]
        self.PET_RADIUS     = pt["radius"]
        self.DRAG_THRESHOLD = pt["radius"] * pt["drag_threshold_multiplier"]
        self.MAX_CHARGE     = lc["max_charge"]
        self.CHARGE_RATE    = lc["charge_rate"]
        self.RENDER_MS      = tm["render_ms"]
        self.WALL_MS        = tm["wall_update_ms"]

    # ── 螢幕視窗 ──────────────────────────────────────

    def _setup_screens(self) -> None:
        screens = QApplication.screens()
        print(f"[Pet] 偵測到 {len(screens)} 個螢幕")
        for i, s in enumerate(screens):
            g = s.geometry()
            print(f"  螢幕{i}: {s.name()} ({g.x()},{g.y()}) {g.width()}x{g.height()}")

        self.virt_x = min(s.geometry().x() for s in screens)
        self.virt_y = min(s.geometry().y() for s in screens)
        max_x = max(s.geometry().x() + s.geometry().width() for s in screens)
        max_y = max(s.geometry().y() + s.geometry().height() for s in screens)
        self.screen_w = max_x - self.virt_x
        self.screen_h = max_y - self.virt_y

        # 每個螢幕建一個視窗
        self._windows = [ScreenWindow(s, self) for s in screens]
        print(f"[Pet] 虛擬桌面: ({self.virt_x},{self.virt_y}) {self.screen_w}x{self.screen_h}")

    # ── 物理 ──────────────────────────────────────────

    def _setup_physics(self) -> None:
        self.space = pymunk.Space()
        self.space.gravity = (0, self.GRAVITY)

        moment = pymunk.moment_for_circle(1, 0, self.PET_RADIUS)
        self.body = pymunk.Body(1, moment)
        self.body.position = (-9999, -9999)  # 螢幕外，等第一次點擊

        self.shape = pymunk.Circle(self.body, self.PET_RADIUS)
        self.shape.elasticity = self.ELASTICITY
        self.shape.friction = self.FRICTION
        self.space.add(self.body, self.shape)

        self.wall_mgr = WallManager(self.space)
        self.wall_mgr.add_screen_walls(
            self.virt_x, self.virt_y,
            self.screen_w, self.screen_h
        )

        self.detector = WindowDetector()
        taskbar = self.detector.get_taskbar()
        if taskbar:
            self.wall_mgr.add_taskbar_wall(taskbar)
            print(f"[Pet] 工作欄牆壁: {taskbar}")

    # ── 輸入 ──────────────────────────────────────────

    def _setup_input(self) -> None:
        self._dragging     = False
        self._drag_offset  = (0.0, 0.0)
        self._charging     = False
        self._charge_start = 0.0
        self._charge       = 0.0
        self._initialized  = False
        self._state_lock   = Lock()

        self.input_handler = InputHandler()
        self.input_handler.on_mouse_press   = self._on_mouse_press
        self.input_handler.on_mouse_release = self._on_mouse_release
        self.input_handler.on_mouse_move    = self._on_mouse_move
        self.input_handler.start()

    # ── 計時器 ────────────────────────────────────────

    def _setup_timers(self) -> None:
        self._render_timer = QTimer()
        self._render_timer.timeout.connect(self._update)
        self._render_timer.start(self.RENDER_MS)

        self._wall_timer = QTimer()
        self._wall_timer.timeout.connect(self._update_walls)
        self._wall_timer.start(self.WALL_MS)

    # ── 更新 ──────────────────────────────────────────

    def _update(self) -> None:
        with self._state_lock:
            if self._charging:
                elapsed = time.time() - self._charge_start
                self._charge = min(elapsed * self.CHARGE_RATE, self.MAX_CHARGE)
            if not self._dragging:
                self.space.step(1 / 60)
        for win in self._windows:
            win.update()

    def _update_walls(self) -> None:
        try:
            windows = self.detector.get_windows()
            self.wall_mgr.rebuild_window_walls(windows)
        except Exception as e:
            print(f"[Pet] 牆壁更新失敗: {e}")

    # ── 輸入事件（pynput = 虛擬桌面座標）────────────

    def _on_mouse_press(self, x: int, y: int) -> None:
        with self._state_lock:
            if not self._initialized:
                self._initialized = True
                self.body.position = (x, y)
                self.body.velocity = (0, 0)
                print(f"[Pet] 初始化位置: ({x}, {y})")
                return

            bx, by = self.body.position
            dist = ((x - bx) ** 2 + (y - by) ** 2) ** 0.5

            if dist < self.DRAG_THRESHOLD:
                self._dragging = True
                self._drag_offset = (x - bx, y - by)
                self.body.velocity = (0, 0)
                self.shape.filter = pymunk.ShapeFilter(mask=0)
            else:
                self._charging = True
                self._charge_start = time.time()
                self._charge = self.BASE_CHARGE

    def _on_mouse_release(self, x: int, y: int) -> None:
        with self._state_lock:
            if self._dragging:
                self._dragging = False
                self.shape.filter = pymunk.ShapeFilter()
            elif self._charging:
                self._charging = False
                bx, by = self.body.position
                dx = x - bx
                dy = y - by
                length = (dx ** 2 + dy ** 2) ** 0.5
                if length > 0:
                    self.body.velocity = (
                        dx / length * self._charge,
                        dy / length * self._charge,
                    )
                self._charge = 0.0

    def _on_mouse_move(self, x: int, y: int) -> None:
        with self._state_lock:
            if self._dragging:
                self.body.position = (
                    x - self._drag_offset[0],
                    y - self._drag_offset[1],
                )

    def stop(self) -> None:
        self.input_handler.stop()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    pet = Pet()
    sys.exit(app.exec())
