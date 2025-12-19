import tkinter as tk
from tkinter import ttk, messagebox, filedialog, Toplevel
from PIL import Image, ImageTk
import cv2
import os
import pyperclip
from pathlib import Path

class MediaTagManager:
    def __init__(self, root):
        self.root = root
        self.root.title("Media Tag Manager")
        self.root.geometry("1000x600")

        # Global tag list for autocompletion and tracking
        self.global_tags = set()

        # Tags from another dataset
        self.other_dataset_tags = set()

        # Dictionary to store thumbnails
        self.thumbnails = {}
        self.large_thumbnails = {}  # For images or first frame of videos
        self.video_thumbnails = {}  # For storing video frame thumbnails
        self.current_video_index = {}  # Track current frame index for each video window

        self.file_frames = []  # To keep track of file list entries

        # Track unsaved changes
        self.unsaved_changes = False
        self.current_tags = []  # Track current tags to detect changes

        # Store copied tags for copy-paste functionality
        self.copied_tags = []

        # UI Components
        self.setup_ui()

        # No directory loaded by default
        self.directory = None
        self.files = []
        
        self.tag_filter_active = False
        self.current_tag_filter = None

    def copy_tags_on_right_click(self, event):
        """Right-click on a file → instantly copy its tags to clipboard"""
        item = self.file_tree.identify_row(event.y)
        if not item:
            return

        file_path = Path(item)  # iid = full path string
        txt_path = file_path.with_suffix(".txt")

        if txt_path.exists():
            try:
                tags = txt_path.read_text(encoding="utf-8").strip()
                pyperclip.copy(tags)
                tag_count = len([t for t in tags.split(",") if t.strip()]) if tags else 0
                self.root.title(f"Media Tag Manager — Copied {tag_count} tag{'s' if tag_count != 1 else ''}")
                # Optional: tiny feedback popup (non-blocking)
                self.root.after(2000, lambda: self.root.title("Media Tag Manager"))
            except Exception as e:
                messagebox.showerror("Error", f"Failed to read tags:\n{e}")
        else:
            pyperclip.copy("")
            self.root.title("Media Tag Manager — No tags found")
            self.root.after(2000, lambda: self.root.title("Media Tag Manager"))

    # Placeholder handling
    def clear_placeholder(self, event, placeholder):
        if event.widget.get() == placeholder:
            event.widget.delete(0, tk.END)
            event.widget.config(fg="black")

    def restore_placeholder(self, event, placeholder):
        if not event.widget.get():
            event.widget.insert(0, placeholder)
            event.widget.config(fg="grey")

    # Filter functions
    def filter_current_tags(self, event=None):
        search_term = self.filter_entry1.get().strip().lower()
        if search_term == "search tags...".lower():
            search_term = ""
        self.all_tags_listbox.delete(0, tk.END)
        for tag in sorted(self.global_tags):
            if search_term in tag.lower():
                self.all_tags_listbox.insert(tk.END, tag)

    def filter_other_tags(self, event=None):
        search_term = self.filter_entry2.get().strip().lower()
        if search_term == "search other tags...".lower():
            search_term = ""
        self.other_tags_listbox.delete(0, tk.END)
        for tag in sorted(self.other_dataset_tags):
            if search_term in tag.lower():
                self.other_tags_listbox.insert(tk.END, tag)

    def clear_filter1(self):
        self.filter_entry1.delete(0, tk.END)
        self.filter_entry1.insert(0, "Search tags...")
        self.filter_entry1.config(fg="grey")
        self.update_all_tags()  # Restore full list

    def clear_filter2(self):
        self.filter_entry2.delete(0, tk.END)
        self.filter_entry2.insert(0, "Search other tags...")
        self.filter_entry2.config(fg="grey")
        self.update_other_tags()  # Restore full list
    
    def toggle_tag_file_filter(self, event=None):
        # Get selected tag from the top-right listbox
        selection = self.all_tags_listbox.curselection()
        if not selection:
            messagebox.showinfo("No Tag Selected", "Please select a tag from 'All Tags' first.")
            return

        selected_tag = self.all_tags_listbox.get(selection[0])

        if self.tag_filter_active and self.current_tag_filter == selected_tag:
            # === TURN OFF FILTER ===
            self.tag_filter_active = False
            self.current_tag_filter = None
            self.filter_by_tag_btn.config(text="Filter Files by Selected Tag", bg="#4CAF50")
            self.reload_file_list()  # Show all files again
        else:
            # === TURN ON FILTER ===
            self.tag_filter_active = True
            self.current_tag_filter = selected_tag
            self.filter_by_tag_btn.config(
                text=f"Showing files with: {selected_tag} (click to clear)",
                bg="#e91e63", fg="white"
            )
            self.filter_files_by_tag(selected_tag)

        # Keep the tag selected visually
        self.all_tags_listbox.selection_set(selection[0])
        
    def filter_files_by_tag(self, tag):
        # Clear current view
        for item in self.file_tree.get_children():
            self.file_tree.delete(item)

        matched = 0
        for file_path in self.files:
            tag_file = file_path.with_suffix(".txt")
            if tag_file.exists():
                try:
                    content = tag_file.read_text(encoding="utf-8")
                    if tag in [t.strip() for t in content.split(",") if t.strip()]:
                        self.add_file_to_tree(file_path)
                        matched += 1
                except:
                    pass

        if matched == 0:
            messagebox.showinfo("No Match", f"No files found with tag: {tag}")

    def reload_file_list(self):
        # Clear and repopulate with ALL files
        for item in self.file_tree.get_children():
            self.file_tree.delete(item)
        for file_path in self.files:
            self.add_file_to_tree(file_path)

    def add_file_to_tree(self, file_path):
        # Use full path as key
        key = str(file_path)
        try:
            thumb = self.thumbnails.get(key)  # ← CHANGE: use key, not file_path.name
            if not thumb:
                thumb = self.generate_thumbnail(file_path, size=120)
                self.thumbnails[key] = thumb
        except:
            thumb = None

        display_name = str(file_path.relative_to(self.directory)) if hasattr(self, 'directory') else file_path.name
        iid = key
        self.file_tree.insert("", "end", iid=iid, text=display_name, image=thumb or "")
    
    def setup_ui(self):
        # Main frame with resizable panes
        self.paned_window = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        self.paned_window.pack(fill=tk.BOTH, expand=True)

        self.left_frame = tk.Frame(self.paned_window)
        self.paned_window.add(self.left_frame, weight=1)

        tk.Button(self.left_frame, text="Load Directory", command=self.load_directory_dialog).pack(pady=5)

        # Recursive checkbox
        self.main_recursive_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(self.left_frame, variable=self.main_recursive_var,
                        text="Load recursively (include subfolders)").pack(pady=2)

        # Treeview with scrollbar
        tree_frame = tk.Frame(self.left_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        self.file_tree = ttk.Treeview(tree_frame, show="tree")  # Only shows tree column
        # ← ADD THESE 3 LINES FOR BIGGER THUMBS ↓
        style = ttk.Style()
        style.configure("Treeview", rowheight=130)        # 130 = perfect for 120px thumbs + text
        style.configure("Treeview.Item", padding=6)       # nice spacing around each item
        
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.file_tree.yview)
        self.file_tree.configure(yscrollcommand=vsb.set)

        self.file_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        # Bind selection and double-click
                # === PERFECT click & double-click behavior ===
        self.file_tree.bind("<Button-1>", self.on_tree_click)
        self.file_tree.bind("<Double-1>", self.on_tree_doubleclick)
        self.file_tree.bind("<ButtonRelease-1>", lambda e: self.file_tree.selection_set(self.file_tree.identify("item", e.x, e.y)))
        
        # NEW: Right-click = instantly copy tags
        self.file_tree.bind("<Button-3>", self.copy_tags_on_right_click)        # Windows / Linux

        # Scrollable frame for file list
        self.file_canvas = tk.Canvas(self.left_frame)
        self.file_scrollbar = ttk.Scrollbar(self.left_frame, orient=tk.VERTICAL, command=self.file_canvas.yview)
        self.file_scrollable_frame = tk.Frame(self.file_canvas)

        self.file_scrollable_frame.bind(
            "<Configure>",
            lambda e: self.file_canvas.configure(scrollregion=self.file_canvas.bbox("all"))
        )

        self.file_canvas.configure(yscrollcommand=self.file_scrollbar.set)

        self.file_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.file_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.file_canvas.create_window((0, 0), window=self.file_scrollable_frame, anchor="nw")

        # Bind mouse wheel scrolling to the left pane
        self.file_canvas.bind("<MouseWheel>", self.on_mouse_wheel)  # Windows
        self.file_canvas.bind("<Button-4>", self.on_mouse_wheel)  # Linux (scroll up)
        self.file_canvas.bind("<Button-5>", self.on_mouse_wheel)  # Linux (scroll down)
        self.file_scrollable_frame.bind("<MouseWheel>", self.on_mouse_wheel)
        self.file_scrollable_frame.bind("<Button-4>", self.on_mouse_wheel)
        self.file_scrollable_frame.bind("<Button-5>", self.on_mouse_wheel)

        # Middle pane: Tags for selected file
        self.middle_frame = tk.Frame(self.paned_window)
        self.paned_window.add(self.middle_frame, weight=2)

        # Middle pane toolbar
        self.middle_toolbar = tk.Frame(self.middle_frame)
        self.middle_toolbar.pack(fill=tk.X)

        self.tag_entry = ttk.Combobox(self.middle_toolbar, values=[])
        self.tag_entry.pack(side=tk.LEFT, padx=5, pady=5)
        self.tag_entry.bind("<Return>", self.add_tag)

        tk.Button(self.middle_toolbar, text="Add Tag", command=self.add_tag).pack(side=tk.LEFT, padx=5)
        tk.Button(self.middle_toolbar, text="Add Tag to All", command=self.add_tag_to_all).pack(side=tk.LEFT, padx=5)
        tk.Button(self.middle_toolbar, text="Remove Tag from All", command=self.remove_tag_from_all).pack(side=tk.LEFT, padx=5)

        self.tag_listbox = tk.Listbox(self.middle_frame, width=40)
        self.tag_listbox.pack(fill=tk.BOTH, expand=True)
        self.tag_listbox.bind("<Delete>", self.delete_tag)  # Bind Delete key
        self.tag_listbox.bind("<Insert>", self.insert_tag)  # Bind Insert key
        self.tag_listbox.bind("<Alt-Up>", self.move_tag_up, add="+")
        self.tag_listbox.bind("<Alt-Down>", self.move_tag_down, add="+")
        self.tag_listbox.bind("<Button-3>", self.edit_tag_in_current)  # Bind right-click to edit

        # Middle pane buttons
        button_frame = tk.Frame(self.middle_frame)
        button_frame.pack(fill=tk.X, pady=5)
        tk.Button(button_frame, text="Remove Selected Tag", command=self.remove_tag).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Copy Tags", command=self.copy_tags).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Paste Tags", command=self.paste_tags).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Save Tags", command=self.save_tags).pack(side=tk.LEFT, padx=5)

        # Right pane: Split into two sections for current dataset tags and other dataset tags
        self.right_frame = tk.Frame(self.paned_window)
        self.paned_window.add(self.right_frame, weight=1)

        # ==================== TOP: All Tags (Current Dataset) ====================
        self.current_tags_frame = tk.Frame(self.right_frame)
        self.current_tags_frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(self.current_tags_frame, text="All Tags (Current Dataset)").pack(anchor="w", padx=5, pady=(5,0))

        # Filter for current dataset tags
        filter_frame1 = tk.Frame(self.current_tags_frame)
        filter_frame1.pack(fill=tk.X, padx=5, pady=2)
        self.filter_entry1 = tk.Entry(filter_frame1)
        self.filter_entry1.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.filter_entry1.insert(0, "Search tags...")
        self.filter_entry1.config(fg="grey")
        self.filter_entry1.bind("<FocusIn>", lambda e: self.clear_placeholder(e, "Search tags..."))
        self.filter_entry1.bind("<FocusOut>", lambda e: self.restore_placeholder(e, "Search tags..."))
        self.filter_entry1.bind("<KeyRelease>", self.filter_current_tags)

        tk.Button(filter_frame1, text="×", width=2, command=self.clear_filter1).pack(side=tk.RIGHT)

        self.all_tags_listbox = tk.Listbox(self.current_tags_frame)
        self.all_tags_listbox.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0,5))
        self.all_tags_listbox.bind("<Double-1>", self.add_tag_from_all)
        self.all_tags_listbox.bind("<Button-3>", self.edit_tag_from_all)
        
        self.filter_by_tag_btn = tk.Button(
            self.current_tags_frame,
            text="Filter Files by Selected Tag",
            bg="#4CAF50", fg="white", relief="raised"
        )
        self.filter_by_tag_btn.pack(fill=tk.X, pady=4)
        self.filter_by_tag_btn.bind("<Button-1>", self.toggle_tag_file_filter)

        # ==================== BOTTOM: Tags from Other Dataset ====================
        self.other_tags_frame = tk.Frame(self.right_frame)
        self.other_tags_frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(self.other_tags_frame, text="Tags from Other Dataset").pack(anchor="w", padx=5, pady=(5,0))

        # Load button + recursive checkbox on the same line
        load_frame = tk.Frame(self.other_tags_frame)
        load_frame.pack(fill=tk.X, pady=2)

        tk.Button(load_frame, text="Load Other Dataset", command=self.load_other_dataset).pack(side=tk.LEFT, padx=5)

        # <<< CREATE THE CHECKBOX HERE (so it exists when we pack it) >>>
        self.recursive_var = tk.BooleanVar(value=False)
        self.recursive_check = ttk.Checkbutton(
            load_frame,
            variable=self.recursive_var,
            text="Load recursively (include subfolders)"
        )
        self.recursive_check.pack(side=tk.LEFT, padx=20)

        # Filter for other dataset tags
        filter_frame2 = tk.Frame(self.other_tags_frame)
        filter_frame2.pack(fill=tk.X, padx=5, pady=2)
        self.filter_entry2 = tk.Entry(filter_frame2)
        self.filter_entry2.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.filter_entry2.insert(0, "Search other tags...")
        self.filter_entry2.config(fg="grey")
        self.filter_entry2.bind("<FocusIn>", lambda e: self.clear_placeholder(e, "Search other tags..."))
        self.filter_entry2.bind("<FocusOut>", lambda e: self.restore_placeholder(e, "Search other tags..."))
        self.filter_entry2.bind("<KeyRelease>", self.filter_other_tags)

        tk.Button(filter_frame2, text="×", width=2, command=self.clear_filter2).pack(side=tk.RIGHT)

        self.other_tags_listbox = tk.Listbox(self.other_tags_frame)
        self.other_tags_listbox.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0,5))
        self.other_tags_listbox.bind("<Double-1>", self.add_tag_from_other)

    def on_tree_click(self, event=None):
        item = self.file_tree.identify("item", event.x, event.y)
        if item:
            file_path = Path(item)  # ← Ensure this is Path
            self.on_file_select(file_path)

    def on_tree_doubleclick(self, event=None):
        item = self.file_tree.identify("item", event.x, event.y)
        if item:
            file_path = Path(item)  # ← Ensure this is Path
            self.show_large_thumbnail(file_path)
        return "break"

    def on_mouse_wheel(self, event):
        # Handle mouse wheel scrolling for the left pane
        if event.num == 4 or event.delta > 0:  # Scroll up
            self.file_canvas.yview_scroll(-1, "units")
        elif event.num == 5 or event.delta < 0:  # Scroll down
            self.file_canvas.yview_scroll(1, "units")

    def load_directory_dialog(self):
        directory = filedialog.askdirectory(title="Select Media Directory")
        if directory:
            self.load_directory(directory)
            messagebox.showinfo("Success", f"Loaded directory: {directory}")
        else:
            messagebox.showwarning("Warning", "No directory selected.")

    def load_directory(self, directory):
        self.directory = Path(directory)
        recursive = self.main_recursive_var.get()

        # Clear everything
        self.file_tree.delete(*self.file_tree.get_children())
        self.files = []
        self.thumbnails.clear()
        self.large_thumbnails.clear()
        self.video_thumbnails.clear()
        self.current_video_index.clear()
        self.global_tags.clear()

        # Reset tag filter when loading new directory
        self.tag_filter_active = False
        self.current_tag_filter = None
        if hasattr(self, 'filter_by_tag_btn'):
            self.filter_by_tag_btn.config(text="Filter Files by Selected Tag", bg="#4CAF50")

        # Find files
        pattern = "**/*" if recursive else "*"
        for path in self.directory.glob(pattern):
            if path.suffix.lower() in (".jpg", ".png", ".mp4", ".avi") and path.is_file():
                self.files.append(path)

        self.files.sort(key=lambda x: x.as_posix().lower())

        # Insert into Treeview with thumbnails
        for file_path in self.files:
            key = str(file_path)  # ← CHANGE: Use full path, not just .name
            try:
                thumb = self.generate_thumbnail(file_path, size=120)
                large = self.generate_thumbnail(file_path, size=300, unrestricted=True)
            except Exception as e:
                print(f"Thumbnail failed for {file_path}: {e}")
                thumb = large = None

            self.thumbnails[key] = thumb          # ← Now safe
            self.large_thumbnails[key] = large
            if file_path.suffix.lower() in (".mp4", ".avi"):
                self.video_thumbnails[key] = []   # Already correct

            display_name = str(file_path.relative_to(self.directory)) if recursive else file_path.name
            iid = key
            self.file_tree.insert("", "end", iid=iid, text=display_name, image=thumb or "")

            # Load tags
            tag_file = file_path.with_suffix(".txt")
            if tag_file.exists():
                try:
                    tags = tag_file.read_text(encoding="utf-8").strip()
                    if tags:
                        self.global_tags.update(t.strip() for t in tags.split(",") if t.strip())
                except Exception as e:
                    print(f"Tag load failed for {file_path}: {e}")

        self.update_all_tags()
        self.update_autocomplete()

    def on_tree_select(self, event=None):
        selected = self.file_tree.selection()
        if selected:
            path_str = selected[0]
            file_path = Path(path_str)
            self.on_file_select(file_path)

    def load_other_dataset(self):
        directory = filedialog.askdirectory(title="Select Other Dataset Directory")
        if not directory:
            messagebox.showwarning("Warning", "No directory selected.")
            return

        recursive = self.recursive_var.get()          # <-- NEW LINE
        self.other_dataset_tags.clear()
        directory_path = Path(directory)

        txt_files = directory_path.rglob("*.txt") if recursive else directory_path.glob("*.txt")

        for tag_file in txt_files:
            with open(tag_file, "r", encoding="utf-8") as f:
                tags = f.read().strip().split(", ")
                self.other_dataset_tags.update(tag for tag in tags if tag)

        self.update_other_tags()
        mode = "recursively " if recursive else ""
        messagebox.showinfo("Success", f"Loaded tags {mode}from other dataset: {directory}")

    def update_other_tags(self):
        current_filter = self.filter_entry2.get().strip().lower()
        placeholder = "search other tags..."
        if current_filter == "" or current_filter == placeholder.lower():
            self.other_tags_listbox.delete(0, tk.END)
            for tag in sorted(self.other_dataset_tags):
                self.other_tags_listbox.insert(tk.END, tag)
        else:
            self.filter_other_tags()

    def add_tag_from_other(self, event):
        """Add a tag from the other dataset to the current selection."""
        selection = self.other_tags_listbox.curselection()
        if not selection:
            return
        tag_to_add = self.other_tags_listbox.get(selection[0])

        # Get the insertion position for the current selection (middle pane)
        insert_pos = tk.END
        current_selection = self.tag_listbox.curselection()
        if current_selection:
            insert_pos = current_selection[0] + 1

        # Add tag to current selection if not present
        if tag_to_add not in self.tag_listbox.get(0, tk.END):
            self.tag_listbox.insert(insert_pos, tag_to_add)
            self.global_tags.add(tag_to_add)  # Add to current dataset's global tags
            self.update_all_tags()
            self.update_autocomplete()
            self.unsaved_changes = True

    def generate_thumbnail(self, file, size=100, unrestricted=False):
        try:
            if file.suffix.lower() in (".jpg", ".png"):
                img = Image.open(file)
            elif file.suffix.lower() in (".mp4", ".avi"):
                cap = cv2.VideoCapture(str(file))
                ret, frame = cap.read()
                if ret:
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    img = Image.fromarray(frame)
                else:
                    img = Image.new("RGB", (size, size), color="gray")
                cap.release()
            else:
                img = Image.new("RGB", (size, size), color="gray")

            # Resize based on parameters
            width, height = img.size
            if unrestricted:
                # Ensure larger side is at least 'size' pixels
                if max(width, height) < size:
                    if width > height:
                        new_width = size
                        new_height = int(height * (size / width))
                    else:
                        new_height = size
                        new_width = int(width * (size / height))
                    img = img.resize((new_width, new_height), Image.LANCZOS)
            else:
                # Fit within 'size' x 'size' square, maintaining aspect ratio
                if width > height:
                    new_width = size
                    new_height = int(height * (size / width))
                else:
                    new_height = size
                    new_width = int(width * (size / height))
                img = img.resize((new_width, new_height), Image.LANCZOS)

            return ImageTk.PhotoImage(img)
        except Exception as e:
            print(f"Error generating thumbnail for {file}: {e}")
            return ImageTk.PhotoImage(Image.new("RGB", (size, size), color="gray"))

    def extract_video_frames(self, file):
        cap = cv2.VideoCapture(str(file))
        frames = []
        frame_count = 0
        # Get screen dimensions
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        max_width = screen_width - 40  # Account for padding/buttons
        max_height = screen_height - 80  # Account for padding/buttons

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            if frame_count % 25 == 0:  # Capture every 25th frame
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                img = Image.fromarray(frame)
                # Resize to at least 300 on larger side for large view
                width, height = img.size
                if max(width, height) < 300:
                    if width > height:
                        new_width = 300
                        new_height = int(height * (300 / width))
                    else:
                        new_height = 300
                        new_width = int(width * (300 / height))
                    img = img.resize((new_width, new_height), Image.LANCZOS)
                
                # Constrain to screen resolution if larger
                width, height = img.size
                if width > max_width or height > max_height:
                    scale = min(max_width / width, max_height / height)
                    new_width = int(width * scale)
                    new_height = int(height * scale)
                    img = img.resize((new_width, new_height), Image.LANCZOS)

                frames.append(ImageTk.PhotoImage(img))
            frame_count += 1
        cap.release()
        return frames

    def show_large_thumbnail(self, file_path):  # ← Note: Now takes full Path, not just file
        # Get screen dimensions
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        max_width = screen_width - 40
        max_height = screen_height - 80

        key = str(file_path)  # ← FIXED: Use full path as key

        if file_path.suffix.lower() in (".mp4", ".avi"):
            # Extract frames if not already done
            if key not in self.video_thumbnails or not self.video_thumbnails[key]:
                self.video_thumbnails[key] = self.extract_video_frames(file_path)
            frames = self.video_thumbnails[key]
            if not frames:
                messagebox.showwarning("Warning", "No frames extracted from video.")
                return

            # Create window for video frames
            thumbnail_window = Toplevel(self.root)
            thumbnail_window.title(f"Video Frames - {file_path.name}")
            self.current_video_index[thumbnail_window] = 0

            # Dynamically size based on first frame
            img = ImageTk.getimage(frames[0])
            window_width = min(img.width + 40, screen_width)
            window_height = min(img.height + 80, screen_height)
            thumbnail_window.geometry(f"{window_width}x{window_height}")

            # Label for current frame
            self.current_image_label = tk.Label(thumbnail_window)  # ← Note: This is class-level, but works for single windows
            self.current_image_label.pack(pady=10)
            self.update_frame_display(thumbnail_window, frames)

            # Navigation buttons
            button_frame = tk.Frame(thumbnail_window)
            button_frame.pack(pady=5)
            tk.Button(button_frame, text="Previous", 
                      command=lambda: self.change_frame(thumbnail_window, frames, -1)).pack(side=tk.LEFT, padx=5)
            tk.Button(button_frame, text="Next", 
                      command=lambda: self.change_frame(thumbnail_window, frames, 1)).pack(side=tk.LEFT, padx=5)
            tk.Button(button_frame, text="Play", 
                      command=lambda: self.play_video(file_path)).pack(side=tk.LEFT, padx=5)
            tk.Button(thumbnail_window, text="Close", command=thumbnail_window.destroy).pack(pady=5)

            # Key bindings
            thumbnail_window.bind("<Left>", lambda e: self.change_frame(thumbnail_window, frames, -1))
            thumbnail_window.bind("<Right>", lambda e: self.change_frame(thumbnail_window, frames, 1))
            thumbnail_window.bind("<Return>", lambda e: self.play_video(file_path))
            thumbnail_window.focus_set()

        else:
            # For images
            large_thumbnail = self.large_thumbnails.get(key)
            if not large_thumbnail:
                large_thumbnail = self.generate_thumbnail(file_path, size=300, unrestricted=True)
                self.large_thumbnails[key] = large_thumbnail

            if large_thumbnail:
                thumbnail_window = Toplevel(self.root)
                thumbnail_window.title(f"Large Thumbnail - {file_path.name}")

                # Get image and constrain to screen
                img = ImageTk.getimage(large_thumbnail)
                width, height = img.size
                if width > max_width or height > max_height:
                    scale = min(max_width / width, max_height / height)
                    new_width = int(width * scale)
                    new_height = int(height * scale)
                    img = img.resize((new_width, new_height), Image.Resampling.LANCZOS if hasattr(Image, 'Resampling') else Image.LANCZOS)
                    large_thumbnail = ImageTk.PhotoImage(img)

                # Size window
                window_width = min(img.width + 20, screen_width)
                window_height = min(img.height + 40, screen_height)
                thumbnail_window.geometry(f"{window_width}x{window_height}")

                label = tk.Label(thumbnail_window, image=large_thumbnail)
                label.image = large_thumbnail  # Reference to avoid GC
                label.pack(expand=True, padx=10, pady=10)
                tk.Button(thumbnail_window, text="Close", command=thumbnail_window.destroy).pack(pady=5)
                thumbnail_window.focus_set()

    def update_frame_display(self, window, frames):
        current_index = self.current_video_index[window]
        self.current_image_label.config(image=frames[current_index])
        self.current_image_label.image = frames[current_index]  # Keep reference
        self.current_image_label.config(text=f"Frame {current_index + 1} of {len(frames)}")
        window.title(f"Video Frames - {self.current_file.name} (Frame {current_index + 1}/{len(frames)})")

    def change_frame(self, window, frames, direction):
        current_index = self.current_video_index[window]
        new_index = (current_index + direction) % len(frames)
        self.current_video_index[window] = new_index
        self.update_frame_display(window, frames)

    def play_video(self, file):
        """Play the video using the default Windows media player."""
        try:
            os.startfile(str(file))  # Opens the file with the default application on Windows
            print(f"Playing video: {file}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to play video: {e}")

    def on_file_select(self, file):
        # Check for unsaved changes before switching
        if self.unsaved_changes:
            response = messagebox.askyesnocancel("Unsaved Changes", "You have unsaved changes. Do you want to save them before switching files?")
            if response is None:  # Cancel
                return
            elif response:  # Yes
                self.save_tags()
        
        self.current_file = file
        # Highlight selected file
        for frame in self.file_frames:
            if frame.winfo_children()[1]["text"] == file.name:
                frame.config(bg="lightblue")
            else:
                frame.config(bg="white")
        # Load tags for the selected file
        self.load_tags()

    def load_tags(self):
        self.tag_listbox.delete(0, tk.END)
        tag_file = self.current_file.with_suffix(".txt")
        if tag_file.exists():
            with open(tag_file, "r") as f:
                tags = f.read().strip().split(", ")
                for tag in tags:
                    if tag:
                        self.tag_listbox.insert(tk.END, tag)
        self.current_tags = list(self.tag_listbox.get(0, tk.END))
        self.unsaved_changes = False

    def add_tag(self, event=None):
        tag = self.tag_entry.get().strip()
        if tag and tag not in self.tag_listbox.get(0, tk.END):
            self.tag_listbox.insert(tk.END, tag)
            self.global_tags.add(tag)
            self.update_all_tags()
            self.update_autocomplete()
            self.unsaved_changes = True
        self.tag_entry.delete(0, tk.END)

    def check_and_update_global_tags(self):
        # Rebuild global_tags from all files to ensure accuracy
        self.global_tags.clear()
        for file in self.files:
            tag_file = file.with_suffix(".txt")
            if tag_file.exists():
                with open(tag_file, "r") as f:
                    tags = f.read().strip().split(", ")
                    self.global_tags.update(tag for tag in tags if tag)
        self.update_all_tags()
        self.update_autocomplete()

    def delete_tag(self, event=None):
        selection = self.tag_listbox.curselection()
        if selection:
            tag_to_delete = self.tag_listbox.get(selection[0])
            self.tag_listbox.delete(selection[0])
            self.unsaved_changes = True
            # Check if this is the last instance of the tag
            self.check_and_update_global_tags()

    def remove_tag(self):
        selection = self.tag_listbox.curselection()
        if selection:
            tag_to_delete = self.tag_listbox.get(selection[0])
            self.tag_listbox.delete(selection[0])
            self.unsaved_changes = True
            # Check if this is the last instance of the tag
            self.check_and_update_global_tags()

    def insert_tag(self, event=None):
        selection = self.tag_listbox.curselection()
        insert_pos = tk.END if not selection else selection[0] + 1

        # Get the coordinates of the insertion point or last visible item
        bbox = self.tag_listbox.bbox(insert_pos) if insert_pos != tk.END else self.tag_listbox.bbox(self.tag_listbox.size() - 1)
        if bbox:
            x, y, width, height = bbox
            # Convert to screen coordinates
            x_screen = self.tag_listbox.winfo_rootx() + x + 20  # Slight horizontal offset
            y_screen = self.tag_listbox.winfo_rooty() + y + height // 2 - 50  # Vertically centered
        else:
            # Fallback to mouse position if bbox fails
            x_screen, y_screen = self.root.winfo_pointerxy()
            x_screen += 20  # Offset from cursor
            y_screen -= 50  # Adjust vertically

        # Create a popup dialog for entering the new tag
        dialog = Toplevel(self.root)
        dialog.title("Add New Tag")
        dialog.geometry(f"800x120+{x_screen}+{y_screen}")  # Increased width to 400
        dialog.transient(self.root)  # Make dialog modal relative to main window
        dialog.grab_set()  # Ensure dialog is modal

        tk.Label(dialog, text="Enter new tag:").pack(pady=5)
        entry = tk.Entry(dialog)
        entry.pack(pady=5, padx=10, fill=tk.X)  # Fill the width of the dialog (minus padding)
        entry.focus_set()

        def on_ok():
            new_tag = entry.get().strip()
            if new_tag:
                self.tag_listbox.insert(insert_pos, new_tag)
                self.global_tags.add(new_tag)
                self.update_all_tags()
                self.update_autocomplete()
                self.unsaved_changes = True
            dialog.destroy()

        def on_cancel():
            dialog.destroy()

        button_frame = tk.Frame(dialog)
        button_frame.pack(pady=5)
        tk.Button(button_frame, text="OK", command=on_ok).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Cancel", command=on_cancel).pack(side=tk.LEFT, padx=5)

        # Bind Enter and Escape keys
        dialog.bind("<Return>", lambda e: on_ok())
        dialog.bind("<Escape>", lambda e: on_cancel())

        # Print debug info to verify the method is called
        print(f"Insert triggered at position {insert_pos}, dialog positioned at {x_screen}, {y_screen}")

    def add_tag_from_all(self, event):
        # Get the selected tag from the all_tags_listbox
        selection = self.all_tags_listbox.curselection()
        if not selection:
            return
        tag_to_add = self.all_tags_listbox.get(selection[0])

        # Get the insertion position for the current selection (middle pane)
        insert_pos = tk.END
        current_selection = self.tag_listbox.curselection()
        if current_selection:
            insert_pos = current_selection[0] + 1

        # Add tag to current selection if not present
        if tag_to_add not in self.tag_listbox.get(0, tk.END):
            self.tag_listbox.insert(insert_pos, tag_to_add)
            self.unsaved_changes = True

    def edit_tag_from_all(self, event):
        # Get the selected tag from the all_tags_listbox
        selection = self.all_tags_listbox.curselection()
        if not selection:
            return
        tag_to_edit = self.all_tags_listbox.get(selection[0])

        # Get the coordinates near the all_tags_listbox
        bbox = self.all_tags_listbox.bbox(selection[0])
        if bbox:
            x, y, width, height = bbox
            x_screen = self.all_tags_listbox.winfo_rootx() + x + 20  # Slight horizontal offset
            y_screen = self.all_tags_listbox.winfo_rooty() + y + height // 2 - 50  # Vertically centered
        else:
            x_screen, y_screen = self.root.winfo_pointerxy()
            x_screen += 20
            y_screen -= 50

        # Create a popup dialog for editing the tag
        dialog = Toplevel(self.root)
        dialog.title("Edit Tag")
        dialog.geometry(f"800x100+{x_screen}+{y_screen}")
        dialog.transient(self.root)
        dialog.grab_set()

        tk.Label(dialog, text="Edit tag (affects all files):").pack(pady=5)
        entry = tk.Entry(dialog, width=30)
        entry.insert(0, tag_to_edit)  # Pre-fill with the current tag
        entry.pack(pady=5)
        entry.focus_set()
        entry.select_range(0, tk.END)  # Select the text for easy editing

        def on_ok():
            new_tag = entry.get().strip()
            if new_tag and new_tag != tag_to_edit:
                # Update the tag in all_tags_listbox
                index = self.all_tags_listbox.get(0, tk.END).index(tag_to_edit)
                self.all_tags_listbox.delete(index)
                self.all_tags_listbox.insert(index, new_tag)

                # Update global_tags
                self.global_tags.remove(tag_to_edit)
                self.global_tags.add(new_tag)

                # Update all media files with the new tag
                self.update_tag_in_all_files(tag_to_edit, new_tag)

                # Update current selection if the old tag is present
                current_tags = self.tag_listbox.get(0, tk.END)
                if tag_to_edit in current_tags:
                    tag_index = current_tags.index(tag_to_edit)
                    self.tag_listbox.delete(tag_index)
                    self.tag_listbox.insert(tag_index, new_tag)

                # Update autocomplete
                self.update_autocomplete()
                self.unsaved_changes = True
            dialog.destroy()

        def on_cancel():
            dialog.destroy()

        button_frame = tk.Frame(dialog)
        button_frame.pack(pady=5)
        tk.Button(button_frame, text="OK", command=on_ok).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Cancel", command=on_cancel).pack(side=tk.LEFT, padx=5)

        # Bind Enter and Escape keys
        dialog.bind("<Return>", lambda e: on_ok())
        dialog.bind("<Escape>", lambda e: on_cancel())

    def edit_tag_in_current(self, event):
        # Get the selected tag from the tag_listbox
        selection = self.tag_listbox.curselection()
        if not selection:
            return
        tag_to_edit = self.tag_listbox.get(selection[0])
        index = selection[0]

        # Get the coordinates near the tag_listbox
        bbox = self.tag_listbox.bbox(index)
        if bbox:
            x, y, width, height = bbox
            x_screen = self.tag_listbox.winfo_rootx() + x + 20  # Slight horizontal offset
            y_screen = self.tag_listbox.winfo_rooty() + y + height // 2 - 50  # Vertically centered
        else:
            x_screen, y_screen = self.root.winfo_pointerxy()
            x_screen += 20
            y_screen -= 50

        # Create a popup dialog for editing the tag
        dialog = Toplevel(self.root)
        dialog.title("Edit Tag")
        dialog.geometry(f"800x100+{x_screen}+{y_screen}")
        dialog.transient(self.root)
        dialog.grab_set()

        tk.Label(dialog, text="Edit tag (current file only):").pack(pady=5)
        entry = tk.Entry(dialog, width=30)
        entry.insert(0, tag_to_edit)  # Pre-fill with the current tag
        entry.pack(pady=5, padx=10, fill=tk.X)
        entry.focus_set()
        entry.select_range(0, tk.END)  # Select the text for easy editing

        def on_ok():
            new_tag = entry.get().strip()
            if new_tag and new_tag != tag_to_edit:
                # Update the tag in the current selection only
                self.tag_listbox.delete(index)
                self.tag_listbox.insert(index, new_tag)
                # Update global_tags if the new tag is not already present
                self.global_tags.add(new_tag)
                # Check if the old tag is still in use across files
                self.check_and_update_global_tags()
                self.unsaved_changes = True
            dialog.destroy()

        def on_cancel():
            dialog.destroy()

        button_frame = tk.Frame(dialog)
        button_frame.pack(pady=5)
        tk.Button(button_frame, text="OK", command=on_ok).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Cancel", command=on_cancel).pack(side=tk.LEFT, padx=5)

        # Bind Enter and Escape keys
        dialog.bind("<Return>", lambda e: on_ok())
        dialog.bind("<Escape>", lambda e: on_cancel())

    def update_tag_in_all_files(self, old_tag, new_tag):
        for file in self.files:
            tag_file = file.with_suffix(".txt")
            if tag_file.exists():
                with open(tag_file, "r") as f:
                    tags = f.read().strip().split(", ")
                if old_tag in tags:
                    tags = [new_tag if tag == old_tag else tag for tag in tags]
                    with open(tag_file, "w") as f:
                        f.write(", ".join(tags))

    def set_selection(self, index):
        """Helper method to set selection and activate the item in the Listbox."""
        self.tag_listbox.selection_clear(0, tk.END)
        self.tag_listbox.selection_set(index)
        self.tag_listbox.activate(index)
        self.tag_listbox.see(index)
        print(f"Set selection to index {index}, selected: {self.tag_listbox.curselection()}")

    def move_tag_up(self, event):
        selection = self.tag_listbox.curselection()
        if not selection or selection[0] == 0:
            return "break"  # Consume the event
        index = selection[0]
        print(f"Before move up: Index {index}, List {self.tag_listbox.get(0, tk.END)}, Selection {self.tag_listbox.curselection()}")
        # Get the tags directly from the Listbox
        tag_above = self.tag_listbox.get(index - 1)
        moved_tag = self.tag_listbox.get(index)
        # Swap the tags in the Listbox without full rebuild
        self.tag_listbox.delete(index)
        self.tag_listbox.insert(index, tag_above)
        self.tag_listbox.delete(index - 1)
        self.tag_listbox.insert(index - 1, moved_tag)
        # Schedule the selection update to ensure it takes effect
        new_index = index - 1
        self.root.after(1, lambda: self.set_selection(new_index))
        self.unsaved_changes = True
        print(f"After move up: New Index {new_index}, List {self.tag_listbox.get(0, tk.END)}, Selection {self.tag_listbox.curselection()}")
        return "break"  # Consume the event to prevent default behavior

    def move_tag_down(self, event):
        selection = self.tag_listbox.curselection()
        if not selection or selection[0] == self.tag_listbox.size() - 1:
            return "break"  # Consume the event
        index = selection[0]
        print(f"Before move down: Index {index}, List {self.tag_listbox.get(0, tk.END)}, Selection {self.tag_listbox.curselection()}")
        # Get the tags directly from the Listbox
        tag_below = self.tag_listbox.get(index + 1)
        moved_tag = self.tag_listbox.get(index)
        # Swap the tags in the Listbox without full rebuild
        self.tag_listbox.delete(index)
        self.tag_listbox.insert(index, tag_below)
        self.tag_listbox.delete(index + 1)
        self.tag_listbox.insert(index + 1, moved_tag)
        # Schedule the selection update to ensure it takes effect
        new_index = index + 1
        self.root.after(1, lambda: self.set_selection(new_index))
        self.unsaved_changes = True
        print(f"After move down: New Index {new_index}, List {self.tag_listbox.get(0, tk.END)}, Selection {self.tag_listbox.curselection()}")
        return "break"  # Consume the event to prevent default behavior

    def copy_tags(self):
        if not hasattr(self, "current_file"):
            messagebox.showwarning("Warning", "No file selected.")
            return
        self.copied_tags = list(self.tag_listbox.get(0, tk.END))
        messagebox.showinfo("Success", f"Copied {len(self.copied_tags)} tags.")

    def paste_tags(self):
        if not hasattr(self, "current_file"):
            messagebox.showwarning("Warning", "No file selected.")
            return
        if not self.copied_tags:
            messagebox.showwarning("Warning", "No tags copied to paste.")
            return
        # Replace the current tags with the copied tags
        self.tag_listbox.delete(0, tk.END)
        for tag in self.copied_tags:
            self.tag_listbox.insert(tk.END, tag)
        self.unsaved_changes = True
        # Update global_tags to reflect any new tags
        self.global_tags.update(self.copied_tags)
        self.update_all_tags()
        self.update_autocomplete()
        messagebox.showinfo("Success", f"Pasted {len(self.copied_tags)} tags.")

    def save_tags(self):
        if not hasattr(self, "current_file"):
            messagebox.showwarning("Warning", "No file selected.")
            return
        tags = self.tag_listbox.get(0, tk.END)
        tag_file = self.current_file.with_suffix(".txt")
        with open(tag_file, "w") as f:
            f.write(", ".join(tags))
        # Update global tags after saving
        self.check_and_update_global_tags()
        self.current_tags = list(self.tag_listbox.get(0, tk.END))
        self.unsaved_changes = False
        messagebox.showinfo("Success", f"Tags saved for {self.current_file.name}")

    def add_tag_to_all(self):
        if not self.files:
            messagebox.showwarning("Warning", "No directory loaded.")
            return
        tag = self.tag_entry.get().strip()
        if not tag:
            messagebox.showwarning("Warning", "Please enter a tag to add.")
            return
        for file in self.files:
            tag_file = file.with_suffix(".txt")
            tags = set()
            if tag_file.exists():
                with open(tag_file, "r") as f:
                    tags = set(f.read().strip().split(", "))
            if tag not in tags:
                tags.add(tag)
                with open(tag_file, "w") as f:
                    f.write(", ".join(tags))
        self.global_tags.add(tag)
        self.update_all_tags()
        self.update_autocomplete()
        self.load_tags()
        messagebox.showinfo("Success", f"Tag '{tag}' added to all files.")

    def remove_tag_from_all(self):
        if not self.files:
            messagebox.showwarning("Warning", "No directory loaded.")
            return
        tag = self.tag_entry.get().strip()
        if not tag:
            messagebox.showwarning("Warning", "Please enter a tag to remove.")
            return
        for file in self.files:
            tag_file = file.with_suffix(".txt")
            if tag_file.exists():
                with open(tag_file, "r") as f:
                    tags = set(f.read().strip().split(", "))
                if tag in tags:
                    tags.remove(tag)
                    with open(tag_file, "w") as f:
                        f.write(", ".join(tags))
        # Check if the tag is still in use
        self.check_and_update_global_tags()
        self.load_tags()
        messagebox.showinfo("Success", f"Tag '{tag}' removed from all files.")

    def update_all_tags(self):
        # Only update if no active filter (or filter is placeholder)
        current_filter = self.filter_entry1.get().strip().lower()
        placeholder = "search tags..."
        if current_filter == "" or current_filter == placeholder.lower():
            self.all_tags_listbox.delete(0, tk.END)
            for tag in sorted(self.global_tags):
                self.all_tags_listbox.insert(tk.END, tag)
        else:
            # If there's an active filter, re-apply it
            self.filter_current_tags()

    def update_autocomplete(self):
        self.tag_entry["values"] = sorted(self.global_tags)

if __name__ == "__main__":
    root = tk.Tk()
    app = MediaTagManager(root)
    root.mainloop()