import type {
    ConnectionPayload,
    Piece,
    ProjectState,
    RoomStatePayload,
} from "../types";
import {
    boardOrderLabel,
    candidateForRoom,
    hasSplitRoomPieces,
    layingVector,
    scopedBoardIdentity,
} from "./planning";

export interface SimulationState {
    roomId: string;
    activeIndex: number;
    stepIndexByKey: Map<string, number>;
}

interface RendererOptions {
    canvas: HTMLCanvasElement;
    state: ProjectState;
    selectedRoomId: string | null;
    simulation: SimulationState | null;
}

function colorWithAlpha(color: string | undefined, alpha: number): string {
    if (!color) {
        return `rgba(220,220,220,${alpha})`;
    }

    if (!color.startsWith("#")) {
        return color;
    }

    const hex = color.slice(1);
    const normalized = hex.length === 3
        ? hex
            .split("")
            .map(character => character + character)
            .join("")
        : hex;

    const red = parseInt(normalized.slice(0, 2), 16);
    const green = parseInt(normalized.slice(2, 4), 16);
    const blue = parseInt(normalized.slice(4, 6), 16);

    return `rgba(${red},${green},${blue},${alpha})`;
}

function projectTransform(
    canvas: HTMLCanvasElement,
    state: ProjectState,
) {
    const width = canvas.clientWidth;
    const height = canvas.clientHeight;
    const bounds = state.bounds;
    const projectWidth = Math.max(1, bounds.max_x - bounds.min_x);
    const projectHeight = Math.max(1, bounds.max_y - bounds.min_y);
    const margin = 30;
    const scale = Math.min(
        (width - 2 * margin) / projectWidth,
        (height - 2 * margin) / projectHeight,
    );

    return {
        scale,
        x: (value: number) =>
            margin
            + (value - bounds.min_x) * scale,
        y: (value: number) =>
            margin
            + (value - bounds.min_y) * scale,
    };
}

function simulationStepState(
    simulation: SimulationState | null,
    piece: Piece,
    roomId: string,
    boardScope: string,
) {
    if (
        !simulation
        || simulation.roomId !== roomId
    ) {
        return "inactive";
    }

    const stepKey = [
        scopedBoardIdentity(piece, boardScope),
        piece.row,
    ].join(":");
    const index = simulation.stepIndexByKey.get(stepKey);

    if (index === undefined) {
        return "inactive";
    }

    if (index < simulation.activeIndex) {
        return "completed";
    }

    if (index === simulation.activeIndex) {
        return "active";
    }

    return "future";
}

function drawVisibleLineSegments(
    context: CanvasRenderingContext2D,
    segments: [number, number][],
    moveTo: (segmentStart: number) => void,
    lineTo: (segmentEnd: number) => void,
) {
    for (const [segmentStart, segmentEnd] of segments) {
        context.beginPath();
        moveTo(segmentStart);
        lineTo(segmentEnd);
        context.stroke();
    }
}

function overlappingSegments(
    start: number,
    end: number,
    segments: [number, number][],
) {
    const clipped = segments
        .map(([segmentStart, segmentEnd]) => [
            Math.max(start, segmentStart),
            Math.min(end, segmentEnd),
        ] as [number, number])
        .filter(
            ([segmentStart, segmentEnd]) =>
                segmentEnd > segmentStart,
        )
        .sort(([startA], [startB]) => startA - startB);

    if (!clipped.length) {
        return [] as [number, number][];
    }

    const merged: [number, number][] = [clipped[0]];

    for (const [segmentStart, segmentEnd] of clipped.slice(1)) {
        const current = merged[merged.length - 1];

        if (segmentStart <= current[1]) {
            current[1] = Math.max(current[1], segmentEnd);
        } else {
            merged.push([segmentStart, segmentEnd]);
        }
    }

    return merged;
}

function visibleSegments(
    start: number,
    end: number,
    blocked: [number, number][],
) {
    const mergedBlocked = overlappingSegments(start, end, blocked);
    const visible: [number, number][] = [];
    let cursor = start;

    for (const [blockStart, blockEnd] of mergedBlocked) {
        if (blockStart > cursor) {
            visible.push([cursor, blockStart]);
        }
        cursor = Math.max(cursor, blockEnd);
    }

    if (cursor < end) {
        visible.push([cursor, end]);
    }

    return visible;
}

