"""Apply existing risk scoring + a conservative 10-stock watchlist to Jongbe UI.
Used by the repository's existing scanner.yml after scanner.py.
This does not change scanner.py, OHLCV, or the original score.
"""
from pathlib import Path

p = Path(__file__).with_name('index.html')
s = p.read_text(encoding='utf-8')

# Keep the prior risk adjustment patch for repositories where it is not yet applied.
changes = [
    ('<option value="score">조건 점수순</option>', '<option value="score">위험조정 점수순</option>'),
    ('  if(searching){\n    const relevance = x => {',
     '  const riskAdjusted = x => Number(x.score) - (Number.isInteger(x.risk_score) && x.risk_score>=0 && x.risk_score<=100 ? Math.min(40, Math.round(x.risk_score*0.5)) : 0);\n  if(searching){\n    const relevance = x => {'),
    ("    if(order==='score') candidates.sort((a,b)=>b.score-a.score||b.value_eok-a.value_eok);",
     "    if(order==='score') candidates.sort((a,b)=>riskAdjusted(b)-riskAdjusted(a)||b.score-a.score||b.value_eok-a.value_eok);"),
    ("    top.append(left,elem('div','score',`${x.score}점`));",
     "    top.append(left,elem('div','score',`${x.score}점`));\n    const adjusted=elem('div','muted',`위험조정 ${riskAdjusted(x)}점 · 과열 ${x.risk_score ?? '미계산'}/100`);\n    adjusted.style.cssText='text-align:right;font-weight:750';\n    top.append(adjusted);"),
]
if '위험조정 점수순' not in s:
    for before, after in changes:
        if s.count(before) != 1:
            raise RuntimeError(f'Risk patch target missing/ambiguous: {before[:60]}')
        s = s.replace(before, after, 1)

# Idempotent: a workflow rerun must not duplicate the panel.
if 'jongbe-top-ten-v1' not in s:
    anchor = "  const searchhint=$('searchhint');"
    if s.count(anchor) != 1:
        raise RuntimeError('Top-10 insertion anchor missing/ambiguous; keeping original site unchanged.')
    patch = r'''  // jongbe-top-ten-v1: separate, conservative watchlist from confirmed EOD bars.
  // This is a rules-based shortlist, not a buy signal or a validated probability.
  let topTenPanel=document.getElementById('jongbeTopTen');
  if(!topTenPanel){
    topTenPanel=document.createElement('section');
    topTenPanel.id='jongbeTopTen';
    topTenPanel.style.cssText='margin:18px 0;padding:16px;background:#eaf6f2;border:1px solid #9bcebd;border-radius:14px;color:#173f36';
    const resultsContainer=document.getElementById('results');
    resultsContainer.parentNode.insertBefore(topTenPanel,resultsContainer.previousElementSibling);
  }
  topTenPanel.replaceChildren();
  const title10=document.createElement('h3');
  title10.textContent='🌱 상승 추세 · 낮은 과열 관찰종목 TOP 10';
  title10.style.cssText='font-size:17px;margin:0 0 8px';
  topTenPanel.append(title10);
  const rule10=document.createElement('div');
  rule10.textContent='기준: 기존점수 70점↑, 과열 35점 미만, 상승추세, 당일 +0~15%, 거래량 1.5배↑, 거래대금 50억원↑. 확정 일봉 기준이며 매수 추천이 아닙니다.';
  rule10.style.cssText='font-size:12px;line-height:1.65;margin-bottom:10px';
  topTenPanel.append(rule10);
  const topTen=dataRows.filter(x=>Number.isInteger(x.risk_score) && x.risk_score>=0 && x.risk_score<35 &&
      Number(x.score)>=70 && ['strong_up','rising'].includes(x.trend) &&
      Number(x.change)>0 && Number(x.change)<15 && Number(x.volume_ratio)>=1.5 &&
      Number(x.value_eok)>=50 && x.chase_risk!==true)
    .sort((a,b)=>riskAdjusted(b)-riskAdjusted(a)||Number(b.value_eok)-Number(a.value_eok)).slice(0,10);
  if(!topTen.length){
    const empty=document.createElement('div');
    empty.textContent='현재 기준을 모두 충족하는 종목이 없습니다. 기준을 임의로 완화하지 않았습니다.';
    empty.style.cssText='font-size:13px;line-height:1.6';topTenPanel.append(empty);
  }
  topTen.forEach((x,i)=>{
    const line=document.createElement('button');line.type='button';
    line.style.cssText='display:block;width:100%;text-align:left;background:#fff;color:#204a43;border:1px solid #b6d9cc;border-radius:9px;padding:11px;margin-top:7px;font-size:13px;line-height:1.55';
    line.textContent=`${i+1}. ${x.name} (${x.code}) · 조정 ${riskAdjusted(x)}점 / 기존 ${x.score}점 · 과열 ${x.risk_score}점 · 거래대금 ${x.value_eok}억`;
    line.addEventListener('click',()=>{
      document.getElementById('query').value=x.code;
      countShown=20;display();
      document.getElementById('results').scrollIntoView({behavior:'smooth',block:'start'});
    });
    topTenPanel.append(line);
  });
'''
    s = s.replace(anchor, patch + anchor, 1)

p.write_text(s, encoding='utf-8')
print('Risk-adjusted ranking and TOP 10 watchlist ready for site deployment.')
