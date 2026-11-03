import csv
import os
import time
from datetime import datetime, timedelta, timezone

import httpx

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_FILE = os.path.join(BASE_DIR, "uni_chart_data.csv")
BJT = timezone(timedelta(hours=8))

API_DAILY = "https://yobang.tencentmusic.com/unichartsapi/yobang/daily/chart?page=1&pageSize=200"
API_WEEKLY = "https://yobang.tencentmusic.com/unichartsapi/v1/songs/charts/dynamic?offset=0&limit=200&platform=website&t={ts}"
API_DETAIL = "https://yobang.tencentmusic.com/unichartsapi/v1/songs/{uid}/charts_detail"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
                  "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                  "Version/16.0 Mobile/15E148 Safari/604.1",
    "Referer": "https://yobang.tencentmusic.com/",
}

HEADER = [
    "时间", "榜单类型",
    "第1名歌名", "第1名歌手", "第1名得分", "第1名播放热度", "第1名畅销度", "第1名推荐度", "第1名官方增幅",
    "第2名歌名", "第2名歌手", "第2名得分", "第2名播放热度", "第2名畅销度", "第2名推荐度", "第2名官方增幅",
    "第3名歌名", "第3名歌手", "第3名得分", "第3名播放热度", "第3名畅销度", "第3名推荐度", "第3名官方增幅",
]


def fetch_daily_top3(client):
    """日榜：一次请求，extend 里直接带三个维度"""
    resp = client.get(API_DAILY)
    resp.raise_for_status()
    items = resp.json()["data"]["data"][:3]
    result = []
    for it in items:
        ext = it.get("extend") or {}
        info = it.get("info") or {}
        result.append({
            "rank": it.get("rank"),
            "name": info.get("trackNameShow", ""),
            "singer": info.get("singerName", ""),
            "score": it.get("score", ""),
            "play": ext.get("playIndex", ""),
            "sales": ext.get("payIndex", ""),
            "recommend": ext.get("popIndex", ""),
            "change": it.get("incrScore", ""),
        })
    return result


def fetch_weekly_top3(client):
    """周榜：dynamic 拿前三，再对每个 uniTrackId 请求 charts_detail 补三个维度"""
    url = API_WEEKLY.format(ts=int(time.time() * 1000))
    resp = client.get(url)
    resp.raise_for_status()
    items = resp.json()["data"]["chartsList"][:3]

    result = []
    for it in items:
        uid = it.get("uniTrackId")
        play = sales = recommend = ""
        if uid:
            try:
                d = client.get(API_DETAIL.format(uid=uid)).json()["data"][0]
                idx_map = {c.get("code"): c.get("index", "") for c in d.get("classifyIndices", [])}
                play = idx_map.get(1, "")
                sales = idx_map.get(4, "")
                recommend = idx_map.get(5, "")
            except Exception as e:
                print(f"[weekly detail] uid={uid} 获取失败: {e}")

        result.append({
            "rank": it.get("rank"),
            "name": it.get("songName", ""),
            "singer": it.get("singerName", ""),
            "score": it.get("uniIndex", ""),
            "play": play,
            "sales": sales,
            "recommend": recommend,
            "change": it.get("uniChange", ""),
        })
    return result


def build_row(chart_type, top3):
    now_str = datetime.now(BJT).strftime("%Y/%m/%d %H:%M")
    row = [now_str, chart_type]
    for i in range(3):
        if i < len(top3):
            t = top3[i]
            row.extend([
                t.get("name", ""), t.get("singer", ""), t.get("score", ""),
                t.get("play", ""), t.get("sales", ""), t.get("recommend", ""),
                t.get("change", ""),
            ])
        else:
            row.extend([""] * 7)
    return row


def load_last_timestamp(chart_type):
    if not os.path.exists(CSV_FILE):
        return None
    with open(CSV_FILE, "r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    for r in reversed(rows[1:]):
        if len(r) > 1 and r[1] == chart_type:
            return r[0]
    return None


def append_rows(rows_to_add):
    """同类型同时间戳去重"""
    file_exists = os.path.exists(CSV_FILE)
    filtered = []
    for r in rows_to_add:
        if r[0] == load_last_timestamp(r[1]):
            print(f"⏭️ 跳过重复 [{r[1]}] {r[0]}")
            continue
        filtered.append(r)

    if not filtered:
        return

    with open(CSV_FILE, "a", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(HEADER)
        writer.writerows(filtered)
    for r in filtered:
        print(f"✅ 写入 [{r[1]}] {r[0]}")


def main():
    print("开始抓取由你榜（纯接口版）...")
    with httpx.Client(headers=HEADERS, timeout=20, follow_redirects=True) as client:
        try:
            daily = fetch_daily_top3(client)
            print(f"[日榜] 抓到 {len(daily)} 条")
        except Exception as e:
            print(f"[日榜] 失败: {e}")
            daily = []

        try:
            weekly = fetch_weekly_top3(client)
            print(f"[周榜] 抓到 {len(weekly)} 条")
        except Exception as e:
            print(f"[周榜] 失败: {e}")
            weekly = []

    rows = [build_row("日榜", daily), build_row("周榜", weekly)]
    append_rows(rows)
    print("任务完成。")


if __name__ == "__main__":
    main()
