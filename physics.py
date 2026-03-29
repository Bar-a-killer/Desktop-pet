import pymunk
from window_detector import Rect
from logger import print_log


class WallManager:
    def __init__(self, space: pymunk.Space):
        self.space = space
        self._dynamic_walls: list[pymunk.Segment] = []
        self._screen_walls: list[pymunk.Segment] = []

    def add_screen_walls(self, ox: int, oy: int, w: int, h: int) -> None:
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
            self._screen_walls.append(seg)
            self.space.add(seg)
        print_log(f"[牆壁] 添加屏幕邊界: ({x0},{y0}) - ({x1},{y1})")

    def clear_screen_walls(self) -> None:
        for seg in self._screen_walls:
            self.space.remove(seg)
        self._screen_walls.clear()

    def clear_dynamic_walls(self) -> None:
        for seg in self._dynamic_walls:
            self.space.remove(seg)
        self._dynamic_walls.clear()

    def _add_rect_wall(self, rect: Rect, elasticity: float = 0.6) -> None:
        x = rect.x
        y = rect.y
        w, h = rect.w, rect.h
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
        x = rect.x
        y = rect.y
        w, h = rect.w, rect.h
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

    def get_all_walls(self) -> list[pymunk.Segment]:
        """獲取所有牆壁段（屏幕邊界 + 動態窗口）"""
        return self._screen_walls + self._dynamic_walls

    def rebuild_window_walls(self, rects: list[Rect]) -> None:
        """重建動態窗口牆壁"""
        self.clear_dynamic_walls()
        if rects:
            print_log(f"[牆壁] 重建 {len(rects)} 個窗口牆")
            for rect in rects:
                print_log(f"  窗口: Rect({rect.x},{rect.y},{rect.w},{rect.h})")
                self._add_rect_wall(rect)
