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

import atexit
import ctypes
import json
import os
import platform
import sys

from pathlib import Path

from PySide6.QtCore import *
from PySide6.QtWidgets import *
from PySide6.QtGui import QPixmap, QIcon

import core
import ui_utilities

from browser import FileBrowser
from resultsviewer import ResultsViewer
from settings import Settings
from textureviewer import TextureViewer


if platform.system() == "Darwin":
    # supposed to work on Mac OS, but didn't test this
    from Foundation import NSURL
else:
    import winreg

CACHESIZE = 100

# The version of the cache generation method. Change this if you change the way the cache is generated, to ensure
# that the tool doesn't try to use outdated caches
CACHEVERSION: int = 4

ALLOW_CACHING: bool = True

DARK_COLOR  = "#2B2B2B"
LIGHT_COLOR = "#FFFAF0"


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


def get_results_category(texture_type: core.TextureType):
    return "Results_Normal" if texture_type == core.TextureType.NORMAL else "Results"


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


def save_cached_results(y_axis_values: list[list[float]], filepath: str, cachepath: str, texture_type: core.TextureType):
    category: str = get_results_category(texture_type)
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


def get_plot_values(filepath: str, texture_type: core.TextureType, force_update: bool = False) -> list[list[float]]:
    raw_deltas = []
    if not force_update:
        raw_deltas = try_getting_cached_results(filepath, cachepath)
    if not raw_deltas:
        raw_deltas = core.calculate_raw_deltas(filepath, True, texture_type == core.TextureType.NORMAL)
        save_cached_results(raw_deltas, filepath, cachepath, texture_type)
    return core.interpret_deltas(raw_deltas, texture_type)


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
        if not core.is_mip_mappable(pixmap.size().width(), pixmap.size().height()):
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


class TextureTypeSettingsDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Automatic texture type Settings")

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

        self.chk_automatic_texture_type = QCheckBox("Set texture type automatically")
        self.chk_automatic_texture_type.setChecked(Settings.use_automatic_texture_type)
        self.chk_automatic_texture_type.setToolTip(self.tr("Change the texture type if an affix is found in the file name"
                                                        "that matches one of the mode affixes defined in the settings"))
        self.chk_automatic_texture_type.checkStateChanged.connect(self.adjust_form_availability)

        lt_lists.addRow(lbl_color_affixes,    self.le_color_affixes)
        lt_lists.addRow(lbl_data_affixes,     self.le_data_affixes)
        lt_lists.addRow(lbl_channels_affixes, self.le_channels_affixes)
        lt_lists.addRow(lbl_normal_affixes,   self.le_normal_affixes)

        lt_main.addLayout(lt_lists)
        lt_main.addWidget(self.chk_automatic_texture_type)
        lt_main.addWidget(self.button_box)
        self.setLayout(lt_main)
        self.adjust_form_availability()

    def clean_affixes_list(self, affixes: list[str]):
        for affix in affixes:
            affix.strip()
        return [affix for affix in affixes if affix != ""]

    def accept(self):
        Settings.color_affixes    = self.clean_affixes_list(self.le_color_affixes.text().split(","))
        Settings.data_affixes     = self.clean_affixes_list(self.le_data_affixes.text().split(","))
        Settings.channels_affixes = self.clean_affixes_list(self.le_channels_affixes.text().split(","))
        Settings.normal_affixes   = self.clean_affixes_list(self.le_normal_affixes.text().split(","))
        Settings.use_automatic_texture_type = self.chk_automatic_texture_type.isChecked()
        Settings.save_settings()
        super().accept()

    def adjust_form_availability(self):
        is_available = self.chk_automatic_texture_type.isChecked()
        self.le_color_affixes.setEnabled(is_available)
        self.le_data_affixes.setEnabled(is_available)
        self.le_channels_affixes.setEnabled(is_available)
        self.le_normal_affixes.setEnabled(is_available)
        self.update()


