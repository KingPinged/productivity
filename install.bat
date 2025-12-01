@echo off
echo Installing Productivity Timer dependencies...
pip install -r requirements.txt

echo.
echo Creating icon...
python create_icon.py

echo.
echo Installation complete!
echo Run 'python run.py' or double-click start.bat to launch.
pause
