import {defineConfig} from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
    plugins: [react()],
    server: {
        host: "127.0.0.1",
        port: 5173,
        proxy: {
            "/socket.io": {
                target:
                    process.env.VITE_API_PROXY_TARGET
                    || "http://127.0.0.1:8765",
                changeOrigin: true,
                ws: true,
                rewriteWsOrigin: true,
            },
            "/api": {
                target:
                    process.env.VITE_API_PROXY_TARGET
                    || "http://127.0.0.1:8765",
                changeOrigin: true,
            },
        },
    },
    test: {
        environment: "jsdom",
        setupFiles: "./src/test/setup.ts",
    },
    build: {
        outDir: "dist",
        emptyOutDir: true,
    },
});
