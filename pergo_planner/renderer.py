from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle as MatplotlibRectangle
from shapely.geometry import Polygon

from .planner import Piece


def plot_plan(
    output_path: Path,
    floor: Polygon,
    pieces: list[Piece],
    rectangles: list[dict],
    orientation: str,
    section_name: str,
    plot_settings: dict | None = None,
    minimum_piece_length: float = 300.0,
) -> None:
    plot_settings = plot_settings or {}
    rectangle_style = plot_settings.get(
        "rectangle_style",
        {},
    )

    figure, axis = plt.subplots(figsize=(13, 9))

    for index, rectangle in enumerate(
        rectangles,
        start=1,
    ):
        outline_color = rectangle.get(
            "outline_color",
            rectangle_style.get("outline_color", "#666666"),
        )
        outline_alpha = float(
            rectangle.get(
                "outline_alpha",
                rectangle_style.get("outline_alpha", 0.85),
            )
        )
        fill_color = rectangle.get(
            "fill_color",
            rectangle_style.get("fill_color", "#eeeeee"),
        )
        fill_alpha = float(
            rectangle.get(
                "fill_alpha",
                rectangle_style.get("fill_alpha", 0.08),
            )
        )

        axis.add_patch(
            MatplotlibRectangle(
                (
                    float(rectangle["x"]),
                    float(rectangle["y"]),
                ),
                float(rectangle["width"]),
                float(rectangle["height"]),
                facecolor=fill_color,
                edgecolor="none",
                alpha=fill_alpha,
                zorder=0,
            )
        )

        axis.add_patch(
            MatplotlibRectangle(
                (
                    float(rectangle["x"]),
                    float(rectangle["y"]),
                ),
                float(rectangle["width"]),
                float(rectangle["height"]),
                fill=False,
                edgecolor=outline_color,
                alpha=outline_alpha,
                linewidth=1.5,
                linestyle="--",
                zorder=3,
            )
        )

        label = rectangle.get("name") or rectangle.get("id") or f"Rektangel {index}"

        axis.text(
            float(rectangle["x"]) + float(rectangle["width"]) / 2,
            float(rectangle["y"]) + float(rectangle["height"]) / 2,
            label,
            ha="center",
            va="center",
            fontsize=8,
            zorder=4,
        )

    for piece in pieces:
        is_short = piece.length < minimum_piece_length

        axis.add_patch(
            MatplotlibRectangle(
                (piece.x1, piece.y1),
                piece.x2 - piece.x1,
                piece.y2 - piece.y1,
                fill=False,
                edgecolor="red" if is_short else "black",
                linewidth=1.0 if is_short else 0.45,
                zorder=2,
            )
        )

    x_values, y_values = floor.exterior.xy
    axis.plot(
        x_values,
        y_values,
        linewidth=2.5,
        zorder=5,
    )

    axis.set_aspect("equal", adjustable="box")
    axis.set_title(f"{section_name} – laminatplan ({orientation})")
    axis.set_xlabel("X (mm) →")
    axis.set_ylabel("Y (mm) ↓")
    axis.grid(True, linewidth=0.2)
    axis.invert_yaxis()
    axis.xaxis.tick_top()
    axis.xaxis.set_label_position("top")

    figure.tight_layout()
    figure.savefig(output_path, dpi=220)
    plt.close(figure)
