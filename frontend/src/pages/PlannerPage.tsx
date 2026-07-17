import {useEffect, useMemo, useRef, useState} from "react";
import Nav from "react-bootstrap/Nav";
import {ActionButton} from "../components/ActionButton";
import {BoardInspection} from "../components/BoardInspection";
import {MetricRows} from "../components/MetricRows";
import {PlannerHeader} from "../components/PlannerHeader";
import {RoomNavigator} from "../components/RoomNavigator";
import {useProjectState} from "../hooks/useProjectState";

import {
    hitTestFloorPiece,
    inspectableFloorPieces,
    renderFloorPlan,
} from "../lib/canvasRenderer";
import type {PieceHit} from "../lib/canvasRenderer";
import {
    boardOrderLabel,
    buildSimulationSteps,
    candidateForRoom,
    continuousConnectionForRoom,
    formatNumber,
    formatSeconds,
    hasSplitRoomPieces,
    roomById,
    titleCaseWords,
} from "../lib/planning";
import type {
    ProjectState,
    RoomActionResponse,
    RoomSettings,
    RoomStatePayload,
} from "../types";


type FormState = Record<string, string>;

interface SimulationRun {
    roomId: string;
    activeIndex: number;
    stepIndexByKey: Map<string, number>;
    timerId: number | null;
    total: number;
}

function formStateFromRoom(room: RoomStatePayload): FormState {
    return Object.fromEntries(
        Object.entries(room.settings).map(([key, value]) => [key, String(value)]),
    );
}

function setIfPresent<T extends keyof RoomSettings>(
    formState: FormState,
    key: T,
) {
    return formState[key] ?? "";
}


function statusForRoom(
    state: ProjectState | null,
    room: RoomStatePayload,
) {
    const connection = continuousConnectionForRoom(state, room.id);
    const continuous = connection?.continuous;
    const progress = continuous?.profile || {};

    if (continuous?.error) {
        return {
            text: `Transition calculation error: ${continuous.error}`,
            kind: "error",
        };
    }

    if (continuous?.running) {
        const percent = Number(progress.percent || 0);
        const etaText =
            progress.eta_s !== null
            && progress.eta_s !== undefined
                ? ` - about ${formatSeconds(progress.eta_s)} remaining`
                : "";

        return {
            text:
                `${progress.message || "Optimizing transition"}`
                + ` - ${formatNumber(percent, 1)} %`
                + etaText,
            kind: "running",
        };
    }

    if (
        continuous?.finished
        && hasSplitRoomPieces(connection)
    ) {
        return {
            text: "Finished - the floor is split at the expansion gap.",
            kind: "finished",
        };
    }

    if (
        continuous?.finished
        && !hasSplitRoomPieces(connection)
    ) {
        return {
            text: "Calculation finished, but split room pieces are missing.",
            kind: "warning",
        };
    }

    if (room.error) {
        return {
            text: room.error,
            kind: "error",
        };
    }

    if (room.paused) {
        return {
            text: "Paused.",
            kind: "paused",
        };
    }

    if (room.running) {
        return {
            text: "Optimizing room …",
            kind: "running",
        };
    }

    if (room.finished) {
        return {
            text: "Room optimization finished. Waiting for shared transition.",
            kind: "warning",
        };
    }

    return {
        text: "Waiting.",
        kind: "idle",
    };
}

