import {useEffect, useMemo, useState} from "react";
import Alert from "react-bootstrap/Alert";
import Button from "react-bootstrap/Button";
import Card from "react-bootstrap/Card";
import Form from "react-bootstrap/Form";
import Spinner from "react-bootstrap/Spinner";
import {Link, useParams} from "react-router-dom";

import type {ProjectRecord} from "../types";

type NumberField = number | string;

interface EditableRectangle {
    name?: string;
    x: NumberField;
    y: NumberField;
    width: NumberField;
    height: NumberField;
}

interface EditableRoom {
    id: string;
    name: string;
    origin: {x: NumberField; y: NumberField};
    rectangles: EditableRectangle[];
    settings?: Record<string, unknown>;
}

interface EditableConnection {
    id: string;
    room_a: string;
    room_b: string;
    type: "open_passage" | "threshold" | "closed_door" | "continuous_then_cut";
    opening: {x1: NumberField; y1: NumberField; x2: NumberField; y2: NumberField};
    align: {rows: boolean; joints: boolean};
    weight: NumberField;
}

interface EditableConfig {
    project_name: string;
    board: {length_mm: NumberField; width_mm: NumberField; saw_kerf_mm: NumberField};
    settings: Record<string, unknown>;
    rooms: EditableRoom[];
    connections: EditableConnection[];
    [key: string]: unknown;
}

const optimizerFields = [
    ["expansion_gap_mm", "Expansion gap", "mm"],
    ["minimum_piece_length_mm", "Minimum piece length", "mm"],
    ["minimum_joint_distance_mm", "Minimum joint distance", "mm"],
    ["stagger_step_mm", "Stagger step", "mm"],
    ["optimization_step_mm", "Optimization step", "mm"],
    ["minimum_row_width_mm", "Minimum row width", "mm"],
    ["preferred_minimum_row_width_mm", "Preferred minimum row width", "mm"],
    ["optimizer_workers", "Optimizer workers", ""],
] as const;

function clone<T>(value: T): T {
    return JSON.parse(JSON.stringify(value)) as T;
}

function asConfig(record: ProjectRecord): EditableConfig {
    const config = clone(record.config) as unknown as EditableConfig;
    config.connections = (config.connections || []).map(connection => ({
        ...connection,
        align: {rows: connection.align?.rows ?? true, joints: connection.align?.joints ?? false},
        weight: connection.weight ?? 1,
    }));
    return config;
}

function numeric(value: NumberField, label: string, positive = false): number {
    const parsed = Number(value);
    if (!Number.isFinite(parsed) || (positive ? parsed <= 0 : parsed < 0)) {
        throw new Error(`${label} must be ${positive ? "greater than zero" : "zero or greater"}.`);
    }
    return parsed;
}

function previewNumber(value: NumberField): number {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
}

function RoomPreview({room, connections}: {room: EditableRoom; connections: EditableConnection[]}) {
    const rectangles = room.rectangles.map(rectangle => ({
        ...rectangle,
        x: previewNumber(rectangle.x),
        y: previewNumber(rectangle.y),
        width: Math.max(0, previewNumber(rectangle.width)),
        height: Math.max(0, previewNumber(rectangle.height)),
    }));
    const minX = Math.min(...rectangles.map(item => item.x), 0);
    const minY = Math.min(...rectangles.map(item => item.y), 0);
    const maxX = Math.max(...rectangles.map(item => item.x + item.width), 1);
    const maxY = Math.max(...rectangles.map(item => item.y + item.height), 1);
    const span = Math.max(maxX - minX, maxY - minY, 1);
    const padding = span * .06;
    const originX = previewNumber(room.origin.x);
    const originY = previewNumber(room.origin.y);
    const openings = connections.filter(connection => connection.room_a === room.id || connection.room_b === room.id);
    return <div className="room-preview">
        <div className="room-preview-title"><strong>Room preview</strong><span>{Math.round(maxX - minX)} × {Math.round(maxY - minY)} mm</span></div>
        <svg aria-label={`Preview of ${room.name}`} preserveAspectRatio="xMidYMid meet" role="img" viewBox={`${minX - padding} ${minY - padding} ${maxX - minX + 2 * padding} ${maxY - minY + 2 * padding}`}>
            {rectangles.map((rectangle, index) => <g key={index}>
                <rect className="room-preview-area" height={rectangle.height} width={rectangle.width} x={rectangle.x} y={rectangle.y} />
                {rectangle.width > span * .18 && rectangle.height > span * .08 && <text className="room-preview-label" x={rectangle.x + rectangle.width / 2} y={rectangle.y + rectangle.height / 2}>{rectangle.name || `Area ${index + 1}`}</text>}
            </g>)}
            {openings.map(connection => <g key={connection.id}>
                <line className="room-preview-opening" x1={previewNumber(connection.opening.x1) - originX} x2={previewNumber(connection.opening.x2) - originX} y1={previewNumber(connection.opening.y1) - originY} y2={previewNumber(connection.opening.y2) - originY} />
                <circle className="room-preview-opening-point" cx={previewNumber(connection.opening.x1) - originX} cy={previewNumber(connection.opening.y1) - originY} r={span * .012} />
                <circle className="room-preview-opening-point" cx={previewNumber(connection.opening.x2) - originX} cy={previewNumber(connection.opening.y2) - originY} r={span * .012} />
            </g>)}
        </svg>
        <small>Updates as values change. Openings are shown as orange lines in shared floor-plan coordinates.</small>
    </div>;
}

