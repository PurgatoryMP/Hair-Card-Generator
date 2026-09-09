from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, Signal

from model.project import Project
from rendering.renderer import HairRenderer


class RenderSignals(QObject):
    """Signals emitted by a render worker back to the GUI thread."""

    finished = Signal(int, str, object, object)
    error = Signal(int, str)


class RenderJob(QRunnable):
    """Render one card, selected cards, or an entire sheet off the GUI thread."""

    def __init__(self, generation: int, mode: str, project: Project, card_index, supersample: int):
        super().__init__()
        self.generation = generation
        self.mode = mode
        self.project = project
        self.card_index = card_index
        self.supersample = max(1, int(supersample))
        self.signals = RenderSignals()

    def _card_size(self, index: int) -> tuple[int, int]:
        cell_w = self.project.width // self.project.columns
        cell_h = self.project.height // self.project.rows
        col = index % self.project.columns
        row = index // self.project.columns
        width = cell_w if col < self.project.columns - 1 else self.project.width - col * cell_w
        height = cell_h if row < self.project.rows - 1 else self.project.height - row * cell_h
        return width, height

    def run(self):
        try:
            renderer = HairRenderer(self.supersample)

            if self.mode == "card":
                index = int(self.card_index)
                card = self.project.cards[index]
                width, height = self._card_size(index)
                image = renderer.render_card(card.style, width, height, card.seed)

            elif self.mode == "cards":
                # Multi-card preview returns a mapping of card index -> tile.
                # The GUI uses the indices to put each finished tile back into
                # its original trim-sheet cell. Do not call render_sheet here.
                indices = tuple(sorted({int(i) for i in self.card_index}))
                tiles = {}
                for index in indices:
                    card = self.project.cards[index]
                    width, height = self._card_size(index)
                    tiles[index] = renderer.render_card(
                        card.style, width, height, card.seed
                    )
                image = tiles

            elif self.mode == "sheet":
                image = renderer.render_sheet(self.project)
                self.card_index = -1

            else:
                raise ValueError(f"Unsupported preview render mode: {self.mode}")

            self.signals.finished.emit(
                self.generation, self.mode, self.card_index, image
            )
        except Exception as exc:
            self.signals.error.emit(
                self.generation, f"{type(exc).__name__}: {exc}"
            )
