"""Entrypoint cho PyInstaller để đóng gói QuickTranslate.exe độc lập."""

from quick_translate.main import main

if __name__ == "__main__":
    raise SystemExit(main())
