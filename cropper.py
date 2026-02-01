#!/usr/bin/env python3
"""
E-ink Picture Cropper
Usage:
  python cropper.py /path/to/pictures  # First time: scan and build list
  python cropper.py                     # Subsequent times: crop pictures
"""

import sys
import os
import re
from PIL import Image, ImageTk

UI_SCALE = 2.0
EDGE_GRAB = int(10 * UI_SCALE)   # thickness of edge grab zones
HANDLE_SIZE = int(12 * UI_SCALE)
CROP_LINE_WIDTH = int(3 * UI_SCALE)


SUPPORTED_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}


def find_pictures(root_path):
    """Recursively find all supported image files."""
    pictures = []

    for dirpath, dirnames, filenames in os.walk(root_path, followlinks=True):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]

        for filename in filenames:
            ext = os.path.splitext(filename)[1].lower()
            if ext in SUPPORTED_EXTS:
                pictures.append(os.path.abspath(os.path.join(dirpath, filename)))

    return pictures


def save_picture_list(pictures, list_file):
    with open(list_file, "w") as f:
        for pic in pictures:
            f.write(pic + "\n")


def load_picture_list(list_file):
    if not os.path.exists(list_file):
        return []
    with open(list_file) as f:
        return [line.strip() for line in f if line.strip()]


def sanitize_filename(filename):
    name, _ = os.path.splitext(filename)
    name = re.sub(r"[^\w\-]", "_", name)
    name = re.sub(r"_+", "_", name)
    return name + ".png"   # OUTPUT ALWAYS PNG


def get_unique_filename(output_dir, filename):
    sanitized = sanitize_filename(filename)
    path = os.path.join(output_dir, sanitized)

    if not os.path.exists(path):
        return path

    base, ext = os.path.splitext(sanitized)
    i = 1
    while True:
        candidate = os.path.join(output_dir, f"{base}_{i}{ext}")
        if not os.path.exists(candidate):
            return candidate
        i += 1


