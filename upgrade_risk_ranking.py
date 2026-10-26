from pathlib import Path
p = Path(__file__).with_name('index.html')
s = p.read_text(encoding='utf-8')
changes = [
('<option value="score">조건 점수순</option>', '<option value="score">위험조정 점수순</option>'),
('  if(searching){\n    const relevance = x => {', '  const riskAdjusted = x => Number(x.score) - (Number.isInteger(x.risk_score) && x.risk_score>=0 && x.risk_score<=100 ? Math.min(40, Math.round(x.risk_score*0.5)) : 0);\n  if(searching){\n    const relevance = x => {'),
("    if(order==='score') candidates.sort((a,b)=>b.score-a.score||b.value_eok-a.value_eok);", "    if(order==='score') candidates.sort((a,b)=>riskAdjusted(b)-riskAdjusted(a)||b.score-a.score||b.value_eok-a.value_eok);"),
("    top.append(left,elem('div','score',`${x.score}점`));", "    top.append(left,elem('div','score',`${x.score}점`));\n    const adjusted=elem('div','muted',`위험조정 ${riskAdjusted(x)}점 · 과열 ${x.risk_score ?? '미계산'}/100`);\n    adjusted.style.cssText='text-align:right;font-weight:750';\n    top.append(adjusted);"),
]
if '위험조정 점수순' in s:
 print('Already applied')
else:
 for before, after in changes:
  n = s.count(before)
  if n != 1: raise RuntimeError(f'Expected 1 occurrence, got {n}: {before[:40]}')
  s = s.replace(before, after, 1)
 p.write_text(s, encoding='utf-8')
 print('Updated index.html. Commit this file to deploy.')