function drawPieceOutline(
    context: CanvasRenderingContext2D,
    piece: Piece,
    boardPieces: Piece[],
    x: (value: number) => number,
    y: (value: number) => number,
    stepState: string,
) {
    const epsilon = 1e-6;
    const topBlocked: [number, number][] = [];
    const bottomBlocked: [number, number][] = [];
    const leftBlocked: [number, number][] = [];
    const rightBlocked: [number, number][] = [];

    for (const otherPiece of boardPieces) {
        if (otherPiece === piece) {
            continue;
        }

        if (Math.abs(otherPiece.y2 - piece.y1) <= epsilon) {
            topBlocked.push([otherPiece.x1, otherPiece.x2]);
        }
        if (Math.abs(otherPiece.y1 - piece.y2) <= epsilon) {
            bottomBlocked.push([otherPiece.x1, otherPiece.x2]);
        }
        if (Math.abs(otherPiece.x2 - piece.x1) <= epsilon) {
            leftBlocked.push([otherPiece.y1, otherPiece.y2]);
        }
        if (Math.abs(otherPiece.x1 - piece.x2) <= epsilon) {
            rightBlocked.push([otherPiece.y1, otherPiece.y2]);
        }
    }

    context.save();
    if (stepState === "future") {
        context.setLineDash([6, 5]);
    }

    drawVisibleLineSegments(
        context,
        visibleSegments(piece.x1, piece.x2, topBlocked),
        segmentStart => context.moveTo(x(segmentStart), y(piece.y1)),
        segmentEnd => context.lineTo(x(segmentEnd), y(piece.y1)),
    );
    drawVisibleLineSegments(
        context,
        visibleSegments(piece.x1, piece.x2, bottomBlocked),
        segmentStart => context.moveTo(x(segmentStart), y(piece.y2)),
        segmentEnd => context.lineTo(x(segmentEnd), y(piece.y2)),
    );
    drawVisibleLineSegments(
        context,
        visibleSegments(piece.y1, piece.y2, leftBlocked),
        segmentStart => context.moveTo(x(piece.x1), y(segmentStart)),
        segmentEnd => context.lineTo(x(piece.x1), y(segmentEnd)),
    );
    drawVisibleLineSegments(
        context,
        visibleSegments(piece.y1, piece.y2, rightBlocked),
        segmentStart => context.moveTo(x(piece.x2), y(segmentStart)),
        segmentEnd => context.lineTo(x(piece.x2), y(segmentEnd)),
    );
    context.restore();
}

function drawArrowHead(
    context: CanvasRenderingContext2D,
    tipX: number,
    tipY: number,
    directionX: number,
    directionY: number,
    size: number,
) {
    const perpendicularX = -directionY;
    const perpendicularY = directionX;
    const baseX = tipX - directionX * size;
    const baseY = tipY - directionY * size;

    context.beginPath();
    context.moveTo(tipX, tipY);
    context.lineTo(
        baseX + perpendicularX * size * 0.7,
        baseY + perpendicularY * size * 0.7,
    );
    context.lineTo(
        baseX - perpendicularX * size * 0.7,
        baseY - perpendicularY * size * 0.7,
    );
    context.closePath();
    context.fill();
}

