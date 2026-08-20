import os,json,openai,collections
from concurrent.futures import ThreadPoolExecutor
c=openai.OpenAI(base_url=os.environ["OPENAI_BASE_URL"],api_key=os.environ["OPENAI_API_KEY"])
tasks=json.load(open('data/webtailbench/webtailbench_test_v2.json'))

SYS=("You classify a web task by whether a MULTI-AGENT system could split it into PARALLEL subtasks with real benefit. "
"Apply this strict test. Output JSON only.\n"
"Fields:\n"
"structure: one of\n"
"  'parallel_decomposable' = has >=2 INDEPENDENT subgoals (no subgoal needs another's output) AND each subgoal is "
"self-contained/executable alone AND the merge is CHEAP (concatenate / compare / assemble a list). Multi-agent WIDTH helps.\n"
"  'sequential_multistep' = multiple steps but CHAINED (a step needs a prior step's result). Width does NOT help.\n"
"  'atomic' = a single flow: one lookup, one booking, one form, one page-read.\n"
"n_independent_subgoals: integer.\n"
"shared_site_state: true if the independent subgoals must act on the SAME live site session/cart/login (so they cannot "
"truly run on separate machines), else false.\n"
"one_line_reason: string (<=25 words).")

def classify(t):
    q=t['confirmed_task']
    for attempt in range(3):
        try:
            r=c.chat.completions.create(model="claude-opus-4-8",
                messages=[{"role":"system","content":SYS},{"role":"user","content":q}],
                max_tokens=250,response_format={"type":"json_object"})
            d=json.loads(r.choices[0].message.content)
            return (t['task_id'],t['benchmark'],d.get('structure'),d.get('n_independent_subgoals'),
                    d.get('shared_site_state'),d.get('one_line_reason',''))
        except Exception as e:
            if attempt==2: return (t['task_id'],t['benchmark'],'ERROR',None,None,str(e)[:80])
    return None

out=[]
with ThreadPoolExecutor(max_workers=10) as ex:
    for i,res in enumerate(ex.map(classify,tasks)):
        out.append(res)
        if (i+1)%100==0: print('...',i+1,flush=True)
json.dump(out,open('/tmp/wtb_structure.json','w'))
print('done',len(out))

struct=collections.Counter(o[2] for o in out)
print('\n=== STRUCTURE (n=%d) ==='%len(out))
for k,v in struct.most_common(): print(f'  {v:3d}  ({100*v/len(out):4.1f}%)  {k}')
dec=[o for o in out if o[2]=='parallel_decomposable']
print(f'\nparallel_decomposable with shared_site_state (VM single-parent conflict): {sum(1 for o in dec if o[4])}/{len(dec)}')
print(f'parallel_decomposable, data-only merge (spine-branch friendly): {sum(1 for o in dec if not o[4])}/{len(dec)}')
