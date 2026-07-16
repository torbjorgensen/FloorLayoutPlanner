const canvas = document.getElementById("floorCanvas");
const context = canvas.getContext("2d");

const roomSelect = document.getElementById("roomSelect");
const settingsForm = document.getElementById("settingsForm");
const selectedRoomName = document.getElementById("selectedRoomName");
const statusText = document.getElementById("statusText");
const progressBar = document.getElementById("progressBar");
const bestStats = document.getElementById("bestStats");
const outputFiles = document.getElementById("outputFiles");
const profileStats = document.getElementById("profileStats");
const validationMessage = document.getElementById("validationMessage");

const POLL_INTERVAL_MS = 500;

let latestState = null;
let selectedRoomId = null;
let formRoomId = null;
let refreshInProgress = false;
let renderedPieceHitboxes = [];
let hoveredPieceKey = null;
let hoveredPhysicalBoardId = null;
let hoverTooltip = null;


function selectedRoom() {
    return (
        latestState?.rooms?.find(
            room => room.id === selectedRoomId,
        ) || null
    );
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
}


roomSelect.addEventListener("change", () => {
    selectedRoomId = roomSelect.value;
    formRoomId = null;
    updateSidePanel();
    draw();
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
            "Forsøk",
            candidate.attempt !== undefined
                ? `${candidate.attempt} / ${candidate.total_attempts}`
                : "–",
        ],
        [
            "Startforskyvning",
            `${formatNumber(candidate.base_offset)} mm`,
        ],
        [
            "Første rad kappes",
            `${formatNumber(candidate.row_width_offset)} mm`,
        ],
        [
            "Korte biter",
            formatNumber(candidate.short_count),
        ],
        [
            "Korteste bit",
            `${formatNumber(candidate.shortest_piece)} mm`,
        ],
        [
            "Skjøtebrudd",
            formatNumber(candidate.joint_violations),
        ],
        [
            "Smaleste rad",
            `${formatNumber(candidate.narrowest_row_width)} mm`,
        ],
        [
            "Lokalt justerte rader",
            Object.keys(candidate.row_offsets || {}).length,
        ],
    ];

    const cut = connection?.continuous?.cut_plan;

    if (cut) {
        rows.push(
            [
                "Overgang",
                cut.method === "natural_joint"
                    ? "Naturlig skjøt"
                    : "Saget ekspansjonsfuge",
            ],
            [
                "Fugeplassering",
                `${formatNumber(cut.position_mm)} mm`,
            ],
            [
                "Fuge",
                `${formatNumber(cut.gap_width_mm, 1)} mm`,
            ],
            [
                "Berørte bord",
                formatNumber(cut.cut_boards),
            ],
            [
                "Korteste bit etter kutt",
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
        ["Fase", profile.phase || "–"],
        [
            "Fremdrift",
            `${profile.completed || 0} / ${profile.total || 0}`,
        ],
        [
            "Hastighet",
            `${formatNumber(profile.candidates_per_second, 1)}/s`,
        ],
        ["Estimert igjen", formatSeconds(profile.eta_s)],
        ["Brukt tid", formatSeconds(profile.elapsed_s)],
        ["Prosesser", profile.workers || 0],
        [
            "Grovsøk",
            `${profile.coarse_completed || 0} / ${profile.coarse_total || 0}`,
        ],
        [
            "Finjustering",
            `${profile.refine_completed || 0} / ${profile.refine_total || 0}`,
        ],
        [
            "Plan-generering",
            formatSeconds(timings.plan_generation_s || 0),
        ],
        [
            "Lokal optimalisering",
            formatSeconds(
                timings.local_optimization_s || 0,
            ),
        ],
        [
            "Scoring",
            formatSeconds(timings.final_scoring_s || 0),
        ],
        [
            "Lokale varianter testet",
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
            text: `Feil i overgangsberegning: ${continuous.error}`,
            kind: "error",
        };
    }

    if (continuous?.running) {
        const percent = Number(progress.percent || 0);
        const etaText =
            progress.eta_s !== null
            && progress.eta_s !== undefined
                ? ` – ca. ${formatSeconds(progress.eta_s)} igjen`
                : "";

        return {
            text:
                `${progress.message || "Optimaliserer overgang"}`
                + ` – ${formatNumber(percent, 1)} %`
                + etaText,
            kind: "running",
        };
    }

    if (
        continuous?.finished
        && hasSplitRoomPieces(connection)
    ) {
        return {
            text: "Ferdig – gulvet er delt ved ekspansjonsfugen.",
            kind: "finished",
        };
    }

    if (
        continuous?.finished
        && !hasSplitRoomPieces(connection)
    ) {
        return {
            text: "Beregningen er ferdig, men mangler oppdelte rombiter.",
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
            text: "Pauset.",
            kind: "paused",
        };
    }

    if (room.running) {
        return {
            text: "Optimaliserer rommet …",
            kind: "running",
        };
    }

    if (room.finished) {
        return {
            text: "Romoptimalisering ferdig. Venter på felles overgang.",
            kind: "warning",
        };
    }

    return {
        text: "Venter.",
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

    selectedRoomName.textContent = room.name;

    if (formRoomId !== room.id) {
        fillForm(room);
    }

    statusText.textContent = status.text;
    statusText.dataset.state = status.kind;

    bestStats.innerHTML =
        statsHtml(candidate, connection);

    profileStats.innerHTML =
        profileHtml(room.profile);

    updateProgress(room, connection);

    outputFiles.textContent =
        latestState?.output_dir || "–";
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
            result.error || "Handlingen mislyktes.",
        );
    }

    return result;
}


