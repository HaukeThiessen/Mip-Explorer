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


import ui_utilities

from PySide6.QtCore import *
from PySide6.QtWidgets import *
from settings import Settings

import matplotlib
matplotlib.use("QtAgg")
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from matplotlib.ticker import MaxNLocator


class ResultsViewer(QSplitter):
    update_forced             = Signal()
    texture_type_changed      = Signal(int)
    settings_window_requested = Signal()

    def __init__(self, *args, **kwargs):
        QSplitter.__init__(self)
        self.fg_color: str = args[0]
        bg_color: str = args[1]

        self.fig = Figure(
            figsize = (12, 5),
            dpi = 100,
            facecolor = "black" if ui_utilities.is_system_dark() else "white",
            layout = "tight",
            linewidth = 0,
        )
        matplotlib.rcParams["xtick.color"]      = self.fg_color
        matplotlib.rcParams["ytick.color"]      = self.fg_color
        matplotlib.rcParams["axes.labelcolor"]  = self.fg_color
        matplotlib.rcParams["axes.edgecolor"]   = self.fg_color
        matplotlib.rcParams["axes.facecolor"]   = bg_color

        self.plt_mips = self.fig.add_subplot(111)
        self.plt_mips.set_xlabel("Mips")
        self.plt_mips.set_ylabel("Information/Pixel")

        #Widgets
        self.btn_manual_update = QPushButton("🔃 R\u0332efresh")
        self.btn_manual_update.setToolTip("Re-calculates the graph for the currently selected texture")
        self.btn_manual_update.clicked.connect(self.update_forced.emit)

        self.cmb_texture_type = QComboBox()
        self.cmb_texture_type.addItems(["🎨 C\u0332olor", "📅 D\u0332ata", "🚦 Cha\u0332nnels", "⬆️ N\u0332ormal"])
        self.cmb_texture_type.setToolTip("🎨 Color:   When calculating the differences between mips, the color channels are weighted according to how sensible the human eye is to them.\n"
                                      "Use this for textures shown directly to the user, like base color or UI textures.\n"
                                      "\n"
                                      "📅 Data:    When calculating the differences between mips, the color channels are weighted equally.\n"
                                      "Use this for textures containing non-color information: Roughness, Metallic, AO, etc...\n"
                                      "\n"
                                      "🚦Channels: The differences are calculated for each channel individually.\n"
                                      "Use this for packed textures, to see the graph for each channel.\n"
                                      "\n"
                                      "⬆️ Normal:  Each mip is normalized, to prevent the normal vector from getting shorter.\n"
                                      "To calculate the difference, the dot product between the vectors is calculated\n"
                                      "Use this for (tangent space) normal maps")
        self.cmb_texture_type.currentIndexChanged.connect(self.texture_type_changed.emit)
        self.cmb_texture_type.setCurrentIndex(Settings.current_texture_type.value)

        self.btn_texture_type_settings = QPushButton("⚙️")
        self.btn_texture_type_settings.setToolTip(self.tr("Change the affixes to search for when setting the texture type.\n"
                                                          "Shortcut: S"))
        self.btn_texture_type_settings.setMinimumWidth(32)
        self.btn_texture_type_settings.setSizePolicy(QSizePolicy.Policy.Minimum,QSizePolicy.Policy.Minimum)
        self.btn_texture_type_settings.clicked.connect(self.settings_window_requested.emit)

        self.numbers_list = QLabel("             ")
        self.numbers_list.setToolTip("The average difference of each pixel to the matching pixel in the next mip.\n"
                                     "When calculating this number, the value range is scaled to 1-1000 instead of 0-1, purely to help readability.\n"
                                     "In a texture using 256 values per channel, the smallest possible difference between two non-identical pixels is 4.\n"
                                     "For non-normal textures, the unit for these values could be called kilo luminance")
        self.scrl_numbers_list = QScrollArea()
        self.scrl_numbers_list.setWidget(self.numbers_list)
        self.scrl_numbers_list.setWidgetResizable(True)
        self.scrl_numbers_list.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.scrl_numbers_list.setFrameStyle(QFrame.Shape.NoFrame)

        results_right_column = QWidget()
        lt_results_right_column = QVBoxLayout()

        lt_results_right_column.addWidget(self.btn_manual_update)
        lt_type_controls = QHBoxLayout()
        lt_type_controls.addWidget(self.cmb_texture_type, 5)
        lt_type_controls.addWidget(self.btn_texture_type_settings, 1)
        lt_results_right_column.addLayout(lt_type_controls)
        lt_results_right_column.addWidget(self.scrl_numbers_list)

        # Organizing widgets in layouts
        results_right_column.setLayout(lt_results_right_column)

        self.canvas = FigureCanvasQTAgg(self.fig)
        self.canvas.draw()
        self.canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.addWidget(self.canvas)
        self.addWidget(results_right_column)
        self.setSizes([1000, 150])
        self.setContentsMargins(0,0,0,10)

    def handle_update(self):
        self.canvas.draw()

    def update_plot(self, y_axis_values: list[list[float]] | list[float]):
        if y_axis_values.__len__() == 0:
            self.plt_mips.set_visible(False)
            return

        self.plt_mips.clear()
        if type(y_axis_values[0]) == list:
            new_grid = [[x[i] for x in y_axis_values] for i in range(len(y_axis_values[0]))] # type: ignore
            self.plt_mips.plot(new_grid[0], "red")
            self.plt_mips.plot(new_grid[1], "green")
            self.plt_mips.plot(new_grid[2], "blue")
            if new_grid.__len__() == 4:
                self.plt_mips.plot(new_grid[3], "gray")
        else:
            self.plt_mips.plot(y_axis_values, self.fg_color)

        self.plt_mips.yaxis.set_major_locator(MaxNLocator(integer = True))
        self.plt_mips.xaxis.set_major_locator(MaxNLocator(integer = True))
        self.plt_mips.set_visible(True)
        self.fig.set_visible(True)
        self.update_list(y_axis_values)
        self.handle_update()

    def update_list(self, y_axis_values: list[list[float]] | list[float]):
      if y_axis_values.__len__() == 0:
          self.numbers_list.setText("   -   ")
          return
      caption = "Information/Pixel:\n"
      if type(y_axis_values[0]) == list:
          for idx, value in enumerate(y_axis_values):
              caption += "  Mip " + "{:<5}".format(str(idx) + ", R: ") + "{:.1f}".format(value[0]) + "  \n" # type: ignore
              caption += "  Mip " + "{:<5}".format(str(idx) + ", G: ") + "{:.1f}".format(value[1]) + "  \n" # type: ignore
              caption += "  Mip " + "{:<5}".format(str(idx) + ", B: ") + "{:.1f}".format(value[2]) + "  \n" # type: ignore
              if(value.__len__() == 4): # type: ignore
                  caption += "  Mip " + "{:<5}".format(str(idx) + ", A: ") + "{:.1f}".format(value[3]) + "  \n\n" # type: ignore
              else:
                  caption +="\n"
      else:
          for idx, value in enumerate(y_axis_values):
              caption += "  Mip " + "{:<5}".format(str(idx) + ":") + "{:.1f}".format(value) + "  \n"
      self.numbers_list.setText(caption)