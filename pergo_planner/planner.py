from __future__ import annotations

from dataclasses import asdict, dataclass
from itertools import count

from shapely.geometry import GeometryCollection, MultiPolygon, Polygon, box

from .geometry import swap_xy_polygon

_EPSILON = 1e-6
_DEFAULT_SAW_KERF_MM = 3.2


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
    Ett faktisk gulvfragment innenfor én nominell bordrad.

    Flere fragmenter kan tilhøre samme fysiske bord dersom vegggeometrien
    endrer seg midt inne i bordbredden. Dette gjør at et bord kan vises som
    flere rektangler uten å bli behandlet som flere fysiske bord.
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


@dataclass(frozen=True)
class BoardPlacement:
    """Ett fysisk bord eller én del av et fysisk bord langs leggeretningen."""

    x1: float
    x2: float
    physical_board_id: str
    source_board_index: int
    is_full_length: bool

    @property
    def length(self) -> float:
        return self.x2 - self.x1


@dataclass(frozen=True)
class Offcut:
    """Resten etter ett tverrkapp, klar som startbit på neste rad."""

    length: float
    physical_board_id: str
    source_board_index: int
    lane_start: float


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


def unrotate_fragment(
    fragment: RowFragment,
    swapped: bool,
) -> RowFragment:
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
    min_x, _, max_x, _ = polygon.bounds
    probe = box(
        min_x - 1.0,
        y - 1e-5,
        max_x + 1.0,
        y + 1e-5,
    )
    intersection = polygon.intersection(probe)
    intervals: list[tuple[float, float]] = []

    for part in polygon_parts(intersection):
        part_min_x, _, part_max_x, _ = part.bounds

        if part_max_x - part_min_x > _EPSILON:
            intervals.append((part_min_x, part_max_x))

    return sorted(intervals)


def unique_breakpoints(
    polygon: Polygon,
    lower_y: float,
    upper_y: float,
) -> list[float]:
    values = {lower_y, upper_y}
    rings = [
        polygon.exterior,
        *polygon.interiors,
    ]

    for ring in rings:
        for _, y in ring.coords:
            if lower_y + _EPSILON < y < upper_y - _EPSILON:
                values.add(float(y))

    return sorted(values)


def build_row_fragments(
    work_floor: Polygon,
    board_width: float,
    row_width_offset: float,
) -> list[RowFragment]:
    min_x, min_y, _, max_y = work_floor.bounds
    normalized_offset = float(row_width_offset) % board_width
    grid_y = min_y - normalized_offset
    row_number = 0
    fragments: list[RowFragment] = []

    while grid_y < max_y - _EPSILON:
        visible_top = max(grid_y, min_y)
        visible_bottom = min(
            grid_y + board_width,
            max_y,
        )

        if visible_bottom > visible_top + _EPSILON:
            row_number += 1
            breakpoints = unique_breakpoints(
                work_floor,
                visible_top,
                visible_bottom,
            )
            segment_number = 0

            for y1, y2 in zip(
                breakpoints,
                breakpoints[1:],
            ):
                if y2 <= y1 + _EPSILON:
                    continue

                intervals = horizontal_intervals_at_y(
                    work_floor,
                    (y1 + y2) / 2,
                )

                for x1, x2 in intervals:
                    if x2 <= x1 + _EPSILON:
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


def _merged_lane_spans(
    fragments: list[RowFragment],
) -> list[tuple[float, float]]:
    """
    Finn sammenhengende gulvspenn langs leggeretningen for én rad.

    Fragmenter som bare er delt fordi en vegg starter midt i bordbredden,
    men som overlapper langs X, beholdes i samme lane. Et faktisk hull gjennom
    hele radbredden lager derimot en ny lane, og bord kan ikke gå gjennom det.
    """
    intervals = sorted(
        (
            fragment.min_x,
            fragment.max_x,
        )
        for fragment in fragments
    )

    if not intervals:
        return []

    merged = [list(intervals[0])]

    for start, end in intervals[1:]:
        current = merged[-1]

        if start <= current[1] + _EPSILON:
            current[1] = max(
                current[1],
                end,
            )
        else:
            merged.append([start, end])

    return [(float(start), float(end)) for start, end in merged]


