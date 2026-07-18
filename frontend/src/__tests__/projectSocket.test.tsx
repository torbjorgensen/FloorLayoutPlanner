import {act, renderHook} from "@testing-library/react";
import {afterEach, describe, expect, it, vi} from "vitest";

import {io} from "socket.io-client";
import {useProjectState} from "../hooks/useProjectState";
import type {ProjectState} from "../types";

const socketMock = vi.hoisted(() => {
    const handlers = new Map<string, (...args: never[]) => void>();
    const socket = {
        on: vi.fn((event: string, handler: (...args: never[]) => void) => {
            handlers.set(event, handler);
            return socket;
        }),
        disconnect: vi.fn(),
    };

    return {handlers, socket};
});

vi.mock("socket.io-client", () => ({
    io: vi.fn(() => socketMock.socket),
}));

const projectState: ProjectState = {
    project_name: "Socket project",
    board: {},
    rooms: [],
    bounds: {min_x: 0, min_y: 0, max_x: 1, max_y: 1},
    output_dir: "output",
    connections: [],
};

describe("useProjectState", () => {
    afterEach(() => {
        socketMock.handlers.clear();
        vi.clearAllMocks();
    });

    it("receives socket snapshots and exposes reconnect state", () => {
        const {result, rerender, unmount} = renderHook(
            ({projectId}) => useProjectState(projectId),
            {initialProps: {projectId: "project-1"}},
        );

        expect(result.current.connectionStatus).toBe("connecting");
        expect(vi.mocked(io)).toHaveBeenCalledWith(
            expect.objectContaining({
                auth: {project_id: "project-1"},
                transports: ["websocket", "polling"],
                tryAllTransports: true,
            }),
        );

        act(() => socketMock.handlers.get("connect")?.());
        expect(result.current.connectionStatus).toBe("connected");

        act(() =>
            socketMock.handlers.get("project_error")?.(
                {error: "Room geometry is disconnected"} as never,
            ),
        );
        expect(result.current.connectionError).toBe("Room geometry is disconnected");

        act(() =>
            socketMock.handlers.get("project_state")?.(projectState as never),
        );
        expect(result.current.state?.project_name).toBe("Socket project");

        act(() =>
            socketMock.handlers.get("connect_error")?.(
                new Error("backend unavailable") as never,
            ),
        );
        expect(result.current.connectionStatus).toBe("reconnecting");
        expect(result.current.connectionError).toBe("backend unavailable");
        act(() => socketMock.handlers.get("connect")?.());
        expect(result.current.connectionStatus).toBe("connected");
        expect(result.current.connectionError).toBeNull();
        expect(result.current.state?.project_name).toBe("Socket project");

        rerender({projectId: "project-2"});
        expect(result.current.state).toBeNull();
        expect(socketMock.socket.disconnect).toHaveBeenCalledOnce();
        expect(vi.mocked(io)).toHaveBeenLastCalledWith(
            expect.objectContaining({auth: {project_id: "project-2"}}),
        );

        unmount();
        expect(socketMock.socket.disconnect).toHaveBeenCalledTimes(2);
    });
});