function drawBoardAnnotation(
    context: CanvasRenderingContext2D,
    piece: Piece,
    room: RoomStatePayload | null,
    x: (value: number) => number,
    y: (value: number) => number,
    scale: number,
    stepState: string,
) {
    const screenX = x(piece.x1);
    const screenY = y(piece.y1);
    const screenWidth = (piece.x2 - piece.x1) * scale;
    const screenHeight = (piece.y2 - piece.y1) * scale;

    if (
        screenWidth < 34
        || screenHeight < 16
        || stepState === "future"
    ) {
        return;
    }

    const direction = layingVector(room);
    const label = boardOrderLabel(piece);
    const horizontal = Math.abs(direction.x) > 0;
    const centerX = screenX + screenWidth / 2;
    const centerY = screenY + screenHeight / 2;
    const labelFontSize = Math.max(
        10,
        Math.min(
            14,
            Math.floor(
                Math.min(screenWidth, screenHeight) * 0.32,
            ),
        ),
    );

    context.save();
    context.font = `600 ${labelFontSize}px sans-serif`;
    context.textAlign = "center";
    context.textBaseline = "middle";

    const textWidth = context.measureText(label).width;
    const chipWidth = textWidth + 14;
    const chipHeight = labelFontSize + 8;

    if (
        chipWidth > screenWidth - 8
        || chipHeight > screenHeight - 6
    ) {
        context.restore();
        return;
    }

    const chipX = centerX - chipWidth / 2;
    const chipY = centerY - chipHeight / 2;
    const arrowClearance = chipWidth / 2 + 10;
    const availableLength = horizontal
        ? screenWidth / 2 - arrowClearance
        : screenHeight / 2 - arrowClearance;
    const arrowLength = Math.max(0, Math.min(availableLength, 22));

    context.fillStyle = stepState === "active"
        ? "rgba(255, 248, 220, 0.96)"
        : "rgba(255, 255, 255, 0.82)";
    context.strokeStyle = stepState === "active"
        ? "rgba(154, 90, 0, 0.88)"
        : "rgba(17, 24, 39, 0.72)";
    context.lineWidth = 1;
    context.beginPath();
    context.roundRect(chipX, chipY, chipWidth, chipHeight, 6);
    context.fill();
    context.stroke();

    context.fillStyle = stepState === "active"
        ? "rgba(120, 66, 18, 0.95)"
        : "rgba(17, 24, 39, 0.92)";
    context.fillText(label, centerX, centerY);

    if (arrowLength >= 10) {
        const arrowStartX = centerX + direction.x * (chipWidth / 2 + 4);
        const arrowStartY = centerY + direction.y * (chipHeight / 2 + 4);
        const arrowEndX = arrowStartX + direction.x * arrowLength;
        const arrowEndY = arrowStartY + direction.y * arrowLength;

        context.strokeStyle = stepState === "active"
            ? "rgba(154, 90, 0, 0.96)"
            : "rgba(17, 24, 39, 0.9)";
        context.fillStyle = stepState === "active"
            ? "rgba(154, 90, 0, 0.96)"
            : "rgba(17, 24, 39, 0.9)";
        context.lineWidth = 1.5;
        context.beginPath();
        context.moveTo(arrowStartX, arrowStartY);
        context.lineTo(arrowEndX, arrowEndY);
        context.stroke();
        drawArrowHead(
            context,
            arrowEndX,
            arrowEndY,
            direction.x,
            direction.y,
            5,
        );
    }

    context.restore();
}

function drawPieces(
    context: CanvasRenderingContext2D,
    pieces: Piece[],
    minimumPieceLength: number,
    selected: boolean,
    x: (value: number) => number,
    y: (value: number) => number,
    scale: number,
    roomId: string,
    boardScope: string,
    room: RoomStatePayload | null,
    simulation: SimulationState | null,
) {
    const piecesByBoardRow = new Map<string, Piece[]>();
    const boardRowAnchors = new Map<string, Piece>();

    for (const piece of pieces || []) {
        const boardRowKey = [
            scopedBoardIdentity(piece, boardScope),
            piece.row,
        ].join(":");
        const grouped = piecesByBoardRow.get(boardRowKey) || [];
        grouped.push(piece);
        piecesByBoardRow.set(boardRowKey, grouped);

        const anchor = boardRowAnchors.get(boardRowKey);
        if (
            !anchor
            || piece.length * piece.width > anchor.length * anchor.width
        ) {
            boardRowAnchors.set(boardRowKey, piece);
        }
    }

    for (const piece of pieces || []) {
        const isShort =
            minimumPieceLength > 0
            && piece.length < minimumPieceLength;
        const stepState = simulationStepState(
            simulation,
            piece,
            roomId,
            boardScope,
        );

        if (stepState === "future") {
            context.fillStyle = isShort
                ? "rgba(255, 214, 214, 0.35)"
                : selected
                    ? "rgba(223, 242, 223, 0.34)"
                    : "rgba(237, 243, 237, 0.28)";
            context.strokeStyle = "rgba(102, 122, 102, 0.55)";
            context.lineWidth = 1;
        } else if (stepState === "active") {
            context.fillStyle = "#ffefb0";
            context.strokeStyle = "#ba7a00";
            context.lineWidth = 2.4;
        } else {
            context.fillStyle = isShort
                ? "#ffd6d6"
                : selected
                    ? "#dff2df"
                    : "#edf3ed";
            context.strokeStyle = isShort ? "#b00020" : "#667a66";
            context.lineWidth = isShort ? 2 : 0.8;
        }

        const screenX = x(piece.x1);
        const screenY = y(piece.y1);
        const screenWidth = (piece.x2 - piece.x1) * scale;
        const screenHeight = (piece.y2 - piece.y1) * scale;

        context.fillRect(screenX, screenY, screenWidth, screenHeight);
        drawPieceOutline(
            context,
            piece,
            piecesByBoardRow.get([
                scopedBoardIdentity(piece, boardScope),
                piece.row,
            ].join(":")) || [],
            x,
            y,
            stepState,
        );
    }

    for (const [boardRowKey, anchor] of boardRowAnchors.entries()) {
        void boardRowKey;
        drawBoardAnnotation(
            context,
            anchor,
            room,
            x,
            y,
            scale,
            simulationStepState(
                simulation,
                anchor,
                roomId,
                boardScope,
            ),
        );
    }
}

