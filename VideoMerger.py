import sys
import os
import math
import subprocess
from collections import Counter

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QPushButton, QFileDialog,
    QVBoxLayout, QWidget, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QAbstractItemView,
    QProgressDialog, QSpacerItem, QSizePolicy
)
from PyQt6.QtGui import QIcon, QPixmap, QImage
from PyQt6.QtCore import Qt, QSize, QTimer, QThread, pyqtSignal

from moviepy.editor import VideoFileClip, concatenate_videoclips


# ──────────────────────── Worker thread for merging (so UI stays responsive) ────────────────────────
class MergeWorker(QThread):
    finished = pyqtSignal(str)   # emits final file path
    failed = pyqtSignal(str)     # emits error message

    def __init__(self, videos, target_res, output_path):
        super().__init__()
        self.videos = videos
        self.target_res = target_res
        self.output_path = output_path

    def run(self):
        try:
            clips = []
            tw, th = self.target_res
            for v in self.videos:
                clip = v["clip"]
                if v["res"] == self.target_res:
                    clips.append(clip)
                else:
                    scale = min(tw / v["res"][0], th / v["res"][1])
                    resized = clip.resize(width=int(v["res"][0] * scale))
                    clips.append(resized.on_color(size=(tw, th), color=(0,0,0), pos="center"))

            final = concatenate_videoclips(clips, method="compose")
            final.write_videofile(self.output_path, codec="libx264", audio_codec="aac",
                                 threads=os.cpu_count() or 4, preset="medium", verbose=False, logger=None)

            # Clean up
            for v in self.videos:
                v["clip"].close()
            final.close()

            self.finished.emit(self.output_path)
        except Exception as e:
            self.failed.emit(str(e))


