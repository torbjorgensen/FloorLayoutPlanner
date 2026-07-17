from __future__ import annotations

from pergo_planner.material import material_metrics, material_score
from pergo_planner.planner import Piece


def piece(board_id: str, row: int, length: float) -> Piece:
    return Piece(
        row=row,
        segment=1,
        piece=1,
        x1=0,
        x2=length,
        y1=(row - 1) * 240,
        y2=row * 240,
        length=length,
        width=240,
        source_board_index=int(board_id[1:]),
        physical_board_id=board_id,
        is_full_length=length == 2050,
    )


def test_exact_offcut_reuse_uses_one_cut_without_discard() -> None:
    metrics = material_metrics(
        [piece("B00001", 1, 1500), piece("B00001", 2, 546.8)],
        board_length=2050,
        saw_kerf_mm=3.2,
    )

    assert metrics["new_boards"] == 1
    assert metrics["exact_offcut_reuses"] == 1
    assert metrics["trimmed_offcut_reuses"] == 0
    assert metrics["cuts"] == 1
    assert metrics["discarded_mm"] == 0


def test_trimmed_offcut_reuse_accounts_for_second_cut_and_remainder() -> None:
    metrics = material_metrics(
        [piece("B00001", 1, 1000), piece("B00001", 2, 800)],
        board_length=2050,
        saw_kerf_mm=3.2,
    )

    assert metrics["new_boards"] == 1
    assert metrics["exact_offcut_reuses"] == 0
    assert metrics["trimmed_offcut_reuses"] == 1
    assert metrics["cuts"] == 2
    assert metrics["kerf_waste_mm"] == 6.4
    assert metrics["discarded_mm"] == 243.6


def test_opening_another_board_is_counted_separately() -> None:
    metrics = material_metrics(
        [piece("B00001", 1, 1000), piece("B00002", 2, 800)],
        board_length=2050,
        saw_kerf_mm=3.2,
    )

    assert metrics["new_boards"] == 2
    assert metrics["trimmed_offcut_reuses"] == 0
    assert metrics["cuts"] == 2


def test_material_score_prefers_exact_then_trimmed_reuse_before_new_board() -> None:
    exact = material_metrics(
        [piece("B00001", 1, 1500), piece("B00001", 2, 546.8)],
        board_length=2050,
        saw_kerf_mm=3.2,
    )
    trimmed = material_metrics(
        [piece("B00001", 1, 1000), piece("B00001", 2, 800)],
        board_length=2050,
        saw_kerf_mm=3.2,
    )
    new_board = material_metrics(
        [piece("B00001", 1, 1000), piece("B00002", 2, 800)],
        board_length=2050,
        saw_kerf_mm=3.2,
    )

    assert material_score(exact) < material_score(trimmed) < material_score(new_board)
