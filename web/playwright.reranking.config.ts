import { defineConfig } from '@playwright/test';
export default defineConfig({ testDir: './tests', testMatch: 'reranking.spec.ts', use: { baseURL: 'http://127.0.0.1:5205' }, webServer: [
 { command: 'uv run python backend/tests/reranker_browser_server.py', cwd: '..', port: 8105, env: {MAGIC_RAG_DB: './test-results/reranking-browser.db'}, reuseExistingServer: false },
 { command: 'npm run dev -- --port 5205 --strictPort', port: 5205, env: { MAGIC_RAG_API: 'http://127.0.0.1:8105' }, reuseExistingServer: false }
] });
