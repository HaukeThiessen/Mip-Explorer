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

from enum import Enum
from PySide6.QtCore import *
from PySide6.QtWidgets import *
from PySide6.QtGui import QPixmap, QIcon
from collections import OrderedDict

matplotlib.use("Qt5Agg")
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from matplotlib.ticker import MaxNLocator

if platform.system() == "Darwin":
    from Foundation import NSURL
else:
    import winreg

SUPPORTEDFORMATS = (
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
    "*.exr",
    "*.hdr",
    "*.pic",
)

CACHESIZE = 100

FILEBROWSER_PATH = os.path.join(os.getenv("WINDIR"), "explorer.exe")

allow_caching = True
selected_file = ""

dark_color = "#2B2B2B"
light_color = "#FFFAF0"


class WorkMode(Enum):
    COLOR = 0
    DATA = 1
    CHANNELS = 2
    MAX = 3


def calculate_deltas(filepath):
    try:
        img1 = cv2.imread(filepath)

        shorter_edge = min(img1.shape[0], img1.shape[1])
        loops = int(math.log2(shorter_edge))
        deltas = []
        for x in range(loops):
            smaller_mip = img1
            smaller_mip = cv2.resize(smaller_mip, (0, 0), fx=0.5, fy=0.5)
            smaller_mip = cv2.resize(smaller_mip, (0, 0), fx=2.0, fy=2.0)
            diff = cv2.absdiff(
                img1, smaller_mip
            )  # nested array with x entries, each containing y pixels with 3 channels
            diff_sum = np.sum(diff, axis=(0, 1))
            diff_sum = np.divide(diff_sum, (img1.shape[:2][0] * img1.shape[:2][1]))
            deltas.append(diff_sum.tolist())
            img1 = cv2.resize(img1, (0, 0), fx=0.5, fy=0.5)
        return deltas
    except:
        print("Failed to calculate deltas")


def try_getting_cached_results(filepath, cachepath):
    if not allow_caching:
        return
    try:
        with open(cachepath) as f:
            data = json.load(f)
        if filepath in data:
            last_time_modified = os.path.getmtime(filepath)
            cached_last_time_modified = data[filepath][1]
            if last_time_modified <= cached_last_time_modified:
                return data[filepath][0]
    except:
        pass


def save_cached_results(y_axis_values, filepath, cachepath):
    cache_entry = {filepath: (y_axis_values, os.path.getmtime(filepath))}

    dir_saved = os.path.dirname(Settings.settings_path)
    if not os.path.exists(dir_saved):
        try:
            os.mkdir(dir_saved)
        except:
            pass
    try:
        with open(cachepath, "r", encoding="utf-8") as file:
            file_data = OrderedDict(json.load(file))
            file_data.update(cache_entry)
    except:
        file_data = cache_entry

    if file_data.__len__() > CACHESIZE:
        file_data.popitem(False)
    try:
        with open(cachepath, "w", encoding="utf-8") as file:
            json.dump(file_data, file, ensure_ascii=False, indent=4)
    except:
        print("Failed to write cached results")


def update_plot(plot, y_axis_values):
    if y_axis_values.__len__() == 0:
        return
    plot.clear()
    if type(y_axis_values[0]) == list:
        new_grid = [[x[i] for x in y_axis_values] for i in range(len(y_axis_values[0]))]
        plot.plot(new_grid[0], "red")
        plot.plot(new_grid[1], "green")
        plot.plot(new_grid[2], "blue")
    else:
        plot.plot(y_axis_values, color_fg)


def update_list(list_widget, y_axis_values, work_mode):
    if y_axis_values.__len__() == 0:
        list_widget.setText("   -   ")
        return
    caption = ""
    if work_mode == 2:
        for idx, value in enumerate(y_axis_values):
            caption += "  Mip " + "{:<5}".format(str(idx) + ", R: ") + "{:.3f}".format(value[0]) + "  \n"
            caption += "  Mip " + "{:<5}".format(str(idx) + ", G: ") + "{:.3f}".format(value[1]) + "  \n"
            caption += "  Mip " + "{:<5}".format(str(idx) + ", B: ") + "{:.3f}".format(value[2]) + "  \n\n"
    else:
        for idx, value in enumerate(y_axis_values):
            caption += "  Mip " + "{:<5}".format(str(idx) + ":") + "{:.3f}".format(value) + "  \n"
    list_widget.setText(caption)


