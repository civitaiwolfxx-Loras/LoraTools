import tkinter as tk
from tkinter import filedialog, ttk, messagebox
import cv2
import os
from moviepy.editor import VideoFileClip
import math
from PIL import Image, ImageTk
import json

class VideoClipExtractor:
    def __init__(self, root):
        self.root = root
        self.root.title("Video Clip Extractor")
        self.root.state('zoomed')
        
        self.video_path = None
        self.video = None
        self.source_fps = 0
        self.source_width = 0
        self.source_height = 0
        self.total_source_frames = 0
        self.last_preview_path = None
        self.crop_x = 0
        self.crop_y = 0
        self.primary_crop = None
        self.current_clip = None
        self.rotation = 0  # Rotation in degrees (0, 90, -90, etc.)
        
        self.config_file = "video_clip_extractor_config.json"
        self.load_config()
        
        self.setup_gui()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        self.root.drop_target_register(DND_FILES)
        self.root.dnd_bind('<<Drop>>', self.handle_drop)

    def load_config(self):
        try:
            with open(self.config_file, 'r') as f:
                config = json.load(f)
                self.last_load_dir = config.get('last_load_dir', os.getcwd())
                self.last_save_dir = config.get('last_save_dir', os.getcwd())
        except (FileNotFoundError, json.JSONDecodeError):
            self.last_load_dir = os.getcwd()
            self.last_save_dir = os.getcwd()

    def save_config(self):
        config = {
            'last_load_dir': self.last_load_dir,
            'last_save_dir': self.last_save_dir
        }
        with open(self.config_file, 'w') as f:
            json.dump(config, f)

    def setup_gui(self):
        top_frame = tk.Frame(self.root)
        top_frame.pack(pady=10)
        
        self.load_button = tk.Button(top_frame, text="Load Video/GIF", command=self.load_video)
        self.load_button.pack(side=tk.LEFT, padx=5)
        
        self.play_original_button = tk.Button(top_frame, text="Play Original", command=self.play_original)
        self.play_original_button.pack(side=tk.LEFT, padx=5)
        
        self.rotate_left_button = tk.Button(top_frame, text="Rotate -90°", command=self.rotate_left)
        self.rotate_left_button.pack(side=tk.LEFT, padx=5)
        
        self.rotate_right_button = tk.Button(top_frame, text="Rotate +90°", command=self.rotate_right)
        self.rotate_right_button.pack(side=tk.LEFT, padx=5)
        
        self.info_label = tk.Label(self.root, text="Video Info: Not loaded")
        self.info_label.pack(pady=5)

        self.preview_frame = tk.Frame(self.root)
        self.preview_frame.pack(pady=20, expand=True)
        
        self.preview_labels = []
        self.preview_canvases = []
        for i, label_text in enumerate(["First", "Early", "Mid", "Late", "Last"]):
            label = tk.Label(self.preview_frame, text=label_text + " Frame")
            label.grid(row=0, column=i, padx=10)
            canvas = tk.Canvas(self.preview_frame, width=384, height=216)
            canvas.grid(row=1, column=i, padx=10)
            canvas.bind("<Button-1>", lambda e, idx=i: self.show_full_frame(idx))
            self.preview_labels.append(label)
            self.preview_canvases.append(canvas)

        bottom_frame = tk.Frame(self.root)
        bottom_frame.pack(pady=20, expand=True)

        config_frame = tk.Frame(bottom_frame)
        config_frame.pack(expand=True)

        row1 = tk.Frame(config_frame)
        row1.pack(fill='x', pady=2)
        
        tk.Label(row1, text="MM:SS:").pack(side=tk.LEFT, padx=5)
        self.time_entry = tk.Entry(row1, width=10)
        self.time_entry.pack(side=tk.LEFT, padx=5)
        self.time_entry.bind("<Return>", lambda e: self.set_start_from_time())
        
        tk.Label(row1, text="Start Frame:").pack(side=tk.LEFT, padx=5)
        self.start_frame_entry = tk.Entry(row1, width=10)
        self.start_frame_entry.pack(side=tk.LEFT, padx=5)
        self.start_frame_entry.bind("<Return>", lambda e: self.apply_config())

        # Frame to hold the four navigation buttons
        nav_frame = tk.Frame(row1)
        nav_frame.pack(side=tk.LEFT, padx=5)

        # Helper function to adjust start frame
        def adjust_start_frame(delta_frames):
            try:
                current = int(self.start_frame_entry.get() or 0)
            except ValueError:
                current = 0
            new_val = max(0, current + delta_frames)
            # Prevent going beyond video length (optional, but nice)
            new_val = min(new_val, self.total_source_frames - 1)
            self.start_frame_entry.delete(0, tk.END)
            self.start_frame_entry.insert(0, str(new_val))
            self.apply_config()  # Immediately refresh preview

        # Buttons: -FPS, -FPS/2, +FPS/2, +FPS
        btn_font = ("Segoe UI", 8)  # or None for default
        btn_padx = 2

        tk.Button(nav_frame, text="−FPS", font=btn_font, padx=btn_padx, width=4,
                  command=lambda: adjust_start_frame(-int(self.source_fps + 0.5))).pack(side=tk.LEFT)
        tk.Button(nav_frame, text="−½", font=btn_font, padx=btn_padx, width=4,
                  command=lambda: adjust_start_frame(-max(1, int(self.source_fps / 2 + 0.5)))).pack(side=tk.LEFT)
        tk.Button(nav_frame, text="−5", font=btn_font, padx=btn_padx, width=4,
                  command=lambda: adjust_start_frame(-max(1, int(5)))).pack(side=tk.LEFT)
        tk.Button(nav_frame, text="−1", font=btn_font, padx=btn_padx, width=4,
                  command=lambda: adjust_start_frame(-max(1, int(1)))).pack(side=tk.LEFT)
        tk.Button(nav_frame, text="+1", font=btn_font, padx=btn_padx, width=4,
                  command=lambda: adjust_start_frame(max(1, int(1)))).pack(side=tk.LEFT)
        tk.Button(nav_frame, text="+5", font=btn_font, padx=btn_padx, width=4,
                  command=lambda: adjust_start_frame(max(1, int(5)))).pack(side=tk.LEFT)
        tk.Button(nav_frame, text="+½", font=btn_font, padx=btn_padx, width=4,
                  command=lambda: adjust_start_frame(max(1, int(self.source_fps / 2 + 0.5)))).pack(side=tk.LEFT)
        tk.Button(nav_frame, text="+FPS", font=btn_font, padx=btn_padx, width=4,
                  command=lambda: adjust_start_frame(int(self.source_fps + 0.5))).pack(side=tk.LEFT)
        
        self.set_time_button = tk.Button(row1, text="Set Time", command=self.set_start_from_time)
        self.set_time_button.pack(side=tk.LEFT, padx=5)
        
        tk.Label(row1, text="Length (seconds):").pack(side=tk.LEFT, padx=5)
        self.length_entry = tk.Entry(row1)
        self.length_entry.pack(side=tk.LEFT, padx=5)
        self.length_entry.bind("<Return>", lambda e: self.apply_config())

        row2 = tk.Frame(config_frame)
        row2.pack(fill='x', pady=2)
        
        tk.Label(row2, text="FPS:").pack(side=tk.LEFT, padx=5)
        self.fps_entry = tk.Entry(row2)
        self.fps_entry.pack(side=tk.LEFT, padx=5)
        self.fps_entry.bind("<Return>", lambda e: self.apply_config())

        self.total_frames_label = tk.Label(row2, text="Total Frames: N/A")
        self.total_frames_label.pack(side=tk.LEFT, padx=5)

        tk.Label(row2, text="Width:").pack(side=tk.LEFT, padx=5)
        self.width_entry = tk.Entry(row2)
        self.width_entry.pack(side=tk.LEFT, padx=5)
        self.width_entry.bind('<FocusOut>', self.update_aspect_ratio)
        self.width_entry.bind("<Return>", lambda e: self.apply_config())

        tk.Label(row2, text="Height:").pack(side=tk.LEFT, padx=5)
        self.height_entry = tk.Entry(row2)
        self.height_entry.pack(side=tk.LEFT, padx=5)
        self.height_entry.bind('<FocusOut>', self.update_aspect_ratio)
        self.height_entry.bind("<Return>", lambda e: self.apply_config())

        row3 = tk.Frame(config_frame)
        row3.pack(fill='x', pady=2)
        
        self.aspect_label = tk.Label(row3, text="Aspect Ratio: N/A")
        self.aspect_label.pack(side=tk.LEFT, padx=5)

        self.keep_aspect = tk.BooleanVar()
        self.aspect_check = tk.Checkbutton(row3, text="Keep Aspect Ratio", 
                                         variable=self.keep_aspect, command=self.toggle_aspect)
        self.aspect_check.pack(side=tk.LEFT, padx=5)

        self.match_duration = tk.BooleanVar(value=True)
        self.duration_check = tk.Checkbutton(row3, text="Match Source Duration", 
                                           variable=self.match_duration)
        self.duration_check.pack(side=tk.LEFT, padx=5)

        self.primary_crop_button = tk.Button(row3, text="Set Primary Crop", command=self.set_primary_crop)
        self.primary_crop_button.pack(side=tk.LEFT, padx=5)

        self.crop_button = tk.Button(row3, text="Adjust Crop", command=self.show_crop_tool)
        self.crop_button.pack(side=tk.LEFT, padx=5)

        button_frame = tk.Frame(bottom_frame)
        button_frame.pack(pady=10)
        
        self.apply_button = tk.Button(button_frame, text="Apply Configuration", 
                                    command=self.apply_config)
        self.apply_button.pack(side=tk.LEFT, padx=5)

        self.generate_button = tk.Button(button_frame, text="Generate & Preview", 
                                       command=self.generate_preview)
        self.generate_button.pack(side=tk.LEFT, padx=5)

        self.play_last_button = tk.Button(button_frame, text="Play Last Preview", 
                                        command=self.play_last_preview)
        self.play_last_button.pack(side=tk.LEFT, padx=5)

        self.save_button = tk.Button(button_frame, text="Save Clip", 
                                   command=self.save_clip)
        self.save_button.pack(side=tk.LEFT, padx=5)

    def handle_drop(self, event):
        dropped_files = self.root.tk.splitlist(event.data)
        if dropped_files:
            file_path = dropped_files[0]
            valid_extensions = ('.mp4', '.avi', '.mov', '.gif')
            if os.path.isfile(file_path) and file_path.lower().endswith(valid_extensions):
                self.video_path = file_path
                self.load_video(from_drop=True)
            else:
                messagebox.showwarning("Invalid File", "Please drop a valid video file (.mp4, .avi, .mov, .gif)")

    def load_video(self, from_drop=False):
        if not from_drop:
            self.cleanup_clip()
            self.video_path = filedialog.askopenfilename(
                initialdir=self.last_load_dir,
                filetypes=[("Video/GIF files", "*.mp4 *.avi *.mov *..gif")]
            )
        if self.video_path:
            self.last_load_dir = os.path.dirname(self.video_path)
            self.video = cv2.VideoCapture(self.video_path)
            self.current_clip = VideoFileClip(self.video_path)
            
            self.source_fps = self.video.get(cv2.CAP_PROP_FPS) or self.current_clip.fps or 25
            self.source_width = int(self.video.get(cv2.CAP_PROP_FRAME_WIDTH)) or self.current_clip.w
            self.source_height = int(self.video.get(cv2.CAP_PROP_FRAME_HEIGHT)) or self.current_clip.h
            self.total_source_frames = int(self.video.get(cv2.CAP_PROP_FRAME_COUNT)) or int(self.current_clip.duration * self.source_fps)
            self.crop_x = 0
            self.crop_y = 0
            self.primary_crop = None
            self.rotation = 0  # Reset rotation on new load
            
            aspect = self.source_width / self.source_height
            info = f"Resolution: {self.source_width}x{self.source_height} | Aspect: {aspect:.2f} | FPS: {self.source_fps:.2f}"
            self.info_label.config(text=info)
            self.total_frames_label.config(text=f"Total Frames: {self.total_source_frames}")
            
            self.fps_entry.delete(0, tk.END)
            self.fps_entry.insert(0, f"{self.source_fps:.2f}")
            self.width_entry.delete(0, tk.END)
            self.width_entry.insert(0, str(self.source_width))
            self.height_entry.delete(0, tk.END)
            self.height_entry.insert(0, str(self.source_height))
            
            self.start_frame_entry.delete(0, tk.END)
            self.start_frame_entry.insert(0, "0")
            default_length_seconds = min(6, self.total_source_frames / self.source_fps)
            self.length_entry.delete(0, tk.END)
            self.length_entry.insert(0, str(int(default_length_seconds)))
            self.time_entry.delete(0, tk.END)
            self.time_entry.insert(0, "00:00")
            
            self.primary_crop_button.config(text="Set Primary Crop", command=self.set_primary_crop)
            self.update_aspect_ratio()
            self.apply_config()

    def rotate_left(self):
        if not self.video:
            return
        self.rotation = (self.rotation - 90) % 360  # Rotate counterclockwise
        self.reset_crops()
        self.swap_dimensions()
        self.apply_config()

    def rotate_right(self):
        if not self.video:
            return
        self.rotation = (self.rotation + 90) % 360  # Rotate clockwise
        self.reset_crops()
        self.swap_dimensions()
        self.apply_config()

    def reset_crops(self):
        self.primary_crop = None
        self.crop_x = 0
        self.crop_y = 0
        self.primary_crop_button.config(text="Set Primary Crop", command=self.set_primary_crop)

    def swap_dimensions(self):
        # Swap width and height in the UI
        current_width = self.width_entry.get()
        current_height = self.height_entry.get()
        self.width_entry.delete(0, tk.END)
        self.width_entry.insert(0, current_height)
        self.height_entry.delete(0, tk.END)
        self.height_entry.insert(0, current_width)
        self.update_aspect_ratio()

    def play_original(self):
        if self.video_path and os.path.exists(self.video_path):
            os.startfile(self.video_path) if os.name == 'nt' else os.system(f"open {self.video_path}")
        else:
            messagebox.showinfo("Info", "No video file has been loaded yet.")

    def update_aspect_ratio(self, event=None):
        try:
            width = float(self.width_entry.get())
            height = float(self.height_entry.get())
            aspect = width / height
            self.aspect_label.config(text=f"Aspect Ratio: {aspect:.2f}")
            
            if self.keep_aspect.get() and event:
                base_width = self.source_width if self.primary_crop is None else (self.primary_crop[2] - self.primary_crop[0])
                base_height = self.source_height if self.primary_crop is None else (self.primary_crop[3] - self.primary_crop[1])
                if event.widget == self.width_entry:
                    new_height = width / (base_width / base_height)
                    self.height_entry.delete(0, tk.END)
                    self.height_entry.insert(0, f"{new_height:.0f}")
                elif event.widget == self.height_entry:
                    new_width = height * (base_width / base_height)
                    self.width_entry.delete(0, tk.END)
                    self.width_entry.insert(0, f"{new_width:.0f}")
        except (ValueError, ZeroDivisionError):
            self.aspect_label.config(text="Aspect Ratio: N/A")

    def toggle_aspect(self):
        if self.keep_aspect.get():
            self.update_aspect_ratio()

    def get_mid_frame_number(self):
        try:
            start_frame = int(self.start_frame_entry.get())
            length_seconds = int(self.length_entry.get())
            length_frames = int(length_seconds * self.source_fps)
            mid_frame = start_frame + length_frames // 2
            return min(max(mid_frame, 0), self.total_source_frames - 1)
        except ValueError:
            return self.total_source_frames // 2

    def set_primary_crop(self):
        if not self.video:
            return
        
        popup = tk.Toplevel(self.root)
        popup.title("Set Primary Crop")
        popup.focus_set()
        
        display_width = min(800, self.source_width)
        scale = display_width / self.source_width
        display_height = int(self.source_height * scale)
        
        mid_frame = self.get_mid_frame_number()
        self.video.set(cv2.CAP_PROP_POS_FRAMES, mid_frame)
        ret, frame = self.video.read()
        if not ret:
            popup.destroy()
            return
        
        # Apply rotation to the preview frame if needed
        if self.rotation:
            frame = cv2.rotate(frame, {90: cv2.ROTATE_90_CLOCKWISE, -90: cv2.ROTATE_90_COUNTERCLOCKWISE, 180: cv2.ROTATE_180}.get(self.rotation % 360, cv2.ROTATE_90_CLOCKWISE))
        
        display_frame = cv2.resize(frame, (display_width, display_height))
        display_frame = cv2.cvtColor(display_frame, cv2.COLOR_BGR2RGB)
        
        canvas = tk.Canvas(popup, width=display_width, height=display_height)
        canvas.pack()
        
        img = Image.fromarray(display_frame)
        photo = ImageTk.PhotoImage(image=img)
        canvas.create_image(display_width//2, display_height//2, image=photo, anchor='center')
        canvas.image = photo
        
        crop_width = display_width
        crop_height = display_height
        crop_x1 = 0
        crop_y1 = 0
        
        crop_rect = canvas.create_rectangle(
            crop_x1, crop_y1, crop_x1 + crop_width, crop_y1 + crop_height,
            outline='blue', width=2
        )
        
        size_frame = tk.Frame(popup)
        size_frame.pack(pady=5)
        
        tk.Label(size_frame, text="Width:").pack(side=tk.LEFT, padx=5)
        width_entry = tk.Entry(size_frame, width=10)
        width_entry.pack(side=tk.LEFT, padx=5)
        width_entry.insert(0, self.width_entry.get())
        
        tk.Label(size_frame, text="Height:").pack(side=tk.LEFT, padx=5)
        height_entry = tk.Entry(size_frame, width=10)
        height_entry.pack(side=tk.LEFT, padx=5)
        height_entry.insert(0, self.height_entry.get())
        
        resize_mode = tk.BooleanVar(value=False)
        toggle_button = tk.Button(size_frame, text="Toggle Resize Mode", 
                                command=lambda: resize_mode.set(not resize_mode.get()))
        toggle_button.pack(side=tk.LEFT, padx=5)
        
        def update_rect_from_entries(event=None):
            nonlocal crop_width, crop_height, crop_x1, crop_y1
            try:
                new_width = int(width_entry.get())
                new_height = int(height_entry.get())
                crop_width = min(new_width * scale, display_width)
                crop_height = min(new_height * scale, display_height)
                crop_x1 = max(0, min(crop_x1, display_width - crop_width))
                crop_y1 = max(0, min(crop_y1, display_height - crop_height))
                canvas.coords(crop_rect, crop_x1, crop_y1, crop_x1 + crop_width, crop_y1 + crop_height)
            except ValueError:
                pass
        
        def move_crop(event):
            nonlocal crop_x1, crop_y1
            x, y = event.x, event.y
            crop_x1 = max(0, min(x - crop_width//2, display_width - crop_width))
            crop_y1 = max(0, min(y - crop_height//2, display_height - crop_height))
            canvas.coords(crop_rect, crop_x1, crop_y1, crop_x1 + crop_width, crop_y1 + crop_height)
            width_entry.delete(0, tk.END)
            width_entry.insert(0, str(int(crop_width / scale)))
            height_entry.delete(0, tk.END)
            height_entry.insert(0, str(int(crop_height / scale)))

        def resize_crop(event):
            nonlocal crop_x1, crop_y1, crop_width, crop_height
            x, y = event.x, event.y
            left = crop_x1
            right = crop_x1 + crop_width
            top = crop_y1
            bottom = crop_y1 + crop_height
            hitbox = 10

            if abs(x - left) <= hitbox and abs(y - top) <= hitbox:  # Top-left
                crop_width = max(right - x, hitbox)
                crop_height = max(bottom - y, hitbox)
                crop_x1 = right - crop_width
                crop_y1 = bottom - crop_height
            elif abs(x - right) <= hitbox and abs(y - top) <= hitbox:  # Top-right
                crop_width = max(x - left, hitbox)
                crop_height = max(bottom - y, hitbox)
                crop_y1 = bottom - crop_height
            elif abs(x - left) <= hitbox and abs(y - bottom) <= hitbox:  # Bottom-left
                crop_width = max(right - x, hitbox)
                crop_height = max(y - top, hitbox)
                crop_x1 = right - crop_width
            elif abs(x - right) <= hitbox and abs(y - bottom) <= hitbox:  # Bottom-right
                crop_width = max(x - left, hitbox)
                crop_height = max(y - top, hitbox)
            elif abs(x - left) <= hitbox:  # Left edge
                crop_width = max(right - x, hitbox)
                crop_x1 = right - crop_width
            elif abs(x - right) <= hitbox:  # Right edge
                crop_width = max(x - left, hitbox)
            elif abs(y - top) <= hitbox:  # Top edge
                crop_height = max(bottom - y, hitbox)
                crop_y1 = bottom - crop_height
            elif abs(y - bottom) <= hitbox:  # Bottom edge
                crop_height = max(y - top, hitbox)

            crop_x1 = max(0, min(crop_x1, display_width - crop_width))
            crop_y1 = max(0, min(crop_y1, display_height - crop_height))
            crop_width = min(crop_width, display_width - crop_x1)
            crop_height = min(crop_height, display_height - crop_y1)

            canvas.coords(crop_rect, crop_x1, crop_y1, crop_x1 + crop_width, crop_y1 + crop_height)
            width_entry.delete(0, tk.END)
            width_entry.insert(0, str(int(crop_width / scale)))
            height_entry.delete(0, tk.END)
            height_entry.insert(0, str(int(crop_height / scale)))

        def on_mouse_down(event):
            if resize_mode.get():
                resize_crop(event)
            else:
                move_crop(event)

        def apply_primary_crop(event=None):
            self.primary_crop = (
                int(crop_x1 / scale), int(crop_y1 / scale),
                int((crop_x1 + crop_width) / scale), int((crop_y1 + crop_height) / scale)
            )
            self.width_entry.delete(0, tk.END)
            self.width_entry.insert(0, str(self.primary_crop[2] - self.primary_crop[0]))
            self.height_entry.delete(0, tk.END)
            self.height_entry.insert(0, str(self.primary_crop[3] - self.primary_crop[1]))
            self.primary_crop_button.config(text="Forget Primary Crop", command=self.forget_primary_crop)
            self.update_aspect_ratio()
            self.apply_config()
            popup.destroy()
        
        def cancel_primary_crop(event=None):
            popup.destroy()
        
        width_entry.bind("<FocusOut>", update_rect_from_entries)
        height_entry.bind("<FocusOut>", update_rect_from_entries)
        canvas.bind("<B1-Motion>", on_mouse_down)
        popup.bind("<Return>", apply_primary_crop)
        popup.bind("<Escape>", cancel_primary_crop)
        
        apply_button = tk.Button(popup, text="Apply Primary Crop", command=apply_primary_crop)
        apply_button.pack(pady=10)

    def forget_primary_crop(self):
        self.primary_crop = None
        self.width_entry.delete(0, tk.END)
        self.width_entry.insert(0, str(self.source_width if self.rotation in (0, 180) else self.source_height))
        self.height_entry.delete(0, tk.END)
        self.height_entry.insert(0, str(self.source_height if self.rotation in (0, 180) else self.source_width))
        self.primary_crop_button.config(text="Set Primary Crop", command=self.set_primary_crop)
        self.update_aspect_ratio()
        self.apply_config()

    def set_start_from_time(self):
        if not self.video:
            return
            
        try:
            time_str = self.time_entry.get()
            minutes, seconds = map(int, time_str.split(':'))
            total_seconds = minutes * 60 + seconds
            start_frame = int(total_seconds * self.source_fps)
            
            if start_frame >= self.total_source_frames:
                messagebox.showerror("Error", "Start time exceeds video length")
                return
                
            self.start_frame_entry.delete(0, tk.END)
            self.start_frame_entry.insert(0, str(start_frame))
            
        except (ValueError, AttributeError):
            messagebox.showerror("Error", "Invalid time format. Use MM:SS")

    def resize_image(self, frame, max_width=384, max_height=216):
        height, width = frame.shape[:2]
        scale = min(max_width/width, max_height/height)
        new_width = int(width * scale)
        new_height = int(height * scale)
        return cv2.resize(frame, (new_width, new_height))

    def resize_to_screen(self, frame):
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight() - 100
        height, width = frame.shape[:2]
        scale = min(screen_width/width, screen_height/height)
        new_width = int(width * scale)
        new_height = int(height * scale)
        return cv2.resize(frame, (new_width, new_height))

    def show_preview(self, frame, canvas):
        if self.rotation:
            frame = cv2.rotate(frame, {90: cv2.ROTATE_90_CLOCKWISE, -90: cv2.ROTATE_90_COUNTERCLOCKWISE, 180: cv2.ROTATE_180}.get(self.rotation % 360, cv2.ROTATE_90_CLOCKWISE))
        if self.primary_crop:
            frame = frame[self.primary_crop[1]:self.primary_crop[3], self.primary_crop[0]:self.primary_crop[2]]
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        frame = self.resize_image(frame)
        img = Image.fromarray(frame)
        photo = ImageTk.PhotoImage(image=img)
        canvas.create_image(canvas.winfo_width()//2, canvas.winfo_height()//2, 
                          image=photo, anchor='center')
        canvas.image = photo

    def show_full_frame(self, preview_idx):
        if not self.video:
            return
        
        try:
            start_frame = int(self.start_frame_entry.get())
            length_seconds = int(self.length_entry.get())
            length_frames = int(length_seconds * self.source_fps)
            frame_positions = self.get_frame_positions(start_frame, length_frames)
            current_idx = preview_idx
            
            popup = tk.Toplevel(self.root)
            popup.title(f"Frame View")
            popup.focus_set()
            
            canvas_width = self.source_width if self.rotation in (0, 180) else self.source_height
            canvas_height = self.source_height if self.rotation in (0, 180) else self.source_width
            if self.primary_crop:
                canvas_width = self.primary_crop[2] - self.primary_crop[0]
                canvas_height = self.primary_crop[3] - self.primary_crop[1]
            canvas = tk.Canvas(popup, width=canvas_width, height=canvas_height)
            canvas.pack()
            
            def update_frame():
                frame_num = frame_positions[current_idx]
                self.video.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
                ret, frame = self.video.read()
                if ret:
                    if self.rotation:
                        frame = cv2.rotate(frame, {90: cv2.ROTATE_90_CLOCKWISE, -90: cv2.ROTATE_90_COUNTERCLOCKWISE, 180: cv2.ROTATE_180}.get(self.rotation % 360, cv2.ROTATE_90_CLOCKWISE))
                    if self.primary_crop:
                        frame = frame[self.primary_crop[1]:self.primary_crop[3], self.primary_crop[0]:self.primary_crop[2]]
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    frame = self.resize_to_screen(frame)
                    img = Image.fromarray(frame)
                    photo = ImageTk.PhotoImage(image=img)
                    canvas.create_image(frame.shape[1]//2, frame.shape[0]//2, 
                                      image=photo, anchor='center')
                    canvas.image = photo
                    popup.title(f"Frame {frame_num}")
            
            def prev_frame(event=None):
                nonlocal current_idx
                current_idx = (current_idx - 1) % 5
                update_frame()
            
            def next_frame(event=None):
                nonlocal current_idx
                current_idx = (current_idx + 1) % 5
                update_frame()
            
            def close_popup(event=None):
                popup.destroy()
            
            update_frame()
            
            popup.bind("<Left>", prev_frame)
            popup.bind("<Right>", next_frame)
            popup.bind("<Escape>", close_popup)
            
            close_button = tk.Button(popup, text="Close", command=popup.destroy)
            close_button.pack(pady=10)
            
        except ValueError:
            pass

    def show_crop_tool(self):
        if not self.video:
            return
        
        try:
            target_width = int(self.width_entry.get())
            target_height = int(self.height_entry.get())
            target_aspect = target_width / target_height
            
            base_width = self.source_width if self.rotation in (0, 180) else self.source_height
            base_height = self.source_height if self.rotation in (0, 180) else self.source_width
            if self.primary_crop:
                base_width = self.primary_crop[2] - self.primary_crop[0]
                base_height = self.primary_crop[3] - self.primary_crop[1]
            
            mid_frame = self.get_mid_frame_number()
            self.video.set(cv2.CAP_PROP_POS_FRAMES, mid_frame)
            ret, frame = self.video.read()
            if not ret:
                return
            
            if self.rotation:
                frame = cv2.rotate(frame, {90: cv2.ROTATE_90_CLOCKWISE, -90: cv2.ROTATE_90_COUNTERCLOCKWISE, 180: cv2.ROTATE_180}.get(self.rotation % 360, cv2.ROTATE_90_CLOCKWISE))
            if self.primary_crop:
                frame = frame[self.primary_crop[1]:self.primary_crop[3], self.primary_crop[0]:self.primary_crop[2]]
            
            popup = tk.Toplevel(self.root)
            popup.title("Adjust Crop")
            popup.focus_set()
            
            display_width = min(800, base_width)
            scale = display_width / base_width
            display_height = int(base_height * scale)
            display_frame = cv2.resize(frame, (display_width, display_height))
            display_frame = cv2.cvtColor(display_frame, cv2.COLOR_BGR2RGB)
            
            canvas = tk.Canvas(popup, width=display_width, height=display_height)
            canvas.pack()
            
            img = Image.fromarray(display_frame)
            photo = ImageTk.PhotoImage(image=img)
            canvas.create_image(display_width//2, display_height//2, image=photo, anchor='center')
            canvas.image = photo
            
            if target_aspect > base_width / base_height:
                crop_height = int(display_width / target_aspect)
                crop_width = display_width
            else:
                crop_width = int(display_height * target_aspect)
                crop_height = display_height
            
            self.crop_x = (display_width - crop_width) // 2
            self.crop_y = (display_height - crop_height) // 2
            
            crop_rect = canvas.create_rectangle(
                self.crop_x, self.crop_y,
                self.crop_x + crop_width, self.crop_y + crop_height,
                outline='red', width=2
            )
            
            def move_crop(event):
                x, y = event.x, event.y
                new_x = max(0, min(x - crop_width//2, display_width - crop_width))
                new_y = max(0, min(y - crop_height//2, display_height - crop_height))
                canvas.coords(crop_rect, new_x, new_y, new_x + crop_width, new_y + crop_height)
                self.crop_x = int(new_x / scale)
                self.crop_y = int(new_y / scale)
            
            def apply_crop(event=None):
                popup.destroy()
            
            def cancel_crop(event=None):
                self.crop_x = (base_width - min(target_width, base_width)) // 2
                self.crop_y = (base_height - min(target_height, base_height)) // 2
                popup.destroy()
            
            canvas.bind("<B1-Motion>", move_crop)
            popup.bind("<Return>", apply_crop)
            popup.bind("<Escape>", cancel_crop)
            
            apply_button = tk.Button(popup, text="Apply Crop", command=apply_crop)
            apply_button.pack(pady=10)
            
        except ValueError:
            messagebox.showerror("Error", "Invalid width or height values")

    def get_frame_positions(self, start_frame, length_frames):
        return [
            start_frame,  # First
            start_frame + length_frames // 4,  # Early
            start_frame + length_frames // 2,  # Mid
            start_frame + 3 * length_frames // 4,  # Late
            start_frame + length_frames - 1  # Last
        ]

    def apply_config(self):
        if not self.video:
            return
        
        try:
            start_frame = int(self.start_frame_entry.get())
            length_seconds = int(self.length_entry.get())
            length_frames = int(length_seconds * self.source_fps)
            
            if start_frame + length_frames > self.total_source_frames:
                messagebox.showerror("Error", "Clip exceeds video length")
                return
                
            frame_positions = self.get_frame_positions(start_frame, length_frames)
            for i, frame_num in enumerate(frame_positions):
                self.video.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
                ret, frame = self.video.read()
                if ret:
                    self.show_preview(frame, self.preview_canvases[i])
                
        except ValueError:
            pass

    def adjust_clip_for_fps(self, clip, start_frame, length_seconds, target_fps):
        if self.match_duration.get():
            new_length_frames = int(length_seconds * target_fps)
            return clip.subclip(0, length_seconds), new_length_frames
        else:
            length_frames = int(length_seconds * self.source_fps)
            return clip.subclip(0, length_frames / self.source_fps), length_frames

    def apply_crops(self, clip):
        if self.rotation:
            clip = clip.rotate(self.rotation)
        if self.primary_crop:
            clip = clip.crop(
                x1=self.primary_crop[0], y1=self.primary_crop[1],
                x2=self.primary_crop[2], y2=self.primary_crop[3]
            )
        
        target_width = int(self.width_entry.get())
        target_height = int(self.height_entry.get())
        if target_width != clip.w or target_height != clip.h:
            crop_width = min(target_width, clip.w)
            crop_height = min(target_height, clip.h)
            clip = clip.crop(
                x1=self.crop_x, y1=self.crop_y,
                x2=self.crop_x + crop_width, y2=self.crop_y + crop_height
            )
            if clip.w != target_width or clip.h != target_height:
                clip = clip.resize(newsize=(target_width, target_height))
        return clip

    def get_next_filename(self, directory):
        base_name = "Converted"
        index = 1
        while True:
            filename = f"{base_name}-{index}.mp4"
            full_path = os.path.join(directory, filename)
            if not os.path.exists(full_path):
                return filename
            index += 1

    def cleanup_clip(self):
        if self.current_clip is not None:
            try:
                self.current_clip.close()
            except Exception:
                pass
            self.current_clip = None

    def generate_preview(self):
        if not self.video:
            return
            
        try:
            start_frame = int(self.start_frame_entry.get())
            length_seconds = int(self.length_entry.get())
            target_fps = float(self.fps_entry.get())
            target_width = int(self.width_entry.get())
            target_height = int(self.height_entry.get())
            
            length_frames_source = int(length_seconds * self.source_fps)
            if start_frame + length_frames_source > self.total_source_frames:
                messagebox.showerror("Error", "Clip exceeds video length")
                return
                
            self.cleanup_clip()
            self.current_clip = VideoFileClip(self.video_path).subclip(
                start_frame / self.source_fps,
                (start_frame + length_frames_source) / self.source_fps
            )
            clip, adjusted_length_frames = self.adjust_clip_for_fps(self.current_clip, start_frame, length_seconds, target_fps)
            clip = self.apply_crops(clip)
            
            self.last_preview_path = os.path.join(os.path.dirname(__file__), "tmp", "preview.mp4")
            os.makedirs(os.path.dirname(self.last_preview_path), exist_ok=True)
            clip.write_videofile(self.last_preview_path, fps=target_fps, codec="libx264")
            
            os.startfile(self.last_preview_path) if os.name == 'nt' else os.system(f"open {self.last_preview_path}")
            
        except Exception as e:
            print(f"Error generating preview: {e}")

    def play_last_preview(self):
        if self.last_preview_path and os.path.exists(self.last_preview_path):
            os.startfile(self.last_preview_path) if os.name == 'nt' else os.system(f"open {self.last_preview_path}")
        else:
            messagebox.showinfo("Info", "No preview has been generated yet.")

    def save_clip(self):
        if not self.video:
            return
            
        default_filename = self.get_next_filename(self.last_save_dir)
        save_path = filedialog.asksaveasfilename(
            initialdir=self.last_save_dir,
            initialfile=default_filename,
            defaultextension=".mp4",
            filetypes=[("MP4 files", "*.mp4")]
        )
        if save_path:
            self.last_save_dir = os.path.dirname(save_path)
            try:
                start_frame = int(self.start_frame_entry.get())
                length_seconds = int(self.length_entry.get())
                target_fps = float(self.fps_entry.get())
                target_width = int(self.width_entry.get())
                target_height = int(self.height_entry.get())
                
                length_frames_source = int(length_seconds * self.source_fps)
                if start_frame + length_frames_source > self.total_source_frames:
                    messagebox.showerror("Error", "Clip exceeds video length")
                    return
                    
                self.cleanup_clip()
                self.current_clip = VideoFileClip(self.video_path).subclip(
                    start_frame / self.source_fps,
                    (start_frame + length_frames_source) / self.source_fps
                )
                clip, adjusted_length_frames = self.adjust_clip_for_fps(self.current_clip, start_frame, length_seconds, target_fps)
                clip = self.apply_crops(clip)
                clip.write_videofile(save_path, fps=target_fps, codec="libx264")
                
            except Exception as e:
                print(f"Error saving clip: {e}")

    def on_closing(self):
        self.cleanup_clip()
        if self.video is not None:
            self.video.release()
        self.save_config()
        self.root.destroy()

if __name__ == "__main__":
    from tkinterdnd2 import *
    root = TkinterDnD.Tk()
    app = VideoClipExtractor(root)
    root.mainloop()