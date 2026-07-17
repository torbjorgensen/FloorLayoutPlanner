import {ActionButton} from "./ActionButton";
import type {ConnectionStatus} from "../hooks/useProjectState";

interface PlannerHeaderProps {
    projectName?: string;
    connectionStatus: ConnectionStatus;
    connectionError: string | null;
    onRestartAll: () => void;
    onBackToProjects?: () => void;
}

export function PlannerHeader({
    projectName,
    connectionStatus,
    connectionError,
    onRestartAll,
    onBackToProjects,
}: PlannerHeaderProps) {
    const connectionLabel = {
        connecting: "Connecting",
        connected: "Live updates connected",
        reconnecting: "Reconnecting",
        disconnected: "Disconnected",
    }[connectionStatus];
    return (
        <header className="topbar">
            <div className="brand-block">
                <h1>Floor Layout Planner</h1>
                <p className="project-subtitle">
                    {projectName || "Waiting for backend state"}
                </p>
            </div>
            <div className="topbar-actions">
                {onBackToProjects && (
                    <ActionButton
                        className="action-button planner-projects-button"
                        onClick={onBackToProjects}
                        type="button"
                    >
                        Projects
                    </ActionButton>
                )}
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
        </header>
    );
}