function normalized(config: EditableConfig): EditableConfig {
    const result = clone(config);
    result.project_name = result.project_name.trim();
    if (!result.project_name) throw new Error("Project name is required.");
    result.board.length_mm = numeric(result.board.length_mm, "Board length", true);
    result.board.width_mm = numeric(result.board.width_mm, "Board width", true);
    result.board.saw_kerf_mm = numeric(result.board.saw_kerf_mm, "Saw kerf");
    if (!result.rooms.length) throw new Error("A project must contain at least one room.");
    const ids = new Set<string>();
    result.rooms.forEach((room, roomIndex) => {
        room.name = room.name.trim();
        if (!room.name) throw new Error(`Room ${roomIndex + 1} needs a name.`);
        if (ids.has(room.id)) throw new Error(`Room id ${room.id} is duplicated.`);
        ids.add(room.id);
        room.origin.x = numeric(room.origin.x, `${room.name} origin X`);
        room.origin.y = numeric(room.origin.y, `${room.name} origin Y`);
        if (!room.rectangles.length) throw new Error(`${room.name} needs at least one rectangle.`);
        room.rectangles.forEach((rectangle, rectangleIndex) => {
            const prefix = `${room.name}, rectangle ${rectangleIndex + 1}`;
            rectangle.name = rectangle.name?.trim() || `Area ${rectangleIndex + 1}`;
            rectangle.x = numeric(rectangle.x, `${prefix} X`);
            rectangle.y = numeric(rectangle.y, `${prefix} Y`);
            rectangle.width = numeric(rectangle.width, `${prefix} width`, true);
            rectangle.height = numeric(rectangle.height, `${prefix} height`, true);
        });
    });
    const connectionIds = new Set<string>();
    result.connections.forEach((connection, index) => {
        connection.id = connection.id.trim();
        if (!connection.id) throw new Error(`Connection ${index + 1} needs an id.`);
        if (connectionIds.has(connection.id)) throw new Error(`Connection id ${connection.id} is duplicated.`);
        connectionIds.add(connection.id);
        if (!ids.has(connection.room_a) || !ids.has(connection.room_b)) throw new Error(`Connection ${connection.id} references an unknown room.`);
        if (connection.room_a === connection.room_b) throw new Error(`Connection ${connection.id} must connect two different rooms.`);
        connection.opening.x1 = numeric(connection.opening.x1, `${connection.id} opening X1`);
        connection.opening.y1 = numeric(connection.opening.y1, `${connection.id} opening Y1`);
        connection.opening.x2 = numeric(connection.opening.x2, `${connection.id} opening X2`);
        connection.opening.y2 = numeric(connection.opening.y2, `${connection.id} opening Y2`);
        if (connection.opening.x1 === connection.opening.x2 && connection.opening.y1 === connection.opening.y2) throw new Error(`Connection ${connection.id} opening needs two distinct endpoints.`);
        connection.weight = numeric(connection.weight, `${connection.id} weight`, true);
    });
    for (const [key, label] of optimizerFields) {
        if (result.settings[key] !== undefined) {
            result.settings[key] = numeric(result.settings[key] as NumberField, label, key !== "expansion_gap_mm");
        }
    }
    return result;
}

