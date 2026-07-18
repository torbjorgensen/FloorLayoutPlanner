import type {InspectablePiece, PieceHit} from "../lib/canvasRenderer";
import {boardOrderLabel, formatNumber} from "../lib/planning";

interface BoardInspectionProps {
    inspection: PieceHit;
    boardParts?: InspectablePiece[];
    pinned?: boolean;
}

export function BoardInspection({
    inspection,
    boardParts = [inspection],
    pinned = false,
}: BoardInspectionProps) {
    const {piece} = inspection;
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
                    <dd>{`Row ${piece.row}, segment ${piece.segment}, #${piece.piece}`}</dd>
                </div>
                <div>
                    <dt>Source</dt>
                    <dd>{piece.source_board_index ?? "–"}</dd>
                </div>
                <div>
                    <dt>Size</dt>
                    <dd>
                        {`${formatNumber(piece.length, 0)} × ${formatNumber(piece.width, 0)} mm`}
                    </dd>
                </div>
                <div>
                    <dt>Type</dt>
                    <dd>{piece.is_full_length ? "Full-length board" : "Cut piece"}</dd>
                </div>
            </dl>
            {piece.length < inspection.minimumPieceLength && (
                <span className="board-inspection-warning">
                    Shorter than the configured minimum
                </span>
            )}
            <section className="board-inspection-parts">
                <strong>{`All parts from this board (${boardParts.length})`}</strong>
                <ol>
                    {boardParts.map(part => (
                        <li
                            className={part.key === inspection.key ? "is-inspected" : ""}
                            key={part.key}
                        >
                            <span>{part.roomName}</span>
                            <span>{boardOrderLabel(part.piece)}</span>
                            <span>
                                {`${formatNumber(part.piece.length, 0)} × ${formatNumber(part.piece.width, 0)} mm`}
                            </span>
                        </li>
                    ))}
                </ol>
            </section>
        </aside>
    );
}
