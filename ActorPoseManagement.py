import sys
import os
import subprocess
import json
import shutil
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QGridLayout, QScrollArea, QLineEdit,
    QPushButton, QComboBox, QInputDialog, QMenu, QFileDialog, QFrame, QToolButton
)
from PyQt6.QtGui import QPixmap, QBrush, QColor, QDragEnterEvent, QDropEvent
from PyQt6.QtCore import Qt, QSize, QEvent, QTimer, QUrl
from PIL import Image

class ActorItem(QWidget):
    def __init__(self, name, num_poses, thumbnail_path, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)
        self.thumbnail = QLabel()
        self.update_thumbnail(thumbnail_path)
        layout.addWidget(self.thumbnail)

        info_layout = QVBoxLayout()
        name_label = QLabel(name)
        name_label.setStyleSheet("font-weight: bold;")
        info_layout.addWidget(name_label)
        info_layout.addWidget(QLabel(f"{num_poses} poses"))
        layout.addLayout(info_layout)

        self.setLayout(layout)
        self.name = name

    def update_thumbnail(self, path):
        if path and os.path.exists(path):
            pixmap = QPixmap(path).scaled(100, 100, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.thumbnail.setPixmap(pixmap)
        else:
            self.thumbnail.setText("No Image")

class PoseItem(QFrame):
    def __init__(self, path, keywords, resolution, parent=None):
        super().__init__(parent)
        self.path = path
        self.keywords = keywords
        self.resolution = resolution
        self.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Raised)
        self.setLineWidth(3)
        self.normal_style = "background-color: palette(base); border: 3px solid transparent;"
        self.selected_style = "background-color: palette(base); border: 3px solid #0066ff;"
        self.setStyleSheet(self.normal_style)

        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(4)

        res_label = QLabel(resolution)
        res_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        res_label.setStyleSheet("font-size: 9pt; color: #555;")
        layout.addWidget(res_label)

        self.image_label = QLabel()
        if path and os.path.exists(path):
            pixmap = QPixmap(path).scaled(150, 150, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.image_label.setPixmap(pixmap)
        else:
            self.image_label.setText("Missing")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.image_label)

        self.kw_label = QLabel()
        self.kw_label.setWordWrap(True)
        self.kw_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.kw_label.setStyleSheet("font-size: 10pt; color: gray;")
        self.update_keywords_display()
        layout.addWidget(self.kw_label)

        self.setLayout(layout)
        self.setMinimumSize(170, 240)

    def update_keywords_display(self):
        if self.keywords:
            self.kw_label.setText(", ".join(self.keywords))
            self.kw_label.setVisible(True)
        else:
            self.kw_label.setVisible(False)

    def set_selected(self, selected):
        self.setStyleSheet(self.selected_style if selected else self.normal_style)

