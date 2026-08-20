import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt, numpy as np
# odysseys45 macro rubric (%); x = single-agent success rate (capability, %)
labels=["Qwen3.6-27B","gpt-5.4-mini","Qwen3.7-Plus"]
cap   =np.array([31.1,44.4,62.2])
macu  =np.array([72.5,76.8,80.2])
spine =np.array([75.1,81.8,90.6])
o=np.argsort(cap); cap,macu,spine=cap[o],macu[o],spine[o]; labels=[labels[i] for i in o]
plt.rcParams.update({"font.size":13,"font.family":"sans-serif","axes.spines.top":False,"axes.spines.right":False,"axes.linewidth":0.8})
C_M="#E39A3B"; C_P="#2C8A46"
fig,ax=plt.subplots(figsize=(6.4,4.6))
ylo,yhi=macu.min()-4,spine.max()+6
# vertical guide line + label for each sub-agent backbone
for x,l in zip(cap,labels):
    ax.axvline(x,color="#7f8c9a",ls="--",lw=1.6,alpha=0.8,zorder=0)
    ax.annotate(l,(x,yhi),xytext=(0,-2),textcoords="offset points",
                fontsize=12,ha="center",va="top",color="#444")
ax.fill_between(cap,macu,spine,color=C_P,alpha=0.12,zorder=1)
ax.plot(cap,spine,'-o',color=C_P,lw=2.6,ms=10,zorder=4,label="Spine-Branch")
ax.plot(cap,macu, '-s',color=C_M,lw=2.6,ms=9, zorder=3,label="MACU")
for x,m,p in zip(cap,macu,spine):
    ax.annotate(f"+{p-m:.1f}",(x,(m+p)/2),xytext=(8,-3),textcoords="offset points",
                fontsize=10,color="#1a7a1a")
ax.set_xlabel("Single-agent CUA Capability")
ax.set_ylabel("Rubric Average [%]")
ax.grid(alpha=0.3); ax.legend(loc="lower right",fontsize=14,frameon=True,framealpha=0.9)
ax.set_xlim(cap.min()-5,cap.max()+7); ax.set_ylim(ylo,yhi)
fig.tight_layout(); out="reports/ablation_gap_increase.png"
fig.savefig(out,dpi=160,bbox_inches="tight"); print("wrote",out,"gaps:",[round(p-m,1) for p,m in zip(spine,macu)])
