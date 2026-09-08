DARK_THEME_QSS = """
/* =========================================================
   Dark theme
   ========================================================= */
QMainWindow, QWidget {
    background: #17191D;
    color: #D9DCE1;
    font-family: "Segoe UI", "Inter", sans-serif;
    font-size: 13px;
}

QFrame#PreviewPanel,
QFrame#InspectorPanel {
    background: #1B1E23;
    border: 1px solid #2B3038;
    border-radius: 8px;
}

QFrame#InfoBar,
QFrame#InspectorHeader {
    background: #20242A;
    border: 1px solid #2B3038;
    border-radius: 7px;
}

QLabel#InspectorTitle {
    color: #F1F3F5;
    font-size: 15px;
    font-weight: 700;
    letter-spacing: 0.6px;
}

QLabel#InspectorSubtitle {
    color: #858C96;
    font-size: 11px;
}

QLabel#SheetInfo,
QLabel#CardInfo {
    color: #AEB5BF;
    font-size: 12px;
    font-weight: 600;
}

QGroupBox {
    background: #20242A;
    border: 1px solid #303640;
    border-radius: 7px;
    margin-top: 12px;
    padding: 12px 10px 10px 10px;
    font-weight: 600;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 0 6px;
    color: #C8CDD5;
    background: #20242A;
}

QFormLayout QLabel {
    color: #AEB5BF;
}

QLineEdit,
QSpinBox,
QDoubleSpinBox,
QComboBox {
    background: #15181C;
    border: 1px solid #353B45;
    border-radius: 5px;
    color: #E5E8EC;
    padding: 5px 8px;
    min-height: 22px;
    selection-background-color: #2F6FEB;
    selection-color: white;
}

QLineEdit:hover,
QSpinBox:hover,
QDoubleSpinBox:hover,
QComboBox:hover {
    border-color: #4A5260;
}

QLineEdit:focus,
QSpinBox:focus,
QDoubleSpinBox:focus,
QComboBox:focus {
    border: 1px solid #4C8DFF;
}

QComboBox::drop-down {
    width: 24px;
    border: none;
}

QComboBox QAbstractItemView {
    background: #20242A;
    border: 1px solid #3A414C;
    color: #E5E8EC;
    selection-background-color: #2F6FEB;
    selection-color: white;
    padding: 4px;
}

QPushButton {
    background: #292E36;
    border: 1px solid #3B424D;
    border-radius: 5px;
    color: #DCE0E6;
    padding: 7px 11px;
    min-height: 24px;
    font-weight: 600;
}

QPushButton:hover {
    background: #323943;
    border-color: #525B68;
}

QPushButton:pressed {
    background: #242932;
    border-color: #4C8DFF;
}

QPushButton:disabled {
    background: #22262C;
    border-color: #2C3138;
    color: #656C76;
}

QPushButton#PrimaryAction {
    background: #2F6FEB;
    border-color: #3F7DF5;
    color: white;
}

QPushButton#PrimaryAction:hover {
    background: #3A7AF0;
    border-color: #5790FF;
}

QPushButton#ExportAction {
    background: #263A55;
    border-color: #35567E;
    color: #DDEBFF;
}

QPushButton#ExportAction:hover {
    background: #2D4767;
    border-color: #4775A8;
}

QPushButton#SecondaryAction {
    background: #24282E;
    color: #BEC5CE;
}

QSlider::groove:horizontal {
    height: 5px;
    background: #363C45;
    border-radius: 2px;
}

QSlider::sub-page:horizontal {
    background: #3D7DF2;
    border-radius: 2px;
}

QSlider::handle:horizontal {
    width: 13px;
    height: 13px;
    margin: -4px 0;
    background: #E2E7EF;
    border: 2px solid #3D7DF2;
    border-radius: 7px;
}

QSlider::handle:horizontal:hover {
    background: white;
    border-color: #65A0FF;
}

QCheckBox {
    spacing: 7px;
    color: #BFC5CD;
}

QCheckBox::indicator {
    width: 15px;
    height: 15px;
    border-radius: 3px;
    border: 1px solid #4A515C;
    background: #15181C;
}

QCheckBox::indicator:hover {
    border-color: #5B91ED;
}

QCheckBox::indicator:checked {
    background: #2F6FEB;
    border-color: #4A88F5;
}

QScrollArea#InspectorScroll,
QGraphicsView#TrimSheetViewport {
    background: #121417;
    border: 1px solid #2B3038;
    border-radius: 7px;
}

QScrollBar:vertical {
    background: #181B20;
    width: 10px;
    margin: 2px;
    border-radius: 5px;
}

QScrollBar::handle:vertical {
    background: #3A414B;
    min-height: 28px;
    border-radius: 5px;
}

QScrollBar::handle:vertical:hover {
    background: #4B5563;
}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {
    background: none;
    border: none;
}

QSplitter::handle {
    background: #2A2F36;
}

QSplitter::handle:hover {
    background: #3F7DF5;
}

QToolTip {
    background: #252A31;
    color: #E7EAF0;
    border: 1px solid #414956;
    padding: 5px 7px;
}
"""
