# Mip Explorer
#  Copyright (c) Hauke Thiessen
#
#  ---------------------------------------------------------------------------
#
#  This software is provided 'as-is', without any express or implied
#  warranty. In no event will the authors be held liable for any damages
#  arising from the use of this software.
#
#  Permission is granted to anyone to use this software for any purpose,
#  including commercial applications, and to alter it and redistribute it
#  freely, subject to the following restrictions:
#
#  1. The origin of this software must not be misrepresented; you must not
#     claim that you wrote the original software. If you use this software
#     in a product, an acknowledgment in the documentation is be
#     appreciated but not required.
#
#  2. Altered versions must be plainly marked as such, and must not be
#     misrepresented as being the original software.
#
#  3. This notice may not be removed or altered from any source distribution.
#
#  ---------------------------------------------------------------------------


from PySide6.QtCore import *
from PySide6.QtWidgets import *
from PySide6.QtGui import QPixmap


class simple_scroller(QScrollArea):
    """
    A scroll bar that doesn't react to the mouse wheel being used
    """
    def __init__(self):
        QScrollArea.__init__(self)

    def wheelEvent(self, ev):
        if ev.type() == QEvent.Wheel:
            ev.ignore()


class TextureViewer(QWidget):
    def __init__(self, *args, **kwargs):
        fg_color: str = args[0]
        QWidget.__init__(self)
        self.texture_size = 300
        self.original_texture_size = [0,0]

        # Widgets
        self.lbl_preview = QLabel()
        self.lbl_preview.setFrameStyle(QFrame.Shape.Box)
        self.lbl_preview.setStyleSheet('background-color: ' + fg_color)
        self.lbl_preview.setScaledContents(True)
        self.lbl_preview.setFixedSize(self.texture_size, self.texture_size)

        self.scrl_preview = simple_scroller()
        self.scrl_preview.setWidget(self.lbl_preview)
        self.scrl_preview.setWidgetResizable(True)
        self.scrl_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.sldr_size = QSlider()
        self.sldr_size.setMinimum(100)
        self.sldr_size.setMaximum(1000)
        self.sldr_size.setPageStep(90)
        self.sldr_size.setValue(300)
        self.sldr_size.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.sldr_size.valueChanged.connect(self.handle_size_changed)

        self.btn_original_size = QPushButton("🟰")
        self.btn_original_size.setMaximumWidth(24)
        self.btn_original_size.setToolTip("Displays the texture at its original size"
                                          "\nShortcut key: 1")
        self.btn_original_size.clicked.connect(self.set_original_size)

        self.btn_fill_size = QPushButton("↔️")
        self.btn_fill_size.setMaximumWidth(24)
        self.btn_fill_size.setToolTip("Displays the texture at a size that fills the available space")
        self.btn_fill_size.clicked.connect(self.set_fill_size)

        self.btn_fit_size = QPushButton("↕️")
        self.btn_fit_size.setMaximumWidth(24)
        self.btn_fit_size.setToolTip("Displays the texture at a size that it fits completely into the available space"
                                     "\nShortcut key: 0")
        self.btn_fit_size.clicked.connect(self.set_fit_size)

        # Layouts
        lt_main = QHBoxLayout(self)
        lt_main.setContentsMargins(0,0,0,0)
        lt_size_controls = QVBoxLayout()

        # Organize widgets in layouts
        lt_main.addLayout(lt_size_controls)
        lt_main.addWidget(self.scrl_preview)
        lt_size_controls.addWidget(self.sldr_size,alignment = Qt.AlignmentFlag.AlignHCenter)
        lt_size_controls.addWidget(self.btn_original_size)
        lt_size_controls.addWidget(self.btn_fill_size)
        lt_size_controls.addWidget(self.btn_fit_size)

        self.pixmap = QPixmap("")
        self.lbl_preview.setPixmap(self.pixmap)

    def update_pixmap(self, pixmap: QPixmap):
        self.pixmap = pixmap
        self.original_texture_size = [pixmap.size().width(), pixmap.size().height()]
        self.lbl_preview.setPixmap(pixmap)
        self.update_texture_view()

    def handle_size_changed(self):
        self.texture_size = self.sldr_size.value()
        self.update_texture_view()
        return

    def set_fill_size(self):
        max_size = self.scrl_preview.width() if self.scrl_preview.width() > self.scrl_preview.height() else self.scrl_preview.height()
        max_size -= self.scrl_preview.verticalScrollBar().width() + 2
        if self.sldr_size.maximum() < max_size:
            self.sldr_size.setMaximum(max_size)

        if self.sldr_size.minimum() > max_size:
            self.sldr_size.setMinimum(max_size)

        self.sldr_size.setValue(max_size)
        self.handle_size_changed()

    def set_fit_size(self):
        if self.original_texture_size[1] == 0:
            return
        min_size = self.scrl_preview.width() if self.scrl_preview.width() < self.scrl_preview.height() else self.scrl_preview.height()
        min_size -= 2
        aspect_ratio = float(self.original_texture_size[0]) / float(self.original_texture_size[1])
        min_size = int(min_size * aspect_ratio)

        if self.sldr_size.maximum() < min_size:
            self.sldr_size.setMaximum(min_size)

        if self.sldr_size.minimum() > min_size:
            self.sldr_size.setMinimum(min_size)

        self.sldr_size.setValue(min_size)
        self.handle_size_changed()

    def set_original_size(self):
          max_dimension = self.original_texture_size[0] if self.original_texture_size[0] > self.original_texture_size[1] else self.original_texture_size[1]
          if self.sldr_size.maximum() < max_dimension:
              self.sldr_size.setMaximum(max_dimension)

          if self.sldr_size.minimum() > max_dimension:
              self.sldr_size.setMinimum(max_dimension)

          self.sldr_size.setValue(max_dimension)
          self.handle_size_changed()

    def wheelEvent(self, event: QEvent):
        numDegrees: QPoint = event.angleDelta() / 8
        self.sldr_size.setValue(self.sldr_size.value() + (numDegrees.y() * 2))
        self.handle_size_changed()
        event.accept()

    def update_texture_view(self):
        if self.lbl_preview.pixmap():
            pixmap = self.lbl_preview.pixmap()
            aspect_ratio: float = pixmap.size().width() / pixmap.size().height()
            self.lbl_preview.setFixedSize(self.texture_size, self.texture_size / aspect_ratio)
            return