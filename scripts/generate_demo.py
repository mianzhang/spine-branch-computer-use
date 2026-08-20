#!/usr/bin/env python3
"""Generate a self-contained interactive HTML demo from a Spine-Branch trajectory.

Reads a task's dependency_graph.json + each subtask's step_*.png screenshots +
traj.jsonl actions + final_results.json timings, and renders a single .html with:
  - the Spine-Branch DAG (branches vs spine, artifact vs state-inheritance edges),
  - a synchronized "video wall" of the agents currently running in parallel,
  - a Gantt timeline with a draggable playhead,
  - per-step action / reasoning captions.

Screenshots are downsampled to JPEG and base64-embedded, so the output is one
portable file. Usage:

  python scripts/generate_demo.py RUN_DIR TASK_ID [-o out.html]
       [--width 880] [--quality 72] [--max-frames-per-node 28]

RUN_DIR is a spine-branch run dir (contains odysseys_eval.json); TASK_ID is the
task hash sub-directory.
"""
import argparse, base64, glob, io, json, os, re, sys
from collections import defaultdict

try:
    from PIL import Image
except ImportError:
    sys.exit("Pillow required: VIRTUAL_ENV=.venv uv pip install pillow")


def log(m): print(m, file=sys.stderr)


# ---------------------------------------------------------------- data loading
def load_graph(task_dir):
    g = json.load(open(os.path.join(task_dir, "dependency_graph.json")))
    inner = g.get("dependency_graph", g)
    subs = list(inner.get("subtasks", inner.get("nodes", [])))
    agg = inner.get("aggregation") or g.get("aggregation")
    if agg and not any(x.get("id") == agg.get("id") for x in subs):
        subs.append(agg)  # final manager-aggregation node
    nodes = []
    for s in subs:
        outs = s.get("outputs") or []
        art = ""
        if outs:
            nm = (outs[0].get("name") or "").strip()
            art = nm.split("__")[-1] if "__" in nm else nm
        nodes.append({
            "id": s["id"],
            "role": s.get("role", "branch"),
            "agent_type": s.get("agent_type", "cua"),
            "deps": list(s.get("dependencies", []) or []),
            "init_from": s.get("init_from"),
            "desc": (s.get("description") or "").strip(),
            "art": art,
        })
    meta = {
        "task_id": g.get("task_id", os.path.basename(task_dir)),
        "task_text": (g.get("task_text") or g.get("instruction") or "").strip(),
        "website": g.get("website", ""),
    }
    return nodes, meta


def load_timings(task_dir):
    """Return {node_id: duration_seconds}, final_vm_subtask_id, final_response, replans."""
    fr_path = os.path.join(task_dir, "final_results.json")
    dur, final_vm, final_resp, replans = {}, None, "", 0
    if os.path.exists(fr_path):
        fr = json.load(open(fr_path))
        for k, v in (fr.get("task_timings") or {}).items():
            if isinstance(v, dict) and isinstance(v.get("duration_seconds"), (int, float)):
                dur[k] = float(v["duration_seconds"])
        final_vm = fr.get("final_vm_subtask_id")
        final_resp = (fr.get("final_response") or "").strip()
        rp = fr.get("replanning") or {}
        if isinstance(rp, dict):
            replans = rp.get("num_replans", rp.get("count", 0)) or 0
    return dur, final_vm, final_resp, replans


def load_score(run_dir, task_id):
    p = os.path.join(run_dir, "odysseys_eval.json")
    if not os.path.exists(p):
        return None
    ev = json.load(open(p))
    tasks = ev.get("tasks", ev)
    if isinstance(tasks, list):
        for e in tasks:
            if (e.get("task_id") or e.get("id")) == task_id:
                return {"score": e.get("average_rubric_score"), "perfect": e.get("perfect")}
    return None


def load_backbone(task_dir):
    p = os.path.join(task_dir, "summary.json")
    if os.path.exists(p):
        sc = json.load(open(p)).get("subtask_costs", {})
        for v in sc.values():
            if v.get("model"):
                return v["model"]
    return "?"


STEP_RE = re.compile(r"step_(\d+)_")


def load_frames(task_dir, node_id, max_frames, width, quality):
    """Return ordered [{s,a,r,t,img}] for a node, subsampled + downsampled."""
    sub_dir = os.path.join(task_dir, node_id)
    pngs = glob.glob(os.path.join(sub_dir, "**", "step_*.png"), recursive=True)
    if not pngs:
        return []
    def stepnum(p):
        m = STEP_RE.search(os.path.basename(p))
        return int(m.group(1)) if m else 0
    pngs.sort(key=stepnum)
    # per-step action/reasoning from traj.jsonl
    traj = {}
    tj = glob.glob(os.path.join(sub_dir, "**", "traj.jsonl"), recursive=True)
    if tj:
        for line in open(tj[0]):
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            def _s(v):  # OSWorld stores action as a structured dict; coerce to text
                if v is None: return ""
                return (v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)).strip()
            traj[str(d.get("step_num"))] = (
                _s(d.get("action")),
                _s(d.get("reasoning") or d.get("response")),
            )
    total = len(pngs)
    # subsample evenly, always keep first and last
    if total > max_frames:
        idxs = sorted(set([0, total - 1] +
                          [round(i * (total - 1) / (max_frames - 1)) for i in range(max_frames)]))
    else:
        idxs = list(range(total))
    frames = []
    for i in idxs:
        p = pngs[i]
        sn = stepnum(p)
        act, rea = traj.get(str(sn), ("", ""))
        try:
            im = Image.open(p).convert("RGB")
            w, h = im.size
            nh = round(h * width / w)
            im = im.resize((width, nh), Image.LANCZOS)
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=quality)
            b64 = base64.b64encode(buf.getvalue()).decode()
        except Exception as e:
            log(f"  ! frame {p}: {e}")
            continue
        frames.append({"s": sn, "a": act[:220], "r": rea[:400], "t": total,
                       "img": "data:image/jpeg;base64," + b64})
    return frames


# ------------------------------------------------------------------- schedule
def schedule(nodes, dur):
    """Topological start/end; independent nodes overlap (parallel)."""
    by_id = {n["id"]: n for n in nodes}
    DEFAULT = 60.0
    start, end = {}, {}
    def compute(nid, seen):
        if nid in end:
            return end[nid]
        if nid in seen:  # cycle guard
            return 0.0
        seen.add(nid)
        n = by_id.get(nid)
        deps = [d for d in (n["deps"] if n else []) if d in by_id]
        st = max([compute(d, seen) for d in deps], default=0.0)
        d = dur.get(nid, DEFAULT) or DEFAULT
        start[nid], end[nid] = st, st + d
        return end[nid]
    for n in nodes:
        compute(n["id"], set())
    return start, end


