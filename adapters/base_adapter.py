from abc import ABC, abstractmethod
from typing import List, Dict


class BaseAdapter(ABC):
    """Base class for all event source adapters."""

    @abstractmethod
    def fetch_events(self) -> List[Dict]:
        """
        Fetch and return a list of event dicts with keys:
        title, event_date, event_time, description, location_name, source_url
        """
        pass

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Human-readable name of this source."""
        pass
