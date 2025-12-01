@echo off
echo Installing dependencies...
pip install -r requirements.txt

echo.
echo Creating icon...
python create_icon.py

echo.
echo Starting Productivity Timer...
python run.py
