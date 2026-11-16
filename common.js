const lineColors = ['#ea3690', '#7c3aed', '#f97316', '#00e268', '#f5cc0b', '#10b981', '#c4b5fd', '#ef4444', '#14b8a6', '#64748b'];

function stripYear(timeStr) {
    if (!timeStr) return '';
    return timeStr.replace(/^\d{4}[-/]/, '');
}

function parseTime(s) {
    const m = (s || '').match(/(\d{4})[-/](\d{1,2})[-/](\d{1,2})(?:[ T](\d{1,2}):(\d{1,2})(?::(\d{1,2}))?)?/);
    if (!m) return null;
    return new Date(
        parseInt(m[1]), parseInt(m[2]) - 1, parseInt(m[3]),
        m[4] ? parseInt(m[4]) : 0,
        m[5] ? parseInt(m[5]) : 0,
        m[6] ? parseInt(m[6]) : 0
    );
}

function getTodayDateForDaily() {
    const now = new Date();
    const effective = new Date(now);
    if (now.getHours() === 0 && now.getMinutes() < 10) {
        effective.setDate(effective.getDate() - 1);
    }
    return effective;
}

function fmtDateLabel(d) {
    return `${d.getMonth() + 1}月${d.getDate()}日`;
}

function fmtDateKey(d) {
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

function getSongKey(r, rank) {
    const name = r[`第${rank}名歌名`] || '';
    const singer = r[`第${rank}名歌手`] || '';
    if (!name) return '';
    return singer ? `${singer}-${name}` : name;
}

function findNextDay0006OrPrev(nextKey, rowByKey, dayRowsMap, dayKey) {
    const exact = rowByKey[`${nextKey} 00:06`];
    if (exact) return exact;

    for (let mm = 5; mm >= 0; mm--) {
        const k = `${nextKey} 00:${String(mm).padStart(2, '0')}`;
        if (rowByKey[k]) return rowByKey[k];
    }

    const list = (dayRowsMap[dayKey] || []).slice().sort(
        (a, b) => (a['时间'] || '').localeCompare(b['时间'] || '')
    );
    return list[list.length - 1] || null;
}

/* ===== 本周周一 00:26 基准行；没有则取周一 00:26 之后最早一条 ===== */
function findWeekAnchorRow(rows) {
    const today = getTodayDateForDaily();
    const monday = getMondayOfWeek(today);
    const mondayKey = fmtDateKey(monday);
    const anchorTs = new Date(monday.getFullYear(), monday.getMonth(), monday.getDate(), 0, 26, 0).getTime();

    const mondayRows = rows
        .map(r => ({ r, t: parseTime(r['时间']) }))
        .filter(x => x.t && fmtDateKey(x.t) === mondayKey)
        .sort((a, b) => a.t - b.t);

    const exact = mondayRows.find(x => x.t.getHours() === 0 && x.t.getMinutes() === 26);
    if (exact) return exact.r;

    const after = mondayRows.find(x => x.t.getTime() >= anchorTs);
    if (after) return after.r;

    return mondayRows.length ? mondayRows[mondayRows.length - 1].r : null;
}

/* ===== 指定日期 00:06 基准行；没有则取 00:06 之后最早一条；再没有取当天最后一条 ===== */
function findDay0006AnchorRow(dayKey, dayRowsMap) {
    const list = (dayRowsMap[dayKey] || [])
        .map(r => ({ r, t: parseTime(r['时间']) }))
        .filter(x => x.t)
        .sort((a, b) => a.t - b.t);

    const exact = list.find(x => x.t.getHours() === 0 && x.t.getMinutes() === 6);
    if (exact) return exact.r;

    const target = new Date(dayKey.replace(/-/g, '/') + ' 00:06:00').getTime();
    const after = list.find(x => x.t.getTime() >= target);
    if (after) return after.r;

    return list.length ? list[list.length - 1].r : null;
}

/*
 * 周榜单日增幅：
 * - dayKey 为本周周一：基准 = findWeekAnchorRow（周一 00:26，无则往后最早）
 * - 其他日期：基准 = 前一天 00:06（无则取前一天 00:06 之后最早一条）
 * - 与基准行中同名歌曲的 deltaField 列作差；找不到同名歌曲则为 null
 * - displayRow 取该日最新一条（次日 00:06 归前一天）
 */
function calcWeeklyDayDelta(dayKey, nextKey, rowByKey, dayRowsMap, anchorRow, deltaField) {
    const df = deltaField || '得分';

    // 该日显示行：优先次日 00:06，否则取当天最后一条
    const next0006 = rowByKey[`${nextKey} 00:06`];
    const dayList = (dayRowsMap[dayKey] || []).slice().sort(
        (a, b) => (a['时间'] || '').localeCompare(b['时间'] || '')
    );
    const last = dayList[dayList.length - 1];
    const displayRow = next0006 || last || null;

    const monday = getMondayOfWeek(getTodayDateForDaily());
    const mondayKey = fmtDateKey(monday);
    const isMonday = dayKey === mondayKey;

    let baseRow = null;
    if (isMonday) {
        // 周一：与本周周一 00:26 作差
        baseRow = anchorRow || null;
    } else {
        // 其余日期：与前一天 00:06 作差
        const dayDate = new Date(dayKey.replace(/-/g, '/') + ' 00:00:00');
        const prevDate = new Date(dayDate);
        prevDate.setDate(prevDate.getDate() - 1);
        const prevKey = fmtDateKey(prevDate);
        baseRow = findDay0006AnchorRow(prevKey, dayRowsMap);
    }

    const delta = {};
    for (let rank = 1; rank <= 3; rank++) {
        if (!displayRow || !baseRow) {
            delta[rank] = null;
            continue;
        }

        const curVal = parseFloat(displayRow[`第${rank}名${df}`]);
        const curKey = getSongKey(displayRow, rank);

        if (isNaN(curVal) || !curKey) {
            delta[rank] = null;
            continue;
        }

        let baseVal = NaN;
        for (let rk = 1; rk <= 3; rk++) {
            if (getSongKey(baseRow, rk) === curKey) {
                baseVal = parseFloat(baseRow[`第${rk}名${df}`]);
                break;
            }
        }

        delta[rank] = !isNaN(baseVal) ? (curVal - baseVal) : null;
    }

    return { delta, displayRow };
}

function calcDailyDeltaList(rows) {
    const today = getTodayDateForDaily();
    const start = new Date(today);
    start.setHours(6, 6, 0, 0);
    const nextDay = new Date(today);
    nextDay.setDate(nextDay.getDate() + 1);
    const end = new Date(nextDay);
    end.setHours(0, 6, 0, 0);

    const sortedAsc = [...rows].sort((a, b) => (a['时间'] || '').localeCompare(b['时间'] || ''));
    const inRange = [];
    sortedAsc.forEach(r => {
        const t = parseTime(r['时间']);
        if (!t) return;
        const ts = t.getTime();
        if (ts < start.getTime() || ts > end.getTime()) return;
        const h = t.getHours();
        if (h >= 1 && h <= 5) return;
        inRange.push(r);
    });

    return inRange.map((r, idx) => {
        const t = parseTime(r['时间']);
        const isDayStart = t && t.getHours() === 6 && t.getMinutes() === 6;
        const prev = idx > 0 ? inRange[idx - 1] : null;

        const deltas = {};
        for (let rank = 1; rank <= 3; rank++) {
            const curKey = getSongKey(r, rank);
            const curScore = parseFloat(r[`第${rank}名得分`]);
            let deltaVal = null;

            if (isDayStart) {
                const raw = r[`第${rank}名官方增幅`] || '';
                if (raw !== '') {
                    const fv = parseFloat(raw);
                    if (!isNaN(fv)) deltaVal = fv;
                }
            } else if (prev) {
                if (getSongKey(prev, rank) === curKey && !isNaN(curScore)) {
                    const preScore = parseFloat(prev[`第${rank}名得分`]);
                    if (!isNaN(preScore)) deltaVal = curScore - preScore;
                } else {
                    for (let rk = 1; rk <= 3; rk++) {
                        if (getSongKey(prev, rk) === curKey) {
                            const preScore = parseFloat(prev[`第${rk}名得分`]);
                            if (!isNaN(curScore) && !isNaN(preScore)) {
                                deltaVal = curScore - preScore;
                            }
                            break;
                        }
                    }
                }
            }
            deltas[rank] = deltaVal;
        }
        return { row: r, deltas };
    });
}

function getMondayOfWeek(d) {
    const date = new Date(d.getFullYear(), d.getMonth(), d.getDate());
    const day = date.getDay();
    const diff = day === 0 ? -6 : 1 - day;
    date.setDate(date.getDate() + diff);
    return date;
}

function loadCsv(url) {
    return new Promise((resolve) => {
        Papa.parse(url + '?t=' + new Date().getTime(), {
            download: true,
            header: true,
            skipEmptyLines: true,
            encoding: 'UTF-8',
            complete: (res) => resolve(res.data || []),
            error: (err) => {
                console.error('加载失败', url, err);
                resolve([]);
            }
        });
    });
}