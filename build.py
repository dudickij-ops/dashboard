"""Собирает index.html из данных таблицы.

Запуск:  python3 build.py
Результат: index.html рядом со скриптом.
"""

import html
import pathlib

from data import load_rows, source_name

OUT = pathlib.Path(__file__).parent / "index.html"

# Цвета проверены валидатором палитры в обоих режимах.
SERIES = {
    "Заказы": {"light": "#2a78d6", "dark": "#3987e5"},
    "Выручка": {"light": "#eb6834", "dark": "#d95926"},
}


def money(value: int) -> str:
    return f"{value:,}".replace(",", " ")


def bar_chart(rows: list[dict], label_col: str, value_col: str, slot: str) -> str:
    """Столбики. Округление 4px только сверху — низ прижат к базовой линии."""
    values = [int(row[value_col]) for row in rows]
    labels = [row[label_col] for row in rows]

    width, height = 400, 240
    pad_l, pad_r, pad_t, pad_b = 8, 8, 30, 30
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b
    base_y = pad_t + plot_h

    gap = 10
    n = len(values)
    # Марки тонкие: столбик не шире 56, группа центрируется в области графика.
    bar_w = min(56, (plot_w - gap * (n - 1)) / n) if n else plot_w
    group_w = bar_w * n + gap * (n - 1)
    offset = pad_l + (plot_w - group_w) / 2
    top = max(values) if values else 1
    radius = 4

    parts = []

    for line in range(1, 4):
        y = pad_t + plot_h * line / 4
        parts.append(
            f'<line x1="{pad_l}" y1="{y:.1f}" x2="{width - pad_r}" y2="{y:.1f}" '
            f'class="grid"/>'
        )

    for i, (label, value) in enumerate(zip(labels, values)):
        x = offset + i * (bar_w + gap)
        h = plot_h * value / top if top else 0
        y = base_y - h
        r = min(radius, h / 2) if h else 0

        path = (
            f"M{x:.1f},{base_y} V{y + r:.1f} "
            f"Q{x:.1f},{y:.1f} {x + r:.1f},{y:.1f} "
            f"H{x + bar_w - r:.1f} "
            f"Q{x + bar_w:.1f},{y:.1f} {x + bar_w:.1f},{y + r:.1f} "
            f"V{base_y} Z"
        )
        shown = money(value)
        parts.append(
            f'<g class="bar" data-label="{html.escape(label)}" '
            f'data-value="{shown}" data-metric="{html.escape(value_col)}">'
            f'<path d="{path}" fill="var(--{slot})"/>'
            f'<text x="{x + bar_w / 2:.1f}" y="{y - 8:.1f}" class="value">{shown}</text>'
            f'<text x="{x + bar_w / 2:.1f}" y="{base_y + 18:.1f}" class="tick">'
            f"{html.escape(label)}</text>"
            f"</g>"
        )

    parts.append(
        f'<line x1="{pad_l}" y1="{base_y}" x2="{width - pad_r}" y2="{base_y}" '
        f'class="axis"/>'
    )

    return (
        f'<svg viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="{html.escape(value_col)} по месяцам">'
        + "".join(parts)
        + "</svg>"
    )


def stat_tile(title: str, value: str, note: str) -> str:
    return (
        f'<div class="tile"><div class="tile-title">{html.escape(title)}</div>'
        f'<div class="tile-value">{value}</div>'
        f'<div class="tile-note">{html.escape(note)}</div></div>'
    )


def table(rows: list[dict]) -> str:
    head = "".join(f"<th>{html.escape(k)}</th>" for k in rows[0])
    body = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(v))}</td>" for v in row.values()) + "</tr>"
        for row in rows
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def build() -> str:
    rows = load_rows()
    orders = sum(int(r["Заказы"]) for r in rows)
    revenue = sum(int(r["Выручка"]) for r in rows)
    months = len(rows)

    return TEMPLATE.format(
        source=html.escape(source_name()),
        tiles=stat_tile("Всего заказов", money(orders), f"за {months} мес.")
        + stat_tile("Всего выручка", money(revenue), f"за {months} мес."),
        chart_orders=bar_chart(rows, "Месяц", "Заказы", "series-1"),
        chart_revenue=bar_chart(rows, "Месяц", "Выручка", "series-2"),
        table=table(rows),
    )


