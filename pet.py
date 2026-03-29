import sys
import time
import platform
import pymunk
from threading import Lock

from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPainter, QColor, QBrush, QPen
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

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 調試：繪製螢幕邊框
        painter.setPen(QPen(QColor(255, 0, 0, 255), 2))  # 紅色實線
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(0, 0, self.sw - 1, self.sh - 1)

        # 調試：顯示座標信息
        painter.setPen(QPen(QColor(0, 255, 0, 255), 1))
        painter.drawText(10, 20, f"Screen: ({self.sx},{self.sy}) {self.sw}x{self.sh}")
        painter.drawText(10, 40, f"Ball: ({x:.0f},{y:.0f}) -> ({draw_x:.0f},{draw_y:.0f})")

        # 繪製牆壁
        self._draw_walls(painter)

        # 繪製球
        t = self._pet._charge / self._pet.MAX_CHARGE
        r = int(100 + 155 * t)
        g = int(200 - 200 * t)
        b = int(255 - 255 * t)

        painter.setBrush(QBrush(QColor(r, g, b, 220)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(
            int(draw_x - self._pet.PET_RADIUS),
            int(draw_y - self._pet.PET_RADIUS),
            self._pet.PET_RADIUS * 2,
            self._pet.PET_RADIUS * 2,
        )

    def _draw_walls(self, painter: QPainter) -> None:
        """繪製所有牆壁"""
        walls = self._pet.wall_mgr.get_all_walls()

        # 設置牆壁顏色和樣式 - 屏幕邊界用紅色，窗口牆用藍色
        screen_walls = self._pet.wall_mgr._screen_walls
        dynamic_walls = self._pet.wall_mgr._dynamic_walls

        # 繪製屏幕邊界牆（紅色實線）
        painter.setPen(QPen(QColor(255, 0, 0, 255), 2))  # 紅色實線
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for wall in screen_walls:
            self._draw_wall_segment(painter, wall)

        # 繪製動態窗口牆（藍色虛線）
        painter.setPen(QPen(QColor(0, 0, 255, 255), 1, Qt.PenStyle.DashLine))  # 藍色虛線
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for wall in dynamic_walls:
            self._draw_wall_segment(painter, wall)

    def _draw_wall_segment(self, painter: QPainter, wall: pymunk.Segment) -> None:
        """繪製單個牆壁段"""
        # 獲取牆壁段的兩個端點
        a = wall.a
        b = wall.b

        # 檢查牆壁是否主要屬於這個螢幕 (避免在多個螢幕上重複繪製)
        wall_min_x = min(a[0], b[0])
        wall_max_x = max(a[0], b[0])
        wall_min_y = min(a[1], b[1])
        wall_max_y = max(a[1], b[1])
        
        # 只繪製牆壁段的 x 和 y 範圍與螢幕相交的牆壁
        if not (wall_max_x >= self.sx and wall_min_x <= self.sx + self.sw and
                wall_max_y >= self.sy and wall_min_y <= self.sy + self.sh):
            return

        # 轉換為屏幕座標
        screen_a_x = a[0] - self.sx
        screen_a_y = a[1] - self.sy
        screen_b_x = b[0] - self.sx
        screen_b_y = b[1] - self.sy

        # 只繪製在屏幕範圍內的牆壁 (擴大範圍以顯示跨越邊界的牆壁)
        if (min(screen_a_x, screen_b_x) <= self.sw + 500 and
            max(screen_a_x, screen_b_x) >= -500 and
            min(screen_a_y, screen_b_y) <= self.sh + 500 and
            max(screen_a_y, screen_b_y) >= -500):
            painter.drawLine(
                int(screen_a_x), int(screen_a_y),
                int(screen_b_x), int(screen_b_y)
            )


class Pet:
    """主控制器，管理物理、輸入、計時器"""

    def __init__(self):
        self._load_config()
        self._screens = QApplication.screens()  # 保存螢幕列表
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
        self.DRAG_MOMENTUM_MULTIPLIER = pt.get("drag_momentum_multiplier", 1.0)
        self.MAX_CHARGE     = lc["max_charge"]
        self.CHARGE_RATE    = lc["charge_rate"]
        self.RENDER_MS      = tm["render_ms"]
        self.PHYSICS_FPS    = tm.get("physics_fps", 60)
        self.PHYSICS_STEP   = 1 / self.PHYSICS_FPS
        self.WALL_MS        = tm["wall_update_ms"]

    # ── 螢幕視窗 ──────────────────────────────────────

    def _setup_screens(self) -> None:
        screens = self._screens
        print(f"[Pet] 偵測到 {len(screens)} 個螢幕")
        for i, s in enumerate(screens):
            g = s.geometry()
            ag = s.availableGeometry()
            print(f"  螢幕{i}: {s.name()}")
            print(f"    幾何: ({g.x()},{g.y()}) {g.width()}x{g.height()}")
            print(f"    可用幾何: ({ag.x()},{ag.y()}) {ag.width()}x{ag.height()}")

        self.virt_x = min(s.geometry().x() for s in screens)
        self.virt_y = min(s.geometry().y() for s in screens)
        max_x = max(s.geometry().x() + s.geometry().width() for s in screens)
        max_y = max(s.geometry().y() + s.geometry().height() for s in screens)
        self.screen_w = max_x - self.virt_x
        self.screen_h = max_y - self.virt_y

        # 每個螢幕建一個視窗
        self._windows = [ScreenWindow(s, self) for s in screens]
        print(f"[Pet] 虛擬桌面: ({self.virt_x},{self.virt_y}) {self.screen_w}x{self.screen_h}")
        print(f"[Pet] 物理世界邊界: ({self.virt_x},{self.virt_y - 100}) - ({self.virt_x + self.screen_w},{self.virt_y + self.screen_h})")

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
        # 清除舊的螢幕邊界
        self.wall_mgr.clear_screen_walls()
        # 為每個螢幕設置邊界牆壁 (精確的螢幕邊緣)
        for screen in self._screens:
            g = screen.geometry()
            # 螢幕的精確邊界
            self.wall_mgr.add_screen_walls(
                g.x(), g.y(),
                g.width(), g.height()
            )
            print(f"[Pet] 螢幕邊界: ({g.x()},{g.y()}) {g.width()}x{g.height()}")

        self.detector = WindowDetector()
        taskbar = self.detector.get_taskbar()
        if taskbar:
            self.wall_mgr.add_taskbar_wall(taskbar)
            print(f"[Pet] 工作欄牆壁: {taskbar}")

    # ── 輸入 ──────────────────────────────────────────

    def _setup_input(self) -> None:
        self._dragging     = False
        self._drag_offset  = (0.0, 0.0)
        self._drag_velocity = (0.0, 0.0)  # 拖動速度
        self._last_drag_pos = (0.0, 0.0)  # 上次拖動位置
        self._last_drag_time = 0.0        # 上次拖動時間
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
                self.space.step(self.PHYSICS_STEP)
        for win in self._windows:
            win.update()

    def _update_walls(self) -> None:
        try:
            windows = self.detector.get_windows()
            self.wall_mgr.rebuild_window_walls(windows)
            # 調試信息：檢查窗口座標
            if windows:
                print(f"[Pet] 檢測到 {len(windows)} 個窗口:")
                for i, w in enumerate(windows[:3]):  # 只顯示前3個
                    print(f"  窗口{i}: ({w.x},{w.y}) {w.w}x{w.h}")
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
                self._drag_velocity = (0.0, 0.0)  # 重置拖動速度
                self._last_drag_pos = (bx, by)
                self._last_drag_time = time.time()
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
                # 使用計算出的拖動速度，乘以調整乘數
                vx = self._drag_velocity[0] * self.DRAG_MOMENTUM_MULTIPLIER
                vy = self._drag_velocity[1] * self.DRAG_MOMENTUM_MULTIPLIER
                self.body.velocity = (vx, vy)
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
                current_time = time.time()
                new_pos = (
                    x - self._drag_offset[0],
                    y - self._drag_offset[1],
                )
                self.body.position = new_pos
                
                # 計算拖動速度 (像素/秒)
                if self._last_drag_time > 0:
                    dt = current_time - self._last_drag_time
                    if dt > 0:
                        vx = (new_pos[0] - self._last_drag_pos[0]) / dt
                        vy = (new_pos[1] - self._last_drag_pos[1]) / dt
                        self._drag_velocity = (vx, vy)
                
                self._last_drag_pos = new_pos
                self._last_drag_time = current_time

    def stop(self) -> None:
        self.input_handler.stop()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    pet = Pet()
    sys.exit(app.exec())
