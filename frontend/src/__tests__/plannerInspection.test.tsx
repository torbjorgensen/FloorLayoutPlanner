import {fireEvent, render, screen, waitFor} from "@testing-library/react";
import {afterEach, beforeEach, describe, expect, it, vi} from "vitest";

import PlannerPage from "../pages/PlannerPage";
import type {PieceHit} from "../lib/canvasRenderer";
import type {ProjectState, RoomSettings} from "../types";

const inspectionMocks = vi.hoisted(() => ({
    hit: vi.fn(),
    pieces: vi.fn(),
    state: null as ProjectState | null,
}));

vi.mock("../hooks/useProjectState", () => ({
    useProjectState: () => ({
        state: inspectionMocks.state,
        connectionStatus: "connected",
        connectionError: null,
    }),
}));

vi.mock("../lib/canvasRenderer", () => ({
    hitTestFloorPiece: inspectionMocks.hit,
    inspectableFloorPieces: inspectionMocks.pieces,
    renderFloorPlan: vi.fn(),
}));

const settings = {
    orientation: "horizontal",
    start_corner: "upper_left",
    expansion_gap_mm: 5,
    saw_kerf_mm: 3.2,
    minimum_piece_length_mm: 300,
    minimum_joint_distance_mm: 300,
    stagger_step_mm: 700,
    optimization_step_mm: 20,
    row_width_optimization_step_mm: 5,
    minimum_row_width_mm: 60,
    preferred_minimum_row_width_mm: 100,
    optimizer_workers: 4,
    preview_every_n_results: 25,
    local_optimize_top_n: 12,
    frame_delay_ms: 60,
    board_length_mm: 1380,
    board_width_mm: 193,
} satisfies RoomSettings;

const state: ProjectState = {
    project_name: "Inspection interactions",
    board: {},
    bounds: {min_x: 0, min_y: 0, max_x: 1000, max_y: 1000},
    output_dir: "output",
    connections: [],
    rooms: [{
        id: "room_1",
        name: "Living room",
        origin: {x: 0, y: 0},
        rectangles: [],
        outline: [],
        bounds: {min_x: 0, min_y: 0, max_x: 1000, max_y: 1000},
        settings,
        minimum_piece_length: 300,
        running: false,
        paused: false,
        finished: true,
        error: null,
        profile: {},
        current: {pieces: []},
        best: null,
    }],
};

function inspection(key: string, boardKey: string): PieceHit {
    return {
        key,
        boardKey,
        boardScope: "room:room_1",
        roomId: "room_1",
        roomName: "Living room",
        minimumPieceLength: 300,
        anchor: {x: 100, y: 100},
        piece: {
            row: 1,
            segment: 1,
            piece: 1,
            x1: 100,
            x2: 500,
            y1: 100,
            y2: 293,
            length: 400,
            width: 193,
            source_board_index: Number(key.slice(-1)),
            physical_board_id: boardKey,
            is_full_length: false,
        },
    };
}

const first = inspection("piece-1", "B00001");
const second = inspection("piece-2", "B00002");

function renderPlanner() {
    inspectionMocks.state = state;
    inspectionMocks.pieces.mockReturnValue([first, second]);
    inspectionMocks.hit.mockImplementation((_, __, point: {x: number}) =>
        point.x < 300 ? first : point.x < 600 ? second : null,
    );
    const result = render(<PlannerPage projectId="project-1" />);
    const canvas = result.container.querySelector("canvas")!;
    vi.spyOn(canvas, "getBoundingClientRect").mockReturnValue({
        x: 0,
        y: 0,
        left: 0,
        top: 0,
        right: 1000,
        bottom: 1000,
        width: 1000,
        height: 1000,
        toJSON: () => ({}),
    });
    return {...result, canvas};
}

describe("planner board inspection interactions", () => {
    beforeEach(() => {
        vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => {
            callback(0);
            return 1;
        });
        vi.stubGlobal("cancelAnimationFrame", vi.fn());
    });

    afterEach(() => {
        vi.restoreAllMocks();
        vi.unstubAllGlobals();
    });

    it("hovers transiently, pins by mouse, and replaces the pinned board", () => {
        const {canvas} = renderPlanner();

        fireEvent.pointerMove(canvas, {pointerType: "mouse", clientX: 100, clientY: 100});
        expect(screen.getByRole("status")).toHaveTextContent("B00001");
        fireEvent.pointerLeave(canvas, {pointerType: "mouse"});
        expect(screen.queryByRole("status")).not.toBeInTheDocument();

        fireEvent.pointerDown(canvas, {pointerType: "mouse", clientX: 100, clientY: 100});
        expect(screen.getByRole("status")).toHaveTextContent("Pinned selection");
        fireEvent.pointerLeave(canvas, {pointerType: "mouse"});
        expect(screen.getByRole("status")).toHaveTextContent("B00001");

        fireEvent.pointerDown(canvas, {pointerType: "mouse", clientX: 400, clientY: 100});
        expect(screen.getByRole("status")).toHaveTextContent("B00002");
    });

    it("dismisses a pin on empty canvas, outside pointer down, and Escape", () => {
        const {canvas} = renderPlanner();

        fireEvent.pointerDown(canvas, {pointerType: "mouse", clientX: 100, clientY: 100});
        fireEvent.pointerDown(canvas, {pointerType: "mouse", clientX: 800, clientY: 100});
        expect(screen.queryByRole("status")).not.toBeInTheDocument();

        fireEvent.pointerDown(canvas, {pointerType: "mouse", clientX: 100, clientY: 100});
        fireEvent.pointerDown(document.body, {pointerType: "mouse"});
        expect(screen.queryByRole("status")).not.toBeInTheDocument();

        fireEvent.pointerDown(canvas, {pointerType: "mouse", clientX: 100, clientY: 100});
        fireEvent.keyDown(canvas, {key: "Escape"});
        expect(screen.queryByRole("status")).not.toBeInTheDocument();
    });

    it("supports touch pinning and clears an unavailable layout", async () => {
        const {canvas, rerender} = renderPlanner();

        fireEvent.pointerDown(canvas, {pointerType: "touch", clientX: 100, clientY: 100});
        expect(screen.getByRole("status")).toHaveTextContent("Pinned selection");

        inspectionMocks.pieces.mockReturnValue([]);
        inspectionMocks.state = {...state, rooms: []};
        rerender(<PlannerPage projectId="project-1" />);

        await waitFor(() => {
            expect(screen.queryByRole("status")).not.toBeInTheDocument();
        });
    });
});
