import csv
import os
import time
from datetime import datetime, timedelta, timezone

import httpx

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_DAILY = os.path.join(BASE_DIR, "uni_chart_daily.csv")
CSV_WEEKLY = os.path.join(BASE_DIR, "uni_chart_weekly.csv")
BJT = timezone(timedelta(hours=8))

API_DAILY = "https://yobang.tencentmusic.com/unichartsapi/yobang/daily/chart?page=1&pageSize=200"
API_WEEKLY = "https://yobang.tencentmusic.com/unichartsapi/v1/songs/charts/dynamic?offset=0&limit=200&platform=website&t={ts}"
API_DETAIL = "https://yobang.tencentmusic.com/unichartsapi/v1/songs/{uid}/charts_detail"
API_DAILY_DETAIL = "https://yobang.tencentmusic.com/unichartsapi/yobang/daily/chart/detail/all?itemId={uid}"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
                  "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                  "Version/16.0 Mobile/15E148 Safari/604.1",
    "Referer": "https://yobang.tencentmusic.com/",
}

HEADER = [
    "时间",
    "第1名歌名", "第1名歌手", "第1名得分", "第1名播放热度", "第1名畅销度", "第1名推荐度", "第1名官方增幅",
    "第2名歌名", "第2名歌手", "第2名得分", "第2名播放热度", "第2名畅销度", "第2名推荐度", "第2名官方增幅",
    "第3名歌名", "第3名歌手", "第3名得分", "第3名播放热度", "第3名畅销度", "第3名推荐度", "第3名官方增幅",
]


def fetch_detail_indices(client, uid):
    """周榜详情：请求 charts_detail，按 code 取三个维度：1=播放热度, 4=畅销度, 5=推荐度"""
    play = sales = recommend = ""
    if not uid:
        return play, sales, recommend
    try:
        resp = client.get(API_DETAIL.format(uid=uid))
        resp.raise_for_status()
        data = resp.json().get("data") or []
        if data:
            idx_map = {c.get("code"): c.get("index", "") for c in data[0].get("classifyIndices", [])}
            play = idx_map.get(1, "")
            sales = idx_map.get(4, "")
            recommend = idx_map.get(5, "")
    except Exception as e:
        print(f"[detail] uid={uid} 失败: {e}")
    return play, sales, recommend


def fetch_daily_detail_indices(client, uid):
    """日榜详情：extend.playIndex=播放热度, extend.payIndex=畅销度, extend.popIndex=推荐度"""
    play = sales = recommend = ""
    if not uid:
        return play, sales, recommend
    try:
        resp = client.get(API_DAILY_DETAIL.format(uid=uid))
        resp.raise_for_status()
        data = resp.json().get("data") or []
        if data:
            current = next((d for d in data if d.get("currentIssue")), data[0])
            ext = current.get("extend") or {}
            play = ext.get("playIndex", "")
            sales = ext.get("payIndex", "")
            recommend = ext.get("popIndex", "")
    except Exception as e:
        print(f"[daily-detail] uid={uid} 失败: {e}")
    return play, sales, recommend


def fetch_daily_top3(client):
    resp = client.get(API_DAILY)
    resp.raise_for_status()
    items = resp.json()["data"]["data"][:3]
    result = []
    for it in items:
        info = it.get("info") or {}
        uid = it.get("itemId")
        play, sales, recommend = fetch_daily_detail_indices(client, uid)
        result.append({
            "name": info.get("trackNameShow", ""),
            "singer": info.get("singerName", ""),
            "score": it.get("score", ""),
            "play": play,
            "sales": sales,
            "recommend": recommend,
            "change": it.get("incrScore", ""),
        })
    return result


def fetch_weekly_top3(client):
    url = API_WEEKLY.format(ts=int(time.time() * 1000))
    resp = client.get(url)
    resp.raise_for_status()
    items = resp.json()["data"]["chartsList"][:3]
    result = []
    for it in items:
        uid = it.get("uniTrackId")
        play, sales, recommend = fetch_detail_indices(client, uid)
        result.append({
            "name": it.get("songName", ""),
            "singer": it.get("singerName", ""),
            "score": it.get("uniIndex", ""),
            "play": play,
            "sales": sales,
            "recommend": recommend,
            "change": it.get("uniChange", ""),
        })
    return result


def build_row(top3):
    now_str = datetime.now(BJT).strftime("%Y/%m/%d %H:%M")
    row = [now_str]
    for i in range(3):
        if i < len(top3):
            t = top3[i]
            row.extend([t["name"], t["singer"], t["score"], t["play"], t["sales"], t["recommend"], t["change"]])
        else:
            row.extend([""] * 7)
    return row


def last_timestamp(csv_file):
    if not os.path.exists(csv_file):
        return None
    with open(csv_file, "r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    return rows[-1][0] if len(rows) > 1 else None


def append_row(csv_file, row):
    if row[0] == last_timestamp(csv_file):
        print(f"⏭️ 跳过重复 {os.path.basename(csv_file)} {row[0]}")
        return
    file_exists = os.path.exists(csv_file)
    with open(csv_file, "a", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(HEADER)
        writer.writerow(row)
    print(f"✅ 写入 {os.path.basename(csv_file)} {row[0]}")


def main():
    print("开始抓取由你榜（日榜/周榜分文件）...")
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

    append_row(CSV_DAILY, build_row(daily))
    append_row(CSV_WEEKLY, build_row(weekly))
    print("任务完成。")


if __name__ == "__main__":
    main()