class ImagePopup(QMainWindow):
    def __init__(self, image_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Full View")
        self.setWindowState(Qt.WindowState.WindowMaximized)
        self.setStyleSheet("background-color: black;")

        central = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.update_image(image_path)

        layout.addWidget(self.image_label)
        central.setLayout(layout)
        self.setCentralWidget(central)

    def update_image(self, path):
        if path and os.path.exists(path):
            pixmap = QPixmap(path)
            screen = QApplication.primaryScreen().availableGeometry()
            scaled = pixmap.scaled(screen.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.image_label.setPixmap(scaled)
        else:
            self.image_label.setText("Image Not Found")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        super().keyPressEvent(event)

class ModelManager(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI Model Manager")
        self.setWindowState(Qt.WindowState.WindowMaximized)
        self.setAcceptDrops(True)  # Enable drag & drop on the whole window
        self.base_folders = []
        self.actors = {}
        self.all_keywords = set()
        self.selected_actor = None
        self.selected_pose_item = None
        self.sort_by_resolution = False
        self.copied_keywords = []

        self.init_ui()
        self.load_config()

    def init_ui(self):
        central = QWidget()
        main_layout = QHBoxLayout()

        # Left panel
        left_layout = QVBoxLayout()
        self.keyword_filter_combo_left = QComboBox()
        self.keyword_filter_combo_left.addItem("No Filter")
        self.keyword_filter_combo_left.currentIndexChanged.connect(self.filter_actors_by_keyword)
        self.reset_keyword_left = QPushButton("Reset")
        self.reset_keyword_left.clicked.connect(self.reset_left_keyword_filter)
        filter_left_top = QHBoxLayout()
        filter_left_top.addWidget(self.keyword_filter_combo_left)
        filter_left_top.addWidget(self.reset_keyword_left)
        left_layout.addLayout(filter_left_top)

        self.name_filter = QLineEdit()
        self.name_filter.setPlaceholderText("Filter by name")
        self.name_filter.textChanged.connect(self.filter_actors_by_name)
        self.clear_name_filter = QPushButton("Clear")
        self.clear_name_filter.clicked.connect(lambda: self.name_filter.setText(""))
        filter_left = QHBoxLayout()
        filter_left.addWidget(self.name_filter)
        filter_left.addWidget(self.clear_name_filter)
        left_layout.addLayout(filter_left)

        self.actors_list = QListWidget()
        self.actors_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.actors_list.itemClicked.connect(self.select_actor_from_click)
        self.actors_list.currentItemChanged.connect(self.select_actor_from_selection)
        self.scroll_left = QScrollArea()
        self.scroll_left.setWidget(self.actors_list)
        self.scroll_left.setWidgetResizable(True)
        left_layout.addWidget(self.scroll_left)
        left_widget = QWidget()
        left_widget.setLayout(left_layout)
        main_layout.addWidget(left_widget, stretch=1)

        # Middle panel
        middle_layout = QVBoxLayout()
        filter_row = QHBoxLayout()
        self.keyword_filter_combo = QComboBox()
        self.keyword_filter_combo.addItem("No Filter")
        self.keyword_filter_combo.currentIndexChanged.connect(self.filter_poses_by_keyword)
        filter_row.addWidget(self.keyword_filter_combo)

        self.reset_keyword = QPushButton("Reset")
        self.reset_keyword.clicked.connect(self.reset_keyword_filter)
        filter_row.addWidget(self.reset_keyword)

        self.sort_resolution_button = QToolButton()
        self.sort_resolution_button.setText("Sort by Resolution ↓")
        self.sort_resolution_button.setCheckable(True)
        self.sort_resolution_button.setStyleSheet("QToolButton:checked { background-color: #0066ff; color: white; }")
        self.sort_resolution_button.clicked.connect(self.toggle_resolution_sort)
        filter_row.addWidget(self.sort_resolution_button)

        middle_layout.addLayout(filter_row)

        self.poses_grid = QWidget()
        self.grid_layout = QGridLayout()
        self.grid_layout.setSpacing(15)
        self.poses_grid.setLayout(self.grid_layout)
        scroll_middle = QScrollArea()
        scroll_middle.setWidget(self.poses_grid)
        scroll_middle.setWidgetResizable(True)
        middle_layout.addWidget(scroll_middle)
        middle_widget = QWidget()
        middle_widget.setLayout(middle_layout)
        main_layout.addWidget(middle_widget, stretch=3)

        # Right panel
        right_layout = QVBoxLayout()
        self.pose_keywords_list = QListWidget()
        self.pose_keywords_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.pose_keywords_list.customContextMenuRequested.connect(self.show_keyword_menu)
        right_layout.addWidget(QLabel("Pose Keywords"))
        right_layout.addWidget(self.pose_keywords_list, stretch=1)

        self.all_keywords_list = QListWidget()
        self.all_keywords_list.itemDoubleClicked.connect(self.add_keyword_to_pose)
        right_layout.addWidget(QLabel("All Keywords"))
        right_layout.addWidget(self.all_keywords_list, stretch=1)

        right_widget = QWidget()
        right_widget.setLayout(right_layout)
        main_layout.addWidget(right_widget, stretch=1)

        central.setLayout(main_layout)
        self.setCentralWidget(central)

        # Menu
        menu = self.menuBar()
        file_menu = menu.addMenu("File")
        file_menu.addAction("Configure Base Folders", self.configure_folders)
        file_menu.addAction("Refresh Collections", self.parse_folders)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if self.selected_actor and event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent):
        if not self.selected_actor:
            print("DEBUG: No actor selected for drop")
            return

        actor_folder = self.actors[self.selected_actor]['folder']
        if not os.path.exists(actor_folder):
            print(f"DEBUG: Actor folder not found: {actor_folder}")
            return

        urls = event.mimeData().urls()
        added_images = False

        for url in urls:
            file_path = url.toLocalFile()
            if not os.path.isfile(file_path):
                continue

            file_name = os.path.basename(file_path)
            dest_path = os.path.join(actor_folder, file_name)

            # Skip if already exists
            if os.path.exists(dest_path):
                print(f"DEBUG: File already exists, skipping: {file_name}")
                continue

            # Copy file
            try:
                shutil.copy2(file_path, dest_path)
                print(f"DEBUG: Copied {file_name} to {actor_folder}")
                if file_name.lower().endswith(('.png', '.jpg', '.jpeg')):
                    added_images = True
            except Exception as e:
                print(f"DEBUG: Error copying {file_name}: {e}")

        if added_images:
            print("DEBUG: New image(s) added → refreshing view")
            # Re-parse to detect new files
            self.parse_folders()
            # Ensure current actor stays selected and grid refreshes
            self.update_actors_list()
            self.update_poses_grid()

        event.acceptProposedAction()

    def keyPressEvent(self, event):
        if self.selected_pose_item:
            modifiers = event.modifiers()
            key = event.key()
            if modifiers == Qt.KeyboardModifier.ControlModifier:
                if key == Qt.Key.Key_C:
                    self.copy_keywords()
                    return
                elif key == Qt.Key.Key_V:
                    self.paste_keywords()
                    return
            elif key == Qt.Key.Key_Delete:
                self.remove_keyword()
                return
            elif key == Qt.Key.Key_Insert:
                self.add_new_keyword()
                return
        super().keyPressEvent(event)

    def copy_keywords(self):
        if self.selected_pose_item and self.selected_pose_item.keywords:
            self.copied_keywords = self.selected_pose_item.keywords[:]

    def paste_keywords(self):
        if self.selected_pose_item and self.copied_keywords:
            self.selected_pose_item.keywords[:] = self.copied_keywords[:]
            self.pose_keywords_list.clear()
            for kw in self.selected_pose_item.keywords:
                self.pose_keywords_list.addItem(kw)
            self.selected_pose_item.update_keywords_display()

    def toggle_resolution_sort(self):
        self.sort_by_resolution = self.sort_resolution_button.isChecked()
        if self.sort_by_resolution:
            self.sort_resolution_button.setText("Sort by Resolution ↓ (Active)")
        else:
            self.sort_resolution_button.setText("Sort by Resolution ↓")
        if self.selected_actor:
            self.update_poses_grid()

    def get_image_resolution(self, path):
        try:
            with Image.open(path) as img:
                w, h = img.size
                return f"{w}×{h}"
        except Exception:
            return "Unknown"

    def get_image_pixels(self, path):
        try:
            with Image.open(path) as img:
                w, h = img.size
                return w * h
        except Exception:
            return 0

    def configure_folders(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Base Folder", "", QFileDialog.Option.ShowDirsOnly)
        if folder and folder not in self.base_folders:
            self.base_folders.append(folder)
            self.parse_folders()
            self.save_config()

    def load_config(self):
        if os.path.exists("config.txt"):
            with open("config.txt", "r") as f:
                self.base_folders = [line.strip() for line in f.readlines() if line.strip()]
            self.parse_folders()

    def save_config(self):
        with open("config.txt", "w") as f:
            for folder in self.base_folders:
                f.write(folder + "\n")

    def parse_folders(self):
        new_actors = {}
        for base in self.base_folders:
            if not os.path.isdir(base):
                continue
            for actor_folder in os.listdir(base):
                actor_path = os.path.join(base, actor_folder)
                if os.path.isdir(actor_path):
                    poses = []
                    thumbnail = None
                    image_files = [f for f in os.listdir(actor_path) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
                    for file in sorted(image_files, key=lambda f: os.path.getmtime(os.path.join(actor_path, f))):
                        full_path = os.path.join(actor_path, file)
                        resolution_str = self.get_image_resolution(full_path)
                        poses.append({'path': full_path, 'keywords': [], 'resolution': resolution_str})
                        if not thumbnail:
                            thumbnail = full_path
                    if poses:
                        new_actors[actor_folder] = {
                            'folder': actor_path,
                            'poses': poses,
                            'thumbnail': thumbnail or ""
                        }
        self.actors = new_actors
        self.load_data()
        self.update_all_keywords()
        self.update_actors_list()
        self.update_keyword_combos()

    def load_data(self):
        if os.path.exists("data.json"):
            try:
                with open("data.json", "r") as f:
                    saved = json.load(f)
                for actor_name, actor_data in saved.items():
                    if actor_name in self.actors:
                        if 'thumbnail' in actor_data and os.path.exists(actor_data['thumbnail']):
                            self.actors[actor_name]['thumbnail'] = actor_data['thumbnail']
                        if 'poses' in actor_data:
                            saved_poses = actor_data['poses']
                            for pose in self.actors[actor_name]['poses']:
                                if pose['path'] in saved_poses:
                                    pose['keywords'] = saved_poses[pose['path']]
            except Exception as e:
                print(f"Error loading data.json: {e}")

    def save_data(self):
        data = {}
        for actor, info in self.actors.items():
            data[actor] = {
                'thumbnail': info['thumbnail'],
                'poses': {pose['path']: pose['keywords'] for pose in info['poses'] if os.path.exists(pose['path'])}
            }
        try:
            with open("data.json", "w") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"Error saving data.json: {e}")

    def update_all_keywords(self):
        self.all_keywords.clear()
        for actor in self.actors.values():
            for pose in actor['poses']:
                self.all_keywords.update(pose['keywords'])
        self.all_keywords_list.clear()
        for kw in sorted(self.all_keywords):
            self.all_keywords_list.addItem(kw)

    def update_keyword_combos(self):
        current_left = self.keyword_filter_combo_left.currentText()
        current_middle = self.keyword_filter_combo.currentText()

        self.keyword_filter_combo.blockSignals(True)
        self.keyword_filter_combo_left.blockSignals(True)

        self.keyword_filter_combo.clear()
        self.keyword_filter_combo_left.clear()
        self.keyword_filter_combo.addItem("No Filter")
        self.keyword_filter_combo_left.addItem("No Filter")
        for kw in sorted(self.all_keywords):
            self.keyword_filter_combo.addItem(kw)
            self.keyword_filter_combo_left.addItem(kw)

        self.keyword_filter_combo.blockSignals(False)
        self.keyword_filter_combo_left.blockSignals(False)

        if current_middle != "No Filter" and current_middle in [self.keyword_filter_combo.itemText(i) for i in range(self.keyword_filter_combo.count())]:
            self.keyword_filter_combo.setCurrentText(current_middle)
        if current_left != "No Filter" and current_left in [self.keyword_filter_combo_left.itemText(i) for i in range(self.keyword_filter_combo_left.count())]:
            self.keyword_filter_combo_left.setCurrentText(current_left)

    def update_actors_list(self, greyed_out=None):
        # Preserve scroll position
        scroll_pos = self.scroll_left.verticalScrollBar().value()

        self.actors_list.blockSignals(True)
        self.actors_list.clear()
        sorted_names = sorted(self.actors.keys())
        for name in sorted_names:
            data = self.actors[name]
            widget = ActorItem(name, len(data['poses']), data['thumbnail'])
            item = QListWidgetItem()
            item.setSizeHint(widget.sizeHint() + QSize(20, 20))

            if greyed_out and name in greyed_out:
                item.setFlags(Qt.ItemFlag.NoItemFlags)
                widget.setStyleSheet("opacity: 0.35; color: gray;")
                item.setBackground(QBrush(QColor(240, 240, 240)))
            else:
                item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                widget.setStyleSheet("")

            self.actors_list.addItem(item)
            self.actors_list.setItemWidget(item, widget)

        # Restore selection
        if self.selected_actor and self.selected_actor in self.actors and (greyed_out is None or self.selected_actor not in greyed_out):
            try:
                row = sorted_names.index(self.selected_actor)
                self.actors_list.setCurrentRow(row)
                # Scroll minimally to make selected item visible
                item = self.actors_list.item(row)
                if item:
                    self.actors_list.scrollToItem(item)
            except ValueError:
                pass
        else:
            self.actors_list.setCurrentRow(-1)

        # Restore approximate scroll position
        QTimer.singleShot(0, lambda: self.scroll_left.verticalScrollBar().setValue(scroll_pos))

        self.actors_list.blockSignals(False)

    def filter_actors_by_name(self, text):
        text = text.lower()
        for i in range(self.actors_list.count()):
            item = self.actors_list.item(i)
            widget = self.actors_list.itemWidget(item)
            if widget and text in widget.name.lower():
                item.setHidden(False)
            else:
                item.setHidden(True)

    def filter_actors_by_keyword(self, index):
        if index <= 0:
            self.update_actors_list()
            return
        kw = self.keyword_filter_combo_left.currentText()
        greyed_out = set()
        for name, data in self.actors.items():
            has_kw = any(kw in pose['keywords'] for pose in data['poses'])
            if not has_kw:
                greyed_out.add(name)
        self.update_actors_list(greyed_out)

    def reset_left_keyword_filter(self):
        self.keyword_filter_combo_left.setCurrentIndex(0)
        self.update_actors_list()

    def select_actor_from_click(self, item):
        if item is None or (item.flags() & Qt.ItemFlag.ItemIsEnabled == 0):
            return
        self.select_actor_internal(item)

    def select_actor_from_selection(self, current, previous):
        if current is None or (current.flags() & Qt.ItemFlag.ItemIsEnabled == 0):
            if previous and (previous.flags() & Qt.ItemFlag.ItemIsEnabled):
                self.actors_list.setCurrentItem(previous)
            else:
                self.actors_list.setCurrentRow(-1)
            return
        self.select_actor_internal(current)

    def select_actor_internal(self, item):
        widget = self.actors_list.itemWidget(item)
        if widget is None:
            return
        new_actor = widget.name

        if self.selected_actor != new_actor:
            self.perform_full_save()

        self.selected_actor = new_actor
        self.selected_pose_item = None
        self.pose_keywords_list.clear()
        self.update_poses_grid()

    def update_poses_grid(self):
        for i in reversed(range(self.grid_layout.count())):
            widget = self.grid_layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)

        if not self.selected_actor or self.selected_actor not in self.actors:
            return

        poses = self.actors[self.selected_actor]['poses'][:]

        if self.sort_by_resolution:
            poses.sort(key=lambda p: self.get_image_pixels(p['path']), reverse=True)

        row, col = 0, 0
        cols = 5
        for pose_dict in poses:
            pose_item = PoseItem(pose_dict['path'], pose_dict['keywords'], pose_dict['resolution'])
            pose_item.installEventFilter(self)
            self.grid_layout.addWidget(pose_item, row, col)
            col += 1
            if col >= cols:
                col = 0
                row += 1

        self.apply_pose_filter()

    def eventFilter(self, source, event):
        if not isinstance(source, PoseItem):
            return super().eventFilter(source, event)

        if event.type() == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.LeftButton:
                if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                    self.open_file_explorer(source.path)
                else:
                    self.select_pose(source)
                return True
            elif event.button() == Qt.MouseButton.RightButton:
                self.set_actor_thumbnail(source.path)
                return True

        elif event.type() == QEvent.Type.MouseButtonDblClick:
            if event.button() == Qt.MouseButton.LeftButton:
                popup = ImagePopup(source.path, self)
                popup.show()
                return True

        return super().eventFilter(source, event)

    def select_pose(self, pose_item):
        if self.selected_pose_item:
            self.selected_pose_item.set_selected(False)

        self.selected_pose_item = pose_item
        pose_item.set_selected(True)

        self.pose_keywords_list.clear()
        for kw in pose_item.keywords:
            self.pose_keywords_list.addItem(kw)

    def perform_full_save(self):
        self.update_all_keywords()
        self.update_keyword_combos()
        self.filter_actors_by_keyword(self.keyword_filter_combo_left.currentIndex())
        self.apply_pose_filter()
        self.save_data()

    def set_actor_thumbnail(self, path):
        if self.selected_actor and os.path.exists(path):
            self.actors[self.selected_actor]['thumbnail'] = path
            self.update_actors_list()
            self.perform_full_save()

    def open_file_explorer(self, path):
        if not os.path.exists(path):
            return
        if sys.platform == 'win32':
            subprocess.Popen(['explorer', '/select,', path.replace('/', '\\')])
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', '-R', path])
        else:
            subprocess.Popen(['xdg-open', os.path.dirname(path)])

    def apply_pose_filter(self):
        current_index = self.keyword_filter_combo.currentIndex()
        if current_index <= 0:
            for i in range(self.grid_layout.count()):
                w = self.grid_layout.itemAt(i).widget()
                if isinstance(w, PoseItem):
                    w.setVisible(True)
            return

        kw = self.keyword_filter_combo.currentText()
        for i in range(self.grid_layout.count()):
            w = self.grid_layout.itemAt(i).widget()
            if isinstance(w, PoseItem):
                w.setVisible(kw in w.keywords)

    def filter_poses_by_keyword(self, index):
        self.apply_pose_filter()

    def reset_keyword_filter(self):
        self.keyword_filter_combo.setCurrentIndex(0)
        self.apply_pose_filter()

    def remove_keyword(self):
        if not self.selected_pose_item:
            return
        current_item = self.pose_keywords_list.currentItem()
        if current_item:
            kw = current_item.text()
            self.selected_pose_item.keywords.remove(kw)
            self.pose_keywords_list.takeItem(self.pose_keywords_list.currentRow())
            self.selected_pose_item.update_keywords_display()

    def add_new_keyword(self):
        if not self.selected_pose_item:
            return
        text, ok = QInputDialog.getText(self, "Add Keyword", "Enter new keyword:")
        if ok and text.strip():
            text = text.strip()
            if text not in self.selected_pose_item.keywords:
                self.selected_pose_item.keywords.append(text)
                self.pose_keywords_list.addItem(text)
                self.selected_pose_item.update_keywords_display()

    def show_keyword_menu(self, pos):
        if self.pose_keywords_list.itemAt(pos):
            menu = QMenu()
            edit_action = menu.addAction("Edit")
            action = menu.exec(self.pose_keywords_list.mapToGlobal(pos))
            if action == edit_action:
                self.edit_keyword()

    def edit_keyword(self):
        if not self.selected_pose_item:
            return
        item = self.pose_keywords_list.currentItem()
        if item:
            old_text = item.text()
            text, ok = QInputDialog.getText(self, "Edit Keyword", "Edit keyword:", text=old_text)
            if ok and text.strip() and text.strip() != old_text:
                self.selected_pose_item.keywords.remove(old_text)
                new_text = text.strip()
                self.selected_pose_item.keywords.append(new_text)
                item.setText(new_text)
                self.selected_pose_item.update_keywords_display()

    def add_keyword_to_pose(self, item):
        if self.selected_pose_item:
            kw = item.text()
            if kw not in self.selected_pose_item.keywords:
                self.selected_pose_item.keywords.append(kw)
                self.pose_keywords_list.addItem(kw)
                self.selected_pose_item.update_keywords_display()

    def closeEvent(self, event):
        self.perform_full_save()
        super().closeEvent(event)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    window = ModelManager()
    window.show()
    sys.exit(app.exec())