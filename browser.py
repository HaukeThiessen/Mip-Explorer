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


import core
import csv
import datetime
import os
import platform
import subprocess

from settings import Settings
from pathlib import Path

from PySide6.QtCore import *
from PySide6.QtWidgets import *
from PySide6.QtGui import QPixmap, QIcon


class IconProvider(QFileIconProvider):
    """
    The default icons provided by the file system model were often mixed up, this icon provider returns the correct icons
    """
    def __init__(self) -> None:
        super().__init__()
        self.ICON_SIZE = QSize(64, 64)
        self.MAX_THUMBNAIL_SIZE: int = 240
        self.ACCEPTED_FORMATS: tuple[str, ...] = (".jpg",".tiff",".png", ".webp", ".tga")
        self.cached_icons: dict[str, QIcon] = {}
        self.use_thumbnails: bool = False
        resources_folder: str
        resources_folder = "/Resources/"

        # Create folder icon
        folder_picture = QPixmap(QSize(32, 32))
        folder_picture.load(os.path.dirname(os.path.realpath(__file__)) + resources_folder + "FolderIcon.png")
        self.folder_icon = QIcon(folder_picture)

        # Create Icons
        csv_picture = QPixmap(QSize(32, 32))
        csv_picture.load(os.path.dirname(os.path.realpath(__file__)) + resources_folder + "csvIcon.png")
        self.csv_icon = QIcon(csv_picture)

        jpg_picture = QPixmap(QSize(32, 32))
        jpg_picture.load(os.path.dirname(os.path.realpath(__file__)) + resources_folder + "jpgIcon.png")
        self.jpg_icon = QIcon(jpg_picture)

        tiff_picture = QPixmap(QSize(32, 32))
        tiff_picture.load(os.path.dirname(os.path.realpath(__file__)) + resources_folder + "tiffIcon.png")
        self.tiff_icon = QIcon(tiff_picture)

        png_picture = QPixmap(QSize(32, 32))
        png_picture.load(os.path.dirname(os.path.realpath(__file__)) + resources_folder + "pngIcon.png")
        self.png_icon = QIcon(png_picture)

        tga_picture = QPixmap(QSize(32, 32))
        tga_picture.load(os.path.dirname(os.path.realpath(__file__)) + resources_folder + "tgaIcon.png")
        self.tga_icon = QIcon(tga_picture)

        bmp_picture = QPixmap(QSize(32, 32))
        bmp_picture.load(os.path.dirname(os.path.realpath(__file__)) + resources_folder + "bmpIcon.png")
        self.bmp_icon = QIcon(bmp_picture)

        webp_picture = QPixmap(QSize(32, 32))
        webp_picture.load(os.path.dirname(os.path.realpath(__file__)) + resources_folder + "webpIcon.png")
        self.webp_icon = QIcon(webp_picture)

    def calculate_thumbnail_size(self, original_size: QSize) -> QSize:
        aspect_ratio: float = float(original_size.width()) / float(original_size.height())
        if aspect_ratio > 1.0:
            return QSize(self.MAX_THUMBNAIL_SIZE, int(self.MAX_THUMBNAIL_SIZE / aspect_ratio))
        else:
            return  QSize(int(self.MAX_THUMBNAIL_SIZE * aspect_ratio), self.MAX_THUMBNAIL_SIZE)

    def icon(self, file_info: QFileInfo) -> QIcon:
        filename: str = ""
        try:
            filename: str = file_info.filePath()
        except:
            pass

        if not self.use_thumbnails:
            if os.path.isdir(filename):
              return self.folder_icon
            if filename.casefold().endswith(".csv"):
                return self.csv_icon
            if filename.casefold().endswith(".jpg") or filename.casefold().endswith(".jpeg"):
                return self.jpg_icon
            if filename.casefold().endswith(".tiff") or filename.casefold().endswith(".tif"):
                return self.tiff_icon
            if filename.casefold().endswith(".png"):
                return self.png_icon
            if filename.casefold().endswith(".tga"):
                return self.tga_icon
            if filename.casefold().endswith(".bmp"):
                return self.bmp_icon
            if filename.casefold().endswith(".webp"):
                return self.webp_icon
            return QIcon()

        if filename.casefold().endswith(self.ACCEPTED_FORMATS):
            if filename in self.cached_icons:
                return self.cached_icons[filename]
            picture = QPixmap(self.ICON_SIZE)
            picture.load(filename)
            icon = QIcon(picture.scaled(self.calculate_thumbnail_size(picture.size())))
            self.cached_icons.update({filename: icon})
            return icon
        else:
            return super().icon(file_info)