settingsForm.addEventListener(
    "submit",
    async event => {
        event.preventDefault();
        validationMessage.textContent = "Arbeider …";
        validationMessage.className = "form-message";

        try {
            const result = await roomPost(
                "apply",
                formPayload(),
            );

            validationMessage.textContent =
                "Innstillingene er brukt.";
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
                result?.message || "Lagret.";
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
                "Tilbakestilt til lagret JSON.";
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
        () => roomPost("restart"),
    );


document
    .getElementById("restartAllButton")
    .addEventListener(
        "click",
        async () => {
            await fetch(
                "/api/restart-all",
                {method: "POST"},
            );
        },
    );


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
            ? "Naturlig skjøt"
            : `Sagspor – ${cut.cut_boards} bord`;

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
        const sameSource =
            hoveredPhysicalBoardId !== null
            && scopedIdentity
                === hoveredPhysicalBoardId;
        const isHovered = key === hoveredPieceKey;

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

        context.strokeRect(
            screenX,
            screenY,
            screenWidth,
            screenHeight,
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
        <strong>Fysisk bord ${scopedIdentity}</strong><br>
        Rom: ${hitbox.roomId || "–"}<br>
        Rad ${piece.row}, segment ${piece.segment}, bit ${piece.piece}<br>
        Lengde: ${formatNumber(piece.length, 0)} mm<br>
        Bredde: ${formatNumber(piece.width, 0)} mm<br>
        Kapp: ${isCut ? "ja" : "nei"}<br>
        Hele bordlengden: ${piece.is_full_length ? "ja" : "nei"}<br>
        Synlige deler fra samme bord: ${fragments.length}<br>
        Kappregel: maks ett tverrkapp og ett langsgående kapp<br>
        ${crossesRooms
            ? `Delt ved overgang mellom: ${roomIds.join(" / ")}<br>`
            : ""}
        ${isShort
            ? `<span style="color:#ffaaaa">Kortere enn minimum ${formatNumber(hitbox.minimumPieceLength)} mm</span>`
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

    const changed =
        hoveredPieceKey !== hitbox.key
        || hoveredPhysicalBoardId
            !== boardIdentity(hitbox.piece);

    hoveredPieceKey = hitbox.key;
    hoveredPhysicalBoardId =
        boardIdentity(hitbox.piece);

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
            "Kunne ikke kontakte serveren.";
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
