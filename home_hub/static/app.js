/* Home Hub front end. All data comes from the local API; URLs are relative so the
   app also works behind Home Assistant ingress. */
"use strict";
const C={solar:"#FFC94D",home:"#6EA8FE",grid:"#B892FF",exp:"#FF7EB6",batt:"#34D3C4",good:"#5BE38F",warn:"#FF9B4A",crit:"#FF4D6D",info:"#8AA0C8",ink:"#EEF2FB",ink2:"#AAB4CC",ink3:"#6E7A96",line:"#1F2A44"};
const STRING_COLORS=["#FFC94D","#FF8F5E","#FFE08A","#F2A65A"];
const $=s=>document.querySelector(s);
const fmt=(n,d=0)=>n==null||isNaN(n)?"–":Number(n).toLocaleString("en-ZA",{minimumFractionDigits:d,maximumFractionDigits:d});
const hh=h=>String(h).padStart(2,"0")+":00";
const mm=m=>String(Math.floor(m/60)).padStart(2,"0")+":"+String(Math.round(m%60)).padStart(2,"0");
const sum=a=>a.reduce((s,v)=>s+(v||0),0);
const esc=s=>String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const monthName=k=>new Date(k+"-15T12:00:00").toLocaleDateString("en-ZA",{month:"short"});
const R=v=>"R"+fmt(v);

/* ---------- api ---------- */
async function api(path,opts){const r=await fetch(path,opts);if(!r.ok){const e=new Error(r.status);e.status=r.status;throw e}return r.json()}
function toast(msg){const t=$("#toast");t.textContent=msg;t.hidden=false;clearTimeout(toast._t);toast._t=setTimeout(()=>t.hidden=true,3000)}

/* ---------- echarts helpers ---------- */
const base={backgroundColor:"transparent",textStyle:{fontFamily:"Inter, system-ui, sans-serif",color:C.ink2},animationDuration:900,animationEasing:"cubicOut",
  tooltip:{backgroundColor:"rgba(13,18,32,.96)",borderColor:"#2A3757",borderWidth:1,textStyle:{color:C.ink,fontSize:12},extraCssText:"border-radius:12px;box-shadow:0 10px 30px rgba(0,0,0,.4);"}};
const ax=(o={})=>Object.assign({axisLine:{lineStyle:{color:C.line}},axisTick:{show:false},axisLabel:{color:C.ink3,fontSize:11,fontFamily:"IBM Plex Mono, monospace"},splitLine:{lineStyle:{color:"rgba(31,42,68,.6)",type:[3,4]}}},o);
const monoLabel=(o={})=>Object.assign({color:C.ink3,fontSize:11,fontFamily:"IBM Plex Mono, monospace"},o);
function hexA(h,a){const n=parseInt(h.slice(1),16);return `rgba(${n>>16},${n>>8&255},${n&255},${a})`}
const grad=(c,a1=.45,a2=0)=>new echarts.graphic.LinearGradient(0,0,0,1,[{offset:0,color:hexA(c,a1)},{offset:1,color:hexA(c,a2)}]);
const charts={};
function mk(id,opt,merge){const el=document.getElementById(id);if(!el)return;let c=echarts.getInstanceByDom(el)||echarts.init(el);c.setOption(merge?opt:Object.assign({},base,opt),!merge);charts[id]=c;return c}
addEventListener("resize",()=>Object.values(charts).forEach(c=>c.resize()));

const IC={
 crit:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 3 2 20h20zM12 10v4M12 17h.01"/></svg>',
 warn:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><path d="M12 7v6M12 16.5h.01"/></svg>',
 info:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5h.01"/></svg>',
 check:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><path d="m5 12 5 5 9-10"/></svg>',
 sun:'<svg viewBox="0 0 24 24" fill="none" stroke="#FFC94D" stroke-width="1.8"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>',
 cloudsun:'<svg viewBox="0 0 24 24" fill="none" stroke-width="1.8"><circle cx="8" cy="8" r="3" stroke="#FFC94D"/><path d="M8 2v1.5M2 8h1.5M3.8 3.8l1 1M12.2 3.8l-1 1" stroke="#FFC94D"/><path d="M9 19h8a3.5 3.5 0 0 0 0-7 5 5 0 0 0-9.5 1.5A2.8 2.8 0 0 0 9 19z" stroke="#AAB4CC"/></svg>',
 cloud:'<svg viewBox="0 0 24 24" fill="none" stroke="#AAB4CC" stroke-width="1.8"><path d="M7 18h10a4 4 0 0 0 0-8 6 6 0 0 0-11.6 1.5A3.3 3.3 0 0 0 7 18z"/></svg>',
 storm:'<svg viewBox="0 0 24 24" fill="none" stroke-width="1.8"><path d="M7 16h10a4 4 0 0 0 0-8 6 6 0 0 0-11.6 1.5A3.3 3.3 0 0 0 7 16z" stroke="#AAB4CC"/><path d="m12 15-2 4h3l-2 4" stroke="#FFC94D"/></svg>',
 rain:'<svg viewBox="0 0 24 24" fill="none" stroke-width="1.8"><path d="M7 15h10a4 4 0 0 0 0-8 6 6 0 0 0-11.6 1.5A3.3 3.3 0 0 0 7 15z" stroke="#AAB4CC"/><path d="M9 18v2M13 18v2M17 18v2" stroke="#6EA8FE"/></svg>'
};
const wxIcon=c=>c>=95?IC.storm:c>=51?IC.rain:c>=3?IC.cloud:c>=1?IC.cloudsun:IC.sun;
const wxName=c=>c>=95?"Thunderstorms":c>=80?"Showers":c>=61?"Rain":c>=51?"Drizzle":c>=45?"Fog":c>=3?"Overcast":c>=1?"Partly cloudy":"Sunny";
const SEV={crit:"High",warn:"Medium",info:"Low"};

/* ---------- state ---------- */
const ST={live:null,views:{},alerts:null};
const VIEWS=["overview","energy","appliances","habits","weather","plan","alerts"];
let current="overview";

async function loadView(v){
  if(v==="alerts"){ST.alerts=await api("api/alerts");return}
  const deps={overview:["overview","weather"],energy:["energy"],appliances:["appliances"],habits:["habits"],weather:["weather"],plan:["plan"]}[v];
  await Promise.all(deps.map(async d=>{ST.views[d]=await api("api/view/"+d)}));
  if(v==="overview"&&!ST.alerts)ST.alerts=await api("api/alerts");
}

async function show(v){
  current=v;
  document.querySelectorAll(".view").forEach(s=>s.hidden=s.dataset.view!==v);
  document.querySelectorAll(".rail a").forEach(a=>a.dataset.v===v?a.setAttribute("aria-current","page"):a.removeAttribute("aria-current"));
  for(const id in charts){const el=document.getElementById(id);if(!el||el.closest(".view").hidden){charts[id].dispose();delete charts[id]}}
  scrollTo({top:0});
  try{await loadView(v);requestAnimationFrame(()=>{builders[v]();Object.values(charts).forEach(c=>c.resize())})}
  catch(e){const h=document.querySelector(`.view[data-view="${v}"] h1`);if(h)h.textContent=e.status===503?"Collecting your data from Home Assistant. This takes a minute the first time.":"Couldn't reach the Home Hub service.";setTimeout(()=>current===v&&show(v),10000)}
}
function route(){show(VIEWS.includes(location.hash.slice(1))?location.hash.slice(1):"overview")}
addEventListener("hashchange",route);

/* ================= LIVE ================= */
async function pollLive(){
  try{
    ST.live=await api("api/live");
    $("#conn").textContent="Connected";$("#conn-sub").textContent="Updated "+new Date().toLocaleTimeString("en-ZA",{hour:"2-digit",minute:"2-digit",second:"2-digit"});
    if(current==="overview"&&ST.views.overview)renderLive();
  }catch(e){$("#conn").textContent="Reconnecting…"}
}
async function pollAlerts(){try{ST.alerts=await api("api/alerts");badge()}catch(e){}}
function openAlerts(){return (ST.alerts?.alerts||[]).filter(a=>!a.resolved_at).sort((a,b)=>"cwi".indexOf(a.severity[0])-"cwi".indexOf(b.severity[0]))}
function badge(){const n=openAlerts().filter(a=>!a.acked_at&&a.severity!=="info").length;const b=$("#badge");b.hidden=!n;b.textContent=n}

