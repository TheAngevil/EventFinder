document.getElementById('toggleAdv')
        .addEventListener('change', e=>{
  document.getElementById('advBox').style.display = e.target.checked?'block':'none';
});

(function(){
  /* ========== DOM 變數 ========== */
  const grid     = document.getElementById('eventGrid');
  const loader   = document.getElementById('loading');
  const form     = document.getElementById('searchForm');
  const advToggle= document.getElementById('toggleAdv');
  const advBox   = document.getElementById('advBox');
  const clearBtn = document.getElementById('clearDates');

  /* ========== 參數狀態 ========== */
  let offset=0, loading=false, done=false;
  const limit = window.matchMedia('(max-width:768px)').matches ? 5 : 9;
  let range   = null;

  /* ========== UI：進階搜尋開關 ========== */
  advToggle.addEventListener('change',()=>
    advBox.style.display = advToggle.checked ? 'block':'none');

  /* ========== flatpickr 初始化 ========== */
  const FP_LOCALE = window.FP_LOCALE || 'en';
  const localeMap = { 'zh-tw':'zh_tw' };
  const fp = flatpickr('#dateRange',{
    mode:'range',
    dateFormat:'Y-m-d',
    minDate:'today',
    maxDate:new Date().fp_incr(120),
    locale: FP_LOCALE==='en'
            ? undefined
            : flatpickr.l10ns[localeMap[FP_LOCALE]||FP_LOCALE],
    onChange(sel){
      range = sel;
      clearBtn.style.display = sel.length ? 'inline-block':'none';
    }
  });

  /* ========== Clear dates ========== */
  clearBtn.addEventListener('click',()=>{
    fp.clear();
    range = null;
    clearBtn.style.display='none';
    fetchEvents(true);          // ↩︎ 此時函式已宣告可用
  });

  /* ========== 卡片 HTML ========== */
  function buildCard(e){
    const tags = (e.tags||[])
                 .map(t=>`<span class="tag">#${t.name}</span>`).join('');
    const btnText = window.TEXT_VIEW_DETAILS || 'View Details';

    return `
      <div class="event-card">
        <h3>${e.title}</h3>
        <p class="date">📅 ${e.date.slice(0,10)} ${e.date.slice(11,16)}</p>
        <p>${e.description.slice(0,100)}…</p>
        <div class="tags">${tags}</div>
        <a class="btn" href="/events/${e.id}">${btnText}</a>
      </div>`;
  }

  /* ========== 主要載入函式 ========== */
  async function fetchEvents(reset=false){
    if(reset){ offset=0; done=false; grid.innerHTML=''; }

    if(loading||done) return;
    loading=true; loader.style.display='block';

    const params = new URLSearchParams(new FormData(form));
    if(range && range.length){
      params.set('start', range[0].toISOString().slice(0,10));
      if(range[1]){
        const diff=(range[1]-range[0])/864e5;
        if(diff>90){ alert('{{ _("Maximum range is 90 days") }}'); loading=false; return; }
        params.set('end', range[1].toISOString().slice(0,10));
      }
    }
    params.set('limit',limit);
    params.set('offset',offset);

    const res  = await fetch('/api/events?'+params);
    const data = await res.json();
    if(data.length < limit) done=true;

    data.forEach(e=>grid.insertAdjacentHTML('beforeend',buildCard(e)));
    offset+=data.length;
    loading=false; loader.style.display='none';
  }

  /* ========== 綁定事件 ========== */
  form.addEventListener('submit',e=>{
    e.preventDefault();
    fetchEvents(true);
  });
  window.addEventListener('scroll',()=>{
    if(window.innerHeight+window.scrollY >= document.body.offsetHeight-300)
      fetchEvents();
  });

  /* ========== 首次載入 ========== */
  fetchEvents();

  // /* 3️⃣ fetchEvents() 補無結果回饋 */
  // document.getElementById('noResult').hidden = !(reset && data.length === 0);
})();
//
//
//     /* ---------- flatpickr init ---------- */
// let range = null;// 之後讀取 start / end
// const advToggle  = document.getElementById('toggleAdv');
// const advBox     = document.getElementById('advBox');
// const clearBtn   = document.getElementById('clearDates');
// advToggle.addEventListener('change', () => {
//   advBox.style.display = advToggle.checked ? 'block' : 'none';
// });
// const FP_LOCALE = window.FP_LOCALE || 'en';
// var locale_code = 'en'
// switch (FP_LOCALE) {
//     case "zh-tw":
//         locale_code = "zh_tw"
// }
//
// const fp =  flatpickr('#dateRange', {
//     mode: 'range',
//     dateFormat: 'Y-m-d',
//     minDate: 'today',
//     maxDate: new Date().fp_incr(120),      // 未來 4 個月 ≈ 120 天
//     locale: locale_code, //FP_LOCALE,         // 跟隨當前語系
//     onChange(sel){
//         range = sel;                         // sel = [Date, Date?]
//         clearBtn.style.display = sel.length ? 'inline-block' : 'none';
//     }
// });
//
// /* ---------- 清空日期 ---------- */
// clearBtn.addEventListener('click', () => {
//   fp.clear();          // UI 歸零
//   range = null;        // 內部狀態歸零
//   clearBtn.style.display = 'none';
//   fetchEvents(true);   // 重新搜尋，保留關鍵字
// });
//
// (function(){
//     const grid     = document.getElementById('eventGrid');
//     const loader   = document.getElementById('loading');
//     const form     = document.getElementById('searchForm');
//     let offset     = 0;
//     const isMobile = window.matchMedia("only screen and (max-width: 768px)").matches;
//     const limit    = isMobile ? 5 : 9;
//     let loading    = false;
//     let done       = false;
//
//     function buildCard(e){
//       const tags = (e.tags||[]).map(t=>`<span class="tag">#${t.name}</span>`).join(' ');
//       return `
//       <div class="event-card">
//         <h3>${e.title}</h3>
//         <p class="date">📅 ${e.date.slice(0,10)} ${e.date.slice(11,16)}</p>
//         <p>${e.description.slice(0,100)}…</p>
//         <div class="tags">${tags}</div>
//         <a class="btn" href="/events/${e.id}">{{ _('View Details') }}</a>
//       </div>`;
//     }
//
//     async function fetchEvents(reset=false){
//         console.log('[fetchEvents called]', { reset, offset, limit, loading, done });
//
//
//
//         if(reset){
//         offset = 0;
//         done   = false;
//         grid.innerHTML = '';
//       }
//
//       if(loading||done) return;
//       loading = true;
//       loader.style.display = 'block';
//
//       const params = new URLSearchParams(new FormData(form));
//
//       if (range && range.length) {
//           params.set('start', range[0].toISOString().slice(0,10));
//           if (range[1]) {
//             // 最多 90 天；flatpickr 只限制 120，所以再判一次
//             const diff = (range[1] - range[0]) / 86400000;
//             if (diff > 90) {
//               alert("{{ _('Maximum range is 90 days') }}");
//               return;
//             }
//             params.set('end', range[1].toISOString().slice(0,10));
//           }
//       }
//
//       params.set('limit',  limit);
//       params.set('offset', offset);
//
//         console.log('[calling api]', '/api/events?' + params);
//       const res  = await fetch('/api/events?' + params);
//         console.log('[api status]', res.status);
//       const data = await res.json();
//         console.log('[api data length]', data.length, data);
//       if(data.length < limit) done = true;
//
//       data.forEach(e => grid.insertAdjacentHTML('beforeend', buildCard(e)));
//       offset += data.length;
//       loading = false;
//       loader.style.display = 'none';
//     }
//
//     // 初次載入
//     fetchEvents();
//
//     // 搜尋時重置並重拉
//     form.addEventListener('submit', e => {
//       e.preventDefault();
//       fetchEvents(true);
//     });
//
//     // 滾動到底部自動載更多
//     window.addEventListener('scroll', () => {
//       if(window.innerHeight + window.scrollY >= document.body.offsetHeight - 300){
//         fetchEvents();
//       }
//     });
//   })();