import { defineConfig } from '@playwright/test';
export default defineConfig({ testDir: './tests', workers:1, testIgnore: ['workspace.spec.ts', 'chat.spec.ts', 'card-viewer.spec.ts', 'vector.spec.ts', 'hybrid.spec.ts', 'reranking.spec.ts', 'filters.spec.ts', 'streaming.spec.ts', 'rewriting.spec.ts'], use: { baseURL: 'http://127.0.0.1:5173' }, webServer: [
 { command: 'uv run python -m magic_rag serve --port 8001', cwd: '..', port: 8001, env: {MAGIC_RAG_DB: './test-results/browser.db'}, reuseExistingServer: false },
 { command: 'npm run dev -- --port 5173 --strictPort', port: 5173, env: { MAGIC_RAG_API: 'http://127.0.0.1:8001' }, reuseExistingServer: false }
] });