TEMPLATE = """<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Дашборд продаж</title>
<style>
  :root {{
    color-scheme: light;
    --plane: #f9f9f7;
    --surface-1: #fcfcfb;
    --text-primary: #0b0b0b;
    --text-secondary: #52514e;
    --muted: #898781;
    --grid: #e1e0d9;
    --axis: #c3c2b7;
    --border: rgba(11,11,11,0.10);
    --series-1: #2a78d6;
    --series-2: #eb6834;
  }}
  @media (prefers-color-scheme: dark) {{
    :root:not([data-theme="light"]) {{
      color-scheme: dark;
      --plane: #0d0d0d;
      --surface-1: #1a1a19;
      --text-primary: #ffffff;
      --text-secondary: #c3c2b7;
      --muted: #898781;
      --grid: #2c2c2a;
      --axis: #383835;
      --border: rgba(255,255,255,0.10);
      --series-1: #3987e5;
      --series-2: #d95926;
    }}
  }}
  :root[data-theme="dark"] {{
    color-scheme: dark;
    --plane: #0d0d0d;
    --surface-1: #1a1a19;
    --text-primary: #ffffff;
    --text-secondary: #c3c2b7;
    --grid: #2c2c2a;
    --axis: #383835;
    --border: rgba(255,255,255,0.10);
    --series-1: #3987e5;
    --series-2: #d95926;
  }}

  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    padding: 32px 20px 56px;
    background: var(--plane);
    color: var(--text-primary);
    font: 15px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif;
  }}
  .wrap {{ max-width: 900px; margin: 0 auto; }}
  h1 {{ font-size: 22px; margin: 0 0 4px; }}
  .source {{ color: var(--muted); font-size: 13px; margin: 0 0 24px; }}

  .tiles {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
            gap: 12px; margin-bottom: 12px; }}
  .tile {{ background: var(--surface-1); border: 1px solid var(--border);
           border-radius: 10px; padding: 16px 18px; }}
  .tile-title {{ color: var(--text-secondary); font-size: 13px; }}
  .tile-value {{ font-size: 30px; font-weight: 600; margin: 4px 0 2px; }}
  .tile-note {{ color: var(--muted); font-size: 12px; }}

  .charts {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
             gap: 12px; }}
  .card {{ background: var(--surface-1); border: 1px solid var(--border);
           border-radius: 10px; padding: 16px 18px 10px; }}
  .card h2 {{ font-size: 14px; font-weight: 600; margin: 0 0 10px;
              color: var(--text-secondary); }}
  svg {{ width: 100%; height: auto; display: block; overflow: visible; }}
  .grid {{ stroke: var(--grid); stroke-width: 1; }}
  .axis {{ stroke: var(--axis); stroke-width: 1; }}
  .value {{ fill: var(--text-secondary); font-size: 12px; text-anchor: middle; }}
  .tick {{ fill: var(--muted); font-size: 12px; text-anchor: middle; }}
  .bar {{ cursor: default; }}
  .bar:hover path {{ opacity: 0.82; }}

  details {{ margin-top: 20px; }}
  summary {{ color: var(--text-secondary); font-size: 13px; cursor: pointer; }}
  table {{ border-collapse: collapse; margin-top: 12px; font-size: 14px;
           font-variant-numeric: tabular-nums; }}
  th, td {{ border-bottom: 1px solid var(--border); padding: 7px 16px 7px 0;
            text-align: left; }}
  th {{ color: var(--text-secondary); font-weight: 600; }}

  #tip {{ position: fixed; pointer-events: none; opacity: 0;
          background: var(--surface-1); color: var(--text-primary);
          border: 1px solid var(--border); border-radius: 8px;
          padding: 7px 10px; font-size: 13px; white-space: nowrap;
          box-shadow: 0 4px 14px rgba(0,0,0,0.14); transition: opacity .1s; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>Дашборд продаж</h1>
  <p class="source">Источник: {source}</p>

  <div class="tiles">{tiles}</div>

  <div class="charts">
    <div class="card"><h2>Заказы по месяцам</h2>{chart_orders}</div>
    <div class="card"><h2>Выручка по месяцам</h2>{chart_revenue}</div>
  </div>

  <details>
    <summary>Показать данные таблицей</summary>
    {table}
  </details>
</div>

<div id="tip"></div>
<script>
  const tip = document.getElementById('tip');
  for (const bar of document.querySelectorAll('.bar')) {{
    bar.addEventListener('mousemove', (e) => {{
      tip.textContent = bar.dataset.label + ' · ' + bar.dataset.metric + ': ' + bar.dataset.value;
      tip.style.opacity = 1;
      tip.style.left = (e.clientX + 14) + 'px';
      tip.style.top = (e.clientY - 34) + 'px';
    }});
    bar.addEventListener('mouseleave', () => {{ tip.style.opacity = 0; }});
  }}
</script>
</body>
</html>
"""


if __name__ == "__main__":
    OUT.write_text(build(), encoding="utf-8")
    print(f"Готово: {OUT}")
