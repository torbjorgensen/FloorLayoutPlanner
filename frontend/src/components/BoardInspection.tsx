import type {PieceHit} from "../lib/canvasRenderer";
import {boardOrderLabel, formatNumber} from "../lib/planning";

interface BoardInspectionProps {
    inspection: PieceHit;
    pinned?: boolean;
}

export function BoardInspection({inspection, pinned = false}: BoardInspectionProps) {
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
        </aside>
    );
}
