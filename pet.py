import sys
import time
import platform
import pymunk

from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPainter, QColor, QBrush

from physics import WallManager
from window_detector import WindowDetector
from input_handler import InputHandler

# ── 常數 ──────────────────────────────────────────────
GRAVITY          = 500
ELASTICITY       = 0.95
FRICTION         = 0.1
PET_RADIUS       = 20
DRAG_THRESHOLD   = PET_RADIUS * 3   # 拖曳觸發範圍（px）
MAX_CHARGE       = 1200             # 最大發射速度
CHARGE_RATE      = 800              # 每秒蓄力速度
WALL_UPDATE_MS   = 2000             # 視窗牆壁更新間隔


class Pet(QWidget):
    def __init__(self):
        super().__init__()
        self._setup_window()
        self._setup_physics()
        self._setup_input()
        self._setup_timers()
        self.show()
        # show 之後才設定 click-through
        if platform.system() == "Linux":
            self._set_click_through_linux()

    # ── 初始化 ────────────────────────────────────────

    def _setup_window(self) -> None:
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        screen = QApplication.primaryScreen().virtualGeometry()
        self.screen_w = screen.width()
        self.screen_h = screen.height()
        self.setGeometry(0, 0, self.screen_w, self.screen_h)


    def _set_click_through_linux(self) -> None:
        try:
            import subprocess
            from Xlib import display, X
            from Xlib.ext import shape

            wid = int(self.winId())

            # 置頂 + notification 類型
            subprocess.run(["xprop", "-id", str(wid),
                "-f", "_NET_WM_WINDOW_TYPE", "32a",
                "-set", "_NET_WM_WINDOW_TYPE", "_NET_WM_WINDOW_TYPE_NOTIFICATION"])
            subprocess.run(["xprop", "-id", str(wid),
                "-f", "_NET_WM_STATE", "32a",
                "-set", "_NET_WM_STATE", "_NET_WM_STATE_ABOVE"])

            # click-through：Input shape 設成空矩形
            d = display.Display()
            win = d.create_resource_object("window", wid)
            shape.rectangles(
                win,           # self
                shape.SO.Set,  # operation
                shape.SK.Input, # destination_kind
                X.Unsorted,    # ordering
                0, 0,          # x_offset, y_offset
                []             # rectangles
            )
            d.flush()
            print("[Pet] click-through + 置頂 設定成功")
        except Exception as e:
            print(f"[Pet] 設定失敗: {e}")

    def _setup_physics(self) -> None:
        self.space = pymunk.Space()
        self.space.gravity = (0, GRAVITY)

        moment = pymunk.moment_for_circle(1, 0, PET_RADIUS)
        self.body = pymunk.Body(1, moment)
        self.body.position = (self.screen_w // 2, 100)

        self.shape = pymunk.Circle(self.body, PET_RADIUS)
        self.shape.elasticity = ELASTICITY
        self.shape.friction = FRICTION
        self.space.add(self.body, self.shape)

        self.wall_mgr = WallManager(self.space)
        self.wall_mgr.add_screen_walls(self.screen_w, self.screen_h)

        self.detector = WindowDetector()

    def _setup_input(self) -> None:
        # 狀態
        self._dragging     = False
        self._drag_offset  = (0.0, 0.0)
        self._charging     = False
        self._charge_start = 0.0
        self._charge       = 0.0
        self._mouse_pos    = (0, 0)

        self.input_handler = InputHandler()
        self.input_handler.on_mouse_press   = self._on_mouse_press
        self.input_handler.on_mouse_release = self._on_mouse_release
        self.input_handler.on_mouse_move    = self._on_mouse_move
        self.input_handler.start()

    def _setup_timers(self) -> None:
        self._render_timer = QTimer()
        self._render_timer.timeout.connect(self._update)
        self._render_timer.start(16)  # ~60 fps

        self._wall_timer = QTimer()
        self._wall_timer.timeout.connect(self._update_walls)
        self._wall_timer.start(WALL_UPDATE_MS)

    # ── 更新 ──────────────────────────────────────────

    def _update(self) -> None:
        if self._charging:
            elapsed = time.time() - self._charge_start
            self._charge = min(elapsed * CHARGE_RATE, MAX_CHARGE)

        if not self._dragging:
            self.space.step(1 / 60)

        self.update()  # 觸發 paintEvent

    def _update_walls(self) -> None:
        windows = self.detector.get_windows()
        self.wall_mgr.rebuild_window_walls(windows)

    # ── 輸入事件 ──────────────────────────────────────

    def _on_mouse_press(self, x: int, y: int) -> None:
        bx, by = self.body.position
        dist = ((x - bx) ** 2 + (y - by) ** 2) ** 0.5

        if dist < DRAG_THRESHOLD:
            # 靠近寵物 → 拖曳
            self._dragging = True
            self._drag_offset = (x - bx, y - by)
            self.body.velocity = (0, 0)
            self.shape.filter = pymunk.ShapeFilter(mask=0)  # 穿透牆壁
        else:
            # 遠離寵物 → 蓄力
            self._charging = True
            self._charge_start = time.time()
            self._charge = 0.0

    def _on_mouse_release(self, x: int, y: int) -> None:
        if self._dragging:
            self._dragging = False
            self.shape.filter = pymunk.ShapeFilter()  # 恢復碰撞

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
        self._mouse_pos = (x, y)
        if self._dragging:
            self.body.position = (
                x - self._drag_offset[0],
                y - self._drag_offset[1],
            )

    # ── 繪製 ──────────────────────────────────────────

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        x, y = self.body.position
        t = self._charge / MAX_CHARGE  # 0.0 ~ 1.0

        # 藍(蓄力0) → 紅(蓄力滿)
        r = int(100 + 155 * t)
        g = int(200 - 200 * t)
        b = int(255 - 255 * t)

        painter.setBrush(QBrush(QColor(r, g, b, 220)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(
            int(x - PET_RADIUS), int(y - PET_RADIUS),
            PET_RADIUS * 2, PET_RADIUS * 2,
        )

    # ── 結束 ──────────────────────────────────────────

    def closeEvent(self, event) -> None:
        self.input_handler.stop()
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    pet = Pet()
    sys.exit(app.exec())
