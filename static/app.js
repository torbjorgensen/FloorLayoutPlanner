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

let latestState = null;
let selectedRoomId = null;
let formRoomId = null;

function selectedRoom() {
    return latestState?.rooms?.find(room => room.id === selectedRoomId) || null;
}

function resizeCanvas() {
    const ratio = window.devicePixelRatio || 1;
    const rectangle = canvas.getBoundingClientRect();
    canvas.width = Math.max(1, Math.floor(rectangle.width * ratio));
    canvas.height = Math.max(1, Math.floor(rectangle.height * ratio));
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    draw();
}
window.addEventListener("resize", resizeCanvas);

function populateRoomSelect() {
    if (!latestState?.rooms) return;

    const currentValue = selectedRoomId;
    roomSelect.innerHTML = "";

    for (const room of latestState.rooms) {
        const option = document.createElement("option");
        option.value = room.id;
        option.textContent = room.name;
        roomSelect.appendChild(option);
    }

    if (!selectedRoomId || !latestState.rooms.some(room => room.id === selectedRoomId)) {
        selectedRoomId = latestState.rooms[0]?.id || null;
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
    if (!room) return;
    for (const [name, value] of Object.entries(room.settings || {})) {
        const field = settingsForm.elements.namedItem(name);
        if (field) field.value = value;
    }
    formRoomId = room.id;
}

function formPayload() {
    return Object.fromEntries(new FormData(settingsForm).entries());
}

function statsHtml(candidate) {
    if (!candidate) return "–";

    return `
        <div class="stat-grid">
            <span>Forsøk</span>
            <span>${candidate.attempt} / ${candidate.total_attempts}</span>
            <span>Startforskyvning</span>
            <span>${candidate.base_offset.toFixed(0)} mm</span>
            <span>Første rad kappes</span>
            <span>${candidate.row_width_offset.toFixed(0)} mm</span>
            <span>Korte biter</span>
            <span>${candidate.short_count}</span>
            <span>Korteste bit</span>
            <span>${candidate.shortest_piece.toFixed(0)} mm</span>
            <span>Skjøtebrudd</span>
            <span>${candidate.joint_violations}</span>
            <span>Smaleste rad</span>
            <span>${candidate.narrowest_row_width.toFixed(0)} mm</span>
            <span>Lokalt justerte rader</span>
            <span>${Object.keys(candidate.row_offsets || {}).length}</span>
        </div>
    `;
}


function formatSeconds(value) {
    if (value === null || value === undefined || !Number.isFinite(value)) {
        return "–";
    }

    if (value < 1) {
        return `${(value * 1000).toFixed(0)} ms`;
    }

    const minutes = Math.floor(value / 60);
    const seconds = Math.floor(value % 60);

    if (minutes > 0) {
        return `${minutes} min ${seconds} s`;
    }

    return `${value.toFixed(1)} s`;
}

function profileHtml(profile) {
    if (!profile) return "–";

    const timings = profile.timing_totals || {};

    return `
        <div class="stat-grid">
            <span>Fase</span>
            <span>${profile.phase || "–"}</span>
            <span>Fremdrift</span>
            <span>${profile.completed || 0} / ${profile.total || 0}</span>
            <span>Hastighet</span>
            <span>${(profile.candidates_per_second || 0).toFixed(1)}/s</span>
            <span>Estimert igjen</span>
            <span>${formatSeconds(profile.eta_s)}</span>
            <span>Brukt tid</span>
            <span>${formatSeconds(profile.elapsed_s)}</span>
            <span>Prosesser</span>
            <span>${profile.workers || 0}</span>
            <span>Grovsøk</span>
            <span>${profile.coarse_completed || 0} / ${profile.coarse_total || 0}</span>
            <span>Finjustering</span>
            <span>${profile.refine_completed || 0} / ${profile.refine_total || 0}</span>
            <span>Plan-generering</span>
            <span>${formatSeconds(timings.plan_generation_s || 0)}</span>
            <span>Lokal optimalisering</span>
            <span>${formatSeconds(timings.local_optimization_s || 0)}</span>
            <span>Scoring</span>
            <span>${formatSeconds(timings.final_scoring_s || 0)}</span>
            <span>Lokale varianter testet</span>
            <span>${profile.local_variants || 0}</span>
        </div>
    `;
}

function updateSidePanel() {
    const room = selectedRoom();
    if (!room) return;

    selectedRoomName.textContent = room.name;

    if (formRoomId !== room.id) {
        fillForm(room);
    }

    if (room.error) {
        statusText.innerHTML = `<span class="error">${room.error}</span>`;
    } else if (room.finished) {
        statusText.textContent = "Ferdig.";
    } else if (room.paused) {
        statusText.textContent = "Pauset.";
    } else if (room.running) {
        statusText.textContent = "Optimaliserer …";
    } else {
        statusText.textContent = "Venter.";
    }

    bestStats.innerHTML = statsHtml(room.best);
    profileStats.innerHTML = profileHtml(room.profile);

    const candidate = room.current || room.best;
    if (candidate) {
        progressBar.max = candidate.total_attempts;
        progressBar.value = candidate.attempt;
    } else {
        progressBar.max = 1;
        progressBar.value = 0;
    }

    outputFiles.textContent = latestState?.output_dir || "–";
}

async function roomPost(action, payload = null) {
    if (!selectedRoomId) return;

    const response = await fetch(`/api/room/${selectedRoomId}/${action}`, {
        method: "POST",
        headers: payload ? {"Content-Type": "application/json"} : {},
        body: payload ? JSON.stringify(payload) : null,
    });

    const result = await response.json();
    if (!response.ok || result.ok === false) {
        throw new Error(result.error || "Handlingen mislyktes.");
    }
    return result;
}

settingsForm.addEventListener("submit", async event => {
    event.preventDefault();
    validationMessage.textContent = "Arbeider …";
    try {
        const result = await roomPost("apply", formPayload());
        validationMessage.textContent = "Innstillingene er brukt.";
        validationMessage.className = "form-message success";
        if (result.settings) {
            Object.entries(result.settings).forEach(([name, value]) => {
                const field = settingsForm.elements.namedItem(name);
                if (field) field.value = value;
            });
        }
    } catch (error) {
        validationMessage.textContent = error.message;
        validationMessage.className = "form-message error";
    }
});

document.getElementById("saveConfigButton").addEventListener("click", async () => {
    try {
        const result = await roomPost("save", formPayload());
        validationMessage.textContent = result.message || "Lagret.";
        validationMessage.className = "form-message success";
    } catch (error) {
        validationMessage.textContent = error.message;
        validationMessage.className = "form-message error";
    }
});

document.getElementById("resetConfigButton").addEventListener("click", async () => {
    try {
        const result = await roomPost("reset");
        if (result.settings) {
            Object.entries(result.settings).forEach(([name, value]) => {
                const field = settingsForm.elements.namedItem(name);
                if (field) field.value = value;
            });
        }
        validationMessage.textContent = "Tilbakestilt til lagret JSON.";
        validationMessage.className = "form-message success";
    } catch (error) {
        validationMessage.textContent = error.message;
        validationMessage.className = "form-message error";
    }
});

document.getElementById("pauseButton").addEventListener("click", () => roomPost("pause"));
document.getElementById("resumeButton").addEventListener("click", () => roomPost("resume"));
document.getElementById("restartButton").addEventListener("click", () => roomPost("restart"));
document.getElementById("restartAllButton").addEventListener("click", () => {
    fetch("/api/restart-all", {method: "POST"});
});

function colorWithAlpha(color, alpha) {
    if (!color) return `rgba(220,220,220,${alpha})`;
    if (color.startsWith("#")) {
        const hex = color.slice(1);
        const normalized = hex.length === 3
            ? hex.split("").map(c => c + c).join("")
            : hex;
        const red = parseInt(normalized.slice(0, 2), 16);
        const green = parseInt(normalized.slice(2, 4), 16);
        const blue = parseInt(normalized.slice(4, 6), 16);
        return `rgba(${red},${green},${blue},${alpha})`;
    }
    return color;
}

function draw() {
    const width = canvas.clientWidth;
    const height = canvas.clientHeight;
    context.clearRect(0, 0, width, height);

    if (!latestState?.rooms?.length) return;

    const bounds = latestState.bounds;
    const projectWidth = Math.max(1, bounds.max_x - bounds.min_x);
    const projectHeight = Math.max(1, bounds.max_y - bounds.min_y);
    const margin = 30;
    const scale = Math.min(
        (width - 2 * margin) / projectWidth,
        (height - 2 * margin) / projectHeight,
    );
    const x = value => margin + (value - bounds.min_x) * scale;
    const y = value => margin + (value - bounds.min_y) * scale;

    const continuousRooms = new Set();
    for (const connection of latestState.connections || []) {
        if (connection.type === "continuous_then_cut" && connection.continuous?.candidate) {
            continuousRooms.add(connection.room_a);
            continuousRooms.add(connection.room_b);
        }
    }

    for (const room of latestState.rooms) {
        const selected = room.id === selectedRoomId;
        for (const rectangle of room.rectangles) {
            context.fillStyle = colorWithAlpha(
                rectangle.fill_color || (selected ? "#dbeafe" : "#eeeeee"),
                rectangle.fill_alpha ?? (selected ? 0.22 : 0.10),
            );
            context.fillRect(x(rectangle.x), y(rectangle.y), rectangle.width * scale, rectangle.height * scale);
        }
        const candidate = room.current || room.best;
        if (candidate && !continuousRooms.has(room.id)) {
            drawPieces(candidate.pieces, room.minimum_piece_length, selected, x, y, scale);
        }
    }

    for (const connection of latestState.connections || []) {
        if (connection.type !== "continuous_then_cut" || !connection.continuous?.candidate) continue;
        drawPieces(connection.continuous.candidate.pieces, 0, true, x, y, scale);
        const cut = connection.continuous.cut_plan;
        const passage = connection.passage;
        if (cut && passage) {
            context.save();
            context.fillStyle = cut.method === "natural_joint" ? "#1b8f3a" : "#202020";
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
                ? "Naturlig skjøt"
                : `Sagspor – ${cut.cut_boards} bord`;
            context.fillText(label, x(passage.x) + 6, y(passage.y) - 7);
            context.restore();
        }
    }

    for (const room of latestState.rooms) {
        const selected = room.id === selectedRoomId;
        context.beginPath();
        room.outline.forEach((point, index) => {
            if (index === 0) context.moveTo(x(point[0]), y(point[1]));
            else context.lineTo(x(point[0]), y(point[1]));
        });
        context.strokeStyle = selected ? "#1a73e8" : "#111";
        context.lineWidth = selected ? 4 : 2;
        context.stroke();
        context.fillStyle = "#111";
        context.font = "600 14px sans-serif";
        context.fillText(room.name, x(room.bounds.min_x) + 8, y(room.bounds.min_y) + 20);
    }
}

function drawPieces(pieces, minimumPieceLength, selected, x, y, scale) {
    for (const piece of pieces || []) {
        const isShort = minimumPieceLength > 0 && piece.length < minimumPieceLength;
        context.fillStyle = isShort ? "#ffd6d6" : (selected ? "#dff2df" : "#edf3ed");
        context.strokeStyle = isShort ? "#b00020" : "#667a66";
        context.lineWidth = isShort ? 2 : 0.8;
        context.fillRect(
            x(piece.x1), y(piece.y1),
            (piece.x2 - piece.x1) * scale,
            (piece.y2 - piece.y1) * scale,
        );
        context.strokeRect(
            x(piece.x1), y(piece.y1),
            (piece.x2 - piece.x1) * scale,
            (piece.y2 - piece.y1) * scale,
        );
    }
}

async function refreshState() {
    try {
        const response = await fetch("/api/state", {cache: "no-store"});
        latestState = await response.json();

        if (!selectedRoomId && latestState.rooms?.length) {
            selectedRoomId = latestState.rooms[0].id;
        }

        populateRoomSelect();
        updateSidePanel();
        draw();
    } catch (error) {
        statusText.innerHTML = `<span class="error">Kunne ikke kontakte serveren.</span>`;
    }
}

resizeCanvas();
refreshState();
setInterval(refreshState, 200);
