import {useEffect, useState} from "react";
import {io} from "socket.io-client";

import type {ProjectState} from "../types";

export type ConnectionStatus =
    | "connecting"
    | "connected"
    | "reconnecting"
    | "disconnected";

interface ProjectStateSocket {
    state: ProjectState | null;
    connectionStatus: ConnectionStatus;
    connectionError: string | null;
}

export function useProjectState(): ProjectStateSocket {
    const [state, setState] = useState<ProjectState | null>(null);
    const [connectionStatus, setConnectionStatus] =
        useState<ConnectionStatus>("connecting");
    const [connectionError, setConnectionError] = useState<string | null>(null);

    useEffect(() => {
        const socket = io({
            path: "/socket.io",
            transports: ["websocket", "polling"],
            tryAllTransports: true,
            reconnection: true,
            reconnectionDelay: 500,
            reconnectionDelayMax: 5000,
        });

        socket.on("connect", () => {
            setConnectionStatus("connected");
            setConnectionError(null);
        });
        socket.on("project_state", (payload: ProjectState) => {
            setState(payload);
        });
        socket.on("disconnect", reason => {
            setConnectionStatus(
                reason === "io client disconnect"
                    ? "disconnected"
                    : "reconnecting",
            );
        });
        socket.on("connect_error", error => {
            setConnectionStatus("reconnecting");
            setConnectionError(error.message);
        });

        return () => {
            socket.disconnect();
        };
    }, []);

    return {state, connectionStatus, connectionError};
}
