from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class TextToSpeechProvider(ABC):
    @abstractmethod
    def synthesize_to_file(self, text: str) -> Path:
        raise NotImplementedError
