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
    "*.exr",
    "*.hdr",
    "*.pic",
    "*.csv",
}

CACHESIZE = 100

# The version of the cache generation method. Change this if you change the way the cache is generated, to ensure
# that the tool doesn't try to use outdated caches
CACHEVERSION: int = 2

FILEBROWSER_PATH: str = os.path.join(os.getenv("WINDIR"), "explorer.exe")

allow_caching: bool = True
selected_file: str = ""

dark_color = "#2B2B2B"
light_color = "#FFFAF0"


class WorkMode(Enum):
    COLOR = 0
    DATA = 1
    CHANNELS = 2
    MAX = 3


def calculate_deltas(filepath: str, b_all_mips: bool) -> list[list[float]]:
    try:
        current_mip = cv2.imread(filepath, cv2.IMREAD_UNCHANGED)

        shorter_edge = min(current_mip.shape[0], current_mip.shape[1])
        loops: int = 1
        if b_all_mips:
            loops = int(math.log2(shorter_edge))
        deltas: list[list[float]] = []
        for x in range(loops):
            smaller_mip = current_mip
            smaller_mip = cv2.resize(smaller_mip, (0, 0), fx=0.5, fy=0.5)
            smaller_mip = cv2.resize(smaller_mip, (0, 0), fx=2.0, fy=2.0)
            diff = cv2.absdiff(
                current_mip, smaller_mip
            )  # nested array with x entries, each containing y pixels with 3-4 channels
            diff_sum = np.sum(diff, axis = (0, 1))
            diff_sum = np.divide(diff_sum, (current_mip.shape[:2][0] * current_mip.shape[:2][1]))
            deltas.append(diff_sum.tolist())
            current_mip = cv2.resize(current_mip, (0, 0), fx=0.5, fy=0.5)
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
        print("Failed to find the cache file")
    open(cachepath, 'a').close()



def try_getting_cached_results(filepath: str, cachepath: str) -> list[list[float]]:
    if not allow_caching:
        return
    try:
        with open(cachepath, "r", encoding="utf-8") as file:
            data = json.load(file)
        if "Results" in data:
            if filepath in data["Results"]:
                last_time_modified = os.path.getmtime(filepath)
                cached_last_time_modified = data["Results"][filepath][1]
                if last_time_modified <= cached_last_time_modified:
                    return data["Results"][filepath][0]
    except:
        print("No cached results found")


def save_cached_results(y_axis_values: list[list[float]], filepath: str, cachepath: str):
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
            if "Results" in data:
                data["Results"].update(cache_entry)
            else:
                cache = {"Results": cache_entry}
                data.update(cache)

            if data["Results"].__len__() > CACHESIZE:
                data["Results"].popitem(False)

            if "Version" in data:
                data["Version"] = CACHEVERSION
            else:
                data.update({"Version": CACHEVERSION})
        with open(cachepath, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=4)
    except:
        print("Failed to write cached results")


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
        plot.plot(y_axis_values, color_fg)


def update_list(list_widget, y_axis_values: list[list[float]], work_mode: WorkMode):
    if y_axis_values.__len__() == 0:
        list_widget.setText("   -   ")
        return
    caption = ""
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


def get_plot_values(filepath: str, work_mode: WorkMode) -> list[list[float]]:
    deltas = try_getting_cached_results(filepath, cachepath)
    if not deltas:
        deltas = calculate_deltas(filepath, True)
        save_cached_results(deltas, filepath, cachepath)
    return convert_deltas_to_plot_values(deltas, work_mode)