def _starter_length_from_offset(
    offset: float,
    board_length: float,
) -> float:
    normalized = float(offset) % board_length

    if normalized <= _EPSILON:
        return board_length

    return normalized


def _place_lane_boards(
    *,
    lane_start: float,
    lane_end: float,
    starter_length: float,
    starter_offcut: Offcut | None,
    board_length: float,
    minimum_piece_length: float,
    saw_kerf_mm: float,
    board_numbers,
) -> tuple[list[BoardPlacement], Offcut | None]:
    remaining = lane_end - lane_start

    if remaining <= _EPSILON:
        return [], None

    placements: list[BoardPlacement] = []
    cursor = lane_start

    def new_board_id() -> tuple[str, int]:
        number = next(board_numbers)
        return f"B{number:05d}", number

    if (
        starter_offcut is not None
        and starter_offcut.length >= minimum_piece_length
        and abs(starter_offcut.lane_start - lane_start) <= 1.0
    ):
        usable = min(
            starter_offcut.length,
            remaining,
        )
        placements.append(
            BoardPlacement(
                x1=cursor,
                x2=cursor + usable,
                physical_board_id=(starter_offcut.physical_board_id),
                source_board_index=(starter_offcut.source_board_index),
                is_full_length=False,
            )
        )
        cursor += usable
        remaining -= usable
    else:
        first_length = min(
            starter_length,
            remaining,
        )
        board_id, board_number = new_board_id()
        placements.append(
            BoardPlacement(
                x1=cursor,
                x2=cursor + first_length,
                physical_board_id=board_id,
                source_board_index=board_number,
                is_full_length=(abs(first_length - board_length) < 0.5),
            )
        )
        cursor += first_length
        remaining -= first_length

    while remaining > _EPSILON:
        used_length = min(
            board_length,
            remaining,
        )
        board_id, board_number = new_board_id()
        placements.append(
            BoardPlacement(
                x1=cursor,
                x2=cursor + used_length,
                physical_board_id=board_id,
                source_board_index=board_number,
                is_full_length=(abs(used_length - board_length) < 0.5),
            )
        )
        cursor += used_length
        remaining -= used_length

    final = placements[-1]

    if final.is_full_length:
        return placements, None

    offcut_length = board_length - final.length - saw_kerf_mm

    if offcut_length < minimum_piece_length:
        return placements, None

    return (
        placements,
        Offcut(
            length=offcut_length,
            physical_board_id=(final.physical_board_id),
            source_board_index=(final.source_board_index),
            lane_start=lane_start,
        ),
    )


