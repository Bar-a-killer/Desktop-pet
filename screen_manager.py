import pymunk
from threading import Lock
from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPainter, QColor, QBrush
import time
import platform

from physics import WallManager
from window_detector import WindowDetector
from input_handler import InputHandler
from logger import print_log
import config


class ScreenManager:
    """管理多個螢幕窗口和共享物理引擎"""
    
    def __init__(self):
        self.app = QApplication.instance()
        self.space = pymunk.Space()
        self.space.gravity = (0, config.physics()["gravity"])
        
        self.wall_mgr = WallManager(self.space)
        self.detector = WindowDetector()
        self.input_handler = InputHandler()
        
        self._state_lock = Lock()
        self._charge = 0.0
        self._charge_start = 0.0
        self._charging = False
        
        # 物理座標系統（共享）
        self.body = None
        self.shape = None
        self._setup_physics()
        
        # 建立向量與拖曳狀態
        self._drag_offset = (0.0, 0.0)
        self._dragging = False
        self._mouse_pos = (0, 0)
        self._calibrated = False
        self.window_global_x = 1920
        self.window_global_y = 0
        
        # 螢幕窗口管理
        self.screens_info = self._detect_screens()
        self.windows = []
        self._create_screen_windows()
        
        # 設定牆壁（只在螢幕邊界，不在螢幕之間）
        self._setup_walls()
        
        # 全局輸入監聽
        self.input_handler.on_mouse_press = self._on_mouse_press
        self.input_handler.on_mouse_release = self._on_mouse_release
        self.input_handler.on_mouse_move = self._on_mouse_move
        self.input_handler.start()
        
        # 計時器
        self._setup_timers()
    
    def _detect_screens(self):
        """檢測所有螢幕"""
        screens = self.app.screens()
        info = []
        for i, s in enumerate(screens):
            geom = s.geometry()
            info.append({
                'index': i,
                'x': geom.x(),
                'y': geom.y(),
                'width': geom.width(),
                'height': geom.height(),
            })
            print_log(f"[螢幕{i}] x={geom.x()} y={geom.y()} w={geom.width()} h={geom.height()}")
        return info
    
    def _setup_physics(self):
        """初始化物理引擎"""
        pt = config.pet()
        moment = pymunk.moment_for_circle(1, 0, pt["radius"])
        self.body = pymunk.Body(1, moment)
        # 初始位置：左螢幕中央
        self.body.position = (-960, 400)
        self.shape = pymunk.Circle(self.body, pt["radius"])
        self.shape.elasticity = config.physics()["elasticity"]
        self.shape.friction = config.physics()["friction"]
        self.space.add(self.body, self.shape)
    
    def _create_screen_windows(self):
        """為每個螢幕建立一個窗口"""
        for info in self.screens_info:
            window = ScreenWindow(self, info)
            self.windows.append(window)
            window.show()
    
    def _setup_walls(self):
        """設定牆壁：只在螢幕上下邊界，左右邊界不設（允許穿透）"""
        # 底部牆壁（工作欄）
        try:
            taskbar = self.detector.get_taskbar()
            self.wall_mgr.add_taskbar_wall(taskbar)
            print_log(f"[牆壁] 工作欄牆: {taskbar}")
        except Exception as e:
            print_log(f"[牆壁] 獲取工作欄失敗: {e}")
        
        # 上下邊界牆壁（所有螢幕）
        min_y = min(s['y'] for s in self.screens_info)
        max_y = max(s['y'] + s['height'] for s in self.screens_info)
        min_x = min(s['x'] for s in self.screens_info)
        max_x = max(s['x'] + s['width'] for s in self.screens_info)
        
        # 上邊界
        seg_top = pymunk.Segment(self.space.static_body, (min_x, min_y), (max_x, min_y), 2)
        seg_top.elasticity = 0.8
        seg_top.friction = 0.1
        self.space.add(seg_top)
        
        # 下邊界（上面已有工作欄，這裡只加邊界）
        seg_bottom = pymunk.Segment(self.space.static_body, (min_x, max_y), (max_x, max_y), 2)
        seg_bottom.elasticity = 0.8
        seg_bottom.friction = 0.1
        self.space.add(seg_bottom)
        
        # 左邊界
        seg_left = pymunk.Segment(self.space.static_body, (min_x - 50, min_y), (min_x - 50, max_y), 2)
        seg_left.elasticity = 0.8
        seg_left.friction = 0.1
        self.space.add(seg_left)
        
        # 右邊界
        seg_right = pymunk.Segment(self.space.static_body, (max_x + 50, min_y), (max_x + 50, max_y), 2)
        seg_right.elasticity = 0.8
        seg_right.friction = 0.1
        self.space.add(seg_right)
        
        # 動態窗口牆壁
        try:
            windows = self.detector.get_windows()
            self.wall_mgr.rebuild_window_walls(windows)
        except Exception as e:
            print_log(f"[牆壁] 重建失敗: {e}")
    
    def _setup_timers(self):
        """設定全局計時器"""
        self._update_start_time = time.time()
        
        # 物理更新
        self._physics_timer = QTimer()
        self._physics_timer.timeout.connect(self._update_physics)
        self._physics_timer.start(config.timers()["render_ms"])
        
        # 牆壁更新
        self._wall_timer = QTimer()
        self._wall_timer.timeout.connect(self._update_walls)
        self._wall_timer.start(config.timers()["wall_update_ms"])
    
    def _update_physics(self):
        """更新物理引擎"""
        with self._state_lock:
            if self._charging:
                elapsed = time.time() - self._charge_start
                max_charge = config.launch()["max_charge"]
                self._charge = min(elapsed * config.launch()["charge_rate"], max_charge)
            
            if not self._dragging:
                self.space.step(1 / 60)
        
        # 通知所有窗口重新繪製
        for window in self.windows:
            window.update()
    
    def _update_walls(self):
        """更新動態窗口牆壁"""
        try:
            windows = self.detector.get_windows()
            self.wall_mgr.rebuild_window_walls(windows)
        except Exception as e:
            print_log(f"[牆壁] 更新失敗: {e}")
    
    def _convert_mouse_coords(self, x: int, y: int) -> tuple[int, int]:
        """將 pynput 座標轉換為物理座標"""
        vx = x - self.window_global_x
        vy = y - self.window_global_y
        return (vx, vy)
    
    def _on_mouse_press(self, x: int, y: int) -> None:
        """全局滑鼠按下"""
        with self._state_lock:
            if not self._calibrated:
                bx, by = self.body.position
                self.window_global_x = x - int(bx)
                self.window_global_y = y - int(by)
                self._calibrated = True
                print_log(f"[校準] 窗口偏移: ({self.window_global_x}, {self.window_global_y})")
            
            vx, vy = self._convert_mouse_coords(x, y)
            bx, by = self.body.position
            dist = ((vx - bx) ** 2 + (vy - by) ** 2) ** 0.5
            drag_threshold = config.pet()["radius"] * config.pet()["drag_threshold_multiplier"]
            
            print_log(f"按下 pynput({x},{y}) -> 物理({vx:.0f},{vy:.0f}) 球({bx:.0f},{by:.0f}) 距離{dist:.0f}")
            
            if dist < drag_threshold:
                self._dragging = True
                self._drag_offset = (vx - bx, vy - by)
                self.body.velocity = (0, 0)
                self.shape.filter = pymunk.ShapeFilter(mask=0)
            else:
                self._charging = True
                self._charge_start = time.time()
                self._charge = config.launch()["base_charge"]
    
    def _on_mouse_release(self, x: int, y: int) -> None:
        """全局滑鼠釋放"""
        with self._state_lock:
            if self._dragging:
                self._dragging = False
                self.shape.filter = pymunk.ShapeFilter()
            elif self._charging:
                self._charging = False
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
                print_log(f"發射: 速度({self.body.velocity[0]:.0f},{self.body.velocity[1]:.0f})")
                self._charge = 0.0
    
    def _on_mouse_move(self, x: int, y: int) -> None:
        """全局滑鼠移動"""
        with self._state_lock:
            self._mouse_pos = (x, y)
            if self._dragging:
                vx, vy = self._convert_mouse_coords(x, y)
                new_x = vx - self._drag_offset[0]
                new_y = vy - self._drag_offset[1]
                self.body.position = (new_x, new_y)
                print_log(f"[拖動] 位置({new_x:.1f},{new_y:.1f})")
    
    def cleanup(self):
        """清理資源"""
        self.input_handler.stop()
        for window in self.windows:
            window.close()


