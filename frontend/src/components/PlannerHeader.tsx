import Paper from "@mui/material/Paper";

import {ActionButton} from "./ActionButton";

interface PlannerHeaderProps {
    projectName?: string;
    onRestartAll: () => void;
}

export function PlannerHeader({projectName, onRestartAll}: PlannerHeaderProps) {
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
                <div className="topbar-note">
                    <span className="note-dot" />
                    React UI with live backend optimization
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