class CropWindow:
    def __init__(self, image_path, list_file, output_dir):
        import tkinter as tk
        from PIL import Image

        self.image_path = image_path
        self.list_file = list_file
        self.output_dir = output_dir
        self.rotation = 0

        self.original_image = Image.open(image_path)
        self.current_image = self.original_image.copy()

        self.target_ratio = 3 / 4

        self.root = tk.Tk()
        self.root.title(os.path.basename(image_path))

        # Start large
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.root.geometry(f"{int(sw*0.95)}x{int(sh*0.95)}+20+20")

        # Toolbar
        toolbar = tk.Frame(self.root)
        toolbar.pack(side=tk.TOP, fill=tk.X)

        btn_opts = {
            "font": ("TkDefaultFont", int(12 * UI_SCALE)),
            "padx": int(10 * UI_SCALE),
            "pady": int(5 * UI_SCALE),
        }

        tk.Button(toolbar, text="⟲ Rotate Left", command=self.rotate_left, **btn_opts).pack(side=tk.LEFT, padx=5)
        tk.Button(toolbar, text="⟳ Rotate Right", command=self.rotate_right, **btn_opts).pack(side=tk.LEFT)
        tk.Button( toolbar, text="✖ Quit", command=self.quit_all, **btn_opts).pack(side=tk.RIGHT, padx=10)


        self.canvas = tk.Canvas(self.root, bg="gray")
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.crop_x = self.crop_y = 0
        self.crop_width = self.crop_height = 100
        self.drag_data = {"x": 0, "y": 0, "item": None}
        self.resize_handle = None
        self.resize_data = {}

        self.display_image()
        self.initialize_crop_rectangle()

        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)

        self.root.bind("<Return>", self.save_cropped)
        self.root.bind("<Escape>", self.skip_picture)
        self.root.bind("<Delete>", self.skip_picture)
        self.root.bind("<Left>", self.rotate_left)
        self.root.bind("<Right>", self.rotate_right)

        def start_move(event):
            self._win_x = event.x
            self._win_y = event.y

        def do_move(event):
            x = self.root.winfo_x() + event.x - self._win_x
            y = self.root.winfo_y() + event.y - self._win_y
            self.root.geometry(f"+{x}+{y}")

        toolbar.bind("<ButtonPress-1>", start_move)
        toolbar.bind("<B1-Motion>", do_move)


    def quit_all(self):
        print("Aborted by user.")
        self.root.quit()
        self.root.destroy()
        sys.exit(0)

    def hit_test_edge(self, x, y):
        left = abs(x - self.crop_x) <= EDGE_GRAB
        right = abs(x - (self.crop_x + self.crop_width)) <= EDGE_GRAB
        top = abs(y - self.crop_y) <= EDGE_GRAB
        bottom = abs(y - (self.crop_y + self.crop_height)) <= EDGE_GRAB

        return {
            "left": left,
            "right": right,
            "top": top,
            "bottom": bottom,
        }


    def display_image(self):
        from PIL import Image, ImageTk

        self.root.update_idletasks()
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()

        iw, ih = self.current_image.size
        scale = min(cw / iw, ch / ih, 1.0)

        self.display_scale = scale
        disp = self.current_image.resize(
            (int(iw * scale), int(ih * scale)),
            Image.Resampling.LANCZOS,
        )

        self.displayed_image = disp
        self.photo = ImageTk.PhotoImage(disp)

        self.image_x = (cw - disp.width) // 2
        self.image_y = (ch - disp.height) // 2

        self.canvas.delete("all")
        self.canvas.create_image(self.image_x, self.image_y, anchor="nw", image=self.photo)

    def initialize_crop_rectangle(self):
        iw, ih = self.displayed_image.size

        if iw / ih > self.target_ratio:
            self.crop_height = ih
            self.crop_width = int(ih * self.target_ratio)
        else:
            self.crop_width = iw
            self.crop_height = int(iw / self.target_ratio)

        self.crop_x = self.image_x + (iw - self.crop_width) // 2
        self.crop_y = self.image_y + (ih - self.crop_height) // 2

        self.draw_crop_rectangle()

    def draw_crop_rectangle(self):
        self.canvas.delete("crop", "handle")

        self.canvas.create_rectangle(
            self.crop_x,
            self.crop_y,
            self.crop_x + self.crop_width,
            self.crop_y + self.crop_height,
            outline="red",
            width=2,
            tags="crop",
        )

        h = 10
        self.resize_handle = self.canvas.create_rectangle(
            self.crop_x + self.crop_width - h,
            self.crop_y + self.crop_height - h,
            self.crop_x + self.crop_width + h,
            self.crop_y + self.crop_height + h,
            fill="red",
            tags="handle",
        )
        self.canvas.tag_raise("crop")


    def on_press(self, event):
        """
        Mouse button pressed:
        - Click near an edge → resize
        - Click inside rectangle → move
        """
        edges = self.hit_test_edge(event.x, event.y)

        # Are we close enough to an edge to resize?
        on_edge = (
            edges["left"] or edges["right"] or
            edges["top"] or edges["bottom"]
        )

        # Are we clearly inside the rectangle (not near edges)?
        inside_inner_area = (
            self.crop_x + EDGE_GRAB < event.x < self.crop_x + self.crop_width - EDGE_GRAB and
            self.crop_y + EDGE_GRAB < event.y < self.crop_y + self.crop_height - EDGE_GRAB
        )

        if on_edge and not inside_inner_area:
            # Start resize
            self.drag_data = {
                "item": "resize",
                "edges": edges,
                "x": event.x,
                "y": event.y,
                "w": self.crop_width,
                "h": self.crop_height,
                "cx": self.crop_x,
                "cy": self.crop_y,
            }
        elif (
            self.crop_x <= event.x <= self.crop_x + self.crop_width and
            self.crop_y <= event.y <= self.crop_y + self.crop_height
        ):
            # Start move
            self.drag_data = {
                "item": "move",
                "x": event.x,
                "y": event.y,
            }
        else:
            # Clicked outside crop rectangle
            self.drag_data = {"item": None}




    def on_drag(self, event):
        if self.drag_data["item"] == "move":
            dx = event.x - self.drag_data["x"]
            dy = event.y - self.drag_data["y"]

            # Calculate new position
            new_x = self.crop_x + dx
            new_y = self.crop_y + dy

            # Get image boundaries
            img_w, img_h = self.displayed_image.size
            img_right = self.image_x + img_w
            img_bottom = self.image_y + img_h

            # Constrain to image boundaries
            new_x = max(self.image_x, min(new_x, img_right - self.crop_width))
            new_y = max(self.image_y, min(new_y, img_bottom - self.crop_height))

            self.crop_x = new_x
            self.crop_y = new_y
            self.drag_data["x"] = event.x
            self.drag_data["y"] = event.y
            self.draw_crop_rectangle()

        elif self.drag_data["item"] == "resize":
            d = self.drag_data
            dx = event.x - d["x"]
            dy = event.y - d["y"]

            # Decide which axis drives the resize
            use_dx = abs(dx) > abs(dy)

            # Start from original geometry
            new_w = d["w"]
            new_h = d["h"]
            new_x = d["cx"]
            new_y = d["cy"]

            # Get image boundaries
            img_w, img_h = self.displayed_image.size
            img_right = self.image_x + img_w
            img_bottom = self.image_y + img_h

            if use_dx:
                # Horizontal-driven resize
                if d["edges"]["right"]:
                    new_w = max(20, d["w"] + dx)
                    # Constrain to image right edge
                    max_w = img_right - d["cx"]
                    new_w = min(new_w, max_w)
                elif d["edges"]["left"]:
                    new_w = max(20, d["w"] - dx)
                    # Constrain to image left edge
                    max_w = d["cx"] + d["w"] - self.image_x
                    new_w = min(new_w, max_w)
                    new_x = d["cx"] + (d["w"] - new_w)

                new_h = int(new_w / self.target_ratio)
                # Constrain height to image boundaries
                if new_y + new_h > img_bottom:
                    new_h = img_bottom - new_y
                    new_w = int(new_h * self.target_ratio)

            else:
                # Vertical-driven resize
                if d["edges"]["bottom"]:
                    new_h = max(20, d["h"] + dy)
                    # Constrain to image bottom edge
                    max_h = img_bottom - d["cy"]
                    new_h = min(new_h, max_h)
                elif d["edges"]["top"]:
                    new_h = max(20, d["h"] - dy)
                    # Constrain to image top edge
                    max_h = d["cy"] + d["h"] - self.image_y
                    new_h = min(new_h, max_h)
                    new_y = d["cy"] + (d["h"] - new_h)

                new_w = int(new_h * self.target_ratio)
                # Constrain width to image boundaries
                if new_x + new_w > img_right:
                    new_w = img_right - new_x
                    new_h = int(new_w / self.target_ratio)

            self.crop_x = new_x
            self.crop_y = new_y
            self.crop_width = new_w
            self.crop_height = new_h

            self.draw_crop_rectangle()




    def on_release(self, _):
        self.drag_data["item"] = None

    def rotate_left(self, _=None):
        from PIL import Image
        self.rotation = (self.rotation + 90) % 360  # PIL rotates counter-clockwise with positive angles
        self.current_image = self.original_image.rotate(self.rotation, expand=True)
        self.display_image()
        self.initialize_crop_rectangle()

    def rotate_right(self, _=None):
        from PIL import Image
        self.rotation = (self.rotation - 90) % 360  # Use negative for clockwise
        self.current_image = self.original_image.rotate(self.rotation, expand=True)
        self.display_image()
        self.initialize_crop_rectangle()

    def save_cropped(self, _=None):
        from PIL import Image

        x = int((self.crop_x - self.image_x) / self.display_scale)
        y = int((self.crop_y - self.image_y) / self.display_scale)
        w = int(self.crop_width / self.display_scale)
        h = int(self.crop_height / self.display_scale)

        cropped = self.current_image.crop((x, y, x + w, y + h))
        final = cropped.resize((1200, 1600), Image.Resampling.LANCZOS)

        out = get_unique_filename(self.output_dir, os.path.basename(self.image_path))
        final.save(out, "PNG")
        print("Saved:", out)

        self.remove_from_list()
        self.root.destroy()

    def skip_picture(self, _=None):
        print("Skipped:", self.image_path)
        self.remove_from_list()
        self.root.destroy()

    def remove_from_list(self):
        pics = load_picture_list(self.list_file)
        if self.image_path in pics:
            pics.remove(self.image_path)
            save_picture_list(pics, self.list_file)

    def run(self):
        self.root.mainloop()


def main():
    output_dir = "./cropped_pictures"
    list_file = os.path.join(output_dir, "pictures_to_process.txt")
    os.makedirs(output_dir, exist_ok=True)

    if len(sys.argv) > 1:
        if os.path.exists(list_file):
            print("Delete existing picture list first.")
            sys.exit(1)

        pictures = find_pictures(sys.argv[1])
        print(f"Found {len(pictures)} images")
        save_picture_list(pictures, list_file)
    else:
        pictures = load_picture_list(list_file)
        while pictures:
            CropWindow(pictures[0], list_file, output_dir).run()
            pictures = load_picture_list(list_file)


if __name__ == "__main__":
    main()
