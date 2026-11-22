"""Vendored pure-numpy CART + bagged forest. Keeps the backend free of any
sklearn dependency, which matters because sklearn is blocked by Application
Control policy on the target Windows machine."""
import numpy as np
# Vectorised CART (Gini) + bagged forest. No sklearn needed.
class Tree:
    def __init__(self,max_depth=None,min_leaf=1,max_features=None,rng=None):
        self.max_depth=max_depth; self.min_leaf=min_leaf
        self.max_features=max_features; self.rng=rng or np.random.default_rng(0)
    def fit(self,X,y,K=None):
        X=np.asarray(X,float); y=np.asarray(y,int)
        self.K=K or int(y.max())+1
        self.root=self._grow(X,y,0); return self
    def _leaf(self,y):
        c=np.bincount(y,minlength=self.K).astype(float); return ("L",c/c.sum())
    def _best(self,X,y,j):
        o=np.argsort(X[:,j],kind="mergesort"); xs=X[o,j]; ys=y[o]; n=len(ys)
        oh=np.zeros((n,self.K)); oh[np.arange(n),ys]=1.0
        cl=np.cumsum(oh,0)[:-1]                       # counts left for each cut
        tot=cl[-1]+oh[-1]
        cr=tot-cl
        nl=np.arange(1,n,dtype=float)[:,None]; nr=n-nl
        gl=1.0-((cl/nl)**2).sum(1); gr=1.0-((cr/nr)**2).sum(1)
        wimp=(nl[:,0]*gl+nr[:,0]*gr)/n
        ok=xs[1:]!=xs[:-1]
        if not ok.any(): return None
        wimp=np.where(ok,wimp,np.inf); i=int(np.argmin(wimp))
        return (wimp[i],j,(xs[i]+xs[i+1])/2)
    def _grow(self,X,y,d):
        n,p=X.shape
        if len(np.unique(y))==1 or n<=self.min_leaf or (self.max_depth and d>=self.max_depth):
            return self._leaf(y)
        feats=range(p) if not self.max_features else self.rng.choice(p,min(self.max_features,p),replace=False)
        cand=[c for c in (self._best(X,y,j) for j in feats) if c]
        if not cand: return self._leaf(y)
        parent=1.0-((np.bincount(y,minlength=self.K)/n)**2).sum()
        imp,j,t=min(cand)
        if parent-imp<=1e-12: return self._leaf(y)
        m=X[:,j]<=t
        if m.all() or (~m).all(): return self._leaf(y)
        return ("N",j,t,self._grow(X[m],y[m],d+1),self._grow(X[~m],y[~m],d+1))
    def _one(self,x,nd):
        while nd[0]=="N": nd=nd[3] if x[nd[1]]<=nd[2] else nd[4]
        return nd[1]
    def predict_proba(self,X):
        X=np.asarray(X,float); return np.array([self._one(x,self.root) for x in X])
    def predict(self,X): return self.predict_proba(X).argmax(1)

class Forest:
    def __init__(self,n=40,max_depth=None,max_features="sqrt",seed=14,balanced=False):
        self.n=n; self.max_depth=max_depth; self.mf=max_features; self.seed=seed; self.balanced=balanced
    def fit(self,X,y,K=None):
        X=np.asarray(X,float); y=np.asarray(y,int); self.K=K or int(y.max())+1
        rng=np.random.default_rng(self.seed); p=X.shape[1]
        mf=int(np.sqrt(p)) if self.mf=="sqrt" else (self.mf or p)
        w=None
        if self.balanced:
            cnt=np.bincount(y,minlength=self.K).astype(float); cnt[cnt==0]=1
            w=(1.0/cnt)[y]; w=w/w.sum()
        self.trees=[]
        for i in range(self.n):
            idx=rng.choice(len(y),len(y),replace=True,p=w)
            if len(np.unique(y[idx]))<2: continue
            self.trees.append(Tree(self.max_depth,1,mf,np.random.default_rng(self.seed+i)).fit(X[idx],y[idx],self.K))
        return self
    def predict_proba(self,X):
        return np.mean([t.predict_proba(X) for t in self.trees],axis=0)
    def predict(self,X): return self.predict_proba(X).argmax(1)

def accuracy(y,p): return float(np.mean(np.asarray(y)==np.asarray(p)))
def balanced_acc(y,p):
    y=np.asarray(y);p=np.asarray(p)
    return float(np.mean([np.mean(p[y==k]==k) for k in np.unique(y)]))
def macro_f1(y,p,K=None):
    y=np.asarray(y);p=np.asarray(p); K=K or int(max(y.max(),p.max()))+1; fs=[]
    for k in range(K):
        if (y==k).sum()==0: continue
        tp=((p==k)&(y==k)).sum(); fp=((p==k)&(y!=k)).sum(); fn=((p!=k)&(y==k)).sum()
        fs.append(0.0 if tp==0 else 2*tp/(2*tp+fp+fn))
    return float(np.mean(fs))