/* ================= OVERVIEW ================= */
let snap="now";
function flowOpt(s){
  const N={solar:[50,82],batt:[14,52],grid:[86,52],home:[50,22]};
  const nodes=[["Solar",N.solar,C.solar,s.solar>20?fmt(s.solar)+" W":"Asleep"],["Grid",N.grid,C.grid,s.gridIn>20?fmt(s.gridIn)+" W in":s.gridOut>20?fmt(s.gridOut)+" W out":"idle"],["House",N.home,C.home,fmt(s.load)+" W"]];
  if(s.hasBatt)nodes.push(["Battery",N.batt,C.batt,(s.soc!=null?Math.round(s.soc)+"% · ":"")+(s.bOut>20?fmt(s.bOut)+" W out":s.bIn>20?fmt(s.bIn)+" W in":"idle")]);
  const L=[],add=(a,b,w,c)=>{if(w>20)L.push({coords:[a,b],w,c})};
  let solarLeft=s.solar;
  const toHouse=Math.min(solarLeft,s.load);add(N.solar,N.home,toHouse,C.solar);solarLeft-=toHouse;
  if(s.hasBatt){const sb=Math.min(solarLeft,s.bIn);add(N.solar,N.batt,sb,C.solar);solarLeft-=sb;if(s.bIn-sb>20)add(N.grid,N.batt,s.bIn-sb,C.grid)}
  add(N.solar,N.grid,Math.min(solarLeft,s.gridOut),C.solar);
  add(N.grid,N.home,s.gridIn-(s.hasBatt?Math.max(0,s.bIn-Math.min(s.solar,s.bIn)):0),C.grid);
  if(s.hasBatt)add(N.batt,N.home,s.bOut,C.batt);
  const all=[[N.solar,N.home],[N.solar,N.grid],[N.grid,N.home]].concat(s.hasBatt?[[N.solar,N.batt],[N.batt,N.home]]:[]);
  return {grid:{left:0,right:0,top:10,bottom:10},xAxis:{min:0,max:100,show:false},yAxis:{min:0,max:100,show:false},tooltip:{show:false},
   series:[
    {type:"lines",coordinateSystem:"cartesian2d",silent:true,z:1,lineStyle:{color:"#24304D",width:2,curveness:.25},data:all.map(c=>({coords:c}))},
    {type:"lines",coordinateSystem:"cartesian2d",silent:true,z:2,effect:{show:true,constantSpeed:28,symbol:"circle",symbolSize:5,trailLength:.5},
     data:L.map(l=>({coords:l.coords,lineStyle:{color:l.c,width:Math.max(2,Math.min(6,l.w/700)),curveness:.25,opacity:.9},effect:{color:l.c,symbolSize:Math.max(4,Math.min(9,l.w/450)),constantSpeed:18+Math.min(60,l.w/120)}}))},
    {type:"effectScatter",coordinateSystem:"cartesian2d",z:3,rippleEffect:{scale:2.2,brushType:"stroke",period:4},
     data:nodes.map(([n,p,c,v])=>({value:p,name:n,v,itemStyle:{color:"#0D1220",borderColor:c,borderWidth:2.5,shadowBlur:24,shadowColor:hexA(c,.55)},symbolSize:n==="House"?64:54})),
     label:{show:true,position:"bottom",distance:10,formatter:p=>`{n|${p.name}}\n{v|${p.data.v}}`,rich:{n:{color:C.ink,fontFamily:"Sora",fontWeight:600,fontSize:13,lineHeight:18},v:{color:C.ink2,fontFamily:"IBM Plex Mono",fontSize:11}}}}]};
}
function liveSnap(){const l=ST.live.live;return {solar:l.solar,load:l.load,gridIn:l.grid_import,gridOut:l.grid_export,bIn:l.batt_charge,bOut:l.batt_discharge,soc:l.soc,hasBatt:l.has_battery}}
function peakSnap(){const T=ST.views.overview.today;if(!T.length)return liveSnap();const p=T.reduce((a,b)=>b[1]>a[1]?b:a);const l=ST.live.live;
  return {solar:p[1]*1000,load:p[2]*1000,gridIn:p[3]*1000,gridOut:p[4]*1000,bIn:Math.max(0,(p[1]-p[2]-p[4]+p[3])*1000),bOut:0,soc:l.soc,hasBatt:l.has_battery,hour:p[0]}}

function headline(){
  const l=ST.live.live,F=ST.views.weather?.forecast||[];const h=new Date().getHours();
  let a;
  if(l.solar>300&&l.grid_export>100)a=`The sun is running the house and selling ${fmt(l.grid_export)} W back to the grid.`;
  else if(l.solar>300&&l.grid_import<100)a=`The sun is running the house right now.`;
  else if(l.solar>300)a=`Solar is making ${fmt(l.solar)} W, and the grid is topping up the rest.`;
  else if(l.batt_discharge>300)a=`The battery is carrying the house${l.soc!=null?` at ${Math.round(l.soc)}%`:""}.`;
  else if(l.has_battery&&l.soc>=97)a=`The battery is full and the grid is carrying the house${h>=17||h<5?" tonight":""}.`;
  else a=`The grid is carrying the house right now.`;
  let b="";
  if(F.length>1){const best=F.slice(1).reduce((x,y)=>y[1]>x[1]?y:x);const d=F.indexOf(best);const name=d===1?"Tomorrow":new Date(best[0]+"T12:00:00").toLocaleDateString("en-ZA",{weekday:"long"});
    b=`<em>${name} is the sunniest day this week.</em>`}
  return a+" "+b;
}

function renderLive(){
  const l=ST.live.live,ov=ST.views.overview;
  $("#ov-head").innerHTML=headline();
  if(snap==="now")mk("flow",flowOpt(liveSnap()));
  $("#snap-now").textContent="Now "+new Date().toLocaleTimeString("en-ZA",{hour:"2-digit",minute:"2-digit"});
  if(l.has_battery){
    mk("soc",{series:[{type:"gauge",startAngle:220,endAngle:-40,min:0,max:100,radius:"92%",progress:{show:true,width:12,roundCap:true,itemStyle:{color:new echarts.graphic.LinearGradient(0,1,1,0,[{offset:0,color:"#1A8F86"},{offset:1,color:C.batt}]),shadowBlur:14,shadowColor:hexA(C.batt,.5)}},
      axisLine:{roundCap:true,lineStyle:{width:12,color:[[1,"#1A2440"]]}},axisTick:{show:false},splitLine:{show:false},axisLabel:{show:false},pointer:{show:false},anchor:{show:false},
      title:{show:true,offsetCenter:[0,"34%"],color:C.ink3,fontSize:11,fontFamily:"IBM Plex Mono"},detail:{valueAnimation:true,offsetCenter:[0,"-4%"],formatter:"{value}%",color:C.ink,fontFamily:"Sora",fontSize:26,fontWeight:600},
      data:[{value:Math.round(l.soc||0),name:l.batt_charge>20?"CHARGING":l.batt_discharge>20?"IN USE":"STANDBY"}]}]});
    const stored=(l.soc||0)/100*l.battery_kwh;
    $("#batt-kwh").innerHTML=`${fmt(stored,1)}<small>of ${fmt(l.battery_kwh,1)} kWh</small>`;
    const hrs=l.load>0?Math.max(0,stored-.1*l.battery_kwh)/(l.load/1000):0;
    $("#batt-d").textContent=`${l.batt_temp!=null?fmt(l.batt_temp)+" °C · ":""}Enough to run the house for about ${fmt(hrs,1)} hours at the current load.`;
  }else $("#soc-wrap").hidden=true;
  renderControls();renderHouse();
}

