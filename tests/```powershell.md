```powershell
cd tg-kruzhki-bot
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

Copy-Item .env.example .env
notepad .env 9087349662:AAHzZit_PMJG5KZr616DWsjTa_Q29vgeQGECHANNEL_ID, MAIN_CHANNEL_URL

.\.venv\Scripts\python.exe run.py
```