def _pieces_from_placements(
    *,
    row_fragments: list[RowFragment],
    placements: list[BoardPlacement],
) -> list[Piece]:
    pieces: list[Piece] = []
    piece_numbers: dict[int, int] = {}

    for placement in placements:
        for fragment in row_fragments:
            start = max(
                placement.x1,
                fragment.min_x,
            )
            end = min(
                placement.x2,
                fragment.max_x,
            )

            if end <= start + _EPSILON:
                continue

            number = (
                piece_numbers.get(
                    fragment.segment,
                    0,
                )
                + 1
            )
            piece_numbers[fragment.segment] = number

            pieces.append(
                Piece(
                    row=fragment.row,
                    segment=fragment.segment,
                    piece=number,
                    x1=start,
                    x2=end,
                    y1=fragment.min_y,
                    y2=fragment.max_y,
                    length=end - start,
                    width=fragment.width,
                    source_board_index=(placement.source_board_index),
                    physical_board_id=(placement.physical_board_id),
                    is_full_length=(placement.is_full_length),
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
    saw_kerf_mm: float = (_DEFAULT_SAW_KERF_MM),
) -> list[Piece]:
    """
    Lag gulvet i faktisk leggerrekkefølge.

    Første rad starter med valgt base-offset. Deretter brukes kappet fra
    slutten av en lane som startbit på neste rad i samme lane når det er langt
    nok. Et hull gjennom hele radbredden bryter lane-sekvensen, slik at bord
    aldri føres gjennom en vegg.

    ``stagger_step`` og ``row_offsets`` brukes som fallback-starter når et
    gyldig kapp ikke finnes. Dermed kan optimizeren fortsatt utforske ulike
    startmønstre uten at fysiske bord-ID-er tildeles i etterkant.
    """
    if board_length <= 0:
        raise ValueError("board_length må være større enn 0.")

    if board_width <= 0:
        raise ValueError("board_width må være større enn 0.")

    if saw_kerf_mm < 0:
        raise ValueError("saw_kerf_mm kan ikke være negativ.")

    work_floor, swapped = rotate_polygon_for_orientation(
        floor,
        orientation,
    )
    fragments = build_row_fragments(
        work_floor=work_floor,
        board_width=board_width,
        row_width_offset=(row_width_offset),
    )
    fragments_by_row: dict[
        int,
        list[RowFragment],
    ] = {}

    for fragment in fragments:
        fragments_by_row.setdefault(
            fragment.row,
            [],
        ).append(fragment)

    board_numbers = count(1)
    active_offcuts: dict[
        float,
        Offcut,
    ] = {}
    pieces: list[Piece] = []

    for row_number in sorted(fragments_by_row):
        row_fragments = fragments_by_row[row_number]
        lane_spans = _merged_lane_spans(row_fragments)
        next_offcuts: dict[
            float,
            Offcut,
        ] = {}

        for lane_start, lane_end in lane_spans:
            matching_fragments = [
                fragment
                for fragment in row_fragments
                if (
                    fragment.max_x > lane_start + _EPSILON
                    and fragment.min_x < lane_end - _EPSILON
                )
            ]
            lane_key = round(
                lane_start,
                3,
            )
            forced_offset = (
                row_offsets.get(row_number)
                if row_offsets and row_number in row_offsets
                else None
            )

            if forced_offset is not None:
                starter_offcut = None
                starter_length = _starter_length_from_offset(
                    forced_offset,
                    board_length,
                )
            else:
                starter_offcut = active_offcuts.get(lane_key)

                if row_number == 1 and starter_offcut is None:
                    fallback_offset = base_offset
                else:
                    fallback_offset = row_offset(
                        row_index=(row_number - 1),
                        board_length=(board_length),
                        stagger_step=(stagger_step),
                        base_offset=(base_offset),
                    )

                starter_length = _starter_length_from_offset(
                    fallback_offset,
                    board_length,
                )

            placements, offcut = _place_lane_boards(
                lane_start=lane_start,
                lane_end=lane_end,
                starter_length=(starter_length),
                starter_offcut=(starter_offcut),
                board_length=(board_length),
                minimum_piece_length=(minimum_piece_length),
                saw_kerf_mm=(saw_kerf_mm),
                board_numbers=(board_numbers),
            )

            pieces.extend(
                _pieces_from_placements(
                    row_fragments=(matching_fragments),
                    placements=placements,
                )
            )

            if offcut is not None:
                next_offcuts[lane_key] = offcut

        active_offcuts = next_offcuts

    return [
        unrotate_piece(
            piece,
            swapped,
        )
        for piece in pieces
    ]


def split_interval_by_board_grid(
    fragment: RowFragment,
    offset: float,
    board_length: float,
) -> list[Piece]:
    """
    Beholdt for bakoverkompatibilitet i tester og hjelpeverktøy.

    Denne funksjonen simulerer én isolert lane uten kappgjenbruk mellom rader.
    Hovedmotoren bruker ``create_plan()``.
    """
    starter_length = _starter_length_from_offset(
        offset - fragment.min_x,
        board_length,
    )
    placements, _ = _place_lane_boards(
        lane_start=fragment.min_x,
        lane_end=fragment.max_x,
        starter_length=starter_length,
        starter_offcut=None,
        board_length=board_length,
        minimum_piece_length=0,
        saw_kerf_mm=0,
        board_numbers=count(1),
    )

    return _pieces_from_placements(
        row_fragments=[fragment],
        placements=placements,
    )


def create_row_fragments(
    floor: Polygon,
    board_width: float,
    orientation: str,
    row_width_offset: float,
) -> list[RowFragment]:
    work_floor, swapped = rotate_polygon_for_orientation(
        floor,
        orientation,
    )
    fragments = build_row_fragments(
        work_floor=work_floor,
        board_width=board_width,
        row_width_offset=(row_width_offset),
    )

    return [
        unrotate_fragment(
            fragment,
            swapped,
        )
        for fragment in fragments
    ]
