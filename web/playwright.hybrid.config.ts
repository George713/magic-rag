import { defineConfig } from '@playwright/test';
export default defineConfig({ testDir: './tests', testMatch: 'hybrid.spec.ts', use: { baseURL: 'http://127.0.0.1:5204' }, webServer: [
 { command: 'uv run python backend/tests/hybrid_browser_server.py', cwd: '..', port: 8104, env: {MAGIC_RAG_DB: './test-results/hybrid-browser.db'}, reuseExistingServer: false },
 { command: 'npm run dev -- --port 5204 --strictPort', port: 5204, env: { MAGIC_RAG_API: 'http://127.0.0.1:8104' }, reuseExistingServer: false }
] });