function drawRoomBackgrounds(
    context: CanvasRenderingContext2D,
    state: ProjectState,
    selectedRoomId: string | null,
    x: (value: number) => number,
    y: (value: number) => number,
    scale: number,
) {
    for (const room of state.rooms) {
        const selected = room.id === selectedRoomId;

        for (const rectangle of room.rectangles) {
            context.fillStyle = colorWithAlpha(
                rectangle.fill_color
                    || (selected ? "#dbeafe" : "#eeeeee"),
                rectangle.fill_alpha
                    ?? (selected ? 0.22 : 0.1),
            );
            context.fillRect(
                x(rectangle.x),
                y(rectangle.y),
                rectangle.width * scale,
                rectangle.height * scale,
            );
        }
    }
}

function drawPassages(
    context: CanvasRenderingContext2D,
    state: ProjectState,
    x: (value: number) => number,
    y: (value: number) => number,
    scale: number,
) {
    for (const connection of state.connections || []) {
        const passage = connection.passage;
        if (
            connection.type !== "continuous_then_cut"
            || !passage
        ) {
            continue;
        }

        context.save();
        context.fillStyle = "rgba(115, 115, 115, 0.10)";
        context.fillRect(
            x(passage.x),
            y(passage.y),
            passage.width * scale,
            passage.height * scale,
        );
        context.strokeStyle = "rgba(60, 60, 60, 0.55)";
        context.lineWidth = 1;
        context.setLineDash([5, 4]);
        context.strokeRect(
            x(passage.x),
            y(passage.y),
            passage.width * scale,
            passage.height * scale,
        );
        context.restore();
    }
}

function drawFloorPieces(
    context: CanvasRenderingContext2D,
    state: ProjectState,
    selectedRoomId: string | null,
    simulation: SimulationState | null,
    x: (value: number) => number,
    y: (value: number) => number,
    scale: number,
) {
    const renderedByContinuous = new Set<string>();

    for (const connection of state.connections || []) {
        if (
            connection.type !== "continuous_then_cut"
            || !hasSplitRoomPieces(connection)
        ) {
            continue;
        }

        for (const [roomId, pieces] of Object.entries(
            connection.continuous?.room_pieces || {},
        )) {
            const room = state.rooms.find(item => item.id === roomId) || null;
            drawPieces(
                context,
                pieces,
                room?.minimum_piece_length || 0,
                roomId === selectedRoomId,
                x,
                y,
                scale,
                roomId,
                `connection:${connection.id}`,
                room,
                simulation,
            );
            renderedByContinuous.add(roomId);
        }
    }

    for (const room of state.rooms) {
        if (renderedByContinuous.has(room.id)) {
            continue;
        }

        const candidate = candidateForRoom(state, room);
        if (!candidate) {
            continue;
        }

        drawPieces(
            context,
            candidate.pieces,
            room.minimum_piece_length,
            room.id === selectedRoomId,
            x,
            y,
            scale,
            room.id,
            `room:${room.id}`,
            room,
            simulation,
        );
    }
}

