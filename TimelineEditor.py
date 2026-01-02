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
CACHE_FILE = Path(__file__).with_name("timeline_cache.json")
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
                return Path(img).name  # Always use basename
    return None

# ===================== FILE DATABASE =====================
class VideoDatabase:
    def __init__(self):
        self.mp4s = {}
        self.pngs = {}
        self.pred = {}
        self.succ = {}

    def scan_folders(self, folders, cache):
        self.mp4s.clear()
        self.pngs.clear()

        current_folders = set(str(Path(f).resolve()) for f in folders)

        # Clean cache for removed folders
        for cached_folder in list(cache.keys()):
            if cached_folder not in current_folders:
                del cache[cached_folder]

        for folder_str in folders:
            folder = Path(folder_str).resolve()
            folder_key = str(folder)
            if folder_key not in cache:
                cache[folder_key] = {"mp4s": {}, "pngs": {}}
            folder_cache = cache[folder_key]

            current_mp4 = {str(p.resolve()): p.stat().st_mtime for p in folder.rglob("*.mp4")}
            current_png = {str(p.resolve()): p.stat().st_mtime for p in folder.rglob("wan22_lastframe_*.png")}

            # Remove deleted
            for path in list(folder_cache["mp4s"]):
                if path not in current_mp4:
                    del folder_cache["mp4s"][path]
            for path in list(folder_cache["pngs"]):
                if path not in current_png:
                    del folder_cache["pngs"][path]

            # MP4s
            for path, mtime in current_mp4.items():
                if path not in folder_cache["mp4s"] or folder_cache["mp4s"][path]["mtime"] != mtime:
                    ctime = os.path.getctime(path)
                    workflow = extract_workflow_from_mp4(path)
                    input_png = find_input_lastframe_png(workflow)
                    folder_cache["mp4s"][path] = {
                        "time": ctime,
                        "workflow": workflow,
                        "input_png": input_png,
                        "mtime": mtime
                    }
                self.mp4s[path] = folder_cache["mp4s"][path]

            # PNGs
            for path, mtime in current_png.items():
                name = Path(path).name
                if name not in folder_cache["pngs"] or folder_cache["pngs"][name]["mtime"] != mtime:
                    folder_cache["pngs"][name] = {
                        "path": path,
                        "time": mtime,  # Use mtime for matching
                        "mtime": mtime
                    }
                self.pngs[name] = folder_cache["pngs"][name]

        self.build_graph()

    def build_graph(self):
        self.pred.clear()
        self.succ.clear()

        for mp4_path, data in self.mp4s.items():
            input_png = data["input_png"]
            if not input_png or input_png not in self.pngs:
                continue

            png_entry = self.pngs[input_png]
            png_time = png_entry["time"]  # mtime

            candidates = []
            for other_mp4, other_data in self.mp4s.items():
                if other_mp4 == mp4_path:
                    continue
                other_time = other_data["time"]  # mtime
                dt = abs(other_time - png_time)
                if dt < TIME_DELTA:
                    candidates.append((dt, other_time, other_mp4))

            if candidates:
                # Pick the one with smallest time difference
                # If tie, pick the most recent
                candidates.sort(key=lambda x: (x[0], -x[1]))
                predecessor = candidates[0][2]
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
        self.cache = self.load_cache()
        self.current_folders = self.load_config()

        self.root.title("ComfyUI Video Timeline – Drag & Drop a Video Here")
        self.root.geometry("1500x900")
        self.root.configure(bg="#f0f0f0")

        # Status bar
        self.status_var = tk.StringVar(value="Initializing...")
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

        # Canvas
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

        # Mouse wheel
        self.root.bind_all("<MouseWheel>", self.on_mouse_wheel)
        self.root.bind_all("<Button-4>", self.on_mouse_wheel)
        self.root.bind_all("<Button-5>", self.on_mouse_wheel)

        # Drag & Drop
        self.canvas.drop_target_register(DND_FILES)
        self.canvas.dnd_bind('<<Drop>>', self.on_drop)

        # Welcome text
        self.welcome_id = self.canvas.create_text(
            self.root.winfo_screenwidth()//2, 200,
            text="Drag and drop any generated MP4 video here\n"
                 "to build its timeline\n\n"
                 "First add your output folders using the controls above",
            font=("Arial", 16), fill="gray", anchor="center"
        )

        # Auto-refresh
        if self.current_folders:
            self.show_progress_popup()
            Thread(target=self.auto_refresh_on_start, daemon=True).start()
        else:
            self.status_var.set("Ready – Add folders to begin")

    def on_mouse_wheel(self, event):
        if sys.platform == "darwin":
            delta = -event.delta
        elif hasattr(event, "num"):
            delta = 120 if event.num == 4 else -120
        else:
            delta = -event.delta
        self.canvas.yview_scroll(int(delta / 120), "units")

    def show_progress_popup(self):
        self.progress_popup = tk.Toplevel(self.root)
        self.progress_popup.title("Scanning...")
        self.progress_popup.geometry("300x100")
        self.progress_popup.resizable(False, False)
        self.progress_popup.configure(bg="#f0f0f0")
        self.progress_popup.transient(self.root)
        self.progress_popup.grab_set()

        ttk.Label(self.progress_popup, text="Scanning folders and loading cache...", font=("Arial", 10)).pack(pady=15)
        progress = ttk.Progressbar(self.progress_popup, mode="indeterminate", length=220)
        progress.pack(pady=10)
        progress.start(10)

        self.root.update_idletasks()
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = (screen_w - 300) // 2
        y = (screen_h - 100) // 2
        self.progress_popup.geometry(f"300x100+{x}+{y}")
        self.progress_popup.lift()

    def close_progress_popup(self):
        if hasattr(self, "progress_popup"):
            try:
                self.progress_popup.destroy()
            except:
                pass

    def auto_refresh_on_start(self):
        self.db.scan_folders(self.current_folders, self.cache)
        self.save_cache()
        self.root.after(0, self.close_progress_popup)
        self.root.after(0, lambda: self.canvas.delete(self.welcome_id))
        self.root.after(0, lambda: self.status_var.set(
            f"Ready – {len(self.db.mp4s)} videos, {len(self.db.pngs)} last-frames loaded"
        ))

    def load_config(self):
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return [str(Path(p).resolve()) for p in data.get("folders", [])]
            except Exception:
                pass
        return []

    def load_cache(self):
        if CACHE_FILE.exists():
            try:
                with open(CACHE_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def save_config(self):
        folders = [f.strip() for f in self.folder_var.get().split(";") if f.strip()]
        resolved = [str(Path(f).resolve()) for f in folders]
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump({"folders": resolved}, f, indent=4)
        except Exception as e:
            messagebox.showerror("Error", f"Could not save config: {e}")

    def save_cache(self):
        try:
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, indent=4)
        except Exception:
            pass

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
            messagebox.showwarning("Warning", "Add at least one folder first.")
            return
        self.current_folders = [str(Path(f).resolve()) for f in folders]
        self.save_config()
        self.show_progress_popup()
        Thread(target=self.perform_scan, daemon=True).start()

    def perform_scan(self):
        self.db.scan_folders(self.current_folders, self.cache)
        self.save_cache()
        self.root.after(0, self.close_progress_popup)
        self.root.after(0, lambda: self.canvas.delete(self.welcome_id))
        self.root.after(0, lambda: self.status_var.set(
            f"Ready – {len(self.db.mp4s)} videos, {len(self.db.pngs)} last-frames loaded"
        ))
        messagebox.showinfo("Scan Complete", f"Found {len(self.db.mp4s)} videos.")

    def on_drop(self, event):
        path = self.get_dropped_path(event)
        if path:
            self.process_video_path(path)

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
            return None
        return path

    def process_video_path(self, video_path):
        if video_path not in self.db.mp4s:
            messagebox.showerror("Invalid Video", "Video not found in database. Refresh first.")
            return

        choice = messagebox.askyesno(
            "Timeline Direction",
            f"Video: {Path(video_path).name}\n\n"
            "Yes → Backward chain\n"
            "No → Forward tree"
        )
        if choice:
            self.show_backward(video_path)
        else:
            self.show_forward(video_path)

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
        level_height = 420
        node_positions = {}
        for level, videos in levels.items():
            y = y_start + level * level_height
            num_videos = len(videos)
            # Generous minimum spacing per node
            min_spacing = 450
            # Use wider canvas area
            available_width = 2200
            spacing = max(min_spacing, available_width // max(1, num_videos))
            total_width = (num_videos - 1) * spacing + NODE_WIDTH
            x_start = max(50, (available_width - total_width) // 2)
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
                    self.canvas.create_line(px, py + 60, cx, cy - 60, arrow=tk.LAST, fill="gray", width=2)

        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def create_node(self, mp4_path, x, y):
        frame = ttk.Frame(self.canvas, relief="groove", borderwidth=3, width=NODE_WIDTH, height=NODE_HEIGHT)
        frame.pack_propagate(False)
        self.canvas.create_window(x, y, window=frame, anchor="nw")

        # Thumbnails
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

        # Button rows: 3 buttons on top row, 2 on bottom
        btn_frame_top = ttk.Frame(frame)
        btn_frame_top.pack(pady=4, fill=tk.X, padx=20)

        ttk.Button(btn_frame_top, text="Play Video", width=14,
                   command=lambda: self.play_video(mp4_path)).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame_top, text="Preview Up To", width=16,
                   command=lambda: self.preview_up_to(mp4_path)).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame_top, text="Save Combined", width=16,
                   command=lambda: self.save_combined(mp4_path)).pack(side=tk.LEFT, padx=5)

        btn_frame_bottom = ttk.Frame(frame)
        btn_frame_bottom.pack(pady=4, fill=tk.X, padx=20)

        ttk.Button(btn_frame_bottom, text="Show in Explorer", width=16,
                   command=lambda p=mp4_path: self.open_in_explorer(p)).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame_bottom, text="Use as Input", width=14,
                   command=lambda: self.process_video_path(mp4_path)).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame_bottom, text="📋 Copy Prompt", width=16,
                   command=lambda p=mp4_path: self.copy_prompt(p)).pack(side=tk.LEFT, padx=5)

        # Filename label
        ttk.Label(frame, text=Path(mp4_path).name, font=("Arial", 9), foreground="gray", anchor="center").pack(pady=5, fill=tk.X)

    def copy_prompt(self, mp4_path):
        if mp4_path not in self.db.mp4s:
            return
        workflow = self.db.mp4s[mp4_path].get("workflow")
        if not workflow:
            messagebox.showinfo("No Prompt", "No workflow found in this video.")
            return

        prompt = None
        for node_id, node in workflow.items():
            if node.get("class_type") == "CLIPTextEncode" or node.get("class_type") == "Prompt":  # Common prompt nodes
                prompt = node["inputs"].get("text")
                if prompt:
                    break
            # Fallback: look for node ID "201" as you mentioned
            if node_id == "201" and "text" in node["inputs"]:
                prompt = node["inputs"]["text"]
                break

        if prompt:
            self.root.clipboard_clear()
            self.root.clipboard_append(prompt.strip())
            self.root.update()  # Makes clipboard persist after app closes
            messagebox.showinfo("Prompt Copied", f"Prompt copied to clipboard!\n\n{prompt[:100]}{'...' if len(prompt) > 100 else ''}")
        else:
            messagebox.showinfo("No Prompt", "No text prompt found in workflow.")
    
    def find_output_png(self, mp4_path):
        # Find all successors of this MP4
        successors = self.db.succ.get(mp4_path, [])
        if not successors:
            return None  # No successors → no output PNG (end of chain)

        # Take the input PNG from the first successor
        first_successor = successors[0]
        input_png_name = self.db.mp4s.get(first_successor, {}).get("input_png")
        if input_png_name and input_png_name in self.db.pngs:
            return self.db.pngs[input_png_name]["path"]

        # Fallback: if something went wrong, try time-based (rare)
        mp4_time = self.db.mp4s[mp4_path]["time"]
        candidates = []
        for name, data in self.db.pngs.items():
            if data["time"] > mp4_time and abs(data["time"] - mp4_time) < 180:
                candidates.append((abs(data["time"] - mp4_time), data["path"]))
        if candidates:
            candidates.sort()
            return candidates[0][1]

        return None

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