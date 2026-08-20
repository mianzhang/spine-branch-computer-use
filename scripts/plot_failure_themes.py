import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
# emergent themes (opus bottom-up clustering of 48 non-perfect runs); share % ; family
themes=[
 ("Instruction-following failure",   29, "cua"),
 ("Anti-bot / CAPTCHA blocks",       25, "web"),
 ("Stops gathering early",           15, "cua"),
 ("Site unreachable",                10, "web"),
 ("Skipped / misexecuted steps",      8, "cua"),
 ("Wasted effort on wrong paths",     8, "cua"),
 ("Fabricated results",               6, "cua"),
]
themes=sorted(themes,key=lambda x:x[1])  # ascending for barh (largest on top)
labels=[t[0] for t in themes]; vals=[t[1] for t in themes]
C={"web":"#E39A3B","cua":"#4C78A8"}
colors=[C[t[2]] for t in themes]
plt.rcParams.update({"font.size":12,"font.family":"sans-serif","axes.spines.top":False,"axes.spines.right":False})
fig,ax=plt.subplots(figsize=(6.4,4.6))
bars=ax.barh(labels,vals,color=colors,edgecolor="white")
for b,v in zip(bars,vals):
    ax.text(v+0.5,b.get_y()+b.get_height()/2,f"{v}%",va="center",fontsize=10,color="#333")
ax.set_xlabel("Share of non-perfect runs (%)")
ax.set_xlim(0,34)
from matplotlib.patches import Patch
web=sum(v for _,v,f in [(t[0],t[1],t[2]) for t in themes] if f=="web")
cua=100-web
ax.legend(handles=[Patch(color=C["web"],label=f"Environment Block ({web}%)"),
                   Patch(color=C["cua"],label=f"CUA Incapability ({cua}%)")],
          loc="lower right",fontsize=10,frameon=False)
fig.tight_layout(); out="reports/failure_themes.png"
fig.savefig(out,dpi=160,bbox_inches="tight"); print("wrote",out,"web=",web,"cua=",cua)
