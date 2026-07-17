from __future__ import annotations

from collections import defaultdict

from floor_layout_planner.planner import Piece

_LENGTH_TOLERANCE_MM = 1.0


def material_score(metrics: dict[str, float | int]) -> tuple[int | float, ...]:
    """Rank board use after all layout-safety and geometry criteria.

    Fewer new boards wins first. With equal board use, exact reuse beats a
    second trimming cut, followed by total cuts and discarded material.
    """
    return (
        int(metrics["new_boards"]),
        int(metrics["trimmed_offcut_reuses"]),
        int(metrics["cuts"]),
        float(metrics["discarded_mm"]),
    )


def material_metrics(
    pieces: list[Piece],
    board_length: float,
    saw_kerf_mm: float,
) -> dict[str, float | int]:
    """Return material-use metrics for a finished candidate.

    A physical placement may be rendered as several geometry fragments in one
    row. Taking the longest fragment per board and row prevents those visual
    fragments from being mistaken for additional cuts or boards.
    """
    placements: dict[str, dict[int, float]] = defaultdict(dict)
    for piece in pieces:
        row_lengths = placements[piece.physical_board_id]
        row_lengths[piece.row] = max(row_lengths.get(piece.row, 0.0), piece.length)

    exact_reuses = 0
    trimmed_reuses = 0
    cuts = 0
    discarded = 0.0

    for row_lengths in placements.values():
        lengths = list(row_lengths.values())
        installed = sum(lengths)
        if len(lengths) > 1:
            # One kerf and a nominal-length sum indicate complementary pieces
            # from the first cut. A smaller sum means the offcut was trimmed by
            # another cut before reuse.
            if abs(installed + saw_kerf_mm - board_length) <= _LENGTH_TOLERANCE_MM:
                exact_reuses += 1
                board_cuts = 1
            else:
                trimmed_reuses += 1
                board_cuts = len(lengths)
        else:
            board_cuts = int(abs(installed - board_length) > _LENGTH_TOLERANCE_MM)

        cuts += board_cuts
        board_discarded = max(0.0, board_length - installed - board_cuts * saw_kerf_mm)
        if board_discarded <= _LENGTH_TOLERANCE_MM:
            board_discarded = 0.0
        discarded += board_discarded

    return {
        "new_boards": len(placements),
        "exact_offcut_reuses": exact_reuses,
        "trimmed_offcut_reuses": trimmed_reuses,
        "cuts": cuts,
        "kerf_waste_mm": cuts * saw_kerf_mm,
        "discarded_mm": discarded,
    }
