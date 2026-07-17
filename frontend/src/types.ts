export interface Piece {
    row: number;
    segment: number;
    piece: number;
    x1: number;
    x2: number;
    y1: number;
    y2: number;
    length: number;
    width: number;
    source_board_index: number | null;
    physical_board_id: string | null;
    is_full_length: boolean;
}

export interface Candidate {
    attempt?: number;
    total_attempts?: number;
    base_offset?: number;
    row_width_offset?: number;
    short_count?: number;
    very_short_count?: number;
    shortest_piece?: number;
    joint_violations?: number;
    narrow_row_count?: number;
    very_narrow_row_count?: number;
    narrowest_row_width?: number;
    row_offsets?: Record<string, number>;
    phase?: string;
    timings?: Record<string, number>;
    material_metrics?: {
        new_boards?: number;
        exact_offcut_reuses?: number;
        trimmed_offcut_reuses?: number;
        cuts?: number;
        kerf_waste_mm?: number;
        discarded_mm?: number;
    };
    pieces: Piece[];
}

export interface RoomSettings {
    orientation: "horizontal" | "vertical";
    start_corner:
        | "upper_left"
        | "upper_right"
        | "lower_left"
        | "lower_right";
    expansion_gap_mm: number;
    saw_kerf_mm: number;
    minimum_piece_length_mm: number;
    minimum_joint_distance_mm: number;
    stagger_step_mm: number;
    optimization_step_mm: number;
    row_width_optimization_step_mm: number;
    minimum_row_width_mm: number;
    preferred_minimum_row_width_mm: number;
    optimizer_workers: number;
    preview_every_n_results: number;
    local_optimize_top_n: number;
    frame_delay_ms: number;
    board_length_mm: number;
    board_width_mm: number;
    waste_percent?: number;
    boards_per_pack?: number;
}

export interface Bounds {
    min_x: number;
    min_y: number;
    max_x: number;
    max_y: number;
}

export interface RoomRectangle {
    x: number;
    y: number;
    width: number;
    height: number;
    fill_color?: string;
    fill_alpha?: number;
}

export interface RoomProfile {
    phase?: string;
    elapsed_s?: number;
    completed?: number;
    total?: number;
    candidates_per_second?: number;
    eta_s?: number | null;
    workers?: number;
    coarse_total?: number;
    coarse_completed?: number;
    refine_total?: number;
    refine_completed?: number;
    timing_totals?: Record<string, number>;
    local_variants?: number;
}

export interface RoomStatePayload {
    id: string;
    name: string;
    origin: {x: number; y: number};
    rectangles: RoomRectangle[];
    outline: [number, number][];
    bounds: Bounds;
    settings: RoomSettings;
    minimum_piece_length: number;
    running: boolean;
    paused: boolean;
    finished: boolean;
    error: string | null;
    current: Candidate | null;
    best: Candidate | null;
    profile: RoomProfile;
}

export interface ContinuousProfile {
    phase?: string;
    completed?: number;
    total?: number;
    percent?: number;
    elapsed_s?: number;
    eta_s?: number | null;
    candidates_per_second?: number;
    workers?: number;
    coarse_total?: number;
    coarse_completed?: number;
    refine_total?: number;
    refine_completed?: number;
    message?: string;
}

export interface Passage {
    x: number;
    y: number;
    width: number;
    height: number;
}

export interface CutPlan {
    method: "natural_joint" | "saw_cut";
    axis: "x" | "y";
    position_mm: number;
    gap_width_mm: number;
    cut_boards: number;
    shortest_fragment_mm: number;
}

export interface ContinuousStatePayload {
    running: boolean;
    finished: boolean;
    error: string | null;
    candidate: Candidate | null;
    profile: ContinuousProfile;
    room_pieces: Record<string, Piece[]>;
    cut_plan: CutPlan | null;
}

export interface ConnectionPayload {
    id: string;
    type: string;
    room_a?: string;
    room_b?: string;
    passage?: Passage;
    continuous?: ContinuousStatePayload | null;
}

export interface ProjectState {
    project_name: string;
    board: Record<string, number | string>;
    rooms: RoomStatePayload[];
    bounds: Bounds;
    output_dir: string;
    connections: ConnectionPayload[];
}

export interface RoomActionResponse {
    ok: boolean;
    settings?: RoomSettings;
    message?: string;
    error?: string;
}
