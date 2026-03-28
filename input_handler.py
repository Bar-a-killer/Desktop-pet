from pynput import keyboard, mouse
from typing import Callable


class InputHandler:
    def __init__(self):
        self.on_key_press:      Callable | None = None
        self.on_mouse_press:    Callable | None = None
        self.on_mouse_release:  Callable | None = None
        self.on_mouse_move:     Callable | None = None
        self._kb_listener    = None
        self._mouse_listener = None

    def start(self) -> None:
        self._kb_listener = keyboard.Listener(on_press=self._handle_key)
        self._mouse_listener = mouse.Listener(
            on_click=self._handle_click,
            on_move=self._handle_move,
        )
        self._kb_listener.daemon = True
        self._mouse_listener.daemon = True
        self._kb_listener.start()
        self._mouse_listener.start()

    def stop(self) -> None:
        if self._kb_listener:
            self._kb_listener.stop()
        if self._mouse_listener:
            self._mouse_listener.stop()

    def _handle_key(self, key) -> None:
        if self.on_key_press:
            self.on_key_press(key)

    def _handle_click(self, x: int, y: int, button, pressed: bool) -> None:
        if button != mouse.Button.left:
            return
        if pressed and self.on_mouse_press:
            self.on_mouse_press(x, y)
        elif not pressed and self.on_mouse_release:
            self.on_mouse_release(x, y)

    def _handle_move(self, x: int, y: int) -> None:
        if self.on_mouse_move:
            self.on_mouse_move(x, y)
