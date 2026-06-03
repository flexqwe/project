import time
from .utils import check_notes, check_telegram_callbacks


def start_checker():
    print("CHECKER RUNNING 🔥")

    while True:
        try:
            check_notes()
            check_telegram_callbacks()
        except Exception as e:
            print("CHECK ERROR:", e)

        time.sleep(20)
