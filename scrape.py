import asyncio
import csv
import os
import re
from datetime import datetime, timedelta, timezone
from playwright.async_api import async_playwright

# ============ 配置 ============
URL_UNI_CHART = "https://yobang.tencentmusic.com/chart/enter.html?platform=qy&from=searchdirect&_video=true&searchid=115824485938112291,&shareFrom=qy&hosteuin=7wEPNKcz7ioi&ADTAG=wxfshare"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_FILE = os.path.join(BASE_DIR, "uni_chart_data.csv")
HTML_FILE = os.path.join(BASE_DIR, "index.html")

BJT = timezone(timedelta(hours=8))

# 表头：每名占 4 列（歌名、得分、官方增幅、自算差值）
HEADER = [
    "时间", "榜单类型",
    "第1名歌名", "第1名得分", "第1名官方增幅", "第1名自算差值",
    "第2名歌名", "第2名得分", "第2名官方增幅", "第2名自算差值",
    "第3名歌名", "第3名得分", "第3名官方增幅", "第3名自算差值",
]


# ============ 抓取 ============
async def scrape_top3(page, chart_type):
    """抓取指定榜单（daily/weekly）前三名"""
    top3 = []
    try:
        await page.route(
            "**/*",
            lambda route: route.abort()
            if route.request.resource_type in ["image", "media", "font"]
            else route.continue_(),
        )
        await page.goto(URL_UNI_CHART, wait_until="domcontentloaded", timeout=20000)

        # 等歌名元素出现，说明榜单已渲染
        await page.wait_for_selector('[class*="songItem_trackName"]', timeout=15000)

        if chart_type == "daily":
            # 日榜切换按钮：按文字“日榜”点击；默认已是日榜时失败也不影响
            try:
                await page.click("text=日榜", timeout=5000)
                await page.wait_for_timeout(2000)
                await page.wait_for_selector('[class*="songItem_trackName"]', timeout=15000)
            except Exception as e:
                print(f"[scrape_top3:daily] 切换日榜失败（可能默认已是日榜）: {e}")

        name_locators = page.locator('[class*="songItem_trackName"]')
        score_locators = page.locator('[class*="songItem_uniIndex"]')
        change_locators = page.locator('[class*="songItem_uniChange"]')

        count = min(3, await name_locators.count(), await score_locators.count())
        for i in range(count):
            name = (await name_locators.nth(i).inner_text()).strip()
            score_text = (await score_locators.nth(i).inner_text()).strip()
            m = re.search(r"\d+(?:\.\d+)?", score_text)
            score = float(m.group()) if m else None

            # 官方增幅，如 "+0.02" / "-0.01"
            page_change = ""
            if i < await change_locators.count():
                change_text = (await change_locators.nth(i).inner_text()).strip()
                cm = re.search(r"[+-]?\d+(?:\.\d+)?", change_text)
                if cm:
                    page_change = cm.group()

            if name and score is not None:
                top3.append({"name": name, "score": score, "page_change": page_change})

    except Exception as e:
        print(f"[scrape_top3:{chart_type}] 抓取失败: {e}")

    print(f"[scrape_top3:{chart_type}] 抓到 {len(top3)} 条: {top3}")
    return top3