class ScreenWindow(QWidget):
    """單個螢幕窗口"""
    
    def __init__(self, manager: ScreenManager, screen_info: dict):
        super().__init__()
        self.manager = manager
        self.screen_info = screen_info
        
        # 設定視窗
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        # 位置和大小
        self.setGeometry(
            screen_info['x'], screen_info['y'],
            screen_info['width'], screen_info['height']
        )
        print_log(f"[窗口] 螢幕{screen_info['index']}: ({screen_info['x']}, {screen_info['y']}) {screen_info['width']}x{screen_info['height']}")
        
        # 啟用點擊穿透
        if platform.system() == "Linux":
            self._set_click_through()
    
    def _set_click_through(self) -> None:
        """啟用點擊穿透(Linux X11)"""
        try:
            import subprocess
            from Xlib import display, X
            from Xlib.ext import shape
            
            wid = int(self.winId())
            # 設置窗口為置頂
            subprocess.run(["xprop", "-id", str(wid),
                "-f", "_NET_WM_STATE", "32a",
                "-set", "_NET_WM_STATE", "_NET_WM_STATE_ABOVE"],
                capture_output=True)
            
            # 設置輸入穿透（點擊穿透）
            d = display.Display()
            win = d.create_resource_object("window", wid)
            shape.rectangles(
                win, shape.SO.Set, shape.SK.Input,
                X.Unsorted, 0, 0, []
            )
            d.flush()
            print_log(f"[點擊穿透] 螢幕{self.screen_info['index']} 設定成功")
        except Exception as e:
            print_log(f"[點擊穿透] 螢幕{self.screen_info['index']} 設定失敗: {e}")

        def paintEvent(self, event) -> None:
            """繪製球"""
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            
            x, y = self.manager.body.position
            screen_left = self.screen_info['x']
            screen_right = self.screen_info['x'] + self.screen_info['width']
            
            # 檢查球是否在此螢幕範圍內（含邊界）
            if x < screen_left - 50 or x > screen_right + 50:
                return
            
            # 轉換為窗口本地座標
            draw_x = x - self.screen_info['x']
            draw_y = y - self.screen_info['y']
            
            # 繪製球
            radius = config.pet()["radius"]
            max_charge = config.launch()["max_charge"]
            t = self.manager._charge / max_charge
            r = int(100 + 155 * t)
            g = int(200 - 200 * t)
            b = int(255 - 255 * t)
            
            painter.setBrush(QBrush(QColor(r, g, b, 220)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(
                int(draw_x - radius), int(draw_y - radius),
                radius * 2, radius * 2,
            )
    
    def closeEvent(self, event) -> None:
        self.manager.cleanup()
        super().closeEvent(event)
