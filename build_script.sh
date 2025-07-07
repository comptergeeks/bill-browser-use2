#!/bin/bash

# PyInstaller script to build the executable
pyinstaller workflow_run.py \
  --onefile \
  --hidden-import pydantic.deprecated.decorator \
  --collect-data patchright \
  --collect-all browser_use \
  --add-data ".env:." \
  --copy-metadata pydantic \
  --copy-metadata openai \
  --exclude-module tkinter \
  --exclude-module matplotlib \
  --exclude-module scipy \
  --exclude-module numpy 