def layers(nodes):
    """Longest-path layer per node for left-to-right DAG layout."""
    by_id = {n["id"]: n for n in nodes}
    lay = {}
    def L(nid, seen):
        if nid in lay:
            return lay[nid]
        if nid in seen:
            return 0
        seen.add(nid)
        n = by_id.get(nid)
        deps = [d for d in (n["deps"] if n else []) if d in by_id]
        lay[nid] = (max([L(d, seen) for d in deps], default=-1) + 1)
        return lay[nid]
    for n in nodes:
        L(n["id"], set())
    return lay


# ---------------------------------------------------------------------- build
def build(run_dir, task_id, out, width, quality, maxf, style="framework", v_gap=34, hide_task=False):
    task_dir = os.path.join(run_dir, task_id)
    if not os.path.isdir(task_dir):
        sys.exit(f"no task dir: {task_dir}")
    nodes, meta = load_graph(task_dir)
    dur, final_vm, final_resp, replans = load_timings(task_dir)
    sc = load_score(run_dir, task_id)
    meta["backbone"] = load_backbone(task_dir)
    meta["v_gap"] = v_gap
    meta["run_label"] = os.path.basename(run_dir.rstrip("/"))
    meta["final_vm"] = final_vm
    meta["final_response"] = final_resp[:1200]
    meta["replans"] = replans
    if sc:
        meta["score"] = sc.get("score")
        meta["perfect"] = sc.get("perfect")

    # load screenshots first, then DROP any CUA node that produced none — those are
    # planned-but-unexecuted subtasks (e.g. timed out before launch) with no VM to show.
    frames = {}
    for n in nodes:
        frames[n["id"]] = load_frames(task_dir, n["id"], maxf, width, quality)
        n["nframes"] = len(frames[n["id"]])
    keep = [n for n in nodes if n["agent_type"] == "manager" or n["nframes"] > 0]
    dropped = [n["id"] for n in nodes if n["agent_type"] != "manager" and n["nframes"] == 0]
    if dropped:
        log(f"  dropping {len(dropped)} node(s) with no screenshots (never executed): {dropped}")
    nodes = keep
    frames = {n["id"]: frames[n["id"]] for n in nodes}

    start, end = schedule(nodes, dur)
    lay = layers(nodes)
    for n in nodes:
        n["layer"] = lay.get(n["id"], 0)
        n["start"] = round(start.get(n["id"], 0), 1)
        n["end"] = round(end.get(n["id"], 0), 1)
        n["dur"] = round(n["end"] - n["start"], 1)
        log(f"  {n['id']:34s} role={n['role']:6s} layer={n['layer']} "
            f"[{n['start']:.0f}-{n['end']:.0f}s] frames={n['nframes']}")

    payload = {"meta": meta, "nodes": nodes, "frames": frames}
    tmpl = FRAMEWORK_TEMPLATE if style == "framework" else HTML_TEMPLATE
    html = tmpl.replace("/*__DATA__*/", json.dumps(payload))
    if hide_task:
        # drop the baked-in task-description box (the site renders the task text as HTML)
        import re as _re
        html = _re.sub(r"<header>.*?</header>", "", html, count=1, flags=_re.S)
        html = html.replace("document.getElementById('ttxt').textContent=M.task_text||'';", "")
        html = html.replace("document.getElementById('ttxt').title=M.task_text||'';", "")
    with open(out, "w") as f:
        f.write(html)
    mb = os.path.getsize(out) / 1048576
    log(f"\nwrote {out} ({mb:.1f} MB)")


