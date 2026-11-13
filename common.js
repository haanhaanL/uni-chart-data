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

function calcWeeklyDayDelta(dayKey, nextKey, rowByKey, dayRowsMap) {
    const next0006 = rowByKey[`${nextKey} 00:06`];

    const dayList = (dayRowsMap[dayKey] || []).slice().sort(
        (a, b) => (a['时间'] || '').localeCompare(b['时间'] || '')
    );
    const last = dayList[dayList.length - 1];

    const displayRow = next0006 || last || null;

    const delta = {};
    for (let rank = 1; rank <= 3; rank++) {
        if (!displayRow) {
            delta[rank] = null;
            continue;
        }

        const curScore = parseFloat(displayRow[`第${rank}名得分`]);
        const curKey = getSongKey(displayRow, rank);

        if (isNaN(curScore) || !curKey) {
            delta[rank] = null;
            continue;
        }

        let firstScore = NaN;
        for (const r of dayList) {
            let hit = false;
            for (let rk = 1; rk <= 3; rk++) {
                if (getSongKey(r, rk) === curKey) {
                    firstScore = parseFloat(r[`第${rk}名得分`]);
                    hit = true;
                    break;
                }
            }
            if (hit) break;
        }

        delta[rank] = !isNaN(firstScore) ? (curScore - firstScore) : null;
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