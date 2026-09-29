"""_names.py -- v20.47: ONE rule for sub-watershed names in every input file (exports, fund file, BM ground files).

YOUR RULE: two spellings whose names match >= 80 % are the same sub-watershed.
    similarity = 1 - (Levenshtein edit distance) / (length of the longer name), on normalised names (lower case,
    letters only, without "sub-watershed", "SWS", "control" or text in brackets). The same measure is used in R (adist).
Two safeguards keep the rule from merging different places (found in your BM files):
  * the best match must be unambiguous: >= 5 points ahead of the next candidate;
  * where rows carry coordinates (BM sites), the sites must lie in that sub-watershed's core -- "Nagagondanahalli" is 81 %
    similar to "Kytagondanahalli" but all 9 of its sites lie in Kyatagondanahalli's RINGS: a neighbouring control.
Known spellings (below) are matched exactly first ("Halligera" is only 78 % similar to "Haligeri").
"""
import re

NAME_MATCH_THRESHOLD = 0.80
NAME_MATCH_MARGIN = 0.05
PROGRAMME_ALIASES = {
    "artal": "Artal", "begur": "Beguru", "beguru": "Beguru", "chatrakodihalli": "Chhatrakodihalli", "chhatrakodihalli": "Chhatrakodihalli",
    "chittaragi": "Chittharagi", "chittharagi": "Chittharagi", "doddenahalli": "Doddenahalli", "gummalapalli": "Gummlapalli",
    "gummlapalli": "Gummlapalli", "halligera": "Haligeri", "haligeri": "Haligeri", "honnutagi": "Honnutagi", "hunsehadagli": "Hunasehadagi",
    "hunasehadagi": "Hunasehadagi", "jammapura": "Jammapur", "jammapur": "Jammapur", "jantapur": "Jantapur", "kodihalli": "Kodihalli",
    "koranahalli": "Koranahalli", "kytagondanahalli": "Kyatagondanahalli", "kyatagondanahalli": "Kyatagondanahalli",
    "maidalakere": "Maidalakere", "mydalakere": "Maidalakere", "mallainupura": "Mallainupura", "murlapura": "Murlapura",
    "nilagunda": "Nilgund", "nilgunda": "Nilgund", "nilgund": "Nilgund", "pashapur": "Pashapur", "shirur": "Sirur", "sirur": "Sirur"}

def norm_name(x):
    s = re.sub(r"\(.*?\)", " ", str(x if x is not None else "").lower())
    s = re.sub(r"sub[\s\-_]*watershed|\bsws\b|control", " ", s)
    return re.sub(r"[^a-z]", "", s)

def levenshtein(a, b):
    if a == b: return 0
    if len(a) < len(b): a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]

def similarity(a, b, normalised=False):
    na, nb = (a, b) if normalised else (norm_name(a), norm_name(b))
    if not na or not nb: return 0.0
    return 1.0 - levenshtein(na, nb) / max(len(na), len(nb))

def programme_candidates(registry_names):
    """normalised spelling -> programme name: every registry name and every known spelling of it."""
    reg = {str(r) for r in registry_names}
    c = {norm_name(r): r for r in reg}
    c.update({k: v for k, v in PROGRAMME_ALIASES.items() if v in reg})
    return c

def best_match(raw, candidates, threshold=NAME_MATCH_THRESHOLD, margin=NAME_MATCH_MARGIN):
    """(name or None, similarity, how). candidates: normalised spelling -> canonical name."""
    n = norm_name(raw)
    if not n: return None, 0.0, "blank"
    if n in candidates: return candidates[n], 1.0, "known spelling"
    best = {}
    for k, canon in candidates.items():
        s = similarity(n, k, normalised=True)
        if s > best.get(canon, -1): best[canon] = s
    ranked = sorted(best.items(), key=lambda t: -t[1])
    if not ranked or ranked[0][1] < threshold:
        return None, (ranked[0][1] if ranked else 0.0), f"no name >= {threshold:.0%} similar"
    if len(ranked) > 1 and ranked[0][1] - ranked[1][1] < margin:
        return None, ranked[0][1], f"ambiguous: {ranked[0][0]} {ranked[0][1]:.0%} vs {ranked[1][0]} {ranked[1][1]:.0%}"
    return ranked[0][0], ranked[0][1], f"{ranked[0][1]:.0%} similar to {ranked[0][0]}"

def cluster_names(names, threshold=NAME_MATCH_THRESHOLD, allowed=None):
    """Group spellings >= threshold similar (single linkage). allowed(a, b) -> bool can veto a pair (e.g. far apart)."""
    names = [n for n in dict.fromkeys(names) if norm_name(n)]
    parent = {n: n for n in names}
    def root(x):
        while parent[x] != x: parent[x] = parent[parent[x]]; x = parent[x]
        return x
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if similarity(a, b) >= threshold and (allowed is None or allowed(a, b)):
                parent[root(b)] = root(a)
    groups = {}
    for n in names: groups.setdefault(root(n), []).append(n)
    return list(groups.values())
