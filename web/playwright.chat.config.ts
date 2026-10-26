import {defineConfig} from '@playwright/test';
export default defineConfig({testDir:'./tests',testMatch:['chat.spec.ts','card-viewer.spec.ts'],workers:1,use:{baseURL:'http://127.0.0.1:5231',permissions:['clipboard-read','clipboard-write']},webServer:[
 {command:'uv run python backend/tests/chat_browser_server.py',cwd:'..',port:8131,env:{MAGIC_RAG_DB:'./test-results/chat-browser.db'}},
 {command:'npm run dev -- --port 5231 --strictPort',port:5231,env:{MAGIC_RAG_API:'http://127.0.0.1:8131'}}
]});
