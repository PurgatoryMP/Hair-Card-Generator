from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSlider, QDoubleSpinBox, QWidget
from utils.math import clamp

class SliderControl(QWidget):
    """Horizontal slider with a compact numeric readout.

    QSlider is integer-only, so floating-point controls are represented using
    a scale factor internally while callers continue to use .value()/setValue().
    """

    valueChanged = Signal(object)

    def __init__(
            self,
            minimum,
            maximum,
            value,
            step=1,
            decimals=0,
            integer=False,
            parent=None,
    ):
        """Perform the   init   operation.

                Args:
                    minimum: Parameter used by this operation.
                    maximum: Parameter used by this operation.
                    value: Parameter used by this operation.
                    step: Parameter used by this operation.
                    decimals: Parameter used by this operation.
                    integer: Parameter used by this operation.
                    parent: Parameter used by this operation.
        """
        super().__init__(parent)
        self._integer = bool(integer)
        self._decimals = int(decimals)
        self._step = float(step)
        self._scale = max(1, int(round(10 ** self._decimals)))
        self._min = int(round(float(minimum) * self._scale))
        self._max = int(round(float(maximum) * self._scale))

        if self._max <= self._min:
            self._max = self._min + 1

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, self._max - self._min)
        self.slider.setSingleStep(max(1, int(round(self._step * self._scale))))
        self.slider.setPageStep(max(1, self.slider.singleStep() * 4))
        self.slider.valueChanged.connect(self._slider_changed)

        self.value_label = QLabel()
        # Fixed width prevents the inspector/form layout from reflowing when
        # values change digit count (for example 9 -> 10 or 0 -> 100).
        self.value_label.setFixedWidth(64)
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self.slider, 1)
        layout.addWidget(self.value_label)

        self.setValue(value)
        self._update_display(self.slider.value())

    def _update_display(self, raw: int):
        """Update the numeric label displayed beside the slider.

                Args:
                    raw: Parameter used by this operation.
        """
        value = (raw + self._min) / self._scale
        if self._integer:
            value = int(round(value))
            self.value_label.setText(str(value))
        else:
            value = round(value, self._decimals)
            self.value_label.setText(f"{value:.{self._decimals}f}")

    def _slider_changed(self, raw: int):
        """Update the slider display and emit its converted value.

                Args:
                    raw: Parameter used by this operation.
        """
        self._update_display(raw)
        self.valueChanged.emit(self.value())

    def value(self):
        """Return the slider value in the configured numeric representation.
        """
        raw = self.slider.value()
        value = (raw + self._min) / self._scale
        return int(round(value)) if self._integer else round(value, self._decimals)

    def setValue(self, value):
        """Set the slider value after clamping it to the configured range.

                Args:
                    value: Parameter used by this operation.
        """
        value = clamp(float(value), self._min / self._scale, self._max / self._scale)
        raw = int(round(value * self._scale)) - self._min
        self.slider.setValue(raw)
        self._update_display(self.slider.value())

    def setRange(self, minimum, maximum):
        """Change the numeric range represented by the slider.

                Args:
                    minimum: Parameter used by this operation.
                    maximum: Parameter used by this operation.
        """
        minimum_i = int(round(float(minimum) * self._scale))
        maximum_i = int(round(float(maximum) * self._scale))
        if maximum_i <= minimum_i:
            maximum_i = minimum_i + 1
        self._min = minimum_i
        self._max = maximum_i
        self.slider.setRange(0, self._max - self._min)