function drawTransition(
    context: CanvasRenderingContext2D,
    connection: ConnectionPayload,
    x: (value: number) => number,
    y: (value: number) => number,
    scale: number,
) {
    const continuous = connection.continuous;
    const cut = continuous?.cut_plan;
    const passage = connection.passage;

    if (!passage) {
        return;
    }

    context.save();

    if (!cut) {
        context.fillStyle = continuous?.running
            ? "rgba(245, 158, 11, 0.28)"
            : "rgba(100, 116, 139, 0.22)";
        context.fillRect(
            x(passage.x),
            y(passage.y),
            passage.width * scale,
            passage.height * scale,
        );
        context.restore();
        return;
    }

    const thresholdWidthMm = Math.min(
        cut.axis === "y" ? passage.height : passage.width,
        Math.max(cut.gap_width_mm + 24, 35),
    );

    context.fillStyle = "rgba(130, 92, 52, 0.28)";
    if (cut.axis === "y") {
        context.fillRect(
            x(passage.x),
            y(cut.position_mm - thresholdWidthMm / 2),
            passage.width * scale,
            Math.max(4, thresholdWidthMm * scale),
        );
    } else {
        context.fillRect(
            x(cut.position_mm - thresholdWidthMm / 2),
            y(passage.y),
            Math.max(4, thresholdWidthMm * scale),
            passage.height * scale,
        );
    }

    context.fillStyle = cut.method === "natural_joint"
        ? "#1b8f3a"
        : "#202020";
    if (cut.axis === "y") {
        context.fillRect(
            x(passage.x),
            y(cut.position_mm - cut.gap_width_mm / 2),
            passage.width * scale,
            Math.max(2, cut.gap_width_mm * scale),
        );
    } else {
        context.fillRect(
            x(cut.position_mm - cut.gap_width_mm / 2),
            y(passage.y),
            Math.max(2, cut.gap_width_mm * scale),
            passage.height * scale,
        );
    }

    context.fillStyle = "#111";
    context.font = "600 12px sans-serif";
    const label = cut.method === "natural_joint"
        ? "Natural joint"
        : `Saw cut - ${cut.cut_boards} boards`;
    context.fillText(label, x(passage.x) + 6, y(passage.y) - 7);
    context.restore();
}

function drawTransitions(
    context: CanvasRenderingContext2D,
    state: ProjectState,
    x: (value: number) => number,
    y: (value: number) => number,
    scale: number,
) {
    for (const connection of state.connections || []) {
        if (connection.type === "continuous_then_cut") {
            drawTransition(context, connection, x, y, scale);
        }
    }
}

function drawRoomOutlines(
    context: CanvasRenderingContext2D,
    state: ProjectState,
    selectedRoomId: string | null,
    x: (value: number) => number,
    y: (value: number) => number,
) {
    for (const room of state.rooms) {
        const selected = room.id === selectedRoomId;
        context.beginPath();
        room.outline.forEach((point, index) => {
            if (index === 0) {
                context.moveTo(x(point[0]), y(point[1]));
            } else {
                context.lineTo(x(point[0]), y(point[1]));
            }
        });
        context.strokeStyle = selected ? "#1a73e8" : "#111";
        context.lineWidth = selected ? 4 : 2;
        context.stroke();

        context.fillStyle = "#111";
        context.font = "600 14px sans-serif";
        context.fillText(
            room.name,
            x(room.bounds.min_x) + 8,
            y(room.bounds.min_y) + 20,
        );
    }
}

export function renderFloorPlan({
    canvas,
    state,
    selectedRoomId,
    simulation,
}: RendererOptions) {
    const context = canvas.getContext("2d");
    if (!context) {
        return;
    }

    const ratio = window.devicePixelRatio || 1;
    const rectangle = canvas.getBoundingClientRect();
    canvas.width = Math.max(1, Math.floor(rectangle.width * ratio));
    canvas.height = Math.max(1, Math.floor(rectangle.height * ratio));
    context.setTransform(ratio, 0, 0, ratio, 0, 0);

    context.clearRect(0, 0, canvas.clientWidth, canvas.clientHeight);
    const {x, y, scale} = projectTransform(canvas, state);

    drawRoomBackgrounds(context, state, selectedRoomId, x, y, scale);
    drawPassages(context, state, x, y, scale);
    drawFloorPieces(
        context,
        state,
        selectedRoomId,
        simulation,
        x,
        y,
        scale,
    );
    drawTransitions(context, state, x, y, scale);
    drawRoomOutlines(context, state, selectedRoomId, x, y);
}
