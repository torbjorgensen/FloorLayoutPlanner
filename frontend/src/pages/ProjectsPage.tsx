import {useEffect, useRef, useState} from "react";
import Alert from "react-bootstrap/Alert";
import Badge from "react-bootstrap/Badge";
import Button from "react-bootstrap/Button";
import Card from "react-bootstrap/Card";
import Form from "react-bootstrap/Form";
import Modal from "react-bootstrap/Modal";
import Spinner from "react-bootstrap/Spinner";
import {Link} from "react-router-dom";

import type {ProjectRecord, ProjectSummary} from "../types";

interface ApiResponse {
    ok: boolean;
    error?: string;
    project?: ProjectRecord;
    projects?: ProjectSummary[];
}

interface NameDialog {
    kind: "create" | "rename" | "duplicate";
    project?: ProjectSummary;
}

async function apiRequest(path: string, options?: RequestInit): Promise<ApiResponse> {
    const response = await fetch(path, options);
    const payload = await response.json() as ApiResponse;
    if (!response.ok || !payload.ok) {
        throw new Error(payload.error || "Project action failed.");
    }
    return payload;
}

function ProjectsPage() {
    const fileInputRef = useRef<HTMLInputElement | null>(null);
    const [projects, setProjects] = useState<ProjectSummary[]>([]);
    const [includeArchived, setIncludeArchived] = useState(false);
    const [loading, setLoading] = useState(true);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [notice, setNotice] = useState<string | null>(null);
    const [nameDialog, setNameDialog] = useState<NameDialog | null>(null);
    const [name, setName] = useState("");
    const [deleteProject, setDeleteProject] = useState<ProjectSummary | null>(null);

    async function loadProjects(showArchived = includeArchived) {
        setLoading(true);
        try {
            const result = await apiRequest(
                `/api/projects${showArchived ? "?include_archived=true" : ""}`,
            );
            setProjects(result.projects || []);
            setError(null);
        } catch (loadError) {
            setError(loadError instanceof Error ? loadError.message : "Could not load projects.");
        } finally {
            setLoading(false);
        }
    }

    useEffect(() => {
        void loadProjects();
        // The toggle explicitly reloads with its next value.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    function openNameDialog(dialog: NameDialog) {
        setNameDialog(dialog);
        setName(
            dialog.kind === "rename"
                ? dialog.project?.name || ""
                : dialog.kind === "duplicate"
                    ? `${dialog.project?.name || "Project"} Copy`
                    : "",
        );
    }

    async function submitNameDialog(event: React.FormEvent) {
        event.preventDefault();
        if (!nameDialog) {
            return;
        }
        setBusy(true);
        setError(null);
        try {
            if (nameDialog.kind === "create") {
                await apiRequest("/api/projects", {
                    method: "POST",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({name}),
                });
                setNotice(`Created ${name.trim()}.`);
            } else if (nameDialog.kind === "rename" && nameDialog.project) {
                await apiRequest(`/api/projects/${nameDialog.project.id}`, {
                    method: "PATCH",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({
                        name,
                        expected_version: nameDialog.project.version,
                    }),
                });
                setNotice(`Renamed project to ${name.trim()}.`);
            } else if (nameDialog.project) {
                await apiRequest(
                    `/api/projects/${nameDialog.project.id}/duplicate`,
                    {
                        method: "POST",
                        headers: {"Content-Type": "application/json"},
                        body: JSON.stringify({
                            name,
                            expected_version: nameDialog.project.version,
                        }),
                    },
                );
                setNotice(`Duplicated project as ${name.trim()}.`);
            }
            setNameDialog(null);
            await loadProjects();
        } catch (actionError) {
            setError(actionError instanceof Error ? actionError.message : "Project action failed.");
        } finally {
            setBusy(false);
        }
    }

    async function setArchived(project: ProjectSummary, archived: boolean) {
        setBusy(true);
        try {
            await apiRequest(
                `/api/projects/${project.id}/${archived ? "archive" : "restore"}`,
                {
                    method: "POST",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({expected_version: project.version}),
                },
            );
            setNotice(`${archived ? "Archived" : "Restored"} ${project.name}.`);
            await loadProjects();
        } catch (actionError) {
            setError(actionError instanceof Error ? actionError.message : "Project action failed.");
        } finally {
            setBusy(false);
        }
    }

    async function permanentlyDelete() {
        if (!deleteProject) {
            return;
        }
        setBusy(true);
        try {
            await apiRequest(`/api/projects/${deleteProject.id}`, {
                method: "DELETE",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({expected_version: deleteProject.version}),
            });
            setNotice(`Permanently deleted ${deleteProject.name}.`);
            setDeleteProject(null);
            await loadProjects();
        } catch (actionError) {
            setError(actionError instanceof Error ? actionError.message : "Delete failed.");
        } finally {
            setBusy(false);
        }
    }

    async function importProject(event: React.ChangeEvent<HTMLInputElement>) {
        const file = event.target.files?.[0];
        if (!file) {
            return;
        }
        setBusy(true);
        try {
            const config = JSON.parse(await file.text()) as unknown;
            await apiRequest("/api/projects/import", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify(config),
            });
            setNotice(`Imported ${file.name}.`);
            await loadProjects();
        } catch (importError) {
            setError(importError instanceof Error ? importError.message : "Import failed.");
        } finally {
            setBusy(false);
            event.target.value = "";
        }
    }

    return (
        <main className="projects-page">
            <header className="projects-header">
                <div>
                    <p className="eyebrow">Floor Layout Planner</p>
                    <h1>Projects</h1>
                    <p>Create, import, and reopen floor-planning projects.</p>
                </div>
                <div className="projects-header-actions">
                    <Form.Check
                        checked={includeArchived}
                        id="showArchived"
                        label="Show archived"
                        onChange={event => {
                            const checked = event.target.checked;
                            setIncludeArchived(checked);
                            void loadProjects(checked);
                        }}
                        type="switch"
                    />
                    <input
                        accept="application/json,.json"
                        className="visually-hidden"
                        onChange={event => void importProject(event)}
                        ref={fileInputRef}
                        type="file"
                    />
                    <Button
                        disabled={busy}
                        onClick={() => fileInputRef.current?.click()}
                        variant="outline-secondary"
                    >
                        Import JSON
                    </Button>
                    <Button disabled={busy} onClick={() => openNameDialog({kind: "create"})}>
                        New project
                    </Button>
                </div>
            </header>

            {error && <Alert dismissible onClose={() => setError(null)} variant="danger">{error}</Alert>}
            {notice && <Alert dismissible onClose={() => setNotice(null)} variant="success">{notice}</Alert>}

            {loading ? (
                <div className="projects-loading"><Spinner size="sm" /> Loading projects…</div>
            ) : projects.length === 0 ? (
                <section className="projects-empty">
                    <h2>No projects found</h2>
                    <p>Create a project or import an existing JSON configuration.</p>
                    <Button onClick={() => openNameDialog({kind: "create"})}>Create project</Button>
                </section>
            ) : (
                <section className="project-grid" aria-label="Projects">
                    {projects.map(project => (
                        <Card className="project-card" key={project.id}>
                            <Card.Body>
                                <div className="project-card-heading">
                                    <div>
                                        <Card.Title>{project.name}</Card.Title>
                                        <Card.Subtitle>
                                            Updated {new Date(project.updated_at).toLocaleString()}
                                        </Card.Subtitle>
                                    </div>
                                    <Badge bg={project.archived ? "secondary" : "primary"}>
                                        {project.archived ? "Archived" : "Active"}
                                    </Badge>
                                </div>
                                <dl className="project-meta">
                                    <div><dt>Version</dt><dd>{project.version}</dd></div>
                                    <div><dt>Optimization</dt><dd>{project.optimization_status.replace("_", " ")}</dd></div>
                                </dl>
                                <div className="project-card-actions">
                                    {!project.archived && (
                                        <>
                                            <Link className="btn btn-primary btn-sm" to={`/projects/${project.id}`}>
                                                Open planner
                                            </Link>
                                            <Link className="btn btn-outline-primary btn-sm" to={`/projects/${project.id}/edit`}>
                                                Edit layout
                                            </Link>
                                        </>
                                    )}
                                    <Button onClick={() => openNameDialog({kind: "rename", project})} size="sm" variant="outline-secondary">Rename</Button>
                                    <Button onClick={() => openNameDialog({kind: "duplicate", project})} size="sm" variant="outline-secondary">Duplicate</Button>
                                    <Button as="a" href={`/api/projects/${project.id}/export`} size="sm" variant="outline-secondary">Export</Button>
                                    {project.archived ? (
                                        <>
                                            <Button disabled={busy} onClick={() => void setArchived(project, false)} size="sm" variant="outline-success">Restore</Button>
                                            <Button disabled={busy} onClick={() => setDeleteProject(project)} size="sm" variant="outline-danger">Delete</Button>
                                        </>
                                    ) : (
                                        <Button disabled={busy} onClick={() => void setArchived(project, true)} size="sm" variant="outline-warning">Archive</Button>
                                    )}
                                </div>
                            </Card.Body>
                        </Card>
                    ))}
                </section>
            )}

            <Modal centered onHide={() => !busy && setNameDialog(null)} show={Boolean(nameDialog)}>
                <Form onSubmit={event => void submitNameDialog(event)}>
                    <Modal.Header closeButton><Modal.Title>{nameDialog?.kind === "create" ? "New project" : nameDialog?.kind === "rename" ? "Rename project" : "Duplicate project"}</Modal.Title></Modal.Header>
                    <Modal.Body><Form.Group controlId="projectName"><Form.Label>Project name</Form.Label><Form.Control autoFocus onChange={event => setName(event.target.value)} required value={name} /></Form.Group></Modal.Body>
                    <Modal.Footer><Button disabled={busy} onClick={() => setNameDialog(null)} variant="outline-secondary">Cancel</Button><Button disabled={busy || !name.trim()} type="submit">{busy ? "Working…" : "Save"}</Button></Modal.Footer>
                </Form>
            </Modal>

            <Modal centered onHide={() => !busy && setDeleteProject(null)} show={Boolean(deleteProject)}>
                <Modal.Header closeButton><Modal.Title>Permanently delete project?</Modal.Title></Modal.Header>
                <Modal.Body>This permanently deletes <strong>{deleteProject?.name}</strong>. Export it first if you may need it again.</Modal.Body>
                <Modal.Footer><Button disabled={busy} onClick={() => setDeleteProject(null)} variant="outline-secondary">Cancel</Button><Button disabled={busy} onClick={() => void permanentlyDelete()} variant="danger">Permanently delete</Button></Modal.Footer>
            </Modal>
        </main>
    );
}

export default ProjectsPage;