def get_plot_values(filepath, work_mode):
    cachepath = os.path.dirname(__file__) + "/Saved/CachedData.json"
    deltas = try_getting_cached_results(filepath, cachepath)
    if not deltas:
        deltas = calculate_deltas(filepath)
        save_cached_results(deltas, filepath, cachepath)
    channel_weights = (0.22, 0.72, 0.07) if work_mode == 0 else (0.333, 0.333, 0.333)
    if work_mode == 2:
        return deltas
    else:
        weighted_deltas = []
        for delta in deltas:
            weighted_deltas.append(
                delta[0] * channel_weights[0] + delta[1] * channel_weights[1] + delta[2] * channel_weights[2]
            )
    return weighted_deltas


def get_automatic_work_mode(filePath):
    base_name = os.path.splitext(os.path.basename(filePath))[0]
    if any(base_name.endswith(suffix) for suffix in Settings.data_suffixes):
        return WorkMode.DATA
    if any(base_name.endswith(suffix) for suffix in Settings.color_suffixes):
        return WorkMode.COLOR
    if any(base_name.endswith(suffix) for suffix in Settings.channels_suffixes):
        return WorkMode.CHANNELS
    return WorkMode.MAX


def is_system_dark():
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
        layout = QHBoxLayout(self)
        lbl_resolution = QLabel("Resolution:")
        lbl_resolution.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.lbl_res_value = QLabel("")
        lbl_size = QLabel("Size:")
        self.lbl_size_value = QLabel()
        lbl_size.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(lbl_resolution)
        layout.addWidget(self.lbl_res_value)
        layout.addWidget(lbl_size)
        layout.addWidget(self.lbl_size_value)

    def update_info(self, filepath, pixmap):
        self.lbl_res_value.setText(str(pixmap.size().height()) + " x " + str(pixmap.size().width()))
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


class FileExplorer(QWidget):
    file_changed = Signal()

    def __init__(self, *args, **kwargs):
        QWidget.__init__(self, *args, **kwargs)
        v_layout = QVBoxLayout(self)
        h_layout = QHBoxLayout()
        self.le_address = QLineEdit()
        self.tree_view = QTreeView()
        self.list_view = QListView()
        self.list_view.setMinimumWidth(150)
        self.tree_view.setMinimumWidth(200)
        h_layout.addWidget(self.tree_view)
        h_layout.addWidget(self.list_view)
        v_layout.addWidget(self.le_address)
        v_layout.addLayout(h_layout)
        path = QDir.rootPath()
        path = ""
        self.dir_model = QFileSystemModel()
        self.dir_model.setRootPath(path)
        self.dir_model.setFilter(QDir.NoDotAndDotDot | QDir.AllDirs)

        self.file_model = QFileSystemModel()
        self.file_model.setFilter(QDir.NoDotAndDotDot | QDir.Files | QDir.AllDirs)
        self.file_model.setNameFilters(SUPPORTEDFORMATS)
        self.tree_view.setModel(self.dir_model)
        self.tree_view.hideColumn(1)
        self.tree_view.hideColumn(2)
        self.tree_view.hideColumn(3)
        self.list_view.setModel(self.file_model)

        self.tree_view.setRootIndex(self.dir_model.index(path))
        self.list_view.setRootIndex(self.file_model.index(path))

        self.tree_view.clicked.connect(self.on_clicked)
        self.tree_view.selectionModel().currentChanged.connect(self.on_clicked)
        self.list_view.selectionModel().selectionChanged.connect(self.handle_selection_changed)
        self.list_view.doubleClicked.connect(self.open_current_directory)
        self.le_address.textEdited.connect(self.handle_address_changed)

    def open_current_directory(self, index):
        selected_file_path = self.list_view.model().filePath(self.list_view.selectedIndexes()[0])
        if os.path.isfile(selected_file_path):
            selected_file_path = os.path.normpath(selected_file_path)
            subprocess.run([FILEBROWSER_PATH, "/select,", selected_file_path])
        else:
            self.jump_to_path(selected_file_path)

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

    def jump_to_path(self, target_path):
        # TODO: Consistent behavior, select file if applicable and jump to correct location
        if os.path.isfile(target_path):
            self.list_view.setRootIndex(self.file_model.setRootPath(target_path))
            target_path = os.path.dirname(target_path)
        if os.path.isdir(target_path):
            self.tree_view.scrollTo(self.dir_model.index(target_path))
            self.tree_view.expand(self.dir_model.index(target_path))
            self.tree_view.setCurrentIndex(self.dir_model.index(target_path))
            self.le_address.setText(target_path)

    def get_current_file(self):
        return self.list_view.selectedIndexes()[0]


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
        layout = QFormLayout()

        lbl_data_prefixes = QLabel("Data")
        lbl_data_prefixes.setToolTip(
            self.tr(
                "Files using any of these suffixes are interpreted as data textures.\nWhen calculating the luminance differences between pixels, all channels have the same weight."
            )
        )
        self.le_data_prefixes = QLineEdit(", ".join(str(x) for x in Settings.data_suffixes))
        self.le_data_prefixes.setToolTip(
            self.tr("Separate suffixes with a comma. Whitespaces are removed automatically.")
        )

        lbl_color_prefixes = QLabel("Color")
        lbl_color_prefixes.setToolTip(
            self.tr(
                "Files using any of these suffixes are interpreted as color textures.\nWhen calculating the luminance differences between pixels, the green channel has the biggest impact."
            )
        )
        self.le_color_prefixes = QLineEdit(", ".join(str(x) for x in Settings.color_suffixes))
        self.le_color_prefixes.setToolTip(
            self.tr("Separate suffixes with a comma. Whitespaces are removed automatically.")
        )

        lbl_channels_prefixes = QLabel("Channels")
        lbl_channels_prefixes.setToolTip(
            self.tr(
                "Files using any of these suffixes are interpreted as packed textures.\nThe differences between the mip maps are calculated for each channel separately."
            )
        )
        self.le_channels_prefixes = QLineEdit(", ".join(str(x) for x in Settings.channels_suffixes))
        self.le_channels_prefixes.setToolTip(
            self.tr("Separate suffixes with a comma. Whitespaces are removed automatically.")
        )

        layout.addWidget(lbl_data_prefixes)
        layout.addWidget(self.le_data_prefixes)
        layout.addWidget(lbl_color_prefixes)
        layout.addWidget(self.le_color_prefixes)
        layout.addWidget(lbl_channels_prefixes)
        layout.addWidget(self.le_channels_prefixes)
        layout.addWidget(self.button_box)
        self.setLayout(layout)

    def clean_suffixes_list(self, suffixes):
        for suffix in suffixes:
            suffix.strip()
        return [suffix for suffix in suffixes if suffix != ""]

    def accept(self):
        Settings.data_suffixes = self.clean_suffixes_list(self.le_data_prefixes.text().split(","))
        Settings.color_suffixes = self.clean_suffixes_list(self.le_color_prefixes.text().split(","))
        Settings.channels_suffixes = self.clean_suffixes_list(self.le_channels_prefixes.text().split(","))
        Settings.save_settings()
        super().accept()


