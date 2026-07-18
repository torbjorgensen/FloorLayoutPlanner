import type {InspectablePiece, PieceHit} from "../lib/canvasRenderer";
import {boardOrderLabel, formatNumber, starterCutTolerance} from "../lib/planning";
import type {Piece, RoomStatePayload} from "../types";

interface BoardInspectionProps {
    inspection: PieceHit;
    boardParts?: InspectablePiece[];
    layoutPieces?: Piece[];
    pinned?: boolean;
    room?: RoomStatePayload | null;
}

export function BoardInspection({
    inspection,
    boardParts = [inspection],
    layoutPieces = [],
    pinned = false,
    room = null,
}: BoardInspectionProps) {
    const {piece} = inspection;
    const installedParts = Array.from(
        boardParts.reduce((groups, part) => {
            const key = `${part.roomId}:${part.piece.row}`;
            const current = groups.get(key) || [];
            current.push(part);
            groups.set(key, current);
            return groups;
        }, new Map<string, InspectablePiece[]>()),
    ).map(([key, fragments]) => {
        const minX = Math.min(...fragments.map(part => part.piece.x1));
        const maxX = Math.max(...fragments.map(part => part.piece.x2));
        const minY = Math.min(...fragments.map(part => part.piece.y1));
        const maxY = Math.max(...fragments.map(part => part.piece.y2));
        return {key, fragments, length: maxX - minX, width: maxY - minY};
    });
    const selectedPart = installedParts.find(part =>
        part.fragments.some(fragment => fragment.key === inspection.key),
    );
    const tolerance = room
        ? starterCutTolerance(layoutPieces, room, piece)
        : null;
    const boardName = piece.physical_board_id
        || `Board ${piece.source_board_index ?? "–"}`;

    return (
        <aside
            id="boardInspection"
            className={`board-inspection${pinned ? " board-inspection-pinned" : ""}`}
            role="status"
            style={{left: inspection.anchor.x, top: inspection.anchor.y}}
        >
            <strong>{boardName}</strong>
            <span>{inspection.roomName}</span>
            {pinned && <span className="board-inspection-state">Pinned selection</span>}
            <dl>
                <div>
                    <dt>Placement</dt>
                    <dd>{boardOrderLabel(piece)}</dd>
                </div>
                <div>
                    <dt>Piece</dt>
                    <dd>{`Row ${piece.row}${selectedPart && selectedPart.fragments.length > 1 ? `, shaped across ${selectedPart.fragments.length} geometry sections` : `, segment ${piece.segment}, #${piece.piece}`}`}</dd>
                </div>
                <div>
                    <dt>Source</dt>
                    <dd>{piece.source_board_index ?? "–"}</dd>
                </div>
                <div>
                    <dt>Size</dt>
                    <dd>
                        {selectedPart
                            ? `${formatNumber(selectedPart.length, 0)} × ${formatNumber(selectedPart.width, 0)} mm envelope`
                            : `${formatNumber(piece.length, 0)} × ${formatNumber(piece.width, 0)} mm`}
                    </dd>
                </div>
                <div>
                    <dt>Type</dt>
                    <dd>{piece.is_full_length ? "Cut from a full-length board" : "Cut piece"}</dd>
                </div>
            </dl>
            {piece.length < inspection.minimumPieceLength && (
                <span className="board-inspection-warning">
                    Shorter than the configured minimum
                </span>
            )}
            {tolerance && <section className="board-inspection-tolerance">
                <strong>Safe starter-cut range</strong>
                <span>{`${formatNumber(tolerance.planned - tolerance.shorter)}–${formatNumber(tolerance.planned + tolerance.longer)} mm`}</span>
                <small>{`Planned ${formatNumber(tolerance.planned)} mm · −${formatNumber(tolerance.shorter)} / +${formatNumber(tolerance.longer)} mm${tolerance.capped ? " or more" : ""}`}</small>
            </section>}
            <section className="board-inspection-parts">
                <strong>{`Installed pieces from this board (${installedParts.length})`}</strong>
                <ol>
                    {installedParts.map(part => (
                        <li
                            className={part.fragments.some(fragment => fragment.key === inspection.key) ? "is-inspected" : ""}
                            key={part.key}
                        >
                            <span>{part.fragments[0].roomName}</span>
                            <span>{`Row ${part.fragments[0].piece.row}`}</span>
                            <span>
                                {`${formatNumber(part.length, 0)} × ${formatNumber(part.width, 0)} mm${part.fragments.length > 1 ? ` (${part.fragments.length} geometry sections)` : ""}`}
                            </span>
                        </li>
                    ))}
                </ol>
            </section>
        </aside>
    );
}
