@echo off
echo Running website blocking test as Administrator...
powershell -Command "Start-Process python -ArgumentList 'test_blocking.py' -Verb RunAs -Wait"
pause