class MainWindow(QMainWindow):
    file_browser: FileBrowser = []

    def __init__(self):
        super().__init__()
        my_icon = QIcon()
        my_icon.addFile(app_icon)
        self.setWindowIcon(my_icon)
        self.setWindowTitle("Mip Explorer")
        self.setAcceptDrops(True)

        # Widgets
        self.texture_info_panel = InfoPanel()
        self.file_browser = FileBrowser()
        if os.path.isdir(Settings.current_directory):
            self.file_browser.jump_to_path(Settings.current_directory)
        self.file_browser.file_selection_changed.connect(self.handle_file_changed)
        self.file_browser.needs_attention.connect(self.alert)

        self.texture_viewer = TextureViewer(fg_color)

        splt_main = QSplitter()
        splt_details = QSplitter()
        splt_details.setOrientation(Qt.Orientation.Vertical)
        details_panel = QWidget()
        self.results_viewer = ResultsViewer(fg_color, bg_color)

        self.results_viewer.update_forced.connect(self.force_update)
        self.results_viewer.texture_type_changed.connect(self.handle_update)
        self.results_viewer.settings_window_requested.connect(self.open_texture_type_settings)

        # Layouts
        lt_main = QHBoxLayout()
        lt_details_options = QHBoxLayout()
        lt_details = QVBoxLayout()
        lt_details.setContentsMargins(10,0,0,0)

        # Organizing widgets in layouts
        details_panel.setLayout(lt_details)

        lt_details.addWidget(splt_details)
        splt_details.addWidget(self.results_viewer)
        splt_details.addWidget(self.texture_viewer)
        lt_details.addLayout(lt_details_options)

        lt_details_options.addWidget(self.texture_info_panel)
        lt_details_options.addStretch(1)


        lt_main.addWidget(splt_main)
        splt_main.addWidget(self.file_browser)
        splt_main.addWidget(details_panel)

        self.installEventFilter(self)

        widget = QWidget()
        widget.setLayout(lt_main)
        self.setCentralWidget(widget)

    def eventFilter(self, widget, event):
        if event.type() == QEvent.KeyPress:
            key = event.key()
            if key == Qt.Key_R:
                self.force_update()
                return True
            # Texture Viewer
            if key == Qt.Key_1:
                self.texture_viewer.set_original_size()
            if key == Qt.Key_0:
                self.texture_viewer.set_fit_size()
            # Results Viewer
            if key == Qt.Key_C:
                self.results_viewer.cmb_texture_type.setCurrentIndex(0)
                return True
            if key == Qt.Key_D:
                self.results_viewer.cmb_texture_type.setCurrentIndex(1)
                return True
            if key == Qt.Key_A:
                self.results_viewer.cmb_texture_type.setCurrentIndex(2)
                return True
            if key == Qt.Key_N:
                self.results_viewer.cmb_texture_type.setCurrentIndex(3)
                return True
            if key == Qt.Key_S:
                self.open_texture_type_settings()
            # File Browser
            if key == Qt.Key_Return or key == Qt.Key_Right:
                self.file_browser.open_current_directory_external()
                return True
            if key == Qt.Key_Left:
                self.file_browser.open_parent_directory()
                return True
            if key == Qt.Key_L:
                self.file_browser.cmb_icon_size.setCurrentIndex(0)
            if key == Qt.Key_M:
                self.file_browser.cmb_icon_size.setCurrentIndex(1)
            if key == Qt.Key_B:
                self.file_browser.cmb_icon_size.setCurrentIndex(2)
        return QWidget.eventFilter(self, widget, event)

    def open_texture_type_settings(self):
        dialog = TextureTypeSettingsDialog()
        dialog.exec()
        return

    def alert(self):
        app.alert(window)

    def handle_file_changed(self):
        automatic_texture_type = Settings.get_automatic_texture_type(self.file_browser.selected_file)
        if not automatic_texture_type == core.TextureType.MAX:
            self.results_viewer.cmb_texture_type.setCurrentIndex(automatic_texture_type.value)
        self.handle_update()
        self.setWindowTitle("Mip Explorer - " + os.path.basename(self.file_browser.selected_file))

    def force_update(self):
        self.handle_update(True)

    def handle_update(self, force_update: bool = False):
        texture_type: core.TextureType = core.TextureType(self.results_viewer.cmb_texture_type.currentIndex())
        Settings.current_texture_type = texture_type
        if not os.path.isfile(self.file_browser.selected_file):
            return
        pixmap = QPixmap(self.file_browser.selected_file)
        self.texture_info_panel.update_info(self.file_browser.selected_file, pixmap)
        if core.is_mip_mappable(pixmap.size().width(), pixmap.size().height()):
            self.texture_viewer.texture_filepath = self.file_browser.selected_file
            self.texture_viewer.texture_type = texture_type
            self.texture_viewer.update_pixmap(pixmap)
            y_axis_values = get_plot_values(self.file_browser.selected_file, texture_type, force_update)
            self.results_viewer.update_plot(y_axis_values)
        else:
            self.results_viewer.update_plot([])
            self.texture_viewer.lbl_preview.setPixmap(QPixmap(""))
            self.texture_viewer.set_controls_state(False)

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
            self.file_browser.jump_to_path(self.fname)
        else:
            e.ignore()


def exit_handler():
    Settings.current_directory = window.file_browser.file_model.rootPath()
    Settings.save_settings()


if __name__ == "__main__":
    cachepath = os.path.dirname(__file__) + "/Saved/CachedData.json"
    if ALLOW_CACHING:
        ensure_cache_version(cachepath)
    use_dark_mode = ui_utilities.is_system_dark()
    bg_color = DARK_COLOR if use_dark_mode else LIGHT_COLOR
    fg_color = LIGHT_COLOR if use_dark_mode else DARK_COLOR
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