const builders={};
builders.overview=function(){
  const ov=ST.views.overview,k=ov.kpi,wx=ST.views.weather,l=ST.live?.live;
  $("#ov-date").textContent=new Date().toLocaleDateString("en-ZA",{weekday:"long",day:"numeric",month:"long"});
  const fct=l?.forecast_today;
  const deltaUse=k.typical_so_far?Math.round((k.use/k.typical_so_far-1)*100):null;
  $("#kpis").innerHTML=[
    ["Solar today",fmt(k.solar,1),"kWh",fct?`<span class="delta ${k.solar>=fct?"up":"down"}">${k.solar>=fct?"+":""}${fmt((k.solar/fct-1)*100)}%</span> vs forecast ${fmt(fct,1)}`:""],
    ["Used today",fmt(k.use,1),"kWh",deltaUse!=null?`<span class="delta ${deltaUse<=0?"up":"down"}">${deltaUse>0?"+":""}${deltaUse}%</span> vs a normal day so far`:""],
    ["Grid cost today",R(k.net_cost),"net",`${R(k.cost_in)} bought · ${R(k.credit_out)} sold`],
    ["Self-powered",k.self_pct??"–","%",`30-day average is ${k.self30}%`]
  ].map(([t,v,u,d])=>`<div class="kpi"><div class="eyebrow">${t}</div><div class="v num">${v}<small>${u}</small></div><div class="d">${d}</div></div>`).join("");

  const T=ov.today,H=[...Array(24).keys()],P=ov.profile;
  const get=i=>H.map(h=>{const r=T.find(x=>x[0]===h);return r?r[i]:null});
  const lastH=T.length?T[T.length-1][0]:-1;
  const pred=H.map(h=>h>lastH?P[h][1]:(h===lastH?get(2)[h]:null));
  const pk=T.length?T.reduce((a,b)=>b[1]>a[1]?b:a):null;
  mk("c-today",{grid:{left:44,right:12,top:24,bottom:28},tooltip:{trigger:"axis",valueFormatter:v=>v==null?"–":fmt(v,2)+" kWh"},
    xAxis:ax({type:"category",data:H.map(hh),boundaryGap:false,axisLabel:monoLabel({interval:2})}),yAxis:ax({type:"value",name:"kWh",nameTextStyle:{color:C.ink3,fontSize:10}}),
    series:[
      {name:"Solar",type:"line",smooth:.35,symbol:"none",data:get(1),lineStyle:{width:2.5,color:C.solar,shadowBlur:12,shadowColor:hexA(C.solar,.5)},areaStyle:{color:grad(C.solar,.5)},
       markPoint:pk&&pk[1]>.2?{symbol:"circle",symbolSize:9,itemStyle:{color:C.solar,borderColor:"#0D1220",borderWidth:2},label:{show:true,position:"top",color:C.ink,fontSize:11,formatter:`Peak ${fmt(pk[1],1)} kWh`},data:[{coord:[hh(pk[0]),pk[1]]}]}:undefined},
      {name:"House use",type:"line",smooth:.35,symbol:"none",data:get(2),lineStyle:{width:2,color:C.home},areaStyle:{color:grad(C.home,.18)}},
      {name:"House use (predicted)",type:"line",smooth:.35,symbol:"none",data:pred,lineStyle:{width:2,color:C.home,type:[4,4]}},
      {name:"Sold",type:"bar",barWidth:5,data:get(4),itemStyle:{color:C.exp,borderRadius:[3,3,0,0]}},
      {name:"Bought",type:"bar",barWidth:5,data:get(3),itemStyle:{color:C.grid,borderRadius:[3,3,0,0]}}]});

  const open=openAlerts();
  $("#al-mini-sub").textContent=open.length?`${open.length} open alert${open.length>1?"s":""}`:"All clear";
  $("#al-mini").innerHTML=open.length?open.slice(0,3).map(a=>`<a class="al ${a.severity}" href="#alerts" style="text-decoration:none;color:inherit"><div class="sev">${IC[a.severity]}</div><div><b>${esc(a.title)}</b></div><div class="meta"><span class="pill ${a.severity}">${SEV[a.severity]}</span></div></a>`).join(""):`<div class="empty">Nothing needs a look right now.</div>`;

  const F=wx.forecast,mx=Math.max(1,...F.map(f=>Math.max(f[1],f[2])));
  const bestIdx=F.length?F.indexOf(F.reduce((x,y)=>y[1]>x[1]?y:x)):-1;
  $("#days").innerHTML=F.map((f,i)=>{const d=new Date(f[0]+"T12:00:00");const name=i===0?"Today":i===1?"Tomorrow":d.toLocaleDateString("en-ZA",{weekday:"short"});
    const ok=i===bestIdx;return `<div class="day ${i===1?"today":""}"><div class="dn">${name}${wxIcon(f[7])}</div><div class="t">${wxName(f[7])} · ${fmt(f[6])}–${fmt(f[5])}°</div>
    <div class="bars"><div>Solar<i style="width:${f[1]/mx*100}%;background:${C.solar}"></i><em>${fmt(f[1])}</em></div><div>Use<i style="width:${f[2]/mx*100}%;background:${C.home}"></i><em>${fmt(f[2])}</em></div></div>
    <div class="verdict" style="color:${ok?C.good:C.ink3}">${ok?"Best day for washing":f[8]>70?"Storm risk "+fmt(f[8])+"%":"Average solar"}</div></div>`}).join("");

  document.querySelectorAll("[data-snap]").forEach(b=>b.onclick=()=>{snap=b.dataset.snap;document.querySelectorAll("[data-snap]").forEach(x=>x.setAttribute("aria-pressed",x===b));mk("flow",flowOpt(snap==="now"?liveSnap():peakSnap()))});
  const ps=peakSnap();$("#snap-peak").textContent=ps.hour!=null?`Today ${hh(ps.hour)}`:"Today's peak";
  if(ST.live)renderLive();
};

function renderControls(){
  const ctl=ST.live.controls;const groups={};ctl.forEach(c=>(groups[c.group]=groups[c.group]||[]).push(c));
  const html=Object.entries(groups).map(([g,items])=>`<div class="eyebrow" style="margin:6px 0 8px">${esc(g)}</div><div class="rooms" style="margin-bottom:12px">`+items.map(c=>{const off=c.state==="unavailable";const on=c.state==="on";
    return `<button class="tog" type="button" id="t-${esc(c.entity_id)}" data-e="${esc(c.entity_id)}" aria-pressed="${on}" ${off?"disabled":""}><span class="sw"></span><span><b>${esc(c.name)}</b><span>${off?"Offline":on?"On":"Off"}${c.area?" · "+esc(c.area):""}</span></span></button>`}).join("")+`</div>`).join("");
  const host=$("#rooms");if(host.dataset.sig!==html){host.innerHTML=html;host.dataset.sig=html;
    host.querySelectorAll(".tog:not(:disabled)").forEach(b=>b.onclick=async()=>{b.classList.add("busy");
      try{await api("api/control",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({entity_id:b.dataset.e})});
        b.setAttribute("aria-pressed",b.getAttribute("aria-pressed")!=="true");setTimeout(pollLive,800)}
      catch(e){toast("Couldn't switch that. Check Home Assistant is reachable.")}finally{b.classList.remove("busy")}})}
}
function renderHouse(){
  $("#house").innerHTML=ST.live.house.map(h=>`<div class="al ${h.kind==="warn"?"warn":"info"}"><div class="sev" style="${h.kind==="good"?"background:rgba(91,227,143,.12);color:var(--good)":""}">${h.kind==="good"?IC.check:IC[h.kind==="warn"?"warn":"info"]}</div><div><b>${esc(h.title)}</b><span>${esc(h.detail)}</span></div><div></div></div>`).join("")||`<div class="empty">Nothing to show.</div>`;
}

