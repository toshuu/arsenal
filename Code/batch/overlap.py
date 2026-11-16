"""Overlap a GPU decode with the next GPU step on a second CUDA stream."""

from __future__ import annotations

import torch


class OverlapDecoder:
    """Run one decode closure on a second stream, then wait on demand."""

    def __init__(self, device: torch.device | str) -> None:
        self.stream = torch.cuda.Stream(device=device)
        self.done = torch.cuda.Event()

    def launch(self, fn) -> None:
        current = torch.cuda.current_stream()
        with torch.cuda.stream(self.stream):
            self.stream.wait_stream(current)
            fn()
            self.done.record(self.stream)

    def wait(self) -> None:
        torch.cuda.current_stream().wait_event(self.done)
        self.done.synchronize()
