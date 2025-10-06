@echo off
setlocal
pushd "%~dp0"

set "STREAMLIT_HOST=192.168.1.37"
set "STREAMLIT_PORT=8501"

if exist ".venv\Scripts\activate.bat" (
  call ".venv\Scripts\activate.bat"
)

echo Lanzando Streamlit...
python -m streamlit run st_app_final.py ^
  --server.address=%STREAMLIT_HOST% ^
  --server.port=%STREAMLIT_PORT% ^
  --server.enableCORS=false ^
  --server.enableXsrfProtection=false

echo.
echo Streamlit se ha cerrado. Pulsa una tecla para salir.
pause >nul
popd
endlocal
