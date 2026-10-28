/* 종베 스캐너 v8.6 add-on: 확정 일봉 적삼병/흑삼병 및 과거 다음 거래일 검증 */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const esc = s => String(s ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  const fmt = n => Number(n).toLocaleString('ko-KR');
  const panel = document.createElement('section');
  panel.id='v86-patterns';
  panel.style.cssText='margin:18px 0;padding:16px;background:#19263c;border:1px solid #53759a;border-radius:13px;color:#e8f2ff';
  panel.innerHTML=`<h2>🕯️ v8.6 · 적삼병 / 흑삼병 자동 검색</h2>
    <p>확정 일봉 3개로 판정하며, 과거 발생 사례의 다음 거래일 시가·종가 변화도 함께 검증합니다.</p>
    <div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin:12px 0">
      <label>패턴<select id="v86type"><option value="all">모두</option><option value="red">🔴 적삼병</option><option value="black">⚫ 흑삼병</option></select></label>
      <label>발생 시점<select id="v86window"><option value="0">최신 거래일</option><option value="3">최근 3거래일</option><option value="5">최근 5거래일</option></select></label>
      <label>시장<select id="v86market"><option value="ALL">코스피 + 코스닥</option><option value="KOSPI">코스피</option><option value="KOSDAQ">코스닥</option></select></label>
      <label>판정<select id="v86strict"><option value="basic">기본 (몸통 40% 이상)</option><option value="strict">엄격 (몸통 60% 이상)</option></select></label>
      <label>다음 거래일 왕복 비용<select id="v86cost"><option value="0">비용 제외</option><option value="0.3">0.3%p</option><option value="0.5" selected>0.5%p</option><option value="0.7">0.7%p</option></select></label>
    </div>
    <button id="v86go" type="button">검색 + 과거 성과 검증</button>
    <p id="v86status" aria-live="polite">검색 버튼을 눌러 주세요.</p>
    <div id="v86summary"></div><div id="v86results" style="overflow-x:auto"></div>
    <small style="display:block;margin-top:12px">통계: 각 패턴의 세 번째 날 종가에 매수했다고 가정 → 다음 거래일 시가 및 종가에 매도. 비용은 왕복 비용·슬리피지 합계의 단순 차감 가정. 실제 체결을 뜻하지 않습니다. 최신일 발생 패턴은 다음날 가격이 아직 없으므로 성과에 포함하지 않습니다. 여러 종목·일자의 관측치는 독립적이지 않고 생존편향이 있을 수 있습니다.</small>`;
  const insertBefore = document.querySelector('section.filters[aria-label="검색 조건"]');
  if(insertBefore) insertBefore.before(panel);
  else (document.querySelector('main') || document.body).append(panel);
  function detect(rows, i, strict) {
    if(i<2)return null;
    const v=rows.slice(i-2,i+1).map(r=>({d:r[0],o:+r[1],h:+r[2],l:+r[3],c:+r[4],volume:+r[5]}));
    if(v.some(c=>![c.o,c.h,c.l,c.c].every(Number.isFinite)||c.o<=0||c.c<=0||c.h<=c.l))return null;
    const minBody=strict?0.6:0.4;
    for(const type of ['red','black']){
      const rising=type==='red';
      if(!v.every(b=>(rising?b.c>b.o:b.c<b.o)&&Math.abs(b.c-b.o)/(b.h-b.l)>=minBody))continue;
      if(!((rising?v[0].c<v[1].c&&v[1].c<v[2].c:v[0].c>v[1].c&&v[1].c>v[2].c)))continue;
      if(![1,2].every(j=>{
        const prev=v[j-1],current=v[j];
        const inside=current.o>=Math.min(prev.o,prev.c)&&current.o<=Math.max(prev.o,prev.c);
        return inside&&(!strict||(rising?(current.h>prev.h&&current.l>=prev.l):(current.l<prev.l&&current.h<=prev.h)));
      }))continue;
      const prior=rows.slice(Math.max(0,i-22),i-2).map(r=>+r[5]).filter(x=>x>0&&Number.isFinite(x));
      const volRatio=prior.length>=5?(v.reduce((a,b)=>a+b.volume,0)/3)/(prior.reduce((a,b)=>a+b,0)/prior.length):null;
      return {type,date:v[2].d,close:v[2].c,volumeRatio:volRatio};
    }
    return null;
  }
  function metric(events, key, cost){
    const vals=events.map(e=>e[key]).filter(Number.isFinite).map(x=>x-cost);
    if(!vals.length)return '자료 없음';
    const avg=vals.reduce((a,b)=>a+b,0)/vals.length;
    const win=vals.filter(x=>x>0).length/vals.length*100;
    return `${vals.length}건 / 평균 ${avg>=0?'+':''}${avg.toFixed(2)}% / 상승 ${win.toFixed(1)}%`;
  }
  $('v86go').addEventListener('click',async()=>{
    const button=$('v86go'),status=$('v86status'),out=$('v86results'),summary=$('v86summary');
    button.disabled=true;out.replaceChildren();summary.replaceChildren();status.textContent='일봉 검사 준비 중…';
    try{
      if(typeof dataRows==='undefined'||!Array.isArray(dataRows)||!dataRows.length)throw Error('v5 확정 일봉 분석 결과가 없습니다. GitHub Actions 자동 분석부터 실행하세요.');
      if(typeof infoDate==='undefined'||!infoDate||infoDate==='-')throw Error('데이터 기준일이 없습니다.');
      const type=$('v86type').value,windowSize=+$('v86window').value,market=$('v86market').value;
      const strict=$('v86strict').value==='strict',cost=+$('v86cost').value;
      const stocks=dataRows.filter(x=>(market==='ALL'||x.market===market)&&/^\d{6}$/.test(String(x.code)));
      const groups=new Map();for(const stock of stocks){const pre=String(stock.code).slice(0,2);if(!groups.has(pre))groups.set(pre,[]);groups.get(pre).push(stock);}
      const seen=[],historical=[];let done=0,failed=0;
      const entries=[...groups.entries()];
      for(let start=0;start<entries.length;start+=4){
        await Promise.all(entries.slice(start,start+4).map(async ([pre,list])=>{
          try{
            const r=await fetch('./charts/'+pre+'.json?asof='+encodeURIComponent(infoDate),{cache:'no-store'});
            if(!r.ok)throw Error('HTTP '+r.status);
            const bundle=await r.json();
            if(bundle.schema!=='jongbe-ohlcv-v1'||bundle.asof!==infoDate||!bundle.stocks)throw Error('차트 기준일 불일치');
            for(const stock of list){
              const bars=bundle.stocks[String(stock.code)];if(!Array.isArray(bars)||bars.length<3)continue;
              const found=[];
              for(let i=2;i<bars.length;i++){
                const p=detect(bars,i,strict);if(!p||(type!=='all'&&p.type!==type))continue;
                if(i<bars.length-1){
                  const next=bars[i+1],nextOpen=+next[1],nextClose=+next[4];
                  if(nextOpen>0&&nextClose>0){historical.push({...p,openPct:(nextOpen/p.close-1)*100,closePct:(nextClose/p.close-1)*100});}
                }
                if(i>=bars.length-1-windowSize)found.push(p);
              }
              if(found.length){found.sort((a,b)=>String(b.date).localeCompare(String(a.date)));seen.push({...found[0],stock});}
            }
          }catch(e){failed++;}finally{done++;status.textContent='확인 '+done+'/'+entries.length+'묶음 · 조건 일치 '+seen.length+'종목';}
        }));
      }
      seen.sort((a,b)=>String(b.date).localeCompare(String(a.date))||(b.volumeRatio??0)-(a.volumeRatio??0));
      const metrics=types=>historical.filter(x=>types==='all'||x.type===types);
      summary.innerHTML=`<p><b>과거 검증 (확정 일봉에 한함)</b> · 다음날 시가: 종가매수→익일 시가 매도 / 다음날 종가: 종가매수→익일 종가 매도</p>`+
        ['red','black'].filter(k=>type==='all'||type===k).map(k=>`<p><b>${k==='red'?'🔴 적삼병':'⚫ 흑삼병'}</b><br>익일 시가: ${metric(metrics(k),'openPct',cost)}<br>익일 종가: ${metric(metrics(k),'closePct',cost)}</p>`).join('');
      status.textContent=`기준일 ${infoDate} · ${fmt(stocks.length)}종목 중 최근 조건 일치 ${fmt(seen.length)}종목`+(failed?` · ${failed}개 차트 묶음 로드 실패: 일부 결과 누락`:'');
      if(!seen.length){out.textContent='최근 조건에 해당하는 종목이 없습니다.';return;}
      const table=document.createElement('table');table.className='history';table.style.width='100%';
      table.innerHTML='<thead><tr><th>종목</th><th>패턴</th><th>발생일</th><th>거래량 배율</th><th>종베 점수</th></tr></thead>';
      const body=document.createElement('tbody');
      for(const p of seen){const tr=document.createElement('tr');tr.innerHTML=`<td>${esc(p.stock.name)} (${esc(p.stock.code)})</td><td>${p.type==='red'?'🔴 적삼병':'⚫ 흑삼병'}</td><td>${esc(p.date)}</td><td>${p.volumeRatio==null?'자료 부족':p.volumeRatio.toFixed(2)+'배'}</td><td>${esc(p.stock.score??'-')}</td>`;body.append(tr);}
      table.append(body);out.append(table);
    }catch(err){status.textContent='오류: '+err.message;}finally{button.disabled=false;}
  });
})();