class FileBrowser(QWidget):
    file_selection_changed  = Signal()
    needs_attention         = Signal()
    scan_directory_label: str = "🗃️ Scan Directory"
    selected_file: str = ""

    def __init__(self, *args, **kwargs):
        QWidget.__init__(self, *args, **kwargs)
        lt_vertical = QVBoxLayout(self)
        lt_vertical.setContentsMargins(0,0,0,0)
        lt_horizontal = QHBoxLayout()
        lt_list = QVBoxLayout()
        lt_list.setContentsMargins(0,0,0,0)
        lt_controls = QHBoxLayout()
        lt_search = QHBoxLayout()

        self.le_address   = QLineEdit()
        self.tree_view    = QTreeView()
        self.list_view    =  QListView()
        self.splitter     = QSplitter()
        self.list_wrapper = QWidget()
        self.search_bar   = QLineEdit()
        self.search_bar.setPlaceholderText("Search Filenames")
        self.search_bar.textEdited.connect(self.handle_search_term_changed)
        lbl_search_caption = QLabel("🔍")
        self.cmb_icon_size = QComboBox()
        self.cmb_icon_size.addItems(["L\u0332ist", "M\u0332edium", "B\u0332ig"])
        self.cmb_icon_size.setToolTip("Controls how the files are displayed.\n"
                                      "'List' doesn't show thumbnails, making it faster when navigating directories with a lot of files.\n"
                                      "'Medium' and 'Big' show thumbnails, but thumbnail generation can be slow.")
        self.btn_batch = QPushButton(self.scan_directory_label)
        self.btn_batch.setToolTip("Calculates Mip 0's information density for all textures in this directory and sub-directories.\n"
                                  "Stores the sorted results in a csv file in the current directory.\n"
                                  "The texture type is determined automatically, and falls back to DATA if the mode can't be derived from the affix.")
        self.list_view.setMinimumWidth(15)
        self.tree_view.setMinimumWidth(15)
        self.splitter.setChildrenCollapsible(False)
        lt_horizontal.addWidget(self.splitter)
        self.splitter.addWidget(self.tree_view)
        self.splitter.addWidget(self.list_wrapper)
        self.list_wrapper.setLayout(lt_list)
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
        self.dir_model.setFilter(QDir.Filter.NoDotAndDotDot | QDir.Filter.AllDirs)

        self.icon_provider = IconProvider()
        self.file_model = QFileSystemModel()
        self.init_file_model()

        self.tree_view.setModel(self.dir_model)
        self.tree_view.hideColumn(1)
        self.tree_view.hideColumn(2)
        self.tree_view.hideColumn(3)

        self.tree_view.setRootIndex(self.dir_model.index(path))
        self.list_view.setRootIndex(self.file_model.index(path))
        self.list_view.setResizeMode(QListView.ResizeMode.Adjust)

        self.tree_view.clicked.connect(self.handle_selected_folder_changed)
        self.tree_view.selectionModel().currentChanged.connect(self.handle_selected_folder_changed)
        self.list_view.doubleClicked.connect(self.open_current_directory_external)
        self.le_address.textEdited.connect(self.handle_address_changed)
        self.cmb_icon_size.currentIndexChanged.connect(self.handle_icon_size_changed)
        self.btn_batch.clicked.connect(self.process_current_directory)

    def handle_search_term_changed(self):
            if self.search_bar.text() == "":
                visible_formats = core.SUPPORTEDFORMATS
                visible_formats.add("*.csv")
                self.file_model.setNameFilters(visible_formats)
            else:
                self.file_model.setNameFilters(["*" + self.search_bar.text() + "*"])

    def handle_icon_size_changed(self):
        current_index = self.cmb_icon_size.currentIndex()
        current_directory = self.file_model.rootPath()
        if current_index == 0:
            self.icon_provider.use_thumbnails = False
            self.list_view.setViewMode(QListView.ViewMode.ListMode)
            self.list_view.setGridSize(QSize(-1, -1))
            self.list_view.setIconSize(QSize(-1, -1))
        else:
            sizes = [128, 256]
            new_size = sizes[current_index - 1]
            self.icon_provider.use_thumbnails = True
            self.list_view.setViewMode(QListView.ViewMode.IconMode)
            self.list_view.setGridSize(QSize(new_size, new_size))
            self.list_view.setIconSize(QSize(new_size - 16, new_size - 16))
        self.file_model = QFileSystemModel()
        self.init_file_model()
        self.jump_to_path(current_directory)

    def init_file_model(self):
        self.file_model.setIconProvider(self.icon_provider)
        self.file_model.setFilter(QDir.Filter.NoDotAndDotDot | QDir.Filter.Files | QDir.Filter.AllDirs)
        self.file_model.setNameFilterDisables(False)
        self.handle_search_term_changed()
        self.list_view.setModel(self.file_model)
        self.list_view.selectionModel().selectionChanged.connect(self.handle_file_selection_changed)

    def process_current_directory(self):
        """
        Create a csv file with the Mip0 info stats of all files, sorted by information density
        """
        self.btn_batch.setEnabled(False)
        self.btn_batch.setText("---")
        path = self.file_model.rootPath()
        supported_formats = []
        if platform.system() == "Windows":
            supported_formats = core.SUPPORTEDFORMATS
        else:
            for format in core.SUPPORTEDFORMATS:
                supported_formats.append(format[1:])
        files = list(p.resolve() for p in Path(path).glob("**/*") if p.suffix in supported_formats)
        results_table: list = []
        progress = QProgressDialog("", "Cancel", 0, len(files), self)
        progress.setWindowTitle("Processing Mips in \n" + path + "...")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        for i in range(0, len(files)):
            progress.setValue(i)
            pixmap = QPixmap(Path(files[i]))
            if core.is_mip_mappable(pixmap.size().width(), pixmap.size().height()):
                raw_deltas: list[list[float]] = core.calculate_raw_deltas(str(files[i]), False)
                texture_type = Settings.get_automatic_texture_type(str(files[i]))
                if texture_type == core.TextureType.MAX or texture_type == core.TextureType.CHANNELS:
                    texture_type = core.TextureType.DATA
                values: list[float] | list[list[float]] = core.interpret_deltas(raw_deltas, texture_type)
                new_entry = [
                    values[0],
                    files[i].__str__(),
                    pixmap.width().__str__() + "x" + pixmap.height().__str__(),
                    pixmap.hasAlpha(),
                    texture_type.__str__()[9:]
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
            base_name: str = "/MipStats_"
            with open(path + base_name + time + ".csv", "w", newline="") as csvfile:
                writer = csv.writer(csvfile, quoting=csv.QUOTE_ALL)
                writer.writerows(results_table_sorted)
        except:
            print("Failed to write Scan Results to csv file.")
        self.needs_attention.emit()
        self.btn_batch.setText(self.scan_directory_label)
        self.btn_batch.setEnabled(True)

    def open_current_directory_external(self):
        model: QFileSystemModel = QFileSystemModel(self.list_view.model())
        selected_file_path = model.filePath(self.list_view.selectedIndexes()[0])
        if os.path.isfile(selected_file_path):
            selected_file_path = os.path.normpath(selected_file_path)
            if platform.system() == "Windows":
                OS_FILEBROWSER_PATH: str = os.path.join(str(os.getenv("WINDIR")), "explorer.exe")
                subprocess.run([OS_FILEBROWSER_PATH, "/select,", selected_file_path])
            else:
                subprocess.Popen(["xdg-open", selected_file_path])
            
        else:
            self.jump_to_path(selected_file_path)

    def open_parent_directory(self):
        self.jump_to_path(str(Path(self.file_model.rootPath()).parent))

    def handle_selected_folder_changed(self, index):
        path = self.dir_model.fileInfo(index).absoluteFilePath()
        self.list_view.setRootIndex(self.file_model.setRootPath(path))
        self.le_address.setText(path)

    def handle_address_changed(self):
        if not os.path.exists(self.le_address.text()):
            return
        self.jump_to_path(self.le_address.text())

    def handle_file_selection_changed(self):
        model: QFileSystemModel = QFileSystemModel(self.list_view.model())
        self.selected_file = model.filePath(self.list_view.selectedIndexes()[0])
        self.le_address.setText(self.selected_file)
        self.file_selection_changed.emit()

    def jump_to_path(self, target_path: str):
        # TODO: Consistent behavior, select file if applicable and jump to correct location
        if os.path.isfile(target_path):
            self.list_view.setRootIndex(self.file_model.setRootPath(target_path))
            target_path = os.path.dirname(target_path)
            return
        if os.path.isdir(target_path):
            self.le_address.setText(target_path)
            new_index = self.dir_model.index(target_path)
            self.tree_view.scrollTo(new_index)
            self.tree_view.expand(new_index)
            self.tree_view.setCurrentIndex(new_index)
            self.list_view.setRootIndex(self.file_model.setRootPath(target_path))