# ------------------------------------------------------------------- template
HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>Spine-Branch Demo</title>
<style>
 :root{--bg:#0e1116;--panel:#171b22;--line:#2a323d;--ink:#e6edf3;--mut:#8b98a6;
   --branch:#3b82f6;--spine:#f59e0b;--mgr:#a855f7;--ok:#22c55e;--accent:#38bdf8;}
 *{box-sizing:border-box}
 body{margin:0;background:var(--bg);color:var(--ink);
   font:14px/1.45 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif}
 header{padding:12px 18px;border-bottom:1px solid var(--line);background:var(--panel)}
 header h1{margin:0 0 4px;font-size:15px;font-weight:600}
 header .task{color:var(--mut);font-size:12.5px;max-width:1100px}
 header .chips{margin-top:7px;display:flex;gap:8px;flex-wrap:wrap}
 .chip{background:#0e141c;border:1px solid var(--line);border-radius:20px;
   padding:2px 10px;font-size:11.5px;color:var(--mut)}
 .chip b{color:var(--ink)}
 .chip.ok b{color:var(--ok)}
 main{display:grid;grid-template-columns:minmax(360px,0.9fr) 1.3fr;gap:14px;padding:14px 18px}
 .card{background:var(--panel);border:1px solid var(--line);border-radius:10px;overflow:hidden}
 .card h2{margin:0;padding:9px 12px;font-size:12px;font-weight:600;color:var(--mut);
   border-bottom:1px solid var(--line);text-transform:uppercase;letter-spacing:.04em}
 #dagWrap{position:relative}
 svg{display:block;width:100%;height:auto}
 .edge{stroke:#3a4552;stroke-width:1.6;fill:none;marker-end:url(#arr)}
 .edge.state{stroke:var(--branch);stroke-width:3;marker-end:url(#arrb)}
 .node rect{stroke-width:2;rx:8;cursor:pointer}
 .node text{fill:var(--ink);font-size:11px;pointer-events:none}
 .node .sub{fill:var(--mut);font-size:9.5px}
 .legend{display:flex;gap:14px;padding:8px 12px;font-size:11px;color:var(--mut);flex-wrap:wrap;
   border-top:1px solid var(--line)}
 .legend i{display:inline-block;width:11px;height:11px;border-radius:3px;margin-right:4px;vertical-align:-1px}
 /* video wall */
 #wall{display:grid;gap:8px;padding:10px}
 .screen{background:#0b0f14;border:1px solid var(--line);border-radius:8px;overflow:hidden;position:relative}
 .screen.pin{outline:2px solid var(--accent)}
 .screen .bar{display:flex;justify-content:space-between;align-items:center;gap:6px;
   padding:5px 8px;font-size:11px;border-bottom:1px solid var(--line)}
 .screen .bar .id{font-weight:600}
 .screen .bar .id .dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:5px;vertical-align:0}
 .screen img{width:100%;display:block;background:#000;aspect-ratio:16/9;object-fit:cover}
 .screen .cap{padding:6px 8px;font-size:10.5px;color:var(--mut);min-height:34px}
 .screen .cap code{color:#9fe6ff;font-size:10px}
 .txtnode{padding:12px;font-size:12px;color:var(--mut)}
 /* controls + gantt */
 #ctl{grid-column:1/3;background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:10px 14px}
 .row{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
 button{background:#1f2937;color:var(--ink);border:1px solid var(--line);border-radius:7px;
   padding:6px 12px;font-size:13px;cursor:pointer}
 button:hover{background:#273244}
 button.primary{background:var(--accent);color:#04222e;border-color:var(--accent);font-weight:600}
 select{background:#1f2937;color:var(--ink);border:1px solid var(--line);border-radius:7px;padding:5px 8px}
 .clock{font-variant-numeric:tabular-nums;color:var(--mut);font-size:12px}
 #gantt{margin-top:10px;position:relative}
 .lane{display:grid;grid-template-columns:150px 1fr;align-items:center;height:26px;gap:8px}
 .lane .nm{font-size:11px;color:var(--mut);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;cursor:pointer}
 .track{position:relative;height:15px;background:#0d1219;border-radius:7px;overflow:hidden}
 .barfill{position:absolute;top:0;height:100%;border-radius:7px;opacity:.85}
 .barprog{position:absolute;top:0;height:100%;border-radius:7px;opacity:1}
 #playhead{position:absolute;top:0;bottom:0;width:2px;background:var(--accent);pointer-events:none}
 #scrub{position:absolute;left:150px;right:0;top:0;bottom:0;cursor:pointer}
</style></head>
<body>
<header>
 <h1 id="ttl">Spine-Branch</h1>
 <div class="task" id="ttxt"></div>
 <div class="chips" id="chips"></div>
</header>
<main>
 <section class="card">
   <h2>Coordination graph</h2>
   <div id="dagWrap"><svg id="dag" viewBox="0 0 100 100"></svg></div>
   <div class="legend">
     <span><i style="background:var(--branch)"></i>Branch (info-gatherer, VM discarded)</span>
     <span><i style="background:var(--spine)"></i>Spine (state-carrying, owns deliverable)</span>
     <span><i style="background:var(--mgr)"></i>Manager (aggregate)</span>
     <span><i style="background:var(--branch);height:3px;border-radius:0"></i>state inheritance</span>
     <span><i style="background:#3a4552;height:3px;border-radius:0"></i>artifact flow</span>
   </div>
 </section>
 <section class="card">
   <h2 id="wallh">Agents running in parallel</h2>
   <div id="wall"></div>
 </section>
 <section id="ctl">
   <div class="row">
     <button id="pp" class="primary">▶ Play</button>
     <button id="rs">⟲ Restart</button>
     <label class="clock">speed
       <select id="spd"><option>0.5</option><option selected>1</option><option>2</option><option>4</option><option>8</option></select>×</label>
     <label class="clock"><input type="checkbox" id="follow" checked> follow active</label>
     <span class="clock" id="clk">0s / 0s</span>
   </div>
   <div id="gantt"></div>
 </section>
</main>
<script>
const DATA = /*__DATA__*/;
const M=DATA.meta, NODES=DATA.nodes, FR=DATA.frames;
const COL={branch:getcss('--branch'),spine:getcss('--spine'),manager:getcss('--mgr')};
function getcss(v){return getComputedStyle(document.documentElement).getPropertyValue(v).trim();}
function roleColor(n){return n.agent_type==='manager'?COL.manager:(n.role==='spine'?COL.spine:COL.branch);}
const TEND=Math.max(...NODES.map(n=>n.end),1);
let now=0, playing=false, speed=1, pinned=null, follow=true, last=null;

// header
document.getElementById('ttl').textContent='Spine-Branch — '+(M.website||M.task_id);
document.getElementById('ttxt').textContent=M.task_text||'';
const chips=[['backbone',M.backbone],['nodes',NODES.length],
  ['spine',NODES.filter(n=>n.role==='spine').length],
  ['branches',NODES.filter(n=>n.role==='branch'&&n.agent_type!=='manager').length],
  ['replans',M.replans]];
let ch=chips.map(c=>`<span class="chip"><b>${c[1]}</b> ${c[0]}</span>`).join('');
if(M.score!=null){const pf=M.perfect;ch+=`<span class="chip ${pf?'ok':''}"><b>${(M.score*100).toFixed(0)}%</b> rubric${pf?' ✓':''}</span>`;}
document.getElementById('chips').innerHTML=ch;

// ---- DAG layout ----
const maxLayer=Math.max(...NODES.map(n=>n.layer));
const byLayer={}; NODES.forEach(n=>{(byLayer[n.layer]=byLayer[n.layer]||[]).push(n);});
const NW=150,NH=46,GX=54,GY=20, PAD=16;
let maxRows=Math.max(...Object.values(byLayer).map(a=>a.length));
const W=PAD*2+(maxLayer+1)*NW+maxLayer*GX;
const H=PAD*2+maxRows*NH+(maxRows-1)*GY;
const pos={};
Object.keys(byLayer).forEach(l=>{
  const arr=byLayer[l]; const totalH=arr.length*NH+(arr.length-1)*GY;
  arr.forEach((n,i)=>{pos[n.id]={x:PAD+l*(NW+GX), y:(H-totalH)/2+i*(NH+GY)};});
});
const svg=document.getElementById('dag');
svg.setAttribute('viewBox',`0 0 ${W} ${H}`);
let s=`<defs>
 <marker id="arr" markerWidth="7" markerHeight="7" refX="6" refY="3" orient="auto"><path d="M0,0L6,3L0,6z" fill="#3a4552"/></marker>
 <marker id="arrb" markerWidth="7" markerHeight="7" refX="6" refY="3" orient="auto"><path d="M0,0L6,3L0,6z" fill="${COL.branch}"/></marker></defs>`;
// edges
NODES.forEach(n=>{
  (n.deps||[]).forEach(d=>{
    if(!pos[d])return;
    const a=pos[d],b=pos[n.id];
    const x1=a.x+NW,y1=a.y+NH/2,x2=b.x,y2=b.y+NH/2;
    const mx=(x1+x2)/2;
    const st=(n.init_from===d)?'edge state':'edge';
    s+=`<path class="${st}" d="M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}"/>`;
  });
});
// nodes
NODES.forEach(n=>{
  const p=pos[n.id],c=roleColor(n);
  s+=`<g class="node" data-id="${n.id}" transform="translate(${p.x},${p.y})">
    <rect id="rect_${cid(n.id)}" width="${NW}" height="${NH}" fill="#111722" stroke="${c}"/>
    <circle id="dot_${cid(n.id)}" cx="13" cy="14" r="5" fill="#33404f"/>
    <text x="24" y="17" font-weight="600">${trim(n.id,20)}</text>
    <text class="sub" x="10" y="34">${n.agent_type==='manager'?'manager · aggregate':n.role+' · '+n.nframes+' steps'}</text>
  </g>`;
});
svg.innerHTML=s;
svg.querySelectorAll('.node').forEach(g=>g.addEventListener('click',()=>{
  const id=g.getAttribute('data-id'); pinned=(pinned===id?null:id);
  document.getElementById('follow').checked=false; follow=false; render();
}));
function cid(x){return x.replace(/[^a-zA-Z0-9_]/g,'_');}
function trim(x,n){return x.length>n?x.slice(0,n-1)+'…':x;}

// ---- Gantt ----
const g=document.getElementById('gantt');
let gh='';
const order=[...NODES].sort((a,b)=>a.start-b.start||a.layer-b.layer);
order.forEach(n=>{
  const c=roleColor(n);
  const L=(n.start/TEND*100), Wd=(Math.max(n.dur,0.5)/TEND*100);
  gh+=`<div class="lane"><div class="nm" data-id="${n.id}" style="color:${c}">${trim(n.id,20)}</div>
    <div class="track"><div class="barfill" style="left:${L}%;width:${Wd}%;background:${c};opacity:.3"></div>
    <div class="barprog" id="prog_${cid(n.id)}" style="left:${L}%;width:0;background:${c}"></div></div></div>`;
});
gh+=`<div id="playhead" style="left:150px"></div><div id="scrub"></div>`;
g.innerHTML=gh;
g.querySelectorAll('.nm').forEach(e=>e.addEventListener('click',()=>{
  pinned=e.getAttribute('data-id');document.getElementById('follow').checked=false;follow=false;render();}));
const scrub=document.getElementById('scrub');
function scrubTo(ev){const r=scrub.getBoundingClientRect();
  now=Math.max(0,Math.min(1,(ev.clientX-r.left)/r.width))*TEND;render();}
let dragging=false;
scrub.addEventListener('mousedown',e=>{dragging=true;pause();scrubTo(e);});
window.addEventListener('mousemove',e=>{if(dragging)scrubTo(e);});
window.addEventListener('mouseup',()=>dragging=false);

// ---- state of a node at time `now` ----
function nodeState(n){
  if(now<n.start)return{st:'pending',fi:-1,prog:0};
  const fr=FR[n.id]||[];
  if(now>=n.end)return{st:'done',fi:fr.length-1,prog:1};
  const prog=n.dur>0?(now-n.start)/n.dur:1;
  return{st:'running',fi:Math.min(fr.length-1,Math.floor(prog*fr.length)),prog};
}
// ---- render ----
const wall=document.getElementById('wall');
function render(){
  // dag node states
  NODES.forEach(n=>{
    const s=nodeState(n),c=roleColor(n);
    const dot=document.getElementById('dot_'+cid(n.id));
    const rect=document.getElementById('rect_'+cid(n.id));
    if(dot){dot.setAttribute('fill', s.st==='done'?getcss('--ok'):s.st==='running'?c:'#33404f');}
    if(rect){rect.setAttribute('fill', s.st==='running'?'#1b2536':'#111722');
      rect.style.filter = s.st==='running'?`drop-shadow(0 0 6px ${c})`:'none';}
    const pr=document.getElementById('prog_'+cid(n.id));
    if(pr)pr.style.width=(Math.max(n.dur,0.5)/TEND*100*Math.min(1,s.prog||0))+'%';
  });
  // playhead
  const ph=document.getElementById('playhead');
  const tr=scrub.getBoundingClientRect();
  ph.style.left=(150+(now/TEND)*tr.width)+'px';
  document.getElementById('clk').textContent=`${now.toFixed(0)}s / ${TEND.toFixed(0)}s`;
  // wall: which nodes to show
  let show;
  if(pinned){show=[NODES.find(n=>n.id===pinned)];}
  else{show=NODES.filter(n=>nodeState(n).st==='running');  // include text/manager nodes
    if(!show.length){ // between phases: show last-finished agent with frames
      const cand=NODES.filter(n=>nodeState(n).st==='done'&&(FR[n.id]||[]).length);
      show=cand.length?[cand.sort((a,b)=>b.end-a.end)[0]]:[NODES[0]];}}
  document.getElementById('wallh').textContent = pinned? 'Focused: '+pinned :
     (show.length>1? show.length+' agents running in parallel':'Agent view');
  const cols=pinned?1:Math.min(4,Math.ceil(Math.sqrt(show.length)));
  wall.style.gridTemplateColumns=`repeat(${cols},1fr)`;
  wall.innerHTML=show.map(n=>{
    const fr=FR[n.id]||[], stt=nodeState(n), f=fr[Math.max(0,stt.fi)];
    const c=roleColor(n);
    if(!f){return `<div class="screen"><div class="bar"><span class="id">
      <span class="dot" style="background:${c}"></span>${n.id}</span><span>${n.role}</span></div>
      <div class="txtnode">${n.agent_type==='manager'?'Manager aggregates branch results into the final answer.<br><br>'+(M.final_response||''):(n.desc||'')}</div></div>`;}
    const badge=stt.st==='done'?'✓ done':'step '+f.s+'/'+f.t;
    return `<div class="screen ${pinned===n.id?'pin':''}">
      <div class="bar"><span class="id"><span class="dot" style="background:${c}"></span>${trim(n.id,26)}</span>
        <span style="color:${c}">${n.role} · ${badge}</span></div>
      <img src="${f.img}">
      <div class="cap"><code>${esc(f.a||'')}</code><br>${esc(trim(f.r||'',150))}</div></div>`;
  }).join('');
}
function esc(x){return (x||'').replace(/[&<>]/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[m]));}

// ---- playback loop ----
let raf=null,tprev=0;
function tick(ts){
  if(!playing)return;
  if(!tprev)tprev=ts;
  now+=(ts-tprev)/1000*speed; tprev=ts;
  if(now>=TEND){now=TEND;pause();}
  render(); if(playing)raf=requestAnimationFrame(tick);
}
function play(){if(now>=TEND)now=0;playing=true;tprev=0;
  document.getElementById('pp').textContent='❚❚ Pause';raf=requestAnimationFrame(tick);}
function pause(){playing=false;document.getElementById('pp').textContent='▶ Play';}
document.getElementById('pp').onclick=()=>playing?pause():play();
document.getElementById('rs').onclick=()=>{now=0;pause();render();};
document.getElementById('spd').onchange=e=>speed=parseFloat(e.target.value);
document.getElementById('follow').onchange=e=>{follow=e.target.checked;if(follow)pinned=null;render();};
window.addEventListener('resize',render);
render();
</script>
</body></html>"""


FRAMEWORK_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>Spine-Branch Framework Demo</title>
<style>
 :root{--bg:#ffffff;--ink:#1e2330;--mut:#5b6472;--spineclr:#3b3f9e;--spinedk:#2f3388;
   --branch:#4b52c4;--fill:#c9cdf2;--fillspine:#3b3f9e;--orange:#ec6a2c;--ok:#22a06b;--line:#3b3f9e;}
 *{box-sizing:border-box}
 body{margin:0;background:var(--bg);color:var(--ink);
   font:14px/1.4 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif}
 header{padding:20px 24px 12px}
 header .taskbox{position:relative;max-width:1180px;margin:0 auto;
   padding:16px 24px 16px 52px;border-radius:16px;overflow:hidden;
   background:linear-gradient(135deg,#f7f8ff 0%,#eef0fc 100%);
   border:1px solid #d3d7f4;box-shadow:0 6px 22px rgba(40,44,120,.10),inset 0 1px 0 rgba(255,255,255,.7)}
 header .taskbox::before{content:"\1F4CB";position:absolute;left:18px;top:16px;font-size:19px;opacity:.85}
 header .taskbox::after{content:"";position:absolute;left:0;top:12px;bottom:12px;width:5px;
   border-radius:5px;background:linear-gradient(180deg,var(--spinedk),var(--branch))}
 header .task{color:#2b2f66;font-size:18px;line-height:1.5;font-weight:500}
 header .chips{margin-top:6px;display:flex;gap:7px;flex-wrap:wrap}
 .chip{background:#f0f1fb;border:1px solid #d7daf5;border-radius:20px;padding:2px 10px;font-size:11.5px;color:var(--mut)}
 .chip b{color:var(--spinedk)} .chip.ok b{color:var(--ok)}
 #stage{position:relative;overflow-x:auto;overflow-y:hidden;padding:0 10px}
 #scene{position:relative;margin:0 auto}
 svg.wires{position:absolute;left:0;top:0;pointer-events:none;overflow:visible}
 /* monitor */
 .mon{position:absolute;border-radius:13px;background:#fff;border:2px solid #9aa0e6;
   box-shadow:0 4px 12px rgba(40,44,120,.10);overflow:hidden;
   transition:box-shadow .3s,opacity .4s,filter .3s,transform .3s,border-color .3s}
 .mon.branch{border-style:dashed}
 .mon.spine{border-style:solid;border-color:var(--spinedk);border-width:2.5px}
 .mon.pending{opacity:.5;filter:grayscale(.5)}
 .mon.active{border-color:var(--branch);transform:translateY(-2px);
   box-shadow:0 0 0 3px rgba(75,82,196,.28),0 12px 26px rgba(40,44,120,.28)}
 .mon.active.spine{border-color:var(--spinedk);
   box-shadow:0 0 0 3px rgba(47,51,136,.38),0 14px 30px rgba(40,44,120,.36)}
 .mon.done{border-color:#7fc7a4}
 .mon.discarded{opacity:.28;filter:grayscale(.92);transform:scale(.93);
   border-style:dotted!important;border-color:#c3c7db!important;box-shadow:none!important}
 .mon.discarded .lbl{background:#f2f3f7;border-color:#e3e4ed}
 .mon.discarded .st{color:#9aa0b4;font-weight:600}
 .mon .lbl{font-size:10.5px;font-weight:700;color:var(--spinedk);padding:5px 9px;
   display:flex;align-items:center;gap:7px;background:linear-gradient(#f8f9ff,#eef0fb);
   border-bottom:1px solid #e5e7f7}
 .mon.spine .lbl{background:linear-gradient(#eef0fb,#e1e4f7)}
 .mon .dots{display:flex;gap:3.5px;flex:0 0 auto}
 .mon .dots i{width:7px;height:7px;border-radius:50%;display:block}
 .mon .nm{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;letter-spacing:.01em}
 .mon .st{font-weight:600;color:var(--mut);font-size:9.5px;flex:0 0 auto}
 .mon.done .st{color:var(--ok)}
 .mon .scr{width:100%;background:#0b0f14;aspect-ratio:16/10;object-fit:cover;object-position:top;display:block}
 .mon .empty{display:flex;align-items:center;justify-content:center;height:100%;padding:9px;
   font-size:10px;color:var(--mut);text-align:center;line-height:1.35}
 .caption{position:absolute;font-size:9.5px;color:var(--mut);width:170px;line-height:1.3}
 .role-tag{position:absolute;font-size:10px;font-weight:700;color:var(--spinedk);text-align:center;width:220px;
   letter-spacing:.05em;text-transform:uppercase;opacity:.8}
 .role-tag.branch{color:var(--branch)}
 /* artifact chip that travels branch -> spine on completion */
 .artifact{position:absolute;transform:translate(-50%,-50%);z-index:6;display:none;align-items:center;gap:4px;
   background:#fff;border:1.5px solid var(--branch);border-radius:20px;padding:2px 9px 2px 7px;
   font-size:10px;font-weight:700;color:var(--spinedk);white-space:nowrap;
   box-shadow:0 3px 10px rgba(75,82,196,.35)}
 .artifact .doc{flex:0 0 auto;display:block}
 .artifact.dock{border-color:var(--ok);color:var(--ok);box-shadow:0 0 0 3px rgba(34,160,107,.18)}
 .artifact.dock .doc path{stroke:var(--ok)!important}
 /* manager */
 .mgr{position:absolute;border:2.5px solid var(--spinedk);border-radius:13px;
   background:linear-gradient(#ffffff,#f3f4fe);
   display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:8px;
   box-shadow:0 4px 12px rgba(40,44,120,.12);transition:box-shadow .25s,transform .25s}
 .mgr.active{transform:translateY(-2px);box-shadow:0 0 0 3px rgba(47,51,136,.30),0 12px 26px rgba(40,44,120,.30)}
 .mgr b{color:var(--spinedk);font-size:13.5px} .mgr i{color:var(--mut);font-size:11px;margin-top:3px}
 /* controls */
 #ctl{position:sticky;bottom:0;background:rgba(255,255,255,.96);border-top:1px solid #e2e4f2;
   padding:9px 20px;display:flex;align-items:center;gap:14px;flex-wrap:wrap;backdrop-filter:blur(4px)}
 button{background:var(--spinedk);color:#fff;border:none;border-radius:7px;padding:7px 14px;font-size:13px;cursor:pointer;font-weight:600}
 button.sec{background:#eceefb;color:var(--spinedk)} button:hover{filter:brightness(1.08)}
 select{border:1px solid #ccd;border-radius:6px;padding:5px 7px}
 #track{position:relative;flex:1;min-width:220px;height:16px;background:#e9ebf7;border-radius:8px;cursor:pointer}
 #trackfill{position:absolute;left:0;top:0;bottom:0;background:var(--orange);border-radius:8px;width:0}
 .clock{font-variant-numeric:tabular-nums;color:var(--mut);font-size:12px;min-width:92px}
 .legend{display:flex;gap:16px;font-size:11px;color:var(--mut);padding:2px 20px 8px;flex-wrap:wrap}
 .legend b{color:var(--spinedk)}
 .swatch{display:inline-block;width:24px;height:0;border-top:3px solid var(--spinedk);vertical-align:3px;margin-right:4px}
 .swatch.dash{border-top-style:dashed;border-color:var(--branch)}
 .swatch.orange{border-color:var(--orange)}
 .swatch.spawn{border-color:#767bb0;border-top-width:5px}
</style></head>
<body>
<header>
 <div class="taskbox"><div class="task" id="ttxt"></div></div>
</header>
<div id="stage"><div id="scene"><svg class="wires" id="wires"></svg></div></div>
<div id="ctl">
 <button id="pp">▶ Play</button>
 <button id="rs" class="sec">⟲ Restart</button>
 <label class="clock">speed <select id="spd"><option>0.5</option><option selected>1</option><option>2</option><option>4</option><option>8</option></select>×</label>
 <div id="track"><div id="trackfill"></div></div>
 <span class="clock" id="clk">0s / 0s</span>
</div>
<script>
const DATA = /*__DATA__*/;
const M=DATA.meta, NODES=DATA.nodes, FR=DATA.frames;
NODES.forEach(n=>n.isMgr=(n.agent_type==='manager'));
const TEND=Math.max(...NODES.map(n=>n.end),1);
const branches=NODES.filter(n=>!n.isMgr&&n.role!=='spine');
const spines=NODES.filter(n=>!n.isMgr&&n.role==='spine');
const mgr=NODES.find(n=>n.isMgr);
let now=0,playing=false,speed=1;

// header — task text only
document.getElementById('ttxt').textContent=M.task_text||'';
document.getElementById('ttxt').title=M.task_text||'';

// ---------- layout ----------
const BW=176,BH=132, SW=212,SH=158, ROWGAP=22, LPAD=60, RPAD=210, MGRW=150,MGRH=104;
const scene=document.getElementById('scene');
let SCW=Math.max(1700, LPAD+RPAD+ (spines.length+1)*(SW+110));
function xOf(t,w){return LPAD+(t/TEND)*(SCW-LPAD-RPAD-w);}
const VGAP=(M.v_gap||34);                     // vertical gap between spine band and branch rows
const HG=78;                                  // horizontal gap between columns (room for return + next spawn)
// COLUMNS by distinct START time: subtasks that run in parallel share a column and thus align
// vertically (spine on the band, its concurrent branches stacked directly above / below it).
const starts=[...new Set(NODES.filter(n=>!n.isMgr).map(n=>n.start))].sort((a,b)=>a-b);
const colOf={}; starts.forEach((s,i)=>colOf[s]=i);
const cols=starts.map(s=>({start:s,spine:null,branches:[]}));
NODES.filter(n=>!n.isMgr).forEach(n=>{ const c=cols[colOf[n.start]]; if(n.role==='spine') c.spine=n; else c.branches.push(n); });
cols.forEach(c=>c.branches.sort((a,b)=>a.end-b.end).forEach((n,j)=>{ n._side=(j%2?'dn':'up'); n._stk=(j>>1); }));
const halfW=c=>((c&&c.spine?SW:BW)/2);
cols.forEach((c,i)=>{ c.x = i===0 ? Math.round(LPAD+halfW(c))
                                  : Math.round(cols[i-1].x+halfW(cols[i-1])+HG+halfW(c)); });
if(mgr){ const last=cols[cols.length-1]; mgr._x=Math.round((last?last.x+halfW(last):LPAD)+130); mgr._w=MGRW; mgr._h=MGRH; }
SCW=(mgr?mgr._x+MGRW+30:(cols.length?cols[cols.length-1].x+halfW(cols[cols.length-1])+40:900));
let nTop=0,nBot=0;
cols.forEach(c=>c.branches.forEach(n=>{ if(n._side==='up')nTop=Math.max(nTop,n._stk+1); else nBot=Math.max(nBot,n._stk+1); }));
const topH=nTop*(BH+ROWGAP), botH=nBot*(BH+ROWGAP);
const TOPM=(nTop>0)?Math.max(24,VGAP-10):34;   // tight top margin when there is no upper branch row
const CAP=44;                                  // room for the "Spine Worker" caption under the band
const spineY = topH + TOPM + SH/2;
// only reserve the lower branch row (and its gap) when branches actually sit below the spine
const SCH = topH + TOPM + SH + (nBot>0 ? VGAP+botH+30 : CAP);
scene.style.width=SCW+'px'; scene.style.height=SCH+'px';
spines.forEach(n=>{ n._x=cols[colOf[n.start]].x-SW/2; n._y=spineY-SH/2; n._w=SW; n._h=SH; });
if(mgr) mgr._y=spineY-MGRH/2;
branches.forEach(n=>{ const c=cols[colOf[n.start]]; n._cx=c.x; n._hasSpine=!!c.spine; n._x=c.x-BW/2; n._w=BW; n._h=BH;
  n._y=(n._side==='up')? spineY-SH/2-VGAP-(n._stk+1)*BH-n._stk*ROWGAP
                       : spineY+SH/2+VGAP+n._stk*(BH+ROWGAP); });
// Lifecycle is TIME-based (VMs with the same start light up together = true parallelism).
// The orange bar IS the timeline: it glides smoothly and reaches a column's connector x EXACTLY at
// that column's start time, so it's never ahead of a not-yet-started VM, yet moves continuously.
const RET=Math.max(45,TEND*0.06);        // real-time budget for an artifact to return to the spine
// playback runs a touch past TEND so the LAST branch's artifact can finish docking
// (a branch ending within RET of TEND would otherwise freeze mid-flight on the held final frame)
const RETEND=branches.reduce((m,n)=>Math.max(m,n.end+RET),TEND)+RET*0.02;
// The orange bar trails COMPLETION: it reaches a column's connector x only once EVERY node in
// that column has finished, so anything behind the bar is guaranteed done (running nodes stay ahead).
const colEnd=cols.map((c,i)=>{ let e=c.start;
  NODES.forEach(n=>{ if(!n.isMgr && colOf[n.start]===i) e=Math.max(e,n.end); }); return e; });
const anchors=cols.map((c,i)=>[colEnd[i], c.x]);
anchors.unshift([0, LPAD-34]);
anchors.push([TEND,(mgr?mgr._x-6:SCW-40)]);
anchors.sort((a,b)=>a[0]-b[0]);
for(let i=1;i<anchors.length;i++) anchors[i][1]=Math.max(anchors[i][1],anchors[i-1][1]);
function frontX(t){ for(let i=1;i<anchors.length;i++){ const a=anchors[i-1],b=anchors[i];
  if(t<=b[0]) return a[1]+(b[0]>a[0]?(t-a[0])/(b[0]-a[0]):1)*(b[1]-a[1]); }
  return anchors[anchors.length-1][1]; }
const nodeById={}; NODES.forEach(n=>nodeById[n.id]=n);

// ---------- SVG wires ----------
const svg=document.getElementById('wires');
svg.setAttribute('width',SCW); svg.setAttribute('height',SCH);
const bandTop=spineY-20, bandBot=spineY+20;
let s=`<defs>
 <marker id="ah" markerWidth="9" markerHeight="9" refX="7" refY="4.5" orient="auto"><path d="M0,0L8,4.5L0,9z" fill="#2f3388"/></marker>
 <marker id="ahg" markerUnits="userSpaceOnUse" markerWidth="18" markerHeight="18" refX="14" refY="9" orient="auto"><path d="M0,1L15,9L0,17z" fill="#767bb0"/></marker>
 <marker id="ahd" markerWidth="8" markerHeight="8" refX="6.5" refY="4" orient="auto"><path d="M0,0L7,4L0,8z" fill="#4b52c4"/></marker>
 <marker id="aho" markerWidth="10" markerHeight="10" refX="7" refY="5" orient="auto"><path d="M0,0L9,5L0,10z" fill="#ec6a2c"/></marker>
 <linearGradient id="spineg" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#454ab0"/><stop offset="0.5" stop-color="#3b3f9e"/><stop offset="1" stop-color="#2e3286"/></linearGradient>
 <filter id="soft" x="-20%" y="-60%" width="140%" height="220%"><feDropShadow dx="0" dy="3" stdDeviation="5" flood-color="#2f3388" flood-opacity="0.22"/></filter></defs>`;
// spine band (big arrow) left -> manager
const bandR = mgr? mgr._x-6 : SCW-40;
// solid flat indigo block-arrow with a bold head, exactly like framework.png
const bandPath=`M${LPAD-34},${bandTop} L${bandR-24},${bandTop} L${bandR-24},${spineY-34} L${bandR+14},${spineY} L${bandR-24},${spineY+34} L${bandR-24},${bandBot} L${LPAD-34},${bandBot} Z`;
s+=`<path d="${bandPath}" fill="#3b3f9e"/>`;
// "Persistent VM State" — plain bold white label on the band, exactly like framework.png
let _lo=LPAD-30,_hi=bandR-46,_bw=0; const _sm2=[...spines].sort((a,b)=>a._x-b._x);
for(let i=0;i<=_sm2.length;i++){ const lo=(i===0?LPAD-30:_sm2[i-1]._x+SW), hi=(i<_sm2.length?_sm2[i]._x:bandR-46);
  if(hi-lo>_bw){_bw=hi-lo;_lo=lo;_hi=hi;} }
const _lcx=(_lo+_hi)/2;                     // center of widest clear stretch
const _tl=Math.min(150, Math.max(72,_bw-26));  // fit the label within the clear gap (never overrun a spine VM)
for(let cx=LPAD+16; cx<bandR-70; cx+=112){ if(Math.abs(cx-_lcx)<_tl/2+34) continue;
  s+=`<text x="${cx}" y="${spineY+5}" fill="#b3b7e6" font-size="16" font-weight="800" opacity=".55">&#8250;&#8250;&#8250;</text>`;}
s+=`<text x="${_lcx}" y="${spineY+5}" text-anchor="middle" textLength="${_tl}" lengthAdjust="spacingAndGlyphs" fill="#fff" font-size="15" font-weight="700">Persistent VM State</text>`;
// progress overlay on band (fills with playhead)
s+=`<clipPath id="bandclip"><path d="${bandPath}"/></clipPath>
 <rect id="bandprog" x="${LPAD-34}" y="${bandTop}" width="0" height="${bandBot-bandTop}" fill="#ec6a2c" opacity=".22" clip-path="url(#bandclip)"/>`;
// connectors: STRAIGHT VERTICALS in the gap under each branch — spawn on the left,
// artifact-return on the right. Zero bends; each sits in a clear inter-VM gap.
// single-bend (L) connectors with SHARP 90° corners — matching framework.png
function elbowV(sx,sy,tx,ty){ return `M${sx},${sy} L${sx},${ty} L${tx},${ty}`; }   // vertical then horizontal
function elbowH(sx,sy,tx,ty){ return `M${sx},${sy} L${tx},${sy} L${tx},${ty}`; }   // horizontal then vertical
branches.forEach(n=>{
  const isTop=n._side==='up', cx=(n._cx!=null?n._cx:n._x+BW/2), half=n._hasSpine?SW/2:BW/2;
  const midY=n._y+BH/2, bandEdge=isTop?bandTop:bandBot;
  // SPAWN (thick gray, sharp one bend, big head): rises from the SPINE (band) then turns into the branch's side
  const ox=Math.round(cx-half-18);
  s+=`<path id="spawn_${cid(n.id)}" d="${elbowV(ox,bandEdge,n._x,midY)}" stroke="#767bb0" stroke-width="6" fill="none" stroke-linejoin="miter" marker-end="url(#ahg)" opacity=".95"/>`;
  // RETURN (blue dashed, sharp one bend): leaves the branch's right side then turns into the spine (band)
  const rx=Math.round(cx+half+18);
  s+=`<path id="deliv_${cid(n.id)}" class="deliv" d="${elbowH(n._x+BW,midY,rx,bandEdge)}" stroke="#5a61d6" stroke-width="2" fill="none" stroke-dasharray="1 7" stroke-linecap="round" stroke-linejoin="miter" marker-end="url(#ahd)" opacity=".45"/>`;
});
svg.innerHTML=s;
function cid(x){return x.replace(/[^a-zA-Z0-9_]/g,'_');}

// ---------- monitor DOM ----------
function mk(n){
  const d=document.createElement('div');
  d.className='mon '+(n.role==='spine'?'spine':'branch');
  d.style.left=n._x+'px'; d.style.top=n._y+'px'; d.style.width=n._w+'px'; d.style.height=n._h+'px';
  d.id='mon_'+cid(n.id);
  d.innerHTML=`<div class="lbl"><span class="dots"><i style="background:#ff5f57"></i><i style="background:#febc2e"></i><i style="background:#28c840"></i></span><span class="nm">${trim(n.id,n.role==='spine'?24:18)}</span><span class="st"></span></div>
    ${(FR[n.id]||[]).length?`<img class="scr" id="scr_${cid(n.id)}">`:`<div class="empty">${esc(n.desc||'')}</div>`}`;
  d.onclick=()=>{pinned=(pinned===n.id?null:n.id);render();};
  scene.appendChild(d);
  // role tag under spine workers
  if(n.role==='spine'){const t=document.createElement('div');t.className='role-tag';
    t.textContent='Spine Worker';t.style.left=(n._x+n._w/2-110)+'px';t.style.top=(n._y+n._h+6)+'px';scene.appendChild(t);}
}
branches.concat(spines).forEach(mk);
let pinned=null;
if(mgr){const d=document.createElement('div');d.className='mgr';d.id='mgrbox';
  d.style.left=mgr._x+'px';d.style.top=mgr._y+'px';d.style.width=MGRW+'px';d.style.height=MGRH+'px';
  d.innerHTML=`<b>Manager</b><i>Aggregate final<br>deliverables</i>`;
  d.title=(M.final_response||''); scene.appendChild(d);}
function trim(x,n){return x.length>n?x.slice(0,n-1)+'…':x;}
function esc(x){return (x||'').replace(/[&<>]/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[m]));}
function smooth(p){p=Math.max(0,Math.min(1,p));return p*p*(3-2*p);}
function shortArt(n){let a=(n.art||'findings');return a.length>15?a.slice(0,14)+'…':a;}

// one travelling artifact chip per branch (a 📄 flies branch -> spine on completion)
const DOC='<svg class="doc" width="10" height="12" viewBox="0 0 10 12" fill="none"><path d="M1 1h5l3 3v7H1z" fill="#eef0fb" stroke="#3b3f9e" stroke-width="1.1"/><path d="M6 1v3h3" stroke="#3b3f9e" stroke-width="1.1"/></svg>';
const TRASH='<svg width="9" height="10" viewBox="0 0 10 11" fill="none" style="vertical-align:-1px;margin-right:2px"><path d="M1.4 2.6h7.2M3.4 2.6v-1h3.2v1M2.4 2.6l.5 7.4h4.2l.5-7.4" stroke="#9aa0b4" stroke-width="1"/></svg>';
const arts={};
branches.forEach(n=>{
  const path=document.getElementById('deliv_'+cid(n.id));
  const el=document.createElement('div'); el.className='artifact'; el.id='art_'+cid(n.id);
  el.innerHTML=DOC+'<span>'+esc(shortArt(n))+'</span>';
  scene.appendChild(el);
  let len=0; try{len=path?path.getTotalLength():0;}catch(e){}
  arts[n.id]={el,path,len};
});

// ---------- state + render ----------
function stateOf(n){
  if(now<n.start)return{st:'pending',fi:-1,p:0};   // parallel VMs share a start -> align
  const fr=FR[n.id]||[];
  if(now>=n.end)return{st:'done',fi:fr.length-1,p:1};
  const p=(now-n.start)/Math.max(1,n.end-n.start);
  return{st:'running',fi:Math.min(fr.length-1,Math.floor(p*fr.length)),p};
}
function render(){
  NODES.forEach(n=>{
    const el=document.getElementById('mon_'+cid(n.id)); if(!el&&!n.isMgr)return;
    const stt=stateOf(n);
    if(!n.isMgr){
      el.classList.toggle('pending',stt.st==='pending');
      el.classList.toggle('active',stt.st==='running'||pinned===n.id);
      el.classList.toggle('done',stt.st==='done');
      const st=el.querySelector('.st'); if(st)st.textContent= stt.st==='done'?'✓ done':stt.st==='running'?('step '+((FR[n.id]||[])[stt.fi]||{}).s+'/'+((FR[n.id]||[])[stt.fi]||{}).t):'';
      const img=document.getElementById('scr_'+cid(n.id));
      const f=(FR[n.id]||[])[Math.max(0,stt.fi)];
      if(img&&f&&img.src!==f.img)img.src=f.img;
    }
    // spawn + artifact return + discard — all keyed off the sweep state (stt), never raw time
    if(n.role!=='spine'&&!n.isMgr){
      const c=arts[n.id], dl=c&&c.path, sp=document.getElementById('spawn_'+cid(n.id));
      if(stt.st==='pending'){           // front not here yet: everything faint, no artifact
        if(dl){dl.setAttribute('opacity','.18'); dl.setAttribute('stroke-width','2');}
        if(sp)sp.setAttribute('opacity','.28');
        if(c)c.el.style.display='none';
      }else{                            // reached: line bright; artifact flies only once done
        if(dl){dl.setAttribute('opacity','.9'); dl.setAttribute('stroke-width','2.6');}
        if(sp)sp.setAttribute('opacity', stt.st==='running'?'.8':'.45');
        if(stt.st==='done'){
          const p=(now-n.end)/RET;
          if(c&&c.path&&c.len>0&&p>=0&&p<1){
            const pt=c.path.getPointAtLength(c.len*smooth(p));
            c.el.style.left=pt.x+'px'; c.el.style.top=pt.y+'px';
            c.el.style.display='flex'; c.el.classList.toggle('dock',p>0.8);
          }else if(c){c.el.style.display='none';}
        }else if(c){c.el.style.display='none';}
      }
      // discard only after the artifact has finished returning
      const discarded = now >= n.end + RET;
      el.classList.toggle('discarded', discarded);
      if(discarded){
        const st2=el.querySelector('.st'); if(st2)st2.innerHTML=TRASH+'VM discarded';
        if(dl)dl.setAttribute('opacity','.25');
      }
    }
  });
  if(mgr){const mb=document.getElementById('mgrbox');if(mb)mb.classList.toggle('active',now>=mgr.start);}
  // band progress + timeline
  const bp=document.getElementById('bandprog');
  if(bp){ bp.setAttribute('width', Math.max(0, frontX(now)-(LPAD-34))+''); }
  document.getElementById('trackfill').style.width=(Math.min(now,TEND)/TEND*100)+'%';
  document.getElementById('clk').textContent=`${Math.min(now,TEND).toFixed(0)}s / ${TEND.toFixed(0)}s`;
}

// ---------- playback ----------
let raf=null,tp=0;
function tick(ts){ if(!playing)return; if(!tp)tp=ts; now+=(ts-tp)/1000*speed*30; tp=ts;
  if(now>=RETEND){now=RETEND;pause();} render(); if(playing)raf=requestAnimationFrame(tick); }
function play(){if(now>=RETEND)now=0;playing=true;tp=0;document.getElementById('pp').textContent='❚❚ Pause';raf=requestAnimationFrame(tick);}
function pause(){playing=false;document.getElementById('pp').textContent='▶ Play';}
document.getElementById('pp').onclick=()=>playing?pause():play();
document.getElementById('rs').onclick=()=>{now=0;pause();render();};
document.getElementById('spd').onchange=e=>speed=parseFloat(e.target.value);
const track=document.getElementById('track');
function seek(e){const r=track.getBoundingClientRect();now=Math.max(0,Math.min(1,(e.clientX-r.left)/r.width))*RETEND;render();}
let drag=false;
track.addEventListener('mousedown',e=>{drag=true;pause();seek(e);});
window.addEventListener('mousemove',e=>{if(drag)seek(e);});
window.addEventListener('mouseup',()=>drag=false);
// external hooks for video capture
window.__seek=function(f){pause();now=Math.max(0,Math.min(1,f))*RETEND;render();};
window.__sceneSize=function(){return {w:SCW,h:SCH};};
render();
</script>
</body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("task_id")
    ap.add_argument("-o", "--out", default=None)
    ap.add_argument("--width", type=int, default=880)
    ap.add_argument("--quality", type=int, default=72)
    ap.add_argument("--max-frames-per-node", type=int, default=28)
    ap.add_argument("--style", choices=["framework", "dashboard"], default="framework",
                    help="framework = animated spine-branch figure (default); dashboard = DAG + video wall")
    ap.add_argument("--v-gap", type=int, default=34,
                    help="framework: vertical gap between the spine band and branch rows")
    ap.add_argument("--hide-task", action="store_true",
                    help="omit the baked-in task-description box (render the task text in the host page instead)")
    a = ap.parse_args()
    out = a.out or f"demo_{a.task_id[:10]}.html"
    build(a.run_dir, a.task_id, out, a.width, a.quality, a.max_frames_per_node, a.style, a.v_gap, a.hide_task)


if __name__ == "__main__":
    main()
