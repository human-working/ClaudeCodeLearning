# settings.py
DATA_DIR = "EMOPIA_1.0/midis"
LABELS_CSV = "EMOPIA_1.0/label.csv"
SPLIT_CSV = "EMOPIA_1.0/metadata_by_song.csv"

FS = 4                 # chroma frames per second
CIRCLE_K = [1, 5]      # which circles to use (1 = chromatic, 5 = fifths)

MAX_DEPTH = 3
TEST_SIZE = 0.2
SEED = 42