function PlannerPage() {
    const canvasRef = useRef<HTMLCanvasElement | null>(null);
    const hoverFrameRef = useRef<number | null>(null);
    const {state, connectionStatus, connectionError} = useProjectState();
    const [selectedRoomId, setSelectedRoomId] = useState<string | null>(null);
    const [activePanel, setActivePanel] = useState(0);
    const [formState, setFormState] = useState<FormState>({});
    const [validationMessage, setValidationMessage] = useState("Ready.");
    const [simulationDelayMs, setSimulationDelayMs] = useState("400");
    const [simulationStatus, setSimulationStatus] = useState("Simulation idle.");
    const [simulationRun, setSimulationRun] = useState<SimulationRun | null>(null);
    const [inspectedPiece, setInspectedPiece] = useState<PieceHit | null>(null);
    const [inspectionPinned, setInspectionPinned] = useState(false);

    const selectedRoom = useMemo(
        () => roomById(state, selectedRoomId),
        [state, selectedRoomId],
    );

    useEffect(() => {
        if (!state) {
            return;
        }

        setSelectedRoomId(previous =>
            previous && state.rooms.some(room => room.id === previous)
                ? previous
                : state.rooms[0]?.id || null,
        );
    }, [state]);

    useEffect(() => {
        if (selectedRoom) {
            setFormState(formStateFromRoom(selectedRoom));
        }
    }, [selectedRoom]);

    useEffect(() => {
        const canvas = canvasRef.current;
        if (!canvas || !state) {
            return;
        }

        renderFloorPlan({
            canvas,
            state,
            selectedRoomId,
            simulation: simulationRun
                ? {
                    roomId: simulationRun.roomId,
                    activeIndex: simulationRun.activeIndex,
                    stepIndexByKey: simulationRun.stepIndexByKey,
                }
                : null,
            inspectedBoardKey: inspectedPiece?.boardKey,
        });

        const onResize = () => {
            if (!canvasRef.current || !state) {
                return;
            }
            renderFloorPlan({
                canvas: canvasRef.current,
                state,
                selectedRoomId,
                simulation: simulationRun
                    ? {
                        roomId: simulationRun.roomId,
                        activeIndex: simulationRun.activeIndex,
                        stepIndexByKey: simulationRun.stepIndexByKey,
                    }
                    : null,
                inspectedBoardKey: inspectedPiece?.boardKey,
            });
        };

        window.addEventListener("resize", onResize);
        return () => window.removeEventListener("resize", onResize);
    }, [state, selectedRoomId, simulationRun, inspectedPiece?.boardKey]);

    useEffect(() => {
        setInspectedPiece(null);
        setInspectionPinned(false);
    }, [selectedRoomId]);

    useEffect(
        () => () => {
            if (simulationRun?.timerId) {
                window.clearTimeout(simulationRun.timerId);
            }
        },
        [simulationRun],
    );

    useEffect(
        () => () => {
            if (hoverFrameRef.current !== null) {
                window.cancelAnimationFrame(hoverFrameRef.current);
            }
        },
        [],
    );

    function pieceAtPointer(
        canvas: HTMLCanvasElement,
        clientX: number,
        clientY: number,
    ) {
        if (!state) {
            return null;
        }
        const rectangle = canvas.getBoundingClientRect();
        return hitTestFloorPiece(
            state,
            {width: rectangle.width, height: rectangle.height},
            {
                x: clientX - rectangle.left,
                y: clientY - rectangle.top,
            },
        );
    }

    function handleCanvasPointerMove(event: React.PointerEvent<HTMLCanvasElement>) {
        if (inspectionPinned || event.pointerType !== "mouse") {
            return;
        }
        if (hoverFrameRef.current !== null) {
            window.cancelAnimationFrame(hoverFrameRef.current);
        }
        const canvas = event.currentTarget;
        const {clientX, clientY} = event;
        hoverFrameRef.current = window.requestAnimationFrame(() => {
            const hit = pieceAtPointer(canvas, clientX, clientY);
            setInspectedPiece(current => current?.key === hit?.key ? current : hit);
            hoverFrameRef.current = null;
        });
    }

    function handleCanvasPointerDown(event: React.PointerEvent<HTMLCanvasElement>) {
        if (event.pointerType === "mouse") {
            return;
        }
        const hit = pieceAtPointer(
            event.currentTarget,
            event.clientX,
            event.clientY,
        );
        setInspectedPiece(hit);
        setInspectionPinned(Boolean(hit));
    }

    function handleCanvasKeyDown(event: React.KeyboardEvent<HTMLCanvasElement>) {
        const navigationKeys = [
            "ArrowRight",
            "ArrowDown",
            "ArrowLeft",
            "ArrowUp",
            "Escape",
        ];
        if (!state || !navigationKeys.includes(event.key)) {
            return;
        }
        event.preventDefault();
        if (event.key === "Escape") {
            setInspectedPiece(null);
            setInspectionPinned(false);
            return;
        }

        const pieces = inspectableFloorPieces(state);
        if (!pieces.length) {
            return;
        }
        const currentIndex = pieces.findIndex(
            piece => piece.key === inspectedPiece?.key,
        );
        const direction = event.key === "ArrowLeft" || event.key === "ArrowUp"
            ? -1
            : 1;
        const nextIndex = currentIndex < 0
            ? 0
            : (currentIndex + direction + pieces.length) % pieces.length;
        const rectangle = event.currentTarget.getBoundingClientRect();
        setInspectedPiece({
            ...pieces[nextIndex],
            anchor: {x: rectangle.width / 2, y: rectangle.height / 2},
        });
        setInspectionPinned(true);
    }

    function stopSimulation(preserveMessage = false) {
        setSimulationRun(current => {
            if (current?.timerId) {
                window.clearTimeout(current.timerId);
            }
            return null;
        });

        if (!preserveMessage) {
            setSimulationStatus("Simulation idle.");
        }
    }

    function selectRoom(roomId: string) {
        stopSimulation();
        setSelectedRoomId(roomId);
    }

    async function roomPost(
        action: string,
        payload: FormState | null = null,
    ) {
        if (!selectedRoomId) {
            return null;
        }

        const response = await fetch(
            `/api/room/${selectedRoomId}/${action}`,
            {
                method: "POST",
                headers: payload
                    ? {"Content-Type": "application/json"}
                    : {},
                body: payload ? JSON.stringify(payload) : null,
            },
        );
        const result = await response.json() as RoomActionResponse;

        if (!response.ok || result.ok === false) {
            throw new Error(result.error || "Action failed.");
        }

        return result;
    }

    async function handleApply(event: React.FormEvent) {
        event.preventDefault();
        stopSimulation();
        setValidationMessage("Working …");

        try {
            const result = await roomPost("apply", formState);
            if (result?.settings) {
                setFormState(
                    Object.fromEntries(
                        Object.entries(result.settings).map(([key, value]) => [
                            key,
                            String(value),
                        ]),
                    ),
                );
            }
            setValidationMessage("Settings applied.");
        } catch (error) {
            setValidationMessage(
                error instanceof Error ? error.message : "Action failed.",
            );
        }
    }

    async function handleReset() {
        stopSimulation();
        try {
            const result = await roomPost("reset");
            if (result?.settings) {
                setFormState(
                    Object.fromEntries(
                        Object.entries(result.settings).map(([key, value]) => [
                            key,
                            String(value),
                        ]),
                    ),
                );
            }
            setValidationMessage("Reset to saved JSON.");
        } catch (error) {
            setValidationMessage(
                error instanceof Error ? error.message : "Reset failed.",
            );
        }
    }

    async function handleSave() {
        try {
            const result = await roomPost("save", formState);
            setValidationMessage(result?.message || "Saved.");
        } catch (error) {
            setValidationMessage(
                error instanceof Error ? error.message : "Save failed.",
            );
        }
    }

    async function handleSimpleAction(action: "pause" | "resume" | "restart") {
        if (action === "restart") {
            stopSimulation();
        }
        try {
            await roomPost(action);
        } catch (error) {
            setValidationMessage(
                error instanceof Error ? error.message : "Action failed.",
            );
        }
    }

    async function handleRestartAll() {
        stopSimulation();
        try {
            await fetch("/api/restart-all", {method: "POST"});
        } catch (error) {
            setValidationMessage(
                error instanceof Error ? error.message : "Restart failed.",
            );
        }
    }

    function runSimulationTick(total: number, roomId: string, stepIndexByKey: Map<string, number>) {
        setSimulationRun(current => {
            if (!current || current.roomId !== roomId) {
                return current;
            }

            const room = roomById(state, roomId);
            const steps = buildSimulationSteps(state, room);
            const currentStep = steps[current.activeIndex];

            if (!currentStep) {
                setSimulationStatus("Simulation finished.");
                return null;
            }

            setSimulationStatus(
                `Simulating ${current.activeIndex + 1}/${total}: row ${currentStep.row}, board ${boardOrderLabel(currentStep.anchor)}.`,
            );

            if (current.activeIndex + 1 >= total) {
                window.setTimeout(() => {
                    setSimulationStatus(
                        `Simulation finished: ${total} board placements shown.`,
                    );
                    setSimulationRun(previous => {
                        if (previous?.timerId) {
                            window.clearTimeout(previous.timerId);
                        }
                        return null;
                    });
                }, Math.max(50, Number(simulationDelayMs) || 400));
                return current;
            }

            const timerId = window.setTimeout(() => {
                setSimulationRun(previous => {
                    if (!previous || previous.roomId !== roomId) {
                        return previous;
                    }

                    return {
                        ...previous,
                        activeIndex: previous.activeIndex + 1,
                    };
                });
            }, Math.max(50, Number(simulationDelayMs) || 400));

            return {
                roomId,
                activeIndex: current.activeIndex,
                stepIndexByKey,
                total,
                timerId,
            };
        });
    }

    useEffect(() => {
        if (!simulationRun) {
            return;
        }

        const {roomId, stepIndexByKey, total} = simulationRun;
        runSimulationTick(total, roomId, stepIndexByKey);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [simulationRun?.activeIndex]);

    function handleSimulate() {
        if (!selectedRoom || !state) {
            setSimulationStatus("No room selected.");
            return;
        }

        const steps = buildSimulationSteps(state, selectedRoom);
        if (!steps.length) {
            stopSimulation(true);
            setSimulationStatus(
                "No finished layout is available to simulate yet.",
            );
            return;
        }

        stopSimulation(true);
        setSimulationRun({
            roomId: selectedRoom.id,
            activeIndex: 0,
            stepIndexByKey: new Map(
                steps.map((step, index) => [step.key, index]),
            ),
            timerId: null,
            total: steps.length,
        });
    }

    const status = selectedRoom
        ? statusForRoom(state, selectedRoom)
        : {text: "Connecting …", kind: "idle"};
    const connection = selectedRoom
        ? continuousConnectionForRoom(state, selectedRoom.id)
        : null;
    const candidate = candidateForRoom(state, selectedRoom);
    const progressValue = connection?.continuous?.running
        ? Math.max(
            0,
            Math.min(100, Number(connection.continuous.profile.percent || 0)),
        )
        : connection?.continuous?.finished
            ? 100
            : Number(candidate?.attempt || 0);
    const progressMax = connection?.continuous?.running
        ? 100
        : connection?.continuous?.finished
            ? 100
            : Math.max(1, Number(candidate?.total_attempts || 1));

    return (
        <div className="app-shell">
            <PlannerHeader
                projectName={state?.project_name}
                connectionStatus={connectionStatus}
                connectionError={connectionError}
                onRestartAll={() => void handleRestartAll()}
            />

            <main className="workspace">
                <section className="canvas-column">
                    <section className="hero-panel">
                        <div className="hero-copy">
                            <p className="eyebrow">Project Monitor</p>
                            <h2>{selectedRoom?.name || "Waiting for room data"}</h2>
                            <p className="hero-status">{status.text}</p>
                        </div>
                        <div className="hero-metrics">
                            <article className="hero-metric">
                                <span className="hero-label">Direction</span>
                                <strong>
                                    {titleCaseWords(selectedRoom?.settings.orientation)}
                                </strong>
                            </article>
                            <article className="hero-metric">
                                <span className="hero-label">Start Corner</span>
                                <strong>
                                    {titleCaseWords(selectedRoom?.settings.start_corner)}
                                </strong>
                            </article>
                            <article className="hero-metric">
                                <span className="hero-label">Progress</span>
                                <strong>
                                    {`${Math.round(progressValue)}/${Math.round(progressMax)}`}
                                </strong>
                            </article>
                            <article className="hero-metric">
                                <span className="hero-label">Output</span>
                                <strong>{state?.output_dir || "–"}</strong>
                            </article>
                        </div>
                    </section>

                    <section className="canvas-card">
                        <div className="canvas-card-header">
                            <div>
                                <p className="eyebrow">Layout View</p>
                                <h2>Board field</h2>
                            </div>
                            <div className="canvas-header-tools">
                                <div className="simulation-controls">
                                    <label className="simulation-label" htmlFor="simulateDelayInput">
                                        Step delay
                                    </label>
                                    <input
                                        id="simulateDelayInput"
                                        min="50"
                                        step="50"
                                        type="number"
                                        value={simulationDelayMs}
                                        onChange={event => setSimulationDelayMs(event.target.value)}
                                    />
                                    <ActionButton
                                        id="simulateButton"
                                        className="action-button action-button-primary"
                                        onClick={handleSimulate}
                                        type="button"
                                    >
                                        Simulate
                                    </ActionButton>
                                    <ActionButton
                                        id="stopSimulationButton"
                                        className="action-button"
                                        onClick={() => stopSimulation()}
                                        type="button"
                                    >
                                        Stop
                                    </ActionButton>
                                </div>
                                <div className="legend-pillbar">
                                    <span className="legend-pill">
                                        <span className="legend-swatch legend-swatch-room"></span>
                                        Active room
                                    </span>
                                    <span className="legend-pill">
                                        <span className="legend-swatch legend-swatch-board"></span>
                                        Board labels
                                    </span>
                                    <span className="legend-pill">
                                        <span className="legend-swatch legend-swatch-short"></span>
                                        Short piece warning
                                    </span>
                                </div>
                            </div>
                        </div>
                        <div className="canvas-stage">
                            <canvas
                                id="floorCanvas"
                                ref={canvasRef}
                                aria-describedby={inspectedPiece ? "boardInspection" : undefined}
                                aria-label="Floor plan. Use arrow keys to inspect board pieces."
                                onBlur={() => {
                                    setInspectedPiece(null);
                                    setInspectionPinned(false);
                                }}
                                onKeyDown={handleCanvasKeyDown}
                                onPointerDown={handleCanvasPointerDown}
                                onPointerLeave={() => {
                                    if (hoverFrameRef.current !== null) {
                                        window.cancelAnimationFrame(hoverFrameRef.current);
                                        hoverFrameRef.current = null;
                                    }
                                    if (!inspectionPinned) {
                                        setInspectedPiece(null);
                                    }
                                }}
                                onPointerMove={handleCanvasPointerMove}
                                tabIndex={0}
                            ></canvas>
                            {inspectedPiece && (
                                <BoardInspection inspection={inspectedPiece} />
                            )}
                            <div className="canvas-overlay">
                                <p className="overlay-title">How to read the view</p>
                                <p className="overlay-copy">
                                    Each placement shows board order and laying direction.
                                    Use simulation to rehearse the finished layout.
                                </p>
                                <p
                                    id="simulationStatus"
                                    className="overlay-copy overlay-copy-strong"
                                >
                                    {simulationStatus}
                                </p>
                            </div>
                        </div>
                    </section>
                </section>
                <aside className="control-column">
                    <RoomNavigator
                        rooms={state?.rooms || []}
                        selectedRoomId={selectedRoomId}
                        onSelectRoom={selectRoom}
                    />
                    <Nav
                        aria-label="Planner controls"
                        className="control-tabs"
                        fill
                        variant="tabs"
                    >
                        <Nav.Item>
                            <Nav.Link
                                active={activePanel === 0}
                                onClick={() => setActivePanel(0)}
                            >
                                Overview
                            </Nav.Link>
                        </Nav.Item>
                        <Nav.Item>
                            <Nav.Link
                                active={activePanel === 1}
                                onClick={() => setActivePanel(1)}
                            >
                                Room settings
                            </Nav.Link>
                        </Nav.Item>
                    </Nav>
                    {activePanel === 0 && (
                        <div className="control-panel-stack">

                    <section className="panel panel-status">
                        <div className="panel-header">
                            <div>
                                <p className="eyebrow">Control Deck</p>
                                <h2>Status & actions</h2>
                            </div>
                            <span className="status-badge" data-state={status.kind} id="statusBadge">
                                {titleCaseWords(status.kind)}
                            </span>
                        </div>
                        <p className="status-text" data-state={status.kind} id="statusText">
                            {status.text}
                        </p>
                        <progress id="progressBar" max={progressMax} value={progressValue}></progress>
                        <div className="room-actions">
                            <ActionButton
                                className="action-button"
                                id="pauseButton"
                                onClick={() => void handleSimpleAction("pause")}
                                type="button"
                            >
                                Pause
                            </ActionButton>
                            <ActionButton
                                className="action-button"
                                id="resumeButton"
                                onClick={() => void handleSimpleAction("resume")}
                                type="button"
                            >
                                Resume
                            </ActionButton>
                            <ActionButton
                                className="action-button action-button-strong"
                                id="restartButton"
                                onClick={() => void handleSimpleAction("restart")}
                                type="button"
                            >
                                Restart room
                            </ActionButton>
                        </div>
                    </section>

                    <section className="panel panel-metrics">
                        <div className="panel-header">
                            <div>
                                <p className="eyebrow">Solver Snapshot</p>
                                <h2>Best solution</h2>
                            </div>
                        </div>
                        <div id="bestStats">
                            {candidate
                                ? <MetricRows rows={[
                                    [
                                        "Attempt",
                                        candidate.attempt !== undefined
                                            ? `${candidate.attempt} / ${candidate.total_attempts}`
                                            : "–",
                                    ],
                                    [
                                        "Start offset",
                                        `${formatNumber(candidate.base_offset)} mm`,
                                    ],
                                    [
                                        "First row cut",
                                        `${formatNumber(candidate.row_width_offset)} mm`,
                                    ],
                                    [
                                        "Short pieces",
                                        formatNumber(candidate.short_count),
                                    ],
                                    [
                                        "Shortest piece",
                                        `${formatNumber(candidate.shortest_piece)} mm`,
                                    ],
                                    [
                                        "Joint violations",
                                        formatNumber(candidate.joint_violations),
                                    ],
                                    [
                                        "Narrowest row",
                                        `${formatNumber(candidate.narrowest_row_width)} mm`,
                                    ],
                                    [
                                        "Physical boards",
                                        formatNumber(candidate.material_metrics?.new_boards),
                                    ],
                                    [
                                        "Exact offcut reuses",
                                        formatNumber(candidate.material_metrics?.exact_offcut_reuses),
                                    ],
                                    [
                                        "Trimmed offcut reuses",
                                        formatNumber(candidate.material_metrics?.trimmed_offcut_reuses),
                                    ],
                                    [
                                        "Saw cuts",
                                        formatNumber(candidate.material_metrics?.cuts),
                                    ],
                                ]} />
                                : "–"}
                        </div>
                    </section>

                    <section className="panel panel-metrics">
                        <div className="panel-header">
                            <div>
                                <p className="eyebrow">Runtime Telemetry</p>
                                <h2>Profiling</h2>
                            </div>
                        </div>
                        <div id="profileStats">
                            {selectedRoom?.profile
                                ? <MetricRows rows={[
                                    ["Phase", selectedRoom.profile.phase || "–"],
                                    [
                                        "Progress",
                                        `${selectedRoom.profile.completed || 0} / ${selectedRoom.profile.total || 0}`,
                                    ],
                                    [
                                        "Rate",
                                        `${formatNumber(selectedRoom.profile.candidates_per_second, 1)}/s`,
                                    ],
                                    ["Estimated remaining", formatSeconds(selectedRoom.profile.eta_s)],
                                    ["Elapsed", formatSeconds(selectedRoom.profile.elapsed_s)],
                                    ["Workers", selectedRoom.profile.workers || 0],
                                ]} />
                                : "–"}
                        </div>
                    </section>

                    <section className="panel panel-output">
                        <div className="panel-header">
                            <div>
                                <p className="eyebrow">Artifacts</p>
                                <h2>Output path</h2>
                            </div>
                        </div>
                        <p className="output-path" id="outputFiles">
                            {state?.output_dir || "Generated per room when finished."}
                        </p>
                    </section>
                        </div>
                    )}

                    {activePanel === 1 && (
                    <section className="panel settings-card">
                        <div className="panel-header">
                            <div>
                                <p className="eyebrow">Room Tuning</p>
                                <h2>
                                    Settings for <span id="selectedRoomName">{selectedRoom?.name || "room"}</span>
                                </h2>
                            </div>
                        </div>
                        <form id="settingsForm" onSubmit={event => void handleApply(event)}>
                            <div className="form-row">
                                <label>
                                    Laying direction
                                    <select
                                        name="orientation"
                                        onChange={event => setFormState(current => ({
                                            ...current,
                                            orientation: event.target.value,
                                        }))}
                                        value={setIfPresent(formState, "orientation")}
                                    >
                                        <option value="horizontal">Horizontal</option>
                                        <option value="vertical">Vertical</option>
                                    </select>
                                </label>
                                <label>
                                    Start corner
                                    <select
                                        name="start_corner"
                                        onChange={event => setFormState(current => ({
                                            ...current,
                                            start_corner: event.target.value,
                                        }))}
                                        value={setIfPresent(formState, "start_corner")}
                                    >
                                        <option value="upper_left">Upper left</option>
                                        <option value="upper_right">Upper right</option>
                                        <option value="lower_left">Lower left</option>
                                        <option value="lower_right">Lower right</option>
                                    </select>
                                </label>
                            </div>

                            <div className="form-grid">
                                {[
                                    ["expansion_gap_mm", "Expansion gap (mm)"],
                                    ["minimum_piece_length_mm", "Minimum piece (mm)"],
                                    ["minimum_joint_distance_mm", "Minimum joint distance (mm)"],
                                    ["stagger_step_mm", "Stagger step (mm)"],
                                ].map(([name, label]) => (
                                    <label key={name}>
                                        {label}
                                        <input
                                            name={name}
                                            onChange={event => setFormState(current => ({
                                                ...current,
                                                [name]: event.target.value,
                                            }))}
                                            type="number"
                                            value={formState[name] || ""}
                                        />
                                    </label>
                                ))}
                            </div>

                            <details>
                                <summary>Advanced layout parameters</summary>
                                <div className="form-grid form-grid-advanced">
                                    {[
                                        ["board_length_mm", "Board length (mm)"],
                                        ["board_width_mm", "Board width (mm)"],
                                        ["saw_kerf_mm", "Saw kerf (mm)"],
                                        ["optimization_step_mm", "Search step (mm)"],
                                        ["row_width_optimization_step_mm", "Row width step (mm)"],
                                        ["minimum_row_width_mm", "Absolute min. row width (mm)"],
                                        [
                                            "preferred_minimum_row_width_mm",
                                            "Preferred min. row width (mm)",
                                        ],
                                        ["optimizer_workers", "Optimizer workers"],
                                        ["preview_every_n_results", "Preview cadence"],
                                        ["local_optimize_top_n", "Local optimize top N"],
                                        ["frame_delay_ms", "Preview delay (ms)"],
                                    ].map(([name, label]) => (
                                        <label key={name}>
                                            {label}
                                            <input
                                                name={name}
                                                onChange={event => setFormState(current => ({
                                                    ...current,
                                                    [name]: event.target.value,
                                                }))}
                                                step="any"
                                                type="number"
                                                value={formState[name] || ""}
                                            />
                                        </label>
                                    ))}
                                </div>
                            </details>

                            <div className="form-actions">
                                <ActionButton className="action-button action-button-primary" type="submit">
                                    Apply settings
                                </ActionButton>
                                <ActionButton
                                    className="action-button"
                                    id="saveConfigButton"
                                    onClick={() => void handleSave()}
                                    type="button"
                                >
                                    Save to JSON
                                </ActionButton>
                                <ActionButton
                                    className="action-button"
                                    id="resetConfigButton"
                                    onClick={() => void handleReset()}
                                    type="button"
                                >
                                    Reset
                                </ActionButton>
                            </div>
                            <p className="form-message" id="validationMessage">
                                {validationMessage}
                            </p>
                        </form>
                    </section>
                    )}
                </aside>
            </main>
        </div>
    );
}

export default PlannerPage;
