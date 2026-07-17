from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle as MatplotlibRectangle
from shapely.geometry import Polygon, box
from shapely.ops import unary_union

from .planner import Piece


def _plot_piece_outline(
    axis,
    geometry,
    *,
    color: str,
    linewidth: float,
    zorder: int,
) -> None:
    if geometry.is_empty:
        return

    if isinstance(geometry, Polygon):
        polygons = [geometry]
    else:
        polygons = list(geometry.geoms)

    for polygon in polygons:
        x_values, y_values = polygon.exterior.xy
        axis.plot(
            x_values,
            y_values,
            color=color,
            linewidth=linewidth,
            zorder=zorder,
        )


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

        label = rectangle.get("name") or rectangle.get("id") or f"Rectangle {index}"

        axis.text(
            float(rectangle["x"]) + float(rectangle["width"]) / 2,
            float(rectangle["y"]) + float(rectangle["height"]) / 2,
            label,
            ha="center",
            va="center",
            fontsize=8,
            zorder=4,
        )

    pieces_by_board = defaultdict(list)

    for piece in pieces:
        pieces_by_board[
            (
                piece.physical_board_id,
                piece.row,
            )
        ].append(piece)

    for board_pieces in pieces_by_board.values():
        is_short = any(piece.length < minimum_piece_length for piece in board_pieces)
        geometry = unary_union(
            [
                box(
                    piece.x1,
                    piece.y1,
                    piece.x2,
                    piece.y2,
                )
                for piece in board_pieces
            ]
        )
        _plot_piece_outline(
            axis,
            geometry,
            color="red" if is_short else "black",
            linewidth=1.0 if is_short else 0.45,
            zorder=2,
        )

    x_values, y_values = floor.exterior.xy
    axis.plot(
        x_values,
        y_values,
        linewidth=2.5,
        zorder=5,
    )

    axis.set_aspect("equal", adjustable="box")
    axis.set_title(f"{section_name} - laminate plan ({orientation})")
    axis.set_xlabel("X (mm) →")
    axis.set_ylabel("Y (mm) ↓")
    axis.grid(True, linewidth=0.2)
    axis.invert_yaxis()
    axis.xaxis.tick_top()
    axis.xaxis.set_label_position("top")

    figure.tight_layout()
    figure.savefig(output_path, dpi=220)
    plt.close(figure)
