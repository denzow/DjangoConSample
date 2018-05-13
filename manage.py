#!/usr/bin/env python
import os
import sys


from logging import getLogger, Formatter, StreamHandler, DEBUG
logger = getLogger('django_con')
formatter = Formatter('%(asctime)s - %(filename)s:%(lineno)s[%(funcName)s] - %(message)s')
handler = StreamHandler()
handler.setLevel(DEBUG)
handler.setFormatter(formatter)
logger.setLevel(DEBUG)
logger.addHandler(handler)



if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "myproj.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)
