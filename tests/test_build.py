"""Сборка страницы: итоги, отпечаток данных, дата обновления, блок замечаний."""

from datetime import datetime, timedelta, timezone

import build

UTC_NOON = datetime(2026, 8, 26, 9, 0, tzinfo=timezone.utc)

ROWS = [
    {"Месяц": "Январь", "Заказы": "120", "Выручка": "340000"},
    {"Месяц": "Февраль", "Заказы": "145", "Выручка": "398000"},
]


def test_разряды_разделяются_пробелом():
    assert build.money(1109000) == "1 109 000"


def test_отпечаток_одинаковых_данных_совпадает():
    assert build.fingerprint(ROWS) == build.fingerprint(list(ROWS))


def test_отпечаток_меняется_вместе_с_цифрой():
    changed = [dict(ROWS[0], **{"Выручка": "340001"}), ROWS[1]]
    assert build.fingerprint(ROWS) != build.fingerprint(changed)


def test_дата_переводится_в_московское_время():
    state = None
    stamp = build.resolve_updated_at(ROWS, UTC_NOON, _tmp(state))
    assert stamp == "26.08.2026, 12:00"


def test_дата_не_меняется_пока_данные_те_же(tmp_path):
    state = tmp_path / "state.json"
    first = build.resolve_updated_at(ROWS, UTC_NOON, state)
    later = build.resolve_updated_at(ROWS, UTC_NOON + timedelta(hours=5), state)
    assert first == later


def test_дата_обновляется_когда_данные_изменились(tmp_path):
    state = tmp_path / "state.json"
    first = build.resolve_updated_at(ROWS, UTC_NOON, state)
    changed = [dict(ROWS[0], **{"Выручка": "999999"}), ROWS[1]]
    later = build.resolve_updated_at(changed, UTC_NOON + timedelta(hours=5), state)
    assert later != first
    assert later == "26.08.2026, 17:00"


def test_битый_файл_состояния_не_роняет_сборку(tmp_path):
    state = tmp_path / "state.json"
    state.write_text("не json", encoding="utf-8")
    assert build.resolve_updated_at(ROWS, UTC_NOON, state) == "26.08.2026, 12:00"


def test_без_замечаний_блока_нет():
    assert build.warnings_block([]) == ""


def test_замечания_попадают_на_страницу():
    block = build.warnings_block(["Первое", "Второе"])
    assert "2 замечания" in block
    assert "Первое" in block and "Второе" in block


def test_разметка_в_замечаниях_экранируется():
    assert "<b>" not in build.warnings_block(["<b>жирный</b>"])


def test_график_рисуется_и_подписывает_столбцы():
    svg = build.bar_chart(ROWS, "Месяц", "Выручка", "series-2")
    assert svg.startswith("<svg")
    assert "Январь" in svg and "340 000" in svg


def test_нулевые_значения_не_роняют_график():
    zero = [dict(row, **{"Выручка": "0"}) for row in ROWS]
    assert "<svg" in build.bar_chart(zero, "Месяц", "Выручка", "series-2")


def _tmp(_unused):
    """Путь, которого нет: проверяем поведение при отсутствующем состоянии."""
    import pathlib
    import tempfile

    return pathlib.Path(tempfile.mkdtemp()) / "state.json"
