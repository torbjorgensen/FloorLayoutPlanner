const canvas = document.getElementById("floorCanvas");
const context = canvas.getContext("2d");

const roomSelect = document.getElementById("roomSelect");
const roomTabs = document.getElementById("roomTabs");
const settingsForm = document.getElementById("settingsForm");
const selectedRoomName = document.getElementById("selectedRoomName");
const statusText = document.getElementById("statusText");
const statusBadge = document.getElementById("statusBadge");
const progressBar = document.getElementById("progressBar");
const bestStats = document.getElementById("bestStats");
const outputFiles = document.getElementById("outputFiles");
const profileStats = document.getElementById("profileStats");
const validationMessage = document.getElementById("validationMessage");
const summaryRoomName = document.getElementById("summaryRoomName");
const summaryStatusText = document.getElementById("summaryStatusText");
const summaryDirection = document.getElementById("summaryDirection");
const summaryStartCorner = document.getElementById("summaryStartCorner");
const summaryProgress = document.getElementById("summaryProgress");
const summaryOutput = document.getElementById("summaryOutput");
const simulateDelayInput = document.getElementById("simulateDelayInput");
const simulateButton = document.getElementById("simulateButton");
const stopSimulationButton = document.getElementById("stopSimulationButton");
const simulationStatus = document.getElementById("simulationStatus");

const POLL_INTERVAL_MS = 500;

let latestState = null;
let selectedRoomId = null;
let formRoomId = null;
let refreshInProgress = false;
let renderedPieceHitboxes = [];
let hoveredPieceKey = null;
let hoveredPhysicalBoardId = null;
let hoverTooltip = null;
let simulationRun = null;


function selectedRoom() {
    return (
        latestState?.rooms?.find(
            room => room.id === selectedRoomId,
        ) || null
    );
}


