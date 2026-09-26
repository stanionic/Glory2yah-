import {openLocalDB} from "./offline-db.js";
const BASE=window.JERE_BIZNIS_BASE||"";
export async function pendingOperations(){const d=await openLocalDB();return new Promise((ok,no)=>{
const t=d.transaction("operations","readonly"),r=t.objectStore("operations").getAll();
r.onsuccess=()=>ok(r.result.filter(x=>x.sync_status!=="SYNCED"));r.onerror=()=>no(r.error);});}
export async function syncInstitution(id){if(!navigator.onLine)return {offline:true};
const ops=await pendingOperations();if(!ops.length)return {synced:0};
const r=await fetch(`${BASE}/api/sync/push`,{method:"POST",
headers:{"Content-Type":"application/json"},body:JSON.stringify({operations:ops})});
if(!r.ok)throw new Error("sync failed");return r.json();}
window.addEventListener("online",()=>syncInstitution(Number(localStorage.getItem("institution_id")||"1")).catch(()=>{}));
