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


import sys
import math
import os
import matplotlib
import json
import numpy as np
import cv2
import platform
import subprocess
import glob
import csv
import datetime
import ctypes
import atexit
from pathlib import Path

from enum import Enum
from PySide6.QtCore import *
from PySide6.QtWidgets import *
from PySide6.QtGui import QPixmap, QIcon

matplotlib.use("Qt5Agg")
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from matplotlib.ticker import MaxNLocator

if platform.system() == "Darwin":
    # supposed to work on Mac OS, but didn't test this
    from Foundation import NSURL
else:
    import winreg

SUPPORTEDFORMATS = {
    "*.bmp",
    "*.dib",
    "*.jpeg",
    "*.jpg",
    "*.jpe",
    "*.jp2",
    "*.png",
    "*.webp",
    "*.pbm",
    "*.pgm",
    "*.ppm",
    "*.pxm",
    "*.pnm",
    "*.sr",
    "*.ras",
    "*.tiff",
    "*.tif",
    "*.pic",
    "*.csv",
}

CACHESIZE = 100

# The version of the cache generation method. Change this if you change the way the cache is generated, to ensure
# that the tool doesn't try to use outdated caches
CACHEVERSION: int = 3

FILEBROWSER_PATH: str = os.path.join(os.getenv("WINDIR"), "explorer.exe")

ALLOW_CACHING: bool = True
selected_file: str = ""

DARK_COLOR =  "#2B2B2B"
LIGHT_COLOR = "#FFFAF0"


class IconProvider(QFileIconProvider):
    """
    The default icons provided by the file system model were often mixed up, this icon provider returns the correct icons
    """
    def __init__(self) -> None:
        super().__init__()
        self.ICON_SIZE = QSize(64,64)
        self.ACCEPTED_FORMATS = (".jpg",".tiff",".png", ".webp", ".tga")
        self.cached_icons = {}

    def icon(self, type: QFileIconProvider.IconType):
        try:
            filename: str = type.filePath()
            if filename.casefold().endswith(self.ACCEPTED_FORMATS):
                if filename in self.cached_icons:
                    return self.cached_icons[filename]
                a = QPixmap(self.ICON_SIZE)
                a.load(filename)
                icon = QIcon(a)
                self.cached_icons.update({filename: icon})
                return icon
            else:
                return super().icon(type)
        except:
            return super().icon(type)


class WorkMode(Enum):
    COLOR = 0
    DATA = 1
    CHANNELS = 2
    NORMAL = 3
    MAX = 4


def normalize_RGB(vec):
    length = np.sqrt(vec[:,:,0]**2 + vec[:,:,1]**2 + vec[:,:,2]**2)
    length = np.clip(length, a_min=0.0001, a_max=10.0)
    vec[:,:,0] = vec[:,:,0] / length
    vec[:,:,1] = vec[:,:,1] / length
    vec[:,:,2] = vec[:,:,2] / length
    return vec


def calculate_deltas(filepath: str, b_all_mips: bool, b_normalize_mips: bool = False) -> list[list[float]]:
    try:
        current_mip = cv2.imread(filepath, cv2.IMREAD_UNCHANGED)
        current_mip = current_mip.astype(float) / 255
        if b_normalize_mips:
            current_mip = current_mip[:,:,:3]
            current_mip = current_mip - [0.5, 0.5, 0.0]
            current_mip = current_mip * [2.0, 2.0, 1.0]
            current_mip = normalize_RGB(current_mip)
        shorter_edge = min(current_mip.shape[0], current_mip.shape[1])
        loops: int = 1
        if b_all_mips:
            loops = int(math.log2(shorter_edge))
        deltas: list[list[float]] = []
        for x in range(loops):
            smaller_mip = current_mip
            smaller_mip = cv2.resize(smaller_mip, (0, 0), fx=0.5, fy=0.5)
            if b_normalize_mips:
                smaller_mip = normalize_RGB(smaller_mip)
            next_mip = smaller_mip
            smaller_mip = cv2.resize(smaller_mip, (0, 0), fx=2.0, fy=2.0)
            num_pixels = current_mip.__len__() * current_mip[0].__len__()
            if b_normalize_mips:
                dot_products = np.sum(current_mip * smaller_mip, axis=-1)
                diff_sum = np.sum(dot_products, axis = (0, 1))
                diff_sum = np.divide(diff_sum, num_pixels)
                diff_sum = 1.0 - diff_sum
                deltas.append(diff_sum)
            else:
                diff = cv2.absdiff(current_mip, smaller_mip) # nested array with x entries, each containing y pixels with 3-4 channels
                diff_sum = np.sum(diff, axis = (0, 1))
                diff_sum = np.divide(diff_sum, num_pixels)
                deltas.append(diff_sum.tolist())
            current_mip = next_mip
        return deltas
    except:
        print("Failed to calculate deltas for " + filepath)
        return [[0.0, 0.0, 0.0]]