def convert_deltas_to_plot_values(deltas: list[list[float]], work_mode: WorkMode) -> list[list[float]] | list[float]:
    if work_mode == WorkMode.CHANNELS or type(deltas[0]) != list:
        return deltas
    else:
      has_alpha_channel = deltas[0].__len__() == 4
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
    base_name = os.path.splitext(os.path.basename(filePath))[0]
    if any(base_name.endswith(suffix) for suffix in Settings.data_suffixes):
        return WorkMode.DATA
    if any(base_name.endswith(suffix) for suffix in Settings.color_suffixes):
        return WorkMode.COLOR
    if any(base_name.endswith(suffix) for suffix in Settings.channels_suffixes):
        return WorkMode.CHANNELS
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
        layout = QHBoxLayout(self)
        lbl_resolution = QLabel("Resolution:")
        lbl_resolution.setAlignment(Qt.AlignmentFlag.AlignRight)

        self.lbl_res_value = QLabel("")
        self.lbl_res_value.setAlignment(Qt.AlignmentFlag.AlignLeft)

        lbl_size = QLabel("Size:")
        lbl_size.setAlignment(Qt.AlignmentFlag.AlignRight)

        self.lbl_size_value = QLabel()
        self.lbl_size_value.setAlignment(Qt.AlignmentFlag.AlignLeft)

        layout.addWidget(lbl_resolution)
        layout.addWidget(self.lbl_res_value)
        layout.addWidget(lbl_size)
        layout.addWidget(self.lbl_size_value)

    def update_info(self, filepath, pixmap: QPixmap):
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
    scan_directory_label: str = "🗃️ Scan Directory"

    def __init__(self, *args, **kwargs):
        QWidget.__init__(self, *args, **kwargs)
        v_layout = QVBoxLayout(self)
        h_layout = QHBoxLayout()
        lt_list = QVBoxLayout()
        self.le_address = QLineEdit()
        self.tree_view = QTreeView()
        self.list_view = QListView()
        self.splitter = QSplitter()
        self.list_container = QWidget()
        self.btn_batch = QPushButton(self.scan_directory_label)
        self.btn_batch.setToolTip("Calculates Mip0's information density for all textures in this directory and sub-directories.\n"
                                  "Stores the sorted results in a csv file.\n"
                                  "The Work mode is set to color for now, regardless of suffix.")
        self.list_view.setMinimumWidth(150)
        self.tree_view.setMinimumWidth(200)
        self.splitter.setChildrenCollapsible(False)
        h_layout.addWidget(self.splitter)
        self.splitter.addWidget(self.tree_view)
        self.splitter.addWidget(self.list_container)
        self.list_container.setLayout(lt_list)
        lt_list.addWidget(self.list_view)
        lt_list.addWidget(self.btn_batch)
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
        self.btn_batch.clicked.connect(self.process_current_directory)

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
                values: list[float] | list[list[float]] = convert_deltas_to_plot_values(deltas, WorkMode.DATA)
                new_entry = [
                    values[0],
                    files[i].__str__(),
                    pixmap.width().__str__() + "x" + pixmap.height().__str__(),
                    pixmap.hasAlpha()
                ]
                results_table.append(new_entry)
            progress.setValue(i)
            if progress.wasCanceled():
                break
        progress.setValue(len(files))
        results_table_sorted = sorted(results_table)
        for entry in results_table_sorted:
            entry[0] = "{:.2f}".format(entry[0])
        results_table_sorted.insert(0, ("Mip0 Information", "Filepath", "Dimensions", "has Alpha"))
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

    def clean_suffixes_list(self, suffixes: list[str]):
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
    color_suffixes: list[str] = []
    data_suffixes: list[str] = []
    channels_suffixes: list[str] = []
    settings_path: str = os.path.dirname(__file__) + "\\Saved\\Settings.json"

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
        self.btn_manual_update = QPushButton("🔃 Refresh")
        self.cmb_work_mode = QComboBox()
        self.cmb_work_mode.addItems(["🎨 Color", "📅 Data", "🚦 Channels"])
        self.cmb_work_mode.currentIndexChanged.connect(self.handle_update)
        self.btn_work_mode_settings = SquareButton("⚙️ Settings")
        self.btn_work_mode_settings.setToolTip(self.tr("Change the suffixes to search for when setting the work mode"))
        self.btn_work_mode_settings.clicked.connect(self.open_work_mode_settings)
        self.btn_manual_update.clicked.connect(self.handle_update)
        self.file_explorer = FileExplorer()
        self.file_explorer.file_changed.connect(self.handle_file_changed)
        self.scrl_numbers_list = QScrollArea()
        self.numbers_list = QLabel("             ")
        self.scrl_numbers_list.setWidget(self.numbers_list)
        self.scrl_numbers_list.setWidgetResizable(True)

        self.texture_info = InfoPanel()

        self.lbl_preview = QLabel(self)
        self.lbl_preview.setScaledContents(True)
        self.lbl_preview.setFixedSize(300, 300)
        self.pixmap = QPixmap("")

        self.lbl_preview.setPixmap(self.pixmap)
        splitter = QSplitter()
        results_panel = QWidget()
        details_panel = QWidget()
        self.scrl_preview = QScrollArea()

        # Layouts
        lt_main = QHBoxLayout()
        lt_results = QHBoxLayout()
        lt_details_options = QHBoxLayout()
        lt_details = QVBoxLayout()

        # Organizing widgets in layouts
        lt_results.addWidget(self.canvas, 5)
        lt_results.addWidget(self.scrl_numbers_list, 1)
        results_panel.setLayout(lt_results)

        self.scrl_preview.setWidget(self.lbl_preview)
        self.scrl_preview.setWidgetResizable(True)
        details_panel.setLayout(lt_details)

        lt_details.addWidget(results_panel)
        lt_details.addWidget(self.texture_info)
        lt_details.addWidget(self.scrl_preview)
        lt_details.addLayout(lt_details_options)

        lt_details_options.addWidget(self.btn_manual_update)
        lt_details_options.addWidget(self.cmb_work_mode)
        lt_details_options.addStretch(3)
        lt_details_options.addWidget(self.btn_work_mode_settings)

        lt_main.addWidget(splitter)
        splitter.addWidget(self.file_explorer)
        splitter.addWidget(details_panel)

        self.canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.file_explorer.installEventFilter(self)

        widget = QWidget()
        widget.setLayout(lt_main)
        self.setCentralWidget(widget)

    def eventFilter(self, widget, event):
        if (event.type() == QEvent.KeyPress and
            widget is self.file_explorer):
            key = event.key()
            if key == Qt.Key_Return or key == Qt.Key_Right:
                self.file_explorer.open_current_directory()
                return True
            if key == Qt.Key_Left:
                self.file_explorer.open_parent_directory()
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

    def handle_update(self):
        if not os.path.isfile(selected_file):
            return
        pixmap = QPixmap(selected_file)
        self.texture_info.update_info(selected_file, pixmap)
        if is_mip_mappable(pixmap):
            self.lbl_preview.setPixmap(pixmap)
            aspect_ratio: float = pixmap.size().width() / pixmap.size().height()
            if aspect_ratio < 1.0:
                self.lbl_preview.setFixedSize(300 * aspect_ratio, 300)
            else:
                self.lbl_preview.setFixedSize(300, 300 / aspect_ratio)
            work_mode: WorkMode = WorkMode(self.cmb_work_mode.currentIndex())
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
            self.file_explorer.jump_to_path(self.fname)
        else:
            e.ignore()


if __name__ == "__main__":
    cachepath = os.path.dirname(__file__) + "/Saved/CachedData.json"
    if allow_caching:
        ensure_cache_version(cachepath)
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

    # Taskbar Icon
    app_ID: str = 'MipExplorer'
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_ID)
    app.setWindowIcon(QIcon(app_icon))

    window = MainWindow()

    window.show()
    app.exec()