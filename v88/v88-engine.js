/* 종베 스캐너 v8.8 관찰 신호 분석 엔진 (확정 일봉 전용).
 * 이 스크립트는 조회/분석만 하며 매수·매도 주문을 수행하지 않는다.
 */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.JongbeV88 = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const N = x => x === null || x === undefined || x === '' ? NaN : Number(x);
  const finite = Number.isFinite;
  const rolling = (values, length) => {
    const result = Array(values.length).fill(null);
    for (let i = length - 1; i < values.length; i++) {
      const slice = values.slice(i - length + 1, i + 1);
      if (slice.every(finite)) result[i] = slice.reduce((a, b) => a + b, 0) / length;
    }
    return result;
  };
  function bollinger(closes, period = 20, multiplier = 2) {
    const middle = rolling(closes, period);
    const upper = [], lower = [], width = [];
    for (let i = 0; i < closes.length; i++) {
      if (middle[i] === null || middle[i] <= 0) { upper.push(null); lower.push(null); width.push(null); continue; }
      const values = closes.slice(i - period + 1, i + 1);
      const variance = values.reduce((a, v) => a + (v - middle[i]) ** 2, 0) / period;
      const deviation = Math.sqrt(variance);
      upper.push(middle[i] + multiplier * deviation);
      lower.push(middle[i] - multiplier * deviation);
      width.push(deviation * multiplier * 2 / middle[i]);
    }
    return { upper, middle, lower, width };
  }
  const midpoint = (b, e, i) => {
    if (i < b - 1) return null;
    const arr = e.slice(i - b + 1, i + 1);
    if (arr.length !== b || !arr.every(x => finite(x.high) && finite(x.low))) return null;
    return (Math.max(...arr.map(x => x.high)) + Math.min(...arr.map(x => x.low))) / 2;
  };
  function cloud(bars) {
    // 오늘 실제 구름대는 26거래일 전에 계산한 선행스팬을 26일 우측 이동한 값이다.
    const ceiling = Array(bars.length).fill(null), floor = Array(bars.length).fill(null);
    for (let i = 0; i < bars.length; i++) {
      const shifted = i - 26;
      if (shifted < 0) continue;
      const tenkan = midpoint(9, bars, shifted);
      const kijun = midpoint(26, bars, shifted);
      const spanB = midpoint(52, bars, shifted);
      if ([tenkan, kijun, spanB].every(finite)) {
        const spanA = (tenkan + kijun) / 2;
        ceiling[i] = Math.max(spanA, spanB);
        floor[i] = Math.min(spanA, spanB);
      }
    }
    return { ceiling, floor };
  }
  function soldier(bars, direction, strictness = 0.40) {
    const group = bars.slice(-3);
    if (group.length !== 3) return false;
    for (let i = 0; i < 3; i++) {
      const b = group[i];
      if (b.high <= b.low) return false;
      const body = Math.abs(b.close - b.open) / (b.high - b.low);
      if (body < strictness) return false;
      if (direction === 'red' && (b.close <= b.open || (b.high-b.close)/(b.high-b.low)>0.35)) return false;
      if (direction === 'black' && (b.close >= b.open || (b.close-b.low)/(b.high-b.low)>0.35)) return false;
      if (i > 0) {
        const prev=group[i-1];
        // Classic soldiers/crows open inside the preceding real body, not above
        // the preceding close via a large overnight gap. Reject gap-only trends.
        if (direction === 'red' && (b.close <= prev.close || b.open < prev.open || b.open > prev.close)) return false;
        if (direction === 'black' && (b.close >= prev.close || b.open > prev.open || b.open < prev.close)) return false;
      }
    }
    return true;
  }
  function parseBars(records) {
    if (!Array.isArray(records)) return [];
    const cleaned=records.map(row => ({
      date: String(row?.[0] ?? ''), open: N(row?.[1]), high: N(row?.[2]),
      low: N(row?.[3]), close: N(row?.[4]), volume: N(row?.[5])
    })).filter(b => /^\d{4}-\d{2}-\d{2}$/.test(b.date) &&
      [b.open, b.high, b.low, b.close, b.volume].every(finite) &&
      b.open > 0 && b.close > 0 && b.high >= Math.max(b.low, b.open, b.close) &&
      b.low <= Math.min(b.open, b.close) && b.low > 0 && b.volume >= 0)
      .sort((a, b) => a.date.localeCompare(b.date));
    // Input source should already dedupe, but a repeated day must never count as
    // an additional completed candle for red/black soldiers or risk statistics.
    const unique=[];
    for(const bar of cleaned){if(unique.length&&unique.at(-1).date===bar.date)unique[unique.length-1]=bar;else unique.push(bar);}
    return unique;
  }
  function analyze(records, opts = {}) {
    const bars = parseBars(records), n = bars.length, signals = [];
    const result = { ready: false, bars, signals, bb: null, cloud: null, avgVolume: null,
      latest: bars.at(-1) || null, reason: '', risk: 'watch' };
    if (n < 80) { result.reason = '80거래일 미만으로 볼린저·일목 계산에 필요한 자료가 부족합니다.'; return result; }
    const closes = bars.map(x => x.close);
    const bb = bollinger(closes), c = cloud(bars), t = n - 1, p = t - 1;
    result.ready = true; result.bb = bb; result.cloud = c;
    const volumes = bars.slice(-21, -1).map(x => x.volume); // 오늘 제외 20일 평균
    const avg = volumes.length === 20 ? volumes.reduce((a, b) => a + b, 0) / 20 : null;
    result.avgVolume = avg;
    result.volumeRatio = avg > 0 ? bars[t].volume / avg : null;
    const bbNowValid = [bb.upper[t], bb.lower[t], bb.upper[p], bb.lower[p]].every(finite);
    const crossedUp = bbNowValid && closes[t] > bb.upper[t] && closes[p] <= bb.upper[p];
    if (bbNowValid && closes[p] < bb.lower[p] && closes[t] >= bb.lower[t]) signals.push('bb_reentry');
    if (crossedUp && result.volumeRatio !== null && result.volumeRatio >= 1.5) signals.push('bb_breakout_volume');
    // 직전까지 밴드폭이 최근 40일 폭의 하위 20%인 경우만 보수적으로 수축으로 간주.
    const previousWidths = bb.width.slice(Math.max(0, p - 39), p + 1).filter(finite).sort((a, b) => a - b);
    const squeeze = previousWidths.length >= 35 && bb.width[p] !== null &&
      bb.width[p] <= previousWidths[Math.floor((previousWidths.length - 1) * 0.2)];
    if (crossedUp && squeeze) signals.push('bb_squeeze_breakout');
    if (soldier(bars, 'red', Number(opts.strictness ?? 0.40))) signals.push('red_soldiers');
    if (soldier(bars, 'black', Number(opts.strictness ?? 0.40))) signals.push('black_soldiers');
    if (finite(c.ceiling[t]) && finite(c.ceiling[p])) {
      if (closes[p] <= c.ceiling[p] && closes[t] > c.ceiling[t]) signals.push('cloud_breakout');
      // 최근 10일 안에 처음 구름대 상향 돌파하고 이후 다시 구름대 하단으로 내려온 종목.
      if (finite(c.floor[t]) && closes[t] < c.floor[t]) {
        for (let j = Math.max(1, t - 10); j < t; j++) {
          if (finite(c.ceiling[j]) && finite(c.ceiling[j - 1]) &&
            closes[j - 1] <= c.ceiling[j - 1] && closes[j] > c.ceiling[j]) {
            signals.push('cloud_failed'); break;
          }
        }
      }
    }
    if (signals.includes('black_soldiers') || signals.includes('cloud_failed')) result.risk = 'danger';
    else if (signals.length) result.risk = 'signal';
    result.reason = signals.length ? '확정 일봉 기반 조건 발견' : '설정한 기술적 조건이 발생하지 않음';
    return result;
  }
  return { parseBars, rolling, bollinger, cloud, soldier, analyze };
});