def ensure_cache_version(cachepath: str):
    """
    Ensure the cache version and cache generation version match. If not, delete the cache
    """
    is_version_correct = True
    try:
        os.makedirs(os.path.dirname(cachepath), exist_ok = True)
    except:
        pass
    try:
        with open(cachepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        if "Version" in data:
            is_version_correct = CACHEVERSION == data["Version"]
        if not is_version_correct:
            try:
                print("Cache generation version changed. Deleting the cache..")
                os.remove(cachepath)
            except:
                pass
    except:
        pass


def get_results_category(work_mode: WorkMode):
    return "Results_Normal" if work_mode == WorkMode.NORMAL else "Results"


def try_getting_cached_results(filepath: str, cachepath: str) -> list[list[float]]:
    category: str = get_results_category
    if not ALLOW_CACHING:
        return
    try:
        with open(cachepath, "r", encoding="utf-8") as file:
            data = json.load(file)
        if category in data:
            if filepath in data[category]:
                last_time_modified = os.path.getmtime(filepath)
                cached_last_time_modified = data[category][filepath][1]
                if last_time_modified <= cached_last_time_modified:
                    return data[category][filepath][0]
    except:
        pass


def save_cached_results(y_axis_values: list[list[float]], filepath: str, cachepath: str, work_mode: WorkMode):
    category: str = get_results_category(work_mode)
    cache_entry = {filepath: (y_axis_values, os.path.getmtime(filepath))}
    output_file_path = Path(cachepath)
    if not output_file_path.exists:
        output_file_path.parent.mkdir(parents=True, exist_ok=True)
        output_file_path.write_text("")
    try:
        with open(cachepath, "r", encoding="utf-8") as file:
            try:
                data = json.load(file)
            except:
                data = dict()
            if category in data:
                data[category].update(cache_entry)
            else:
                cache = {category: cache_entry}
                data.update(cache)

            if data[category].__len__() > CACHESIZE:
                data[category].popitem(False)

            if "Version" in data:
                data["Version"] = CACHEVERSION
            else:
                data.update({"Version": CACHEVERSION})
        with open(cachepath, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=4)
    except:
        open(cachepath, 'a').close()


def update_plot(plot, y_axis_values: list[list[float]]):
    if y_axis_values.__len__() == 0:
        return
    plot.clear()
    if type(y_axis_values[0]) == list:
        new_grid = [[x[i] for x in y_axis_values] for i in range(len(y_axis_values[0]))]
        plot.plot(new_grid[0], "red")
        plot.plot(new_grid[1], "green")
        plot.plot(new_grid[2], "blue")
        if new_grid.__len__() == 4:
            plot.plot(new_grid[3], "gray")
    else:
        plot.plot(y_axis_values, fg_Color)


def update_list(list_widget: QLabel, y_axis_values: list[list[float]], work_mode: WorkMode):
    if y_axis_values.__len__() == 0:
        list_widget.setText("   -   ")
        return
    caption = "Information/Pixel:\n"
    if work_mode == WorkMode.CHANNELS and type(y_axis_values[0]) == list:
        for idx, value in enumerate(y_axis_values):
            caption += "  Mip " + "{:<5}".format(str(idx) + ", R: ") + "{:.3f}".format(value[0]) + "  \n"
            caption += "  Mip " + "{:<5}".format(str(idx) + ", G: ") + "{:.3f}".format(value[1]) + "  \n"
            caption += "  Mip " + "{:<5}".format(str(idx) + ", B: ") + "{:.3f}".format(value[2]) + "  \n"
            if(value.__len__() == 4):
                caption += "  Mip " + "{:<5}".format(str(idx) + ", A: ") + "{:.3f}".format(value[3]) + "  \n\n"
            else:
                caption +="\n"
    else:
        for idx, value in enumerate(y_axis_values):
            caption += "  Mip " + "{:<5}".format(str(idx) + ":") + "{:.3f}".format(value) + "  \n"
    list_widget.setText(caption)


def get_plot_values(filepath: str, work_mode: WorkMode, force_update: bool = False) -> list[list[float]]:
    deltas = []
    if not force_update:
        deltas = try_getting_cached_results(filepath, cachepath)
    if not deltas:
        deltas = calculate_deltas(filepath, True, work_mode == WorkMode.NORMAL)
        save_cached_results(deltas, filepath, cachepath, work_mode)
    return convert_deltas_to_plot_values(deltas, work_mode)


def convert_deltas_to_plot_values(deltas: list[list[float]], work_mode: WorkMode) -> list[list[float]] | list[float]:
    if work_mode == WorkMode.CHANNELS or type(deltas[0]) != list:
        return deltas

    has_alpha_channel = deltas[0].__len__() == 4

    if work_mode == WorkMode.NORMAL:
        angle_deltas: list[list[float]] = []
        for delta in deltas:
            angle_deltas.append(delta[2])
        return angle_deltas

    if has_alpha_channel:
        channel_weights = (0.165, 0.54, 0.052, 0.243) if work_mode == WorkMode.COLOR else (0.25, 0.25, 0.25, 0.25)
    else:
        channel_weights = (0.22, 0.72, 0.07) if work_mode == WorkMode.COLOR else (0.333, 0.333, 0.333)

    weighted_deltas: list[list[float]] = []
    for delta in deltas:
        if has_alpha_channel:
            weighted_deltas.append(
                delta[0] * channel_weights[0] +
                delta[1] * channel_weights[1] +
                delta[2] * channel_weights[2] +
                delta[3] * channel_weights[3]
            )
        else:
            weighted_deltas.append(
                delta[0] * channel_weights[0] +
                delta[1] * channel_weights[1] +
                delta[2] * channel_weights[2]
            )
    return weighted_deltas


def get_automatic_work_mode(filePath: str) -> WorkMode:
    if Settings.use_automatic_work_mode == False:
        return WorkMode.MAX

    base_name = os.path.splitext(os.path.basename(filePath))[0]
    if any(base_name.endswith(affix) for affix in Settings.color_affixes)     or any(base_name.startswith(affix) for affix in Settings.color_affixes):
        return WorkMode.COLOR
    if any(base_name.endswith(affix) for affix in Settings.data_affixes)      or any(base_name.startswith(affix) for affix in Settings.data_affixes):
        return WorkMode.DATA
    if any(base_name.endswith(affix) for affix in Settings.channels_affixes)  or any(base_name.startswith(affix) for affix in Settings.channels_affixes):
        return WorkMode.CHANNELS
    if any(base_name.endswith(affix) for affix in Settings.normal_affixes)    or any(base_name.startswith(affix) for affix in Settings.normal_affixes):
        return WorkMode.NORMAL
    return WorkMode.MAX


def is_system_dark() -> bool:
    if platform.system() == "Darwin":
        try:
            cmd = "defaults read -g AppleInterfaceStyle"
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
            return bool(p.communicate()[0])
        except Exception:
            return False
    else:
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, "Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize"
            )
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return value == 0
        except Exception as e:
            return False


