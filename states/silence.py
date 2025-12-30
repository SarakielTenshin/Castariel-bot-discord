import time
from dataclasses import dataclass

@dataclass
class ChannelRest:
    until_ts: float = 0.0

    def active(self) -> bool:
        return time.time() < self.until_ts

    def set_for(self, seconds: int) -> None:
        self.until_ts = time.time() + seconds