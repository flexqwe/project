import os
import threading

from django.apps import AppConfig as DjangoAppConfig


_checker_started = False


class AppConfig(DjangoAppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app'

    def ready(self):
        global _checker_started

        # runserver autoreloader ikki marta start bermasligi uchun guard
        if os.environ.get('RUN_MAIN') != 'true' and os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
            return

        if _checker_started:
            return

        try:
            from .background import start_checker

            thread = threading.Thread(target=start_checker, daemon=True)
            thread.start()
            _checker_started = True

            print("BACKGROUND STARTED 🔥")

        except Exception as e:
            print("BACKGROUND ERROR:", e)
