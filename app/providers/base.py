from abc import ABC, abstractmethod
class Provider(ABC):
    name="provider"
    @abstractmethod
    def fetch_events(self): ...
