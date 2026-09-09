from __future__ import annotations

import copy
import json
import logging
import random
from dataclasses import asdict
from pathlib import Path
from typing import Optional
from PIL import Image

from PySide6.QtCore import Qt, QTimer, QThreadPool
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog, QFileDialog, QFormLayout, QFrame, QGroupBox, QLineEdit, QHBoxLayout,
    QLabel, QMainWindow, QMessageBox, QPushButton, QScrollArea, QSpinBox, QComboBox,
    QCheckBox, QVBoxLayout, QWidget, QDoubleSpinBox, QApplication, QSlider, QSplitter
)

from model.hair_style import HairStyle
from model.project import HairCard, Project
from model.presets import STYLE_PRESETS, COLOR_PRESETS
from rendering.renderer import HairRenderer
from workers.render_worker import RenderJob
from app.controls import SliderControl
from app.viewport import TrimSheetView
from utils.math import clamp

LOGGER=logging.getLogger("hair_card_generator")

class HairCardEditor(QMainWindow):
    STYLE_PRESETS = STYLE_PRESETS
    COLOR_PRESETS = COLOR_PRESETS

    def __init__(self):
        """Perform the   init   operation.
        """
        super().__init__()
        self.setWindowTitle("Procedural Hair Card Trim Sheet Editor")
        self.resize(1500, 900)

        self.project = Project()
        self.renderer = HairRenderer(supersample=2)
        self.selected_index = 0
        self.selected_indices: set[int] = {0}
        self._copied_style: Optional[HairStyle] = None
        self._updating = False
        self._sheet_image: Optional[Image.Image] = None

        # Interactive rendering state. Rendering is deliberately kept out of
        # the Qt GUI thread so slider changes never freeze the window.
        self._render_pool = QThreadPool(self)
        self._render_pool.setMaxThreadCount(1)
        self._render_generation = 0
        self._render_busy = False
        self._pending_render: Optional[tuple[str, int, int]] = None
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.timeout.connect(self._start_pending_preview)
        self._preview_delay_ms = 120
        self._last_render_error = ""
        # Debounced preview requests can be either a selected-card refresh or
        # a structural full-sheet refresh. Keeping the mode explicit prevents
        # width/height/grid changes from accidentally rendering only the active
        # card when the debounce timer fires.
        self._preview_request_mode = "selected"

        self._build_ui()
        self._load_card_to_controls()
        self.render_sheet()

    def _build_ui(self):
        # Main editor layout: large preview workspace + resizable inspector.
        """Construct the editor layout, controls, actions, and viewport.
        """
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        root.addWidget(splitter, 1)

        # Preview workspace
        preview_panel = QFrame()
        preview_panel.setObjectName("PreviewPanel")
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(8)

        self.viewport = TrimSheetView()
        self.viewport.setObjectName("TrimSheetViewport")
        self.viewport.selectionChanged.connect(self._selection_changed)
        preview_layout.addWidget(self.viewport, 1)

        info_bar = QFrame()
        info_bar.setObjectName("InfoBar")
        info_layout = QHBoxLayout(info_bar)
        info_layout.setContentsMargins(12, 7, 12, 7)
        info_layout.setSpacing(12)
        self.sheet_info = QLabel()
        self.sheet_info.setObjectName("SheetInfo")
        self.card_info = QLabel()
        self.card_info.setObjectName("CardInfo")
        info_layout.addWidget(self.sheet_info)
        info_layout.addStretch(1)
        info_layout.addWidget(self.card_info)
        preview_layout.addWidget(info_bar)
        splitter.addWidget(preview_panel)

        # Inspector / controls

        inspector = QFrame()
        inspector.setObjectName("InspectorPanel")
        inspector_layout = QVBoxLayout(inspector)
        inspector_layout.setContentsMargins(0, 0, 0, 0)
        inspector_layout.setSpacing(8)

        header = QFrame()
        header.setObjectName("InspectorHeader")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(14, 12, 14, 12)
        header_layout.setSpacing(2)
        title = QLabel("HAIR CARD EDITOR")
        title.setObjectName("InspectorTitle")
        subtitle = QLabel("Trim sheet generation & card controls")
        subtitle.setObjectName("InspectorSubtitle")
        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        inspector_layout.addWidget(header)

        scroll = QScrollArea()
        scroll.setObjectName("InspectorScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        controls_container = QWidget()
        controls_container.setObjectName("ControlsContainer")
        controls_layout = QVBoxLayout(controls_container)
        controls_layout.setContentsMargins(2, 2, 2, 2)
        controls_layout.setSpacing(8)
        controls_layout.addWidget(self._make_project_group())
        controls_layout.addWidget(self._make_card_group())
        controls_layout.addWidget(self._make_style_group())
        controls_layout.addWidget(self._make_shape_group())
        controls_layout.addWidget(self._make_braid_group())
        controls_layout.addWidget(self._make_render_group())
        scroll.setWidget(controls_container)
        inspector_layout.addWidget(scroll, 1)

        # All project/render actions live in the inspector, not underneath
        # the preview. This keeps the workspace clean and makes the controls
        # behave like a conventional DCC/property editor.
        actions = QGroupBox("Actions")
        actions.setObjectName("ActionsGroup")
        actions_layout = QVBoxLayout(actions)
        actions_layout.setContentsMargins(10, 12, 10, 10)
        actions_layout.setSpacing(6)

        render_row = QHBoxLayout()
        self.btn_render = QPushButton("Render Sheet")
        self.btn_render.setObjectName("PrimaryAction")
        self.btn_render.clicked.connect(self.render_sheet)
        self.btn_render_selected = QPushButton("Render Selected")
        self.btn_render_selected.clicked.connect(self.render_selected)
        render_row.addWidget(self.btn_render, 1)
        render_row.addWidget(self.btn_render_selected, 1)
        actions_layout.addLayout(render_row)

        export_row = QHBoxLayout()
        self.btn_export = QPushButton("Export PNG")
        self.btn_export.setObjectName("ExportAction")
        self.btn_export.clicked.connect(self.export_png)
        self.btn_export_card = QPushButton("Export Card PNG")
        self.btn_export_card.setObjectName("ExportAction")
        self.btn_export_card.clicked.connect(self.export_selected_card)
        export_row.addWidget(self.btn_export, 1)
        export_row.addWidget(self.btn_export_card, 1)
        actions_layout.addLayout(export_row)

        project_row = QHBoxLayout()
        self.btn_save = QPushButton("Save Project")
        self.btn_save.setObjectName("SecondaryAction")
        self.btn_save.clicked.connect(self.save_project)
        self.btn_load = QPushButton("Load Project")
        self.btn_load.setObjectName("SecondaryAction")
        self.btn_load.clicked.connect(self.load_project)
        project_row.addWidget(self.btn_save, 1)
        project_row.addWidget(self.btn_load, 1)
        actions_layout.addLayout(project_row)

        inspector_layout.addWidget(actions)
        splitter.addWidget(inspector)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setSizes([1120, 430])

    def _form_widget():
        """Create a widget containing a configured form layout.
        """
        box = QWidget()
        form = QFormLayout(box)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        return box, form

    def _make_project_group(self):
        """Create controls for trim-sheet dimensions and rendering quality.
        """
        group = QGroupBox("Trim Sheet")
        layout = QFormLayout(group)

        self.sheet_width = QSpinBox()
        self.sheet_width.setRange(64, 16384)
        self.sheet_width.setSingleStep(64)
        self.sheet_width.valueChanged.connect(self._project_changed)
        layout.addRow("Width", self.sheet_width)

        self.sheet_height = QSpinBox()
        self.sheet_height.setRange(64, 16384)
        self.sheet_height.setSingleStep(64)
        self.sheet_height.valueChanged.connect(self._project_changed)
        layout.addRow("Height", self.sheet_height)

        self.columns = QSpinBox()
        self.columns.setRange(1, 32)
        self.columns.valueChanged.connect(self._grid_changed)
        layout.addRow("Cards Across", self.columns)

        self.rows = QSpinBox()
        self.rows.setRange(1, 32)
        self.rows.valueChanged.connect(self._grid_changed)
        layout.addRow("Cards Down", self.rows)

        self.card_count_label = QLabel()
        layout.addRow("Total Cards", self.card_count_label)

        bg_row = QWidget()
        bg_layout = QHBoxLayout(bg_row)
        bg_layout.setContentsMargins(0, 0, 0, 0)
        self.background_button = QPushButton()
        self.background_button.clicked.connect(self._choose_background_color)
        bg_layout.addWidget(self.background_button, 1)
        self.background_reset = QPushButton("Reset")
        self.background_reset.clicked.connect(self._reset_background_color)
        bg_layout.addWidget(self.background_reset)
        layout.addRow("Preview Background", bg_row)

        self.supersample = QComboBox()
        self.supersample.addItems(["1x", "2x", "3x", "4x"])
        self.supersample.setCurrentIndex(1)
        self.supersample.currentIndexChanged.connect(self._supersample_changed)
        layout.addRow("Quality", self.supersample)

        return group

    def _make_card_group(self):
        """Create controls for card selection and bulk editing.
        """
        group = QGroupBox("Card Selection / Bulk Editing")
        layout = QFormLayout(group)

        self.card_selector = QSpinBox()
        self.card_selector.setRange(1, self.project.columns * self.project.rows)
        self.card_selector.valueChanged.connect(lambda v: self.select_card(v - 1))
        layout.addRow("Active Card", self.card_selector)

        self.selection_info = QLabel("1 card selected")
        self.selection_info.setWordWrap(True)
        layout.addRow("Selection", self.selection_info)

        select_row = QWidget()
        select_layout = QHBoxLayout(select_row)
        select_layout.setContentsMargins(0, 0, 0, 0)
        self.select_all_btn = QPushButton("Select All")
        self.select_all_btn.clicked.connect(self._select_all_cards)
        self.clear_selection_btn = QPushButton("Clear")
        self.clear_selection_btn.clicked.connect(self._clear_selection)
        select_layout.addWidget(self.select_all_btn)
        select_layout.addWidget(self.clear_selection_btn)
        layout.addRow("Selection", select_row)

        self.card_name = QLineEdit()
        self.card_name.textChanged.connect(self._active_card_metadata_changed)
        layout.addRow("Name", self.card_name)

        self.seed = SliderControl(0, 2147483647, 1000, step=1, decimals=0, integer=True)
        self.seed.valueChanged.connect(self._active_card_metadata_changed)
        layout.addRow("Seed", self.seed)

        self.preset = QComboBox()
        self.preset.addItem("Custom")
        self.preset.addItems([name for name, _ in self.STYLE_PRESETS])
        self.preset.currentTextChanged.connect(self._preset_changed)
        layout.addRow("Style Preset", self.preset)

        self.apply_preset = QPushButton("Apply Preset to Selected")
        self.apply_preset.clicked.connect(self._apply_preset)
        layout.addRow("", self.apply_preset)

        self.color_preset = QComboBox()
        self.color_preset.addItem("Custom")
        self.color_preset.addItems([name for name, _ in self.COLOR_PRESETS])
        layout.addRow("Color Preset", self.color_preset)

        self.apply_color_preset = QPushButton("Apply Color to Selected")
        self.apply_color_preset.clicked.connect(self._apply_color_preset)
        layout.addRow("", self.apply_color_preset)

        copy_row = QWidget()
        copy_layout = QHBoxLayout(copy_row)
        copy_layout.setContentsMargins(0, 0, 0, 0)
        self.copy_settings_btn = QPushButton("Copy Style")
        self.copy_settings_btn.clicked.connect(self._copy_style)
        self.paste_settings_btn = QPushButton("Paste to Selected")
        self.paste_settings_btn.clicked.connect(self._paste_style)
        self.paste_settings_btn.setEnabled(False)
        copy_layout.addWidget(self.copy_settings_btn)
        copy_layout.addWidget(self.paste_settings_btn)
        layout.addRow("Style Clipboard", copy_row)

        self.duplicate_btn = QPushButton("Duplicate Active Style to Selected")
        self.duplicate_btn.setToolTip(
            "Copies the active card's style to every selected card while "
            "giving each target a new seed."
        )
        self.duplicate_btn.clicked.connect(self._duplicate_active_to_selected)
        layout.addRow("", self.duplicate_btn)

        self.randomize = QPushButton("Randomize Selected Cards")
        self.randomize.setToolTip(
            "Generate a randomized hairstyle and color theme for every selected card."
        )
        self.randomize.clicked.connect(self._randomize_selected)
        layout.addRow("", self.randomize)

        self.bulk_help = QLabel(
            "Ctrl+Click selects individual cards. Shift+Click selects a range. "
            "Hair/style controls edit all selected cards; name and seed edit only the active card."
        )
        self.bulk_help.setWordWrap(True)
        layout.addRow("", self.bulk_help)

        return group

    def _make_style_group(self):
        """Create controls for core hair style parameters.
        """
        group = QGroupBox("Hair Style")
        layout = QFormLayout(group)

        self.length = self._double(5, 100, 0.5, 94, 1)
        layout.addRow("Length %", self.length)

        self.length_variation = self._double(0, 80, 1, 12, 0)
        self.length_variation.setToolTip(
            "Maximum percentage by which individual strand tips are shortened. "
            "0% = uniform length; higher values create more varied tips."
        )
        layout.addRow("Tip Length Variation %", self.length_variation)

        self.root_width = self._double(0, 100, 1, 64, 1)
        self.root_width.setToolTip(
            "Overall width of the hair lock at the root. "
            "0% = a point; 100% = full usable card width."
        )
        layout.addRow("Root Width %", self.root_width)

        self.middle_width = self._double(0, 100, 1, 48, 1)
        self.middle_width.setToolTip("Overall width of the hair lock at the middle of the card.")
        layout.addRow("Middle Width %", self.middle_width)

        self.tip_width = self._double(0, 100, 1, 30, 1)
        self.tip_width.setToolTip(
            "Overall width of the hair lock at the tip. "
            "0% forms a point; 100% creates a full-width fan."
        )
        layout.addRow("Tip Width %", self.tip_width)

        self.primary = self._spin(0, 250, 1, 50)
        layout.addRow("Primary Strands", self.primary)

        self.secondary = self._spin(0, 250, 1, 50)
        layout.addRow("Secondary Strands", self.secondary)

        self.flyaways = self._spin(0, 3000, 10, 20)
        layout.addRow("Flyaway Strands", self.flyaways)

        self.clump_count = self._spin(0, 128, 1, 8)
        layout.addRow("Clump Count", self.clump_count)

        self.clump_strength = self._double(0, 1, 0.01, 0.55, 2)
        layout.addRow("Clump Strength", self.clump_strength)

        return group

    def _make_shape_group(self):
        """Create controls for wave, frizz, tip, and strand parameters.
        """
        group = QGroupBox("Wave / Frizz / Tips")
        layout = QFormLayout(group)

        self.wave_cycles = self._double(0, 60, 0.1, 2, 1)
        layout.addRow("Wave Cycles", self.wave_cycles)

        self.wave_amp = self._double(0, 60, 0.1, 5, 1)
        layout.addRow("Wave Amplitude %", self.wave_amp)

        self.secondary_cycles = self._double(0, 120, 0.1, 4, 1)
        layout.addRow("Secondary Cycles", self.secondary_cycles)

        self.secondary_amp = self._double(0, 30, 0.1, 1.5, 1)
        layout.addRow("Secondary Amplitude %", self.secondary_amp)

        self.frizz = self._double(0, 30, 0.05, 0.7, 2)
        layout.addRow("Frizz %", self.frizz)

        self.frizz_freq = self._double(0.1, 10, 0.1, 1.0, 1)
        layout.addRow("Frizz Frequency", self.frizz_freq)

        self.tip_spread = self._double(0, 100, 0.5, 10, 1)
        layout.addRow("Tip Spread %", self.tip_spread)

        self.tip_breakup = self._double(0, 1, 0.01, 0.2, 2)
        layout.addRow("Tip Breakup", self.tip_breakup)

        self.strand_start_width = self._double(0.15, 16, 0.05, 1.55, 2)
        self.strand_start_width.setToolTip("Width of each strand at the root/start of the hair card.")
        layout.addRow("Strand Start Width px", self.strand_start_width)

        self.strand_width = self._double(0.15, 16, 0.05, 1.55, 2)
        self.strand_width.setToolTip("Width of each strand at the tip/end of the hair card.")
        layout.addRow("Strand End Width px", self.strand_width)

        self.width_variation = self._double(0, 0.9, 0.01, 0.35, 2)
        layout.addRow("Width Variation", self.width_variation)

        return group

    def _make_braid_group(self):
        """Create controls for the optional procedural braid structure."""
        group = QGroupBox("Braid Structure")
        layout = QFormLayout(group)

        self.braid_enabled = QCheckBox("Enable Braid")
        self.braid_enabled.setChecked(False)
        self.braid_enabled.setToolTip("Replace the normal lateral strand distribution with an interweaving braid structure.")
        self.braid_enabled.toggled.connect(self._card_changed)
        layout.addRow(self.braid_enabled)

        self.braid_strands = self._spin(2, 5, 1, 3)
        self.braid_strands.setToolTip("Number of strand groups interweaving through the braid.")
        layout.addRow("Braid Strands", self.braid_strands)

        self.braid_cycles = self._double(1, 30, 0.1, 8.0, 1)
        self.braid_cycles.setToolTip("Number of complete interweaving cycles along the braid.")
        layout.addRow("Braid Cycles", self.braid_cycles)

        self.braid_width = self._double(10, 100, 1, 70.0, 0)
        self.braid_width.setToolTip("Width of the braid's interweaving path relative to the card silhouette.")
        layout.addRow("Braid Width %", self.braid_width)

        self.braid_tightness = self._double(0, 1, 0.01, 0.75, 2)
        self.braid_tightness.setToolTip("Controls how strongly the strand groups separate and cross. Higher values make a tighter braid.")
        layout.addRow("Braid Tightness", self.braid_tightness)

        self.braid_taper = self._double(0, 90, 1, 25.0, 0)
        self.braid_taper.setToolTip("Reduces braid width progressively toward the tip.")
        layout.addRow("Braid Taper %", self.braid_taper)

        return group

    def _make_render_group(self):
        """Create controls for opacity, color, containment, and preview settings.
        """
        group = QGroupBox("Rendering / Containment / Color")
        layout = QFormLayout(group)

        self.opacity = self._spin(0, 255, 1, 235)
        layout.addRow("Primary Opacity", self.opacity)

        self.secondary_opacity = self._spin(0, 255, 1, 115)
        layout.addRow("Secondary Opacity", self.secondary_opacity)

        self.flyaway_opacity = self._spin(0, 255, 1, 145)
        layout.addRow("Flyaway Opacity", self.flyaway_opacity)

        self.color_variation = self._double(0, 0.5, 0.01, 0.08, 2)
        layout.addRow("Color Variation", self.color_variation)

        self.highlight_probability = self._double(0, 1, 0.01, 0.06, 2)
        layout.addRow("Highlight Probability", self.highlight_probability)

        self.highlight_strength = self._double(0, 1, 0.01, 0.28, 2)
        layout.addRow("Highlight Strength", self.highlight_strength)

        self.safe_margin = self._double(0, 50, 0.25, 3.0, 2)
        layout.addRow("Safe Margin %", self.safe_margin)

        self.live_preview = QCheckBox("Live preview when controls change")
        self.live_preview.setChecked(True)
        self.live_preview.toggled.connect(self._live_preview_toggled)
        layout.addRow("", self.live_preview)

        self.preview_delay = QSpinBox()
        self.preview_delay.setRange(50, 1000)
        self.preview_delay.setSingleStep(25)
        self.preview_delay.setValue(120)
        self.preview_delay.setSuffix(" ms")
        self.preview_delay.valueChanged.connect(self._preview_delay_changed)
        layout.addRow("Preview Delay", self.preview_delay)

        self.preview_quality = QComboBox()
        self.preview_quality.addItems(["1x", "2x", "3x"])
        self.preview_quality.setCurrentIndex(0)
        self.preview_quality.currentIndexChanged.connect(self._preview_quality_changed)
        layout.addRow("Interactive Quality", self.preview_quality)

        self.render_status = QLabel("Ready")
        layout.addRow("Status", self.render_status)

        self._color_buttons = {}
        for label, attr in (
                ("Root Color", "root_color"),
                ("Mid Color", "mid_color"),
                ("Tip Color", "tip_color"),
                ("Highlight Color", "highlight_color"),
        ):
            btn = QPushButton()
            btn.clicked.connect(lambda checked=False, a=attr: self._choose_color(a))
            self._color_buttons[attr] = btn
            layout.addRow(label, btn)

        return group

    def _set_background_button(self, value: str):
        """Update the preview-background button appearance.

                Args:
                    value: Parameter used by this operation.
        """
        self.background_button.setProperty("color_hex", value)
        self.background_button.setText(value.upper())
        self.background_button.setStyleSheet(
            f"QPushButton {{ background: {value}; color: white; font-weight: bold; }}"
        )

    def _choose_background_color(self):
        """Open a color picker and update the preview background.
        """
        current = QColor(self.project.background)
        result = QColorDialog.getColor(
            current,
            self,
            "Choose Preview Background",
        )
        if not result.isValid():
            return
        value = result.name().upper()
        self.project.background = value
        self._set_background_button(value)
        self.viewport.set_preview_background(value)

    def _reset_background_color(self):
        """Restore the default preview background color.
        """
        self.project.background = "#151515"
        self._set_background_button(self.project.background)
        self.viewport.set_preview_background(self.project.background)

    def _spin(self, minimum, maximum, step, value):
        """Create an integer-style slider control connected to card updates.

                Args:
                    minimum: Parameter used by this operation.
                    maximum: Parameter used by this operation.
                    step: Parameter used by this operation.
                    value: Parameter used by this operation.
        """
        box = SliderControl(minimum, maximum, value, step=step, decimals=0, integer=True)
        box.valueChanged.connect(self._card_changed)
        return box

    def _double(self, minimum, maximum, step, value, decimals):
        """Create a floating-point slider control connected to card updates.

                Args:
                    minimum: Parameter used by this operation.
                    maximum: Parameter used by this operation.
                    step: Parameter used by this operation.
                    value: Parameter used by this operation.
                    decimals: Parameter used by this operation.
        """
        box = SliderControl(minimum, maximum, value, step=step, decimals=decimals, integer=False)
        box.valueChanged.connect(self._card_changed)
        return box

    def _project_changed(self):
        """Apply sheet dimension changes and schedule a full preview refresh.
        """
        if self._updating:
            return
        self.project.width = self.sheet_width.value()
        self.project.height = self.sheet_height.value()
        self._pending_render = None
        self._update_card_info()
        # Width/height alter every card's pixel dimensions. A partial card
        # update is therefore invalid; debounce a complete sheet rebuild.
        self._schedule_full_preview(delay=True)
        if self.live_preview.isChecked():
            self.render_status.setText("Waiting for sheet changes to settle…")
        else:
            self.render_status.setText("Modified — click Render Sheet")

    def _grid_changed(self):
        """Apply grid changes and rebuild the project card collection.
        """
        if self._updating:
            return
        self.project.columns = self.columns.value()
        self.project.rows = self.rows.value()
        self.project.normalize_card_count()
        self.card_selector.setMaximum(len(self.project.cards))
        self._update_card_info()
        if self.selected_index >= len(self.project.cards):
            self.selected_index = len(self.project.cards) - 1
        self.selected_indices = {self.selected_index}
        self._load_card_to_controls()
        # Grid changes invalidate the entire raster layout. Rebuild from a
        # fresh sheet instead of patching tiles into the previous dimensions.
        self._sheet_image = None
        self.viewport.set_selection(self.selected_indices, self.selected_index)
        self._schedule_full_preview(delay=True)
        if self.live_preview.isChecked():
            self.render_status.setText(
                f"Updating trim sheet… {self.project.columns} × "
                f"{self.project.rows} ({len(self.project.cards)} cards)"
            )
        else:
            self.render_status.setText("Modified — click Render Sheet")

    def _supersample_changed(self):
        # Final/export quality. Interactive preview has its own quality setting
        # so a high-quality export setting does not make slider dragging slow.
        """Apply the final render quality setting to future previews.
        """
        self._invalidate_render_generation()
        if self.live_preview.isChecked():
            self._schedule_full_preview()

    def _live_preview_toggled(self, enabled: bool):
        """Enable or disable debounced live previews.

                Args:
                    enabled: Parameter used by this operation.
        """
        if enabled:
            self.render_status.setText("Live preview enabled")
            self._schedule_selected_preview(delay=False)
        else:
            self._preview_timer.stop()
            self._pending_render = None
            self.render_status.setText("Live preview disabled — use Render buttons")

    def _preview_delay_changed(self, value: int):
        """Update the interactive preview debounce delay.

                Args:
                    value: Parameter used by this operation.
        """
        self._preview_delay_ms = int(value)
        if self._preview_timer.isActive():
            self._preview_timer.start(self._preview_delay_ms)

    def _preview_quality_changed(self):
        """Apply a changed interactive preview quality setting.
        """
        if self.live_preview.isChecked():
            self._schedule_selected_preview()

    def _selection_changed(self, indices, active: int):
        """Synchronize editor selection state with the viewport.

                Args:
                    indices: Parameter used by this operation.
                    active: Parameter used by this operation.
        """
        if not self.project.cards:
            return
        self.selected_indices = {
                                    int(i) for i in indices
                                    if 0 <= int(i) < len(self.project.cards)
                                } or {int(active)}
        self.selected_index = int(active)
        self._load_card_to_controls()
        self._update_card_info()
        self.viewport.set_selection(self.selected_indices, self.selected_index)

    def select_card(self, index: int):
        """Select one card as the active card.

                Args:
                    index: Parameter used by this operation.
        """
        if self._updating or not self.project.cards:
            return
        index = int(clamp(index, 0, len(self.project.cards) - 1))
        self.selected_index = index
        self.selected_indices = {index}
        self._load_card_to_controls()
        self._update_card_info()
        self.viewport.set_selection(self.selected_indices, self.selected_index)

    def _select_all_cards(self):
        """Select every card in the current project.
        """
        self.selected_indices = set(range(len(self.project.cards)))
        self.selected_index = min(self.selected_indices) if self.selected_indices else 0
        self._load_card_to_controls()
        self._update_card_info()
        self.viewport.set_selection(self.selected_indices, self.selected_index)

    def _clear_selection(self):
        # Keep one active card selected so bulk operations always have a valid target.
        """Reduce the selection to the current active card.
        """
        self.selected_indices = {self.selected_index}
        self._load_card_to_controls()
        self._update_card_info()
        self.viewport.set_selection(self.selected_indices, self.selected_index)

    def _update_card_info(self):
        """Refresh labels describing the sheet and current selection.
        """
        count = self.project.columns * self.project.rows
        selected_count = len(self.selected_indices) if self.selected_indices else 1
        self.card_count_label.setText(str(count))
        self.selection_info.setText(
            f"{selected_count} card{'s' if selected_count != 1 else ''} selected"
        )
        self.sheet_info.setText(
            f"{self.project.width} × {self.project.height} px  |  "
            f"{self.project.columns} × {self.project.rows} cards"
        )
        if self.project.cards:
            self.card_info.setText(
                f"Active Card {self.selected_index + 1} / {len(self.project.cards)}  |  "
                f"Selected: {selected_count}"
            )

    def _active_card_metadata_changed(self):
        """Write the active card name and seed back to the project.
        """
        if self._updating or not self.project.cards:
            return
        card = self.project.cards[self.selected_index]
        card.style.name = self.card_name.text().strip() or f"Card {card.index + 1}"
        card.seed = int(self.seed.value())
        self._schedule_selected_cards_preview()

    def _card_changed(self):
        """Write control values to selected cards and schedule a preview.
        """
        if self._updating or not self.project.cards:
            return

        self._write_controls_to_selected()
        self._pending_render = None
        self._render_generation += 1
        if self.live_preview.isChecked():
            self._preview_timer.start(self._preview_delay_ms)
            self.render_status.setText(
                f"Waiting for changes to settle… ({len(self.selected_indices)} cards)"
            )
        else:
            self.render_status.setText("Modified — click Render Selected")

    def _invalidate_render_generation(self):
        """Invalidate pending preview work and increment the render generation.
        """
        self._render_generation += 1
        self._pending_render = None
        self._preview_timer.stop()
        self.render_status.setText("Rendering state changed…")

    def _preview_supersample_value(self) -> int:
        """Return the supersampling factor used for interactive previews.

                Returns:
                    int: The operation result.
        """
        return max(1, self.preview_quality.currentIndex() + 1)

    def _final_supersample_value(self) -> int:
        """Return the supersampling factor used for final rendering.

                Returns:
                    int: The operation result.
        """
        return max(1, self.supersample.currentIndex() + 1)

    def _snapshot_project(self) -> Project:
        # Worker threads must never read mutable widget-backed state directly.
        """Create an isolated project copy safe for a worker thread.

                Returns:
                    Project: The operation result.
        """
        return copy.deepcopy(self.project)

    def _schedule_selected_preview(self, delay: bool = True):
        """Schedule an interactive preview of the current selection.

                Args:
                    delay: Parameter used by this operation.
        """
        self._schedule_selected_cards_preview(delay=delay)

    def _schedule_full_preview(self, delay: bool = True):
        """Schedule an interactive full-sheet preview.

                Args:
                    delay: Parameter used by this operation.
        """
        if not self.project.cards:
            return
        self._render_generation += 1
        self._preview_request_mode = "sheet"
        if delay and self.live_preview.isChecked():
            self._preview_timer.start(self._preview_delay_ms)
        else:
            self._preview_timer.stop()
            self._queue_render("sheet", -1, self._preview_supersample_value())

    def _schedule_selected_cards_preview(self, delay: bool = True):
        """Schedule an interactive preview of selected cards.

                Args:
                    delay: Parameter used by this operation.
        """
        if not self.live_preview.isChecked() or not self.project.cards:
            return
        self._render_generation += 1
        self._preview_request_mode = "selected"
        if delay:
            self._preview_timer.start(self._preview_delay_ms)
        else:
            self._preview_timer.stop()
            self._start_pending_preview()

    def _start_pending_preview(self):
        """Start the currently pending interactive preview request.
        """
        if not self.live_preview.isChecked() or not self.project.cards:
            return

        # Structural changes (sheet size / grid) must always rebuild the entire
        # sheet. Never let the generic debounce timer turn a full-sheet request
        # into a selected-card request.
        if self._preview_request_mode == "sheet":
            self._queue_render(
                "sheet", -1, self._preview_supersample_value()
            )
            return

        indices = tuple(sorted(self.selected_indices))
        self._queue_render(
            "cards" if len(indices) > 1 else "card",
            indices if len(indices) > 1 else self.selected_index,
            self._preview_supersample_value(),
        )

    def _queue_render(self, mode: str, card_index, supersample: int):
        """Queue a render without collapsing multi-card selections into one int.

                - ``card`` mode expects a single integer index.
                - ``cards`` mode expects an iterable of integer indices.
                - ``sheet`` mode uses ``-1``.

        Args:
            mode: Parameter used by this operation.
            card_index: Parameter used by this operation.
            supersample: Parameter used by this operation.
        """
        if mode == "cards":
            if isinstance(card_index, int):
                targets = (card_index,)
            else:
                targets = tuple(sorted({int(i) for i in card_index}))
        elif mode == "card":
            targets = int(card_index)
        else:
            targets = int(card_index)

        self._pending_render = (
            mode,
            targets,
            max(1, int(supersample)),
        )

        if self._render_busy:
            self.render_status.setText("Rendering… latest change queued")
            return

        self._start_next_render()

    def _start_next_render(self):
        """Start the next pending preview render when the worker is idle.
        """
        if self._render_busy or self._pending_render is None:
            return

        mode, card_index, supersample = self._pending_render

        # Export jobs use their own completion callbacks because they also
        # need to write the finished image to disk. Route them here so a
        # queued request can never accidentally be handed to RenderJob with
        # an unsupported mode.
        if mode == "sheet_export":
            self._start_next_export_render()
            return
        if mode == "card_export":
            self._start_next_export_card_render()
            return

        self._pending_render = None
        project = self._snapshot_project()
        project.normalize_card_count()

        self._render_busy = True
        self.render_status.setText(
            "Rendering card preview…"
            if mode == "card"
            else "Rendering trim sheet…"
        )

        job = RenderJob(
            self._render_generation,
            mode,
            project,
            card_index,
            supersample,
        )
        job.signals.finished.connect(self._render_finished)
        job.signals.error.connect(self._render_failed)
        self._render_pool.start(job)

    def _render_finished(self, generation: int, mode: str, card_index, image):
        """Apply a completed preview render if it is still current.

                Args:
                    generation: Parameter used by this operation.
                    mode: Parameter used by this operation.
                    card_index: Parameter used by this operation.
                    image: Parameter used by this operation.
        """
        self._render_busy = False

        # Discard results from an older request. This is what prevents an
        # earlier slider position from overwriting a newer position.
        if generation == self._render_generation:
            if mode == "sheet":
                self._sheet_image = image
            elif mode == "card":
                self._replace_card_in_sheet(int(card_index), image)
            elif mode == "cards":
                self._replace_cards_in_sheet(image)

            if self._sheet_image is not None:
                self.viewport.set_sheet(
                    self._sheet_image,
                    self.project,
                    self.selected_index,
                    self.selected_indices,
                )
                self._update_card_info()

            self.render_status.setText("Ready")

        if self._pending_render is not None:
            self._start_next_render()

    def _render_failed(self, generation: int, error: str):
        """Handle a failed background preview render.

                Args:
                    generation: Parameter used by this operation.
                    error: Parameter used by this operation.
        """
        self._render_busy = False
        if generation == self._render_generation:
            self._last_render_error = error
            self.render_status.setText(f"Render error: {error}")

        if self._pending_render is not None:
            self._start_next_render()

    def _replace_cards_in_sheet(self, tiles: dict[int, Image.Image]):
        """Replace multiple rasterized card tiles inside the current sheet.

                Args:
                    tiles: Parameter used by this operation.
        """
        if self._sheet_image is None:
            self._queue_render(
                "sheet",
                -1,
                self._preview_supersample_value(),
            )
            return
        for index, tile in tiles.items():
            self._replace_card_in_sheet(int(index), tile)

    def _replace_card_in_sheet(self, index: int, tile: Image.Image):
        """Replace one rasterized card tile inside the current sheet.

                Args:
                    index: Parameter used by this operation.
                    tile: Parameter used by this operation.
        """
        if self._sheet_image is None:
            # The initial full-sheet render may still be pending. Keep this
            # result out of the viewport rather than constructing a partial
            # sheet, then request a full preview using the latest state.
            self._queue_render(
                "sheet",
                -1,
                self._preview_supersample_value(),
            )
            return

        cell_w = self.project.width // self.project.columns
        cell_h = self.project.height // self.project.rows
        row = index // self.project.columns
        col = index % self.project.columns
        x = col * cell_w
        y = row * cell_h

        expected_w = (
            cell_w
            if col < self.project.columns - 1
            else self.project.width - x
        )
        expected_h = (
            cell_h
            if row < self.project.rows - 1
            else self.project.height - y
        )

        if tile.size != (expected_w, expected_h):
            tile = tile.resize(
                (expected_w, expected_h),
                Image.Resampling.LANCZOS,
            )

        # Clear the previous contents of this exact tile before compositing.
        # A transparent source pixel must remove old hair rather than merely
        # leave the previous render underneath it.
        self._sheet_image.paste(
            (0, 0, 0, 0),
            (x, y, x + expected_w, y + expected_h),
        )
        self._sheet_image.alpha_composite(tile, (x, y))

    def render_sheet(self):
        """Public button action: force a full preview at final quality.
        """
        self._write_controls_to_card()
        self._render_generation += 1
        self._preview_timer.stop()
        self._queue_render(
            "sheet",
            -1,
            self._final_supersample_value(),
        )

    def render_selected(self):
        """Public button action: render only the selected card.
        """
        self._write_controls_to_card()
        self._render_generation += 1
        self._preview_timer.stop()
        indices = tuple(sorted(self.selected_indices))
        self._queue_render(
            "cards" if len(indices) > 1 else "card",
            indices if len(indices) > 1 else self.selected_index,
            self._final_supersample_value(),
        )

    def _write_controls_to_selected(self):
        """Copy all style controls into every selected card.
        """
        indices = sorted(self.selected_indices) or [self.selected_index]
        for index in indices:
            card = self.project.cards[index]
            s = card.style
            s.length_pct = self.length.value()
            s.length_variation_pct = self.length_variation.value()
            s.root_width_pct = self.root_width.value()
            s.middle_width_pct = self.middle_width.value()
            s.tip_width_pct = self.tip_width.value()
            s.primary_strands = int(self.primary.value())
            s.secondary_strands = int(self.secondary.value())
            s.flyaway_strands = int(self.flyaways.value())
            s.clump_count = int(self.clump_count.value())
            s.clump_strength = self.clump_strength.value()
            s.wave_cycles = self.wave_cycles.value()
            s.wave_amplitude_pct = self.wave_amp.value()
            s.secondary_wave_cycles = self.secondary_cycles.value()
            s.secondary_wave_amplitude_pct = self.secondary_amp.value()
            s.frizz_pct = self.frizz.value()
            s.frizz_frequency = self.frizz_freq.value()
            s.tip_spread_pct = self.tip_spread.value()
            s.tip_breakup = self.tip_breakup.value()
            s.strand_start_width_px = self.strand_start_width.value()
            s.strand_width_px = self.strand_width.value()
            s.strand_width_variation = self.width_variation.value()
            s.opacity = int(self.opacity.value())
            s.secondary_opacity = int(self.secondary_opacity.value())
            s.flyaway_opacity = int(self.flyaway_opacity.value())
            s.color_variation = self.color_variation.value()
            s.highlight_probability = self.highlight_probability.value()
            s.highlight_strength = self.highlight_strength.value()
            s.safe_margin_pct = self.safe_margin.value()
            s.braid_enabled = self.braid_enabled.isChecked()
            s.braid_strands = int(self.braid_strands.value())
            s.braid_cycles = self.braid_cycles.value()
            s.braid_width_pct = self.braid_width.value()
            s.braid_tightness = self.braid_tightness.value()
            s.braid_taper_pct = self.braid_taper.value()

            for attr, btn in self._color_buttons.items():
                setattr(s, attr, btn.property("color_hex") or getattr(s, attr))

    def _write_controls_to_card(self):
        # Compatibility helper used by project/export actions.
        """Copy the active card controls and metadata into the project.
        """
        self._write_controls_to_selected()
        card = self.project.cards[self.selected_index]
        card.style.name = self.card_name.text().strip() or f"Card {card.index + 1}"
        card.seed = int(self.seed.value())

    def _load_card_to_controls(self):
        """Load the active card values into the editor controls.
        """
        if not self.project.cards:
            return
        self._updating = True
        try:
            card = self.project.cards[self.selected_index]
            s = card.style

            # Keep the project controls synchronized with the actual project
            # before loading the active card. This is especially important on
            # first launch and after loading a project; the rendered sheet and
            # inspector must describe the same state.
            self.sheet_width.setValue(self.project.width)
            self.sheet_height.setValue(self.project.height)
            self.columns.setValue(self.project.columns)
            self.rows.setValue(self.project.rows)
            self.card_selector.setMaximum(len(self.project.cards))
            self.card_selector.setValue(self.selected_index + 1)
            self.card_name.setText(s.name)
            self.seed.setValue(card.seed)

            values = {
                self.length: s.length_pct,
                self.length_variation: s.length_variation_pct,
                self.root_width: s.root_width_pct,
                self.middle_width: s.middle_width_pct,
                self.tip_width: s.tip_width_pct,
                self.primary: s.primary_strands,
                self.secondary: s.secondary_strands,
                self.flyaways: s.flyaway_strands,
                self.clump_count: s.clump_count,
                self.clump_strength: s.clump_strength,
                self.wave_cycles: s.wave_cycles,
                self.wave_amp: s.wave_amplitude_pct,
                self.secondary_cycles: s.secondary_wave_cycles,
                self.secondary_amp: s.secondary_wave_amplitude_pct,
                self.frizz: s.frizz_pct,
                self.frizz_freq: s.frizz_frequency,
                self.tip_spread: s.tip_spread_pct,
                self.tip_breakup: s.tip_breakup,
                self.strand_start_width: getattr(s, "strand_start_width_px", s.strand_width_px),
                self.strand_width: s.strand_width_px,
                self.width_variation: s.strand_width_variation,
                self.opacity: s.opacity,
                self.secondary_opacity: s.secondary_opacity,
                self.flyaway_opacity: s.flyaway_opacity,
                self.color_variation: s.color_variation,
                self.highlight_probability: s.highlight_probability,
                self.highlight_strength: s.highlight_strength,
                self.safe_margin: s.safe_margin_pct,
                self.braid_strands: getattr(s, "braid_strands", 3),
                self.braid_cycles: getattr(s, "braid_cycles", 8.0),
                self.braid_width: getattr(s, "braid_width_pct", 70.0),
                self.braid_tightness: getattr(s, "braid_tightness", 0.75),
                self.braid_taper: getattr(s, "braid_taper_pct", 25.0),
            }
            for widget, value in values.items():
                widget.setValue(value)
            self.braid_enabled.setChecked(bool(getattr(s, "braid_enabled", False)))

            self._set_preset_selection(s.name)
            self._set_color_preset_selection("Custom")
            current_colors = (s.root_color, s.mid_color, s.tip_color, s.highlight_color)
            for preset_name, preset_colors in self.COLOR_PRESETS:
                if tuple(current_colors) == tuple(preset_colors):
                    self._set_color_preset_selection(preset_name)
                    break
            for attr, btn in self._color_buttons.items():
                hex_value = getattr(s, attr)
                btn.setProperty("color_hex", hex_value)
                btn.setStyleSheet(
                    f"QPushButton {{ background: {hex_value}; color: white; }}"
                )
            self._set_background_button(self.project.background)
            self._update_card_info()
        finally:
            self._updating = False

    def _set_preset_selection(self, name: str):
        """Select a style preset by name when it exists.

                Args:
                    name: Parameter used by this operation.
        """
        for i in range(self.preset.count()):
            if self.preset.itemText(i) == name:
                self.preset.setCurrentIndex(i)
                return
        self.preset.setCurrentIndex(0)

    def _preset_changed(self, text: str):
        # Changing the combo itself does not modify the card; the explicit
        # Apply button avoids accidental replacement of a carefully tuned card.
        """Handle style preset selection changes.

                Args:
                    text: Parameter used by this operation.
        """
        return

    def _apply_preset(self):
        """Apply the selected hairstyle preset to all selected cards.
        """
        name = self.preset.currentText()
        if name == "Custom":
            return
        selected = dict(self.STYLE_PRESETS).get(name)
        if selected is None:
            return
        for index in sorted(self.selected_indices):
            self.project.cards[index].style = copy.deepcopy(selected)
            self.project.cards[index].style.name = f"{name}"
        self._load_card_to_controls()
        self._schedule_selected_cards_preview(delay=False)

    def _apply_color_preset(self):
        """Apply the selected color preset to all selected cards.
        """
        name = self.color_preset.currentText()
        if name == "Custom":
            return
        selected = dict(self.COLOR_PRESETS).get(name)
        if selected is None:
            return

        root_color, mid_color, tip_color, highlight_color = selected
        for index in sorted(self.selected_indices):
            card = self.project.cards[index]
            card.style.root_color = root_color
            card.style.mid_color = mid_color
            card.style.tip_color = tip_color
            card.style.highlight_color = highlight_color

        self._load_card_to_controls()
        self._set_color_preset_selection(name)
        self._schedule_selected_cards_preview(delay=False)

    def _set_color_preset_selection(self, name: str):
        """Select a color preset by name when it exists.

                Args:
                    name: Parameter used by this operation.
        """
        for i in range(self.color_preset.count()):
            if self.color_preset.itemText(i) == name:
                self.color_preset.setCurrentIndex(i)
                return
        self.color_preset.setCurrentIndex(0)

    def _copy_style(self):
        """Copy the active card style into the style clipboard.
        """
        if not self.project.cards:
            return
        # Controls are normally synchronized continuously, but committing the
        # active control values here makes Copy deterministic even when a caller
        # invokes it immediately after a selection/control transition.
        self._write_controls_to_selected()
        self._copied_style = copy.deepcopy(self.project.cards[self.selected_index].style)
        self.render_status.setText(
            f"Copied style from Card {self.selected_index + 1}"
        )
        self.paste_settings_btn.setEnabled(True)

    def _paste_style(self):
        """Paste the clipboard style into all selected cards.

        Bulk mutations invalidate the current render generation before the
        mutation, so an obsolete worker can never win a race with this action.
        """
        if self._copied_style is None:
            QMessageBox.information(
                self,
                "Style Clipboard",
                "Copy a card's style first.",
            )
            return

        targets = sorted(self.selected_indices) or [self.selected_index]
        self._render_generation += 1
        self._pending_render = None
        for index in targets:
            current_name = self.project.cards[index].style.name
            self.project.cards[index].style = copy.deepcopy(self._copied_style)
            self.project.cards[index].style.name = current_name

        self._load_card_to_controls()
        self._update_card_info()
        if self.live_preview.isChecked():
            self._schedule_selected_cards_preview(delay=False)
        else:
            self.render_status.setText("Pasted style — click Render Selected")
        self.render_status.setText(
            f"Pasted style to {len(self.selected_indices)} card(s)"
        )

    def _duplicate_active_to_selected(self):
        """Duplicate the active style into the other selected cards.
        """
        if not self.project.cards:
            return
        source = self.project.cards[self.selected_index]
        targets = [i for i in sorted(self.selected_indices) if i != self.selected_index]
        if not targets:
            QMessageBox.information(
                self,
                "Duplicate Style",
                "Select one or more target cards in addition to the active card.",
            )
            return

        rng = random.Random()
        self._render_generation += 1
        self._pending_render = None
        for index in targets:
            self.project.cards[index].style = copy.deepcopy(source.style)
            self.project.cards[index].style.name = f"{source.style.name} Copy"
            self.project.cards[index].seed = rng.randint(0, 2147483647)

        self._load_card_to_controls()
        self._update_card_info()
        if self.live_preview.isChecked():
            self._schedule_selected_cards_preview(delay=False)
        else:
            self.render_status.setText("Duplicated style — click Render Selected")

    def _randomize_selected(self):
        """Generate randomized styles, colors, and seeds for selected cards.
        """
        if not self.project.cards:
            return

        rng = random.Random()
        selections = sorted(self.selected_indices) or [self.selected_index]
        self._render_generation += 1
        self._pending_render = None

        for index in selections:
            preset_name, base = rng.choice(self.STYLE_PRESETS)
            style = copy.deepcopy(base)

            style.length_pct = clamp(style.length_pct + rng.uniform(-15.0, 8.0), 25.0, 100.0)
            style.length_variation_pct = clamp(style.length_variation_pct + rng.uniform(-8.0, 20.0), 0.0, 75.0)
            style.root_width_pct = clamp(style.root_width_pct + rng.uniform(-18.0, 18.0), 5.0, 100.0)
            style.middle_width_pct = clamp(style.middle_width_pct + rng.uniform(-18.0, 18.0), 3.0, 100.0)
            style.tip_width_pct = clamp(style.tip_width_pct + rng.uniform(-15.0, 18.0), 0.0, 100.0)

            style.primary_strands = rng.randint(40, 250)
            style.secondary_strands = rng.randint(35, 250)
            style.flyaway_strands = rng.randint(0, 70)
            style.clump_count = rng.randint(4, 18)
            style.clump_strength = clamp(style.clump_strength + rng.uniform(-0.18, 0.18), 0.05, 0.98)

            style.wave_cycles = clamp(style.wave_cycles + rng.uniform(-1.5, 3.0), 0.0, 25.0)
            style.wave_amplitude_pct = clamp(style.wave_amplitude_pct + rng.uniform(-3.5, 5.5), 0.0, 20.0)
            style.secondary_wave_cycles = clamp(style.secondary_wave_cycles + rng.uniform(-2.0, 6.0), 0.0, 45.0)
            style.secondary_wave_amplitude_pct = clamp(style.secondary_wave_amplitude_pct + rng.uniform(-0.7, 1.5), 0.0,
                                                       8.0)
            style.frizz_pct = clamp(style.frizz_pct + rng.uniform(-0.7, 1.2), 0.0, 8.0)
            style.frizz_frequency = clamp(style.frizz_frequency + rng.uniform(-0.45, 0.8), 0.1, 4.0)
            style.tip_spread_pct = clamp(style.tip_spread_pct + rng.uniform(-8.0, 18.0), 0.0, 75.0)
            style.tip_breakup = clamp(style.tip_breakup + rng.uniform(-0.14, 0.20), 0.0, 0.95)
            style.strand_width_px = clamp(style.strand_width_px + rng.uniform(-0.35, 0.45), 0.4, 4.5)
            style.strand_start_width_px = clamp(
                style.strand_start_width_px + rng.uniform(-0.45, 0.65), 0.4, 6.0
            )
            style.strand_width_variation = clamp(style.strand_width_variation + rng.uniform(-0.10, 0.18), 0.0, 0.85)
            style.opacity = rng.randint(215, 248)
            style.secondary_opacity = rng.randint(75, 140)
            style.flyaway_opacity = rng.randint(85, 165)
            style.color_variation = clamp(style.color_variation + rng.uniform(-0.03, 0.08), 0.0, 0.25)
            style.highlight_probability = clamp(style.highlight_probability + rng.uniform(-0.025, 0.07), 0.0, 0.25)
            style.highlight_strength = clamp(style.highlight_strength + rng.uniform(-0.08, 0.15), 0.0, 0.9)
            style.safe_margin_pct = clamp(style.safe_margin_pct + rng.uniform(-0.8, 2.0), 0.5, 12.0)
            style.braid_enabled = rng.random() < 0.12
            style.braid_strands = rng.randint(3, 3)
            style.braid_cycles = rng.uniform(5.0, 13.0)
            style.braid_width_pct = rng.uniform(55.0, 85.0)
            style.braid_tightness = rng.uniform(0.55, 0.9)
            style.braid_taper_pct = rng.uniform(10.0, 45.0)

            _, colors = rng.choice(self.COLOR_PRESETS)
            style.root_color, style.mid_color, style.tip_color, style.highlight_color = colors
            style.name = f"Randomized - {preset_name}"

            card = self.project.cards[index]
            card.style = style
            card.seed = rng.randint(0, 2147483647)

        self._load_card_to_controls()
        self._update_card_info()
        if self.live_preview.isChecked():
            self._schedule_selected_cards_preview(delay=False)
        else:
            self.render_status.setText("Randomized selected cards — click Render Selected")

    def _choose_color(self, attr: str):
        """Open a color picker and apply the selected color to the selected cards.

                Args:
                    attr: Parameter used by this operation.
        """
        card = self.project.cards[self.selected_index]
        current = QColor(getattr(card.style, attr))
        result = QColorDialog.getColor(current, self, f"Choose {attr.replace('_', ' ').title()}")
        if not result.isValid():
            return
        value = result.name().upper()
        for index in sorted(self.selected_indices):
            setattr(self.project.cards[index].style, attr, value)
        btn = self._color_buttons[attr]
        btn.setProperty("color_hex", value)
        btn.setStyleSheet(f"QPushButton {{ background: {value}; color: white; }}")
        self._set_color_preset_selection("Custom")
        self._schedule_selected_cards_preview(delay=False)

    def _handle_ui_error(self, operation: str, exc: Exception) -> None:
        """Log an exception and present a concise error message to the user.

                Args:
                    operation: Human-readable description of the failed operation.
                    exc: Exception that caused the failure.

                Returns:
                    None.
        """
        LOGGER.error(
            "%s failed",
            operation,
            exc_info=(type(exc), exc, exc.__traceback__),
        )
        message = f"{operation} failed.\n\n{type(exc).__name__}: {exc}"
        if hasattr(self, "render_status"):
            self.render_status.setText(message.split("\n", 1)[0])
        QMessageBox.critical(self, "Application Error", message)

    def export_png(self):
        """Prompt for a path and render the complete trim sheet for export.
        """
        self._write_controls_to_card()
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Export Hair Card Trim Sheet",
            "hair_trimsheet.png",
            "PNG Files (*.png)",
        )
        if not filename:
            return

        # Store the requested export path and render at final quality off the
        # GUI thread. This keeps export responsive too.
        self._export_png_path = filename
        self._render_generation += 1
        self._preview_timer.stop()
        self._pending_render = ("sheet_export", -1, self._final_supersample_value())
        self._start_next_export_render()

    def _start_next_export_render(self):
        """Start a pending full-sheet export render.
        """
        if self._render_busy or self._pending_render is None:
            return

        mode, card_index, supersample = self._pending_render
        if mode != "sheet_export":
            return
        self._pending_render = None

        project = self._snapshot_project()
        project.normalize_card_count()
        self._render_busy = True
        self.render_status.setText("Exporting trim sheet…")

        job = RenderJob(
            self._render_generation,
            "sheet",
            project,
            -1,
            supersample,
        )
        job.signals.finished.connect(self._export_sheet_finished)
        job.signals.error.connect(self._export_render_failed)
        self._render_pool.start(job)

    def _export_sheet_finished(self, generation: int, mode: str, card_index: int, image):
        """Save a completed trim-sheet export and update the viewport.

                Args:
                    generation: Parameter used by this operation.
                    mode: Parameter used by this operation.
                    card_index: Parameter used by this operation.
                    image: Parameter used by this operation.
        """
        self._render_busy = False
        if generation != self._render_generation:
            if self._pending_render is not None:
                self._start_next_render()
            return
        try:
            image.save(self._export_png_path, "PNG")
            self._sheet_image = image
            self.viewport.set_sheet(
                self._sheet_image,
                self.project,
                self.selected_index,
                self.selected_indices,
            )
            self.render_status.setText("Export complete")
            QMessageBox.information(
                self,
                "Export Complete",
                f"Saved:\n{self._export_png_path}",
            )
        except Exception as exc:
            self.render_status.setText("Export failed")
            QMessageBox.critical(self, "Export Error", str(exc))

    def _export_render_failed(self, generation: int, error: str):
        """Handle an export render failure.

                Args:
                    generation: Parameter used by this operation.
                    error: Parameter used by this operation.
        """
        self._render_busy = False
        if generation == self._render_generation:
            self.render_status.setText(f"Export error: {error}")
            QMessageBox.critical(self, "Export Error", error)
        if self._pending_render is not None:
            self._start_next_render()

    def export_selected_card(self):
        """Prompt for a path and render the active card for export.
        """
        self._write_controls_to_card()
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Export Selected Hair Card",
            f"hair_card_{self.selected_index + 1:02d}.png",
            "PNG Files (*.png)",
        )
        if not filename:
            return

        self._export_card_path = filename
        self._export_card_index = self.selected_index
        self._render_generation += 1
        self._preview_timer.stop()
        self._pending_render = (
            "card_export",
            self.selected_index,
            self._final_supersample_value(),
        )
        self._start_next_export_card_render()

    def _start_next_export_card_render(self):
        """Start a pending single-card export render.
        """
        if self._render_busy or self._pending_render is None:
            return
        mode, card_index, supersample = self._pending_render
        if mode != "card_export":
            return
        self._pending_render = None

        project = self._snapshot_project()
        project.normalize_card_count()
        self._render_busy = True
        self.render_status.setText("Exporting selected card…")

        job = RenderJob(
            self._render_generation,
            "card",
            project,
            card_index,
            supersample,
        )
        job.signals.finished.connect(self._export_card_finished)
        job.signals.error.connect(self._export_render_failed)
        self._render_pool.start(job)

    def _export_card_finished(self, generation: int, mode: str, card_index: int, image):
        """Save a completed single-card export.

                Args:
                    generation: Parameter used by this operation.
                    mode: Parameter used by this operation.
                    card_index: Parameter used by this operation.
                    image: Parameter used by this operation.
        """
        self._render_busy = False
        if generation != self._render_generation:
            if self._pending_render is not None:
                self._start_next_render()
            return
        try:
            image.save(self._export_card_path, "PNG")
            self.render_status.setText("Export complete")
            QMessageBox.information(
                self,
                "Export Complete",
                f"Saved:\n{self._export_card_path}",
            )
        except Exception as exc:
            self.render_status.setText("Export failed")
            QMessageBox.critical(self, "Export Error", str(exc))

    def save_project(self):
        """Serialize the current project to a JSON project file.

                Returns:
                    None.
        """
        try:
            self._write_controls_to_card()
            filename, _ = QFileDialog.getSaveFileName(
                self,
                "Save Hair Card Project",
                "hair_card_project.json",
                "JSON Files (*.json)",
            )
            if not filename:
                return

            data = {
                "width": self.project.width,
                "height": self.project.height,
                "columns": self.project.columns,
                "rows": self.project.rows,
                "background": self.project.background,
                "cards": [
                    {
                        "index": card.index,
                        "seed": card.seed,
                        "style": asdict(card.style),
                    }
                    for card in self.project.cards
                ],
            }

            Path(filename).write_text(
                json.dumps(data, indent=2),
                encoding="utf-8",
            )
            QMessageBox.information(self, "Project Saved", f"Saved:\n{filename}")
        except (OSError, TypeError, ValueError) as exc:
            self._handle_ui_error("Saving project", exc)

    def load_project(self):
        """Load and validate a project from a JSON project file.

                Returns:
                    None.
        """
        try:
            filename, _ = QFileDialog.getOpenFileName(
                self,
                "Load Hair Card Project",
                "",
                "JSON Files (*.json)",
            )
            if not filename:
                return

            data = json.loads(Path(filename).read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("Project file must contain a JSON object.")

            project = Project(
                width=int(data["width"]),
                height=int(data["height"]),
                columns=int(data["columns"]),
                rows=int(data["rows"]),
                background=str(data.get("background", "#151515")),
                cards=[],
            )

            cards_data = data.get("cards", [])
            if not isinstance(cards_data, list):
                raise ValueError("The 'cards' field must be a JSON array.")

            for item in cards_data:
                if not isinstance(item, dict) or not isinstance(item.get("style"), dict):
                    raise ValueError("Each card must contain a valid 'style' object.")

                style_data = dict(item["style"])
                style_data.setdefault("length_variation_pct", 12.0)
                style_data.setdefault("middle_width_pct", 48.0)
                style_data.setdefault("strand_start_width_px", style_data.get("strand_width_px", 1.55))
                style_data.setdefault("braid_enabled", False)
                style_data.setdefault("braid_strands", 3)
                style_data.setdefault("braid_cycles", 8.0)
                style_data.setdefault("braid_width_pct", 70.0)
                style_data.setdefault("braid_tightness", 0.75)
                style_data.setdefault("braid_taper_pct", 25.0)
                style = HairStyle(**style_data)

                project.cards.append(
                    HairCard(
                        int(item["index"]),
                        style,
                        int(item["seed"]),
                    )
                )

            project.normalize_card_count()
            self.project = project
            self.selected_index = 0
            self.selected_indices = {0}

            self._updating = True
            try:
                self.sheet_width.setValue(project.width)
                self.sheet_height.setValue(project.height)
                self.columns.setValue(project.columns)
                self.rows.setValue(project.rows)
                self.card_selector.setMaximum(len(project.cards))
            finally:
                self._updating = False

            self._load_card_to_controls()
            self.render_sheet()
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            self._handle_ui_error("Loading project", exc)

    def closeEvent(self, event):
        """Stop timers and background rendering before closing the window.

                Args:
                    event: Parameter used by this operation.
        """
        self._preview_timer.stop()
        self._pending_render = None
        self._render_pool.clear()
        self._render_pool.waitForDone(2000)
        event.accept()
