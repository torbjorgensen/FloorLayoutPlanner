import {io} from "socket.io-client";

const baseUrl = process.argv[2] ?? "http://127.0.0.1:8080";
const timeoutMs = 15_000;

// Force WebSocket so the smoke test catches broken Nginx upgrade handling;
// Socket.IO's normal polling fallback could otherwise hide that regression.
const socket = io(baseUrl, {
    transports: ["websocket"],
    reconnection: false,
    timeout: timeoutMs,
});

const timer = setTimeout(() => {
    socket.close();
    console.error("Timed out waiting for project_state over WebSocket");
    process.exit(1);
}, timeoutMs);

socket.on("project_state", (payload) => {
    if (!payload || !Array.isArray(payload.rooms)) {
        clearTimeout(timer);
        socket.close();
        console.error("WebSocket returned an invalid project_state payload");
        process.exit(1);
    }

    clearTimeout(timer);
    socket.close();
    console.log(`Received project_state for ${payload.rooms.length} room(s)`);
});

socket.on("connect_error", (error) => {
    clearTimeout(timer);
    socket.close();
    console.error(`WebSocket connection failed: ${error.message}`);
    process.exit(1);
});
