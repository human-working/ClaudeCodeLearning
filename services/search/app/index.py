"""A small in-memory BM25 search engine (inverted index)."""
import math
import re
import threading
from collections import Counter, defaultdict
from dataclasses import dataclass

TOKEN_RE = re.compile(r"[a-z0-9]+")
STOPWORDS = frozenset(
    "a an and are as at be but by for if in into is it no not of on or such that the their then "
    "there these they this to was will with i you we he she".split()
)
TITLE_BOOST = 2  # title tokens are counted this many times


def tokenize(text: str) -> list[str]:
    return [t for t in TOKEN_RE.findall(text.lower()) if t not in STOPWORDS]


@dataclass
class Document:
    id: str
    title: str
    body: str
    author: str
    length: int


class BM25Index:
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.docs: dict[str, Document] = {}
        self.postings: dict[str, dict[str, int]] = defaultdict(dict)  # term -> {doc_id: term freq}
        self.total_length = 0
        self._lock = threading.Lock()

    def __len__(self) -> int:
        return len(self.docs)

    def upsert(self, doc_id: str, title: str, body: str, author: str) -> None:
        tokens = tokenize(title) * TITLE_BOOST + tokenize(body)
        with self._lock:
            self._remove(doc_id)
            self.docs[doc_id] = Document(doc_id, title, body, author, len(tokens))
            self.total_length += len(tokens)
            for term, freq in Counter(tokens).items():
                self.postings[term][doc_id] = freq

    def remove(self, doc_id: str) -> None:
        with self._lock:
            self._remove(doc_id)

    def _remove(self, doc_id: str) -> None:
        doc = self.docs.pop(doc_id, None)
        if not doc:
            return
        self.total_length -= doc.length
        for term in set(tokenize(doc.title) + tokenize(doc.body)):
            docs_for_term = self.postings.get(term)
            if docs_for_term is not None:
                docs_for_term.pop(doc_id, None)
                if not docs_for_term:
                    del self.postings[term]

    def search(self, query: str, limit: int = 10) -> list[tuple[Document, float]]:
        terms = set(tokenize(query))
        with self._lock:
            n_docs = len(self.docs)
            if not terms or not n_docs:
                return []
            avg_len = self.total_length / n_docs or 1
            scores: Counter[str] = Counter()
            for term in terms:
                docs_for_term = self.postings.get(term)
                if not docs_for_term:
                    continue
                df = len(docs_for_term)
                idf = math.log(1 + (n_docs - df + 0.5) / (df + 0.5))
                for doc_id, tf in docs_for_term.items():
                    norm = 1 - self.b + self.b * self.docs[doc_id].length / avg_len
                    scores[doc_id] += idf * tf * (self.k1 + 1) / (tf + self.k1 * norm)
            return [(self.docs[d], s) for d, s in scores.most_common(limit)]
