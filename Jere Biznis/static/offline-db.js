const DB="g2yp-institution-local";const V=1;
export function openLocalDB(){return new Promise((ok,no)=>{const r=indexedDB.open(DB,V);
r.onupgradeneeded=()=>{const d=r.result;if(!d.objectStoreNames.contains("operations"))d.createObjectStore("operations",{keyPath:"operation_id"});
if(!d.objectStoreNames.contains("subscription"))d.createObjectStore("subscription",{keyPath:"institution_id"});};
r.onsuccess=()=>ok(r.result);r.onerror=()=>no(r.error);});}
export async function queueOperation(op){const d=await openLocalDB();return new Promise((ok,no)=>{
const t=d.transaction("operations","readwrite");t.objectStore("operations").put(op);t.oncomplete=ok;t.onerror=()=>no(t.error);});}
