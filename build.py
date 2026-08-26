"""Собирает index.html из данных таблицы.

Запуск:  python3 build.py
Результат: index.html рядом со скриптом.
"""

import hashlib
import html
import json
import pathlib
from datetime import datetime, timedelta, timezone

from data import check_rows, load_rows, source_name

HERE = pathlib.Path(__file__).parent
OUT = HERE / "index.html"
STATE = HERE / "state.json"

# Заказчик в Москве, сборка идёт в UTC. Фиксированное смещение, а не имя зоны:
# на раннере может не оказаться базы часовых поясов.
MSK = timezone(timedelta(hours=3))

# Названия колонок в таблице. Поменялись заголовки — правим здесь, в одном месте.
COL_MONTH = "Месяц"
COL_ORDERS = "Заказы"
COL_REVENUE = "Выручка"


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


def fingerprint(rows: list[dict]) -> str:
    """Отпечаток данных. Меняется только когда меняются сами цифры."""
    payload = json.dumps(rows, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def resolve_updated_at(rows: list[dict], now: datetime, state_file: pathlib.Path) -> str:
    """Возвращает время последнего ИЗМЕНЕНИЯ данных, а не время сборки.

    Иначе страница менялась бы каждый час, и каждая пересборка давала бы
    коммит и деплой на ровном месте.
    """
    current = fingerprint(rows)

    try:
        saved = json.loads(state_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        saved = {}

    if saved.get("fingerprint") == current and saved.get("updated_at"):
        return saved["updated_at"]

    stamp = now.astimezone(MSK).strftime("%d.%m.%Y, %H:%M")
    state_file.write_text(
        json.dumps({"fingerprint": current, "updated_at": stamp}, ensure_ascii=False),
        encoding="utf-8",
    )
    return stamp


def warnings_block(problems: list[str]) -> str:
    """Претензии к данным показываем на самой странице, а не в консоли сборки."""
    if not problems:
        return ""
    items = "".join(f"<li>{html.escape(p)}</li>" for p in problems)
    word = "замечание" if len(problems) == 1 else "замечания"
    return (
        f'<div class="warn"><div class="warn-head">Данные требуют внимания '
        f"({len(problems)} {word})</div><ul>{items}</ul>"
        f"<p>Цифры показаны как есть — исправлять их за вас нельзя. "
        f"Поправьте в таблице и обновите страницу.</p></div>"
    )


def build() -> str:
    rows = load_rows()
    orders = sum(int(r[COL_ORDERS]) for r in rows)
    revenue = sum(int(r[COL_REVENUE]) for r in rows)
    months = len(rows)

    updated = resolve_updated_at(rows, datetime.now(timezone.utc), STATE)

    return TEMPLATE.format(
        core=CORE_HTML,
        source=html.escape(source_name()),
        updated=html.escape(updated),
        warnings=warnings_block(check_rows(rows, COL_MONTH, [COL_ORDERS, COL_REVENUE])),
        tiles=stat_tile("Всего заказов", money(orders), f"за {months} мес.")
        + stat_tile("Всего выручка", money(revenue), f"за {months} мес."),
        chart_orders=bar_chart(rows, COL_MONTH, COL_ORDERS, "series-1"),
        chart_revenue=bar_chart(rows, COL_MONTH, COL_REVENUE, "series-2"),
        table=table(rows),
    )


# Фоновое ядро. Вставляется в шаблон готовой строкой, поэтому фигурные
# скобки внутри шейдера не нужно удваивать — .format() их не видит.
#
# Никаких внешних библиотек: Three.js весит около 600 КБ ради одной сферы,
# а здесь хватает пересечения луча со сферой и объёмного шума.
CORE_HTML = """<canvas id="core" aria-hidden="true"></canvas>
<script>
(function () {
  var canvas = document.getElementById('core');
  if (!canvas) return;

  var gl = canvas.getContext('webgl', { alpha: true, antialias: false, premultipliedAlpha: false })
        || canvas.getContext('experimental-webgl', { alpha: true, antialias: false });
  if (!gl) { canvas.style.display = 'none'; return; }

  var VERT = [
    'attribute vec2 p;',
    'void main() { gl_Position = vec4(p, 0.0, 1.0); }'
  ].join('\\n');

  var FRAG = [
    'precision highp float;',
    'uniform vec2 uRes;',
    'uniform float uTime;',

    'float hash(vec3 p) {',
    '  p = fract(p * 0.3183099 + 0.1);',
    '  p *= 17.0;',
    '  return fract(p.x * p.y * p.z * (p.x + p.y + p.z));',
    '}',

    'float noise(vec3 x) {',
    '  vec3 i = floor(x);',
    '  vec3 f = fract(x);',
    '  f = f * f * (3.0 - 2.0 * f);',
    '  return mix(',
    '    mix(mix(hash(i + vec3(0.0, 0.0, 0.0)), hash(i + vec3(1.0, 0.0, 0.0)), f.x),',
    '        mix(hash(i + vec3(0.0, 1.0, 0.0)), hash(i + vec3(1.0, 1.0, 0.0)), f.x), f.y),',
    '    mix(mix(hash(i + vec3(0.0, 0.0, 1.0)), hash(i + vec3(1.0, 0.0, 1.0)), f.x),',
    '        mix(hash(i + vec3(0.0, 1.0, 1.0)), hash(i + vec3(1.0, 1.0, 1.0)), f.x), f.y), f.z);',
    '}',

    'float fbm(vec3 p) {',
    '  float a = 0.5;',
    '  float s = 0.0;',
    '  for (int i = 0; i < 5; i++) { s += a * noise(p); p *= 2.03; a *= 0.5; }',
    '  return s;',
    '}',

    'vec3 iridescence(float t) {',
    '  return 0.5 + 0.5 * cos(6.28318 * (vec3(0.0, 0.33, 0.67) + t));',
    '}',

    'void main() {',
    '  vec2 uv = (gl_FragCoord.xy - 0.5 * uRes) / min(uRes.x, uRes.y);',
    '  vec3 ro = vec3(0.0, 0.0, 2.7);',
    '  vec3 rd = normalize(vec3(uv * 1.25, -1.7));',

    '  float b = dot(ro, rd);',
    '  float c = dot(ro, ro) - 1.0;',
    '  float h = b * b - c;',

    '  float t = uTime * 0.09;',
    '  vec3 col = vec3(0.0);',
    '  float alpha = 0.0;',

    '  if (h > 0.0) {',
    '    vec3 pos = ro + rd * (-b - sqrt(h));',
    '    vec3 n = normalize(pos);',
    '    float ca = cos(t);',
    '    float sa = sin(t);',
    '    vec3 q = vec3(n.x * ca - n.z * sa, n.y, n.x * sa + n.z * ca);',
    '    float f = fbm(q * 2.6 + vec3(0.0, t * 1.4, 0.0));',
    '    float fres = pow(1.0 - max(dot(n, -rd), 0.0), 2.2);',
    '    col = iridescence(f * 0.85 + t * 0.7 + 0.55) * (0.30 + 0.85 * f);',
    '    col += vec3(0.45, 0.68, 1.0) * fres * 0.9;',
    '    alpha = 0.50 + 0.45 * f;',
    '  }',

    '  float d = length(uv);',
    '  float glow = exp(-max(d - 0.42, 0.0) * 5.0);',
    '  col += iridescence(t * 0.7 + 0.55) * glow * 0.30;',
    '  alpha = max(alpha, glow * 0.5);',

    '  gl_FragColor = vec4(col, clamp(alpha, 0.0, 1.0));',
    '}'
  ].join('\\n');

  function compile(type, src) {
    var sh = gl.createShader(type);
    gl.shaderSource(sh, src);
    gl.compileShader(sh);
    if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) return null;
    return sh;
  }

  var vs = compile(gl.VERTEX_SHADER, VERT);
  var fs = compile(gl.FRAGMENT_SHADER, FRAG);
  if (!vs || !fs) { canvas.style.display = 'none'; return; }

  var prog = gl.createProgram();
  gl.attachShader(prog, vs);
  gl.attachShader(prog, fs);
  gl.linkProgram(prog);
  if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) { canvas.style.display = 'none'; return; }
  gl.useProgram(prog);

  var buf = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, buf);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
  var loc = gl.getAttribLocation(prog, 'p');
  gl.enableVertexAttribArray(loc);
  gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);

  gl.enable(gl.BLEND);
  gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
  gl.clearColor(0, 0, 0, 0);

  var uRes = gl.getUniformLocation(prog, 'uRes');
  var uTime = gl.getUniformLocation(prog, 'uTime');

  // Считаем в пониженном разрешении: пиксели фона стоят дорого,
  // а размытое ядро от этого не страдает.
  function resize() {
    var scale = Math.min(window.devicePixelRatio || 1, 1.5) * 0.7;
    var w = Math.max(1, Math.round(canvas.clientWidth * scale));
    var h = Math.max(1, Math.round(canvas.clientHeight * scale));
    if (canvas.width !== w || canvas.height !== h) {
      canvas.width = w;
      canvas.height = h;
    }
    gl.viewport(0, 0, canvas.width, canvas.height);
    gl.uniform2f(uRes, canvas.width, canvas.height);
  }

  function draw(seconds) {
    gl.uniform1f(uTime, seconds);
    gl.clear(gl.COLOR_BUFFER_BIT);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
  }

  // Кому анимация мешает — тот получает один статичный кадр.
  var still = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  window.addEventListener('resize', function () { resize(); if (still) draw(0); });
  resize();

  if (still) { draw(0); return; }

  var start = performance.now();
  (function frame(now) {
    if (!document.hidden) { resize(); draw((now - start) / 1000); }
    requestAnimationFrame(frame);
  })(start);
})();
</script>"""


TEMPLATE = """<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Дашборд продаж</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Wix+Madefor+Display:wght@600;700&family=Wix+Madefor+Text:wght@400;500&family=JetBrains+Mono:wght@400;500&display=swap">
<style>
  /* Палитра рядов проверена валидатором на различимость при дальтонизме
     в светлой и тёмной теме. Менять только вместе с повторной проверкой. */
  :root {{
    color-scheme: light;
    --plane: #eef1f4;
    --surface: #ffffff;
    --ink: #0d1116;
    --ink-2: #4a5763;
    --muted: #7c8894;
    --rule: #dee4ea;
    --rule-soft: #edf1f4;
    --series-1: #2a78d6;
    --series-2: #eb6834;
    --warn-soft: #fdf5e6;
    --warn-line: #ecd6a6;
    --warn-ink: #8a5a10;
    /* На светлом фоне ядро приходится приглушать: пастель на белом
       съедает контраст текста быстрее, чем на тёмном. */
    --core-opacity: 0.55;
    --surface-alpha: 60%;

    --display: "Wix Madefor Display", ui-sans-serif, system-ui, sans-serif;
    --text: "Wix Madefor Text", ui-sans-serif, system-ui, sans-serif;
    --mono: "JetBrains Mono", ui-monospace, "SF Mono", monospace;
  }}
  @media (prefers-color-scheme: dark) {{
    :root:not([data-theme="light"]) {{
      color-scheme: dark;
      --plane: #090c0f;
      --surface: #14181d;
      --ink: #eef2f5;
      --ink-2: #9fabb6;
      --muted: #6f7b86;
      --rule: #222a31;
      --rule-soft: #1a1f25;
      --series-1: #3987e5;
      --series-2: #d95926;
      --warn-soft: #2a2116;
      --warn-line: #4d3d20;
      --warn-ink: #d9a44e;
    --core-opacity: 0.72;
    --surface-alpha: 74%;
      --core-opacity: 0.72;
      --surface-alpha: 74%;
    }}
  }}
  :root[data-theme="dark"] {{
    color-scheme: dark;
    --plane: #090c0f;
    --surface: #14181d;
    --ink: #eef2f5;
    --ink-2: #9fabb6;
    --muted: #6f7b86;
    --rule: #222a31;
    --rule-soft: #1a1f25;
    --series-1: #3987e5;
    --series-2: #d95926;
    --warn-soft: #2a2116;
    --warn-line: #4d3d20;
    --warn-ink: #d9a44e;
  }}

  * {{ box-sizing: border-box; }}

  /* Ядро живёт под содержимым и ничего не перехватывает.
     Прозрачность разная по темам: на светлом фоне оно должно быть тише,
     иначе текст теряет контраст. */
  #core {{
    position: fixed;
    inset: 0;
    width: 100%;
    height: 100%;
    z-index: 0;
    pointer-events: none;
    opacity: var(--core-opacity);
  }}

  body {{
    margin: 0;
    padding: 40px 20px 72px;
    background: var(--plane);
    color: var(--ink);
    font-family: var(--text);
    font-size: 15px;
    line-height: 1.55;
    -webkit-font-smoothing: antialiased;
  }}

  .wrap {{
    max-width: 940px;
    margin: 0 auto;
    display: flex;
    flex-direction: column;
    gap: 14px;
    position: relative;
    z-index: 1;
  }}

  /* Карточки слегка прозрачны, чтобы ядро читалось сквозь них.
     Там, где размытие фона не поддерживается, остаётся плотный фон. */
  .tile, .card, details {{
    background: color-mix(in srgb, var(--surface) calc(var(--surface-alpha) + 16%), transparent);
  }}
  @supports (backdrop-filter: blur(1px)) {{
    .tile, .card, details {{
      background: color-mix(in srgb, var(--surface) var(--surface-alpha), transparent);
      backdrop-filter: blur(14px) saturate(1.05);
    }}
  }}

  .head {{
    display: flex;
    flex-wrap: wrap;
    align-items: flex-end;
    justify-content: space-between;
    gap: 14px;
    padding-bottom: 6px;
  }}
  .eyebrow {{
    font-family: var(--mono);
    font-size: 11px;
    font-weight: 500;
    letter-spacing: 0.11em;
    text-transform: uppercase;
    color: var(--muted);
    margin: 0 0 5px;
  }}
  h1 {{
    font-family: var(--display);
    font-weight: 700;
    font-size: clamp(24px, 4vw, 31px);
    letter-spacing: -0.02em;
    line-height: 1.1;
    margin: 0;
  }}
  .stamp {{ text-align: right; display: flex; flex-direction: column; gap: 1px; }}
  .stamp-label {{
    font-family: var(--mono);
    font-size: 10.5px;
    letter-spacing: 0.09em;
    text-transform: uppercase;
    color: var(--muted);
  }}
  .stamp-value {{ font-size: 14px; font-weight: 500; font-variant-numeric: tabular-nums; }}
  .stamp-src {{ font-size: 12px; color: var(--muted); }}

  .warn {{
    background: var(--warn-soft);
    border: 1px solid var(--warn-line);
    border-radius: 12px;
    padding: 16px 18px;
  }}
  .warn-head {{ font-family: var(--display); font-weight: 600; font-size: 14.5px; color: var(--warn-ink); }}
  .warn ul {{ margin: 9px 0 0; padding-left: 19px; }}
  .warn li {{ font-size: 14px; margin-bottom: 3px; }}
  .warn p {{ margin: 11px 0 0; font-size: 13px; color: var(--ink-2); }}

  .tiles {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 14px; }}
  .tile {{
    background: var(--surface);
    border: 1px solid var(--rule);
    border-radius: 14px;
    padding: 18px 20px 16px;
  }}
  .tile-title {{
    font-family: var(--mono);
    font-size: 10.5px;
    letter-spacing: 0.09em;
    text-transform: uppercase;
    color: var(--muted);
  }}
  .tile-value {{
    font-family: var(--display);
    font-weight: 700;
    font-size: clamp(28px, 4.6vw, 36px);
    letter-spacing: -0.025em;
    line-height: 1.12;
    margin: 7px 0 3px;
  }}
  .tile-note {{ font-size: 12.5px; color: var(--muted); }}

  .charts {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 14px; }}
  .card {{
    background: var(--surface);
    border: 1px solid var(--rule);
    border-radius: 14px;
    padding: 18px 20px 12px;
  }}
  .card h2 {{
    font-family: var(--display);
    font-weight: 600;
    font-size: 14.5px;
    letter-spacing: -0.005em;
    margin: 0 0 14px;
  }}

  svg {{ width: 100%; height: auto; display: block; overflow: visible; }}
  .grid {{ stroke: var(--rule-soft); stroke-width: 1; }}
  .axis {{ stroke: var(--rule); stroke-width: 1; }}
  .value {{
    fill: var(--ink-2);
    font-family: var(--mono);
    font-size: 11px;
    text-anchor: middle;
  }}
  .tick {{
    fill: var(--muted);
    font-family: var(--mono);
    font-size: 10.5px;
    text-anchor: middle;
  }}
  .bar path {{ transition: opacity .12s; }}
  .bar:hover path {{ opacity: 0.78; }}

  details {{
    background: var(--surface);
    border: 1px solid var(--rule);
    border-radius: 14px;
    padding: 15px 20px;
  }}
  summary {{
    font-family: var(--mono);
    font-size: 11.5px;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--ink-2);
    cursor: pointer;
  }}
  summary:focus-visible {{ outline: 2px solid var(--series-1); outline-offset: 3px; border-radius: 3px; }}
  .table-wrap {{ overflow-x: auto; }}
  table {{ border-collapse: collapse; margin-top: 14px; font-size: 14px; font-variant-numeric: tabular-nums; }}
  th, td {{ text-align: left; padding: 9px 24px 9px 0; border-bottom: 1px solid var(--rule-soft); white-space: nowrap; }}
  th {{
    font-family: var(--mono);
    font-weight: 500;
    font-size: 10.5px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--muted);
  }}
  tr:last-child td {{ border-bottom: none; }}

  #tip {{
    position: fixed;
    pointer-events: none;
    opacity: 0;
    background: var(--surface);
    color: var(--ink);
    border: 1px solid var(--rule);
    border-radius: 9px;
    padding: 7px 11px;
    font-size: 13px;
    white-space: nowrap;
    box-shadow: 0 6px 20px rgba(0,0,0,0.16);
    transition: opacity .1s;
  }}

  @media (prefers-reduced-motion: reduce) {{
    * {{ transition: none !important; }}
  }}
</style>
</head>
<body>
{core}
<div class="wrap">

  <header class="head">
    <div>
      <p class="eyebrow">Продажи по месяцам</p>
      <h1>Дашборд продаж</h1>
    </div>
    <div class="stamp">
      <span class="stamp-label">Данные обновлены</span>
      <span class="stamp-value">{updated}</span>
      <span class="stamp-src">{source}</span>
    </div>
  </header>

  {warnings}

  <div class="tiles">{tiles}</div>

  <div class="charts">
    <div class="card"><h2>Заказы по месяцам</h2>{chart_orders}</div>
    <div class="card"><h2>Выручка по месяцам</h2>{chart_revenue}</div>
  </div>

  <details>
    <summary>Данные таблицей</summary>
    <div class="table-wrap">{table}</div>
  </details>

</div>

<div id="tip"></div>
<script>
  const tip = document.getElementById('tip');
  for (const bar of document.querySelectorAll('.bar')) {{
    bar.addEventListener('mousemove', (e) => {{
      tip.textContent = bar.dataset.label + ' · ' + bar.dataset.metric + ': ' + bar.dataset.value;
      tip.style.opacity = 1;
      tip.style.left = Math.min(e.clientX + 14, window.innerWidth - 190) + 'px';
      tip.style.top = (e.clientY - 38) + 'px';
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
