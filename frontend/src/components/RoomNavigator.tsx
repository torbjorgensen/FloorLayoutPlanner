import Form from "react-bootstrap/Form";

import {titleCaseWords} from "../lib/planning";
import type {RoomStatePayload} from "../types";
import {ActionButton} from "./ActionButton";

interface RoomNavigatorProps {
    rooms: RoomStatePayload[];
    selectedRoomId: string | null;
    onSelectRoom: (roomId: string) => void;
}

export function RoomNavigator({
    rooms,
    selectedRoomId,
    onSelectRoom,
}: RoomNavigatorProps) {
    return (
        <section className="panel panel-room-picker">
            <div className="panel-header">
                <div>
                    <p className="eyebrow">Navigator</p>
                    <h2>Rooms</h2>
                </div>
                <span className="badge text-bg-success">Live</span>
            </div>
            <div className="room-tab-grid" id="roomTabs">
                {rooms.map(room => (
                    <ActionButton
                        className={`room-tab ${room.id === selectedRoomId ? "is-active" : ""}`}
                        data-room-id={room.id}
                        key={room.id}
                        onClick={() => onSelectRoom(room.id)}
                        type="button"
                    >
                        <span className="room-tab-title">{room.name}</span>
                        <span className="room-tab-meta">
                            {titleCaseWords(room.settings.orientation)}
                            {" · "}
                            {titleCaseWords(room.settings.start_corner)}
                        </span>
                    </ActionButton>
                ))}
            </div>
            <Form.Select
                id="roomSelect"
                aria-label="Room dropdown"
                onChange={event => onSelectRoom(event.target.value)}
                size="sm"
                value={selectedRoomId || ""}
            >
                {rooms.map(room => (
                    <option key={room.id} value={room.id}>
                        {room.name}
                    </option>
                ))}
            </Form.Select>
        </section>
    );
}
