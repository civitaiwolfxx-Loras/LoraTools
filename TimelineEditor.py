#!/usr/bin/env python3

import os
import json
import re
import subprocess
import tempfile
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from datetime import datetime
from PIL import Image, ImageTk
from moviepy.editor import VideoFileClip
from mutagen.mp4 import MP4
from threading import Thread
import sys

# ===================== CONFIG =====================
CONFIG_FILE = Path(__file__).with_name("timeline_config.json")
THUMB_SIZE = (160, 160)
NODE_WIDTH = 620
NODE_HEIGHT = 300
TIME_DELTA = 30
PNG_PATTERN = re.compile(r'^wan22_lastframe_.*\.png$', re.IGNORECASE)
FFMPEG = "ffmpeg"

# ===================== METADATA EXTRACTION =====================
def extract_workflow_from_mp4(mp4_path):
    try:
        video = MP4(mp4_path)
        if "\xa9cmt" not in video.tags:
            return None
        raw = str(video.tags["\xa9cmt"][0])
        outer = json.loads(raw)
        if "prompt" in outer:
            return json.loads(outer["prompt"])
        if "workflow" in outer:
            return outer["workflow"]
    except Exception:
        return None
    return None

def find_input_lastframe_png(workflow):
    if not workflow:
        return None
    for node in workflow.values():
        if node.get("class_type") == "LoadImage":
            img = node["inputs"].get("image", "")
            if PNG_PATTERN.match(img):
                return img
    return None

# ===================== FILE DATABASE =====================
class VideoDatabase:
    def __init__(self):
        self.mp4s = {}
        self.pngs = {}
        self.pred = {}
        self.succ = {}

    def scan_folders(self, folders):
        self.mp4s.clear()
        self.pngs.clear()
        for folder_str in folders:
            folder = Path(folder_str)
            if not folder.is_dir():
                continue
            for path in folder.rglob("*.mp4"):
                full_path = str(path.resolve())
                ctime = path.stat().st_ctime
                workflow = extract_workflow_from_mp4(full_path)
                input_png = find_input_lastframe_png(workflow)
                self.mp4s[full_path] = {
                    "time": ctime,
                    "workflow": workflow,
                    "input_png": input_png
                }
            for path in folder.rglob("wan22_lastframe_*.png"):
                self.pngs[path.name] = {
                    "path": str(path.resolve()),
                    "time": path.stat().st_ctime
                }
        self.build_graph()

    def build_graph(self):
        self.pred.clear()
        self.succ.clear()
        for mp4_path, data in self.mp4s.items():
            input_png = data["input_png"]
            if not input_png or input_png not in self.pngs:
                continue
            png_time = self.pngs[input_png]["time"]
            candidates = []
            for other_mp4, other_data in self.mp4s.items():
                if other_mp4 == mp4_path:
                    continue
                dt = abs(other_data["time"] - png_time)
                if dt < TIME_DELTA and other_data["time"] < png_time:
                    candidates.append((dt, other_mp4))
            if candidates:
                candidates.sort()
                predecessor = candidates[0][1]
                self.pred[mp4_path] = predecessor
                self.succ.setdefault(predecessor, []).append(mp4_path)

    def get_backward_chain(self, start_mp4):
        chain = []
        current = start_mp4
        while current:
            chain.append(current)
            current = self.pred.get(current)
        chain.reverse()
        return chain

    def get_forward_tree(self, start_mp4):
        tree = {}
        def recurse(mp4):
            children = self.succ.get(mp4, [])
            tree[mp4] = children
            for child in children:
                recurse(child)
        recurse(start_mp4)
        return tree

# ===================== DRAG & DROP SETUP =====================
try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
except ImportError:
    messagebox.showerror("Missing Dependency",
                         "Drag & Drop requires tkinterdnd2.\n\n"
                         "Install with:\n    pip install tkinterdnd2")
    raise

