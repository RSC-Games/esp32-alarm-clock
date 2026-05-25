from hal.drivers.ssd1309 import Display

class Window:
    def __init__(self):
        ...

    def tick(self) -> None:
        ...

    def repaint(self, display: Display) -> None:
        ...