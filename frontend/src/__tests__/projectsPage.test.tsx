import {cleanup, fireEvent, render, screen, waitFor} from "@testing-library/react";
import {afterEach, describe, expect, it, vi} from "vitest";

import App from "../App";

const project = {
    id: "project-1",
    name: "Ground floor",
    version: 3,
    archived: false,
    created_at: "2026-07-17T10:00:00Z",
    updated_at: "2026-07-17T11:00:00Z",
    optimization_status: "not_started",
};

function jsonResponse(payload: unknown, status = 200) {
    return Promise.resolve(new Response(JSON.stringify(payload), {
        status,
        headers: {"Content-Type": "application/json"},
    }));
}

describe("project dashboard", () => {
    afterEach(() => {
        cleanup();
        vi.restoreAllMocks();
        window.history.replaceState({}, "", "/");
    });

    it("lists projects and links to a stable planner route", async () => {
        vi.spyOn(globalThis, "fetch").mockImplementation(() =>
            jsonResponse({ok: true, projects: [project]}),
        );

        render(<App />);

        expect(await screen.findByText("Ground floor")).toBeInTheDocument();
        expect(screen.getByRole("link", {name: "Open planner"}))
            .toHaveAttribute("href", "/projects/project-1");
        expect(screen.getByText("not started")).toBeInTheDocument();
    });

    it("creates a named project and refreshes the list", async () => {
        const fetchMock = vi.spyOn(globalThis, "fetch")
            .mockImplementationOnce(() =>
                jsonResponse({ok: true, projects: [project]}),
            )
            .mockImplementationOnce((_input, options) => {
                expect(options?.method).toBe("POST");
                expect(JSON.parse(String(options?.body))).toEqual({name: "Upstairs"});
                return jsonResponse({ok: true, project: {...project, name: "Upstairs"}}, 201);
            })
            .mockImplementationOnce(() =>
                jsonResponse({ok: true, projects: [{...project, name: "Upstairs"}]}),
            );

        render(<App />);
        await screen.findByText("Ground floor");
        fireEvent.click(screen.getByRole("button", {name: "New project"}));
        fireEvent.change(screen.getByLabelText("Project name"), {
            target: {value: "Upstairs"},
        });
        fireEvent.click(screen.getByRole("button", {name: "Save"}));

        expect(await screen.findByText("Created Upstairs.")).toBeInTheDocument();
        await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    });

    it("archives using the current optimistic version", async () => {
        const fetchMock = vi.spyOn(globalThis, "fetch")
            .mockImplementationOnce(() =>
                jsonResponse({ok: true, projects: [project]}),
            )
            .mockImplementationOnce((_input, options) => {
                expect(options?.method).toBe("POST");
                expect(JSON.parse(String(options?.body))).toEqual({expected_version: 3});
                return jsonResponse({ok: true, project: {...project, archived: true, version: 4}});
            })
            .mockImplementationOnce(() =>
                jsonResponse({ok: true, projects: []}),
            );

        render(<App />);
        await screen.findByText("Ground floor");
        fireEvent.click(screen.getByRole("button", {name: "Archive"}));

        expect(await screen.findByText("Archived Ground floor.")).toBeInTheDocument();
        expect(fetchMock.mock.calls[1]?.[0]).toBe("/api/projects/project-1/archive");
    });
});