class Settings:
    color_suffixes = []
    data_suffixes = []
    channels_suffixes = []
    settings_path = os.path.dirname(__file__) + "/Saved/Settings.json"

    @staticmethod
    def load_settings():
        try:
            with open(Settings.settings_path) as f:
                data = json.load(f)
            if "colorSuffixes" in data:
                Settings.color_suffixes = data["colorSuffixes"]
            if "dataSuffixes" in data:
                Settings.data_suffixes = data["dataSuffixes"]
            if "channelsSuffixes" in data:
                Settings.channels_suffixes = data["channelsSuffixes"]
        except:
            print("Failed to load settings")
            pass

    @staticmethod
    def save_settings():
        dir_saved = os.path.dirname(Settings.settings_path)
        if not os.path.exists(dir_saved):
            try:
                os.mkdir(dir_saved)
            except:
                pass
        try:
            with open(Settings.settings_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "dataSuffixes": Settings.data_suffixes,
                        "colorSuffixes": Settings.color_suffixes,
                        "channelsSuffixes": Settings.channels_suffixes,
                    },
                    f,
                    ensure_ascii=False,
                    indent=4,
                )
        except:
            print("Failed to write settings to file")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        my_icon = QIcon()
        my_icon.addFile(app_icon)
        self.setWindowIcon(my_icon)
        self.setMinimumSize(700, 700)
        self.setWindowTitle("Mip Explorer")
        self.setAcceptDrops(True)

        self.fig = Figure(
            figsize=(12, 5),
            dpi=100,
            facecolor="black" if is_system_dark() else "white",
            layout="tight",
            linewidth=0,
        )
        matplotlib.rcParams["xtick.color"] = color_fg
        matplotlib.rcParams["ytick.color"] = color_fg
        matplotlib.rcParams["figure.edgecolor"] = "red"
        matplotlib.rcParams["axes.facecolor"] = bgColor
        matplotlib.rcParams["legend.facecolor"] = "green"
        matplotlib.rcParams["axes.titlecolor"] = "green"

        matplotlib.rcParams["axes.labelcolor"] = color_fg
        matplotlib.rcParams["axes.edgecolor"] = color_fg

        self.plt_mips = self.fig.add_subplot(111)
        self.plt_mips.set_xlabel("Mips")
        self.plt_mips.set_ylabel("Information")

        self.canvas = FigureCanvasQTAgg(self.fig)
        self.canvas.draw()

        # Widgets
        self.btn_manual_update = QPushButton("Refresh")
        self.cmb_work_mode = QComboBox()
        self.cmb_work_mode.addItems(["Color", "Data", "Channels"])
        self.cmb_work_mode.currentIndexChanged.connect(self.handle_update)
        self.btn_work_mode_settings = SquareButton("...")
        self.btn_work_mode_settings.setToolTip(self.tr("Change the suffixes to search for when setting the work mode"))
        self.btn_work_mode_settings.clicked.connect(self.open_work_mode_settings)
        self.btn_manual_update.clicked.connect(self.handle_update)
        self.lst_file_list = FileExplorer()
        self.lst_file_list.file_changed.connect(self.handle_file_changed)
        self.numbers_list_scroll = QScrollArea()
        self.numbers_list = QLabel("             ")
        self.numbers_list_scroll.setWidget(self.numbers_list)
        self.numbers_list_scroll.setWidgetResizable(True)

        self.texture_info = InfoPanel()
        self.lbl_preview = QLabel(self)
        self.lbl_preview.setScaledContents(True)
        self.lbl_preview.setFixedSize(300, 300)
        self.pixmap = QPixmap("")

        self.lbl_preview.setPixmap(self.pixmap)
        # Layouts
        main_layout = QHBoxLayout()
        file_explorer = QVBoxLayout()
        details_panel = QVBoxLayout()
        results_panel = QHBoxLayout()
        details_options = QHBoxLayout()

        # Organizing widgets in layouts
        results_panel.addWidget(self.canvas, 5)
        results_panel.addWidget(self.numbers_list_scroll, 1)
        details_panel.addLayout(results_panel)
        details_panel.addWidget(self.texture_info)
        details_panel.addWidget(self.lbl_preview)
        details_panel.addLayout(details_options)
        details_options.addWidget(self.btn_manual_update)
        details_options.addWidget(self.cmb_work_mode)
        details_options.addStretch(3)
        details_options.addWidget(self.btn_work_mode_settings)
        file_explorer.addWidget(self.lst_file_list)
        main_layout.addLayout(file_explorer, 2)
        main_layout.addLayout(details_panel, 10)

        file_explorer.setSizeConstraint(QLayout.SetMaximumSize)
        self.canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        file_explorer.sizeConstraint = 100

        widget = QWidget()
        widget.setLayout(main_layout)
        self.setCentralWidget(widget)

    def open_work_mode_settings(self):
        dialog = WorkModeSettingsDialog()
        dialog.exec()
        return

    def is_mip_mappable(self, pixmap):
        if pixmap.size().width() == 0 or pixmap.size().height() == 0:
            return False
        return (
            math.log(pixmap.size().width(), 2).is_integer()
            and math.log(pixmap.size().height(), 2).is_integer()
            and pixmap.size().width() > 3
            and pixmap.size().height() > 3
        )

    def handle_file_changed(self):
        automatic_work_mode = get_automatic_work_mode(selected_file)
        if not automatic_work_mode == WorkMode.MAX:
            print("set automatic work mode to " + str(automatic_work_mode))
            self.cmb_work_mode.setCurrentIndex(automatic_work_mode.value)
        self.handle_update()

    def handle_update(self):
        if not os.path.isfile(selected_file):
            return
        pixmap = QPixmap(selected_file)
        self.texture_info.update_info(selected_file, pixmap)
        if self.is_mip_mappable(pixmap):
            self.lbl_preview.setPixmap(pixmap)
            aspect_ratio = pixmap.size().width() / pixmap.size().height()
            if aspect_ratio < 1.0:
                self.lbl_preview.setFixedSize(300 * aspect_ratio, 300)
            else:
                self.lbl_preview.setFixedSize(300, 300 / aspect_ratio)
            work_mode = self.cmb_work_mode.currentIndex()
            y_axis_values = get_plot_values(selected_file, work_mode)
            update_plot(self.plt_mips, y_axis_values)
            self.plt_mips.set_xlabel("Mips")
            self.plt_mips.set_ylabel("Information per Pixel")
            self.plt_mips.yaxis.set_major_locator(MaxNLocator(integer=True))
            self.plt_mips.xaxis.set_major_locator(MaxNLocator(integer=True))
            self.plt_mips.set_visible(True)
            self.fig.set_visible(True)
            self.canvas.draw()
            update_list(self.numbers_list, y_axis_values, work_mode)
        else:
            update_plot(self.plt_mips, [])
            self.plt_mips.set_visible(False)
            self.canvas.draw()
            self.lbl_preview.setPixmap(QPixmap(""))

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
            self.lst_file_list.jump_to_path(self.fname)
        else:
            e.ignore()


if __name__ == "__main__":
    use_dark_mode = is_system_dark()
    bgColor = dark_color if use_dark_mode else light_color
    color_fg = light_color if use_dark_mode else dark_color
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
    window = MainWindow()
    window.show()

    app.exec()