function titleCaseWords(value) {
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


function setSimulationStatus(message) {
    if (simulationStatus) {
        simulationStatus.textContent = message;
    }
}


function setText(element, value) {
    if (element) {
        element.textContent = value;
    }
}


function syncRoomTabs() {
    if (!roomTabs) {
        return;
    }

    for (const button of roomTabs.querySelectorAll(".room-tab")) {
        button.classList.toggle(
            "is-active",
            button.dataset.roomId === selectedRoomId,
        );
    }
}


function selectRoom(roomId) {
    stopSimulation();
    selectedRoomId = roomId;
    formRoomId = null;
    roomSelect.value = roomId;
    syncRoomTabs();
    updateSidePanel();
    draw();
}


function roomById(roomId) {
    return (
        latestState?.rooms?.find(
            room => room.id === roomId,
        ) || null
    );
}


function continuousConnectionForRoom(roomId) {
    return (
        latestState?.connections?.find(
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


function hasSplitRoomPieces(connection) {
    const roomPieces = connection?.continuous?.room_pieces;

    return Boolean(
        roomPieces
        && Object.keys(roomPieces).length > 0,
    );
}


function candidateForRoom(room) {
    if (!room) {
        return null;
    }

    const connection = continuousConnectionForRoom(room.id);
    const splitPieces =
        connection?.continuous?.room_pieces?.[room.id];

    if (Array.isArray(splitPieces) && splitPieces.length > 0) {
        const sharedCandidate =
            connection.continuous.candidate;

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


function roomPiecesForSimulation(room) {
    if (!room) {
        return null;
    }

    const connection = continuousConnectionForRoom(room.id);
    const splitPieces =
        connection?.continuous?.room_pieces?.[room.id];

    if (Array.isArray(splitPieces) && splitPieces.length > 0) {
        return {
            pieces: splitPieces,
            boardScope: `connection:${connection.id}`,
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


function boardRowIdentity(piece, boardScope) {
    return [
        scopedBoardIdentity(piece, boardScope),
        piece.row,
    ].join(":");
}


function resizeCanvas() {
    const ratio = window.devicePixelRatio || 1;
    const rectangle = canvas.getBoundingClientRect();

    canvas.width = Math.max(
        1,
        Math.floor(rectangle.width * ratio),
    );
    canvas.height = Math.max(
        1,
        Math.floor(rectangle.height * ratio),
    );

    context.setTransform(
        ratio,
        0,
        0,
        ratio,
        0,
        0,
    );

    draw();
}


window.addEventListener("resize", resizeCanvas);


function populateRoomSelect() {
    if (!latestState?.rooms) {
        return;
    }

    roomSelect.innerHTML = "";

    for (const room of latestState.rooms) {
        const option = document.createElement("option");
        option.value = room.id;
        option.textContent = room.name;
        roomSelect.appendChild(option);
    }

    if (
        !selectedRoomId
        || !latestState.rooms.some(
            room => room.id === selectedRoomId,
        )
    ) {
        selectedRoomId =
            latestState.rooms[0]?.id || null;
    }

    roomSelect.value = selectedRoomId;
    populateRoomTabs();
}


function populateRoomTabs() {
    if (!roomTabs || !latestState?.rooms) {
        return;
    }

    roomTabs.innerHTML = "";

    for (const room of latestState.rooms) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "room-tab";
        button.dataset.roomId = room.id;

        const orientation = titleCaseWords(
            room.settings?.orientation || "–",
        );
        const startCorner = titleCaseWords(
            room.settings?.start_corner || "upper_left",
        );

        button.innerHTML = `
            <span class="room-tab-title">${room.name}</span>
            <span class="room-tab-meta">${orientation} · ${startCorner}</span>
        `;
        button.addEventListener("click", () => selectRoom(room.id));
        roomTabs.appendChild(button);
    }

    syncRoomTabs();
}


roomSelect.addEventListener("change", () => {
    selectRoom(roomSelect.value);
});


function fillForm(room) {
    if (!room) {
        return;
    }

    for (
        const [name, value]
        of Object.entries(room.settings || {})
    ) {
        const field =
            settingsForm.elements.namedItem(name);

        if (field) {
            field.value = value;
        }
    }

    formRoomId = room.id;
}


function formPayload() {
    return Object.fromEntries(
        new FormData(settingsForm).entries(),
    );
}


function formatNumber(value, decimals = 0) {
    const number = Number(value);

    if (!Number.isFinite(number)) {
        return "–";
    }

    return number.toFixed(decimals);
}


function formatSeconds(value) {
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


function metricRows(rows) {
    return `
        <div class="stat-grid">
            ${rows.map(
                ([label, value]) => `
                    <span>${label}</span>
                    <span>${value}</span>
                `,
            ).join("")}
        </div>
    `;
}


function statsHtml(candidate, connection = null) {
    if (!candidate) {
        return "–";
    }

    const rows = [
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
            "Locally adjusted rows",
            Object.keys(candidate.row_offsets || {}).length,
        ],
    ];

    const cut = connection?.continuous?.cut_plan;

    if (cut) {
        rows.push(
            [
                "Transition",
                cut.method === "natural_joint"
                    ? "Natural joint"
                    : "Saw-cut expansion gap",
            ],
            [
                "Gap position",
                `${formatNumber(cut.position_mm)} mm`,
            ],
            [
                "Gap",
                `${formatNumber(cut.gap_width_mm, 1)} mm`,
            ],
            [
                "Affected boards",
                formatNumber(cut.cut_boards),
            ],
            [
                "Shortest piece after cut",
                `${formatNumber(cut.shortest_fragment_mm)} mm`,
            ],
        );
    }

    return metricRows(rows);
}


function profileHtml(profile) {
    if (!profile) {
        return "–";
    }

    const timings = profile.timing_totals || {};

    return metricRows([
        ["Phase", profile.phase || "–"],
        [
            "Progress",
            `${profile.completed || 0} / ${profile.total || 0}`,
        ],
        [
            "Rate",
            `${formatNumber(profile.candidates_per_second, 1)}/s`,
        ],
        ["Estimated remaining", formatSeconds(profile.eta_s)],
        ["Elapsed", formatSeconds(profile.elapsed_s)],
        ["Workers", profile.workers || 0],
        [
            "Coarse search",
            `${profile.coarse_completed || 0} / ${profile.coarse_total || 0}`,
        ],
        [
            "Refinement",
            `${profile.refine_completed || 0} / ${profile.refine_total || 0}`,
        ],
        [
            "Plan generation",
            formatSeconds(timings.plan_generation_s || 0),
        ],
        [
            "Local optimization",
            formatSeconds(
                timings.local_optimization_s || 0,
            ),
        ],
        [
            "Scoring",
            formatSeconds(timings.final_scoring_s || 0),
        ],
        [
            "Local variants tested",
            profile.local_variants || 0,
        ],
    ]);
}


function statusForRoom(room) {
    const connection =
        continuousConnectionForRoom(room.id);
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


function updateProgress(room, connection) {
    const continuous = connection?.continuous;
    const progress = continuous?.profile;

    if (continuous?.running && progress) {
        progressBar.max = 100;
        progressBar.value = Math.max(
            0,
            Math.min(100, Number(progress.percent || 0)),
        );
        return;
    }

    if (continuous?.finished) {
        progressBar.max = 100;
        progressBar.value = 100;
        return;
    }

    const candidate = room.current || room.best;

    if (candidate) {
        progressBar.max = Math.max(
            1,
            Number(candidate.total_attempts || 1),
        );
        progressBar.value = Math.min(
            progressBar.max,
            Number(candidate.attempt || 0),
        );
        return;
    }

    progressBar.max = 1;
    progressBar.value = 0;
}


function updateSidePanel() {
    const room = selectedRoom();

    if (!room) {
        return;
    }

    const connection =
        continuousConnectionForRoom(room.id);
    const status = statusForRoom(room);
    const candidate = candidateForRoom(room);
    const orientation = titleCaseWords(
        room.settings?.orientation,
    );
    const startCorner = titleCaseWords(
        room.settings?.start_corner,
    );

    selectedRoomName.textContent = room.name;

    if (formRoomId !== room.id) {
        fillForm(room);
    }

    statusText.textContent = status.text;
    statusText.dataset.state = status.kind;
    statusBadge.textContent = titleCaseWords(status.kind);
    statusBadge.dataset.state = status.kind;
    setText(summaryRoomName, room.name);
    setText(summaryStatusText, status.text);
    setText(summaryDirection, orientation);
    setText(summaryStartCorner, startCorner);
    setText(
        summaryOutput,
        latestState?.output_dir || "–",
    );

    bestStats.innerHTML =
        statsHtml(candidate, connection);

    profileStats.innerHTML =
        profileHtml(room.profile);

    updateProgress(room, connection);

    outputFiles.textContent =
        latestState?.output_dir || "–";
    setText(
        summaryProgress,
        `${Math.round(progressBar.value)}/${Math.round(progressBar.max)}`,
    );
}


async function roomPost(action, payload = null) {
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
            body: payload
                ? JSON.stringify(payload)
                : null,
        },
    );

    const result = await response.json();

    if (!response.ok || result.ok === false) {
        throw new Error(
            result.error || "Action failed.",
        );
    }

    return result;
}


settingsForm.addEventListener(
    "submit",
    async event => {
        event.preventDefault();
        stopSimulation();
        validationMessage.textContent = "Working …";
        validationMessage.className = "form-message";

        try {
            const result = await roomPost(
                "apply",
                formPayload(),
            );

            validationMessage.textContent =
                "Settings applied.";
            validationMessage.className =
                "form-message success";

            if (result?.settings) {
                for (
                    const [name, value]
                    of Object.entries(result.settings)
                ) {
                    const field =
                        settingsForm.elements.namedItem(name);

                    if (field) {
                        field.value = value;
                    }
                }
            }
        } catch (error) {
            validationMessage.textContent =
                error.message;
            validationMessage.className =
                "form-message error";
        }
    },
);


document
    .getElementById("saveConfigButton")
    .addEventListener("click", async () => {
        try {
            const result = await roomPost(
                "save",
                formPayload(),
            );

            validationMessage.textContent =
                result?.message || "Saved.";
            validationMessage.className =
                "form-message success";
        } catch (error) {
            validationMessage.textContent =
                error.message;
            validationMessage.className =
                "form-message error";
        }
    });


document
    .getElementById("resetConfigButton")
    .addEventListener("click", async () => {
        stopSimulation();
        try {
            const result = await roomPost("reset");

            if (result?.settings) {
                for (
                    const [name, value]
                    of Object.entries(result.settings)
                ) {
                    const field =
                        settingsForm.elements.namedItem(name);

                    if (field) {
                        field.value = value;
                    }
                }
            }

            validationMessage.textContent =
                "Reset to saved JSON.";
            validationMessage.className =
                "form-message success";
        } catch (error) {
            validationMessage.textContent =
                error.message;
            validationMessage.className =
                "form-message error";
        }
    });


document
    .getElementById("pauseButton")
    .addEventListener(
        "click",
        () => roomPost("pause"),
    );


document
    .getElementById("resumeButton")
    .addEventListener(
        "click",
        () => roomPost("resume"),
    );


document
    .getElementById("restartButton")
    .addEventListener(
        "click",
        () => {
            stopSimulation();
            return roomPost("restart");
        },
    );


document
    .getElementById("restartAllButton")
    .addEventListener(
        "click",
        async () => {
            stopSimulation();
            await fetch(
                "/api/restart-all",
                {method: "POST"},
            );
        },
    );


simulateButton.addEventListener("click", () => {
    startSimulation();
});


stopSimulationButton.addEventListener("click", () => {
    stopSimulation();
});


function colorWithAlpha(color, alpha) {
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

    const red = parseInt(
        normalized.slice(0, 2),
        16,
    );
    const green = parseInt(
        normalized.slice(2, 4),
        16,
    );
    const blue = parseInt(
        normalized.slice(4, 6),
        16,
    );

    return `rgba(${red},${green},${blue},${alpha})`;
}


function projectTransform() {
    const width = canvas.clientWidth;
    const height = canvas.clientHeight;
    const bounds = latestState.bounds;

    const projectWidth = Math.max(
        1,
        bounds.max_x - bounds.min_x,
    );
    const projectHeight = Math.max(
        1,
        bounds.max_y - bounds.min_y,
    );
    const margin = 30;

    const scale = Math.min(
        (width - 2 * margin) / projectWidth,
        (height - 2 * margin) / projectHeight,
    );

    return {
        scale,
        x: value =>
            margin
            + (value - bounds.min_x) * scale,
        y: value =>
            margin
            + (value - bounds.min_y) * scale,
    };
}


function drawRoomBackgrounds(x, y, scale) {
    for (const room of latestState.rooms) {
        const selected =
            room.id === selectedRoomId;

        for (const rectangle of room.rectangles) {
            context.fillStyle = colorWithAlpha(
                rectangle.fill_color
                    || (
                        selected
                            ? "#dbeafe"
                            : "#eeeeee"
                    ),
                rectangle.fill_alpha
                    ?? (
                        selected
                            ? 0.22
                            : 0.10
                    ),
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


function drawPassageBackgrounds(x, y, scale) {
    for (
        const connection
        of latestState.connections || []
    ) {
        const passage = connection.passage;

        if (
            connection.type !== "continuous_then_cut"
            || !passage
        ) {
            continue;
        }

        context.save();
        context.fillStyle =
            "rgba(115, 115, 115, 0.10)";
        context.fillRect(
            x(passage.x),
            y(passage.y),
            passage.width * scale,
            passage.height * scale,
        );
        context.strokeStyle =
            "rgba(60, 60, 60, 0.55)";
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


function drawFloorPieces(x, y, scale) {
    const renderedByContinuous =
        new Set();

    for (
        const connection
        of latestState.connections || []
    ) {
        if (
            connection.type !== "continuous_then_cut"
            || !hasSplitRoomPieces(connection)
        ) {
            continue;
        }

        for (
            const [roomId, pieces]
            of Object.entries(
                connection.continuous.room_pieces,
            )
        ) {
            const room = roomById(roomId);

            drawPieces(
                pieces,
                room?.minimum_piece_length || 0,
                roomId === selectedRoomId,
                x,
                y,
                scale,
                roomId,
                `connection:${connection.id}`,
            );

            renderedByContinuous.add(roomId);
        }
    }

    for (const room of latestState.rooms) {
        if (renderedByContinuous.has(room.id)) {
            continue;
        }

        const candidate =
            room.current || room.best;

        if (!candidate) {
            continue;
        }

        drawPieces(
            candidate.pieces,
            room.minimum_piece_length,
            room.id === selectedRoomId,
            x,
            y,
            scale,
            room.id,
            `room:${room.id}`,
        );
    }
}


function drawTransition(connection, x, y, scale) {
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
        cut.axis === "y"
            ? passage.height
            : passage.width,
        Math.max(
            cut.gap_width_mm + 24,
            35,
        ),
    );

    context.fillStyle =
        "rgba(130, 92, 52, 0.28)";

    if (cut.axis === "y") {
        context.fillRect(
            x(passage.x),
            y(
                cut.position_mm
                - thresholdWidthMm / 2,
            ),
            passage.width * scale,
            Math.max(
                4,
                thresholdWidthMm * scale,
            ),
        );
    } else {
        context.fillRect(
            x(
                cut.position_mm
                - thresholdWidthMm / 2,
            ),
            y(passage.y),
            Math.max(
                4,
                thresholdWidthMm * scale,
            ),
            passage.height * scale,
        );
    }

    context.fillStyle =
        cut.method === "natural_joint"
            ? "#1b8f3a"
            : "#202020";

    if (cut.axis === "y") {
        context.fillRect(
            x(passage.x),
            y(
                cut.position_mm
                - cut.gap_width_mm / 2,
            ),
            passage.width * scale,
            Math.max(
                2,
                cut.gap_width_mm * scale,
            ),
        );
    } else {
        context.fillRect(
            x(
                cut.position_mm
                - cut.gap_width_mm / 2,
            ),
            y(passage.y),
            Math.max(
                2,
                cut.gap_width_mm * scale,
            ),
            passage.height * scale,
        );
    }

    context.fillStyle = "#111";
    context.font = "600 12px sans-serif";

    const label =
        cut.method === "natural_joint"
            ? "Natural joint"
            : `Saw cut - ${cut.cut_boards} boards`;

    context.fillText(
        label,
        x(passage.x) + 6,
        y(passage.y) - 7,
    );

    context.restore();
}


function drawTransitions(x, y, scale) {
    for (
        const connection
        of latestState.connections || []
    ) {
        if (
            connection.type ===
            "continuous_then_cut"
        ) {
            drawTransition(
                connection,
                x,
                y,
                scale,
            );
        }
    }
}


function drawRoomOutlines(x, y) {
    for (const room of latestState.rooms) {
        const selected =
            room.id === selectedRoomId;

        context.beginPath();

        room.outline.forEach(
            (point, index) => {
                if (index === 0) {
                    context.moveTo(
                        x(point[0]),
                        y(point[1]),
                    );
                } else {
                    context.lineTo(
                        x(point[0]),
                        y(point[1]),
                    );
                }
            },
        );

        context.strokeStyle = selected
            ? "#1a73e8"
            : "#111";
        context.lineWidth = selected
            ? 4
            : 2;
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


function draw() {
    renderedPieceHitboxes = [];

    const width = canvas.clientWidth;
    const height = canvas.clientHeight;

    context.clearRect(
        0,
        0,
        width,
        height,
    );

    if (!latestState?.rooms?.length) {
        return;
    }

    const {x, y, scale} =
        projectTransform();

    drawRoomBackgrounds(x, y, scale);
    drawPassageBackgrounds(x, y, scale);
    drawFloorPieces(x, y, scale);
    drawTransitions(x, y, scale);
    drawRoomOutlines(x, y);
}


function pieceKey(
    piece,
    roomId = "",
    boardScope = "",
) {
    return [
        roomId,
        scopedBoardIdentity(piece, boardScope),
        piece.row,
        piece.segment,
        piece.piece,
        piece.x1,
        piece.y1,
        piece.x2,
        piece.y2,
    ].join(":");
}


function drawPieces(
    pieces,
    minimumPieceLength,
    selected,
    x,
    y,
    scale,
    roomId = "",
    boardScope = `room:${roomId}`,
) {
    const piecesByBoardRow = new Map();
    const boardRowAnchors = new Map();
    const room = roomById(roomId);

    for (const piece of pieces || []) {
        const boardRowKey = [
            scopedBoardIdentity(
                piece,
                boardScope,
            ),
            piece.row,
        ].join(":");
        const grouped =
            piecesByBoardRow.get(boardRowKey) || [];
        grouped.push(piece);
        piecesByBoardRow.set(
            boardRowKey,
            grouped,
        );

        const anchor =
            boardRowAnchors.get(boardRowKey);

        if (!anchor || piece.length * piece.width > anchor.area) {
            boardRowAnchors.set(
                boardRowKey,
                {
                    piece,
                    area: piece.length * piece.width,
                },
            );
        }
    }

    for (const piece of pieces || []) {
        const isShort =
            minimumPieceLength > 0
            && piece.length < minimumPieceLength;
        const key = pieceKey(
            piece,
            roomId,
            boardScope,
        );
        const scopedIdentity = scopedBoardIdentity(
            piece,
            boardScope,
        );
        const boardRowKey = [
            scopedIdentity,
            piece.row,
        ].join(":");
        const stepState = simulationStepState(
            piece,
            roomId,
            boardScope,
        );
        const sameSource =
            hoveredPhysicalBoardId !== null
            && scopedIdentity
                === hoveredPhysicalBoardId;
        const isHovered = key === hoveredPieceKey;

        if (stepState === "future") {
            context.fillStyle = isShort
                ? "rgba(255, 214, 214, 0.35)"
                : (
                    selected
                        ? "rgba(223, 242, 223, 0.34)"
                        : "rgba(237, 243, 237, 0.28)"
                );
            context.strokeStyle = "rgba(102, 122, 102, 0.55)";
            context.lineWidth = 1;
        } else if (stepState === "active") {
            context.fillStyle = isHovered
                ? "#ffd166"
                : "#ffefb0";
            context.strokeStyle = isHovered
                ? "#9a5a00"
                : "#ba7a00";
            context.lineWidth = isHovered ? 3 : 2.4;
        } else {
            context.fillStyle = isHovered
                ? "#ffe082"
                : sameSource
                    ? "#fff3bf"
                    : isShort
                        ? "#ffd6d6"
                        : (
                            selected
                                ? "#dff2df"
                                : "#edf3ed"
                        );

            context.strokeStyle = isHovered
                ? "#b26a00"
                : sameSource
                    ? "#d39e00"
                    : isShort
                        ? "#b00020"
                        : "#667a66";

            context.lineWidth = isHovered
                ? 3
                : sameSource
                    ? 2
                    : isShort
                        ? 2
                        : 0.8;
        }

        const screenX = x(piece.x1);
        const screenY = y(piece.y1);
        const screenWidth =
            (piece.x2 - piece.x1) * scale;
        const screenHeight =
            (piece.y2 - piece.y1) * scale;

        context.fillRect(
            screenX,
            screenY,
            screenWidth,
            screenHeight,
        );

        drawPieceOutline(
            piece,
            piecesByBoardRow.get(boardRowKey) || [],
            x,
            y,
            stepState,
        );

        renderedPieceHitboxes.push({
            key,
            roomId,
            boardScope,
            piece,
            x1: screenX,
            y1: screenY,
            x2: screenX + screenWidth,
            y2: screenY + screenHeight,
            minimumPieceLength,
        });
    }

    for (const [boardRowKey, anchor] of boardRowAnchors.entries()) {
        drawBoardAnnotation(
            anchor.piece,
            room,
            x,
            y,
            scale,
            simulationStepState(
                anchor.piece,
                roomId,
                boardScope,
            ),
        );
    }
}


function overlappingSegments(
    start,
    end,
    segments,
) {
    const clipped = segments
        .map(([segmentStart, segmentEnd]) => [
            Math.max(start, segmentStart),
            Math.min(end, segmentEnd),
        ])
        .filter(
            ([segmentStart, segmentEnd]) =>
                segmentEnd > segmentStart,
        )
        .sort(
            ([startA], [startB]) =>
                startA - startB,
        );

    if (!clipped.length) {
        return [];
    }

    const merged = [clipped[0]];

    for (const [segmentStart, segmentEnd] of clipped.slice(1)) {
        const current =
            merged[merged.length - 1];

        if (segmentStart <= current[1]) {
            current[1] = Math.max(
                current[1],
                segmentEnd,
            );
        } else {
            merged.push([
                segmentStart,
                segmentEnd,
            ]);
        }
    }

    return merged;
}


function visibleSegments(
    start,
    end,
    blocked,
) {
    const mergedBlocked =
        overlappingSegments(
            start,
            end,
            blocked,
        );
    const visible = [];
    let cursor = start;

    for (const [blockStart, blockEnd] of mergedBlocked) {
        if (blockStart > cursor) {
            visible.push([
                cursor,
                blockStart,
            ]);
        }
        cursor = Math.max(cursor, blockEnd);
    }

    if (cursor < end) {
        visible.push([cursor, end]);
    }

    return visible;
}


function drawVisibleLineSegments(
    segments,
    moveTo,
    lineTo,
) {
    for (const [segmentStart, segmentEnd] of segments) {
        context.beginPath();
        moveTo(segmentStart);
        lineTo(segmentEnd);
        context.stroke();
    }
}


function drawPieceOutline(
    piece,
    boardPieces,
    x,
    y,
    stepState = "inactive",
) {
    const epsilon = 1e-6;
    const topBlocked = [];
    const bottomBlocked = [];
    const leftBlocked = [];
    const rightBlocked = [];

    for (const otherPiece of boardPieces) {
        if (otherPiece === piece) {
            continue;
        }

        if (
            Math.abs(otherPiece.y2 - piece.y1) <= epsilon
        ) {
            topBlocked.push([
                otherPiece.x1,
                otherPiece.x2,
            ]);
        }

        if (
            Math.abs(otherPiece.y1 - piece.y2) <= epsilon
        ) {
            bottomBlocked.push([
                otherPiece.x1,
                otherPiece.x2,
            ]);
        }

        if (
            Math.abs(otherPiece.x2 - piece.x1) <= epsilon
        ) {
            leftBlocked.push([
                otherPiece.y1,
                otherPiece.y2,
            ]);
        }

        if (
            Math.abs(otherPiece.x1 - piece.x2) <= epsilon
        ) {
            rightBlocked.push([
                otherPiece.y1,
                otherPiece.y2,
            ]);
        }
    }

    context.save();

    if (stepState === "future") {
        context.setLineDash([6, 5]);
    }

    drawVisibleLineSegments(
        visibleSegments(
            piece.x1,
            piece.x2,
            topBlocked,
        ),
        segmentStart =>
            context.moveTo(
                x(segmentStart),
                y(piece.y1),
            ),
        segmentEnd =>
            context.lineTo(
                x(segmentEnd),
                y(piece.y1),
            ),
    );
    drawVisibleLineSegments(
        visibleSegments(
            piece.x1,
            piece.x2,
            bottomBlocked,
        ),
        segmentStart =>
            context.moveTo(
                x(segmentStart),
                y(piece.y2),
            ),
        segmentEnd =>
            context.lineTo(
                x(segmentEnd),
                y(piece.y2),
            ),
    );
    drawVisibleLineSegments(
        visibleSegments(
            piece.y1,
            piece.y2,
            leftBlocked,
        ),
        segmentStart =>
            context.moveTo(
                x(piece.x1),
                y(segmentStart),
            ),
        segmentEnd =>
            context.lineTo(
                x(piece.x1),
                y(segmentEnd),
            ),
    );
    drawVisibleLineSegments(
        visibleSegments(
            piece.y1,
            piece.y2,
            rightBlocked,
        ),
        segmentStart =>
            context.moveTo(
                x(piece.x2),
                y(segmentStart),
            ),
        segmentEnd =>
            context.lineTo(
                x(piece.x2),
                y(segmentEnd),
            ),
    );

    context.restore();
}


function layingVector(room) {
    const orientation =
        room?.settings?.orientation
        || "horizontal";
    const startCorner =
        room?.settings?.start_corner
        || "upper_left";

    if (orientation === "horizontal") {
        return startCorner.endsWith("right")
            ? {x: -1, y: 0}
            : {x: 1, y: 0};
    }

    return startCorner.startsWith("lower")
        ? {x: 0, y: -1}
        : {x: 0, y: 1};
}


function compareAlongDirection(first, second, room) {
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


function buildSimulationSteps(room) {
    const simulationPieces =
        roomPiecesForSimulation(room);

    if (!simulationPieces) {
        return [];
    }

    const stepsByBoardRow = new Map();

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


function simulationStepDelayMs() {
    const value = Number(simulateDelayInput?.value);

    if (!Number.isFinite(value)) {
        return 400;
    }

    return Math.max(50, Math.round(value));
}


function stopSimulation(options = {}) {
    const preserveMessage =
        options.preserveMessage || false;

    if (simulationRun?.timerId) {
        window.clearTimeout(simulationRun.timerId);
    }

    simulationRun = null;

    if (!preserveMessage) {
        setSimulationStatus("Simulation idle.");
    }

    draw();
}


function simulationStepState(
    piece,
    roomId,
    boardScope,
) {
    if (
        !simulationRun
        || simulationRun.roomId !== roomId
    ) {
        return "inactive";
    }

    const stepKey = boardRowIdentity(
        piece,
        boardScope,
    );
    const index =
        simulationRun.stepIndexByKey.get(stepKey);

    if (index === undefined) {
        return "inactive";
    }

    if (index < simulationRun.activeIndex) {
        return "completed";
    }

    if (index === simulationRun.activeIndex) {
        return "active";
    }

    return "future";
}


function startSimulation() {
    const room = selectedRoom();
    const steps = buildSimulationSteps(room);

    if (!room || !steps.length) {
        stopSimulation({preserveMessage: true});
        setSimulationStatus(
            "No finished layout is available to simulate yet.",
        );
        return;
    }

    stopSimulation({preserveMessage: true});

    simulationRun = {
        roomId: room.id,
        steps,
        activeIndex: 0,
        stepIndexByKey: new Map(
            steps.map((step, index) => [step.key, index]),
        ),
        timerId: null,
    };

    const delayMs = simulationStepDelayMs();

    const tick = () => {
        if (!simulationRun) {
            return;
        }

        const currentStep =
            simulationRun.steps[
                simulationRun.activeIndex
            ];
        const currentNumber =
            simulationRun.activeIndex + 1;
        const total =
            simulationRun.steps.length;

        setSimulationStatus(
            `Simulating ${currentNumber}/${total}: row ${currentStep.row}, board ${boardOrderLabel(currentStep.anchor)}.`,
        );
        draw();

        if (currentNumber >= total) {
            setSimulationStatus(
                `Simulation finished: ${total} board placements shown.`,
            );
            simulationRun = null;
            draw();
            return;
        }

        simulationRun.timerId =
            window.setTimeout(() => {
                if (!simulationRun) {
                    return;
                }

                simulationRun.activeIndex += 1;
                tick();
            }, delayMs);
    };

    tick();
}


function boardOrderLabel(piece) {
    const boardIndex = Number(piece.source_board_index);

    if (Number.isFinite(boardIndex)) {
        return `${boardIndex}`;
    }

    const match = String(piece.physical_board_id || "").match(/(\d+)/);

    return match ? match[1] : "?";
}


function drawArrowHead(
    tipX,
    tipY,
    directionX,
    directionY,
    size,
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
    piece,
    room,
    x,
    y,
    scale,
    stepState = "inactive",
) {
    const screenX = x(piece.x1);
    const screenY = y(piece.y1);
    const screenWidth =
        (piece.x2 - piece.x1) * scale;
    const screenHeight =
        (piece.y2 - piece.y1) * scale;

    if (
        screenWidth < 34
        || screenHeight < 16
    ) {
        return;
    }

    if (stepState === "future") {
        return;
    }

    const direction = layingVector(room);
    const label = boardOrderLabel(piece);
    const horizontal =
        Math.abs(direction.x) > 0;
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

    const textMetrics = context.measureText(label);
    const textWidth = textMetrics.width;
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
    const arrowLength = Math.max(
        0,
        Math.min(availableLength, 22),
    );

    context.fillStyle = stepState === "active"
        ? "rgba(255, 248, 220, 0.96)"
        : "rgba(255, 255, 255, 0.82)";
    context.strokeStyle = stepState === "active"
        ? "rgba(154, 90, 0, 0.88)"
        : "rgba(17, 24, 39, 0.72)";
    context.lineWidth = 1;
    context.beginPath();
    context.roundRect(
        chipX,
        chipY,
        chipWidth,
        chipHeight,
        6,
    );
    context.fill();
    context.stroke();

    context.fillStyle = stepState === "active"
        ? "rgba(120, 66, 18, 0.95)"
        : "rgba(17, 24, 39, 0.92)";
    context.fillText(
        label,
        centerX,
        centerY,
    );

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
        context.moveTo(
            arrowStartX,
            arrowStartY,
        );
        context.lineTo(
            arrowEndX,
            arrowEndY,
        );
        context.stroke();
        drawArrowHead(
            arrowEndX,
            arrowEndY,
            direction.x,
            direction.y,
            5,
        );
    }

    context.restore();
}


function ensureHoverTooltip() {
    if (hoverTooltip) {
        return hoverTooltip;
    }

    hoverTooltip = document.createElement("div");
    hoverTooltip.id = "boardHoverTooltip";
    hoverTooltip.style.position = "fixed";
    hoverTooltip.style.zIndex = "1000";
    hoverTooltip.style.pointerEvents = "none";
    hoverTooltip.style.display = "none";
    hoverTooltip.style.maxWidth = "280px";
    hoverTooltip.style.padding = "9px 11px";
    hoverTooltip.style.borderRadius = "8px";
    hoverTooltip.style.background = "rgba(20, 20, 20, 0.94)";
    hoverTooltip.style.color = "#fff";
    hoverTooltip.style.font = "13px/1.35 sans-serif";
    hoverTooltip.style.boxShadow =
        "0 4px 18px rgba(0, 0, 0, 0.24)";
    document.body.appendChild(hoverTooltip);

    return hoverTooltip;
}


function boardIdentity(piece) {
    return piece.physical_board_id
        || [
            "legacy",
            piece.row,
            piece.segment,
            piece.source_board_index,
        ].join(":");
}


function scopedBoardIdentity(
    piece,
    boardScope,
) {
    return `${boardScope}:${boardIdentity(piece)}`;
}


function physicalBoardFragments(scopedPhysicalBoardId) {
    return renderedPieceHitboxes.filter(
        item =>
            scopedBoardIdentity(
                item.piece,
                item.boardScope,
            ) === scopedPhysicalBoardId,
    );
}


function hoverInfoHtml(hitbox) {
    const piece = hitbox.piece;
    const scopedIdentity =
        scopedBoardIdentity(
            piece,
            hitbox.boardScope,
        );
    const fragments = physicalBoardFragments(
        scopedIdentity,
    );
    const roomIds = [
        ...new Set(
            fragments
                .map(item => item.roomId)
                .filter(Boolean),
        ),
    ];
    const isShort =
        hitbox.minimumPieceLength > 0
        && piece.length
            < hitbox.minimumPieceLength;
    const crossesRooms = roomIds.length > 1;
    const isCut =
        !piece.is_full_length
        || fragments.length > 1;

    return `
        <strong>Physical board ${scopedIdentity}</strong><br>
        Room: ${hitbox.roomId || "–"}<br>
        Row ${piece.row}, segment ${piece.segment}, piece ${piece.piece}<br>
        Length: ${formatNumber(piece.length, 0)} mm<br>
        Width: ${formatNumber(piece.width, 0)} mm<br>
        Cut: ${isCut ? "yes" : "no"}<br>
        Full board length: ${piece.is_full_length ? "yes" : "no"}<br>
        Visible parts from the same board: ${fragments.length}<br>
        Cut rule: at most one crosscut and one rip cut<br>
        ${crossesRooms
            ? `Split across transition between: ${roomIds.join(" / ")}<br>`
            : ""}
        ${isShort
            ? `<span style="color:#ffaaaa">Shorter than minimum ${formatNumber(hitbox.minimumPieceLength)} mm</span>`
            : ""}
    `;
}


function findHoveredPiece(canvasX, canvasY) {
    for (
        let index = renderedPieceHitboxes.length - 1;
        index >= 0;
        index -= 1
    ) {
        const hitbox = renderedPieceHitboxes[index];

        if (
            canvasX >= hitbox.x1
            && canvasX <= hitbox.x2
            && canvasY >= hitbox.y1
            && canvasY <= hitbox.y2
        ) {
            return hitbox;
        }
    }

    return null;
}


canvas.addEventListener("mousemove", event => {
    const rectangle = canvas.getBoundingClientRect();
    const canvasX = event.clientX - rectangle.left;
    const canvasY = event.clientY - rectangle.top;
    const hitbox = findHoveredPiece(
        canvasX,
        canvasY,
    );
    const tooltip = ensureHoverTooltip();

    if (!hitbox) {
        const changed =
            hoveredPieceKey !== null
            || hoveredPhysicalBoardId !== null;

        hoveredPieceKey = null;
        hoveredPhysicalBoardId = null;
        tooltip.style.display = "none";

        if (changed) {
            draw();
        }

        return;
    }

    const scopedIdentity = scopedBoardIdentity(
        hitbox.piece,
        hitbox.boardScope,
    );
    const changed =
        hoveredPieceKey !== hitbox.key
        || hoveredPhysicalBoardId
            !== scopedIdentity;

    hoveredPieceKey = hitbox.key;
    hoveredPhysicalBoardId =
        scopedIdentity;

    tooltip.innerHTML = hoverInfoHtml(hitbox);
    tooltip.style.display = "block";

    const offset = 14;
    const tooltipWidth = tooltip.offsetWidth;
    const tooltipHeight = tooltip.offsetHeight;

    let left = event.clientX + offset;
    let top = event.clientY + offset;

    if (left + tooltipWidth > window.innerWidth - 8) {
        left = event.clientX - tooltipWidth - offset;
    }

    if (top + tooltipHeight > window.innerHeight - 8) {
        top = event.clientY - tooltipHeight - offset;
    }

    tooltip.style.left = `${Math.max(8, left)}px`;
    tooltip.style.top = `${Math.max(8, top)}px`;

    if (changed) {
        draw();
    }
});


canvas.addEventListener("mouseleave", () => {
    const changed =
        hoveredPieceKey !== null
        || hoveredPhysicalBoardId !== null;

    hoveredPieceKey = null;
    hoveredPhysicalBoardId = null;

    if (hoverTooltip) {
        hoverTooltip.style.display = "none";
    }

    if (changed) {
        draw();
    }
});


async function refreshState() {
    if (refreshInProgress) {
        return;
    }

    refreshInProgress = true;

    try {
        const response = await fetch(
            "/api/state",
            {cache: "no-store"},
        );

        if (!response.ok) {
            throw new Error(
                `HTTP ${response.status}`,
            );
        }

        latestState = await response.json();

        if (
            !selectedRoomId
            && latestState.rooms?.length
        ) {
            selectedRoomId =
                latestState.rooms[0].id;
        }

        populateRoomSelect();
        updateSidePanel();
        draw();
    } catch (error) {
        statusText.textContent =
            "Could not reach the server.";
        statusText.dataset.state = "error";
    } finally {
        refreshInProgress = false;
    }
}


resizeCanvas();
refreshState();
setInterval(
    refreshState,
    POLL_INTERVAL_MS,
);