# ──────────────────────────────────────── Main Window ────────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Video Merger")
        self.setMinimumSize(1100, 700)

        self.videos = []
        self.target_resolution = None
        self.last_merged = None
        self.worker = None

        # UI
        central = QWidget()
        layout = QVBoxLayout()

        self.res_label = QLabel("Target Resolution: None")
        self.res_label.setStyleSheet("font-size: 17px; font-weight: bold; padding: 12px;")
        layout.addWidget(self.res_label)

        self.list_widget = VideoList(self)
        layout.addWidget(self.list_widget)

        btns = QHBoxLayout()
        btns.addWidget(QPushButton("Add Video(s)", clicked=self.add_videos_dialog))
        btns.addWidget(QPushButton("Merge & Save", clicked=self.merge_and_save))
        btns.addWidget(QPushButton("Play Last Merged", clicked=self.play_last))
        btns.addStretch()
        layout.addLayout(btns)

        # Status label with animation
        self.status_label = QLabel("Ready")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("font-size: 16px; color: #555; padding: 8px;")
        layout.addWidget(self.status_label)

        central.setLayout(layout)
        self.setCentralWidget(central)

        # Animation timer
        self.dots = 0
        self.anim_timer = QTimer()
        self.anim_timer.timeout.connect(self.update_dots)

    def update_dots(self):
        self.dots = (self.dots + 1) % 4
        self.status_label.setText("Working" + "." * self.dots)

    # ──────────────────────────────────────── Rest of your perfect code ────────────────────────────────────────
    def add_videos_dialog(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Select Videos", "",
            "Video Files (*.mp4 *.avi *.mov *.mkv *.webm *.ts *.wmv *.flv *.mpg *.mpeg)")
        for p in paths:
            self.add_video(p)

    def add_video(self, path: str):
        try:
            clip = VideoFileClip(path)
            w, h = clip.size
            frame = clip.get_frame(0)
            height, width, _ = frame.shape
            qimg = QImage(frame.tobytes(), width, height, QImage.Format.Format_RGB888)

            pix = QPixmap.fromImage(qimg).scaled(160, 100,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation) if not qimg.isNull() else QPixmap(160, 100).fill(Qt.GlobalColor.darkGray)

            item = QListWidgetItem()
            item.setIcon(QIcon(pix))
            item.setData(Qt.ItemDataRole.UserRole, path)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            self.list_widget.addItem(item)
            self.videos.append({"path": path, "clip": clip, "res": (w, h)})
            self.recalculate_target_resolution()
        except Exception as e:
            print(f"Failed to load {path}: {e}")

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            for item in reversed(self.list_widget.selectedItems()):
                self.list_widget.takeItem(self.list_widget.row(item))
            self.sync_order()
            QTimer.singleShot(0, lambda: (
                self.list_widget.setViewMode(QListWidget.ViewMode.ListMode),
                self.list_widget.setViewMode(QListWidget.ViewMode.IconMode)
            ))

    def sync_order(self):
        new = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            path = item.data(Qt.ItemDataRole.UserRole)
            for v in self.videos:
                if v["path"] == path:
                    new.append(v)
                    break
        self.videos = new
        self.recalculate_target_resolution()

    def recalculate_target_resolution(self):
        if not self.videos:
            self.target_resolution = None
            self.res_label.setText("Target Resolution: None")
            return

        counts = Counter(v["res"] for v in self.videos)
        candidates = [r for r, c in counts.items() if c == max(counts.values())]

        if len(candidates) == 1:
            self.target_resolution = candidates[0]
        else:
            self.target_resolution = min(candidates,
                key=lambda r: sum(abs(math.log(max(min(r[0]/w, r[1]/h), 0.01)))
                                  for w, h in (v["res"] for v in self.videos)))

        tw, th = self.target_resolution
        self.res_label.setText(f"Target Resolution: {tw}×{th}")

        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            res = next(v["res"] for v in self.videos if v["path"] == item.data(Qt.ItemDataRole.UserRole))
            txt = f"{res[0]}×{res[1]}"
            if res != self.target_resolution:
                txt += "\nscaled"
            item.setText(txt)

    # ──────────────────────── MERGE WITH NICE ANIMATED FEEDBACK ────────────────────────
    def merge_and_save(self):
        if not self.videos:
            return

        folder = QFileDialog.getExistingDirectory(self, "Select output folder")
        if not folder:
            return

        out_path = os.path.join(folder, "merged.mp4")
        i = 1
        while os.path.exists(out_path):
            out_path = os.path.join(folder, f"merged ({i}).mp4")
            i += 1

        # Start animation
        self.status_label.setText("Working.")
        self.dots = 0
        self.anim_timer.start(300)

        # Run merge in background thread
        self.worker = MergeWorker(self.videos.copy(), self.target_resolution, out_path)
        self.worker.finished.connect(self.on_merge_finished)
        self.worker.failed.connect(self.on_merge_failed)
        self.worker.start()

    def on_merge_finished(self, path):
        self.anim_timer.stop()
        self.status_label.setText('<span style="color:green; font-weight:bold;">Merge Complete!</span>')
        self.last_merged = path
        print(f"Saved: {path}")
        QTimer.singleShot(3000, lambda: self.status_label.setText("Ready"))

    def on_merge_failed(self, error):
        self.anim_timer.stop()
        self.status_label.setText('<span style="color:red;">Merge Failed!</span>')
        print(f"Merge error: {error}")
        QTimer.singleShot(5000, lambda: self.status_label.setText("Ready"))

    def play_last(self):
        if self.last_merged and os.path.exists(self.last_merged):
            if sys.platform.startswith("win"):
                os.startfile(self.last_merged)
            elif sys.platform == "darwin":
                subprocess.call(["open", self.last_merged])
            else:
                subprocess.call(["xdg-open", self.last_merged])


# ──────────────────────────────────────── VideoList (same as last perfect version) ────────────────────────────────────────
class VideoList(QListWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window

        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)

        self.setViewMode(QListWidget.ViewMode.IconMode)
        self.setFlow(QListWidget.Flow.LeftToRight)
        self.setWrapping(True)
        self.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.setMovement(QListWidget.Movement.Free)
        self.setIconSize(QSize(160, 100))
        self.setSpacing(15)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

    def dragEnterEvent(self, event):
        event.acceptProposedAction()

    def dragMoveEvent(self, event):
        event.acceptProposedAction()

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
            for url in event.mimeData().urls():
                path = url.toLocalFile()
                if path.lower().endswith(('.mp4', '.avi', '.mov', '.mkv', '.webm', '.ts', '.wmv', '.flv', '.mpg', '.mpeg')):
                    self.main_window.add_video(path)
        else:
            super().dropEvent(event)
            self.main_window.sync_order()
            QTimer.singleShot(0, lambda: (
                self.setViewMode(QListWidget.ViewMode.ListMode),
                self.setViewMode(QListWidget.ViewMode.IconMode)
            ))
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())