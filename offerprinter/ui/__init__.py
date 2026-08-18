"""Terminal presentation helpers.

Kept apart from the pipeline so that nothing in the core depends on how (or
whether) progress is drawn. The CLI is the only consumer.
"""

from offerprinter.ui.printer import PrinterAnimation, render_fit_bar

__all__ = ["PrinterAnimation", "render_fit_bar"]
