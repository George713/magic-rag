import { defineConfig } from '@playwright/test';
export default defineConfig({testDir:'./tests',testMatch:'rewriting.spec.ts',use:{baseURL:'http://127.0.0.1:5211'},webServer:[
 {command:'uv run python backend/tests/rewrite_browser_server.py',cwd:'..',port:8111,env:{MAGIC_RAG_DB:'./test-results/rewriting.db'},reuseExistingServer:false},
 {command:'npm run dev -- --port 5211 --strictPort',port:5211,env:{MAGIC_RAG_API:'http://127.0.0.1:8111'},reuseExistingServer:false}
]});
