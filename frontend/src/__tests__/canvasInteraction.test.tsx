import {render, screen} from "@testing-library/react";
import {describe, expect, it} from "vitest";

import {BoardInspection} from "../components/BoardInspection";
import {
    hitTestFloorPiece,
    inspectableFloorPieces,
} from "../lib/canvasRenderer";
import type {PieceHit} from "../lib/canvasRenderer";
import type {ProjectState} from "../types";

const state: ProjectState = {
    project_name: "Inspection test",
    board: {},
    bounds: {min_x: 0, min_y: 0, max_x: 1000, max_y: 1000},
    output_dir: "output",
    connections: [],
    rooms: [
        {
            id: "room_1",
            name: "Living room",
            origin: {x: 0, y: 0},
            rectangles: [],
            outline: [],
            bounds: {min_x: 0, min_y: 0, max_x: 1000, max_y: 1000},
            settings: {
                orientation: "horizontal",
                start_corner: "upper_left",
                expansion_gap_mm: 5,
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
            },
            minimum_piece_length: 300,
            running: false,
            paused: false,
            finished: true,
            error: null,
            profile: {},
            current: {
                pieces: [
                    {
                        row: 2,
                        segment: 1,
                        piece: 3,
                        x1: 100,
                        x2: 300,
                        y1: 100,
                        y2: 250,
                        length: 200,
                        width: 150,
                        source_board_index: 7,
                        physical_board_id: "B00007",
                        is_full_length: false,
                    },
                ],
            },
            best: null,
        },
    ],
};

describe("canvas board inspection", () => {
    it("finds the rendered piece under a canvas point", () => {
        const hit = hitTestFloorPiece(
            state,
            {width: 1000, height: 1000},
            {x: 200, y: 180},
        );

        expect(hit?.piece.physical_board_id).toBe("B00007");
        expect(hit?.roomName).toBe("Living room");
        expect(hitTestFloorPiece(
            state,
            {width: 1000, height: 1000},
            {x: 800, y: 800},
        )).toBeNull();
    });

    it("exposes the same visible pieces used by the renderer", () => {
        expect(inspectableFloorPieces(state)).toHaveLength(1);
        expect(inspectableFloorPieces(state)[0]?.boardScope).toBe("room:room_1");
    });

    it("groups every cut piece from the same physical board", () => {
        const firstPiece = state.rooms[0].current!.pieces[0];
        const cutBoardState: ProjectState = {
            ...state,
            rooms: [
                {
                    ...state.rooms[0],
                    current: {
                        pieces: [
                            firstPiece,
                            {
                                ...firstPiece,
                                piece: 4,
                                segment: 2,
                                x1: 400,
                                x2: 550,
                                length: 150,
                            },
                            {
                                ...firstPiece,
                                piece: 5,
                                segment: 3,
                                x1: 600,
                                x2: 800,
                                physical_board_id: "B00008",
                            },
                        ],
                    },
                },
            ],
        };

        const pieces = inspectableFloorPieces(cutBoardState);

        expect(pieces[0]?.boardKey).toBe(pieces[1]?.boardKey);
        expect(pieces[0]?.boardKey).not.toBe(pieces[2]?.boardKey);
        expect(pieces[0]?.key).not.toBe(pieces[1]?.key);
    });

    it("inspects split transition pieces instead of stale room candidates", () => {
        const transitionPiece = {
            ...state.rooms[0].current!.pieces[0],
            physical_board_id: "C00001",
        };
        const continuousState: ProjectState = {
            ...state,
            connections: [
                {
                    id: "shared_floor",
                    type: "continuous_then_cut",
                    room_a: "room_1",
                    continuous: {
                        running: false,
                        finished: true,
                        error: null,
                        candidate: null,
                        profile: {},
                        room_pieces: {room_1: [transitionPiece]},
                        cut_plan: null,
                    },
                },
            ],
        };

        const pieces = inspectableFloorPieces(continuousState);

        expect(pieces).toHaveLength(1);
        expect(pieces[0]?.piece.physical_board_id).toBe("C00001");
        expect(pieces[0]?.boardScope).toBe("connection:shared_floor");
    });

    it("shows board metadata and a short-piece warning", () => {
        const inspection: PieceHit = {
            ...inspectableFloorPieces(state)[0],
            anchor: {x: 100, y: 100},
        };

        render(<BoardInspection inspection={inspection} />);

        expect(screen.getByRole("status")).toHaveTextContent("B00007");
        expect(screen.getByRole("status")).toHaveTextContent("Living room");
        expect(screen.getByRole("status")).toHaveTextContent("Source7");
        expect(screen.getByRole("status")).toHaveTextContent("200 × 150 mm");
        expect(screen.getByRole("status")).toHaveTextContent("Cut piece");
        expect(screen.getByRole("status")).toHaveTextContent(
            "Shorter than the configured minimum",
        );
    });
});
