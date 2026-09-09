from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QGraphicsPixmapItem, QGraphicsRectItem, QGraphicsScene, QGraphicsTextItem, QGraphicsView
from PIL import Image
from model.project import Project

def pil_to_qpixmap(image: Image.Image) -> QPixmap:
    """Convert a Pillow RGBA image into a detached QPixmap.

        Args:
            image: Parameter used by this operation.

        Returns:
            QPixmap: The operation result.
    """
    rgba = image.convert("RGBA")
    data = rgba.tobytes("raw", "RGBA")
    qimage = QImage(
        data,
        rgba.width,
        rgba.height,
        rgba.width * 4,
        QImage.Format.Format_RGBA8888,
    ).copy()
    return QPixmap.fromImage(qimage)

class TrimSheetView(QGraphicsView):
    cardClicked = Signal(int)
    selectionChanged = Signal(object, int)

    def __init__(self, parent=None):
        """Perform the   init   operation.

                Args:
                    parent: Parameter used by this operation.
        """
        super().__init__(parent)
        self.scene_obj = QGraphicsScene(self)
        self.setScene(self.scene_obj)
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setBackgroundBrush(QColor("#111111"))
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setMinimumSize(650, 600)
        self.card_rects: list[QGraphicsRectItem] = []
        self.card_labels: list[QGraphicsTextItem] = []
        self.selected_indices: set[int] = {0}
        self.active_index = 0
        self.project: Optional[Project] = None
        self._pix_item: Optional[QGraphicsPixmapItem] = None
        self._has_user_view = False

    def set_preview_background(self, color: str):
        """Set the viewport background color.

                Args:
                    color: Parameter used by this operation.
        """
        self.setBackgroundBrush(QColor(color))

    def set_sheet(
            self,
            image: Image.Image,
            project: Project,
            selected: int,
            selected_indices: Optional[set[int]] = None,
    ):
        """Replace the viewport contents with a rendered trim sheet.

                Args:
                    image: Parameter used by this operation.
                    project: Parameter used by this operation.
                    selected: Parameter used by this operation.
                    selected_indices: Parameter used by this operation.
        """
        self.project = project
        self.active_index = int(selected)
        self.selected_indices = set(selected_indices or {selected})
        self.selected_indices = {
                                    i for i in self.selected_indices
                                    if 0 <= i < len(project.cards)
                                } or {self.active_index}
        self.set_preview_background(project.background)
        self.scene_obj.clear()
        self.card_rects.clear()
        self.card_labels.clear()
        self._pix_item = self.scene_obj.addPixmap(pil_to_qpixmap(image))
        self._pix_item.setZValue(0)

        cell_w = project.width / project.columns
        cell_h = project.height / project.rows

        for idx in range(project.columns * project.rows):
            row = idx // project.columns
            col = idx % project.columns
            x = col * cell_w
            y = row * cell_h
            rect = QGraphicsRectItem(QRectF(x, y, cell_w, cell_h))
            rect.setZValue(2)
            self.card_rects.append(rect)
            self.scene_obj.addItem(rect)

            label = QGraphicsTextItem(str(idx + 1))
            label.setDefaultTextColor(QColor(255, 255, 255, 190))
            label.setPos(x + 7, y + 5)
            label.setZValue(3)
            self.card_labels.append(label)
            self.scene_obj.addItem(label)

        self._update_overlays()
        self.scene_obj.setSceneRect(0, 0, project.width, project.height)

        # Do not call fitInView on every render. Rendering a card changes the
        # pixmap but should not change the user's navigation state. Only the
        # first displayed sheet is fitted automatically; subsequent renders
        # preserve whatever zoom/pan the user has chosen.
        if self._pix_item and not self._has_user_view:
            self.fitInView(self._pix_item, Qt.AspectRatioMode.KeepAspectRatio)

    def set_selection(self, indices, active: Optional[int] = None, emit: bool = False):
        """Update the selected card indices and active card.

                Args:
                    indices: Parameter used by this operation.
                    active: Parameter used by this operation.
                    emit: Parameter used by this operation.
        """
        if not self.project or not self.project.cards:
            return
        valid = {
            int(i) for i in indices
            if 0 <= int(i) < len(self.project.cards)
        }
        if not valid:
            valid = {self.active_index}
        self.selected_indices = valid
        if active is not None and int(active) in valid:
            self.active_index = int(active)
        elif self.active_index not in valid:
            self.active_index = min(valid)
        self._update_overlays()
        if emit:
            self.selectionChanged.emit(set(self.selected_indices), self.active_index)

    def _update_overlays(self):
        """Refresh the selection outlines drawn over the cards.
        """
        for i, rect in enumerate(self.card_rects):
            if i == self.active_index:
                pen = QPen(QColor("#FFD24A"), 4)
            elif i in self.selected_indices:
                pen = QPen(QColor("#58C7FF"), 3)
            else:
                pen = QPen(QColor(255, 255, 255, 75), 1)
            rect.setPen(pen)

    def mousePressEvent(self, event):
        """Handle card selection clicks and modifier-based multi-selection.

                Args:
                    event: Parameter used by this operation.
        """
        if event.button() == Qt.MouseButton.LeftButton and self.project:
            scene_pos = self.mapToScene(event.position().toPoint())
            if (
                    0 <= scene_pos.x() <= self.project.width
                    and 0 <= scene_pos.y() <= self.project.height
            ):
                cell_w = self.project.width / self.project.columns
                cell_h = self.project.height / self.project.rows
                col = int(scene_pos.x() // cell_w)
                row = int(scene_pos.y() // cell_h)
                idx = row * self.project.columns + col
                if 0 <= idx < len(self.project.cards):
                    modifiers = event.modifiers()
                    if modifiers & Qt.KeyboardModifier.ShiftModifier:
                        a = min(self.active_index, idx)
                        b = max(self.active_index, idx)
                        selection = set(range(a, b + 1))
                    elif modifiers & Qt.KeyboardModifier.ControlModifier:
                        selection = set(self.selected_indices)
                        if idx in selection and len(selection) > 1:
                            selection.remove(idx)
                        else:
                            selection.add(idx)
                    else:
                        selection = {idx}

                    self.selected_indices = selection or {idx}
                    self.active_index = idx
                    self._update_overlays()
                    self.cardClicked.emit(idx)
                    self.selectionChanged.emit(
                        set(self.selected_indices),
                        self.active_index,
                    )
                    return
        super().mousePressEvent(event)

    def wheelEvent(self, event):
        """Zoom the trim-sheet viewport in or out around the mouse position.

                Args:
                    event: Parameter used by this operation.
        """
        factor = 1.15 if event.angleDelta().y() > 0 else (1.0 / 1.15)
        self.scale(factor, factor)
        self._has_user_view = True