class InfoPanel(QWidget):
    def __init__(self, *args, **kwargs):
        QWidget.__init__(self, *args, **kwargs)
        lt_main = QHBoxLayout(self)
        lt_main.setContentsMargins(0,0,0,0)
        lbl_resolution = QLabel("Resolution:")
        lbl_resolution.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.lbl_res_value = QLabel("")
        self.lbl_res_value.setAlignment(Qt.AlignmentFlag.AlignCenter)

        lbl_size = QLabel("Size:")
        lbl_size.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.lbl_size_value = QLabel()
        self.lbl_size_value.setAlignment(Qt.AlignmentFlag.AlignCenter)

        lt_main.addWidget(lbl_resolution)
        lt_main.addWidget(self.lbl_res_value)
        lt_main.addSpacing(15)
        lt_main.addWidget(lbl_size)
        lt_main.addWidget(self.lbl_size_value)

    def update_info(self, filepath, pixmap: QPixmap):
        res_value_caption = str(pixmap.size().height()) + " x " + str(pixmap.size().width())
        if not is_mip_mappable(pixmap):
            res_value_caption += " ⚠️ Not using powers of two"
        self.lbl_res_value.setText(res_value_caption)
        file_size = os.path.getsize(filepath)
        if file_size < 1048576:  # Smaller than 1 MB
            self.lbl_size_value.setText("{:.2f}".format(os.path.getsize(filepath) / 1024.0) + " KB")
        else:
            self.lbl_size_value.setText("{:.2f}".format(os.path.getsize(filepath) / 1024.0 / 1024) + " MB")

    def blank(self):
        self.lbl_res_value.setText("-")
        self.lbl_size_value.setText("-")


class SquareButton(QPushButton):
    def resize_event(self, event):
        super().resize_event(event)
        self.setMaximumWidth(min(self.width(), self.height()))


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
        QWidget.__init__(self, *args, **kwargs)
        self.texture_size = 300
        self.original_texture_size = [0,0]

        # Widgets
        self.lbl_preview = QLabel()
        self.lbl_preview.setFrameStyle(QFrame.Shape.Box)
        self.lbl_preview.setStyleSheet('background-color: ' + str(fg_Color))
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


