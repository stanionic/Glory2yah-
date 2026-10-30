"""Detect low-contrast (white-on-light) buttons/labels in the KONFERANS room page."""
import os
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5000"
OUT = "_konf_screens"
OWNER = {"identifier": "+50948592888", "password": "pass123"}
ROOM_CODE = "UBTKE6"

JS = r"""
() => {
  function parseColor(s){
    if(!s) return null;
    let m = s.match(/rgba?\(([^)]+)\)/);
    if(!m) return null;
    const p = m[1].split(/[,\s/]+/).filter(x=>x.length).map(Number);
    return {r:p[0],g:p[1],b:p[2],a:p.length>3?p[3]:1};
  }
  function lastLayer(s){
    // return the bottom-most (last) background layer string, respecting parentheses
    let depth = 0, splitAt = -1;
    for(let i=0;i<s.length;i++){
      const ch = s[i];
      if(ch==='(') depth++;
      else if(ch===')') depth--;
      else if(ch===',' && depth===0) splitAt = i;
    }
    return splitAt<0 ? s : s.slice(splitAt+1);
  }
  function gradRgb(s){
    // average the rgb() stops of the bottom-most gradient layer
    if(!s || s === 'none') return null;
    const layer = lastLayer(s);
    if(!/gradient\(/.test(layer)) return null;
    const stops = [];
    const re = /rgba?\((\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([\d.]+))?\)/g;
    let m;
    while((m = re.exec(layer))){
      const a = m[4] === undefined ? 1 : parseFloat(m[4]);
      if(a > 0.15) stops.push({r:+m[1], g:+m[2], b:+m[3], a});
    }
    if(!stops.length) return null;
    const t = stops.reduce((s,c)=>({r:s.r+c.r*c.a, g:s.g+c.g*c.a, b:s.b+c.b*c.a}), {r:0,g:0,b:0});
    const n = stops.reduce((s,c)=>s+c.a, 0) || 1;
    return {r:Math.round(t.r/n), g:Math.round(t.g/n), b:Math.round(t.b/n), a:1};
  }
  function gradHasOpaqueLayer(s){
    // true if the bottom-most layer is a gradient with an opaque color stop
    if(!s || s === 'none') return false;
    const layer = lastLayer(s);
    if(!/gradient\(/.test(layer)) return false;
    return /rgba?\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*(?:,\s*1(?:\.0+)?\s*)?\)/.test(layer);
  }
  function ownBg(el){
    // solid color if opaque enough; gradient average only when the gradient has an opaque layer
    if(el.tagName === 'BODY') return null;  // room sections paint their own dark backdrop
    const cs = getComputedStyle(el);
    const c = parseColor(cs.backgroundColor);
    if(gradHasOpaqueLayer(cs.backgroundImage)){
      const g = gradRgb(cs.backgroundImage);
      if(g) return g;
    }
    if(c && c.a >= 0.85) return {r:c.r,g:c.g,b:c.b,a:1};
    if(c && c.a > 0.05) return c;
    return null;
  }
  function effBg(el){
    // composite the ancestor background stack from root down (solid colors + gradients)
    const stack = [];
    let cur = el;
    while(cur){
      const c = ownBg(cur);
      if(c) stack.push(c);
      cur = cur.parentElement;
    }
    // fall back to the page background (this app's body is dark-navy on konf pages)
    let bg = {r:17,g:24,b:39};
    for(let i=stack.length-1;i>=0;i--){
      const c = stack[i]; const a = c.a==null?1:c.a;
      bg = {r: c.r*a + bg.r*(1-a), g: c.g*a + bg.g*(1-a), b: c.b*a + bg.b*(1-a)};
    }
    return {r:Math.round(bg.r),g:Math.round(bg.g),b:Math.round(bg.b),a:1};
  }
  function fgOverBg(fg, bg){
    const a = fg.a==null?1:fg.a;
    return {r: fg.r*a+bg.r*(1-a), g: fg.g*a+bg.g*(1-a), b: fg.b*a+bg.b*(1-a), a:1};
  }
  function lum(c){
    const f = v => { v/=255; return v<=0.03928? v/12.92 : Math.pow((v+0.055)/1.055,2.4); };
    return 0.2126*f(c.r)+0.7152*f(c.g)+0.0722*f(c.b);
  }
  function contrast(a,b){ const L1=lum(a),L2=lum(b); const hi=Math.max(L1,L2),lo=Math.min(L1,L2); return (hi+0.05)/(lo+0.05); }
  const out = [];
  const sel = "button, .konf-ctrl-btn, .konf-avmode-btn, .konf-mini-btn, .konf-btn, select, a.konf-btn, .konf-lock-label, .konf-camera-select";
  document.querySelectorAll(sel).forEach(el=>{
    const r = el.getBoundingClientRect();
    if(r.width<2||r.height<2) return;
    const txt = (el.textContent||'').trim().slice(0,28);
    if(!txt) return;
    const cs = getComputedStyle(el);
    const fgRaw = parseColor(cs.color);
    const bg = effBg(el);
    if(!fgRaw) return;
    const fg = fgOverBg(fgRaw, bg);
    const ratio = contrast(fg, bg);
    if(ratio < 2.5){
      out.push({tag:el.tagName.toLowerCase(), cls:el.className.toString().slice(0,40), txt,
                fg:cs.color, bg:`rgb(${bg.r},${bg.g},${bg.b})`, ratio:+ratio.toFixed(2)});
    }
  });
  return out;
}
"""

def main():
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1366, "height": 900})
        page = ctx.new_page()
        page.goto(BASE + "/auth/login", wait_until="networkidle")
        try:
            d = page.query_selector(".pwa-popup-dismiss-btn")
            if d and d.is_visible(): d.click()
        except Exception: pass
        page.fill("input[name='identifier']", OWNER["identifier"])
        page.fill("input[name='password']", OWNER["password"])
        page.click("#loginSubmit")
        page.wait_for_timeout(2500)
        page.goto(BASE + f"/konferans/room/{ROOM_CODE}?user_name=Owner", wait_until="networkidle")
        page.wait_for_timeout(1500)
        fails = page.evaluate(JS)
        with open(f"{OUT}/_contrast_owner.txt", "w", encoding="utf-8") as fh:
            fh.write("LOW-CONTRAST ELEMENTS (owner room)\n")
            for f in fails:
                fh.write(f"{f}\n")
        print("owner fails:", len(fails))

        # guest
        ctx2 = b.new_context(viewport={"width": 1366, "height": 900})
        pg = ctx2.new_page()
        pg.goto(BASE + "/konferans/room/VD1R78?user_name=Tester", wait_until="networkidle")
        pg.wait_for_timeout(1500)
        gfails = pg.evaluate(JS)
        with open(f"{OUT}/_contrast_guest.txt", "w", encoding="utf-8") as fh:
            fh.write("LOW-CONTRAST ELEMENTS (guest room)\n")
            for f in gfails:
                fh.write(f"{f}\n")
        print("guest fails:", len(gfails))
        b.close()

if __name__ == "__main__":
    main()
