/* Additive V8.8 extension for original V8.7. Does not overwrite existing UI or APIs. */
(() => {
'use strict';
const E=window.JongbeV88, F=window.JongbeForecast;
if(!E||!F)return;
const root=document.getElementById('v88Root');if(!root)return;
const $=id=>root.querySelector('#'+id);
const node=(tag,cls,txt)=>{const el=document.createElement(tag);if(cls)el.className=cls;if(txt!==undefined)el.textContent=String(txt);return el;};
const amount=n=>Number(n).toLocaleString('ko-KR');
const num=v=>v===null||v===undefined||v===''?null:Number.isFinite(Number(v))?Number(v):null;
const pips={nq_pct:['나스닥100 선물 (일봉 대용)','%'],kospi_night_pct:['코스피200 야간선물','%'],us10y_bp:['미국채 10년물 변화','bp'],sox_pct:['필라델피아 반도체지수','%']};
const tags={bb_reentry:'볼린저 하단 이탈 후 재진입',bb_squeeze_breakout:'스퀴즈 후 상단 돌파',bb_breakout_volume:'상단 돌파 + 거래량 증가',red_soldiers:'적삼병',black_soldiers:'흑삼병',cloud_breakout:'구름대 상향 돌파',cloud_failed:'구름대 돌파 실패'};
let latest=null,hist=[],rows=[],refClass=null,investorFlows=null,asof='-',active=null,found=[],chartCache=new Map(),universe=[],currentStock=null,first=true;
const elt=(parent,tag,cls,txt)=>{const e=node(tag,cls,txt);parent.append(e);return e};
function addSelect(parent,id,label,opts){const l=elt(parent,'label','',label),s=elt(l,'select');s.id=id;for(const [val,title] of opts){const o=elt(s,'option','',title);o.value=val}return s}
function addInput(parent,id,label,placeholder){const l=elt(parent,'label','',label),i=elt(l,'input');i.id=id;i.type='number';i.step='any';i.placeholder=placeholder||'';return i}
function button(parent,id,label,secondary=false){const b=elt(parent,'button',secondary?'v88-secondary':'',label);b.id=id;b.type='button';return b}
function init(){
 root.innerHTML='';
 elt(root,'h2','','✨ 종베 스캐너 V8.8 · 통합 확장');
 elt(root,'div','v88-note','확정 일봉 기반 기술 패턴과 시장 시나리오를 함께 관찰합니다. 거래 자동 실행 없음 · 실시간 보장 없음 · 예상가격은 학습/검증 조건을 통과한 경우에만 연구용으로 표시합니다. V8.7 원래 기능은 유지됩니다.');
 const m=elt(root,'section','v88-panel');elt(m,'h3','','🌐 밤사이 시장지표 확인');
 const metrics=elt(m,'div','v88-grid v88-market-grid');metrics.id='v88MarketCards';
 const btns=elt(m,'div','v88-row');button(btns,'v88Reload','↻ 시장지표 새로고침',true);
 const status=elt(m,'div','v88-status','시장자료 미확인');status.id='v88MarketStatus';
 elt(m,'small','','국내 야선 데이터는 검증 가능한 공급원 또는 시각·출처가 기재된 수동 값이 필요합니다. NQ·SOX Yahoo 일봉은 실시간 야간선물 가격이 아니며, 미국채 FRED 수치에는 발표 지연이 있습니다.');
 const s=elt(root,'section','v88-panel');elt(s,'h3','','🔎 통합 자동검색');
 const grid=elt(s,'div','v88-grid');
 addSelect(grid,'v88Pattern','검색 패턴',[['all','모든 패턴'],...Object.entries(tags)]);
 addSelect(grid,'v88Size','기업 규모 조건',[['large','시총 5,000억원 이상 (분류 대용 아님)'],['verified','출처 기재된 중견·대기업'],['unverified','기업 분류 미확인'],['all','전체 종목'],['unknown','시가총액 미확인']]);
 addSelect(grid,'v88Turnover','거래대금 필터',[['500','500억원 이상'],['1000','1,000억원 이상'],['100','100억원 이상'],['0','제한 없음']]);
 addSelect(grid,'v88Market','시장',[['ALL','코스피 + 코스닥'],['KOSPI','코스피'],['KOSDAQ','코스닥']]);
 addSelect(grid,'v88Strict','삼병 패턴 몸통 기준',[['0.4','기본 40%'],['0.6','엄격 60%']]);
 addSelect(grid,'v88Sort','정렬',[['score','위험조정 점수순'],['money','거래대금순']]);
 const buttons=elt(s,'div','v88-row');button(buttons,'v88Start','종목 자동검색');button(buttons,'v88Stop','검색 중단',true).disabled=true;button(buttons,'v88CSV','검색 결과 CSV',true).disabled=true;
 const progress=elt(s,'div','v88-status','아직 검색 전입니다.');progress.id='v88SearchStatus';const results=elt(s,'div');results.id='v88Results';
 const b=elt(root,'section','v88-panel');elt(b,'h3','','📉 다음 거래일 시초가 연구 및 시나리오');
 elt(b,'p','','종목을 검색한 뒤 개별 종목에서 “다음 날 시초가 분석”을 누르세요. 4개 시장 지표의 개장 전 과거자료 80거래일 이상이 확보되고, 별도 20회 검증에서 단순 기준선보다 오차가 작을 때만 예상액을 표시합니다.');
 const chosen=elt(b,'div','v88-status','종목 미선택');chosen.id='v88Chosen';
 const fg=elt(b,'div','v88-grid');
 addInput(fg,'v88Close','확정 종가 (원)','종목 선택 시 입력됨');
 addSelect(fg,'v88Category','종목 분류',[['general','일반주'],['semis','반도체주'],['growth','기술·성장주']]);
 for(const [k,[lab,unit]] of Object.entries(pips))addInput(fg,'v88_'+k,lab+' ('+unit+')','확인된 값만 입력');
 elt(b,'p','','수동 입력 시나리오의 가중치는 임의 가정이며 예측 검증·정확도·실제 수익률이 아닙니다. 값이 비어 있으면 계산하지 않습니다.');
 const actions=elt(b,'div','v88-row');button(actions,'v88Scenario','수동 시나리오 계산');button(actions,'v88Forecast','과거 검증 모델 확인',true);
 const box=elt(b,'div','v88-status','');box.id='v88ForecastOut';
 $('v88Reload').addEventListener('click',reload);
 $('v88Start').addEventListener('click',search);
 $('v88Stop').addEventListener('click',()=>{if(active)active.abort()});
 $('v88CSV').addEventListener('click',exportCSV);
 $('v88Scenario').addEventListener('click',scenario);
 $('v88Forecast').addEventListener('click',forecastSelected);
 reload();
}
async function readJSON(path,signal){const r=await fetch(path,{cache:'no-store',signal});if(!r.ok)throw Error(path+' HTTP '+r.status);return r.json()}
async function reload(){
 $('v88MarketStatus').textContent='시장자료 확인 중…';
 try{
  const [s,h]=await Promise.all([readJSON('./v88/market-latest.json'),readJSON('./v88/market-history.json')]);
  if(s?.schema!=='jongbe-market-snapshot-v1'||h?.schema!=='jongbe-market-history-v1')throw Error('시장 데이터 형식 오류');
  latest=s;hist=Array.isArray(h.sessions)?h.sessions:[];
  const cards=$('v88MarketCards');cards.replaceChildren();
  for(const [k,[label,unit]] of Object.entries(pips)){
    const div=elt(cards,'div','v88-metric');elt(div,'div','',label);
    const value=num(s.factors?.[k]);elt(div,'strong','',value===null?'미확인':(value>0?'+':'')+value.toFixed(k==='us10y_bp'?1:2)+unit);
    const src=s.sources?.[k];elt(div,'span','',src?.source||'출처 확인 필요');
    elt(div,'span','',src?.observed_at_kst||src?.observation_date||'관측시각 미확인');
  }
  const complete=s.complete===true;
  const targetOpen=Date.parse(String(s.session_date||'')+'T09:00:00+09:00');
  const pastTarget=Number.isFinite(targetOpen)&&Date.now()>=targetOpen;
  $('v88MarketStatus').textContent=`대상 한국 거래일 ${s.session_date||'미확인'} · 생성 ${s.generated_at_kst||'미수집'} · ${pastTarget?'⚠️ 이 자료는 대상 거래일 개장 이후의 과거 기록입니다.':complete?'4개 수치 확보(일봉 대용·지연 가능)':'⚠️ 불완전: 미확인 값을 0으로 대체하지 않음'} · 예측 검증용 과거 세션 ${hist.length}개`;
  if(pastTarget)$('v88MarketStatus').classList.add('warning');
  else $('v88MarketStatus').classList.remove('warning');
  for(const k of Object.keys(pips)){$('v88_'+k).value='';}
  // Never silently preload yesterday's factors as if they were current.
  if(s.collected_before_open===true&&!pastTarget){for(const k of Object.keys(pips)){const val=num(s.factors?.[k]);if(val!==null)$('v88_'+k).value=String(val);}}
 }catch(e){latest=null;hist=[];$('v88MarketStatus').textContent='⚠️ 시장지표 자동 자료를 가져오지 못했습니다. (설치 전이거나 원본 수집 실패) '+e.message;}
}
async function getChart(prefix,signal){
 if(!chartCache.has(prefix)){const p=readJSON('./charts/'+prefix+'.json?asof='+encodeURIComponent(asof),signal);
 chartCache.set(prefix,p);p.catch(()=>{if(chartCache.get(prefix)===p)chartCache.delete(prefix)});}
 return chartCache.get(prefix);
}
function adjust(r){const score=num(r.score)||0,risk=num(r.risk_score);return score-(risk===null?0:Math.min(40,Math.round(risk*.5)))}
async function search(){
 if(active)active.abort();const ctrl=new AbortController();active=ctrl;found=[];chartCache.clear();
 $('v88Start').disabled=true;$('v88Stop').disabled=false;$('v88CSV').disabled=true;$('v88Results').replaceChildren();
 try{
  $('v88SearchStatus').textContent='종목 목록 읽는 중…';
  const data=await readJSON('./results.json?t='+Date.now(),ctrl.signal);
  if(!/^\d{4}-\d{2}-\d{2}$/.test(String(data.asof||''))||!Array.isArray(data.rows))throw Error('확정 일봉 데이터 미수집 또는 형식 불일치');
  asof=data.asof;rows=data.rows;
  // A classification/flow file is optional. Failure never fabricates a zero flow or enterprise size.
  const [classLoad,flowLoad]=await Promise.allSettled([
    readJSON('./v88/corporate-classification.json?t='+Date.now(),ctrl.signal),
    readJSON('./v88/investor-flows.json?t='+Date.now(),ctrl.signal)
  ]);
  refClass=classLoad.status==='fulfilled'&&classLoad.value?.schema==='jongbe-corporate-classification-v1'&&
    classLoad.value.entries&&typeof classLoad.value.entries==='object'&&!Array.isArray(classLoad.value.entries)?classLoad.value.entries:null;
  investorFlows=flowLoad.status==='fulfilled'&&flowLoad.value?.schema==='jongbe-investor-flows-v1'&&
    flowLoad.value.session_date===asof&&flowLoad.value.entries&&typeof flowLoad.value.entries==='object'&&!Array.isArray(flowLoad.value.entries)?flowLoad.value.entries:null;

  const market=$('v88Market').value,minMoney=Number($('v88Turnover').value),size=$('v88Size').value,strictness=Number($('v88Strict').value),want=$('v88Pattern').value;
  if(data.data_status==='delayed'||(data.expected_asof&&data.expected_asof>asof)){
    $('v88SearchStatus').textContent=`⚠️ 자료 지연: 기준 ${asof}, 기대일 ${data.expected_asof}. 최신 종가로 간주하면 안 됩니다.\n`;
  }
  universe=rows.filter(x=>/^\d{6}$/.test(String(x.code))&&Number(x.value_eok)>=minMoney&&(market==='ALL'||market===x.market));
  const groups=new Map();for(const x of universe){const key=String(x.code).slice(0,2);if(!groups.has(key))groups.set(key,[]);groups.get(key).push(x)}
  const items=[...groups.entries()];let cursor=0,completed=0,failed=0,checked=0,unknown=0;
  async function worker(){while(cursor<items.length){if(ctrl.signal.aborted)throw DOMException('aborted','AbortError');const [pre,stockRows]=items[cursor++];
    try{const blob=await getChart(pre,ctrl.signal);if(blob.schema!=='jongbe-ohlcv-v1'||blob.asof!==asof)throw Error('시세 기준 불일치');
      for(const x of stockRows){const cap=num(blob.profiles?.[x.code]?.market_cap_krw);if(cap===null)unknown++;
        const corp=refClass?.[x.code];
        const hasClass=corp&&['large','mid','sme'].includes(corp.category)&&
            typeof corp.source==='string'&&corp.source.trim().length>=3&&
            /^\d{4}-\d{2}-\d{2}$/.test(String(corp.checked_on||''))&&corp.checked_on<=asof&&
            Date.parse(asof+'T00:00:00Z')-Date.parse(corp.checked_on+'T00:00:00Z')<=550*86400000;
        const category=hasClass?corp.category:null;
        if(size==='large'&&(cap===null||cap<5000*1e8))continue;
        if(size==='unknown'&&cap!==null)continue;
        if(size==='verified'&&!['large','mid'].includes(category))continue;
        if(size==='unverified'&&category!==null)continue;
        const bars=blob.stocks?.[x.code];if(!Array.isArray(bars))continue;
        checked++;const a=E.analyze(bars,{strictness});if(a.ready&&a.signals.length&&(want==='all'||a.signals.includes(want)))
        found.push({stock:x,analysis:a,bars,cap,corp:category?corp:null});
      }
    }catch(e){if(ctrl.signal.aborted)throw e;failed++}
    completed++;$('v88SearchStatus').textContent=`확정일 ${asof} · 차트 ${completed}/${items.length} · 분석 ${checked} · 일치 ${found.length} · 누락 묶음 ${failed}`;
  }}
  await Promise.all(Array.from({length:Math.min(4,items.length)},worker));
  if(ctrl.signal.aborted)return;
  if($('v88Sort').value==='score')found.sort((a,b)=>adjust(b.stock)-adjust(a.stock)||Number(b.stock.value_eok)-Number(a.stock.value_eok));
  else found.sort((a,b)=>Number(b.stock.value_eok)-Number(a.stock.value_eok));
  $('v88SearchStatus').textContent=`완료 · 기준일 ${asof} · 후보 ${universe.length} / 실제 분석 ${checked} / 조건 일치 ${found.length} / 시총 미확인 ${unknown} / 실패 묶음 ${failed}`+(failed?'\n⚠️ 일부 결과 누락 가능':'')+'\n※ 중견·대기업은 출처 기재 자료만 사용하며 시총 5,000억 이상과 다릅니다. 외인·기관 수급은 기준일 일치 자료만 표시합니다. 기술 조건은 매수 신호나 성공 확률이 아닙니다.';
  $('v88CSV').disabled=!found.length;render();
 }catch(e){$('v88SearchStatus').textContent='검색 중단/실패: '+e.message}
 finally{if(active===ctrl){active=null;$('v88Start').disabled=false;$('v88Stop').disabled=true;}}
}
function plot(analysis){
 const bars=analysis.bars.slice(-60),bb=analysis.bb,start=analysis.bars.length-bars.length;
 const W=650,H=220,pad=20,vals=bars.flatMap((b,i)=>[b.low,b.high,bb.upper[start+i],bb.lower[start+i]].filter(Number.isFinite));
 if(!vals.length)return node('span','','차트 없음');
 const min=Math.min(...vals),max=Math.max(...vals),diff=Math.max(1,max-min),x=i=>pad+(i+.5)*(W-2*pad)/bars.length,y=v=>pad+(max-v)/diff*(H-2*pad);
 const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox',`0 0 ${W} ${H}`);svg.setAttribute('role','img');svg.setAttribute('aria-label','최근 60거래일 볼린저 밴드 3선과 주가');
 function add(t,attrs){const e=document.createElementNS('http://www.w3.org/2000/svg',t);for(const [k,v]of Object.entries(attrs))e.setAttribute(k,String(v));svg.append(e);}
 for(const [key,col]of [['upper','#b77722'],['middle','#416fc5'],['lower','#1b9ac0']]){
   const pts=bars.map((_,i)=>({i,v:bb[key][start+i]})).filter(r=>Number.isFinite(r.v)).map(r=>`${x(r.i)},${y(r.v)}`).join(' ');
   if(pts)add('polyline',{points:pts,fill:'none',stroke:col,'stroke-width':2});
 }
 for(let i=0;i<bars.length;i++){const b=bars[i],color=b.close>=b.open?'#db424a':'#256dc8';
   add('line',{x1:x(i),x2:x(i),y1:y(b.high),y2:y(b.low),stroke:color,'stroke-width':1});
   add('rect',{x:x(i)-3.4,y:Math.min(y(b.open),y(b.close)),width:6.8,height:Math.max(1,Math.abs(y(b.close)-y(b.open))),fill:color});
 }
 return svg;
}
function pastSignal(bars,signal,strict){
 let count=0,open=[],close=[];
 const last=Math.min(bars.length-1,252);
 for(let end=Math.max(79,bars.length-last);end<bars.length-1;end++){
   const a=E.analyze(bars.slice(0,end+1),{strictness:strict});if(a.ready&&a.signals.includes(signal)){
     const old=bars[end],next=bars[end+1];if(!old||!next||num(old[4])===null||num(next[1])===null||num(next[4])===null||old[4]<=0)continue;
     const o=(next[1]/old[4]-1)*100,c=(next[4]/old[4]-1)*100;
     if(Number.isFinite(o)&&Number.isFinite(c)){count++;open.push(o);close.push(c);}
   }
 }
 if(!count)return {count:0};
 const mean=arr=>arr.reduce((s,x)=>s+x,0)/arr.length;
 return {count,openMean:mean(open),closeMean:mean(close),wins:100*close.filter(n=>n>0).length/count};
}
function render(){const out=$('v88Results');out.replaceChildren();
 if(!found.length){elt(out,'p','','일치 종목이 없습니다.');return}
 let shown=0;const page=20;
 function addPage(){for(const row of found.slice(shown,shown+page)){
  const x=row.stock,a=row.analysis,danger=a.risk==='danger'||x.risk_level==='high'||x.chase_risk===true;
  const card=elt(out,'article','v88-result');
  const title=elt(card,'div','v88-result-title',`${x.name} (${x.code})`);
  const status=elt(card,'span','v88-pill'+(danger?' warning':''),danger?'🔴 위험 관찰':'🟢 조건 관찰');
  elt(card,'div','',`종가 ${amount(x.price)}원 · 종베 ${x.score??'-'}점 · 위험조정 ${adjust(x)}점 · 거래대금 ${amount(x.value_eok)}억원 · 시총 ${row.cap===null?'미확인':amount(Math.round(row.cap/1e8))+'억원'}`);
  elt(card,'div','v88-tags',a.signals.map(s=>tags[s]||s).join(' · '));
  // Do not present an unverified company classification as an official finding.
  const corpLabel=row.corp?({large:'대기업',mid:'중견기업',sme:'중소기업'}[row.corp.category]):null;
  if(corpLabel)elt(card,'div','v88-reference',`🏢 기업 분류: ${corpLabel} · 출처 기재: ${row.corp.source} · 확인일 ${row.corp.checked_on} (원문 별도 확인 필요)`);
  else elt(card,'div','v88-reference','🏢 법정 기업 분류 미확인 · 시가총액과 별개');
  const flow=investorFlows?.[x.code];
  const validFlow=flow&&flow.source&&String(flow.source).trim().length>=3&&
       flow.observed_at_kst&&Number.isFinite(Date.parse(flow.observed_at_kst))&&
       new Date(flow.observed_at_kst).getTime() >= Date.parse(asof+'T09:00:00+09:00')&&
       new Date(flow.observed_at_kst).getTime() < Date.parse(asof+'T18:00:00+09:00')&&
       num(flow.foreign_net_eok)!==null&&num(flow.institution_net_eok)!==null&&
       Math.abs(num(flow.foreign_net_eok))<=100000&&Math.abs(num(flow.institution_net_eok))<=100000;
  const flowInfo=validFlow?`외국인 ${num(flow.foreign_net_eok)>=0?'+':''}${num(flow.foreign_net_eok).toFixed(1)}억원 · 기관 ${num(flow.institution_net_eok)>=0?'+':''}${num(flow.institution_net_eok).toFixed(1)}억원 · ${flow.source} · ${flow.observed_at_kst}`:
                           '외국인·기관 순매수: 확인된 해당일 자료 없음';
  elt(card,'div','v88-reference','📊 '+flowInfo);

  const actions=elt(card,'div','v88-row');const c=button(actions,'','📊 다음 날 시초가 분석',true);c.addEventListener('click',()=>{
    currentStock=row;$('v88Chosen').textContent=`선택 종목: ${x.name} (${x.code}) · 확정 종가 ${amount(x.price)}원 · 기준 ${asof}`;
    $('v88Close').value=String(x.price);$('v88ForecastOut').textContent='선택 완료. 수동 시나리오 또는 과거 검증 모델을 눌러주세요.';
    $('v88Chosen').scrollIntoView({behavior:'smooth',block:'center'});
  });
  const j=button(actions,'','기존 V8.7 상세 보기',true);j.addEventListener('click',()=>{
    const q=document.getElementById('query');if(!q){alert('기존 검색창을 찾을 수 없습니다.');return}q.value=x.code;
    try{if(typeof display==='function')display()}catch(_){}q.scrollIntoView({behavior:'smooth',block:'center'});
  });
  const details=elt(card,'details');elt(details,'summary','','3선 차트·패턴 과거 관찰');
  details.addEventListener('toggle',()=>{if(!details.open||details.dataset.loaded)return;details.dataset.loaded='1';
     details.append(plot(a));for(const signal of a.signals){const b=pastSignal(row.bars,signal,Number($('v88Strict').value));
     const div=elt(details,'div','v88-backtest',b.count===0?`${tags[signal]}: 과거 비교 관찰 없음`: `${tags[signal]}: 과거 ${b.count}건 · 익일 시가 갭 평균 ${b.openMean.toFixed(2)}% · 익일 종가 변동 평균 ${b.closeMean.toFixed(2)}% · 종가 상승 사례 ${(b.wins).toFixed(0)}%`);
     elt(div,'small','',b.count<20?'⚠️ 표본 20건 미만. 통계적 신뢰도가 낮습니다.':'동일 종목·조건의 사후 관찰치. 독립 표본·매매비용·거래 불가능한 갭을 보정하지 않았습니다.');
     }
  });
 }shown+=page;
 const old=root.querySelector('#v88More');if(old)old.remove();
 if(shown<found.length){const more=button(out,'v88More',`더 보기 (${Math.min(page,found.length-shown)}개)`,true);more.addEventListener('click',addPage)}
 }
 addPage();
}
function exportCSV(){if(!found.length)return;const head=['code','name','date','price','score','risk_score','market_cap_krw','corporate_category','value_eok','signals'];
 const enc=s=>{let v=String(s??'');if(/^[\s]*[=+@-]/.test(v))v="'"+v;return '"'+v.replaceAll('"','""')+'"'};
 const lines=[head.join(',')];for(const r of found){const x=r.stock;lines.push([x.code,x.name,asof,x.price,x.score,x.risk_score,r.cap,r.corp?.category||'',x.value_eok,r.analysis.signals.join('|')].map(enc).join(','))}
 const blob=new Blob(['\uFEFF'+lines.join('\r\n')],{type:'text/csv;charset=utf-8'}),url=URL.createObjectURL(blob),a=node('a');a.href=url;a.download=`jongbe-v8.8-${asof}.csv`;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),2000);
}
function scenario(){const out=$('v88ForecastOut'),close=num($('v88Close').value);
 if(close===null||close<=0){out.textContent='⚠️ 먼저 종목과 확정 종가를 입력하세요.';return}
 const factors={};for(const k of F.KEYS){const x=num($('v88_'+k).value);if(x===null){out.textContent='⚠️ 시장지표가 모두 필요합니다. 없는 값을 0으로 넣지 마세요.';return}
  if(Math.abs(x)>(k==='us10y_bp'?150:30)){out.textContent='⚠️ 입력값 범위가 지나치게 큽니다.';return}factors[k]=x;
 }
 // Demonstration weights only, not calibrated. Partial collinearity intentionally damped.
 const weights={general:[.15,.46,-.012,.09],semis:[.12,.42,-.012,.26],growth:[.23,.30,-.021,.12]}[$('v88Category').value];
 const gap=weights[0]*factors.nq_pct+weights[1]*factors.kospi_night_pct+weights[2]*factors.us10y_bp+weights[3]*factors.sox_pct;
 const price=Math.round(close*(1+gap/100));
 out.textContent=`🧮 임의 가중치 가정: ${price.toLocaleString('ko-KR')}원 · ${gap>=0?'+':''}${gap.toFixed(2)}%. 실제 예측값이나 확률이 아니며 오차 범위를 산출할 수 없습니다.`;
}
function forecastSelected(){const out=$('v88ForecastOut');
 if(!currentStock){out.textContent='먼저 통합검색으로 종목을 선택하세요.';return}
 if(!latest){out.textContent='시장지표 수집 파일을 확인하지 못했습니다.';return}
 const nowK=new Date(),parts=new Intl.DateTimeFormat('en-US',{timeZone:'Asia/Seoul',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(nowK);
 const part=k=>parts.find(x=>x.type===k)?.value||'';
 const day=part('year')+'-'+part('month')+'-'+part('day'),hhmm=Number(part('hour'))*60+Number(part('minute'));
 if(latest.session_date<day||(latest.session_date===day&&hhmm>=540)){out.textContent='⚠️ 이 시장자료의 대상 거래일 개장시각이 이미 지났습니다. 다음 거래일 예측으로 보여주지 않습니다.';return}
 // Safeguard against stale EOD data. Without an exact official KRX previous
 // session, any price estimate could accidentally use a close from days ago.
 if(!/^\d{4}-\d{2}-\d{2}$/.test(String(latest.previous_session||'')) ||
    latest.previous_session!==asof || currentStock.bars.at(-1)?.[0]!==asof){
    out.textContent='⚠️ 직전 한국 정규 거래일의 확정 종가와 야간시장 관측 대상일이 일치하지 않습니다. 예상액 표시를 중단합니다.';return;
 }
 // A manually typed scenario close is not the validated closing-price input.
 // Use the actual selected row's EOD price, not the editable input.
 const verifiedClose=num(currentStock.stock.price);
 if(verifiedClose===null || verifiedClose<=0 || Number(currentStock.bars.at(-1)?.[4])!==verifiedClose){
    out.textContent='⚠️ 종목 목록과 확정 차트의 종가가 다릅니다. 예측을 보류합니다.';return;
 }
 const p=F.forecast(currentStock.bars,hist,latest,verifiedClose);
 if(p.status==='research')out.textContent=`📌 연구용 다음 시초가: ${amount(p.predicted_open)}원 (갭 ${p.predicted_gap_pct>=0?'+':''}${p.predicted_gap_pct.toFixed(2)}%) · 과거 검증 오차 참고구간 ${amount(p.reference_low)}~${amount(p.reference_high)}원. 별도 기간 ${p.holdout}거래일 MAE ${p.mae_pct.toFixed(2)}%p (종가 유지 기준선 ${p.baseline_mae_pct.toFixed(2)}%p). 실제 가격 보장이나 신뢰구간이 아닙니다.`;
 else out.textContent=`⚠️ 예상액 표시 보류: ${p.reason||'자료 검증 실패'}${p.count!==undefined?' · 유효 기록 '+p.count+'개':''}`;
}
init();
})();
