import cv2
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from PIL import Image, ImageTk
import numpy as np
import os

class VideoFrameEditor:
    def __init__(self, root):
        self.root = root
        self.root.title("Video Frame Editor")
        
        # Variables
        self.video_path = ""
        self.frames = []
        self.selected_frames = set()
        self.photo_images = []
        self.selection_rects = {}  # To store selection rectangles
        
        # GUI Setup
        self.setup_gui()
        
        # Drag and drop setup
        self.root.drop_target_register(DND_FILES)
        self.root.dnd_bind('<<Drop>>', self.handle_drop)
        
    def setup_gui(self):
        self.open_btn = ttk.Button(self.root, text="Open Video", command=self.open_video)
        self.open_btn.pack(pady=5)
        
        self.canvas_frame = ttk.Frame(self.root)
        self.canvas_frame.pack(pady=5, fill=tk.BOTH, expand=True)
        
        self.canvas = tk.Canvas(self.canvas_frame, bg='gray')
        self.v_scrollbar = ttk.Scrollbar(self.canvas_frame, orient=tk.VERTICAL, command=self.canvas.yview)
        self.h_scrollbar = ttk.Scrollbar(self.canvas_frame, orient=tk.HORIZONTAL, command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=self.v_scrollbar.set, xscrollcommand=self.h_scrollbar.set)
        
        self.v_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.h_scrollbar.pack(side=tk.BOTTOM, fill=tk.X)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        self.save_btn = ttk.Button(self.root, text="Save Video", command=self.save_video)
        self.save_btn.pack(pady=5)
        
        self.root.bind('<Delete>', self.delete_selected_frames)
        self.root.bind('<Escape>', self.close_popup)
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        
    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        
    def handle_drop(self, event):
        file_path = event.data
        if file_path.startswith('{') and file_path.endswith('}'):
            file_path = file_path[1:-1]
        if os.path.splitext(file_path)[1].lower() in ['.mp4', '.avi', '.mov']:
            self.load_video(file_path)
        
    def open_video(self):
        file_path = filedialog.askopenfilename(filetypes=[("Video files", "*.mp4 *.avi *.mov")])
        if file_path:
            self.load_video(file_path)
            
    def load_video(self, file_path):
        self.video_path = file_path
        self.frames.clear()
        self.selected_frames.clear()
        self.canvas.delete("all")
        self.photo_images.clear()
        self.selection_rects.clear()
        
        cap = cv2.VideoCapture(file_path)
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            self.frames.append(frame_rgb)
        cap.release()
        
        self.display_frames()
        
    def display_frames(self):
        self.canvas.delete("all")
        self.photo_images.clear()
        self.selection_rects.clear()
        
        thumb_size = (100, 100)
        cols = 10
        
        for i, frame in enumerate(self.frames):
            img = Image.fromarray(frame)
            img.thumbnail(thumb_size)
            photo = ImageTk.PhotoImage(img)
            self.photo_images.append(photo)
            
            row = i // cols
            col = i % cols
            x_pos = col * (thumb_size[0] + 10) + 10
            y_pos = row * (thumb_size[1] + 10) + 10
            
            frame_id = self.canvas.create_image(x_pos, y_pos, 
                                              anchor=tk.NW, image=photo, 
                                              tags=f"frame_{i}")
            
            self.canvas.tag_bind(f"frame_{i}", "<Button-1>", lambda e, idx=i: self.select_frame(idx))
            self.canvas.tag_bind(f"frame_{i}", "<Double-Button-1>", 
                               lambda e, idx=i: self.inspect_frame(idx))
            
            # Redraw selection rectangle if frame was previously selected
            if i in self.selected_frames:
                self._draw_selection_rect(i, x_pos, y_pos, thumb_size)
        
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        
    def _draw_selection_rect(self, index, x_pos, y_pos, thumb_size):
        # Draw a red rectangle around the selected frame
        rect = self.canvas.create_rectangle(
            x_pos - 2, y_pos - 2, 
            x_pos + thumb_size[0] + 2, y_pos + thumb_size[1] + 2,
            outline="red", width=2, tags=f"rect_{index}"
        )
        self.selection_rects[index] = rect
        
    def select_frame(self, index):
        thumb_size = (100, 100)
        cols = 10
        row = index // cols
        col = index % cols
        x_pos = col * (thumb_size[0] + 10) + 10
        y_pos = row * (thumb_size[1] + 10) + 10
        
        if index in self.selected_frames:
            self.selected_frames.remove(index)
            if index in self.selection_rects:
                self.canvas.delete(self.selection_rects[index])
                del self.selection_rects[index]
        else:
            self.selected_frames.add(index)
            self._draw_selection_rect(index, x_pos, y_pos, thumb_size)
                
    def inspect_frame(self, index):
        self.select_frame(index)
        
        self.popup = tk.Toplevel(self.root)
        self.popup.title(f"Frame {index}")
        self.popup.transient(self.root)
        
        img = Image.fromarray(self.frames[index])
        photo = ImageTk.PhotoImage(img)
        
        label = ttk.Label(self.popup, image=photo)
        label.image = photo
        label.pack()
        
        self.popup.focus_set()
        
    def close_popup(self, event=None):
        if hasattr(self, 'popup') and self.popup.winfo_exists():
            self.popup.destroy()
            
    def delete_selected_frames(self, event=None):
        if not self.selected_frames:
            return
            
        if messagebox.askyesno("Confirm", "Delete selected frames?"):
            for index in sorted(self.selected_frames, reverse=True):
                del self.frames[index]
                if index in self.selection_rects:
                    self.canvas.delete(self.selection_rects[index])
                    del self.selection_rects[index]
            
            self.selected_frames.clear()
            self.display_frames()
            
    def save_video(self):
        if not self.frames:
            messagebox.showerror("Error", "No frames to save!")
            return
            
        save_path = filedialog.asksaveasfilename(defaultextension=".mp4",
                                                filetypes=[("MP4 files", "*.mp4")])
        if not save_path:
            return
            
        cap = cv2.VideoCapture(self.video_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        cap.release()
        
        height, width = self.frames[0].shape[:2]
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(save_path, fourcc, fps, (width, height))
        
        for frame in self.frames:
            frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            out.write(frame_bgr)
        
        out.release()
        messagebox.showinfo("Success", "Video saved successfully!")

try:
    from tkinterdnd2 import *
    root = TkinterDnD.Tk()
except ImportError:
    root = tk.Tk()
    print("Drag and drop functionality requires tkinterdnd2. Install with 'pip install tkinterdnd2'")

if __name__ == "__main__":
    app = VideoFrameEditor(root)
    root.mainloop()