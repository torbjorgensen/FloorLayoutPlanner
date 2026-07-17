from __future__ import annotations

import csv
from pathlib import Path

from pergo_planner.models import Candidate


def write_piece_csv(path: Path, candidate: Candidate) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file, delimiter=";")
        writer.writerow(
            [
                "row",
                "segment",
                "piece",
                "x1_mm",
                "x2_mm",
                "y1_mm",
                "y2_mm",
                "length_mm",
                "width_mm",
                "global_board_index",
                "full_board_length",
            ]
        )
        for piece in candidate.pieces:
            writer.writerow(
                [
                    piece.row,
                    piece.segment,
                    piece.piece,
                    round(piece.x1, 1),
                    round(piece.x2, 1),
                    round(piece.y1, 1),
                    round(piece.y2, 1),
                    round(piece.length, 1),
                    round(piece.width, 1),
                    piece.source_board_index,
                    "yes" if piece.is_full_length else "no",
                ]
            )
