@echo off
cd /d "%~dp0"
.\.venv\Scripts\python.exe -m PyInstaller ^
  --onefile --windowed --clean --noconfirm ^
  --name QuickTranslate ^
  --paths src ^
  --hidden-import pynput.keyboard._win32 ^
  --hidden-import pynput.mouse._win32 ^
  --collect-data certifi ^
  --exclude-module PySide6.QtWebEngineCore ^
  --exclude-module PySide6.QtWebEngineWidgets ^
  --exclude-module PySide6.QtWebEngineQuick ^
  --exclude-module PySide6.QtPdf ^
  --exclude-module PySide6.QtPdfWidgets ^
  --exclude-module PySide6.Qt3DCore ^
  --exclude-module PySide6.Qt3DRender ^
  --exclude-module PySide6.QtMultimedia ^
  --exclude-module PySide6.QtMultimediaWidgets ^
  --exclude-module PySide6.QtCharts ^
  --exclude-module PySide6.QtQml ^
  --exclude-module PySide6.QtQuick ^
  --exclude-module PySide6.QtQuickWidgets ^
  --exclude-module PySide6.QtDesigner ^
  --exclude-module PySide6.QtSql ^
  --exclude-module PySide6.QtTest ^
  launcher.py
echo.
echo Build xong! File nam tai: dist\QuickTranslate.exe
pause
