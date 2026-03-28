import pymunk
from window_detector import Rect
from logger import print_log


class WallManager:
    def __init__(self, space: pymunk.Space):
        self.space = space
        self._dynamic_walls: list[pymunk.Segment] = []

    def add_screen_walls(self, ox: int, oy: int, w: int, h: int) -> None:
        """螢幕四邊牆壁，ox/oy 是虛擬桌面左上角座標"""
        x0, y0 = ox, oy
        x1, y1 = ox + w, oy + h
        edges = [
            [(x0, y1), (x1, y1)],  # 下
            [(x0, y0), (x0, y1)],  # 左
            [(x1, y0), (x1, y1)],  # 右
            [(x0, y0), (x1, y0)],  # 上
        ]
        for a, b in edges:
            seg = pymunk.Segment(self.space.static_body, a, b, 2)
            seg.elasticity = 0.8
            seg.friction = 0.1
            self.space.add(seg)

    def clear_dynamic_walls(self) -> None:
        for seg in self._dynamic_walls:
            self.space.remove(seg)
        self._dynamic_walls.clear()

    def _add_rect_wall(self, rect: Rect, elasticity: float = 0.6) -> None:
        x, y, w, h = rect.x, rect.y, rect.w, rect.h
        edges = [
            [(x,     y),     (x + w, y)    ],
            [(x + w, y),     (x + w, y + h)],
            [(x + w, y + h), (x,     y + h)],
            [(x,     y + h), (x,     y)    ],
        ]
        for a, b in edges:
            seg = pymunk.Segment(self.space.static_body, a, b, 2)
            seg.elasticity = elasticity
            seg.friction = 0.5
            self._dynamic_walls.append(seg)
            self.space.add(seg)

    def add_taskbar_wall(self, rect: Rect) -> None:
        """工作欄牆壁（永久，不會被 rebuild 清除）"""
        x, y, w, h = rect.x, rect.y, rect.w, rect.h
        edges = [
            [(x,     y),     (x + w, y)    ],
            [(x + w, y),     (x + w, y + h)],
            [(x + w, y + h), (x,     y + h)],
            [(x,     y + h), (x,     y)    ],
        ]
        for a, b in edges:
            seg = pymunk.Segment(self.space.static_body, a, b, 2)
            seg.elasticity = 0.8
            seg.friction = 0.1
            self.space.add(seg)

    def rebuild_window_walls(self, rects: list[Rect]) -> None:
        """重建动态墙壁（窗口墙壁），任务栏墙壁保留"""
        self.clear_dynamic_walls()
        if rects:
            print_log(f"[牆壁] 重建 {len(rects)} 個窗口牆")
            for rect in rects:
                print_log(f"  窗口: Rect({rect.x},{rect.y},{rect.w},{rect.h})")
                self._add_rect_wall(rect)
