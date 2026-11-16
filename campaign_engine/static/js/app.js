(function(){
  const $=(s,r=document)=>r.querySelector(s), $$=(s,r=document)=>[...r.querySelectorAll(s)];
  /* ---------- theme ---------- */
  const root=document.documentElement;
  const saved=localStorage.getItem('theme');
  root.dataset.theme = saved || (matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light');
  window.toast=(m)=>{let t=$('#toast');t.textContent=m;t.classList.add('on');setTimeout(()=>t.classList.remove('on'),1800)};
  document.addEventListener('click',e=>{
    if(e.target.closest('#themeBtn')){root.dataset.theme=root.dataset.theme==='dark'?'light':'dark';localStorage.setItem('theme',root.dataset.theme);Charts.retheme()}
    if(e.target.closest('#menuBtn')) $('#sidebar').classList.toggle('open');
    else if(!e.target.closest('#sidebar')) $('#sidebar')?.classList.remove('open');
    const p=e.target.closest('[data-print]'); if(p) window.print();
  });
  /* ---------- filter auto-submit ---------- */
  $$('form[data-auto] select').forEach(s=>s.addEventListener('change',()=>s.form.submit()));

  /* ---------- charts ---------- */
  const PAL=['#0b9a93','#e9a23b','#7a5ce0','#d6455d','#2f9e6e','#3b82c4','#c2578f','#8a9a2b','#e07a1f','#5b6b7a','#14b8a6','#a855f7','#f43f5e','#84cc16'];
  const css=v=>getComputedStyle(root).getPropertyValue(v).trim();
  const Charts={list:{},
    defaults(){ if(!window.Chart)return;
      Chart.defaults.color=css('--muted'); Chart.defaults.borderColor=css('--line');
      Chart.defaults.font.family=getComputedStyle(document.body).fontFamily; Chart.defaults.font.size=12;
      Chart.defaults.plugins.tooltip.padding=10; Chart.defaults.maintainAspectRatio=false; Chart.defaults.responsive=true;
      Chart.defaults.plugins.legend.labels.usePointStyle=true; Chart.defaults.plugins.legend.labels.boxWidth=8;
    },
    prep(cfg){
      cfg=JSON.parse(JSON.stringify(cfg)); const o=cfg.options=cfg.options||{};
      const byPoint=o.colorByPoint, noGrid=o.noGrid, click=o.clickPostId; delete o.colorByPoint; delete o.noGrid; delete o.clickPostId;
      (cfg.data.datasets||[]).forEach((d,i)=>{
        if(cfg.type==='doughnut'||cfg.type==='pie'){ d.backgroundColor=d.backgroundColor||cfg.data.labels.map((_,j)=>PAL[j%PAL.length]); d.borderColor=css('--surface'); d.borderWidth=2; }
        else if(byPoint&&cfg.data.datasets.length===1){ d.backgroundColor=cfg.data.labels.map((_,j)=>PAL[j%PAL.length]); d.borderRadius=6; }
        else { const c=PAL[i%PAL.length]; d.backgroundColor=d.backgroundColor||c; d.borderColor=d.borderColor||c; if(cfg.type==='bar')d.borderRadius=5; }
      });
      if(noGrid){o.scales=o.scales||{};['x','y'].forEach(a=>{o.scales[a]=Object.assign({grid:{display:false}},o.scales[a]||{})})}
      o.plugins=o.plugins||{}; o.interaction=o.interaction||{mode:cfg.type==='scatter'?'nearest':'index',intersect:cfg.type==='scatter'};
      if(cfg.type==='scatter'){
        o.plugins.tooltip=Object.assign({callbacks:{label:function(c){const r=c.raw;return c.dataset.label+(r.id?' \u00b7 '+r.id:'')+' ('+r.x+', '+r.y+')'}}},o.plugins.tooltip||{});
      }
      if(click){ o.onClick=(e,els,ch)=>{ if(!els.length)return; const r=ch.data.datasets[els[0].datasetIndex].data[els[0].index]; if(r.id) location.href='/posts/'+r.id; }; o.onHover=(e,els)=>{e.native.target.style.cursor=els.length?'pointer':'default'} }
      return cfg;
    },
    make(id,cfg){ const el=document.getElementById(id); if(!el||!window.Chart)return;
      this.defaults(); if(this.list[id])this.list[id].destroy();
      const c=new Chart(el,this.prep(cfg)); c._src=cfg; this.list[id]=c; el.setAttribute('role','img'); return c; },
    retheme(){ this.defaults(); Object.entries(this.list).forEach(([id,c])=>this.make(id,c._src)); },
    init(){ $$('script[type="application/json"][data-chart]').forEach(s=>this.make(s.dataset.chart,JSON.parse(s.textContent))); }
  };
  window.Charts=Charts;
  document.addEventListener('DOMContentLoaded',()=>{Charts.init();document.body.classList.add('ready')});
})();
