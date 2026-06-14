# botauto2 tutorial

This folder contains the version of the bot that saves entries to Google Sheets instead of writing to the local Excel file.

## What this project does

The bot connects to Telegram using your saved session, watches the target promotion groups, detects GPU and monitor deals by keyword and price, and appends the matches to a spreadsheet in Google Drive. It can also keep sending Telegram alerts if you leave `BOT_TOKEN` and `USER_ID` configured.

## 1. What you need first

You need these items before the bot can run:

- A Telegram API ID and API hash from my.telegram.org.
- A valid Telegram string session.
- A Google Cloud service account JSON key.
- A Google Spreadsheet already created in your Google Drive.
- Edit access granted on that spreadsheet to the service account email.

## 2. Configure the environment

Open [\.env.example](.env.example) and copy it to `.env`. Fill in the values like this:

```env
TELEGRAM_API_ID=123456
TELEGRAM_API_HASH=your_api_hash_here
TELEGRAM_STRING_SESSION=your_string_session_here
BOT_TOKEN=your_optional_bot_token_here
USER_ID=your_telegram_user_id_here
GOOGLE_SPREADSHEET_ID=your_spreadsheet_id_here
GOOGLE_SERVICE_ACCOUNT_FILE=C:\path\to\service-account.json
GOOGLE_SERVICE_ACCOUNT_JSON=
PORT=8080
```

Use either `GOOGLE_SERVICE_ACCOUNT_FILE` or `GOOGLE_SERVICE_ACCOUNT_JSON`.

If you use a file, point it to the downloaded JSON key. If you use JSON text, paste the full service-account JSON into `GOOGLE_SERVICE_ACCOUNT_JSON`.

## 3. Share the spreadsheet

Open the Google Spreadsheet you want to use and share it with the service account email from your Google Cloud JSON file. Without that step, the bot will not be able to create or update tabs.

## 4. Install dependencies

From inside the `botauto2` folder, install the packages:

```bash
pip install -r requirements.txt
```

## 5. Run the bot locally

Start the bot with:

```bash
python main.py
```

When it starts successfully, it will:

- connect to Telegram,
- open the Google Spreadsheet,
- create the expected tabs if they are missing,
- wait for new messages from the target groups,
- save matching rows to the spreadsheet,
- update the daily summary tabs.

## 6. What gets saved in Sheets

The bot uses these tabs:

- `Promocoes` for GPU matches.
- `Resumo Diario` for the GPU summary.
- `Monitores` for monitor matches.
- `Resumo Monitores` for the monitor summary.

## 7. How the matching works

The bot looks for a price in the message and then checks whether the text contains a known product keyword.

Examples:

- `5060` or `9060 XT` counts as a GPU match.
- `monitor` counts as a monitor match.
- The price must fall inside the configured range for that category.

## 8. Optional Telegram alerts

If `BOT_TOKEN` and `USER_ID` are filled in, the bot also sends you a Telegram message when it saves a matching offer. If you want Sheets only, you can leave those values empty.

## 9. Running on Render

The bot exposes a simple health check on the `PORT` you set in the environment. That makes it suitable for Render or a similar host that expects a web process to stay alive.

## 10. Common problems

If the bot does not write to the spreadsheet:

- Check that the spreadsheet was shared with the service account email.
- Check that `GOOGLE_SPREADSHEET_ID` is correct.
- Check that the service account file path exists.
- Check that the Telegram string session is valid.

If the bot starts but never saves rows:

- Make sure the monitored Telegram groups are still the same.
- Make sure the message includes both a price and a supported keyword.
- Check the log file `botauto2.log` for errors.
