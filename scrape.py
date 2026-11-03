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

BJT = timezone(timedelta(hours=8))

# 表头：每名占 3 列（歌名、得分、官方增幅）
HEADER = [
    "时间", "榜单类型",
    "第1名歌名", "第1名得分", "第1名官方增幅",
    "第2名歌名", "第2名得分", "第2名官方增幅",
    "第3名歌名", "第3名得分", "第3名官方增幅",
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


def build_row(chart_type, top3):
    now_str = datetime.now(BJT).strftime("%Y/%m/%d %H:%M")
    row = [now_str, chart_type]
    for i in range(3):
        if i < len(top3):
            name = top3[i]["name"]
            score = top3[i]["score"]
            page_change = top3[i].get("page_change", "")
        else:
            name, score, page_change = "", "", ""
        row.extend([name, score if score != "" else "", page_change])
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

    rows_to_add = [
        build_row("日榜", daily_top3),
        build_row("周榜", weekly_top3),
    ]
    append_rows(rows_to_add)


async def main():
    print("开始执行由你榜抓取（15分钟粒度，仅写 CSV）...")
    try:
        await run_once()
        print("任务完成。")
    except Exception as e:
        print(f"[抓取失败]: {e}")


if __name__ == "__main__":
    asyncio.run(main())
