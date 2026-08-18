"""Entry point for the standalone PyInstaller binary.

PyInstaller needs a real script to analyse, not a console-script entry point,
so this is the two lines that stand in for `offerprinter = offerprinter.cli:app`.
"""

from offerprinter.cli import app

if __name__ == "__main__":
    app()