class FileExplorer(QWidget):
    file_changed = Signal()
    scan_directory_label: str = "🗃️ Scan Directory"

    def __init__(self, *args, **kwargs):
        QWidget.__init__(self, *args, **kwargs)
        lt_vertical = QVBoxLayout(self)
        lt_vertical.setContentsMargins(0,0,0,0)
        lt_horizontal = QHBoxLayout()
        lt_list = QVBoxLayout()
        lt_list.setContentsMargins(0,0,0,0)
        lt_controls = QHBoxLayout()
        lt_search = QHBoxLayout()
        self.le_address = QLineEdit()
        self.tree_view = QTreeView()
        self.list_view = QListView()
        self.splitter = QSplitter()
        self.list_container = QWidget()
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Search Filenames")
        self.search_bar.textEdited.connect(self.handle_search_term_changed)
        lbl_search_caption = QLabel("🔍")
        self.cmb_icon_size = QComboBox()
        self.cmb_icon_size.addItems(["L\u0332ist", "M\u0332edium", "B\u0332ig"])
        self.cmb_icon_size.setToolTip("Icon Size")
        self.btn_batch = QPushButton(self.scan_directory_label)
        self.btn_batch.setToolTip("Calculates Mip 0's information density for all textures in this directory and sub-directories.\n"
                                  "Stores the sorted results in a csv file in the current directory.\n"
                                  "The work mode is determined automatically, and falls back to DATA if the mode can't be derived from the affix.")
        self.list_view.setMinimumWidth(15)
        self.tree_view.setMinimumWidth(15)
        self.splitter.setChildrenCollapsible(False)
        lt_horizontal.addWidget(self.splitter)
        self.splitter.addWidget(self.tree_view)
        self.splitter.addWidget(self.list_container)
        self.list_container.setLayout(lt_list)
        lt_list.addLayout(lt_search)
        lt_search.addWidget(lbl_search_caption)
        lt_search.addWidget(self.search_bar)
        lt_list.addWidget(self.list_view)
        lt_list.addLayout(lt_controls)
        lt_controls.addWidget(self.cmb_icon_size)
        lt_controls.addWidget(self.btn_batch)
        lt_vertical.addWidget(self.le_address)
        lt_vertical.addLayout(lt_horizontal)
        path = QDir.rootPath()
        path = ""

        self.dir_model = QFileSystemModel()
        self.dir_model.setRootPath(path)
        self.dir_model.setFilter(QDir.NoDotAndDotDot | QDir.AllDirs)

        self.file_model = QFileSystemModel()
        self.icon_provider = IconProvider()
        self.file_model.setIconProvider(self.icon_provider)
        self.file_model.setFilter(QDir.NoDotAndDotDot | QDir.Files | QDir.AllDirs)
        self.file_model.setNameFilters(SUPPORTEDFORMATS)
        self.file_model.setNameFilterDisables(False)

        self.tree_view.setModel(self.dir_model)
        self.tree_view.hideColumn(1)
        self.tree_view.hideColumn(2)
        self.tree_view.hideColumn(3)
        self.list_view.setModel(self.file_model)

        self.tree_view.setRootIndex(self.dir_model.index(path))
        self.list_view.setRootIndex(self.file_model.index(path))
        self.list_view.setResizeMode(QListView.ResizeMode.Adjust)

        self.tree_view.clicked.connect(self.on_clicked)
        self.tree_view.selectionModel().currentChanged.connect(self.on_clicked)
        self.list_view.selectionModel().selectionChanged.connect(self.handle_selection_changed)
        self.list_view.doubleClicked.connect(self.open_current_directory)
        self.le_address.textEdited.connect(self.handle_address_changed)
        self.cmb_icon_size.currentIndexChanged.connect(self.handle_icon_size_changed)
        self.btn_batch.clicked.connect(self.process_current_directory)

        if os.path.isdir(Settings.current_directory):
            self.jump_to_path(Settings.current_directory)

    def handle_search_term_changed(self):
            if self.search_bar.text() == "":
                self.file_model.setNameFilters(SUPPORTEDFORMATS)
            else:
                self.file_model.setNameFilters(["*" + self.search_bar.text() + "*"])

    def handle_icon_size_changed(self):
        current_index = self.cmb_icon_size.currentIndex()
        if current_index == 0:
            self.list_view.setViewMode(QListView.ViewMode.ListMode)
            self.list_view.setGridSize(QSize(-1, -1))
            self.list_view.setIconSize(QSize(-1, -1))
        else:
            sizes = [128, 256]
            new_size = sizes[current_index - 1]
            self.list_view.setViewMode(QListView.ViewMode.IconMode)
            self.list_view.setGridSize(QSize(new_size, new_size))
            self.list_view.setIconSize(QSize(new_size - 16, new_size - 16))
        QWidget.update(self.list_view)

    def process_current_directory(self):
        """
        Create a csv file with the Mip0 info stats of all files, sorted
        """
        self.btn_batch.setEnabled(False)
        self.btn_batch.setText("---")
        path = self.file_model.rootPath()
        files: list[str] = glob.glob(self.le_address.text() + "/**/*.tif", recursive=True)
        supportedEndings: list[str] = []
        for SupportedFormat in SUPPORTEDFORMATS:
            supportedEndings.append(SupportedFormat[1:])

        files = list(p.resolve() for p in Path(path).glob("**/*") if p.suffix in supportedEndings)
        results_table: list[list[float | str, str, str]] = []
        progress = QProgressDialog("", "Cancel", 0, len(files), self)
        progress.setWindowTitle("Processing Mips in \n" + path + "...")
        progress.setWindowModality(Qt.WindowModal)
        for i in range(0, len(files)):
            progress.setValue(i)
            pixmap = QPixmap(Path(files[i]))
            if is_mip_mappable(pixmap):
                deltas: list[list[float]] = calculate_deltas(files[i], False)
                work_mode = get_automatic_work_mode(files[i])
                if work_mode == WorkMode.MAX or work_mode == WorkMode.CHANNELS:
                    work_mode = WorkMode.DATA
                values: list[float] | list[list[float]] = convert_deltas_to_plot_values(deltas, work_mode)
                new_entry = [
                    values[0],
                    files[i].__str__(),
                    pixmap.width().__str__() + "x" + pixmap.height().__str__(),
                    pixmap.hasAlpha(),
                    work_mode.__str__()[9:]
                ]
                results_table.append(new_entry)
            progress.setValue(i)
            if progress.wasCanceled():
                break
        progress.setValue(len(files))
        results_table_sorted = sorted(results_table)
        for entry in results_table_sorted:
            entry[0] = "{:.3f}".format(entry[0])
        results_table_sorted.insert(0, ("Mip0 Information", "Filepath", "Dimensions", "has Alpha", "Mode"))
        time: str = datetime.datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
        try:
            with open(path + "\\MipStats_ " + time + ".csv", "w", newline="") as csvfile:
                writer = csv.writer(csvfile, quoting=csv.QUOTE_ALL)
                writer.writerows(results_table_sorted)
        except:
            print("Failed to write Scan Results to csv file.")
        app.alert(window)
        self.btn_batch.setText(self.scan_directory_label)
        self.btn_batch.setEnabled(True)

    def open_current_directory(self):
        selected_file_path = self.list_view.model().filePath(self.list_view.selectedIndexes()[0])
        if os.path.isfile(selected_file_path):
            selected_file_path = os.path.normpath(selected_file_path)
            subprocess.run([FILEBROWSER_PATH, "/select,", selected_file_path])
        else:
            self.jump_to_path(selected_file_path)

    def open_parent_directory(self):
        self.jump_to_path(str(Path(self.file_model.rootPath()).parent))

    def on_clicked(self, index):
        path = self.dir_model.fileInfo(index).absoluteFilePath()
        self.list_view.setRootIndex(self.file_model.setRootPath(path))
        self.le_address.setText(path)

    def handle_address_changed(self):
        if not os.path.exists(self.le_address.text()):
            return
        self.jump_to_path(self.le_address.text())

    def handle_selection_changed(self):
        global selected_file
        selected_file = self.list_view.model().filePath(self.list_view.selectedIndexes()[0])
        self.le_address.setText(selected_file)
        self.file_changed.emit()

    def jump_to_path(self, target_path: str):
        # TODO: Consistent behavior, select file if applicable and jump to correct location
        if os.path.isfile(target_path):
            self.list_view.setRootIndex(self.file_model.setRootPath(target_path))
            target_path = os.path.dirname(target_path)
        if os.path.isdir(target_path):
            self.le_address.setText(target_path)
            new_index = self.dir_model.index(target_path)
            self.tree_view.scrollTo(new_index)
            self.tree_view.expand(new_index)
            self.tree_view.setCurrentIndex(new_index)


class WorkModeSettingsDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Automatic Work Mode Settings")

        my_icon = QIcon()
        my_icon.addFile(settings_icon)
        self.setWindowIcon(my_icon)

        QBtn = QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.RestoreDefaults
        self.button_box = QDialogButtonBox(QBtn)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        lt_lists = QFormLayout()
        lt_main = QVBoxLayout()

        lbl_color_affixes = QLabel("🎨 Color Affixes: ")
        lbl_color_affixes.setToolTip(
            self.tr(
                "Files using any of these affixes are interpreted as color textures.\n"
                "When calculating the luminance differences between pixels, the green channel has the biggest impact."))

        self.le_color_affixes = QLineEdit(", ".join(str(x) for x in Settings.color_affixes))
        self.le_color_affixes.setToolTip(
            self.tr("Separate affixes with a comma. Whitespaces are removed automatically."))

        lbl_data_affixes = QLabel("📅 Data Affixes: ")
        lbl_data_affixes.setToolTip(
            self.tr("Files using any of these affixes are interpreted as data textures.\n"
                    "When calculating the luminance differences between pixels, all channels have the same weight."))

        self.le_data_affixes = QLineEdit(", ".join(str(x) for x in Settings.data_affixes))
        self.le_data_affixes.setToolTip(
            self.tr("Separate affixes with a comma. Whitespaces are removed automatically."))

        lbl_channels_affixes = QLabel("🚦 Channels Affixes: ")
        lbl_channels_affixes.setToolTip(
            self.tr("Files using any of these affixes are interpreted as packed textures.\n"
                    "The differences between the mip maps are calculated for each channel separately."))

        self.le_channels_affixes = QLineEdit(", ".join(str(x) for x in Settings.channels_affixes))
        self.le_channels_affixes.setToolTip(self.tr("Separate affixes with a comma. Whitespaces are removed automatically."))

        lbl_normal_affixes = QLabel("⬆️ Normal Affixes: ")
        lbl_normal_affixes.setToolTip(
            self.tr("Files using any of these affixes are interpreted as normal maps.\n"
                    "The vectors in each mip get normalized, and the z component is used for comparisons"))

        self.le_normal_affixes = QLineEdit(", ".join(str(x) for x in Settings.normal_affixes))
        self.le_normal_affixes.setToolTip(
            self.tr("Separate affixes with a comma. Whitespaces are removed automatically."))

        self.chk_automatic_work_mode = QCheckBox("Set work mode automatically")
        self.chk_automatic_work_mode.setChecked(Settings.use_automatic_work_mode)
        self.chk_automatic_work_mode.setToolTip(self.tr("Change the work mode if an affix is found in the file name"
                                                        "that matches one of the mode affixes defined in the settings"))

        lt_lists.addRow(lbl_color_affixes,    self.le_color_affixes)
        lt_lists.addRow(lbl_data_affixes,     self.le_data_affixes)
        lt_lists.addRow(lbl_channels_affixes, self.le_channels_affixes)
        lt_lists.addRow(lbl_normal_affixes,   self.le_normal_affixes)

        lt_main.addLayout(lt_lists)
        lt_main.addWidget(self.chk_automatic_work_mode)
        lt_main.addWidget(self.button_box)
        self.setLayout(lt_main)

    def clean_affixes_list(self, affixes: list[str]):
        for affix in affixes:
            affix.strip()
        return [affix for affix in affixes if affix != ""]

    def accept(self):
        Settings.color_affixes    = self.clean_affixes_list(self.le_color_affixes.text().split(","))
        Settings.data_affixes     = self.clean_affixes_list(self.le_data_affixes.text().split(","))
        Settings.channels_affixes = self.clean_affixes_list(self.le_channels_affixes.text().split(","))
        Settings.normal_affixes   = self.clean_affixes_list(self.le_normal_affixes.text().split(","))
        Settings.use_automatic_work_mode = self.chk_automatic_work_mode.isChecked()
        Settings.save_settings()
        super().accept()


