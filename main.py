from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Sequence

import requests
from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.sessions import StringSession

from sheets_store import GoogleSheetsStore, SheetLayout

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("botauto2.log", encoding="utf-8")],
)

TARGET_GROUPS = ["ofertasepromoaquibr", "TJGOFERTASs", "promomarks", "pobregram", "urubupromo", "ofertagpu"]

GPU_RULES = [
    {"keywords": ("9060xt 16gb", "9060 xt 16gb", "9060xt 16 gb", "9060 xt 16 gb"), "name": "9060 XT", "min": 1400, "max": 4000},
    {"keywords": ("5060",), "name": "5060", "min": 1200, "max": 3500},
    {"keywords": ("5060ti 16gb", "5060 ti 16gb", "5060ti 16 gb", "5060 ti 16 gb"), "name": "5060 TI 16GB", "min": 1400, "max": 4500}
]

PROMO_LAYOUT = SheetLayout("Promocoes", ["Data e Hora", "Grupo", "Mensagem", "Produto", "Preco", "Link"])
SUMMARY_LAYOUT = SheetLayout("Resumo Diario", ["Data", "Produto", "Menor Preco", "Preco Medio", "Total de Ofertas"])


def clean_value(value: str | None) -> str:
    return (value or "").strip().strip("'\"\n\r")


def require_env(name: str) -> str:
    value = clean_value(os.getenv(name))
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def load_optional_json(value: str | None) -> dict | None:
    cleaned = clean_value(value)
    if not cleaned:
        return None
    if os.path.exists(cleaned):
        with open(cleaned, "r", encoding="utf-8") as handle:
            return json.load(handle)
    return json.loads(cleaned)


def extract_price(price_text: str) -> float:
    numbers = re.sub(r"[^\d,\.]", "", price_text).rstrip(".,")
    if not numbers:
        return 0.0

    if "." in numbers and "," in numbers:
        if numbers.rfind(",") > numbers.rfind("."):
            numbers = numbers.replace(".", "").replace(",", ".")
        else:
            numbers = numbers.replace(",", "")
    elif "," in numbers:
        numbers = numbers.replace(",", "") if len(numbers.split(",")[-1]) == 3 else numbers.replace(",", ".")
    elif "." in numbers and len(numbers.split(".")[-1]) == 3:
        numbers = numbers.replace(".", "")

    try:
        return float(numbers)
    except ValueError:
        return 0.0


def compact_text(text: str) -> str:
    return re.sub(r"\s+", "", text.lower())


def keyword_matches(message_text: str, keywords: Sequence[str]) -> bool:
    compact_message = compact_text(message_text)
    return any(compact_text(keyword) in compact_message for keyword in keywords)


def build_message_link(chat, message_id: int) -> str:
    username = getattr(chat, "username", None)
    if username:
        return f"https://t.me/{username}/{message_id}"

    chat_id = str(getattr(chat, "id", "")).replace("-100", "")
    return f"https://t.me/c/{chat_id}/{message_id}"


def get_group_name(chat, fallback: str) -> str:
    username = getattr(chat, "username", None)
    return username or fallback



def send_telegram_alert(token: str | None, user_id: str | None, message: str) -> None:
    if not token or not user_id:
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        requests.post(
            url,
            data={
                "chat_id": user_id,
                "text": message,
                "parse_mode": "html",
                "disable_web_page_preview": True,
            },
            timeout=15,
        )
    except Exception as exc:
        logging.error("Telegram notification failed: %s", exc)


@dataclass(frozen=True)
class MatchResult:
    category: str
    product_name: str
    price: float


class PromotionBot:
    def __init__(self) -> None:
        self.api_id = int(require_env("TELEGRAM_API_ID"))
        self.api_hash = require_env("TELEGRAM_API_HASH")
        self.string_session = require_env("TELEGRAM_STRING_SESSION")
        self.telegram_token = clean_value(os.getenv("BOT_TOKEN")) or None
        self.telegram_user_id = clean_value(os.getenv("USER_ID")) or None
        self.spreadsheet_id = require_env("GOOGLE_SPREADSHEET_ID")
        self.service_account_file = clean_value(os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")) or None
        self.service_account_json = clean_value(os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")) or None
        self.client = TelegramClient(StringSession(self.string_session), self.api_id, self.api_hash)
        self.store = GoogleSheetsStore(
            spreadsheet_id=self.spreadsheet_id,
            service_account_file=self.service_account_file,
            service_account_json=self.service_account_json,
        )
        self.store.ensure_layouts([PROMO_LAYOUT, SUMMARY_LAYOUT])

    def find_matches(self, message_text: str) -> list[MatchResult]:
        matches: list[MatchResult] = []

        for line in message_text.splitlines():
            line_lower = line.lower().strip()
            if not line_lower:
                continue

            price_match = re.search(r"r\$\s*\d+(?:[\.,]\d+)*", line_lower)
            if not price_match:
                continue

            price = extract_price(price_match.group(0))
            if price <= 0:
                continue

            for rule in GPU_RULES:
                if keyword_matches(line_lower, rule["keywords"]) and rule["min"] <= price <= rule["max"]:
                    matches.append(MatchResult("gpu", rule["name"], price))

        return matches

    def save_match(self, match: MatchResult, message_text: str, group_name: str, timestamp: str, link: str) -> None:
        day = timestamp.split(" ")[0]

        self.store.append_row("Promocoes", [timestamp, group_name, message_text, match.product_name, match.price, link])
        self.store.upsert_daily_summary("Resumo Diario", day, match.product_name, match.price)

    def format_alert(self, match: MatchResult, group_name: str, link: str) -> str:
        return (
            "🔥 <b>ALERTA DE PRECO BAIXO (GPU)</b> 🔥\n\n"
            f"🎮 <b>Produto:</b> {match.product_name}\n"
            f"💰 <b>Valor:</b> R$ {match.price:.2f}\n"
            f"📍 <b>Grupo:</b> {group_name}\n\n"
            f"🔗 <a href='{link}'>🛒 Ver Oferta</a>"
        )

    async def handle_message(self, event) -> None:
        message_text = event.raw_text
        if not message_text:
            return

        matches = self.find_matches(message_text)
        if not matches:
            return

        group_name = get_group_name(event.chat, "Grupo Privado")
        timestamp = datetime.now().strftime("%d/%m/%Y %H:%M")
        link = build_message_link(event.chat, event.id)

        for match in matches:
            await asyncio.to_thread(self.save_match, match, message_text, group_name, timestamp, link)
            logging.info("Saved %s match: %s at R$ %.2f", match.category, match.product_name, match.price)
            alert_text = self.format_alert(match, group_name, link)
            await asyncio.to_thread(send_telegram_alert, self.telegram_token, self.telegram_user_id, alert_text)

    async def health_check(self, reader, writer) -> None:
        response = "HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 2\r\n\r\nOK"
        writer.write(response.encode("utf-8"))
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    async def run(self) -> None:
        @self.client.on(events.NewMessage(chats=TARGET_GROUPS))
        async def on_new_message(event):
            await self.handle_message(event)

        await self.client.start()
        logging.info("Telegram connection established.")

        port = int(clean_value(os.getenv("PORT")) or "8080")
        server = await asyncio.start_server(self.health_check, "0.0.0.0", port)
        logging.info("Health check server listening on port %s.", port)

        async with server:
            await self.client.run_until_disconnected()


async def main() -> None:
    bot = PromotionBot()
    await bot.run()


if __name__ == "__main__":
    if os.name == "nt":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
