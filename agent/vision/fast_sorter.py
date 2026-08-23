import os
import sys
import shutil
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk
from dotenv import load_dotenv

class FastSorterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Lightning Fast Image Sorter ⚡")
        self.root.geometry("1000x800")
        self.root.configure(bg="#1e1e1e")
        
        # State
        self.current_dir = ""
        self.image_files = []
        self.current_index = 0
        self.categories = []
        self.category_dirs = {}
        self.undo_stack = [] # list of tuples: (original_path, new_path)
        
        # Try to load categories from .env
        self.load_categories()
        
        # Setup UI
        self.setup_ui()
        
        # Bind Keys
        self.root.bind("<Left>", lambda e: self.prev_image())
        self.root.bind("<Right>", lambda e: self.next_image())
        self.root.bind("<Control-z>", lambda e: self.undo_last_move())
        for i in range(1, 10):
            self.root.bind(str(i), lambda e, idx=i: self.sort_image(idx))
            
        # Prompt for folder to review
        self.root.after(100, self.select_folder)

    def load_categories(self):
        load_dotenv()
        dirs_env = os.getenv("CNN_TRAINING_DIRECTORIES", "")
        if not dirs_env:
            dirs_env = r"F:\Users\myfri\Downloads\LabeledCrops(Test)" # Fallback
            
        self.gold_standard_dir = os.getenv("CNN_GOLD_STANDARD_DIR", "")
            
        dir_paths = [d.strip() for d in dirs_env.split(',') if d.strip()]
        
        category_set = set()
        for dir_path in dir_paths:
            if os.path.exists(dir_path):
                for d in os.listdir(dir_path):
                    full_path = os.path.join(dir_path, d)
                    if os.path.isdir(full_path):
                        category_set.add(d)
                        
        self.categories = sorted(list(category_set))

    def setup_ui(self):
        # Top Frame (Controls & Info)
        self.top_frame = tk.Frame(self.root, bg="#2d2d2d", pady=10)
        self.top_frame.pack(fill=tk.X)
        
        self.lbl_info = tk.Label(self.top_frame, text="Select a folder to begin...", bg="#2d2d2d", fg="white", font=("Arial", 14))
        self.lbl_info.pack()
        
        # Legend Frame (Hotkeys)
        self.legend_frame = tk.Frame(self.root, bg="#1e1e1e", pady=10)
        self.legend_frame.pack(fill=tk.X)
        
        self.legend_labels = []
        for i, cat in enumerate(self.categories):
            key = i + 1
            if key > 9: break # Only map 1-9
            lbl = tk.Label(self.legend_frame, text=f"[{key}] {cat}", bg="#3d3d3d", fg="#56b6c2", font=("Arial", 12, "bold"), padx=10, pady=5)
            lbl.pack(side=tk.LEFT, padx=5)
            self.legend_labels.append(lbl)
            
        # Image Display
        self.canvas = tk.Canvas(self.root, bg="#000000", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Bottom Instructions
        self.bottom_frame = tk.Frame(self.root, bg="#2d2d2d")
        self.bottom_frame.pack(fill=tk.X, side=tk.BOTTOM)
        tk.Label(self.bottom_frame, text="Left/Right: Navigate | 1-9: Move to Folder | Ctrl+Z: Undo", bg="#2d2d2d", fg="#abb2bf", font=("Arial", 10), pady=5).pack()

    def select_folder(self):
        if not self.categories:
            messagebox.showerror("Error", "Could not load target categories. Check CNN_TRAINING_DIRECTORIES in .env")
            return
            
        folder = filedialog.askdirectory(title="Select Folder to Review (e.g. Background)")
        if not folder:
            sys.exit()
            
        self.current_dir = folder
        self.load_images()
        
    def load_images(self):
        self.image_files = []
        for f in os.listdir(self.current_dir):
            if f.lower().endswith(('.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp')):
                self.image_files.append(os.path.join(self.current_dir, f))
                
        self.image_files.sort()
        self.current_index = 0
        self.undo_stack.clear()
        
        if not self.image_files:
            messagebox.showinfo("Done", "No images found in this folder!")
            return
            
        self.show_image()
        
    def show_image(self):
        if not self.image_files:
            self.canvas.delete("all")
            self.lbl_info.config(text="Folder is empty! All done!")
            return
            
        # Bounds check
        if self.current_index >= len(self.image_files):
            self.current_index = len(self.image_files) - 1
        if self.current_index < 0:
            self.current_index = 0
            
        img_path = self.image_files[self.current_index]
        filename = os.path.basename(img_path)
        
        self.lbl_info.config(text=f"[{self.current_index + 1} / {len(self.image_files)}] {filename}")
        
        try:
            img = Image.open(img_path)
            
            # Calculate scale to fit canvas while preserving aspect ratio
            canvas_w = self.canvas.winfo_width()
            canvas_h = self.canvas.winfo_height()
            
            # Fallback if canvas isn't drawn yet
            if canvas_w < 10: canvas_w = 800
            if canvas_h < 10: canvas_h = 600
            
            img_w, img_h = img.size
            scale = min(canvas_w / img_w, canvas_h / img_h) * 0.45  # 45% of canvas size
            
            new_w = max(1, int(img_w * scale))
            new_h = max(1, int(img_h * scale))
            
            # Use LANCZOS for high-quality smoothing instead of raw pixels
            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            
            self.photo = ImageTk.PhotoImage(img)
            self.canvas.delete("all")
            self.canvas.create_image(canvas_w//2, canvas_h//2, anchor=tk.CENTER, image=self.photo)
        except Exception as e:
            print(f"Error loading {img_path}: {e}")
            
    def next_image(self):
        if self.image_files and self.current_index < len(self.image_files) - 1:
            self.current_index += 1
            self.show_image()

    def prev_image(self):
        if self.image_files and self.current_index > 0:
            self.current_index -= 1
            self.show_image()
            
    def sort_image(self, key_idx):
        if not self.image_files: return
        
        # key_idx is 1-based
        list_idx = key_idx - 1
        if list_idx >= len(self.categories):
            return # Invalid key for current categories
            
        target_cat = self.categories[list_idx]
        
        # Move it to the sibling directory in the staging area!
        staging_root = os.path.dirname(self.current_dir)
        target_dir = os.path.join(staging_root, target_cat)
        os.makedirs(target_dir, exist_ok=True)
        
        current_img_path = self.image_files[self.current_index]
        filename = os.path.basename(current_img_path)
        new_path = os.path.join(target_dir, filename)
        
        try:
            # Move file
            shutil.move(current_img_path, new_path)
            
            # Copy to Gold Standard if enabled
            gs_copy_path = None
            if self.gold_standard_dir and os.path.exists(self.gold_standard_dir):
                gs_target_dir = os.path.join(self.gold_standard_dir, target_cat)
                os.makedirs(gs_target_dir, exist_ok=True)
                gs_copy_path = os.path.join(gs_target_dir, filename)
                shutil.copy2(new_path, gs_copy_path)
            
            # Record for undo
            self.undo_stack.append((current_img_path, new_path, gs_copy_path))
            
            # Flash the legend label to show it worked
            lbl = self.legend_labels[list_idx]
            orig_bg = lbl.cget("bg")
            lbl.config(bg="#98c379", fg="#282c34")
            self.root.after(200, lambda: lbl.config(bg=orig_bg, fg="#56b6c2"))
            
            # Remove from list and show next
            del self.image_files[self.current_index]
            self.show_image()
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to move file:\n{e}")

    def undo_last_move(self):
        if not self.undo_stack:
            return
            
        orig_path, new_path, gs_copy_path = self.undo_stack.pop()
        
        try:
            # Move back to staging
            shutil.move(new_path, orig_path)
            
            # Remove from Gold Standard if we copied it there
            if gs_copy_path and os.path.exists(gs_copy_path):
                os.remove(gs_copy_path)
            
            # Insert back into list and jump to it
            self.image_files.insert(self.current_index, orig_path)
            self.show_image()
            
            # Visual feedback
            self.lbl_info.config(text=f"UNDO: Restored {os.path.basename(orig_path)}", fg="#e06c75")
            self.root.after(1000, lambda: self.lbl_info.config(fg="white"))
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to undo:\n{e}")

if __name__ == "__main__":
    root = tk.Tk()
    app = FastSorterApp(root)
    root.mainloop()
