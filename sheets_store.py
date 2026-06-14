from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from typing import Iterable, Sequence

import gspread
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


@dataclass(frozen=True)
class SheetLayout:
    name: str
    headers: Sequence[str]


class GoogleSheetsStore:
    def __init__(self, *, spreadsheet_id: str, service_account_file: str | None = None, service_account_json: str | None = None) -> None:
        self._lock = threading.Lock()
        self._spreadsheet_id = spreadsheet_id.strip()
        self._client = self._build_client(service_account_file, service_account_json)
        self._spreadsheet = self._client.open_by_key(self._spreadsheet_id)

    @staticmethod
    def _build_client(service_account_file: str | None, service_account_json: str | None) -> gspread.Client:
        if service_account_file:
            return gspread.authorize(
                Credentials.from_service_account_file(service_account_file, scopes=SCOPES)
            )

        if service_account_json:
            return gspread.authorize(
                Credentials.from_service_account_info(json.loads(service_account_json), scopes=SCOPES)
            )

        raise ValueError(
            "Google Sheets credentials not configured. Set GOOGLE_SERVICE_ACCOUNT_FILE or GOOGLE_SERVICE_ACCOUNT_JSON."
        )

    def ensure_layouts(self, layouts: Iterable[SheetLayout]) -> None:
        with self._lock:
            for layout in layouts:
                self._ensure_sheet(layout.name, layout.headers)

    def _ensure_sheet(self, sheet_name: str, headers: Sequence[str]) -> gspread.Worksheet:
        try:
            worksheet = self._spreadsheet.worksheet(sheet_name)
        except gspread.WorksheetNotFound:
            worksheet = self._spreadsheet.add_worksheet(title=sheet_name, rows=1000, cols=max(len(headers), 8))
            worksheet.append_row(list(headers), value_input_option="USER_ENTERED")
            return worksheet

        values = worksheet.get_all_values()
        if not values:
            worksheet.append_row(list(headers), value_input_option="USER_ENTERED")
        return worksheet

    def append_row(self, sheet_name: str, values: Sequence[object]) -> None:
        with self._lock:
            worksheet = self._spreadsheet.worksheet(sheet_name)
            worksheet.append_row(list(values), value_input_option="USER_ENTERED")

    def upsert_daily_summary(self, sheet_name: str, day_value: str, product: str, price: float) -> None:
        with self._lock:
            worksheet = self._spreadsheet.worksheet(sheet_name)
            rows = worksheet.get_all_values()

            matched_row_index = None
            for row_index, row in enumerate(rows[1:], start=2):
                if len(row) >= 5 and row[0] == day_value and row[1] == product:
                    matched_row_index = row_index
                    break

            if matched_row_index is None:
                worksheet.append_row([day_value, product, price, price, 1], value_input_option="USER_ENTERED")
                return

            current_min = self._safe_float(worksheet.cell(matched_row_index, 3).value)
            current_avg = self._safe_float(worksheet.cell(matched_row_index, 4).value)
            current_count = int(self._safe_float(worksheet.cell(matched_row_index, 5).value) or 0)

            new_count = current_count + 1
            new_min = min(current_min, price)
            new_avg = ((current_avg * current_count) + price) / new_count if current_count else price

            worksheet.update_cell(matched_row_index, 3, new_min)
            worksheet.update_cell(matched_row_index, 4, new_avg)
            worksheet.update_cell(matched_row_index, 5, new_count)

    @staticmethod
    def _safe_float(value: object) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0
