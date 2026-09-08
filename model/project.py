from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Optional

from .hair_style import HairStyle

@dataclass
class HairCard:
    index: int
    style: HairStyle
    seed: int

@dataclass
class Project:
    width: int = 1024
    height: int = 1024
    columns: int = 4
    rows: int = 1
    background: str = "#151515"
    cards: Optional[list[HairCard]] = None

    def __post_init__(self):
        """Initialize missing cards and validate core project dimensions.

                Raises:
                    ValueError: If dimensions or grid counts are invalid.
        """
        if self.width < 1 or self.height < 1:
            raise ValueError("Project width and height must be positive.")
        if self.columns < 1 or self.rows < 1:
            raise ValueError("Project columns and rows must be positive.")
        if self.cards is None:
            self.cards = []
            base = HairStyle()
            for i in range(self.columns * self.rows):
                style = copy.deepcopy(base)
                style.name = f"Card {i + 1}"
                self.cards.append(HairCard(i, style, 1000 + i * 37))

    def normalize_card_count(self):
        """Resize the card list to match the current project grid.

                Existing cards are preserved whenever possible, and new cards receive
                deterministic default seeds based on their index.
        """
        target = self.columns * self.rows
        if target < 1:
            target = 1
        while len(self.cards) < target:
            i = len(self.cards)
            style = HairStyle(name=f"Card {i + 1}")
            self.cards.append(HairCard(i, style, 1000 + i * 37))
        if len(self.cards) > target:
            self.cards = self.cards[:target]
        for i, card in enumerate(self.cards):
            card.index = i
