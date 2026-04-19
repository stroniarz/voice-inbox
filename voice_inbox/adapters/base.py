from dataclasses import dataclass
from typing import Protocol, Iterable


@dataclass
class Event:
    source: str
    external_id: str
    author: str
    short: str
    title: str
    body: str
    priority: int = 3  # 0=None, 1=Urgent, 2=High, 3=Normal (default), 4=Low


class Adapter(Protocol):
    name: str

    def poll(self) -> Iterable[Event]:
        ...