/* ================= ENERGY ================= */
builders.energy=function(){
  const E=ST.views.energy,t=E.totals30,y=E.yield,best=E.yield_best;
  const last=y.length?y[y.length-1][1]:null,drop=best&&last?Math.round((1-last/best)*100):0;
  $("#en-head").innerHTML=drop>=40?`Your panels make <em>${drop}% less power</em> from the same sunshine than in your best month.`:`Solar covered <em>${t.self_pct}%</em> of the house over the last 30 days.`;
  $("#e-stats").innerHTML=[["Solar made · 30 days",fmt(t.solar),"kWh",`${fmt(t.solar/30,1)} kWh a day`],["Self-powered",fmt(t.self_pct),"%","of everything the house used"],
    ["Saved by solar",R(t.saved),"",`${R(t.saved_self)} not bought · ${R(t.credit)} sold`],["Lifetime solar",fmt(E.lifetime_solar),"kWh",E.lifetime_solar?`≈ ${R(E.lifetime_solar*E.prices.import)} at today's tariff`:""]]
    .map(([k,v,u,d])=>`<div class="card stat"><div class="eyebrow">${k}</div><div class="v num">${v}<small>${u}</small></div><div class="d">${d}</div></div>`).join("");

  const s=E.sankey,nodes=[{name:"Solar",itemStyle:{color:C.solar}},{name:"Grid",itemStyle:{color:C.grid}},{name:"House",itemStyle:{color:C.home}},{name:"Sold back",itemStyle:{color:C.exp}}];
  const links=[{source:"Solar",target:"House",value:s.solar_house},{source:"Solar",target:"Sold back",value:s.solar_grid},{source:"Grid",target:"House",value:s.grid_house}];
  if(s.solar_batt||s.batt_house){nodes.push({name:"Battery",itemStyle:{color:C.batt}});links.push({source:"Solar",target:"Battery",value:s.solar_batt},{source:"Battery",target:"House",value:s.batt_house})}
  mk("c-sankey",{tooltip:{trigger:"item",formatter:p=>p.dataType==="edge"?`${p.data.source} → ${p.data.target}<br><b>${fmt(p.data.value)} kWh</b>`:`${p.name}: <b>${fmt(p.value)} kWh</b>`},
    series:[{type:"sankey",left:8,right:110,top:10,bottom:10,nodeWidth:12,nodeGap:18,draggable:false,emphasis:{focus:"adjacency"},
      label:{color:C.ink,formatter:p=>`{a|${p.name}}\n{b|${fmt(p.value)} kWh}`,rich:{a:{color:C.ink,fontWeight:600,lineHeight:16},b:{color:C.ink2,fontFamily:"IBM Plex Mono",fontSize:11}}},
      lineStyle:{color:"gradient",opacity:.35,curveness:.5},data:nodes,links:links.filter(l=>l.value>0)}]});

  const pill=$("#yield-pill");pill.className="pill "+(drop>=40?"crit":drop>=28?"warn":"good");pill.textContent=drop>=40?"Investigate":drop>=28?"Watch":"Normal";
  mk("c-yield",{grid:{left:40,right:12,top:30,bottom:28},tooltip:{trigger:"axis",formatter:p=>`${p[0].name}<br><b>${p[0].value} kWh per MJ/m²</b>`},
    xAxis:ax({type:"category",data:y.map(v=>monthName(v[0]))}),yAxis:ax({type:"value",min:0}),
    series:[{type:"bar",barWidth:"46%",data:y.map(v=>{const bad=best&&v[1]<0.72*best;return {value:v[1],itemStyle:{borderRadius:[6,6,0,0],color:new echarts.graphic.LinearGradient(0,0,0,1,[{offset:0,color:bad?C.crit:C.solar},{offset:1,color:hexA(bad?C.crit:C.solar,.25)}])}}}),
      label:{show:true,position:"top",color:C.ink2,fontFamily:"IBM Plex Mono",fontSize:11},
      markArea:best?{silent:true,itemStyle:{color:"rgba(91,227,143,.07)"},label:{color:C.good,fontSize:10,position:"insideTopRight"},data:[[{yAxis:best*0.72,name:"Normal seasonal range"},{yAxis:best}]]}:undefined}]});

  /* strings */
  const S=E.strings,slots=[...Array(96).keys()].map(i=>mm(i*15));
  $("#str-legend").innerHTML=S.map((x,i)=>`<span><i style="background:${STRING_COLORS[i%4]}"></i>${x.name}</span>`).join("");
  const thr=S[0]?.threshold||500;
  $("#str-sub").textContent=`Average output of each string over the last 10 days, in 15-minute steps. The band marks useful power (over ${fmt(thr)} W per string).`;
  const firstOn=S.map(x=>x.curve.findIndex(v=>v>=thr)),lastOn=S.map(x=>{let i=-1;x.curve.forEach((v,j)=>{if(v>=thr)i=j});return i});
  const bandA=Math.min(...firstOn.filter(i=>i>=0)),bandB=Math.max(...lastOn);
  mk("c-strings",{grid:{left:48,right:16,top:22,bottom:30},tooltip:{trigger:"axis",valueFormatter:v=>fmt(v)+" W"},
    xAxis:ax({type:"category",data:slots,boundaryGap:false,axisLabel:monoLabel({interval:7}),min:20,max:80}),yAxis:ax({type:"value",name:"W",nameTextStyle:{color:C.ink3}}),
    series:S.map((x,i)=>({name:x.name,type:"line",smooth:.4,symbol:"none",data:x.curve,lineStyle:{width:2.5,color:STRING_COLORS[i%4],shadowBlur:i?0:10,shadowColor:hexA(STRING_COLORS[i%4],.5)},areaStyle:{color:grad(STRING_COLORS[i%4],i?.2:.35)},
      ...(i===0&&bandA>=0&&isFinite(bandA)?{markLine:{silent:true,symbol:"none",lineStyle:{color:C.ink3,type:[4,4]},label:{color:C.ink3,fontSize:10,formatter:fmt(thr)+" W"},data:[{yAxis:thr}]},
        markArea:{silent:true,itemStyle:{color:"rgba(255,201,77,.06)"},label:{color:C.solar,fontSize:11,fontFamily:"IBM Plex Mono",position:"insideTop"},data:[[{xAxis:slots[bandA],name:`Useful power ${slots[bandA]}–${slots[bandB]}`},{xAxis:slots[bandB]}]]}}:{})}))});
  const avg=(r,i)=>r.length?Math.round(sum(r.map(x=>x[i]))/r.length/5)*5:null;
  const ins=[];
  if(S.length){
    const st=S.map(x=>({n:x.name,on:avg(x.ramps,1),off:avg(x.ramps,2),pk:avg(x.ramps,3),pw:x.ramps.length?Math.round(sum(x.ramps.map(r=>r[4]))/x.ramps.length):0}));
    const early=st.filter(x=>x.on!=null).sort((a,b)=>a.on-b.on);
    if(early.length)ins.push(["Useful power starts",mm(early[0].on),st.map(x=>x.on!=null?`${x.n} passes ${fmt(thr)} W at ${mm(x.on)}`:"").filter(Boolean).join(", ")+". "+(early.length>1&&early[early.length-1].on-early[0].on>45?`${early[0].n} starts much earlier, so it probably faces east, or ${early[early.length-1].n} is shaded in the morning.`:"")]);
    const late=st.filter(x=>x.off!=null).sort((a,b)=>b.off-a.off);
    if(late.length)ins.push(["Useful power ends",mm(late[0].off),st.map(x=>x.off!=null?`${x.n} drops below ${fmt(thr)} W at ${mm(x.off)}`:"").filter(Boolean).join(", ")+"."]);
    if(st[0].pk!=null)ins.push(["Peak",mm(st[0].pk),`Peaks around ${mm(st[0].pk)} at about ${fmt(st[0].pw)} W per string. Run big loads in the two hours either side.`]);
    const win=late.length&&early.length?(late[0].off-early[0].on)/60:0;
    if(win)ins.push(["Productive window",fmt(win,1)+" h",`About ${fmt(win,1)} hours a day of useful solar across all strings.`]);
  }
  const drop2=(ST.alerts?.alerts||[]).find(a=>a.key.startsWith("string_dropout")&&!a.resolved_at);
  if(drop2)ins.push(["Drop-out",drop2.title.split(" on ")[1]||"",drop2.detail]);
  $("#ramp-ins").innerHTML=ins.map(([t,b,p])=>`<div class="insight"><span class="eyebrow">${t}</span><span class="big num">${b}</span><p>${esc(p)}</p></div>`).join("");

  const months=Object.keys(S[0]?.monthly||{}),hrs=[...Array(15).keys()].map(i=>i+5),hm=[];
  months.forEach((m,mi)=>hrs.forEach((h,hi)=>hm.push([hi,mi,sum(S.map(x=>(x.monthly[m]||[])[h]||0))])));
  const hmax=Math.max(500,...hm.map(v=>v[2]));
  mk("c-window",{grid:{left:44,right:16,top:10,bottom:56},tooltip:{formatter:p=>`${monthName(months[p.value[1]])} · ${hh(hrs[p.value[0]])}<br><b>${fmt(p.value[2])} W</b> average`},
    xAxis:ax({type:"category",data:hrs.map(hh)}),yAxis:ax({type:"category",data:months.map(monthName),splitLine:{show:false}}),
    visualMap:{min:0,max:hmax,orient:"horizontal",left:"center",bottom:0,itemHeight:180,itemWidth:10,text:[fmt(hmax/1000,1)+" kW",""],textStyle:{color:C.ink3,fontSize:10},inRange:{color:["#0F1628","#3B2A3F","#9A5A2E","#FFC94D","#FFF1C2"]}},
    series:[{type:"heatmap",data:hm,itemStyle:{borderColor:"#111829",borderWidth:2,borderRadius:4}}]});

  const days=[...new Set(S.flatMap(x=>x.ramps.map(r=>r[0])))].sort();
  const pick=(r,d,i)=>{const x=r.find(z=>z[0]===d);return x?x[i]:null};
  const allT=S.flatMap(x=>x.ramps.flatMap(r=>[r[1],r[2]]));const lo=Math.floor((Math.min(...allT,480)-30)/60)*60,hi=Math.ceil((Math.max(...allT,1020)+30)/60)*60;
  $("#ramp-sub").textContent=`When each string first and last passes ${fmt(thr)} W`;
  mk("c-ramps",{grid:{left:52,right:16,top:16,bottom:30},tooltip:{trigger:"axis",formatter:p=>p[0].axisValue+"<br>"+p.map(x=>`${x.marker}${x.seriesName}: ${mm(x.value[1])}–${mm(x.value[2])}`).join("<br>")},
    xAxis:ax({type:"category",data:days.map(d=>new Date(d+"T12:00:00").toLocaleDateString("en-ZA",{day:"numeric",month:"short"}))}),
    yAxis:ax({type:"value",min:lo,max:hi,interval:120,inverse:true,axisLabel:monoLabel({formatter:v=>mm(v)})}),
    series:S.map((x,si)=>({name:x.name,type:"custom",encode:{x:0,y:[1,2]},data:days.map((d,i)=>[i,pick(x.ramps,d,1),pick(x.ramps,d,2)]).filter(v=>v[1]!=null),
      renderItem:(p,api)=>{const a=api.coord([api.value(0),api.value(1)]),b=api.coord([api.value(0),api.value(2)]),w=Math.max(3,Math.min(8,api.size([1,0])[0]/(S.length*2.5)));
        return {type:"rect",shape:{x:a[0]+(si-S.length/2)*(w+3),y:a[1],width:w,height:b[1]-a[1],r:4},style:{fill:STRING_COLORS[si%4]}}}}))});

  mk("c-cal",{tooltip:{formatter:p=>`${p.value[0]}<br><b>${p.value[1]}% self-powered</b>`},
    visualMap:{min:0,max:Math.max(40,...E.calendar.map(c=>c[1])),show:true,orient:"horizontal",right:10,top:0,itemHeight:120,itemWidth:9,text:["more","less"],textStyle:{color:C.ink3,fontSize:10},inRange:{color:["#141C30","#1E4A4A","#2A8F7F",C.batt,"#B9FFF4"]}},
    calendar:{top:34,left:34,right:10,bottom:6,range:[E.calendar[0]?.[0]||new Date().toISOString().slice(0,10),E.calendar[E.calendar.length-1]?.[0]||new Date().toISOString().slice(0,10)],cellSize:["auto",15],splitLine:{show:false},
      itemStyle:{color:"#0D1220",borderColor:"#111829",borderWidth:3},yearLabel:{show:false},dayLabel:{color:C.ink3,fontSize:10,firstDay:1,nameMap:["S","M","T","W","T","F","S"]},monthLabel:monoLabel()},
    series:[{type:"heatmap",coordinateSystem:"calendar",data:E.calendar,itemStyle:{borderRadius:3}}]});

  const P=E.profile,H=[...Array(24).keys()];
  mk("c-profile",{grid:{left:44,right:12,top:16,bottom:28},tooltip:{trigger:"axis",valueFormatter:v=>fmt(v,2)+" kWh"},
    xAxis:ax({type:"category",data:H.map(hh),boundaryGap:false,axisLabel:monoLabel({interval:2})}),yAxis:ax({type:"value"}),
    series:[["Solar",0,C.solar,.4],["House use",1,C.home,.15],["Bought",2,C.grid,.12],["Sold",3,C.exp,.12]].map(([n,i,c,a])=>({name:n,type:"line",smooth:.4,symbol:"none",data:P.map(p=>p[i]),lineStyle:{width:2,color:c},areaStyle:{color:grad(c,a)}}))});
};

