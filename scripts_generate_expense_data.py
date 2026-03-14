#!/usr/bin/env python3
"""Generate browser-consumable expense data from expenses/expense_log.md.

Source of truth remains expenses/expense_log.md.
Run:
    python3 scripts_generate_expense_data.py
Outputs:
    expenses/expense_data.js
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "expenses" / "expense_log.md"
OUTPUT = ROOT / "expenses" / "expense_data.js"

CATEGORY_MAP = {
    "机票": "flight",
    "住宿": "hotel",
    "餐饮": "meal",
    "交通": "transport",
    "门票/景点": "ticket",
    "其他": "other",
}

CATEGORY_LABELS = {
    "flight": {"zh": "机票", "en": "Flights"},
    "hotel": {"zh": "住宿", "en": "Hotels"},
    "meal": {"zh": "餐饮", "en": "Meals"},
    "transport": {"zh": "交通", "en": "Transport"},
    "ticket": {"zh": "门票/景点", "en": "Tickets / Attractions"},
    "other": {"zh": "其他", "en": "Other"},
}

HOUSEHOLDS = [
    {"id": "mav", "name": {"zh": "Mav家", "en": "Mav Household"}, "members": ["Mav", "严正"]},
    {"id": "chan", "name": {"zh": "Chan家", "en": "Chan Household"}, "members": ["Chan", "Chan配偶"]},
    {"id": "ling", "name": {"zh": "Ling家", "en": "Ling Household"}, "members": ["Ling", "Ling配偶"]},
    {"id": "anita", "name": {"zh": "Anita家", "en": "Anita Household"}, "members": ["Anita", "Benson"]},
    {"id": "zhongxin", "name": {"zh": "仲欣", "en": "Zhong Xin"}, "members": ["仲欣"]},
]

GROUP_ALIASES = {
    "8人": ["mav", "chan", "ling", "anita"],
    "7人": ["mav", "chan", "ling", "anita"],
    "Mav家": ["mav"],
    "Chan家": ["chan"],
    "Ling家": ["ling"],
    "Anita家": ["anita"],
    "仲欣": ["zhongxin"],
}

# Default interpretation for current ledger strings.
PARTICIPANT_NOTES = {
    "8人": {
        "zh": "按 4 家共 8 人分摊：Mav+严正、Chan夫妇、Ling夫妇、Anita+Benson",
        "en": "Split across 4 households / 8 people: Mav+Yan Zheng, Chan couple, Ling couple, Anita+Benson",
    },
    "7人": {
        "zh": "同行 8 人中 Benson 未参与消费，网页暂仍按 4 家显示明细；结算可切换按人查看",
        "en": "Benson did not consume this item. Detail remains visible under the 4-household group; switch to per-person view for fine-grained settlement.",
    },
}


def parse_money(value: str) -> float:
    m = re.search(r"([\d,.]+)", value)
    return float(m.group(1).replace(",", "")) if m else 0.0


def split_row(row: str) -> list[str]:
    return [cell.strip() for cell in row.strip().strip("|").split("|")]


def infer_participants(raw: str, category_key: str) -> tuple[list[str], str]:
    raw = raw.strip()
    households = GROUP_ALIASES.get(raw)
    split_mode = "household"
    if households:
        if raw == "7人":
            split_mode = "person"
        return households, split_mode
    return [], "household"


def build_entry(category_cn: str, headers: list[str], values: list[str]) -> dict:
    row = dict(zip(headers, values))
    category_key = CATEGORY_MAP[category_cn]
    amount = 0.0
    payer = row.get("付费人") or row.get("人员") or ""
    participants_raw = row.get("参与者") or row.get("住宿者") or row.get("人员") or ""
    households, split_mode = infer_participants(participants_raw, category_key)

    if category_cn == "餐饮":
        title = row.get("地点/餐厅", "")
        subtitle = row.get("用餐类型", "")
        amount = parse_money(row.get("费用", "0"))
    elif category_cn == "交通":
        title = row.get("路线", "")
        subtitle = row.get("类型", "")
        amount = parse_money(row.get("费用", "0"))
    elif category_cn == "住宿":
        title = row.get("酒店", "")
        subtitle = f"{row.get('房型', '')} · {row.get('晚数', '')}晚".strip(" ·")
        amount = parse_money(row.get("总费用", row.get("费用/晚", "0")))
    elif category_cn == "机票":
        title = row.get("路线", "")
        subtitle = row.get("航班号", "")
        amount = parse_money(row.get("费用", "0"))
    elif category_cn == "门票/景点":
        title = row.get("景点", "")
        subtitle = ""
        amount = parse_money(row.get("费用", "0"))
    else:
        title = row.get("项目", "")
        subtitle = row.get("说明", "")
        amount = parse_money(row.get("费用", "0"))

    return {
        "date": row.get("日期", ""),
        "category": category_key,
        "categoryLabel": CATEGORY_LABELS[category_key],
        "title": title,
        "subtitle": subtitle,
        "payer": payer,
        "participantsRaw": participants_raw,
        "households": households,
        "splitMode": split_mode,
        "amount": amount,
        "notes": PARTICIPANT_NOTES.get(participants_raw),
        "raw": row,
    }


def parse_markdown_tables(text: str) -> list[dict]:
    entries: list[dict] = []
    current_category = None
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        h = re.match(r"^###\s+(.+)$", line)
        if h:
            current_category = h.group(1).strip()
            i += 1
            continue
        if current_category in CATEGORY_MAP and line.strip().startswith("|"):
            headers = split_row(line)
            if i + 1 < len(lines) and lines[i + 1].strip().startswith("|---"):
                i += 2
                while i < len(lines) and lines[i].strip().startswith("|"):
                    values = split_row(lines[i])
                    if len(values) == len(headers) and any(v for v in values):
                        entry = build_entry(current_category, headers, values)
                        if entry["amount"] > 0:
                            entries.append(entry)
                    i += 1
                continue
        i += 1
    return entries


def main() -> None:
    text = SOURCE.read_text(encoding="utf-8")
    entries = parse_markdown_tables(text)
    payload = {
        "source": "expenses/expense_log.md",
        "generatedAt": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "households": HOUSEHOLDS,
        "entries": entries,
    }
    OUTPUT.write_text(
        "// Auto-generated from expenses/expense_log.md by scripts_generate_expense_data.py\n"
        f"window.EXPENSE_DATA = {json.dumps(payload, ensure_ascii=False, indent=2)};\n",
        encoding="utf-8",
    )
    print(f"Generated {OUTPUT} with {len(entries)} entries")


if __name__ == "__main__":
    main()
