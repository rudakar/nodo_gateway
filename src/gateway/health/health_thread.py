import threading
from gateway.bridge import ArduinoBridge


class HealthThread(threading.Thread):
    """
    Hilo que publica un latido periódico vía ArduinoBridge (modo por líneas).
    No usa atributo ._stop (para no romper threading tras fork).
    """

    def __init__(self, bridge: ArduinoBridge, interval: int = 60):
        super().__init__()
        self.bridge = bridge
        self.interval = interval
        self.running = True

    def run(self):
        while self.running:
            ...

    def stop(self):
        self.running = False
        