/* ================= APPLIANCES ================= */
builders.appliances=function(){
  const A=ST.views.appliances,apps=A.apps.slice().sort((a,b)=>"cwngo".indexOf(a.status[0])-"cwngo".indexOf(b.status[0])||a.name.localeCompare(b.name));
  const warn=apps.filter(a=>a.status==="warn"||a.status==="crit"),off=apps.filter(a=>a.status==="off");
  $("#ap-eyebrow").textContent=`Appliance health · ${apps.length} monitored`;
  $("#ap-head").innerHTML=warn.length?`${warn.map(a=>a.name).slice(0,3).join(", ").replace(/, ([^,]*)$/," and $1")} ${warn.length>1?"need":"needs"} a look. <em>${apps.length-warn.length-off.length} others look healthy.</em>`:`<em>Everything looks healthy.</em>`;
  const label={good:"Healthy",warn:"Check soon",crit:"Service now",off:"Offline",new:"Learning"};
  const pillCls={good:"good",warn:"warn",crit:"crit",off:"info",new:"info"};
  $("#apps").innerHTML=apps.map((a,i)=>`<button class="app-c" type="button" data-i="${i}" aria-pressed="${i===0}"><div class="ring" id="ring${i}"></div><div><b>${esc(a.name)}</b><div class="s">${esc(a.note)}</div><div class="row"><span class="pill ${pillCls[a.status]}">${label[a.status]}</span><span class="mono" style="font-size:.72rem;color:var(--ink-3)">${fmt(a.kwh56)} kWh · 8 wks${a.now_w!=null?" · now "+fmt(a.now_w)+" W":""}</span></div></div></button>`).join("");
  apps.forEach((a,i)=>{const c={warn:C.warn,crit:C.crit,good:C.good}[a.status]||C.ink3;mk("ring"+i,{series:[{type:"gauge",startAngle:90,endAngle:-270,min:0,max:100,radius:"100%",pointer:{show:false},progress:{show:true,roundCap:true,width:6,itemStyle:{color:c}},axisLine:{lineStyle:{width:6,color:[[1,"#1A2440"]]}},splitLine:{show:false},axisTick:{show:false},axisLabel:{show:false},detail:{offsetCenter:[0,0],fontSize:a.score==null?12:15,fontFamily:"Sora",fontWeight:600,color:C.ink,formatter:a.score==null?"–":"{value}"},data:[{value:a.score??0}]}]})});
  document.querySelectorAll(".app-c").forEach(b=>b.onclick=()=>{document.querySelectorAll(".app-c").forEach(x=>x.setAttribute("aria-pressed",x===b));detail(apps[+b.dataset.i])});
  function detail(a){
    const c={warn:C.warn,crit:C.crit,good:C.good}[a.status]||C.info;
    $("#ad-title").textContent=`${a.name} · ${a.continuous?"average power":"running power"}`;
    $("#ad-pill").className="pill "+pillCls[a.status];$("#ad-pill").textContent=label[a.status];
    $("#ad-sub").textContent=a.baseline?`Monthly figure against its normal range (shaded). ${a.status==="warn"?"It has moved out of its normal range.":"It is staying inside it."}`:"Not enough history yet to set a normal range.";
    const sp=a.spark||[];
    mk("c-appdetail",{grid:{left:56,right:20,top:24,bottom:28},tooltip:{trigger:"axis",formatter:p=>`${p[0].name}<br>${p.map(x=>`${x.marker}${x.seriesName}: <b>${fmt(x.value,1)}</b> ${x.seriesName==="Energy"?"kWh":"W"}`).join("<br>")}`},
      xAxis:ax({type:"category",data:sp.map(s=>monthName(s[0])),boundaryGap:false}),yAxis:ax({type:"value",scale:true,name:"W",nameTextStyle:{color:C.ink3}}),
      series:[{name:a.continuous?"Average power":"Running power",type:"line",smooth:.35,data:sp.map(s=>s[1]),symbol:"circle",symbolSize:8,itemStyle:{color:c,borderColor:"#0D1220",borderWidth:2},lineStyle:{width:3,color:c,shadowBlur:14,shadowColor:hexA(c,.5)},areaStyle:{color:grad(c,.25)},
        markArea:a.baseline?{silent:true,itemStyle:{color:"rgba(138,160,200,.08)"},label:{show:true,position:"insideTopLeft",color:C.ink3,fontSize:10,formatter:"Normal range"},data:[[{yAxis:a.baseline-a.spread*1.5},{yAxis:a.baseline+a.spread*1.5}]]}:undefined}]});
  }
  if(apps.length)detail(apps[0]);
  const pal=[C.grid,C.exp,C.home,C.batt,C.solar,"#8FB8FF","#C7A6FF","#FFA3CC","#7EE6DA","#FFD98A"];
  const tree=apps.filter(a=>a.kwh56>0.5).map(a=>({name:a.name,value:Math.round(a.kwh56*A.price)})).sort((a,b)=>b.value-a.value).map((t,i)=>({...t,itemStyle:{color:pal[i%pal.length]}}));
  const rest=Math.max(0,A.use56-A.monitored56);
  if(rest>0)tree.push({name:"Not on a smart plug",value:Math.round(rest*A.price),itemStyle:{color:"#2A3757"},label:{rich:{n:{color:C.ink2},v:{color:C.ink3}}}});
  $("#tree-sub").textContent=`Last 8 weeks at R${fmt(A.price,2)}/kWh. ${Math.round(A.monitored56/Math.max(1,A.use56)*100)}% of use is on a smart plug.`;
  mk("c-tree",{tooltip:{formatter:p=>`${p.name}<br><b>${R(p.value)}</b> in 8 weeks`},
    series:[{type:"treemap",roam:false,nodeClick:false,breadcrumb:{show:false},left:0,right:0,top:0,bottom:0,
      label:{show:true,formatter:p=>`{n|${p.name}}\n{v|${R(p.value)}}`,rich:{n:{color:"#0B1020",fontWeight:600,fontSize:12,lineHeight:16},v:{color:"rgba(11,16,32,.75)",fontFamily:"IBM Plex Mono",fontSize:11}}},
      itemStyle:{borderColor:"#111829",borderWidth:3,gapWidth:3,borderRadius:8},data:tree}]});
};

