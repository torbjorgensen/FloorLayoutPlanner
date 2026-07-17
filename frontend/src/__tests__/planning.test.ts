import {describe, expect, it} from "vitest";

import {buildSimulationSteps, titleCaseWords} from "../lib/planning";
import type {ProjectState} from "../types";

const state: ProjectState = {
    project_name: "Demo",
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
            outline: [
                [0, 0],
                [1000, 0],
                [1000, 1000],
                [0, 1000],
            ],
            bounds: {min_x: 0, min_y: 0, max_x: 1000, max_y: 1000},
            settings: {
                orientation: "horizontal",
                start_corner: "lower_right",
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
                        row: 1,
                        segment: 1,
                        piece: 1,
                        x1: 600,
                        x2: 1000,
                        y1: 0,
                        y2: 193,
                        length: 400,
                        width: 193,
                        source_board_index: 1,
                        physical_board_id: "B00001",
                        is_full_length: false,
                    },
                    {
                        row: 1,
                        segment: 2,
                        piece: 2,
                        x1: 0,
                        x2: 600,
                        y1: 0,
                        y2: 193,
                        length: 600,
                        width: 193,
                        source_board_index: 2,
                        physical_board_id: "B00002",
                        is_full_length: false,
                    },
                ],
            },
            best: null,
        },
    ],
};

describe("planning helpers", () => {
    it("formats title-cased labels", () => {
        expect(titleCaseWords("lower_right")).toBe("Lower Right");
    });

    it("orders simulation steps along the laying direction", () => {
        const room = state.rooms[0];
        const steps = buildSimulationSteps(state, room);

        expect(steps).toHaveLength(2);
        expect(steps[0]?.anchor.physical_board_id).toBe("B00001");
        expect(steps[1]?.anchor.physical_board_id).toBe("B00002");
    });
});
