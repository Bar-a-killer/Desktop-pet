import pymunk


class WallManager:
    def __init__(self, space: pymunk.Space):
        self.space = space
        self._dynamic_walls: list[pymunk.Segment] = []

    def add_screen_walls(self, w: int, h: int) -> None:
        """螢幕四邊永久牆壁"""
        edges = [
            [(0, h), (w, h)],  # 下
            [(0, 0), (0, h)],  # 左
            [(w, 0), (w, h)],  # 右
            [(0, 0), (w, 0)],  # 上
        ]
        for a, b in edges:
            seg = pymunk.Segment(self.space.static_body, a, b, 2)
            seg.elasticity = 0.8
            seg.friction = 0.1
            self.space.add(seg)

    def clear_dynamic_walls(self) -> None:
        """清除所有視窗牆壁"""
        for seg in self._dynamic_walls:
            self.space.remove(seg)
        self._dynamic_walls.clear()

    def add_window_wall(self, x: int, y: int, w: int, h: int) -> None:
        """為單一視窗加入四邊牆壁"""
        corners = [
            [(x,     y),     (x + w, y)    ],  # 上
            [(x + w, y),     (x + w, y + h)],  # 右
            [(x + w, y + h), (x,     y + h)],  # 下
            [(x,     y + h), (x,     y)    ],  # 左
        ]
        for a, b in corners:
            seg = pymunk.Segment(self.space.static_body, a, b, 2)
            seg.elasticity = 0.6
            seg.friction = 0.5
            self._dynamic_walls.append(seg)
            self.space.add(seg)

    def rebuild_window_walls(self, windows: list[tuple[int, int, int, int]]) -> None:
        """重建所有視窗牆壁"""
        self.clear_dynamic_walls()
        for (x, y, w, h) in windows:
            self.add_window_wall(x, y, w, h)
