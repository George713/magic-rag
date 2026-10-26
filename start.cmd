@echo off
setlocal
pushd "%~dp0"
uv run --env-file .env --extra models --python 3.11 python -m magic_rag.dev %*
set "result=%ERRORLEVEL%"
popd
exit /b %result%