/* ================= HABITS ================= */
builders.habits=function(){
  const H=ST.views.habits,price=ST.views.appliances?.price||ST.views.plan?.prices?.import||3.4864;
  const base=H.base_kw;
  $("#hb-head").innerHTML=`The house never drops below <em>${fmt(base*1000)} W</em>, even at 3am. That costs about ${R(base*24*30*price)} a month.`;
  const wd=["Mon","Tue","Wed","Thu","Fri","Sat","Sun"],hm=[];
  H.heat.forEach((row,d)=>row.forEach((v,h)=>hm.push([h,d,v])));
  const vmax=Math.max(1,...hm.map(v=>v[2]));
  mk("c-heat",{grid:{left:44,right:12,top:10,bottom:60},tooltip:{formatter:p=>`${wd[p.value[1]]} ${hh(p.value[0])}<br><b>${fmt(p.value[2],2)} kWh</b> average`},
    xAxis:ax({type:"category",data:[...Array(24).keys()].map(hh),axisLabel:monoLabel({interval:2})}),yAxis:ax({type:"category",data:wd,inverse:true,splitLine:{show:false}}),
    visualMap:{min:Math.min(...hm.map(v=>v[2])),max:vmax,orient:"horizontal",left:"center",bottom:0,itemHeight:200,itemWidth:10,text:[fmt(vmax,1)+" kWh",""],textStyle:{color:C.ink3,fontSize:10},inRange:{color:["#121A2E","#23366B","#4E63C9",C.home,"#D7E6FF"]}},
    series:[{type:"heatmap",data:hm,itemStyle:{borderColor:"#111829",borderWidth:2,borderRadius:4}}]});
  const top=H.clock.filter(c=>!c.always_on).slice(0,5),cols=[C.grid,C.batt,C.exp,C.home,"#C7A6FF"];
  mk("c-polar",{tooltip:{trigger:"item",formatter:p=>p.seriesType==="bar"?`${p.seriesName} · ${hh(p.dataIndex)}<br><b>${fmt(p.value,2)} kWh</b> a day on average`:""},
    legend:{bottom:0,textStyle:{color:C.ink2,fontSize:11},icon:"roundRect",itemWidth:10,itemHeight:10,data:top.map(t=>t.name)},
    angleAxis:{type:"category",data:[...Array(24).keys()].map(h=>h%6===0?hh(h):""),startAngle:90,clockwise:true,axisLine:{lineStyle:{color:C.line}},axisTick:{show:false},axisLabel:monoLabel({fontSize:10}),splitLine:{show:true,lineStyle:{color:"rgba(31,42,68,.6)"}}},
    radiusAxis:{axisLine:{show:false},axisTick:{show:false},axisLabel:{show:false},splitLine:{lineStyle:{color:"rgba(31,42,68,.5)",type:[3,4]}}},
    polar:{radius:["14%","74%"],center:["50%","46%"]},
    series:[...top.map((t,i)=>({name:t.name,type:"bar",coordinateSystem:"polar",stack:"a",data:t.byh,itemStyle:{color:cols[i],borderRadius:2},emphasis:{focus:"series"}})),
      {type:"pie",radius:["78%","81%"],center:["50%","46%"],silent:true,label:{show:false},startAngle:90-9*15,clockwise:true,data:[{value:6,itemStyle:{color:C.solar}},{value:18,itemStyle:{color:"transparent"}}]}]});
  const ins=[["Always-on load",fmt(base*1000)+" W",`Even at 3am the house draws ${fmt(base*1000)} W. That's ${fmt(base*24*30)} kWh, about ${R(base*24*30*price)} a month.`+(H.clock.filter(c=>c.always_on).length?` Fridges account for about ${fmt(sum(H.clock.filter(c=>c.always_on).map(c=>c.kwh56))/56/24*1000)} W of it.`:"")]];
  H.clock.filter(c=>!c.always_on).slice(0,5).forEach(c=>{
    const when=c.peaks.map(hh).join(" & ");
    ins.push([c.name,c.solar_share+"% on solar",c.solar_share>=60?`Already runs mostly in the solar window. Busiest around ${when}.`:`Only ${c.solar_share}% runs between 09:00 and 15:00. Busiest around ${when}, when power comes from the grid. About ${fmt(c.kwh56/8,1)} kWh a week.`])});
  ins.push(["Weekends",(H.weekend_pct>0?"+":"")+H.weekend_pct+"%",`Weekend days use ${Math.abs(H.weekend_pct)}% ${H.weekend_pct>=0?"more":"less"} than weekdays.`]);
  $("#habit-ins").innerHTML=ins.map(([t,b,p])=>`<div class="insight"><span class="eyebrow">${esc(t)}</span><span class="big num">${b}</span><p>${esc(p)}</p></div>`).join("");
};

