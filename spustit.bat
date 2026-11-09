@echo off
chcp 65001 >nul
rem Prejde do slozky, kde lezi tento soubor (at se spusti odkudkoli)
cd /d "%~dp0"
echo Kontroluji potrebne knihovny...
python -m pip install -q -r requirements.txt
python hledani.py
