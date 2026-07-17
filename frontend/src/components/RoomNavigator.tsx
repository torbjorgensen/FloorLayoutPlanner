import Chip from "@mui/material/Chip";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import TextField from "@mui/material/TextField";

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
        <Paper className="panel panel-room-picker" component="section" elevation={0}>
            <div className="panel-header">
                <div>
                    <p className="eyebrow">Navigator</p>
                    <h2>Rooms</h2>
                </div>
                <Chip className="panel-chip" label="Live" size="small" />
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
            <TextField
                fullWidth
                id="roomSelect"
                label="Room dropdown"
                onChange={event => onSelectRoom(event.target.value)}
                select
                size="small"
                value={selectedRoomId || ""}
            >
                {rooms.map(room => (
                    <MenuItem key={room.id} value={room.id}>
                        {room.name}
                    </MenuItem>
                ))}
            </TextField>
        </Paper>
    );
}
