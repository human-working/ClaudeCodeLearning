
import math, numpy as np

def chord_point(notes):
    xs = [math.cos((n % 12) * math.pi / 6) for n in notes]
    ys = [math.sin((n % 12) * math.pi / 6) for n in notes]
    return (np.mean(xs), np.mean(ys))


features = [
    chord_point.mean(axis=0),       
    chord_point.std(axis=0),                 
]

