import os, math
import numpy as np
import pretty_midi
from sklearn.tree import DecisionTreeClassifier, export_text
from sklearn.model_selection import GroupShuffleSplit
import setttings

# Unit-circle position of each pitch class (k = 1 circle)
ANGLES = np.arange(12) * math.pi / 6
COS, SIN = np.cos(ANGLES), np.sin(ANGLES)

def clip_r(midi):
    """Chord point at every time step → array of shape (T, 2)."""
    chroma = midi.get_chroma(fs=setttings.FS)      
    totals = chroma.sum(axis=0)
    active = totals > 0                         
    chroma, totals = chroma[:, active], totals[active]
    xs = COS @ chroma / totals                  
    ys = SIN @ chroma / totals                   # weighted average y per frame
    return np.stack([xs, ys], axis=1)

def clip_features(midi):
    """One feature row per clip."""
    r = clip_r(midi)
    if len(r) < 2:
        return None
    speed = np.linalg.norm(np.diff(r, axis=0), axis=1)
    return np.concatenate([
        r.mean(axis=0),      
        r.std(axis=0),       
        [speed.mean()],      
    ])

X, y, groups = [], [], []
for fname in sorted(os.listdir(setttings.DATA_DIR)):
    if not fname.endswith(".mid"):
        continue
    midi = pretty_midi.PrettyMIDI(os.path.join(setttings.DATA_DIR, fname))
    feats = clip_features(midi)
    if feats is None:
        continue
    X.append(feats)
    y.append(fname[:2])                                   
    groups.append(fname[3:-4].rsplit("_", 1)[0])          

X, y = np.array(X), np.array(y)
print(X.shape, "→", len(set(groups)), "songs")

# Split by song so no song appears in both train and test
split = GroupShuffleSplit(n_splits=1, test_size=setttings.TEST_SIZE, random_state=setttings.SEED)
train_idx, test_idx = next(split.split(X, y, groups))

tree = DecisionTreeClassifier(max_depth=setttings.MAX_DEPTH, random_state=setttings.SEED)
tree.fit(X[train_idx], y[train_idx])

print("Test accuracy:", tree.score(X[test_idx], y[test_idx]))
print(export_text(tree, feature_names=["mean_x", "mean_y", "std_x", "std_y", "speed"]))