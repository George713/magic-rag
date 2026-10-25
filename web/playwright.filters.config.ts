import { defineConfig } from '@playwright/test';
export default defineConfig({testDir:'./tests',testMatch:'filters.spec.ts',use:{baseURL:'http://127.0.0.1:5206'},webServer:[
 {command:'uv run python backend/tests/filter_browser_server.py',cwd:'..',port:8106,env:{MAGIC_RAG_DB:'./test-results/filters.db'},reuseExistingServer:false},
 {command:'npm run dev -- --port 5206 --strictPort',port:5206,env:{MAGIC_RAG_API:'http://127.0.0.1:8106'},reuseExistingServer:false}
]});
