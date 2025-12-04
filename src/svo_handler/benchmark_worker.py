"""
Worker thread for running benchmarks.
"""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from .benchmark_config import BenchmarkConfig


class BenchmarkWorker(QThread):
    """Background worker for running model benchmarks."""

    progress_updated = Signal(int, str)  # progress, status message
    benchmark_complete = Signal(dict)  # results dictionary
    benchmark_failed = Signal(str)  # error message

    def __init__(self, config: BenchmarkConfig) -> None:
        super().__init__()
        self._config = config
        self._cancelled = False

    def cancel(self) -> None:
        """Cancel the running benchmark."""
        self._cancelled = True

    def run(self) -> None:
        """Run the benchmark (executed in background thread)."""
        # TODO: Implement benchmark execution
        pass
