"""
PowerMaster_ASUS - Silent Windows Launcher (.pyw)
Executes PowerMaster with pythonw.exe without opening a console window.
"""

import os
import sys

# Ensure current working directory is the application root
APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)
os.chdir(APP_DIR)

from main import main

if __name__ == "__main__":
    main()