class Settings:
    color_affixes:    list[str] = []
    data_affixes:     list[str] = []
    channels_affixes: list[str] = []
    normal_affixes:   list[str] = []
    use_automatic_work_mode = False

    current_directory = ""

    settings_path: str = os.path.dirname(__file__) + "\\Saved\\Settings.json"

    @staticmethod
    def load_settings():
        try:
            with open(Settings.settings_path) as f:
                data = json.load(f)
            if "color_affixes" in data:
                Settings.color_affixes = data["color_affixes"]
            if "data_affixes" in data:
                Settings.data_affixes = data["data_affixes"]
            if "channels_affixes" in data:
                Settings.channels_affixes = data["channels_affixes"]
            if "normal_affixes" in data:
                Settings.normal_affixes = data["normal_affixes"]
            if "use_automatic_work_mode" in data:
                Settings.use_automatic_work_mode = data["use_automatic_work_mode"]
            if "current_directory" in data:
                Settings.current_directory = data["current_directory"]
        except:
            print("No saved settings found. Using default settings")

    @staticmethod
    def save_settings():
        dir_saved = os.path.dirname(Settings.settings_path)
        if not os.path.exists(dir_saved):
            try:
                os.mkdir(dir_saved)
            except:
                print("Failed to create the Saved directory")
        try:
            with open(Settings.settings_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "color_affixes":          Settings.color_affixes,
                        "data_affixes":           Settings.data_affixes,
                        "channels_affixes":       Settings.channels_affixes,
                        "normal_affixes":         Settings.normal_affixes,
                        "use_automatic_work_mode":Settings.use_automatic_work_mode,
                        "current_directory":      Settings.current_directory
                    },
                    f,
                    ensure_ascii = False,
                    indent = 4,
                )
        except:
            print("Failed to write settings to file")


