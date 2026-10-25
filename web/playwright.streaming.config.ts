import { defineConfig } from '@playwright/test';
export default defineConfig({testDir:'./tests',testMatch:'streaming.spec.ts',workers:1,use:{baseURL:'http://127.0.0.1:5210'},webServer:[
 {command:'uv run python backend/tests/stream_browser_server.py',cwd:'..',port:8100,env:{MAGIC_RAG_DB:'./test-results/stream-browser.db'},reuseExistingServer:false},
 {command:'npm run dev -- --port 5210 --strictPort',port:5210,env:{MAGIC_RAG_API:'http://127.0.0.1:8100'},reuseExistingServer:false}
]});