/* ================= WEATHER ================= */
builders.weather=function(){
  const W=ST.views.weather,F=W.forecast,f=W.fits;
  const lab=F.map((x,i)=>i===0?"Today":new Date(x[0]+"T12:00:00").toLocaleDateString("en-ZA",{weekday:"short",day:"numeric"}));
  const sol=F.map(x=>x[1]),avgSol=sum(sol)/Math.max(1,sol.length),storms=F.filter(x=>x[7]>=95).length;
  $("#wx-head").innerHTML=`Each degree warmer ${f.slope>=0?"adds":"saves"} <em>${fmt(Math.abs(f.slope),2)} kWh</em> a day. ${storms?`${storms} stormy day${storms>1?"s":""} this week will`:"This week should"} hold solar around ${fmt(avgSol)} kWh a day.`;
  mk("c-fc",{grid:{left:44,right:12,top:24,bottom:24},tooltip:{trigger:"axis",valueFormatter:v=>fmt(v,1)+" kWh"},
    xAxis:ax({type:"category",data:lab}),yAxis:ax({type:"value",name:"kWh",nameTextStyle:{color:C.ink3}}),
    series:[
      {name:"Solar",type:"bar",barWidth:16,data:F.map(x=>x[1]),itemStyle:{borderRadius:[6,6,0,0],color:new echarts.graphic.LinearGradient(0,0,0,1,[{offset:0,color:C.solar},{offset:1,color:hexA(C.solar,.2)}])}},
      {name:"House use",type:"bar",barWidth:16,data:F.map(x=>x[2]),itemStyle:{borderRadius:[6,6,0,0],color:new echarts.graphic.LinearGradient(0,0,0,1,[{offset:0,color:C.home},{offset:1,color:hexA(C.home,.2)}])}},
      {name:"Bought",type:"line",smooth:.3,data:F.map(x=>x[3]),symbol:"circle",symbolSize:8,lineStyle:{color:C.grid,width:2.5},itemStyle:{color:C.grid,borderColor:"#0D1220",borderWidth:2},
        label:{show:true,position:"top",color:C.ink2,fontFamily:"IBM Plex Mono",fontSize:10,formatter:p=>R(p.value*(ST.views.plan?.prices?.import||3.4864))}}]});
  mk("c-fc-t",{grid:{left:44,right:12,top:10,bottom:20},tooltip:{trigger:"axis",formatter:p=>{const x=F[p[0].dataIndex];return `${lab[p[0].dataIndex]}<br>${fmt(x[6])}–${fmt(x[5])} °C · rain ${fmt(x[8])}% · ${wxName(x[7])}`}},
    xAxis:ax({type:"category",data:lab,axisLabel:{show:false}}),yAxis:ax({type:"value",scale:true,axisLabel:monoLabel({formatter:"{value}°",fontSize:10})}),
    series:[{type:"custom",encode:{x:0,y:[1,2]},data:F.map((x,i)=>[i,x[6],x[5]]),renderItem:(p,api)=>{const lo=api.coord([api.value(0),api.value(1)]),hi=api.coord([api.value(0),api.value(2)]);
      return {type:"rect",shape:{x:lo[0]-4,y:hi[1],width:8,height:lo[1]-hi[1],r:4},style:{fill:new echarts.graphic.LinearGradient(0,0,0,1,[{offset:0,color:"#FF8F5E"},{offset:1,color:"#6EA8FE"}])}}}}]});
  const P=f.points,xs=P.map(p=>p[0]),lo=Math.min(...xs),hi=Math.max(...xs);
  mk("c-sc-temp",{grid:{left:44,right:16,top:20,bottom:36},tooltip:{formatter:p=>p.seriesType==="scatter"?`${p.data[2]}<br>${fmt(p.data[0],1)} °C · <b>${fmt(p.data[1],1)} kWh</b>`:""},
    xAxis:ax({type:"value",name:"Average temperature °C",nameLocation:"middle",nameGap:24,nameTextStyle:{color:C.ink3},min:Math.floor(lo),max:Math.ceil(hi)}),yAxis:ax({type:"value",name:"kWh used",nameTextStyle:{color:C.ink3},scale:true}),
    series:[{type:"scatter",symbolSize:7,data:P.map(p=>[p[0],p[1],p[4]]),itemStyle:{color:hexA(C.home,.7),borderColor:"#0D1220",borderWidth:1}},
      {type:"line",symbol:"none",silent:true,data:[[lo,f.slope*lo+f.intercept],[hi,f.slope*hi+f.intercept]],lineStyle:{color:C.solar,width:2,type:[6,4]},endLabel:{show:true,color:C.solar,fontSize:11,formatter:`${f.slope>=0?"+":""}${fmt(f.slope,2)} kWh per °C`}}]});
  const months=[...new Set(P.map(p=>p[4].slice(0,7)))];
  const ramp=["#6EA8FE","#7F9CF5","#9A8FEA","#B892FF","#E08AD0","#FF7EB6","#FF4D6D","#FF8F5E","#FFC94D","#B9E26B","#5BE38F","#34D3C4"];
  const ms=months.slice(-12);
  mk("c-sc-rad",{grid:{left:44,right:16,top:20,bottom:60},legend:{bottom:0,textStyle:{color:C.ink2,fontSize:11},itemWidth:9,itemHeight:9},tooltip:{formatter:p=>`${p.data[2]}<br>${fmt(p.data[0],1)} MJ/m² · <b>${fmt(p.data[1],1)} kWh</b>`},
    xAxis:ax({type:"value",name:"Sunshine MJ/m²",nameLocation:"middle",nameGap:24,nameTextStyle:{color:C.ink3}}),yAxis:ax({type:"value",name:"Solar kWh",nameTextStyle:{color:C.ink3}}),
    series:ms.map((mo,i)=>({name:monthName(mo),type:"scatter",symbolSize:7,data:P.filter(p=>p[4].startsWith(mo)).map(p=>[p[2],p[3],p[4]]),itemStyle:{color:ramp[(i+ramp.length-ms.length)%ramp.length],borderColor:"#0D1220",borderWidth:1}}))});
};

