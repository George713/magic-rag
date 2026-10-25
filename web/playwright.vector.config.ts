import { defineConfig } from '@playwright/test';
export default defineConfig({ testDir: './tests', testMatch: 'vector.spec.ts', use: { baseURL: 'http://127.0.0.1:5203' }, webServer: [
 { command: 'uv run python backend/tests/vector_browser_server.py', cwd: '..', port: 8103, env: {MAGIC_RAG_DB: './test-results/vector-browser.db'}, reuseExistingServer: false },
 { command: 'npm run dev -- --port 5203 --strictPort', port: 5203, env: { MAGIC_RAG_API: 'http://127.0.0.1:8103' }, reuseExistingServer: false }
] });
