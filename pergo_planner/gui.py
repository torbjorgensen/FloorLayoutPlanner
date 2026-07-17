from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from shapely.geometry import Polygon

from .optimizer import Candidate


class LiveOptimizerWindow:
    def __init__(
        self,
        title: str,
        floor: Polygon,
        rectangles: list[dict],
        minimum_piece_length: float,
        candidates,
        on_finished: Callable[[Candidate], None],
        frame_delay_ms: int = 40,
    ) -> None:
        self.floor = floor
        self.rectangles = rectangles
        self.minimum_piece_length = minimum_piece_length
        self.candidates = iter(candidates)
        self.on_finished = on_finished
        self.frame_delay_ms = max(1, frame_delay_ms)

        self.current: Candidate | None = None
        self.best: Candidate | None = None
        self.running = True
        self.finished = False

        self.root = tk.Tk()
        self.root.title(title)
        self.root.geometry("1200x800")
        self.root.minsize(850, 600)

        self._build_ui()
        self.root.after(100, self._next_candidate)

    def _build_ui(self) -> None:
        toolbar = ttk.Frame(self.root, padding=8)
        toolbar.pack(side=tk.TOP, fill=tk.X)

        self.status_var = tk.StringVar(value="Starting optimization …")
        ttk.Label(toolbar, textvariable=self.status_var).pack(side=tk.LEFT)

        self.pause_button = ttk.Button(
            toolbar,
            text="Pause",
            command=self._toggle_pause,
        )
        self.pause_button.pack(side=tk.RIGHT, padx=(6, 0))

        ttk.Button(
            toolbar,
            text="Stop and use best",
            command=self._stop,
        ).pack(side=tk.RIGHT)

        self.progress = ttk.Progressbar(
            self.root,
            mode="determinate",
        )
        self.progress.pack(side=tk.TOP, fill=tk.X, padx=8)

        content = ttk.Frame(self.root)
        content.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(
            content,
            background="white",
            highlightthickness=0,
        )
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        info = ttk.Frame(content, padding=12, width=260)
        info.pack(side=tk.RIGHT, fill=tk.Y)
        info.pack_propagate(False)

        ttk.Label(info, text="Current solution", font=("", 12, "bold")).pack(anchor="w")
        self.current_var = tk.StringVar(value="–")
        ttk.Label(info, textvariable=self.current_var, justify=tk.LEFT).pack(
            anchor="w", pady=(4, 18)
        )

        ttk.Label(info, text="Best so far", font=("", 12, "bold")).pack(anchor="w")
        self.best_var = tk.StringVar(value="–")
        ttk.Label(info, textvariable=self.best_var, justify=tk.LEFT).pack(
            anchor="w", pady=(4, 18)
        )

        ttk.Label(
            info,
            text=(
                "Red: piece below minimum length\n"
                "Green: valid piece\n\n"
                "The window tests global start offsets."
            ),
            justify=tk.LEFT,
        ).pack(anchor="w")

        self.canvas.bind("<Configure>", lambda _event: self._redraw())

    def _toggle_pause(self) -> None:
        if self.finished:
            return
        self.running = not self.running
        self.pause_button.configure(text="Pause" if self.running else "Resume")
        if self.running:
            self.root.after(1, self._next_candidate)

    def _stop(self) -> None:
        if self.finished:
            self.root.destroy()
            return

        self.finished = True
        self.running = False
        if self.best is not None:
            self.on_finished(self.best)
        self.status_var.set("Stopped - best solution has been saved.")
        self.pause_button.configure(text="Close", command=self.root.destroy)

    def _next_candidate(self) -> None:
        if self.finished or not self.running:
            return

        try:
            candidate = next(self.candidates)
        except StopIteration:
            self.finished = True
            self.running = False
            if self.best is not None:
                self.on_finished(self.best)
                self.status_var.set(
                    f"Finished - best start offset: {self.best.base_offset:.0f} mm"
                )
            else:
                self.status_var.set("Finished - no solution found.")
            self.pause_button.configure(text="Close", command=self.root.destroy)
            return

        self.current = candidate

        if self.best is None or candidate.score < self.best.score:
            self.best = candidate

        self.progress.configure(maximum=candidate.total_attempts)
        self.progress["value"] = candidate.attempt

        self.status_var.set(
            f"Attempt {candidate.attempt} of {candidate.total_attempts} "
            f"- start offset {candidate.base_offset:.0f} mm"
        )

        self.current_var.set(self._candidate_text(candidate))
        self.best_var.set(self._candidate_text(self.best))
        self._redraw()

        self.root.after(self.frame_delay_ms, self._next_candidate)

    @staticmethod
    def _candidate_text(candidate: Candidate | None) -> str:
        if candidate is None:
            return "–"
        return (
            f"Offset: {candidate.base_offset:.0f} mm\n"
            f"Short pieces: {candidate.short_count}\n"
            f"Under 100 mm: {candidate.very_short_count}\n"
            f"Shortest piece: {candidate.shortest_piece:.0f} mm"
        )

    def _redraw(self) -> None:
        self.canvas.delete("all")
        candidate = self.current or self.best
        if candidate is None:
            return

        minx, miny, maxx, maxy = self.floor.bounds
        width = max(maxx - minx, 1)
        height = max(maxy - miny, 1)

        canvas_width = max(self.canvas.winfo_width(), 100)
        canvas_height = max(self.canvas.winfo_height(), 100)
        margin = 30

        scale = min(
            (canvas_width - 2 * margin) / width,
            (canvas_height - 2 * margin) / height,
        )

        def sx(value: float) -> float:
            return margin + (value - minx) * scale

        def sy(value: float) -> float:
            # Y øker nedover i både konfigurasjonen og Tkinter.
            return margin + (value - miny) * scale

        # Rektangelbakgrunner
        for rectangle in self.rectangles:
            fill = rectangle.get("fill_color", "#e6e6e6")
            self.canvas.create_rectangle(
                sx(float(rectangle["x"])),
                sy(float(rectangle["y"])),
                sx(float(rectangle["x"]) + float(rectangle["width"])),
                sy(float(rectangle["y"]) + float(rectangle["height"])),
                fill=fill,
                outline="",
            )

        # Bordbiter
        for piece in candidate.pieces:
            is_short = piece.length < self.minimum_piece_length
            self.canvas.create_rectangle(
                sx(piece.x1),
                sy(piece.y1),
                sx(piece.x2),
                sy(piece.y2),
                fill="#ffd6d6" if is_short else "#dff2df",
                outline="#b00020" if is_short else "#4f6f4f",
                width=2 if is_short else 1,
            )

        # Samlet ytterkontur
        coords = []
        for x, y in self.floor.exterior.coords:
            coords.extend((sx(x), sy(y)))
        self.canvas.create_line(*coords, fill="black", width=3)

    def run(self) -> None:
        self.root.mainloop()