# ===================== MAIN APP =====================
class TimelineApp:
    def __init__(self, root):
        self.root = root
        self.db = VideoDatabase()
        self.thumbnails = {}
        self.current_folders = self.load_config()

        self.root.title("ComfyUI Video Timeline – Drag & Drop a Video Here")
        self.root.geometry("1500x900")
        self.root.configure(bg="#f0f0f0")

        # Status bar
        self.status_var = tk.StringVar(value="Loading configuration...")
        status_bar = ttk.Label(root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        # Top bar
        top_frame = ttk.Frame(root)
        top_frame.pack(fill=tk.X, padx=10, pady=10)

        ttk.Label(top_frame, text="Working Folders:").pack(side=tk.LEFT)
        self.folder_var = tk.StringVar(value="; ".join(self.current_folders))
        ttk.Entry(top_frame, textvariable=self.folder_var, width=100).pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

        ttk.Button(top_frame, text="Add Folder", command=self.add_folder).pack(side=tk.LEFT, padx=5)
        ttk.Button(top_frame, text="Save & Refresh", command=self.save_and_refresh).pack(side=tk.LEFT, padx=5)

        # Canvas frame
        canvas_frame = ttk.Frame(root)
        canvas_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0,10))

        self.canvas = tk.Canvas(canvas_frame, bg="white", highlightthickness=0)
        v_scroll = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=self.canvas.yview)
        h_scroll = ttk.Scrollbar(root, orient=tk.HORIZONTAL, command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set)

        self.canvas.grid(row=0, column=0, sticky="nsew")
        v_scroll.grid(row=0, column=1, sticky="ns")
        h_scroll.pack(fill=tk.X, side=tk.BOTTOM)

        canvas_frame.grid_rowconfigure(0, weight=1)
        canvas_frame.grid_columnconfigure(0, weight=1)

        # Mouse wheel scrolling (cross-platform)
        self.canvas.bind_all("<MouseWheel>", self.on_mouse_wheel)        # Windows
        self.canvas.bind_all("<Button-4>", self.on_mouse_wheel)          # Linux scroll up
        self.canvas.bind_all("<Button-5>", self.on_mouse_wheel)          # Linux scroll down

        # Drag & Drop on canvas
        self.canvas.drop_target_register(DND_FILES)
        self.canvas.dnd_bind('<<Drop>>', self.on_drop)

        # Welcome text
        self.welcome_text = self.canvas.create_text(
            self.root.winfo_screenwidth()//2, 200,
            text="Drag and drop any generated MP4 video here\n"
                 "to build its timeline\n\n"
                 "First add your output folders using the controls above",
            font=("Arial", 16), fill="gray", anchor="center", tags="welcome"
        )

        # Auto-refresh on startup
        if self.current_folders and self.current_folders != ["."]:
            self.show_progress_popup()
            Thread(target=self.auto_refresh_on_start, daemon=True).start()

    def on_mouse_wheel(self, event):
        if sys.platform == "darwin":
            scroll_amount = -1 * (event.delta)
        elif event.num == 4:
            scroll_amount = -120
        elif event.num == 5:
            scroll_amount = 120
        else:
            scroll_amount = -1 * event.delta
        self.canvas.yview_scroll(int(scroll_amount / 120), "units")

    def show_progress_popup(self):
        self.progress_popup = tk.Toplevel(self.root)
        self.progress_popup.title("Scanning...")
        self.progress_popup.geometry("300x100")
        self.progress_popup.resizable(False, False)
        self.progress_popup.transient(self.root)
        self.progress_popup.grab_set()

        label = ttk.Label(self.progress_popup, text="Scanning folders and building graph...")
        label.pack(pady=15)

        progress = ttk.Progressbar(self.progress_popup, mode="indeterminate", length=200)
        progress.pack(pady=10)
        progress.start()

        # Center on parent
        self.root.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - 150
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - 50
        self.progress_popup.geometry(f"+{x}+{y}")

    def close_progress_popup(self):
        if hasattr(self, "progress_popup") and self.progress_popup.winfo_exists():
            self.progress_popup.destroy()

    def auto_refresh_on_start(self):
        self.current_folders = [str(Path(f).resolve()) for f in self.current_folders]
        self.db.scan_folders(self.current_folders)
        self.root.after(0, self.close_progress_popup)
        self.canvas.delete("welcome")
        self.status_var.set(f"Ready – {len(self.db.mp4s)} videos, {len(self.db.pngs)} last-frames loaded")

    def load_config(self):
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return [str(Path(p).resolve()) for p in data.get("folders", [])]
            except Exception:
                pass
        return []

    def save_config(self):
        folders = [f.strip() for f in self.folder_var.get().split(";") if f.strip()]
        resolved = [str(Path(f).resolve()) for f in folders]
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump({"folders": resolved}, f, indent=4)
        except Exception as e:
            messagebox.showerror("Error", f"Could not save config: {e}")

    def add_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            resolved = str(Path(folder).resolve())
            current = [f.strip() for f in self.folder_var.get().split(";") if f.strip()]
            if resolved not in current:
                current.append(resolved)
                self.folder_var.set("; ".join(current))

    def save_and_refresh(self):
        folders = [f.strip() for f in self.folder_var.get().split(";") if f.strip()]
        if not folders:
            messagebox.showwarning("Warning", "Please add at least one working folder first.")
            return
        self.show_progress_popup()
        self.current_folders = [str(Path(f).resolve()) for f in folders]
        self.save_config()
        Thread(target=self.perform_scan, daemon=True).start()

    def perform_scan(self):
        self.db.scan_folders(self.current_folders)
        self.root.after(0, self.close_progress_popup)
        self.canvas.delete("welcome")
        self.status_var.set(f"Ready – {len(self.db.mp4s)} videos, {len(self.db.pngs)} last-frames loaded")
        messagebox.showinfo("Scan Complete", f"Found {len(self.db.mp4s)} videos.")

    def on_drop(self, event):
        self.process_video_path(self.get_dropped_path(event))

    def process_video_path(self, video_path):
        if not video_path or video_path not in self.db.mp4s:
            messagebox.showerror("Invalid Video", "Video not found in database. Refresh folders first.")
            return

        choice = messagebox.askyesno(
            "Timeline Direction",
            f"Video: {Path(video_path).name}\n\n"
            "Yes → Backward chain (to root)\n"
            "No → Forward tree (continuations)"
        )
        if choice:
            self.show_backward(video_path)
        else:
            self.show_forward(video_path)

    def get_dropped_path(self, event):
        files = self.root.tk.splitlist(event.data)
        mp4_files = [f.strip("{}") for f in files if f.lower().endswith(".mp4")]
        if not mp4_files:
            return None
        path = str(Path(mp4_files[0]).resolve())
        folder = str(Path(path).parent.resolve())
        if folder not in self.current_folders:
            if messagebox.askyesno("Add Folder?", f"Add folder?\n{folder}"):
                current = [f.strip() for f in self.folder_var.get().split(";") if f.strip()]
                current.append(folder)
                self.folder_var.set("; ".join(current))
                self.save_and_refresh()
            else:
                return None
        return path

    def preload_thumbs(self, mp4_list):
        self.thumbnails.clear()
        for mp4 in mp4_list:
            try:
                with VideoFileClip(mp4) as clip:
                    first = Image.fromarray(clip.get_frame(0)).resize(THUMB_SIZE)
                    last = Image.fromarray(clip.get_frame(clip.duration - 0.04)).resize(THUMB_SIZE)
                self.thumbnails[mp4] = (ImageTk.PhotoImage(first), ImageTk.PhotoImage(last))
            except Exception as e:
                print(f"Thumb error {mp4}: {e}")

    def show_backward(self, start_mp4):
        chain = self.db.get_backward_chain(start_mp4)
        self.preload_thumbs(chain)
        self.draw_linear(chain, f"Backward Chain → {Path(start_mp4).name}")

    def show_forward(self, start_mp4):
        tree = self.db.get_forward_tree(start_mp4)
        all_videos = set([start_mp4])
        for children in tree.values():
            all_videos.update(children)
        self.preload_thumbs(all_videos)
        self.draw_tree(tree, start_mp4)

    def draw_linear(self, chain, title):
        self.canvas.delete("all")
        self.canvas.create_text(20, 20, text=title, anchor="nw", font=("Arial", 14, "bold"))

        num_nodes = len(chain)
        spacing = max(150, (self.canvas.winfo_width() - num_nodes * NODE_WIDTH) // max(1, num_nodes + 1))

        x = spacing
        y = 100

        for i, mp4 in enumerate(chain):
            self.create_node(mp4, x, y)
            if i < len(chain) - 1:
                self.canvas.create_line(
                    x + NODE_WIDTH // 2, y + NODE_HEIGHT // 2,
                    x + NODE_WIDTH // 2 + spacing, y + NODE_HEIGHT // 2,
                    arrow=tk.LAST, width=4, fill="steelblue"
                )
            x += NODE_WIDTH + spacing

        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def draw_tree(self, tree, root_mp4):
        self.canvas.delete("all")
        self.canvas.create_text(20, 20, text=f"Forward Tree from {Path(root_mp4).name}", anchor="nw", font=("Arial", 14, "bold"))

        levels = {}
        queue = [(root_mp4, 0)]
        visited = set()
        while queue:
            mp4, level = queue.pop(0)
            if mp4 in visited: continue
            visited.add(mp4)
            levels.setdefault(level, []).append(mp4)
            for child in tree.get(mp4, []):
                queue.append((child, level + 1))

        y_start = 100
        level_height = 380
        node_positions = {}
        for level, videos in levels.items():
            y = y_start + level * level_height
            num_videos = len(videos)
            spacing = max(300, 1600 // max(1, num_videos))
            total_width = (num_videos - 1) * spacing + NODE_WIDTH
            x_start = max(50, (1600 - total_width) // 2)
            for i, mp4 in enumerate(videos):
                x = x_start + i * spacing
                node_positions[mp4] = (x + NODE_WIDTH // 2, y + NODE_HEIGHT // 2)
                self.create_node(mp4, x, y)

        for parent, children in tree.items():
            if parent not in node_positions:
                continue
            px, py = node_positions[parent]
            for child in children:
                if child in node_positions:
                    cx, cy = node_positions[child]
                    self.canvas.create_line(
                        px, py + 60,
                        cx, cy - 60,
                        arrow=tk.LAST, fill="gray", width=2
                    )

        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def create_node(self, mp4_path, x, y):
        frame = ttk.Frame(self.canvas, relief="groove", borderwidth=3, width=NODE_WIDTH, height=NODE_HEIGHT)
        frame.pack_propagate(False)
        self.canvas.create_window(x, y, window=frame, anchor="nw")

        thumb_frame = ttk.Frame(frame)
        thumb_frame.pack(pady=10)
        first_tk, last_tk = self.thumbnails.get(mp4_path, (None, None))
        if first_tk:
            lbl_first = ttk.Label(thumb_frame, image=first_tk)
            lbl_first.pack(side=tk.LEFT, padx=10)
            lbl_first.bind("<Double-Button-1>", lambda e: self.show_large(mp4_path, True))
        if last_tk:
            lbl_last = ttk.Label(thumb_frame, image=last_tk)
            lbl_last.pack(side=tk.LEFT, padx=10)
            lbl_last.bind("<Double-Button-1>", lambda e: self.show_large(mp4_path, False))

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(pady=8, fill=tk.X, padx=15)

        ttk.Button(btn_frame, text="Play Video", width=14,
                   command=lambda: self.play_video(mp4_path)).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="Preview Up To", width=16,
                   command=lambda: self.preview_up_to(mp4_path)).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="Save Combined", width=16,
                   command=lambda: self.save_combined(mp4_path)).pack(side=tk.LEFT, padx=4)
        output_png = self.find_output_png(mp4_path)
        if output_png:
            ttk.Button(btn_frame, text="Open Last PNG", width=16,
                       command=lambda: self.open_in_explorer(output_png)).pack(side=tk.LEFT, padx=4)

        # NEW BUTTON: Use as Input
        ttk.Button(btn_frame, text="Use as Input", width=14,
                   command=lambda: self.process_video_path(mp4_path)).pack(side=tk.LEFT, padx=4)

        ttk.Label(frame, text=Path(mp4_path).name, font=("Arial", 9), foreground="gray", anchor="center").pack(pady=5, fill=tk.X)

    def find_output_png(self, mp4_path):
        if mp4_path not in self.db.mp4s:
            return None
        mp4_time = self.db.mp4s[mp4_path]["time"]
        candidates = [
            (data["time"], data["path"])
            for data in self.db.pngs.values()
            if data["time"] > mp4_time and abs(data["time"] - mp4_time) < TIME_DELTA
        ]
        if candidates:
            candidates.sort()
            return candidates[0][1]
        return None

    # ... (rest of methods: play_video, get_videos_up_to, preview_up_to, save_combined, concat_videos, open_in_explorer, show_large remain the same as previous version)

    def play_video(self, mp4_path):
        if os.name == "nt":
            os.startfile(mp4_path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", mp4_path])
        else:
            subprocess.Popen(["xdg-open", mp4_path])

    def get_videos_up_to(self, target_mp4):
        chain = []
        current = target_mp4
        while current:
            chain.append(current)
            current = self.db.pred.get(current)
        chain.reverse()
        return chain

    def preview_up_to(self, target_mp4):
        videos = self.get_videos_up_to(target_mp4)
        if len(videos) == 1:
            self.play_video(videos[0])
            return
        self.status_var.set(f"Combining {len(videos)} clips (fast preview)...")
        self.root.update_idletasks()
        temp_path = self.concat_videos(videos, high_quality=False)
        self.status_var.set(f"Ready – {len(self.db.mp4s)} videos loaded")
        if temp_path:
            self.play_video(temp_path)

    def save_combined(self, target_mp4):
        videos = self.get_videos_up_to(target_mp4)
        if len(videos) <= 1:
            messagebox.showinfo("Nothing to combine", "Only one video selected.")
            return
        default_name = Path(target_mp4).parent / f"combined_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
        out_path = filedialog.asksaveasfilename(
            initialfile=default_name.name,
            initialdir=default_name.parent,
            defaultextension=".mp4",
            filetypes=[("MP4 files", "*.mp4")]
        )
        if not out_path:
            return
        self.status_var.set(f"Saving lossless combined video ({len(videos)} clips)...")
        self.root.update_idletasks()
        result_path = self.concat_videos(videos, output_path=out_path, high_quality=True)
        self.status_var.set(f"Ready – {len(self.db.mp4s)} videos loaded")
        if result_path:
            messagebox.showinfo("Success", f"Combined video saved:\n{out_path}")

    def concat_videos(self, video_list, output_path=None, high_quality=False):
        if not video_list:
            return None
        if len(video_list) == 1:
            return video_list[0]

        if output_path is None:
            fd, output_path = tempfile.mkstemp(suffix=".mp4")
            os.close(fd)

        preset = "veryslow" if high_quality else "veryfast"
        crf = "17" if high_quality else "23"

        list_path = tempfile.mktemp(suffix=".txt")
        with open(list_path, "w", encoding="utf-8") as f:
            for v in video_list:
                escaped = v.replace("'", "'\\''")
                f.write(f"file '{escaped}'\n")

        cmd = [
            FFMPEG, "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", list_path,
            "-c:v", "libx264",
            "-preset", preset,
            "-crf", crf,
            "-pix_fmt", "yuv420p",
            output_path
        ]

        result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        os.remove(list_path)

        if result.returncode != 0:
            print("FFmpeg error:", result.stderr.decode(errors='ignore'))
            messagebox.showerror("Concat Failed", "Could not combine videos.")
            if os.path.exists(output_path):
                os.remove(output_path)
            return None

        return output_path

    def open_in_explorer(self, path):
        path = os.path.normpath(path)
        if os.name == "nt":
            subprocess.Popen(f'explorer /select,"{path}"')
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", path])
        else:
            subprocess.Popen(["xdg-open", os.path.dirname(path)])

    def show_large(self, mp4_path, is_first):
        try:
            with VideoFileClip(mp4_path) as clip:
                t = 0 if is_first else clip.duration - 0.04
                frame = clip.get_frame(t)
            img = Image.fromarray(frame)
            ratio = min(1920/img.width, 1080/img.height, 1)
            new_size = (int(img.width * ratio), int(img.height * ratio))
            img = img.resize(new_size, Image.Resampling.LANCZOS)
            tk_img = ImageTk.PhotoImage(img)

            popup = tk.Toplevel(self.root)
            popup.title(Path(mp4_path).name + (" - First Frame" if is_first else " - Last Frame"))
            popup.geometry(f"{new_size[0]}x{new_size[1]}")
            popup.resizable(False, False)
            lbl = ttk.Label(popup, image=tk_img)
            lbl.image = tk_img
            lbl.pack()
            popup.bind("<Escape>", lambda e: popup.destroy())
            popup.focus_force()
        except Exception as e:
            messagebox.showerror("Error", f"Could not load frame:\n{e}")

# ===================== MAIN =====================
def main():
    root = TkinterDnD.Tk()
    app = TimelineApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()