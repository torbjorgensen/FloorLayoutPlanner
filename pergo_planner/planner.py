from __future__ import annotations

import math
from dataclasses import asdict, dataclass

from shapely.geometry import GeometryCollection, MultiPolygon, Polygon, box

from .geometry import swap_xy_polygon


@dataclass(frozen=True)
class Piece:
    row: int
    segment: int
    piece: int
    x1: float
    x2: float
    y1: float
    y2: float
    length: float
    width: float
    source_board_index: int
    physical_board_id: str
    is_full_length: bool

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class RowFragment:
    """
    Ett faktisk gulvfragment innenfor én bordrad.

    Et L-formet rom kan gi flere fragmenter i samme rad. Fragmentets høyde
    kan være mindre enn bordbredden når en vegg eller et innhakk starter midt
    inne i raden.
    """

    row: int
    segment: int
    min_x: float
    max_x: float
    min_y: float
    max_y: float

    @property
    def width(self) -> float:
        return self.max_y - self.min_y

    @property
    def length(self) -> float:
        return self.max_x - self.min_x


def rotate_polygon_for_orientation(
    polygon: Polygon,
    orientation: str,
) -> tuple[Polygon, bool]:
    if orientation == "horizontal":
        return polygon, False

    if orientation == "vertical":
        return swap_xy_polygon(polygon), True

    raise ValueError("orientation må være 'horizontal' eller 'vertical'.")


def unrotate_piece(piece: Piece, swapped: bool) -> Piece:
    if not swapped:
        return piece

    return Piece(
        row=piece.row,
        segment=piece.segment,
        piece=piece.piece,
        x1=piece.y1,
        x2=piece.y2,
        y1=piece.x1,
        y2=piece.x2,
        length=piece.length,
        width=piece.width,
        source_board_index=piece.source_board_index,
        physical_board_id=piece.physical_board_id,
        is_full_length=piece.is_full_length,
    )


def unrotate_fragment(fragment: RowFragment, swapped: bool) -> RowFragment:
    if not swapped:
        return fragment

    return RowFragment(
        row=fragment.row,
        segment=fragment.segment,
        min_x=fragment.min_y,
        max_x=fragment.max_y,
        min_y=fragment.min_x,
        max_y=fragment.max_x,
    )


def row_offset(
    row_index: int,
    board_length: float,
    stagger_step: float,
    base_offset: float,
) -> float:
    return (base_offset + row_index * stagger_step) % board_length


def polygon_parts(geometry) -> list[Polygon]:
    """Trekk ut alle polygoner fra Polygon/MultiPolygon/GeometryCollection."""
    if geometry.is_empty:
        return []

    if isinstance(geometry, Polygon):
        return [geometry]

    if isinstance(geometry, MultiPolygon):
        return list(geometry.geoms)

    if isinstance(geometry, GeometryCollection):
        result: list[Polygon] = []
        for item in geometry.geoms:
            result.extend(polygon_parts(item))
        return result

    return []


def horizontal_intervals_at_y(
    polygon: Polygon,
    y: float,
) -> list[tuple[float, float]]:
    """
    Finn alle X-intervaller inne i polygonet ved en bestemt Y-verdi.

    Vi bruker små probe-bokser i stedet for en ren linje for å unngå ustabile
    resultater når proben treffer nøyaktig på en polygonkant.
    """
    min_x, _, max_x, _ = polygon.bounds
    epsilon = 1e-5
    probe = box(
        min_x - 1.0,
        y - epsilon,
        max_x + 1.0,
        y + epsilon,
    )

    intersection = polygon.intersection(probe)
    intervals: list[tuple[float, float]] = []

    for part in polygon_parts(intersection):
        part_min_x, _, part_max_x, _ = part.bounds
        if part_max_x - part_min_x > 1e-6:
            intervals.append((part_min_x, part_max_x))

    return sorted(intervals)


def unique_breakpoints(
    polygon: Polygon,
    lower_y: float,
    upper_y: float,
) -> list[float]:
    """
    Finn alle Y-koordinater der vegggeometrien endrer seg innenfor radstripen.

    Dermed blir én nominell bordrad delt opp dersom en vegg/arm starter eller
    slutter midt i bordbredden.
    """
    values = {lower_y, upper_y}

    rings = [polygon.exterior, *polygon.interiors]
    for ring in rings:
        for _, y in ring.coords:
            if lower_y + 1e-6 < y < upper_y - 1e-6:
                values.add(float(y))

    return sorted(values)


