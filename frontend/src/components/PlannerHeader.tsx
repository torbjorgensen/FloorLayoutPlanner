import Paper from "@mui/material/Paper";

import {ActionButton} from "./ActionButton";
import type {ConnectionStatus} from "../hooks/useProjectState";

interface PlannerHeaderProps {
    projectName?: string;
    connectionStatus: ConnectionStatus;
    connectionError: string | null;
    onRestartAll: () => void;
}

export function PlannerHeader({
    projectName,
    connectionStatus,
    connectionError,
    onRestartAll,
}: PlannerHeaderProps) {
    const connectionLabel = {
        connecting: "Connecting",
        connected: "Live updates connected",
        reconnecting: "Reconnecting",
        disconnected: "Disconnected",
    }[connectionStatus];
    return (
        <Paper className="topbar" component="header" elevation={0}>
            <div className="brand-block">
                <p className="eyebrow">Laying Engine Studio</p>
                <h1>Floor Layout Planner</h1>
                <p className="project-subtitle">
                    {projectName || "Waiting for backend state"}
                </p>
            </div>
            <div className="topbar-actions">
                <div
                    className="topbar-note"
                    data-status={connectionStatus}
                    title={connectionError || undefined}
                >
                    <span className="note-dot" />
                    {connectionLabel}
                </div>
                <ActionButton
                    className="action-button action-button-primary"
                    onClick={onRestartAll}
                    type="button"
                >
                    Restart all rooms
                </ActionButton>
            </div>
        </Paper>
    );
}
