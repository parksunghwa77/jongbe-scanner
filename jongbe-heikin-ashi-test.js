/* Jongbe Heikin-Ashi test add-on v1: read-only, confirmed OHLCV only.
 * Load AFTER the existing index.html inline chart script.
 * Keeps the original chart untouched; adds an alternate HA canvas.
 */
(() => {
  'use strict';
  if (typeof window.buildChart !== 'function') {
    console.warn('Jongbe HA: buildChart not found. Load add-on after the original chart script.');
    return;
  }
  if (window.__jongbeHAInstalled) return;
  window.__jongbeHAInstalled = true;
  const original = window.buildChart;
  const num = x => Number(x);
  const mean = (arr, n, i) => i + 1 < n ? null : arr.slice(i-n+1,i+1).reduce((a,b)=>a+b,0)/n;
  function heikinAshi(records) {
    const out=[];
    for (const r of records) {
      const o=num(r[1]),h=num(r[2]),l=num(r[3]),c=num(r[4]);
      if (![o,h,l,c].every(Number.isFinite) || o<=0 || c<=0 || h<Math.max(o,c) || l>Math.min(o,c)) continue;
      const close=(o+h+l+c)/4;
      const open=out.length ? (out.at(-1).open+out.at(-1).close)/2 : (o+c)/2;
      out.push({date:r[0],open,close,high:Math.max(h,open,close),low:Math.min(l,open,close),volume:num(r[5]),realClose:c});
    }
    return out;
  }
  window.JongbeHeikinAshi = Object.freeze({compute:heikinAshi});
  window.buildChart = function(parent, records, code) {
    original.apply(this, arguments);
    if (!parent || !Array.isArray(records) || !records.length) return;
    const daily = parent.firstElementChild;
    if (!daily) return;
    const ha = heikinAshi(records);
    if (!ha.length) return;
    const switcher=document.createElement('div');
    switcher.style.cssText='display:flex;gap:8px;flex-wrap:wrap;margin:8px 0;align-items:center';
    const regular=document.createElement('button'),alternate=document.createElement('button');
    for(const b of [regular,alternate]){
      b.type='button';
      b.style.cssText='min-height:44px;padding:9px 13px;border:1px solid #99aec8;border-radius:9px;background:#fff;color:#163552;font-size:14px;font-weight:700;cursor:pointer';
    }
    regular.textContent='일반 캔들';alternate.textContent='하이킨 아시';
    switcher.append(regular,alternate);
    const panel=document.createElement('section');
    panel.hidden=true;
    panel.style.cssText='margin:6px 0 15px';
    const caption=document.createElement('p');
    caption.style.cssText='color:#425b78;font-size:13px;margin:5px 0 10px;line-height:1.5';
    caption.textContent='하이킨 아시는 변환 캔들입니다. 일반 시세가 아니므로 HA 시가·종가를 실제 주문 가격으로 사용하지 마세요. 이동평균선은 실제 종가 기준입니다.';
    const periodBar=document.createElement('div');
    periodBar.style.cssText='display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px';
    const holder=document.createElement('div');
    holder.style.cssText='overflow-x:auto;max-width:100%;touch-action:pan-x';
    const canvas=document.createElement('canvas');
    canvas.height=360;
    canvas.style.cssText='height:360px;display:block';
    canvas.setAttribute('role','img');canvas.setAttribute('aria-label',code+' 하이킨 아시 캔들과 실제 종가 이동평균선');
    holder.append(canvas);
    const detail=document.createElement('p');
    detail.style.cssText='font-size:13px;color:#294763;margin:10px 0 0';
    panel.append(caption,periodBar,holder,detail);
    parent.insertBefore(switcher,daily);
    parent.append(panel);
    let current=21;
    const periods=[['1개월',21],['3개월',63],['6개월',126],['1년',252]];
    const buttons=[];
    for (const [label,count] of periods){
      const btn=document.createElement('button');btn.type='button';btn.textContent=label;
      btn.style.cssText='min-height:38px;padding:6px 10px;border:1px solid #99aec8;border-radius:8px;background:#fff;color:#163552';
      btn.addEventListener('click',()=>{current=count;draw();});
      periodBar.append(btn);buttons.push(btn);
    }
    function draw(){
      if(panel.hidden || !holder.clientWidth) return;
      const view=ha.slice(-current);
      const start=ha.length-view.length;
      const barWidth=current<=21?18:current<=63?12:current<=126?9:6;
      const width=Math.max(holder.clientWidth-2,64+view.length*barWidth+18);
      canvas.style.width=width+'px';
      const dpr=Math.min(window.devicePixelRatio||1,2);
      canvas.width=Math.round(width*dpr);canvas.height=Math.round(360*dpr);
      const g=canvas.getContext('2d');if(!g)return;
      g.setTransform(dpr,0,0,dpr,0,0);
      const left=55,right=13,top=18,bottom=277,vt=294,vb=339;
      g.fillStyle='#ffffff';g.fillRect(0,0,width,360);
      const closes=ha.map(x=>x.realClose);
      const lines=[5,20,200].map(n=>({n,color:n===5?'#1b62ca':n===20?'#e47d13':'#9d5de0',vals:closes.map((_,i)=>mean(closes,n,i))}));
      const price=[...view.flatMap(x=>[x.high,x.low])];
      for(const ln of lines)for(let i=start;i<ha.length;i++)if(Number.isFinite(ln.vals[i])){
        const v=ln.vals[i],mid=(Math.min(...price)+Math.max(...price))/2;
        if(Math.abs(v-mid)<mid*.20)price.push(v);
      }
      let lo=Math.min(...price),hi=Math.max(...price);
      const pad=Math.max((hi-lo)*.07,hi*.003,1);lo=Math.max(0,lo-pad);hi+=pad;
      const y=p=>bottom-(p-lo)/(hi-lo)*(bottom-top);
      const step=(width-left-right)/view.length,x=i=>left+(i+.5)*step;
      g.font='11px system-ui';g.textAlign='right';g.textBaseline='middle';
      for(let k=0;k<5;k++){
        const yy=top+(bottom-top)*k/4;
        g.strokeStyle='#e3eaf3';g.beginPath();g.moveTo(left,yy);g.lineTo(width-right,yy);g.stroke();
        g.fillStyle='#425b78';g.fillText(Math.round(hi-(hi-lo)*k/4).toLocaleString('ko-KR'),left-5,yy);
      }
      const maxV=Math.max(1,...view.map(r=>Number.isFinite(r.volume)?r.volume:0));
      view.forEach((r,i)=>{
        const up=r.close>=r.open,col=up?'#e34e61':'#2474d9',cx=x(i);
        g.strokeStyle=col;g.fillStyle=col;
        g.beginPath();g.moveTo(cx,y(r.high));g.lineTo(cx,y(r.low));g.stroke();
        const topY=y(Math.max(r.open,r.close)),bottomY=y(Math.min(r.open,r.close));
        g.fillRect(cx-Math.max(1,step*.32),topY,Math.max(2,step*.64),Math.max(1,bottomY-topY));
        const vol=Math.max(0,r.volume||0)/maxV*(vb-vt);
        g.globalAlpha=.6;g.fillRect(cx-Math.max(1,step*.32),vb-vol,Math.max(2,step*.64),vol);g.globalAlpha=1;
      });
      for(const ln of lines){g.strokeStyle=ln.color;g.lineWidth=1.5;g.beginPath();let started=false;
        view.forEach((_,i)=>{const v=ln.vals[start+i];if(!Number.isFinite(v)){started=false;return;}
          if(!started){g.moveTo(x(i),y(v));started=true;}else g.lineTo(x(i),y(v));});g.stroke();}
      g.fillStyle='#425b78';g.textAlign='center';g.font='10px system-ui';
      for(let i=0;i<view.length;i+=Math.max(1,Math.ceil(view.length/5)))g.fillText(view[i].date.slice(5),x(i),355);
      for(let i=0;i<buttons.length;i++){
        const active=periods[i][1]===current;
        buttons[i].style.background=active?'#deebff':'#fff';buttons[i].setAttribute('aria-pressed',String(active));
      }
      const prev=ha.at(-2),last=ha.at(-1);
      const turn=prev && last.close>=last.open && prev.close<prev.open?'양봉 전환 관찰':prev && last.close<last.open && prev.close>=prev.open?'음봉 전환 관찰':'전환 없음';
      detail.textContent=`${last.date} · HA ${last.close>=last.open?'양봉':'음봉'} · ${turn} · 실제 종가 ${Math.round(last.realClose).toLocaleString('ko-KR')}원 (하이킨 아시만으로 매수 판정하지 않음)`;
      holder.scrollLeft=Math.max(0,holder.scrollWidth-holder.clientWidth);
    }
    function mode(active){
      daily.hidden=active;panel.hidden=!active;
      regular.style.background=active?'#fff':'#deebff';alternate.style.background=active?'#deebff':'#fff';
      regular.setAttribute('aria-pressed',String(!active));alternate.setAttribute('aria-pressed',String(active));
      if(active)draw();
    }
    regular.addEventListener('click',()=>mode(false));alternate.addEventListener('click',()=>mode(true));
    mode(false);
    if(typeof ResizeObserver!=='undefined'){
      const observer=new ResizeObserver(()=>{if(!panel.isConnected)observer.disconnect();else if(!panel.hidden)draw();});
      observer.observe(holder);
    }
  };
})();