export default function ProjectEditorPage() {
    const {projectId} = useParams();
    const [project, setProject] = useState<ProjectRecord | null>(null);
    const [config, setConfig] = useState<EditableConfig | null>(null);
    const [baseline, setBaseline] = useState("");
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [notice, setNotice] = useState<string | null>(null);
    const dirty = useMemo(() => config !== null && JSON.stringify(config) !== baseline, [config, baseline]);

    useEffect(() => {
        async function load() {
            try {
                const response = await fetch(`/api/projects/${projectId}`);
                const payload = await response.json() as {ok: boolean; project?: ProjectRecord; error?: string};
                if (!response.ok || !payload.ok || !payload.project) throw new Error(payload.error || "Could not load project.");
                const loaded = asConfig(payload.project);
                setProject(payload.project);
                setConfig(loaded);
                setBaseline(JSON.stringify(loaded));
            } catch (loadError) {
                setError(loadError instanceof Error ? loadError.message : "Could not load project.");
            } finally {
                setLoading(false);
            }
        }
        void load();
    }, [projectId]);

    useEffect(() => {
        const warn = (event: BeforeUnloadEvent) => {
            if (dirty) event.preventDefault();
        };
        window.addEventListener("beforeunload", warn);
        return () => window.removeEventListener("beforeunload", warn);
    }, [dirty]);

    function change(mutator: (next: EditableConfig) => void) {
        setConfig(current => {
            if (!current) return current;
            const next = clone(current);
            mutator(next);
            return next;
        });
        setNotice(null);
    }

    function addRoom() {
        change(next => {
            let index = next.rooms.length + 1;
            while (next.rooms.some(room => room.id === `room_${index}`)) index += 1;
            next.rooms.push({
                id: `room_${index}`,
                name: `Room ${index}`,
                origin: {x: 0, y: 0},
                rectangles: [{name: "Main area", x: 0, y: 0, width: 4000, height: 3000}],
                settings: {},
            });
        });
    }

    function addConnection() {
        change(next => {
            if (next.rooms.length < 2) return;
            let index = next.connections.length + 1;
            while (next.connections.some(item => item.id === `connection_${index}`)) index += 1;
            next.connections.push({id: `connection_${index}`, room_a: next.rooms[0].id, room_b: next.rooms[1].id, type: "open_passage", opening: {x1: 0, y1: 0, x2: 1000, y2: 0}, align: {rows: true, joints: false}, weight: 1});
        });
    }

    async function save(event: React.FormEvent) {
        event.preventDefault();
        if (!config || !project) return;
        setSaving(true);
        setError(null);
        try {
            const cleaned = normalized(config);
            const response = await fetch(`/api/projects/${project.id}`, {
                method: "PATCH",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({config: cleaned, expected_version: project.version}),
            });
            const payload = await response.json() as {ok: boolean; project?: ProjectRecord; error?: string};
            if (!response.ok || !payload.ok || !payload.project) throw new Error(payload.error || "Could not save project.");
            const saved = asConfig(payload.project);
            setProject(payload.project);
            setConfig(saved);
            setBaseline(JSON.stringify(saved));
            setNotice("Project configuration saved.");
        } catch (saveError) {
            setError(saveError instanceof Error ? saveError.message : "Could not save project.");
        } finally {
            setSaving(false);
        }
    }

    if (loading) return <main className="editor-page"><Spinner size="sm" /> Loading editor…</main>;
    if (!config || !project) return <main className="editor-page"><Alert variant="danger">{error || "Project not found."}</Alert><Link to="/">Back to projects</Link></main>;

    return (
        <main className="editor-page">
            <header className="editor-header">
                <div><p className="eyebrow">Floor Layout Planner</p><h1>Edit {project.name}</h1><p>Configure the board and rectangle-based room geometry.</p></div>
                <div className="editor-actions"><span className={dirty ? "dirty-indicator dirty" : "dirty-indicator"}>{dirty ? "Unsaved changes" : "Saved"}</span><Link className="btn btn-outline-secondary" to="/">Projects</Link><Link className="btn btn-outline-primary" to={`/projects/${project.id}`}>Planner</Link></div>
            </header>
            {error && <Alert dismissible onClose={() => setError(null)} variant="danger">{error}</Alert>}
            {notice && <Alert dismissible onClose={() => setNotice(null)} variant="success">{notice}</Alert>}
            <Form onSubmit={event => void save(event)}>
                <Card className="editor-card"><Card.Body><Card.Title>Project and board</Card.Title><div className="editor-grid four">
                    <Form.Group><Form.Label>Project name</Form.Label><Form.Control value={config.project_name} onChange={event => change(next => {next.project_name = event.target.value;})} /></Form.Group>
                    {(["length_mm", "width_mm", "saw_kerf_mm"] as const).map(key => <Form.Group key={key}><Form.Label>{key === "length_mm" ? "Board length (mm)" : key === "width_mm" ? "Board width (mm)" : "Saw kerf (mm)"}</Form.Label><Form.Control min="0" step="any" type="number" value={config.board[key]} onChange={event => change(next => {next.board[key] = event.target.value;})} /></Form.Group>)}
                </div><div className="editor-grid four optimizer-grid">{optimizerFields.map(([key, label, unit]) => <Form.Group key={key}><Form.Label>{label}{unit && ` (${unit})`}</Form.Label><Form.Control min="0" step="any" type="number" value={String(config.settings[key] ?? "")} onChange={event => change(next => {next.settings[key] = event.target.value;})} /></Form.Group>)}</div></Card.Body></Card>

                <div className="rooms-heading"><div><h2>Rooms</h2><p>Origins position each room on the shared floor plan. Rectangle coordinates are relative to that origin.</p></div><Button onClick={addRoom} type="button" variant="outline-primary">Add room</Button></div>
                {config.rooms.map((room, roomIndex) => <Card className="editor-card room-editor" key={room.id}><Card.Body>
                    <div className="room-editor-heading"><Card.Title>Room {roomIndex + 1}</Card.Title><div>
                        <Button disabled={roomIndex === 0} onClick={() => change(next => {const [item] = next.rooms.splice(roomIndex, 1); next.rooms.splice(roomIndex - 1, 0, item);})} size="sm" type="button" variant="outline-secondary">Move up</Button>{" "}
                        <Button onClick={() => change(next => {const source = clone(next.rooms[roomIndex]); let suffix = 2; let id = `${source.id}_copy`; while (next.rooms.some(item => item.id === id)) id = `${source.id}_copy_${suffix++}`; source.id = id; source.name += " Copy"; next.rooms.splice(roomIndex + 1, 0, source);})} size="sm" type="button" variant="outline-secondary">Duplicate</Button>{" "}
                        <Button disabled={config.rooms.length === 1} onClick={() => change(next => {const removedId = next.rooms[roomIndex].id; next.rooms.splice(roomIndex, 1); next.connections = next.connections.filter(connection => connection.room_a !== removedId && connection.room_b !== removedId);})} size="sm" type="button" variant="outline-danger">Remove</Button>
                    </div></div>
                    <div className="editor-grid four"><Form.Group><Form.Label>Name</Form.Label><Form.Control value={room.name} onChange={event => change(next => {next.rooms[roomIndex].name = event.target.value;})} /></Form.Group><Form.Group><Form.Label>Stable id</Form.Label><Form.Control readOnly value={room.id} /><Form.Text>Used by saved connections.</Form.Text></Form.Group>{(["x", "y"] as const).map(axis => <Form.Group key={axis}><Form.Label>Origin {axis.toUpperCase()} (mm)</Form.Label><Form.Control min="0" step="any" type="number" value={room.origin[axis]} onChange={event => change(next => {next.rooms[roomIndex].origin[axis] = event.target.value;})} /></Form.Group>)}</div>
                    <h3>Rectangles</h3>{room.rectangles.map((rectangle, rectangleIndex) => <div className="rectangle-row" key={rectangleIndex}><Form.Group><Form.Label>Name</Form.Label><Form.Control value={rectangle.name || ""} onChange={event => change(next => {next.rooms[roomIndex].rectangles[rectangleIndex].name = event.target.value;})} /></Form.Group>{(["x", "y", "width", "height"] as const).map(key => <Form.Group key={key}><Form.Label>{key[0].toUpperCase() + key.slice(1)} (mm)</Form.Label><Form.Control min="0" step="any" type="number" value={rectangle[key]} onChange={event => change(next => {next.rooms[roomIndex].rectangles[rectangleIndex][key] = event.target.value;})} /></Form.Group>)}<Button disabled={room.rectangles.length === 1} onClick={() => change(next => {next.rooms[roomIndex].rectangles.splice(rectangleIndex, 1);})} type="button" variant="outline-danger">Remove</Button></div>)}
                    <Button onClick={() => change(next => {next.rooms[roomIndex].rectangles.push({name: `Area ${next.rooms[roomIndex].rectangles.length + 1}`, x: 0, y: 0, width: 1000, height: 1000});})} size="sm" type="button" variant="outline-primary">Add rectangle</Button>
                    <RoomPreview connections={config.connections} room={room} />
                </Card.Body></Card>)}
                <div className="rooms-heading"><div><h2>Connections</h2><p>Define openings between rooms. Coordinates use the shared floor-plan coordinate system.</p></div><Button disabled={config.rooms.length < 2} onClick={addConnection} type="button" variant="outline-primary">Add connection</Button></div>
                {!config.connections.length && <Alert variant="secondary">No room connections defined yet.</Alert>}
                {config.connections.map((connection, connectionIndex) => <Card className="editor-card" key={connection.id}><Card.Body>
                    <div className="room-editor-heading"><Card.Title>Connection {connectionIndex + 1}</Card.Title><Button onClick={() => change(next => {next.connections.splice(connectionIndex, 1);})} size="sm" type="button" variant="outline-danger">Remove</Button></div>
                    <div className="editor-grid four">
                        <Form.Group><Form.Label>Connection id</Form.Label><Form.Control value={connection.id} onChange={event => change(next => {next.connections[connectionIndex].id = event.target.value;})} /></Form.Group>
                        {(["room_a", "room_b"] as const).map((key, side) => <Form.Group key={key}><Form.Label>Room {side ? "B" : "A"}</Form.Label><Form.Select value={connection[key]} onChange={event => change(next => {next.connections[connectionIndex][key] = event.target.value;})}>{config.rooms.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</Form.Select></Form.Group>)}
                        <Form.Group><Form.Label>Opening type</Form.Label><Form.Select value={connection.type} onChange={event => change(next => {next.connections[connectionIndex].type = event.target.value as EditableConnection["type"];})}><option value="open_passage">Open passage</option><option value="threshold">Threshold</option><option value="closed_door">Closed door</option>{connection.type === "continuous_then_cut" && <option value="continuous_then_cut">Legacy continuous opening</option>}</Form.Select></Form.Group>
                    </div>
                    <h3>Opening line</h3><div className="editor-grid four">{(["x1", "y1", "x2", "y2"] as const).map(key => <Form.Group key={key}><Form.Label>{key.toUpperCase()} (mm)</Form.Label><Form.Control min="0" step="any" type="number" value={connection.opening[key]} onChange={event => change(next => {next.connections[connectionIndex].opening[key] = event.target.value;})} /></Form.Group>)}</div>
                    <div className="connection-options"><Form.Check checked={connection.align.rows} label="Align rows" onChange={event => change(next => {next.connections[connectionIndex].align.rows = event.target.checked;})} /><Form.Check checked={connection.align.joints} label="Align joints" onChange={event => change(next => {next.connections[connectionIndex].align.joints = event.target.checked;})} /><Form.Group><Form.Label>Weight</Form.Label><Form.Control min="0.01" step="any" type="number" value={connection.weight} onChange={event => change(next => {next.connections[connectionIndex].weight = event.target.value;})} /></Form.Group></div>
                    {connection.type === "continuous_then_cut" && <Alert className="mt-3 mb-0" variant="warning">This saved connection uses the legacy continuous-layout mode. Select an opening type above to stop planning continuous boards through it.</Alert>}
                </Card.Body></Card>)}
                <div className="editor-savebar"><Button disabled={!dirty || saving} onClick={() => {setConfig(JSON.parse(baseline) as EditableConfig); setError(null);}} type="button" variant="outline-secondary">Discard changes</Button><Button disabled={!dirty || saving} type="submit">{saving ? "Saving…" : "Save configuration"}</Button></div>
            </Form>
        </main>
    );
}
