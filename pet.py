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
from logger import print_log


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

    # ── 初始化 ────────────────────────────────────────

    def _setup_window(self) -> None:
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # 虛擬桌面完整範圍（所有螢幕的聯集）
        # 不能信任 virtualGeometry()，需要手動計算所有螢幕的邊界
        screens = QApplication.screens()
        if not screens:
            raise RuntimeError("No screens found!")
        
        print_log(f"[窗口] 檢測到 {len(screens)} 個屏幕")
        for i, s in enumerate(screens):
            geom = s.geometry()
            print_log(f"  屏幕{i}: x={geom.x()} y={geom.y()} w={geom.width()} h={geom.height()}")
        
        # 手動設定虛擬桌面範圍以匹配 Qt 座標系
        self.virt_x = 0
        self.virt_y = 0
        self.screen_w = 3840
        self.screen_h = 1080

        self.resize(self.screen_w, self.screen_h)
        self.move(self.virt_x, self.virt_y)

        # 計算窗口全局座標偏移（pynput使用全局座標，需要轉換為虛擬座標）
        # pynput返回全局座標，虛擬座標 = 全局座標 - window_global_offset
        # 初始假設為匹配 Qt 座標
        self.window_global_x = 0
        self.window_global_y = 0

        print_log(f"虛擬桌面: 左上({self.virt_x},{self.virt_y}) 大小{self.screen_w}x{self.screen_h} 右下({self.virt_x + self.screen_w},{self.virt_y + self.screen_h})")
        print_log(f"窗口全局偏移初始值: ({self.window_global_x}, {self.window_global_y})")

    def _set_click_through_linux(self) -> None:
        try:
            import subprocess
            from Xlib import display, X
            from Xlib.ext import shape

            wid = int(self.winId())
            # subprocess.run(["xprop", "-id", str(wid),
            #     "-f", "_NET_WM_WINDOW_TYPE", "32a",
            #     "-set", "_NET_WM_WINDOW_TYPE", "_NET_WM_WINDOW_TYPE_NOTIFICATION"],
            #     capture_output=True)
            subprocess.run(["xprop", "-id", str(wid),
                "-f", "_NET_WM_STATE", "32a",
                "-set", "_NET_WM_STATE", "_NET_WM_STATE_ABOVE"],
                capture_output=True)

            d = display.Display()
            win = d.create_resource_object("window", wid)
            shape.rectangles(
                win, shape.SO.Set, shape.SK.Input,
                X.Unsorted, 0, 0, []
            )
            d.flush()
            print_log("[Pet] click-through + 置頂 設定成功")
        except Exception as e:
            print_log(f"[Pet] 設定失敗: {e}")

    def _setup_physics(self) -> None:
        self.space = pymunk.Space()
        self.space.gravity = (0, self.GRAVITY)

        moment = pymunk.moment_for_circle(1, 0, self.PET_RADIUS)
        self.body = pymunk.Body(1, moment)
        # 初始位置：屏幕中央
        init_x = self.virt_x + self.screen_w // 2
        init_y = self.virt_y + 100
        self.body.position = (init_x, init_y)

        self.shape = pymunk.Circle(self.body, self.PET_RADIUS)
        self.shape.elasticity = self.ELASTICITY
        self.shape.friction = self.FRICTION
        self.space.add(self.body, self.shape)

        # 牆壁用虛擬座標
        self.wall_mgr = WallManager(self.space)
        self.wall_mgr.add_screen_walls(
            self.virt_x, self.virt_y,
            self.screen_w, self.screen_h
        )
        print_log(f"[物理] 屏幕牆設置: ({self.virt_x},{self.virt_y}) {self.screen_w}x{self.screen_h}")

        self.detector = WindowDetector()
        taskbar = self.detector.get_taskbar()
        if taskbar:
            self.wall_mgr.add_taskbar_wall(taskbar)
            print_log(f"[Pet] 工作欄牆壁: {taskbar}")

    def _setup_input(self) -> None:
        self._dragging     = False
        self._drag_offset  = (0.0, 0.0)
        self._charging     = False
        self._charge_start = 0.0
        self._charge       = 0.0
        self._mouse_pos    = (0, 0)
        self._state_lock   = Lock()  # 保护线程安全
        
        # 第一次鼠標事件時校準座標
        self._calibrated = False

        self.input_handler = InputHandler()
        self.input_handler.on_mouse_press   = self._on_mouse_press
        self.input_handler.on_mouse_release = self._on_mouse_release
        self.input_handler.on_mouse_move    = self._on_mouse_move
        self.input_handler.start()

    def _setup_timers(self) -> None:
        self._update_start_time = time.time()  # 统一计时源
        
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

        self.update()

    def _update_walls(self) -> None:
        try:
            windows = self.detector.get_windows()
            self.wall_mgr.rebuild_window_walls(windows)
        except Exception as e:
            print_log(f"[Pet] 牆壁更新失敗，跳過此次更新: {e}")
            # 不重新建牆壁，保持現有牆壁

    # ── 輸入事件（pynput回報全局座標，需轉換為虛擬座標）────

    def _convert_mouse_coords(self, x: int, y: int) -> tuple[int, int]:
        """
        將pynput全局座標轉換為虛擬座標
        pynput使用X11坐標系 (-1920, 1920)
        Qt使用 (0, 3840)
        需要先轉換為Qt坐標，再減去窗口偏移
        """
        # 將pynput X11坐標轉換為Qt坐標
        qt_x = x + 1920  # X11 left monitor starts at -1920
        qt_y = y
        
        # 虛擬座標 = Qt座標 - 窗口全局偏移
        vx = qt_x - self.window_global_x
        vy = qt_y - self.window_global_y
        
        return (vx, vy)

    def _on_mouse_press(self, x: int, y: int) -> None:
        with self._state_lock:
            # 第一次點擊時校準座標（根據球的已知位置和鼠標點擊推算偏移）
            if not self._calibrated:
                bx, by = self.body.position
                # pynput給的是X11坐標 (-1920到1920)
                # 轉換為Qt坐標後，計算window_global_x偏移
                # window_global_x = qt_x - vx = (x + 1920) - (bx)  
                self.window_global_x = (x + 1920) - int(bx)
                self.window_global_y = y - int(by)
                self._calibrated = True
                print_log(f"[校準] 窗口全局偏移: ({self.window_global_x}, {self.window_global_y}) (pynput x={x})")
            
            # 轉換座標
            vx, vy = self._convert_mouse_coords(x, y)
            bx, by = self.body.position
            dist = ((vx - bx) ** 2 + (vy - by) ** 2) ** 0.5
            print_log(f"按下 pynput({x},{y}) -> Qt({x+1920},{y}) -> 虛擬({vx},{vy}) 球:({bx:.0f},{by:.0f}) 距離:{dist:.0f}")

            if dist < self.DRAG_THRESHOLD:
                self._dragging = True
                self._drag_offset = (vx - bx, vy - by)
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
                # 轉換座標
                vx, vy = self._convert_mouse_coords(x, y)
                bx, by = self.body.position
                dx = vx - bx
                dy = vy - by
                length = (dx ** 2 + dy ** 2) ** 0.5
                if length > 0:
                    self.body.velocity = (
                        dx / length * self._charge,
                        dy / length * self._charge,
                    )
                self._charge = 0.0

    def _on_mouse_move(self, x: int, y: int) -> None:
        with self._state_lock:
            self._mouse_pos = (x, y)
            if self._dragging:
                # 转换座标
                vx, vy = self._convert_mouse_coords(x, y)
                
                # 计算新位置
                new_x = vx - self._drag_offset[0]
                new_y = vy - self._drag_offset[1]
                
                # 移除边界限制，让物理引擎的墙壁来约束
                self.body.position = (new_x, new_y)
                
                # 诊断：如果拖到左屏幕，打印座标
                if new_x < 100:  # 接近左屏幕
                    print_log(f"[拖動] 拖到左屏: 全局({x},{y}) -> 虛擬({vx},{vy}) -> 物理({new_x:.1f},{new_y:.1f})")
                print_log(f"[拖動] 位置更新: 物理({new_x:.1f},{new_y:.1f})")

    # ── 繪製（物理座標 → 視窗內部座標）──────────────

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        x, y = self.body.position

        draw_x = x - self.virt_x
        draw_y = y - self.virt_y

        print_log(f"[繪製] 球位置: 物理({x:.1f},{y:.1f}) 繪製({draw_x:.1f},{draw_y:.1f}) 窗口大小{self.screen_w}x{self.screen_h}")

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