def build_row_fragments(
    work_floor: Polygon,
    board_width: float,
    row_width_offset: float,
) -> list[RowFragment]:
    """
    Bygg faktiske radfragmenter fra hele radstriper.

    I motsetning til den gamle midtlinje-metoden tar dette hensyn til alle
    parallelle vegger og innhakk i et L-formet rom.
    """
    min_x, min_y, max_x, max_y = work_floor.bounds
    normalized_offset = float(row_width_offset) % board_width
    grid_y = min_y - normalized_offset
    row_number = 0
    fragments: list[RowFragment] = []

    while grid_y < max_y - 1e-6:
        nominal_top = grid_y
        nominal_bottom = grid_y + board_width

        visible_top = max(nominal_top, min_y)
        visible_bottom = min(nominal_bottom, max_y)

        if visible_bottom > visible_top + 1e-6:
            row_number += 1

            # Del raden ved alle vegghøyder som finnes inne i stripen.
            y_breaks = unique_breakpoints(
                work_floor,
                visible_top,
                visible_bottom,
            )

            segment_number = 0
            for y1, y2 in zip(y_breaks, y_breaks[1:]):
                if y2 <= y1 + 1e-6:
                    continue

                probe_y = (y1 + y2) / 2
                intervals = horizontal_intervals_at_y(
                    work_floor,
                    probe_y,
                )

                for x1, x2 in intervals:
                    if x2 <= x1 + 1e-6:
                        continue

                    segment_number += 1
                    fragments.append(
                        RowFragment(
                            row=row_number,
                            segment=segment_number,
                            min_x=x1,
                            max_x=x2,
                            min_y=y1,
                            max_y=y2,
                        )
                    )

        grid_y += board_width

    return fragments


def split_interval_by_board_grid(
    fragment: RowFragment,
    offset: float,
    board_length: float,
) -> list[Piece]:
    epsilon = 1e-6
    x_start = fragment.min_x
    x_end = fragment.max_x

    first_index = math.floor((x_start - offset) / board_length)
    last_index = math.ceil((x_end - offset) / board_length)

    cuts = [x_start]

    for index in range(first_index, last_index + 1):
        boundary = offset + index * board_length
        if x_start + epsilon < boundary < x_end - epsilon:
            cuts.append(boundary)

    cuts.append(x_end)
    cuts = sorted(set(round(value, 6) for value in cuts))

    pieces: list[Piece] = []

    for piece_index, (start, end) in enumerate(
        zip(cuts, cuts[1:]),
        start=1,
    ):
        if end - start <= epsilon:
            continue

        source_index = math.floor((((start + end) / 2) - offset) / board_length)
        physical_board_id = f"r{fragment.row}:s{fragment.segment}:g{source_index}"
        length = end - start

        pieces.append(
            Piece(
                row=fragment.row,
                segment=fragment.segment,
                piece=piece_index,
                x1=start,
                x2=end,
                y1=fragment.min_y,
                y2=fragment.max_y,
                length=length,
                width=fragment.width,
                source_board_index=source_index,
                physical_board_id=physical_board_id,
                is_full_length=abs(length - board_length) < 0.5,
            )
        )

    return pieces


def create_plan(
    floor: Polygon,
    board_length: float,
    board_width: float,
    orientation: str,
    stagger_step: float,
    minimum_piece_length: float,
    base_offset: float = 0.0,
    row_offsets: dict[int, float] | None = None,
    row_width_offset: float = 0.0,
) -> list[Piece]:
    work_floor, swapped = rotate_polygon_for_orientation(
        floor,
        orientation,
    )
    min_x, _, _, _ = work_floor.bounds

    fragments = build_row_fragments(
        work_floor=work_floor,
        board_width=board_width,
        row_width_offset=row_width_offset,
    )

    pieces: list[Piece] = []

    for fragment in fragments:
        row_index = fragment.row - 1

        if row_offsets and fragment.row in row_offsets:
            offset = min_x + (float(row_offsets[fragment.row]) % board_length)
        else:
            offset = min_x + row_offset(
                row_index=row_index,
                board_length=board_length,
                stagger_step=stagger_step,
                base_offset=base_offset,
            )

        row_pieces = split_interval_by_board_grid(
            fragment=fragment,
            offset=offset,
            board_length=board_length,
        )

        pieces.extend(unrotate_piece(piece, swapped) for piece in row_pieces)

    return pieces


def create_row_fragments(
    floor: Polygon,
    board_width: float,
    orientation: str,
    row_width_offset: float,
) -> list[RowFragment]:
    """
    Offentlig hjelpefunksjon til optimizeren.

    Returnerer alle faktiske lokale radfragmenter, slik at radbredde-score
    vurderer hver vegg og hvert innhakk, ikke bare første/siste yttervegg.
    """
    work_floor, swapped = rotate_polygon_for_orientation(
        floor,
        orientation,
    )

    fragments = build_row_fragments(
        work_floor=work_floor,
        board_width=board_width,
        row_width_offset=row_width_offset,
    )

    return [unrotate_fragment(fragment, swapped) for fragment in fragments]
