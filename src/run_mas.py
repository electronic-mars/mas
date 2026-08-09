"""Entry point for PyInstaller: the package is imported by name, not relatively."""
import sys

from mas.app import main

if __name__ == "__main__":
    sys.exit(main())
