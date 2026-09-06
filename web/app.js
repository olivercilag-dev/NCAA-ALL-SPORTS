const I18N={
en:{sub:"All NCAA events • One chronological feed • UTC",yesterday:"YESTERDAY",today:"TODAY",tomorrow:"TOMORROW",next:"NEXT 7 DAYS",search:"Search team, sport, conference or venue",all:"All sports",events:"events",empty:"No verified events in this period.",sources:"Sources",confidence:"Data confidence",scheduled:"Scheduled",close:"Close"},
sr:{sub:"Svi NCAA događaji • Jedan hronološki feed • UTC",yesterday:"JUČE",today:"DANAS",tomorrow:"SUTRA",next:"SLEDEĆIH 7 DANA",search:"Pretraži tim, sport, konferenciju ili mesto",all:"Svi sportovi",events:"događaja",empty:"Nema potvrđenih događaja u ovom periodu.",sources:"Izvori",confidence:"Pouzdanost podataka",scheduled:"Zakazano",close:"Zatvori"},
es:{sub:"Todos los eventos NCAA • Un feed cronológico • UTC",yesterday:"AYER",today:"HOY",tomorrow:"MAÑANA",next:"PRÓXIMOS 7 DÍAS",search:"Buscar equipo, deporte, conferencia o sede",all:"Todos los deportes",events:"eventos",empty:"No hay eventos verificados en este periodo.",sources:"Fuentes",confidence:"Confianza de datos",scheduled:"Programado",close:"Cerrar"},
fr:{sub:"Tous les événements NCAA • Un fil chronologique • UTC",yesterday:"HIER",today:"AUJOURD'HUI",tomorrow:"DEMAIN",next:"7 PROCHAINS JOURS",search:"Rechercher équipe, sport, conférence ou lieu",all:"Tous les sports",events:"événements",empty:"Aucun événement vérifié pour cette période.",sources:"Sources",confidence:"Fiabilité des données",scheduled:"Programmé",close:"Fermer"},
de:{sub:"Alle NCAA-Veranstaltungen • Ein chronologischer Feed • UTC",yesterday:"GESTERN",today:"HEUTE",tomorrow:"MORGEN",next:"NÄCHSTE 7 TAGE",search:"Team, Sport, Konferenz oder Ort suchen",all:"Alle Sportarten",events:"Veranstaltungen",empty:"Keine verifizierten Veranstaltungen in diesem Zeitraum.",sources:"Quellen",confidence:"Datenvertrauen",scheduled:"Geplant",close:"Schließen"},
it:{sub:"Tutti gli eventi NCAA • Un feed cronologico • UTC",yesterday:"IERI",today:"OGGI",tomorrow:"DOMANI",next:"PROSSIMI 7 GIORNI",search:"Cerca squadra, sport, conference o luogo",all:"Tutti gli sport",events:"eventi",empty:"Nessun evento verificato in questo periodo.",sources:"Fonti",confidence:"Affidabilità dati",scheduled:"Programmato",close:"Chiudi"},
pt:{sub:"Todos os eventos NCAA • Um feed cronológico • UTC",yesterday:"ONTEM",today:"HOJE",tomorrow:"AMANHÃ",next:"PRÓXIMOS 7 DIAS",search:"Pesquisar equipe, esporte, conferência ou local",all:"Todos os esportes",events:"eventos",empty:"Nenhum evento verificado neste período.",sources:"Fontes",confidence:"Confiança dos dados",scheduled:"Agendado",close:"Fechar"},
nl:{sub:"Alle NCAA-evenementen • Eén chronologische feed • UTC",yesterday:"GISTEREN",today:"VANDAAG",tomorrow:"MORGEN",next:"VOLGENDE 7 DAGEN",search:"Zoek team, sport, conferentie of locatie",all:"Alle sporten",events:"evenementen",empty:"Geen geverifieerde evenementen in deze periode.",sources:"Bronnen",confidence:"Databetrouwbaarheid",scheduled:"Gepland",close:"Sluiten"},
tr:{sub:"Tüm NCAA etkinlikleri • Tek kronolojik akış • UTC",yesterday:"DÜN",today:"BUGÜN",tomorrow:"YARIN",next:"SONRAKİ 7 GÜN",search:"Takım, spor, konferans veya tesis ara",all:"Tüm sporlar",events:"etkinlik",empty:"Bu dönemde doğrulanmış etkinlik yok.",sources:"Kaynaklar",confidence:"Veri güveni",scheduled:"Planlandı",close:"Kapat"},
ja:{sub:"NCAA全イベント • 時系列フィード • UTC",yesterday:"昨日",today:"今日",tomorrow:"明日",next:"次の7日間",search:"チーム、競技、カンファレンス、会場を検索",all:"全競技",events:"イベント",empty:"この期間に確認済みイベントはありません。",sources:"情報源",confidence:"データ信頼度",scheduled:"予定",close:"閉じる"}
};
const SPORTS={football:"Football",soccer:"Soccer",basketball:"Basketball",volleyball:"Volleyball",baseball:"Baseball",softball:"Softball",ice_hockey:"Ice Hockey",field_hockey:"Field Hockey",track_field:"Track & Field",swimming_diving:"Swimming & Diving",wrestling:"Wrestling",gymnastics:"Gymnastics",lacrosse:"Lacrosse",cross_country:"Cross Country",water_polo:"Water Polo",rowing:"Rowing",golf:"Golf",fencing:"Fencing"};
let lang=localStorage.getItem("ncaaLang")||navigator.language.slice(0,2); if(!I18N[lang])lang="en";
let range="today", events=[];
const $=id=>document.getElementById(id);
function t(k){return I18N[lang][k]||I18N.en[k]||k}
function dayKey(d){return d.toISOString().slice(0,10)}
function utcDayOffset(n){let d=new Date();d.setUTCHours(0,0,0,0);d.setUTCDate(d.getUTCDate()+n);return dayKey(d)}
function setup(){
 $("lang").innerHTML=Object.keys(I18N).map(x=>`<option value="${x}">${x.toUpperCase()}</option>`).join("");$("lang").value=lang;
 $("lang").onchange=e=>{lang=e.target.value;localStorage.setItem("ncaaLang",lang);render()};
 $("ranges").innerHTML=[["yesterday","yesterday"],["today","today"],["tomorrow","tomorrow"],["next","next"]].map(([k,v])=>`<button data-r="${v}">${t(k)}</button>`).join("");
 document.querySelectorAll("#ranges button").forEach(b=>b.onclick=()=>{range=b.dataset.r;document.querySelectorAll("#ranges button").forEach(x=>x.classList.toggle("active",x===b));render()});
 $("search").oninput=render; $("sport").onchange=render; $("close").onclick=()=> $("modal").classList.add("hidden");
}
function applyTexts(){
 $("sub").textContent=t("sub");$("search").placeholder=t("search");
 $("ranges").querySelectorAll("button").forEach(b=>b.textContent=t(b.dataset.r==="next"?"next":b.dataset.r));
 $("sport").innerHTML=`<option value="">${t("all")}</option>`+Object.entries(SPORTS).map(([k,v])=>`<option value="${k}">${v}</option>`).join("");
}
function render(){
 applyTexts();let today=utcDayOffset(0);
 let days=range==="yesterday"?[utcDayOffset(-1)]:range==="tomorrow"?[utcDayOffset(1)]:range==="next"?Array.from({length:7},(_,i)=>utcDayOffset(i+1)):[today];
 let q=$("search").value.toLowerCase(), sp=$("sport").value;
 let list=events.filter(e=>days.includes(e.start_utc.slice(0,10))&&( !sp||e.sport===sp)&&JSON.stringify(e).toLowerCase().includes(q));
 $("feed").innerHTML="";
 if(!list.length){$("feed").innerHTML=`<div class="empty">${t("empty")}</div>`;return}
 for(const day of days){let arr=list.filter(e=>e.start_utc.slice(0,10)===day);if(!arr.length)continue;
   let h=document.createElement("div");h.className="day";h.textContent=day+" UTC • "+arr.length+" "+t("events");$("feed").appendChild(h);
   arr.forEach(e=>{let card=document.createElement("article");card.className="event";card.innerHTML=`<div class="time">${e.start_utc.slice(11,16)}<br><small>UTC</small></div><div><span class="sportbar" style="background:${e.color||"#94a3b8"}"></span><div class="teams">${e.home||"TBD"} <span class="vs">VS</span> ${e.away||"TBD"}</div><div class="meta">${SPORTS[e.sport]||e.sport} • ${e.conference||e.competition||"NCAA"}${e.venue?" • "+e.venue:""}</div></div><div class="badge"><span class="status">${e.status||t("scheduled")}</span></div>`;card.onclick=()=>detail(e);$("feed").appendChild(card)})}
}
function detail(e){
 $("detail").innerHTML=`<h2>${e.home||"TBD"} vs ${e.away||"TBD"}</h2>
 <div class="row"><div class="label">UTC</div>${e.start_utc}</div>
 <div class="row"><div class="label">Sport</div>${SPORTS[e.sport]||e.sport}</div>
 <div class="row"><div class="label">Competition / Conference</div>${e.competition||"NCAA"} ${e.conference?"/ "+e.conference:""}</div>
 <div class="row"><div class="label">Venue</div>${e.venue||"TBD"}</div>
 <div class="row"><div class="label">${t("confidence")}</div>${Math.round((e.confidence||0)*100)}%</div>
 <div class="row"><div class="label">${t("sources")}</div>${e.source||"—"}${e.source_url?` — <a href="${e.source_url}" target="_blank" rel="noopener">open source</a>`:""}</div>`;
 $("modal").classList.remove("hidden");
}
async function load(){try{let r=await fetch("/api/events");events=await r.json();render()}catch(e){$("feed").innerHTML='<div class="empty">API unavailable.</div>'}}
function clock(){let d=new Date();$("clock").textContent=d.toISOString().replace("T"," ").slice(0,19)+" UTC"}
setup();document.querySelector('#ranges button[data-r="today"]').classList.add("active");load();clock();setInterval(clock,1000);setInterval(load,60000);
