#!/usr/bin/env python3

import os
import json
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from datetime import datetime
from PIL import Image, ImageTk
from moviepy.editor import VideoFileClip
from mutagen.mp4 import MP4
import subprocess
import sys

# ===================== CONFIG =====================
THUMB_SIZE = (160, 160)
GRID_COLS = 6
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
    except Exception as e:
        print(f"Error extracting workflow: {e}")
        return None

# ===================== MAIN APP =====================
class ClipTrimmerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Clip Trimmer – Drag & Drop an MP4 Video Here")
        self.root.geometry("1000x700")
        self.root.configure(bg="#f0f0f0")

        # Status bar
        self.status_var = tk.StringVar(value="Ready – Drag an MP4 video here")
        status_bar = ttk.Label(root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        # Canvas for grid
        canvas_frame = ttk.Frame(root)
        canvas_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.canvas = tk.Canvas(canvas_frame, bg="white", highlightthickness=0)
        v_scroll = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=self.canvas.yview)
        h_scroll = ttk.Scrollbar(root, orient=tk.HORIZONTAL, command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set)

        self.canvas.grid(row=0, column=0, sticky="nsew")
        v_scroll.grid(row=0, column=1, sticky="ns")
        h_scroll.pack(fill=tk.X, side=tk.BOTTOM)

        canvas_frame.grid_rowconfigure(0, weight=1)
        canvas_frame.grid_columnconfigure(0, weight=1)

        # Mouse wheel scrolling (fixed)
        self.canvas.bind("<MouseWheel>", self.on_mouse_wheel)  # Windows
        self.canvas.bind("<Button-4>", self.on_mouse_wheel)    # Linux up
        self.canvas.bind("<Button-5>", self.on_mouse_wheel)    # Linux down

        # Drag & Drop
        self.canvas.drop_target_register(DND_FILES)
        self.canvas.dnd_bind('<<Drop>>', self.on_drop)

        self.frames = []
        self.thumbs = []
        self.selected_frame = None
        self.video_path = None
        self.workflow = None
        self.fps = 30

        # Save button
        self.save_button = ttk.Button(root, text="Save New Clip & Last Frame", command=self.save_new_clip, state=tk.DISABLED)
        self.save_button.pack(pady=10)

    def on_mouse_wheel(self, event):
        if event.num == 4 or event.delta > 0:
            self.canvas.yview_scroll(-1, "units")
        elif event.num == 5 or event.delta < 0:
            self.canvas.yview_scroll(1, "units")

    def on_drop(self, event):
        files = self.root.tk.splitlist(event.data)
        mp4_files = [f.strip("{}") for f in files if f.lower().endswith(".mp4")]
        if not mp4_files:
            messagebox.showwarning("Invalid File", "Please drop an MP4 video file.")
            return

        self.video_path = Path(mp4_files[0]).resolve()
        self.load_video()

    def load_video(self):
        try:
            clip = VideoFileClip(str(self.video_path))
            self.fps = clip.fps
            duration = clip.duration
            num_frames = int(duration * self.fps) + 1
            self.frames = []
            for i in range(num_frames):
                t = min(i / self.fps, duration)
                frame = clip.get_frame(t)
                self.frames.append(frame)
            clip.close()
        except Exception as e:
            messagebox.showerror("Error", f"Could not load video:\n{e}")
            return

        self.workflow = extract_workflow_from_mp4(str(self.video_path))

        self.display_frames()
        self.save_button['state'] = tk.NORMAL
        self.status_var.set(f"Loaded {len(self.frames)} frames from {self.video_path.name}")

    def display_frames(self):
        self.canvas.delete("all")
        self.thumbs = []

        num_frames = len(self.frames)
        cols = max(GRID_COLS, self.canvas.winfo_width() // (THUMB_SIZE[0] + 30))
        rows = (num_frames + cols - 1) // cols

        for i in range(num_frames):
            row = i // cols
            col = i % cols
            img = Image.fromarray(self.frames[i])
            thumb = img.resize(THUMB_SIZE, Image.LANCZOS)
            tk_thumb = ImageTk.PhotoImage(thumb)
            self.thumbs.append(tk_thumb)

            x = col * (THUMB_SIZE[0] + 30) + 20
            y = row * (THUMB_SIZE[1] + 40) + 20

            self.canvas.create_image(x, y, image=tk_thumb, anchor=tk.NW, tags=("frame", str(i)))

            if self.selected_frame == i:
                self.canvas.create_rectangle(
                    x - 5, y - 5,
                    x + THUMB_SIZE[0] + 5, y + THUMB_SIZE[1] + 5,
                    outline="red", width=4
                )

            self.canvas.create_text(x + THUMB_SIZE[0]//2, y + THUMB_SIZE[1] + 15,
                                    text=str(i+1), font=("Arial", 8), fill="gray")

        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self.canvas.tag_bind("frame", "<Double-Button-1>", self.show_full_frame)

    def show_full_frame(self, event):
        item = self.canvas.find_closest(event.x, event.y)[0]
        tags = self.canvas.gettags(item)
        if "frame" in tags:
            frame_idx = int(tags[1])
            self.open_frame_viewer(frame_idx)

    def open_frame_viewer(self, start_idx):
        if not (0 <= start_idx < len(self.frames)):
            return

        current_idx = [start_idx]  # Mutable list to track current index

        popup = tk.Toplevel(self.root)
        popup.title(f"Frame {start_idx + 1} / {len(self.frames)}")
        popup.focus_force()
        popup.grab_set()

        # Initial image
        def update_display(idx):
            if 0 <= idx < len(self.frames):
                current_idx[0] = idx
                img = Image.fromarray(self.frames[idx])
                screen_w = popup.winfo_screenwidth()
                screen_h = popup.winfo_screenheight()
                ratio = min((screen_w - 100) / img.width, (screen_h - 100) / img.height, 1)
                new_size = (int(img.width * ratio), int(img.height * ratio))
                resized = img.resize(new_size, Image.LANCZOS)
                tk_img = ImageTk.PhotoImage(resized)

                label.configure(image=tk_img)
                label.image = tk_img  # Keep reference
                popup.geometry(f"{new_size[0]}x{new_size[1]}")
                popup.title(f"Frame {idx + 1} / {len(self.frames)}")

        # Create label (now defined before use)
        label = ttk.Label(popup)
        label.pack()

        # Load initial frame
        update_display(start_idx)

        # Key bindings
        popup.bind("<Left>", lambda e: update_display(current_idx[0] - 1))
        popup.bind("<Right>", lambda e: update_display(current_idx[0] + 1))
        popup.bind("<Escape>", lambda e: popup.destroy())
        popup.bind("<Return>", lambda e: (self.select_frame(current_idx[0]), popup.destroy()))

    def select_frame(self, idx):
        self.selected_frame = idx
        self.display_frames()
        self.status_var.set(f"Selected frame {idx + 1} as new last frame")

    def save_new_clip(self):
        if self.selected_frame is None:
            messagebox.showwarning("No Selection", "Please select a frame first.")
            return

        output_dir = filedialog.askdirectory(title="Select Output Folder")
        if not output_dir:
            return
        output_dir = Path(output_dir)

        now = datetime.now()
        timestamp = now.strftime("%d%m%H%M")
        new_mp4 = output_dir / f"wan22_{timestamp}.mp4"
        new_png = output_dir / f"wan22_lastframe_{timestamp}_.png"

        # Save PNG
        img = Image.fromarray(self.frames[self.selected_frame])
        img.save(new_png)

        # Save trimmed high-quality MP4
        end_time = (self.selected_frame + 1) / self.fps
        cmd = [
            FFMPEG, "-y",
            "-i", str(self.video_path),
            "-t", f"{end_time:.3f}",
            "-c:v", "libx264",
            "-preset", "veryslow",
            "-crf", "17",
            "-pix_fmt", "yuv420p",
            "-avoid_negative_ts", "make_zero",
            str(new_mp4)
        ]
        result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        if result.returncode != 0:
            messagebox.showerror("Error", f"Failed to save clip:\n{result.stderr.decode(errors='ignore')}")
            return

        # Re-embed workflow
        if self.workflow:
            try:
                new_video = MP4(str(new_mp4))
                original = MP4(str(self.video_path))
                if "\xa9cmt" in original.tags:
                    new_video.tags["\xa9cmt"] = original.tags["\xa9cmt"]
                    new_video.save()
            except Exception as e:
                print(f"Workflow embed failed: {e}")

        messagebox.showinfo("Success", f"Saved:\n{new_mp4.name}\n{new_png.name}")
        self.status_var.set("Ready")

# ===================== DRAG & DROP SETUP =====================
try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
except ImportError:
    messagebox.showerror("Missing Dependency",
                         "Drag & Drop requires tkinterdnd2.\n\n"
                         "Install with:\n    pip install tkinterdnd2")
    raise

# ===================== MAIN =====================
def main():
    root = TkinterDnD.Tk()
    app = ClipTrimmerApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()