import sys

from hitori_addon.const import DESKTOP_DIR
from hitori_addon.image import img_to_kk_color
from hitori_addon.path import get_file_stem


def main():
    args = sys.argv[sys.argv.index("--") + 1 :]
    img_paths = args
    for img_path in img_paths:
        img_stem = get_file_stem(img_path)
        output_path = DESKTOP_DIR / f"{img_stem}.png"
        img_to_kk_color(img_path, output_path, "PNG")


if __name__ == "__main__":
    main()
