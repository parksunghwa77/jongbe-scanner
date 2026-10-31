/* Jongbe v8.8 historical next-open gap research engine. NO trading, NO guaranteed forecasts.
 * Feature rows keyed by Korean target stock trading session (market observations obtained
 * before 09:00 KST). Labels are the opening gap against previous session CLOSE.
 */
(function(root, factory){
 const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;
 else root.JongbeForecast=api;
})(typeof globalThis!=='undefined'?globalThis:this,function(){
 'use strict';
 const KEYS=['nq_pct','kospi_night_pct','us10y_bp','sox_pct'];
 const safe=v=>v!==null&&v!==''&&v!==undefined&&Number.isFinite(Number(v));
 const dateOK=s=>/^\d{4}-\d{2}-\d{2}$/.test(String(s||''));
 function extractMarket(row){
   if(!row||!dateOK(row.session_date)||row.complete!==true)return null;
   // Observed pre-open timestamps are essential: the model must never train on
   // factors appended after the corresponding stock OPEN (look-ahead bias).
   const stamp=String(row.generated_at_kst||'');
   const received=Date.parse(stamp);
   const cutoff=Date.parse(row.session_date+'T09:00:00+09:00');
   if(!/^\d{4}-\d{2}-\d{2}T/.test(stamp)||!Number.isFinite(received)||
      !Number.isFinite(cutoff)||received>=cutoff||received<cutoff-9*3600*1000)return null;
   const src=row.factors||{};
   if(!KEYS.every(k=>safe(src[k])&&Math.abs(Number(src[k]))<=(k==='us10y_bp'?150:30)))return null;
   if(!row.collected_before_open)return null;
   return KEYS.map(k=>Number(src[k]));
 }
 function trainingRows(bars,history){
   const xs=Array.isArray(bars)?bars:[], markets=new Map();
   for(const item of (Array.isArray(history)?history:[])){
     const x=extractMarket(item);if(x)markets.set(item.session_date,x);
   }
   const rows=[];
   for(let i=1;i<xs.length;i++){
     const old=xs[i-1], next=xs[i];
     if(!Array.isArray(old)||!Array.isArray(next)||old.length<6||next.length<6)continue;
     if(!safe(old[4])||!safe(next[1])||Number(old[4])<=0||Number(next[1])<=0)continue;
     const features=markets.get(String(next[0]));
     if(features){const gap=100*(Number(next[1])/Number(old[4])-1);
       if(Number.isFinite(gap)&&Math.abs(gap)<=30)rows.push({date:String(next[0]),x:features,y:gap});
     }
   }
   return rows.sort((a,b)=>a.date.localeCompare(b.date));
 }
 // Gaussian elimination over a 5x5 system, with standardized factors and ridge penalty.
 function solve(A,B){
   const n=B.length,a=A.map((row,i)=>row.slice().concat(B[i]));
   for(let col=0;col<n;col++){
     let pivot=col;for(let r=col+1;r<n;r++)if(Math.abs(a[r][col])>Math.abs(a[pivot][col]))pivot=r;
     if(Math.abs(a[pivot][col])<1e-8)return null;
     [a[pivot],a[col]]=[a[col],a[pivot]];
     const div=a[col][col];for(let c=col;c<=n;c++)a[col][c]/=div;
     for(let r=0;r<n;r++)if(r!==col){const fac=a[r][col];for(let c=col;c<=n;c++)a[r][c]-=fac*a[col][c];}
   }
   return a.map(row=>row[n]);
 }
 function fit(rows,lambda=14){
   if(!Array.isArray(rows)||rows.length<60)return null;
   const p=KEYS.length;
   const mean=KEYS.map((_,i)=>rows.reduce((s,r)=>s+r.x[i],0)/rows.length);
   const sd=KEYS.map((_,i)=>Math.sqrt(rows.reduce((s,r)=>s+(r.x[i]-mean[i])**2,0)/rows.length));
   const norm=x=>x.map((v,i)=>(v-mean[i])/(sd[i]>1e-8?sd[i]:1));
   const XtX=Array.from({length:p+1},()=>Array(p+1).fill(0)), Xty=Array(p+1).fill(0);
   for(const r of rows){const v=[1,...norm(r.x)];for(let i=0;i<=p;i++){
     Xty[i]+=v[i]*r.y;for(let j=0;j<=p;j++)XtX[i][j]+=v[i]*v[j];
   }}
   for(let i=1;i<=p;i++)XtX[i][i]+=lambda;
   const beta=solve(XtX,Xty);if(!beta)return null;
   return {beta,predict:x=>beta[0]+norm(x).reduce((s,v,i)=>s+v*beta[i+1],0)};
 }
 function evaluate(records,latest,price,minTrain=60,holdout=20){
   if(!safe(price)||Number(price)<=0)return {status:'unavailable',reason:'확정 종가가 없습니다.'};
   const rows=Array.isArray(records)?records:[];
   if(rows.length<minTrain+holdout)return {status:'collecting',count:rows.length,required:minTrain+holdout,reason:'시장지표 4종의 시점 검증된 과거 기록이 부족합니다.'};
   const newest=extractMarket(latest);
   if(!newest)return {status:'unavailable',reason:'최신 4개 시장지표 중 미확인 값이 있거나 개장 후 수집된 자료입니다.'};
   if(rows.at(-1)?.date>=latest.session_date)return {status:'unavailable',reason:'예측 대상일이 이미 과거 학습 표본에 포함되었습니다.'};
   // Walk-forward on the final holdout sessions. No holdout value in any training fit.
   const recent=rows.slice(-Math.max(holdout+minTrain,130));
   const predictions=[];
   for(let i=recent.length-holdout;i<recent.length;i++){
     const model=fit(recent.slice(0,i),14);
     if(!model)return {status:'collecting',reason:'학습 표본이 부족합니다.'};
     const r=recent[i];predictions.push({date:r.date,actual:r.y,predicted:model.predict(r.x)});
   }
   const mae=predictions.reduce((s,r)=>s+Math.abs(r.actual-r.predicted),0)/predictions.length;
   const baseline=predictions.reduce((s,r)=>s+Math.abs(r.actual),0)/predictions.length;
   const coverage=predictions.filter(r=>Math.sign(r.actual)===Math.sign(r.predicted)).length/predictions.length;
   if(mae>=baseline)return {status:'unverified',count:rows.length,holdout:predictions.length,
     mae_pct:mae,baseline_mae_pct:baseline,reason:'과거 검증에서 종가 유지 가정보다 예측 오차가 작지 않아 예상액을 표시하지 않습니다.'};
   const model=fit(recent);if(!model)return {status:'unavailable',reason:'모형 추정 실패'};
   const gap=Math.max(-20,Math.min(20,model.predict(newest)));
   const errors=predictions.map(r=>Math.abs(r.actual-r.predicted)).sort((a,b)=>a-b);
   // Historic residual span, not a formal confidence interval. 80% in-sample coverage by construction.
   const spread=Math.max(0.2,errors[Math.ceil(.80*(errors.length-1))]);
   const raw=Number(price)*(1+gap/100);
   return {status:'research',target_session:latest.session_date,predicted_gap_pct:gap,
     predicted_open:Math.round(raw),reference_low:Math.round(Number(price)*(1+(gap-spread)/100)),
     reference_high:Math.round(Number(price)*(1+(gap+spread)/100)),error_band_pct:spread,
     mae_pct:mae,baseline_mae_pct:baseline,sign_match_pct:100*coverage,
     count:rows.length,holdout:predictions.length,
     reason:'과거 관측 오차 기반 참고값입니다. 실제 시초가의 보장 범위나 성공 확률은 아닙니다.'};
 }
 function forecast(bars,history,latest,close){return evaluate(trainingRows(bars,history),latest,close);}
 return {KEYS,extractMarket,trainingRows,fit,evaluate,forecast};
});
