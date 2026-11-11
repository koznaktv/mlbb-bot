# MLBB Telegram Bot

## Files
- main.py: bot code
- requirements.txt: Python packages
- .env.example: environment variable template

## Replit setup
1. Upload these files to your Replit Python project.
2. In Shell run: `pip install -r requirements.txt`
3. Add Secrets (Tools -> Secrets):
   - BOT_TOKEN = your NEW Telegram bot token
   - CHANNEL_ID = @your_channel_username or the numeric channel ID
4. Add the bot to your Telegram channel as an administrator with permission to post messages.
5. Run `python main.py`.

Do not publish your token in code, screenshots, GitHub, or chat. Since your earlier token was exposed, revoke it with BotFather and use a newly generated token.

## Notes
- Account search by price means: show accounts priced at or below the amount entered (up to 10 results).
- Account photos/video are Telegram file IDs stored in SQLite.
- SQLite data persists only as long as the host preserves the project filesystem.
- This bot does not request account passwords, login codes, or other private credentials.
