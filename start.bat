@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo === Подготовка окружения ===
if not exist ".venv\Scripts\python.exe" (
    echo Создаю виртуальное окружение...
    python -m venv .venv
    if errorlevel 1 (
        echo.
        echo Python не найден. Установи Python 3.11+ и запусти снова.
        pause
        exit /b 1
    )
)

.venv\Scripts\python.exe -m pip install --quiet --upgrade pip
.venv\Scripts\python.exe -m pip install --quiet -r requirements.txt
if errorlevel 1 (
    echo Не удалось установить зависимости. Проверь интернет.
    pause
    exit /b 1
)

if not exist ".env" copy ".env.example" ".env" >nul

echo.
echo === Проверка настроек ===
.venv\Scripts\python.exe tools\check_setup.py
if errorlevel 1 (
    echo.
    echo === НАСТРОЙКА (отвечай на вопросы ниже) ===
    .venv\Scripts\python.exe setup_env.py
    if errorlevel 1 (
        pause
        exit /b 1
    )
)

echo.
echo === Проверка каналов и прав бота ===
.venv\Scripts\python.exe tools\check_bot.py
if errorlevel 1 (
    echo.
    echo Бот запустится, но часть каналов настроена неверно - смотри выше.
    pause
)

echo.
echo === Запуск бота ===
.venv\Scripts\python.exe run.py
echo.
echo Бот остановлен.
pause