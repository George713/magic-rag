import { defineConfig } from '@playwright/test';
process.env.MAGIC_RAG_TEST_DB = './test-results/conversations.db';
export default defineConfig({testDir:'./tests',testMatch:'conversations.spec.ts',use:{baseURL:'http://127.0.0.1:5207'},webServer:[
 {command:'uv run python -m magic_rag serve --port 8107',cwd:'..',port:8107,env:{MAGIC_RAG_DB:'./test-results/conversations.db'},reuseExistingServer:false},
 {command:'npm run dev -- --port 5207 --strictPort',port:5207,env:{MAGIC_RAG_API:'http://127.0.0.1:8107'},reuseExistingServer:false}
]});
