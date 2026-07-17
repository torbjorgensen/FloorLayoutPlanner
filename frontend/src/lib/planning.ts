import type {
    ConnectionPayload,
    Piece,
    ProjectState,
    RoomStatePayload,
} from "../types";

export interface SimulationStep {
    key: string;
    roomId: string;
    boardScope: string;
    row: number;
    anchor: Piece;
    pieces: Piece[];
}

export function titleCaseWords(value: string | null | undefined): string {
    return String(value || "–")
        .split(/[_\s-]+/)
        .filter(Boolean)
        .map(
            word =>
                word.charAt(0).toUpperCase()
                + word.slice(1),
        )
        .join(" ");
}

export function roomById(
    state: ProjectState | null,
    roomId: string | null,
): RoomStatePayload | null {
    return (
        state?.rooms.find(room => room.id === roomId)
        || null
    );
}

export function continuousConnectionForRoom(
    state: ProjectState | null,
    roomId: string,
): ConnectionPayload | null {
    return (
        state?.connections.find(
            connection =>
                connection.type === "continuous_then_cut"
                && connection.continuous
                && (
                    connection.room_a === roomId
                    || connection.room_b === roomId
                ),
        ) || null
    );
}

export function hasSplitRoomPieces(
    connection: ConnectionPayload | null,
): boolean {
    const roomPieces = connection?.continuous?.room_pieces;

    return Boolean(
        roomPieces
        && Object.keys(roomPieces).length > 0,
    );
}

export function candidateForRoom(
    state: ProjectState | null,
    room: RoomStatePayload | null,
) {
    if (!room) {
        return null;
    }

    const connection = continuousConnectionForRoom(
        state,
        room.id,
    );
    const splitPieces =
        connection?.continuous?.room_pieces?.[room.id];

    if (Array.isArray(splitPieces) && splitPieces.length > 0) {
        const sharedCandidate =
            connection?.continuous?.candidate;

        return sharedCandidate
            ? {
                ...sharedCandidate,
                pieces: splitPieces,
            }
            : {
                pieces: splitPieces,
            };
    }

    return room.current || room.best || null;
}

export function boardIdentity(piece: Piece): string {
    return (
        piece.physical_board_id
        || [
            "legacy",
            piece.row,
            piece.segment,
            piece.source_board_index,
        ].join(":")
    );
}

export function scopedBoardIdentity(
    piece: Piece,
    boardScope: string,
): string {
    return `${boardScope}:${boardIdentity(piece)}`;
}

export function boardRowIdentity(
    piece: Piece,
    boardScope: string,
): string {
    return [
        scopedBoardIdentity(piece, boardScope),
        piece.row,
    ].join(":");
}

export function roomPiecesForSimulation(
    state: ProjectState | null,
    room: RoomStatePayload | null,
) {
    if (!room) {
        return null;
    }

    const connection = continuousConnectionForRoom(
        state,
        room.id,
    );
    const splitPieces =
        connection?.continuous?.room_pieces?.[room.id];

    if (Array.isArray(splitPieces) && splitPieces.length > 0) {
        return {
            pieces: splitPieces,
            boardScope: `connection:${connection?.id}`,
        };
    }

    const candidate = room.current || room.best;

    if (!candidate?.pieces?.length) {
        return null;
    }

    return {
        pieces: candidate.pieces,
        boardScope: `room:${room.id}`,
    };
}

export function layingVector(room: RoomStatePayload | null) {
    const orientation =
        room?.settings.orientation || "horizontal";
    const startCorner =
        room?.settings.start_corner || "upper_left";

    if (orientation === "horizontal") {
        return startCorner.endsWith("right")
            ? {x: -1, y: 0}
            : {x: 1, y: 0};
    }

    return startCorner.startsWith("lower")
        ? {x: 0, y: -1}
        : {x: 0, y: 1};
}

export function compareAlongDirection(
    first: Piece,
    second: Piece,
    room: RoomStatePayload | null,
): number {
    const direction = layingVector(room);

    if (Math.abs(direction.x) > 0) {
        const firstValue =
            direction.x > 0 ? first.x1 : first.x2;
        const secondValue =
            direction.x > 0 ? second.x1 : second.x2;

        if (firstValue !== secondValue) {
            return direction.x > 0
                ? firstValue - secondValue
                : secondValue - firstValue;
        }
    } else {
        const firstValue =
            direction.y > 0 ? first.y1 : first.y2;
        const secondValue =
            direction.y > 0 ? second.y1 : second.y2;

        if (firstValue !== secondValue) {
            return direction.y > 0
                ? firstValue - secondValue
                : secondValue - firstValue;
        }
    }

    return Number(first.source_board_index || 0)
        - Number(second.source_board_index || 0);
}

export function buildSimulationSteps(
    state: ProjectState | null,
    room: RoomStatePayload | null,
): SimulationStep[] {
    const simulationPieces =
        roomPiecesForSimulation(state, room);

    if (!simulationPieces || !room) {
        return [];
    }

    const stepsByBoardRow = new Map<string, SimulationStep>();

    for (const piece of simulationPieces.pieces) {
        const key = boardRowIdentity(
            piece,
            simulationPieces.boardScope,
        );
        const existing = stepsByBoardRow.get(key);

        if (existing) {
            existing.pieces.push(piece);
            if (
                compareAlongDirection(
                    piece,
                    existing.anchor,
                    room,
                ) < 0
            ) {
                existing.anchor = piece;
            }
            continue;
        }

        stepsByBoardRow.set(key, {
            key,
            roomId: room.id,
            boardScope: simulationPieces.boardScope,
            row: Number(piece.row || 0),
            anchor: piece,
            pieces: [piece],
        });
    }

    return [...stepsByBoardRow.values()].sort(
        (first, second) => {
            if (first.row !== second.row) {
                return first.row - second.row;
            }

            return compareAlongDirection(
                first.anchor,
                second.anchor,
                room,
            );
        },
    );
}

export function boardOrderLabel(piece: Piece): string {
    const boardIndex = Number(piece.source_board_index);

    if (Number.isFinite(boardIndex)) {
        return `${boardIndex}`;
    }

    const match = String(piece.physical_board_id || "").match(/(\d+)/);
    return match ? match[1] : "?";
}

export function formatNumber(
    value: number | null | undefined,
    decimals = 0,
): string {
    const number = Number(value);

    if (!Number.isFinite(number)) {
        return "–";
    }

    return number.toFixed(decimals);
}

export function formatSeconds(
    value: number | null | undefined,
): string {
    if (
        value === null
        || value === undefined
        || !Number.isFinite(Number(value))
    ) {
        return "–";
    }

    const secondsValue = Number(value);

    if (secondsValue < 1) {
        return `${Math.round(secondsValue * 1000)} ms`;
    }

    const minutes = Math.floor(secondsValue / 60);
    const seconds = Math.floor(secondsValue % 60);

    if (minutes > 0) {
        return `${minutes} min ${seconds} s`;
    }

    return `${secondsValue.toFixed(1)} s`;
}