def is_mip_mappable(pixmap: QPixmap) -> bool:
    if pixmap.size().width() == 0 or pixmap.size().height() == 0:
        return False
    return (
        math.log(pixmap.size().width(), 2).is_integer()
        and math.log(pixmap.size().height(), 2).is_integer()
        and pixmap.size().width() > 3
        and pixmap.size().height() > 3
    )


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        my_icon = QIcon()
        my_icon.addFile(app_icon)
        self.setWindowIcon(my_icon)
        self.setWindowTitle("Mip Explorer")
        self.setAcceptDrops(True)

        self.fig = Figure(
            figsize = (12, 5),
            dpi = 100,
            facecolor = "black" if is_system_dark() else "white",
            layout = "tight",
            linewidth = 0,
        )
        matplotlib.rcParams["xtick.color"]      = fg_Color
        matplotlib.rcParams["ytick.color"]      = fg_Color
        matplotlib.rcParams["axes.labelcolor"]  = fg_Color
        matplotlib.rcParams["axes.edgecolor"]   = fg_Color
        matplotlib.rcParams["axes.facecolor"]   = bg_Color

        self.plt_mips = self.fig.add_subplot(111)
        self.plt_mips.set_xlabel("Mips")
        self.plt_mips.set_ylabel("Information/Pixel")

        self.canvas = FigureCanvasQTAgg(self.fig)
        self.canvas.draw()

        # Widgets
        self.btn_manual_update = QPushButton("🔃 R\u0332efresh")
        self.btn_manual_update.setToolTip("Re-calculates the graph for the currently selected texture")
        self.btn_manual_update.clicked.connect(self.force_update)
        self.cmb_work_mode = QComboBox()
        self.cmb_work_mode.addItems(["🎨 C\u0332olor", "📅 D\u0332ata", "🚦 Cha\u0332nnels", "⬆️ N\u0332ormal"])
        self.cmb_work_mode.setToolTip("🎨 Color:   When calculating the differences between mips, the color channels are weighted according to how sensible the human eye is to them.\n"
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
        self.cmb_work_mode.currentIndexChanged.connect(self.handle_update)
        self.btn_work_mode_settings = SquareButton("⚙️ S\u0332ettings")
        self.btn_work_mode_settings.setToolTip(self.tr("Change the affixes to search for when setting the work mode"))
        self.btn_work_mode_settings.clicked.connect(self.open_work_mode_settings)

        self.texture_info_panel = InfoPanel()
        self.file_explorer = FileExplorer()
        self.file_explorer.file_changed.connect(self.handle_file_changed)
        results_right_column = QWidget()
        self.scrl_numbers_list = QScrollArea()
        self.numbers_list = QLabel("             ")
        self.scrl_numbers_list.setWidget(self.numbers_list)
        self.scrl_numbers_list.setWidgetResizable(True)

        self.scrl_numbers_list.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.scrl_numbers_list.setFrameStyle(QFrame.Shape.NoFrame)

        self.texture_viewer = TextureViewer(self)

        splt_main = QSplitter()
        splt_details = QSplitter()
        splt_details.setOrientation(Qt.Orientation.Vertical)
        details_panel = QWidget()
        splt_results = QSplitter()

        # Layouts
        lt_main = QHBoxLayout()
        lt_results = QHBoxLayout()
        lt_results.setContentsMargins(0,0,0,0)
        lt_results_right_column = QVBoxLayout()
        lt_details_options = QHBoxLayout()
        lt_details = QVBoxLayout()
        lt_details.setContentsMargins(10,0,0,0)

        # Organizing widgets in layouts
        results_right_column.setLayout(lt_results_right_column)
        lt_results_right_column.addWidget(self.btn_manual_update)
        lt_results_right_column.addWidget(self.cmb_work_mode)
        lt_results_right_column.addWidget(self.scrl_numbers_list)
        splt_results.addWidget(self.canvas)
        splt_results.addWidget(results_right_column)
        splt_results.setSizes([1000, 150])

        splt_results.setContentsMargins(0,0,0,10)
        details_panel.setLayout(lt_details)

        lt_details.addWidget(splt_details)
        splt_details.addWidget(splt_results)
        splt_details.addWidget(self.texture_viewer)
        lt_details.addLayout(lt_details_options)

        lt_details_options.addWidget(self.texture_info_panel)
        lt_details_options.addStretch(1)
        lt_details_options.addWidget(self.btn_work_mode_settings)

        lt_main.addWidget(splt_main)
        splt_main.addWidget(self.file_explorer)
        splt_main.addWidget(details_panel)

        self.canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.installEventFilter(self)

        widget = QWidget()
        widget.setLayout(lt_main)
        self.setCentralWidget(widget)

    def eventFilter(self, widget, event):
        if event.type() == QEvent.KeyPress:
            key = event.key()
            if widget is self.file_explorer:
                if key == Qt.Key_Return or key == Qt.Key_Right:
                    self.file_explorer.open_current_directory()
                    return True
                if key == Qt.Key_Left:
                    self.file_explorer.open_parent_directory()
                    return True
            if key == Qt.Key_R:
                self.force_update()
                return True
            if key == Qt.Key_C:
                self.cmb_work_mode.setCurrentIndex(0)
                return True
            if key == Qt.Key_D:
                self.cmb_work_mode.setCurrentIndex(1)
                return True
            if key == Qt.Key_A:
                self.cmb_work_mode.setCurrentIndex(2)
                return True
            if key == Qt.Key_N:
                self.cmb_work_mode.setCurrentIndex(3)
                return True
            if key == Qt.Key_S:
                self.open_work_mode_settings()
            if key == Qt.Key_L:
                self.file_explorer.cmb_icon_size.setCurrentIndex(0)
            if key == Qt.Key_M:
                self.file_explorer.cmb_icon_size.setCurrentIndex(1)
            if key == Qt.Key_B:
                self.file_explorer.cmb_icon_size.setCurrentIndex(2)
            if key == Qt.Key_1:
                self.texture_viewer.set_original_size()
            if key == Qt.Key_0:
                self.texture_viewer.set_fit_size()
        return QWidget.eventFilter(self, widget, event)

    def open_work_mode_settings(self):
        dialog = WorkModeSettingsDialog()
        dialog.exec()
        return

    def handle_file_changed(self):
        automatic_work_mode = get_automatic_work_mode(selected_file)
        if not automatic_work_mode == WorkMode.MAX:
            self.cmb_work_mode.setCurrentIndex(automatic_work_mode.value)
        self.handle_update()
        self.setWindowTitle("Mip Explorer - " + os.path.basename(selected_file))

    def force_update(self):
        self.handle_update(True)

    def handle_update(self, force_update: bool = False):
        if not os.path.isfile(selected_file):
            return
        pixmap = QPixmap(selected_file)
        self.texture_info_panel.update_info(selected_file, pixmap)
        if is_mip_mappable(pixmap):
            self.texture_viewer.update_pixmap(pixmap)
            work_mode: WorkMode = WorkMode(self.cmb_work_mode.currentIndex())
            y_axis_values = get_plot_values(selected_file, work_mode, force_update)
            update_plot(self.plt_mips, y_axis_values)
            self.plt_mips.yaxis.set_major_locator(MaxNLocator(integer = True))
            self.plt_mips.xaxis.set_major_locator(MaxNLocator(integer = True))
            self.plt_mips.set_visible(True)
            self.fig.set_visible(True)
            self.canvas.draw()
            update_list(self.numbers_list, y_axis_values, work_mode)
        else:
            update_plot(self.plt_mips, [])
            self.plt_mips.set_visible(False)
            self.canvas.draw()
            self.texture_viewer.lbl_preview.setPixmap(QPixmap(""))

    # The following three methods set up dragging and dropping for the app
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls:
            e.accept()
        else:
            e.ignore()

    def dragMoveEvent(self, e):
        if e.mimeData().hasUrls:
            e.accept()
        else:
            e.ignore()

    def dropEvent(self, e):
        if e.mimeData().hasUrls:
            e.setDropAction(Qt.CopyAction)
            e.accept()
            # Workaround for OSx dragging and dropping
            for url in e.mimeData().urls():
                if platform.system() == "Darwin":
                    fname = str(NSURL.URLWithString_(str(url.toString())).filePathURL().path())
                else:
                    fname = str(url.toLocalFile())
            self.fname = fname
            self.file_explorer.jump_to_path(self.fname)
        else:
            e.ignore()


def exit_handler():
    Settings.current_directory = window.file_explorer.file_model.rootPath()
    Settings.save_settings()


if __name__ == "__main__":
    cachepath = os.path.dirname(__file__) + "/Saved/CachedData.json"
    if ALLOW_CACHING:
        ensure_cache_version(cachepath)
    use_dark_mode = is_system_dark()
    bg_Color = DARK_COLOR if use_dark_mode else LIGHT_COLOR
    fg_Color = LIGHT_COLOR if use_dark_mode else DARK_COLOR
    dir_path = os.path.dirname(os.path.realpath(__file__))
    app_icon = (
        dir_path + "\\Resources\\AppIcon_Light.png" if use_dark_mode else dir_path + "\\Resources\\AppIcon_Dark.png"
    )
    settings_icon = (
        dir_path + "\\Resources\\SettingsIcon_Light.png"
        if use_dark_mode
        else dir_path + "\\Resources\\SettingsIcon_Dark.png"
    )

    Settings.load_settings()

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # Taskbar Icon
    app_ID: str = 'MipExplorer'
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_ID)
    app.setWindowIcon(QIcon(app_icon))

    window = MainWindow()

    window.show()
    atexit.register(exit_handler)

    app.exec()