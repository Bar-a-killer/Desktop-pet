import sys
import time
import platform
import pymunk

from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPainter, QColor, QBrush

import config
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
        self._load_config()
        self._setup_window()
        self._setup_physics()
        self._setup_input()
        self._setup_timers()
        self.show()
        if platform.system() == "Linux":
            self._set_click_through_linux()

    # ── 初始化 ────────────────────────────────────────
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

    def _setup_window(self) -> None:
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # 取得虛擬桌面完整範圍
        virtual = QApplication.primaryScreen().virtualGeometry()
        primary = QApplication.primaryScreen().geometry()

        self.screen_w = virtual.width()
        self.screen_h = virtual.height()

        # 視窗從虛擬桌面左上角開始（可能是負座標）
        self.win_offset_x = virtual.x() - primary.x()
        self.win_offset_y = virtual.y() - primary.y()

        self.setGeometry(
            self.win_offset_x, self.win_offset_y,
            self.screen_w, self.screen_h
        )

        print(f"virtual: {virtual}  primary: {primary}")
        print(f"視窗偏移: ({self.win_offset_x}, {self.win_offset_y})")

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
        self.space.gravity = (0, self.GRAVITY)

        moment = pymunk.moment_for_circle(1, 0, self.PET_RADIUS)
        self.body = pymunk.Body(1, moment)
        #self.body.position = (self.screen_w // 4, 100)
        #self.body.position = (960, 100)  # 左螢幕中間
        self.body.position = (480, 100)
        #self.body.position = (2880, 100)
        self.shape = pymunk.Circle(self.body, self.PET_RADIUS)
        self.shape.elasticity = self.ELASTICITY
        self.shape.friction = self.FRICTION
        self.space.add(self.body, self.shape)

        self.wall_mgr = WallManager(self.space)
        self.wall_mgr.add_screen_walls(self.screen_w, self.screen_h)

        self.detector = WindowDetector()
        taskbar = self.detector.get_taskbar()
        if taskbar:
            self.wall_mgr.add_taskbar_wall(taskbar)
            print(f"[Pet] 工作欄牆壁: {taskbar}")

    def _setup_input(self) -> None:
        # 狀態
        self._dragging     = False
        self._drag_offset  = (0.0, 0.0)
        self._charging     = False
        self._charge_start = 0.0
        self._charge       = 0.0
        self._mouse_pos    = (0, 0)
        primary_geo = QApplication.primaryScreen().geometry()
        self._screen_offset_x = 0
        self._screen_offset_y = 0
        print(f"座標偏移: ({self._screen_offset_x}, {self._screen_offset_y})")
        

        self.input_handler = InputHandler()
        self.input_handler.on_mouse_press   = self._on_mouse_press
        self.input_handler.on_mouse_release = self._on_mouse_release
        self.input_handler.on_mouse_move    = self._on_mouse_move
        self.input_handler.start()

    def _setup_timers(self) -> None:
        self._render_timer = QTimer()
        self._render_timer.timeout.connect(self._update)
        self._render_timer.start(self.RENDER_MS)

        self._wall_timer = QTimer()
        self._wall_timer.timeout.connect(self._update_walls)
        self._wall_timer.start(self.WALL_MS)

    # ── 更新 ──────────────────────────────────────────

    def _update(self) -> None:
        if self._charging:
            elapsed = time.time() - self._charge_start
            self._charge = min(elapsed * self.CHARGE_RATE, self.MAX_CHARGE)

        if not self._dragging:
            self.space.step(1 / 60)

        self.update()  # 觸發 paintEvent

    def _update_walls(self) -> None:
        windows = self.detector.get_windows()
        self.wall_mgr.rebuild_window_walls(windows)
    # ── 座標轉換 ──────────────────────────────────────
 
    def _to_physics(self, x: int, y: int) -> tuple[float, float]:
        return (
            x - self._screen_offset_x,
            y - self._screen_offset_y,
        )
    # ── 輸入事件 ──────────────────────────────────────

    def _on_mouse_press(self, x: int, y: int) -> None:
        px, py = self._to_physics(x, y)
        bx, by = self.body.position
        dist = ((px - bx) ** 2 + (py - by) ** 2) ** 0.5
        print(f"按下 pynput:({x},{y}) 物理:({px:.0f},{py:.0f}) 球:({bx:.0f},{by:.0f}) 距離:{dist:.0f} 閾值:{self.DRAG_THRESHOLD}")
        if dist < self.DRAG_THRESHOLD:
            self._dragging = True
            self._drag_offset = (px - bx, py - by)
            self.body.velocity = (0, 0)
            self.shape.filter = pymunk.ShapeFilter(mask=0)  # 穿透牆壁
        else:
            self._charging = True
            self._charge_start = time.time()
            self._charge = self.BASE_CHARGE

    def _on_mouse_release(self, x: int, y: int) -> None:
        bx, by = self.body.position
        px, py = self._to_physics(x, y)
        print(f"滑鼠原始: ({x}, {y})  物理座標: ({px:.0f}, {py:.0f})  球: ({bx:.0f}, {by:.0f})")

        if self._dragging:
            self._dragging = False
            self.shape.filter = pymunk.ShapeFilter()  # 恢復碰撞

        elif self._charging:
            self._charging = False
            bx, by = self.body.position
            dx = px - bx
            dy = py - by
            length = (dx ** 2 + dy ** 2) ** 0.5
            print(f"方向: ({dx:.0f}, {dy:.0f})  長度: {length:.0f}  力道: {self._charge:.0f}")
        
            if length > 0:
                self.body.velocity = (
                    dx / length * self._charge,
                    dy / length * self._charge,
                )
            self._charge = 0.0

    def _on_mouse_move(self, x: int, y: int) -> None:
        px, py = self._to_physics(x, y)
        self._mouse_pos = (x, y)
        if self._dragging:
            self.body.position = (
                px - self._drag_offset[0],
                py - self._drag_offset[1],
            )

    # ── 繪製 ──────────────────────────────────────────

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        x, y = self.body.position
        # 修正繪製座標（物理座標 → 視窗座標）
        draw_x = x
        draw_y = y

        t = self._charge / self.MAX_CHARGE
        r = int(100 + 155 * t)
        g = int(200 - 200 * t)
        b = int(255 - 255 * t)

        painter.setBrush(QBrush(QColor(r, g, b, 220)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(
            int(draw_x - self.PET_RADIUS), int(draw_y - self.PET_RADIUS),
            self.PET_RADIUS * 2, self.PET_RADIUS * 2,
        )

    # ── 結束 ──────────────────────────────────────────

    def closeEvent(self, event) -> None:
        self.input_handler.stop()
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    pet = Pet()
    sys.exit(app.exec())
