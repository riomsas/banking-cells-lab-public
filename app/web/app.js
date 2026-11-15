/*
 * Copyright 2026 Consulting RIOM S.A.S.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

"use strict";
const $ = id => document.getElementById(id);
const notice = message => { $("notice").textContent = message; };
const request = async (path, body) => {
  const response = await fetch(path, body === undefined ? {} : {
    method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify(body)
  });
  const result = await response.json();
  if (!response.ok) throw Error(result.error || "REQUEST_FAILED");
  return result;
};
const node = (tag, text, parent) => { const e=document.createElement(tag); e.textContent=String(text); if(parent)parent.append(e); return e; };
const cellText = (row, values) => { const tr=node("tr","",row); values.forEach(v=>node("td",v,tr)); return tr; };

// Keep stable API/storage codes; translate only at the presentation boundary.
const DOMAIN_LABELS = Object.freeze({
  "general-banking": "General Banking",
  "onboarding": "Onboarding",
  "payments": "Payments"
});
const domainLabel = code => DOMAIN_LABELS[code] || code;

const CHANNEL_LABELS = Object.freeze({ digital: "Digital", branch: "Sucursal" });
const channelLabel = code => CHANNEL_LABELS[code] || code;

const STATE_LABELS = Object.freeze({
  DRAFT: "Borrador",
  ACTIVE: "Activa",
  SUSPENDED: "Suspendida",
  INACTIVE: "Inactiva",
  RETIRED: "Retirada"
});
const stateLabel = code => STATE_LABELS[code] || code;

const ACTION_LABELS = Object.freeze({
  ACTIVE: "Activar",
  SUSPENDED: "Suspender",
  INACTIVE: "Desactivar",
  RETIRED: "Retirar"
});
const actionLabel = code => ACTION_LABELS[code] || code;

let cells = [], domains = [];
async function refresh() {
  try {
    const [stats, nextCells, events, analytics, scenarios] = await Promise.all([
      request("/api/metrics"), request("/api/cells"), request("/api/events?limit=100"), request("/api/analytics"), request("/api/simulations")
    ]);
    cells = nextCells;
    const kpis = [["Células",stats.cells_total],["Activas",stats.cells_active],
      ["Inactivas",stats.cells_inactive],["Capacidad disponible",stats.capacity_available],
      ["Carga actual",stats.capacity_used],["Solicitudes procesadas",stats.requests_processed],
      ["Solicitudes rechazadas",stats.requests_rejected],["Utilización",stats.utilization_percent+"%"]];
    $("kpis").replaceChildren();
    kpis.forEach(([k,v])=>{ const a=node("article","",$("kpis")); node("small",k,a); node("strong",v,a); });
    $("distribution").replaceChildren();
    for (const domain of domains) for(const channel of ["digital","branch"]) {
      const matched=cells.filter(c=>c.domain===domain&&c.channel===channel);
      cellText($("distribution"),[domainLabel(domain),channelLabel(channel),matched.length,matched.filter(c=>c.state==="ACTIVE").length,matched.reduce((a,c)=>a+c.used,0)]);
    }
    $("cells-body").replaceChildren();
    for(const c of cells) {
      const tr=cellText($("cells-body"),[c.id,domainLabel(c.domain),channelLabel(c.channel),stateLabel(c.state),c.used+" / "+c.capacity,c.priority]);
      const td=node("td","",tr), controls=node("div","",td);controls.className="actions";
      const next={DRAFT:["ACTIVE","INACTIVE"],ACTIVE:["SUSPENDED","INACTIVE"],SUSPENDED:["ACTIVE","INACTIVE"],INACTIVE:["ACTIVE","RETIRED"],RETIRED:[]};
      for(const state of next[c.state]){
        const b=node("button",actionLabel(state),controls);
        b.dataset.state=state;
        b.dataset.action=actionLabel(state);
        b.disabled=c.used>0&&state!=="ACTIVE";
        b.addEventListener("click",async()=>{
          if(!confirm("¿" + actionLabel(state) + " célula " + c.id + "?")) return;
          try {
            await request("/api/cells/"+encodeURIComponent(c.id)+"/transition",{state,reason:"Cambio manual de laboratorio"});
            await refresh();
            notice("Estado actualizado");
          }
          catch(e){notice("Error: "+e.message);}
        });
      }
      if(c.state!=="RETIRED"){
        const b=node("button","Capacidad",controls);
        b.addEventListener("click",async()=>{const v=prompt("Nueva capacidad para "+c.id,c.capacity);if(v===null)return;
          try{await request("/api/cells/"+encodeURIComponent(c.id)+"/capacity",{capacity:Number(v)});await refresh();notice("Capacidad actualizada");}
          catch(e){notice("Error: "+e.message);}
        });
      }
    }
    $("scenarios-body").replaceChildren();
    for(const item of scenarios) cellText($("scenarios-body"),[item.id,domainLabel(item.domain),channelLabel(item.channel),item.requested,item.routed,item.rejected]);
    $("requests-dist").replaceChildren();
    for(const item of analytics.requests_by_domain_channel) cellText($("requests-dist"),[domainLabel(item.domain),channelLabel(item.channel),item.requests]);
    $("event-trend").replaceChildren();
    for(const item of analytics.event_trend) cellText($("event-trend"),[item.minute,item.type,item.count]);
    $("events-body").replaceChildren();
    for(const e of events){cellText($("events-body"),[e.at,e.type,e.cell_id||"—",e.request_id||"—",JSON.stringify(e.detail)]);}
    notice("Datos sintéticos actualizados");
  } catch(e) {notice("No fue posible actualizar: "+e.message);}
}
document.querySelectorAll("[data-view]").forEach(b=>b.addEventListener("click",()=>{
  for(const s of ["dashboard","cells","routing","simulation","analytics","events"]) $(s).hidden=s!==b.dataset.view;
  document.querySelectorAll("[data-view]").forEach(x=>x.setAttribute("aria-pressed",String(x===b)));
}));
const submit = (id, endpoint, build, done) => $(id).addEventListener("submit",async event=>{
  event.preventDefault();const form=event.currentTarget, data=Object.fromEntries(new FormData(form));
  const button=form.querySelector("button[type=submit],button"); button.disabled=true;
  try{ const result=await request(endpoint,build(data)); if(done)done(result); await refresh();notice("Operación sintética completada"); }
  catch(e){notice("Error: "+e.message);}
  finally{button.disabled=false;}
});
submit("create-cell","/api/cells",d=>({...d,capacity:Number(d.capacity),priority:Number(d.priority),synthetic:true}));
submit("route","/api/routing",d=>({...d,synthetic:true}),r=>{
  $("route-output").replaceChildren();
  const p=node("p","Solicitud "+r.request_id+" asignada a "+r.cell_id,$("route-output"));
  const b=node("button","Completar y liberar capacidad",$("route-output"));
  b.addEventListener("click",async()=>{try{await request("/api/requests/"+encodeURIComponent(r.request_id)+"/complete",{});await refresh();p.textContent="Solicitud completada";b.disabled=true;}catch(e){notice("Error: "+e.message);}});
});
submit("simulate","/api/simulations",d=>({...d,count:Number(d.count),synthetic:true}),r=>{$("simulation-output").textContent=JSON.stringify(r,null,2);});
(async()=>{
  try {
    domains = await request("/api/domains");
    document.querySelectorAll(".domains").forEach(sel=>domains.forEach(d=>{
      const o=node("option",domainLabel(d),sel);
      o.value=d;
    }));
    await refresh();
  } catch(e) {
    notice("Error de conexión: "+e.message);
  }
})();
