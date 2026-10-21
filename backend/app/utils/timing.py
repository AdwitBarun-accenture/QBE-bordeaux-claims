import time


class Stopwatch:
    """sw = Stopwatch(); ...; sw.ms -> elapsed milliseconds"""

    def __init__(self):
        self._start = time.perf_counter()

    @property
    def ms(self) -> int:
        return int((time.perf_counter() - self._start) * 1000)
