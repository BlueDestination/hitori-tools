from hitori_addon.const import KK_DIR
from hitori_addon.run import run_command


def start_game():
    kk_exe = KK_DIR / "KoikatsuSunshine.exe"
    run_command([kk_exe], block=False, window=True)


if __name__ == "__main__":
    start_game()