/* ================= PLAN ================= */
builders.plan=function(){
  const P=ST.views.plan;
  if(!P.ready){$("#pl-head").textContent="The plan needs two weeks of hourly history. Check back soon.";return}
  const pi=P.prices.import,pe=P.prices.export,B=P.base,start=B.net;
  $("#pl-head").innerHTML=start>0?`You're <em>${fmt(start)} kWh</em> a month short of net positive. Here's the path.`:`You already send back <em>${fmt(-start)} kWh</em> a month more than you use.`;
  $("#bill-sub").textContent=P.equal_rates?`kWh per month. Buy and sell are both R${fmt(pi,2)}/kWh, so the bill is bought minus sold.`:`kWh per month. Buy R${fmt(pi,2)}, sell R${fmt(pe,2)} per kWh.`;
  const on=new Set(P.actions.filter(a=>a.default).map(a=>a.key));
  $("#acts").innerHTML=P.actions.map(a=>{const big=a.net_delta>5;
    return `<button class="act" type="button" data-k="${a.key}" aria-pressed="${on.has(a.key)}"><span class="ck">${IC.check}</span><span><b>${esc(a.title)}</b><span>${esc(a.desc)} · ${esc(a.cost)}</span></span>
    <span class="imp"><strong>${a.saving>5?"≈ "+R(a.saving)+"/mo":"R0 saved"}</strong>${big?"−"+fmt(a.net_delta)+" kWh net":"−"+fmt(Math.max(0,a.imp_delta))+" kWh from grid"}</span></button>`}).join("");
  function update(){
    const sel=P.actions.filter(a=>on.has(a.key));
    let net=start;const wf=[["Today",start,0]];
    sel.forEach(a=>{if(Math.abs(a.net_delta)>2){wf.push([a.title.split(" ").slice(0,3).join(" "),net,a.net_delta]);net-=a.net_delta}});
    wf.push(["Result",net,0]);
    const imp=Math.max(0,B.imp-sum(sel.map(a=>a.imp_delta))),exp=Math.max(0,imp-net);
    const pct=start>0?Math.max(0,Math.min(100,(start-net)/start*100)):100;
    $("#meter").style.width=pct+"%";$("#meter-v").textContent=fmt(pct)+"%";
    $("#meter-sub").textContent=net<=0?`Net positive: you'd send back ${fmt(-net)} kWh more than you buy each month.`:`${fmt(net)} kWh a month still to close`;
    mk("c-water",{grid:{left:50,right:16,top:24,bottom:50},tooltip:{trigger:"axis",formatter:p=>{const w=wf[p[0].dataIndex];return w[2]?`${w[0]}<br><b>−${fmt(w[2])} kWh</b> a month`:`${w[0]}<br><b>${fmt(w[1])} kWh</b> net bought`}},
      xAxis:ax({type:"category",data:wf.map(w=>w[0]),axisLabel:{color:C.ink3,fontSize:10,interval:0,width:84,overflow:"break",lineHeight:13}}),yAxis:ax({type:"value",name:"kWh/mo",nameTextStyle:{color:C.ink3}}),
      series:[{type:"bar",stack:"w",silent:true,itemStyle:{color:"transparent"},data:wf.map((w,i)=>i===0||i===wf.length-1?0:Math.max(0,w[1]-w[2]))},
        {type:"bar",stack:"w",barWidth:"48%",data:wf.map((w,i)=>i===0?{value:w[1],itemStyle:{color:C.grid,borderRadius:6}}:i===wf.length-1?{value:w[1],itemStyle:{color:w[1]<=0?C.good:C.grid,borderRadius:6}}:{value:w[2],itemStyle:{color:new echarts.graphic.LinearGradient(0,0,0,1,[{offset:0,color:C.good},{offset:1,color:hexA(C.good,.35)}]),borderRadius:6}}),
          label:{show:true,position:"top",color:C.ink2,fontFamily:"IBM Plex Mono",fontSize:10,formatter:p=>{const w=wf[p.dataIndex];return w[2]?"−"+fmt(w[2]):fmt(w[1])}}}]});
    const bill0=B.imp*pi-B.exp*pe,bill1=imp*pi-exp*pe;
    mk("c-bill",{grid:{left:50,right:16,top:50,bottom:28},tooltip:{trigger:"axis",valueFormatter:v=>fmt(v)+" kWh"},
      graphic:[{type:"text",left:50,top:4,style:{text:`Net bill ${R(Math.max(0,bill0))} → ${bill1<0?"credit "+R(-bill1):R(bill1)}`,fill:C.ink,font:"600 13px Sora"}}],
      xAxis:ax({type:"category",data:["Today","With plan"]}),yAxis:ax({type:"value"}),
      series:[{name:"Bought",type:"bar",barWidth:34,data:[B.imp,imp],itemStyle:{color:C.grid,borderRadius:[6,6,0,0]},label:{show:true,position:"top",color:C.ink2,fontFamily:"IBM Plex Mono",fontSize:11,formatter:p=>fmt(p.value)+" kWh"}},
        {name:"Sold",type:"bar",barWidth:34,data:[B.exp,exp],itemStyle:{color:C.exp,borderRadius:[6,6,0,0]},label:{show:true,position:"top",color:C.ink2,fontFamily:"IBM Plex Mono",fontSize:11,formatter:p=>fmt(p.value)+" kWh"}}]});
  }
  document.querySelectorAll(".act").forEach(b=>b.onclick=()=>{const k=b.dataset.k;on.has(k)?on.delete(k):on.add(k);b.setAttribute("aria-pressed",on.has(k));update()});
  update();
};

/* ================= ALERTS ================= */
builders.alerts=async function(){
  const all=ST.alerts.alerts,open=all.filter(a=>!a.resolved_at),resolved=all.filter(a=>a.resolved_at).slice(0,10);
  const serious=open.filter(a=>a.severity!=="info"&&!a.acked_at);
  $("#al-head").innerHTML=serious.length?`${serious.length} thing${serious.length>1?"s":""} need${serious.length>1?"":"s"} a look. <em>${open.some(a=>a.severity==="crit"&&!a.acked_at)?"One is high priority.":"Nothing is urgent."}</em>`:"<em>All clear.</em> Nothing needs attention.";
  const when=t=>new Date(t*1000).toLocaleDateString("en-ZA",{day:"numeric",month:"short"});
  const row=(a,res)=>`<div class="al ${a.severity} ${a.acked_at?"acked":""} ${res?"resolved":""}"><div class="sev">${IC[a.severity]}</div><div><b>${esc(a.title)}</b><span>${esc(a.detail)}</span></div>
    <div class="meta">${res?`Resolved ${when(a.resolved_at)}`:`Raised ${when(a.first_seen)}`}<br>${!res&&!a.acked_at?`<button class="btn" type="button" data-ack="${esc(a.key)}" style="margin-top:6px">Acknowledge</button>`:a.acked_at&&!res?"Acknowledged":""}</div></div>`;
  $("#al-full").innerHTML=(open.length?open.map(a=>row(a,false)).join(""):`<div class="empty">No open alerts.</div>`)+(resolved.length?`<div class="eyebrow" style="margin-top:10px">Recently resolved</div>`+resolved.map(a=>row(a,true)).join(""):"");
  document.querySelectorAll("[data-ack]").forEach(b=>b.onclick=async()=>{await api("api/alerts/"+encodeURIComponent(b.dataset.ack)+"/ack",{method:"POST"});ST.alerts=await api("api/alerts");badge();builders.alerts()});
  const bt=await api("api/battery-temp");
  if(!bt.rows.length)$("#batt-card").hidden=true;
  else{const B=bt.rows;mk("c-batt",{grid:{left:44,right:16,top:20,bottom:28},tooltip:{trigger:"axis",valueFormatter:v=>fmt(v,1)+" °C"},
    xAxis:ax({type:"category",data:B.map(b=>new Date(b[0]*1000).toLocaleString("en-ZA",{day:"numeric",month:"short",hour:"2-digit"})),boundaryGap:false,axisLabel:monoLabel({interval:23,fontSize:10})}),
    yAxis:ax({type:"value",scale:true,axisLabel:monoLabel({formatter:"{value}°"})}),
    series:[{name:"Peak",type:"line",symbol:"none",data:B.map(b=>b[2]),lineStyle:{width:1,color:hexA(C.warn,.5)},areaStyle:{color:grad(C.warn,.18)}},
      {name:"Average",type:"line",smooth:.3,symbol:"none",data:B.map(b=>b[1]),lineStyle:{width:2.5,color:C.warn,shadowBlur:10,shadowColor:hexA(C.warn,.5)},
       markLine:{silent:true,symbol:"none",lineStyle:{color:C.crit,type:[5,4]},label:{color:C.crit,fontSize:10,formatter:"45 °C",position:"insideEndTop"},data:[{yAxis:45}]}}]})}
  const L=ST.alerts.log.filter(l=>l.event==="raised"),wk=t=>{const d=new Date(t*1000);d.setDate(d.getDate()-((d.getDay()+6)%7));return d.toISOString().slice(0,10)};
  const weeks=[];for(let i=11;i>=0;i--){const d=new Date();d.setDate(d.getDate()-i*7);weeks.push(wk(d/1000))}
  const cnt=s=>weeks.map(w=>L.filter(l=>wk(l.ts)===w&&l.severity===s).length);
  mk("c-alhist",{grid:{left:30,right:10,top:20,bottom:28},tooltip:{trigger:"axis"},
    xAxis:ax({type:"category",data:weeks.map(w=>new Date(w+"T12:00:00").toLocaleDateString("en-ZA",{day:"numeric",month:"short"})),axisLabel:monoLabel({fontSize:10,interval:2})}),yAxis:ax({type:"value",minInterval:1}),
    series:[["High","crit",C.crit],["Medium","warn",C.warn],["Low","info",C.info]].map(([n,s,c])=>({name:n,type:"bar",stack:"a",barWidth:12,data:cnt(s),itemStyle:{color:c}}))});
};

/* ---------- boot ---------- */
(async function boot(){
  try{const s=await api("api/status");if(s.location)$("#loc-name").textContent=s.location;$("#conn-sub").textContent=`${fmt(s.counts?.entities)} entities`}catch(e){}
  await Promise.all([pollLive(),pollAlerts()]);
  route();
  setInterval(pollLive,5000);
  setInterval(pollAlerts,60000);
  setInterval(()=>{if(["overview","energy","appliances","habits","weather","plan"].includes(current)){loadView(current).then(()=>current!=="overview"||builders.overview()).catch(()=>{})}},300000);
})();
