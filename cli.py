#!/usr/bin/env python3
"""Convenience entry point: `python cli.py …`.

The real CLI lives in `offerprinter/cli.py` so that it ships inside the
installed package and `offerprinter` works as a console script after
`pip install offerprinter`. This shim keeps the documented
`python cli.py --cv … --jd …` invocation working from a git clone.
"""

from offerprinter.cli import app

if __name__ == "__main__":
    app()