# ============ CSV 读写 ============
def load_all_rows():
    """返回 (header, data_rows)"""
    if not os.path.exists(CSV_FILE):
        return HEADER, []
    with open(CSV_FILE, "r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    return rows[0], rows[1:]


def load_last_row_by_type(chart_type):
    """取指定榜单类型的最后一条记录，用于算差值"""
    _, data_rows = load_all_rows()
    for row in reversed(data_rows):
        if len(row) > 1 and row[1] == chart_type:
            return row
    return None


def build_row(chart_type, top3, prev_row):
    now_str = datetime.now(BJT).strftime("%Y/%m/%d %H:%M")
    row = [now_str, chart_type]
    for i in range(3):
        if i < len(top3):
            name = top3[i]["name"]
            score = top3[i]["score"]
            page_change = top3[i].get("page_change", "")
        else:
            name, score, page_change = "", "", ""

        delta = ""
        if prev_row and name and score != "":
            try:
                prev_name = prev_row[2 + i * 4]
                prev_score = prev_row[3 + i * 4]
                if prev_name == name and prev_score != "":
                    delta = round(score - float(prev_score), 2)
            except (IndexError, ValueError):
                pass

        row.extend([name, score if score != "" else "", page_change, delta])
    return row


def append_rows(rows_to_add):
    """追加写入，跳过与最后一条同类型记录时间戳完全相同的行"""
    _, data_rows = load_all_rows()
    last_by_type = {}
    for r in data_rows:
        if len(r) > 1:
            last_by_type[r[1]] = r

    filtered = []
    for r in rows_to_add:
        last = last_by_type.get(r[1])
        if last and last[0] == r[0]:
            print(f"⏭️ 跳过重复记录 [{r[1]}] {r[0]}")
            continue
        filtered.append(r)

    if not filtered:
        return

    file_exists = os.path.exists(CSV_FILE)
    with open(CSV_FILE, "a", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(HEADER)
        writer.writerows(filtered)
    for r in filtered:
        print(f"✅ 写入 [{r[1]}] {r[0]}")


# ============ HTML 生成 ============
def generate_html():
    """读取 CSV，生成日榜/周榜两张表格的 index.html"""
    _, data_rows = load_all_rows()

    daily_rows = [r for r in data_rows if len(r) > 1 and r[1] == "日榜"]
    weekly_rows = [r for r in data_rows if len(r) > 1 and r[1] == "周榜"]

    table_header = ["时间"]
    for n in ("1", "2", "3"):
        table_header += [f"第{n}名", f"{n}名得分", f"{n}名官方增幅", f"{n}名自算差值"]

    def render_table(rows, title):
        html = [f'<h2>{title}</h2>', '<table>',
                '<thead><tr>' + ''.join(f'<th>{h}</th>' for h in table_header) + '</tr></thead>',
                '<tbody>']
        for r in reversed(rows):
            cells = [f'<td>{r[0]}</td>']
            for i in range(3):
                name = r[2 + i * 4] if len(r) > 2 + i * 4 else ""
                score = r[3 + i * 4] if len(r) > 3 + i * 4 else ""
                page_change = r[4 + i * 4] if len(r) > 4 + i * 4 else ""
                delta = r[5 + i * 4] if len(r) > 5 + i * 4 else ""

                def color_class(v):
                    if v == "":
                        return ""
                    try:
                        fv = float(v)
                        return "up" if fv > 0 else ("down" if fv < 0 else "")
                    except ValueError:
                        return ""

                cells.append(f'<td>{name}</td>')
                cells.append(f'<td>{score}</td>')
                cells.append(f'<td class="{color_class(page_change)}">{page_change}</td>')
                cells.append(f'<td class="{color_class(delta)}">{delta}</td>')
            html.append('<tr>' + ''.join(cells) + '</tr>')
        html.append('</tbody></table>')
        return "\n".join(html)

    html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>腾讯音乐由你榜 · 前三追踪</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 20px; background: #f5f6f8; }}
  h1 {{ text-align: center; }}
  h2 {{ margin-top: 30px; }}
  table {{ border-collapse: collapse; width: 100%; background: #fff; box-shadow: 0 1px 3px rgba(0,0,0,.08); }}
  th, td {{ border: 1px solid #e0e0e0; padding: 8px 10px; text-align: center; font-size: 14px; }}
  th {{ background: #2b6cb0; color: #fff; }}
  tr:nth-child(even) {{ background: #f9fafb; }}
  .up {{ color: #e53e3e; }}
  .down {{ color: #38a169; }}
</style>
</head>
<body>
<h1>腾讯音乐由你榜 · 日榜/周榜前三追踪</h1>
<p style="text-align:center;color:#888;">最后生成：{datetime.now(BJT).strftime('%Y/%m/%d %H:%M')}（北京时间）</p>
{render_table(daily_rows, "📅 日榜")}
{render_table(weekly_rows, "📆 周榜")}
</body>
</html>
"""
    with open(HTML_FILE, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"✅ 已生成 {os.path.basename(HTML_FILE)}")


# ============ 主流程 ============
async def run_once():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
                       "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                       "Version/16.0 Mobile/15E148 Safari/604.1"
        )
        page_daily = await context.new_page()
        page_weekly = await context.new_page()

        daily_top3, weekly_top3 = await asyncio.gather(
            scrape_top3(page_daily, "daily"),
            scrape_top3(page_weekly, "weekly"),
        )
        await browser.close()

    rows_to_add = []
    for chart_type, top3 in (("日榜", daily_top3), ("周榜", weekly_top3)):
        prev_row = load_last_row_by_type(chart_type)
        rows_to_add.append(build_row(chart_type, top3, prev_row))

    append_rows(rows_to_add)
    generate_html()


async def main():
    print("开始执行由你榜抓取（15分钟粒度，单 CSV + HTML 双表）...")
    try:
        await run_once()
        print("任务完成。")
    except Exception as e:
        print(f"[抓取失败]: {e}")


if __name__ == "__main__":
    asyncio.run(main())
