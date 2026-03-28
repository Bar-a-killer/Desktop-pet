import pymunk
from window_detector import Rect


class WallManager:
    def __init__(self, space: pymunk.Space):
        self.space = space
        self._dynamic_walls: list[pymunk.Segment] = []

    def add_screen_walls(self, w: int, h: int) -> None:
        edges = [
            [(0, h), (w, h)],
            [(0, 0), (0, h)],
            [(w, 0), (w, h)],
            [(0, 0), (w, 0)],
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
        self.clear_dynamic_walls()
        for rect in rects:
            self._add_rect_wall(rect)
