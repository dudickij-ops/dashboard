"""Источник данных для дашборда.

Пока данные выдуманные. Когда появится Google-таблица и ключ,
меняется только функция load_rows() — всё остальное не трогаем.
"""

import csv
import io
import os
import pathlib
import urllib.parse
import urllib.request


def _load_env_file() -> None:
    """Читает .env рядом со скриптом. Файл в .gitignore — в репозиторий не попадёт."""
    path = pathlib.Path(__file__).parent / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


_load_env_file()

# Ни ключ, ни адрес таблицы в код не вписываются: репозиторий публичный,
# а ссылка на таблицу — тоже доступ. Без .env код работает на выдуманных данных.
SHEET_ID = os.environ.get("SHEET_ID", "")
API_KEY = os.environ.get("GOOGLE_API_KEY", "")
SHEET_RANGE = os.environ.get("SHEET_RANGE", "Лист1!A1:C100")

MOCK_CSV = """Месяц,Заказы,Выручка
Январь,120,340000
Февраль,145,398000
Март,132,371000
Апрель,178,502000
Май,190,545000
Июнь,165,471000
Июль,203,588000
Август,221,634000
"""


def _rows_from_csv(text: str) -> list[dict]:
    """Обрезает пробелы по краям: в таблицах их набивают руками и не замечают."""
    reader = csv.DictReader(io.StringIO(text.strip()))
    return [
        {(k or "").strip(): (v or "").strip() for k, v in row.items()}
        for row in reader
    ]


def load_mock_rows() -> list[dict]:
    """Выдуманные данные. Работают всегда, ключ не нужен."""
    return _rows_from_csv(MOCK_CSV)


def load_sheet_rows() -> list[dict]:
    """Настоящие данные из Google-таблицы. Нужны SHEET_ID и GOOGLE_API_KEY."""
    if not SHEET_ID or not API_KEY:
        raise RuntimeError(
            "Нет SHEET_ID или GOOGLE_API_KEY. "
            "Задай их переменными окружения перед запуском."
        )

    encoded_range = urllib.parse.quote(SHEET_RANGE)
    url = (
        f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}"
        f"/values/{encoded_range}?key={API_KEY}"
    )

    with urllib.request.urlopen(url, timeout=15) as response:
        payload = response.read().decode("utf-8")

    import json

    values = json.loads(payload).get("values", [])
    if not values:
        return []

    header, *body = values
    return [dict(zip(header, row)) for row in body]


def load_csv_rows() -> list[dict]:
    """Таблица, открытая по ссылке, отдаёт себя как CSV. Ключ не нужен."""
    url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv"
    with urllib.request.urlopen(url, timeout=15) as response:
        return _rows_from_csv(response.read().decode("utf-8"))


def source_name() -> str:
    if SHEET_ID and API_KEY:
        return "Google Sheets API (по ключу)"
    if SHEET_ID:
        return "Google-таблица (CSV по ссылке)"
    return "выдуманные данные"


def check_rows(rows: list[dict], label_col: str, value_cols: list[str]) -> list[str]:
    """Ищет то, что сломает картинку. Ничего не чинит — только называет вслух.

    Правило: подозрительные данные показываем, а не прячем и не угадываем
    за клиента, что он имел в виду.
    """
    if not rows:
        return ["Таблица пустая — читать нечего."]

    problems = _check_labels(rows, label_col)
    for col in value_cols:
        problems += _check_column(rows, label_col, col)
    return problems


def _check_labels(rows: list[dict], label_col: str) -> list[str]:
    """Пустые и повторяющиеся подписи: и то и другое ломает ось."""
    problems: list[str] = []
    seen: set[str] = set()

    for row in rows:
        name = row.get(label_col, "")
        if not name:
            problems.append(f"Есть строка без значения в «{label_col}».")
        elif name in seen:
            problems.append(f"«{name}» встречается больше одного раза.")
        else:
            seen.add(name)

    return problems


# Во сколько раз значение должно превысить медиану, чтобы счесть его выбросом.
OUTLIER_FACTOR = 50

# Насколько значение должно оказаться НИЖЕ медианы. Порог мягче верхнего:
# слабый месяц бывает, а вот значение в тысячу раз меньше — это потерянные цифры.
OUTLIER_LOW_FACTOR = 1000


def _check_column(rows: list[dict], label_col: str, col: str) -> list[str]:
    """Нечисловые, пустые и выбросы в одной числовой колонке."""
    problems: list[str] = []
    numbers: list[tuple[str, int]] = []

    for row in rows:
        name = row.get(label_col, "?")
        raw = row.get(col, "")
        if raw == "":
            problems.append(f"«{name}»: пустое значение в «{col}».")
            continue
        try:
            value = int(raw)
        except ValueError:
            problems.append(f"«{name}»: «{raw}» в «{col}» — не число.")
            continue

        # Отрицательное неверно само по себе, без оглядки на остальные месяцы.
        if value < 0:
            problems.append(f"«{name}»: {value} в «{col}» — отрицательное значение.")
        numbers.append((name, value))

    return problems + _check_outliers(numbers, col)


def _check_outliers(numbers: list[tuple[str, int]], col: str) -> list[str]:
    """Сравниваем с медианой, а не со средним: среднее сам выброс и утаскивает."""
    if len(numbers) < 3:
        return []

    ordered = sorted(value for _, value in numbers)
    median = ordered[len(ordered) // 2]
    if median <= 0:
        return []

    problems: list[str] = []

    for name, value in numbers:
        if value > median * OUTLIER_FACTOR:
            problems.append(
                f"«{name}»: {value:,} в «{col}» — в {value // median:,} раз больше "
                f"остальных. Похоже на лишние нули.".replace(",", " ")
            )
        elif value == 0:
            problems.append(
                f"«{name}»: ноль в «{col}», у остальных месяцев около "
                f"{median:,}. Проверьте.".replace(",", " ")
            )
        elif 0 < value * OUTLIER_LOW_FACTOR < median:
            problems.append(
                f"«{name}»: {value:,} в «{col}» — в {median // value:,} раз меньше "
                f"остальных. Похоже на потерянные цифры.".replace(",", " ")
            )

    return problems


def load_rows() -> list[dict]:
    """Настоящие данные, если настроены. Иначе выдуманные."""
    if SHEET_ID and API_KEY:
        return load_sheet_rows()
    if SHEET_ID:
        return load_csv_rows()
    return load_mock_rows()


if __name__ == "__main__":
    rows = load_rows()
    print(f"Источник: {source_name()}")
    print(f"Строк: {len(rows)}")
    for row in rows:
        print(" ", row)
