import { defineConfig } from '@playwright/test';
export default defineConfig({testDir:'./tests',testMatch:'workspace.spec.ts',workers:1,use:{baseURL:'http://127.0.0.1:5230'},webServer:[
{command:'uv run python -m magic_rag serve --port 8130',cwd:'..',port:8130,env:{PYTHONPATH:'./backend',MAGIC_RAG_DB:'./test-results/browser.db'}},
{command:'npm run dev -- --port 5230 --strictPort',port:5230,env:{MAGIC_RAG_API:'http://127.0.0.1:8130'}}]});
