#!/usr/bin/env python3
"""Outil de mise à jour de l'appli 10DEC - FDR.

Tout l'état (événements en clair, clés de chiffrement) est stocké CHIFFRÉ dans state.enc
avec une clé technique qui n'est PAS dans ce dépôt (elle est dans un Google Sheet privé).

Commandes (dossier de travail : $FDR_WORK, par défaut /tmp/fdr_work, jamais dans le dépôt) :
  fdr.py unlock <cle_technique_base64>      -> déchiffre state.enc dans $FDR_WORK/state.json
  fdr.py codes <codes_values.json>          -> écrit $FDR_WORK/codes.json à partir de get_values CODES!A4:G60
  fdr.py sheet <event_id> <values.json>     -> applique le contenu visible d'une fiche FDR (get_values FDR!A1:E250) à l'événement
  fdr.py addevent <event.json>              -> ajoute / remplace un événement (format CONSIGNES_AGENT.md)
  fdr.py addbillet <event_id> <qui> <sens> <fileId> <titre> <pdf>  -> ajoute un vrai billet PDF à un trajet
  fdr.py sheetgen <event_id> <out.json>     -> requêtes Sheets (mise en forme) + <out>.values.json pour créer une fiche FDR
  fdr.py build                              -> régénère index.html et b/*.txt à la racine du dépôt
  fdr.py lock <cle_technique_base64>        -> rechiffre $FDR_WORK/state.json dans state.enc
  fdr.py list                               -> liste les événements (id, date, qui, fiche, dossier Drive)
  fdr.py fiches                             -> {id de fiche Sheets: id événement}
  fdr.py meta get|set <clé> [valeur]        -> lit / écrit last_sync, last_gmail…
  fdr.py setev <event_id> <champ> <valeur>  -> ex. setev X fiche https://… ; setev X visible false
"""
import json, os, sys, base64, secrets, random, re, shutil, glob, subprocess, urllib.parse, hashlib, datetime
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(REPO, "tools")
WORK = os.environ.get("FDR_WORK", "/tmp/fdr_work")
os.makedirs(WORK, exist_ok=True)
STATE = os.path.join(WORK, "state.json")
ITER = 300000

def load(p, d=None):
    return json.load(open(p)) if os.path.exists(p) else d
def save(p, o):
    json.dump(o, open(p, "w"), ensure_ascii=False, indent=1); os.chmod(p, 0o600)

# ---------- état chiffré ----------
def unlock(k64):
    k = base64.b64decode(k64); raw = open(os.path.join(REPO, "state.enc"), "rb").read()
    save(STATE, json.loads(AESGCM(k).decrypt(raw[:12], raw[12:], None)))
    print("ok", len(load(STATE)["events"]), "événements")
def lock(k64):
    k = base64.b64decode(k64); iv = secrets.token_bytes(12)
    data = json.dumps(load(STATE), ensure_ascii=False).encode()
    open(os.path.join(REPO, "state.enc"), "wb").write(iv + AESGCM(k).encrypt(iv, data, None)); print("ok")

# ---------- codes ----------
def slugify(prenom, nom):
    s = prenom.lower()
    for a, b in (("é", "e"), ("è", "e"), ("ê", "e"), ("ë", "e"), ("à", "a"), ("ï", "i"), ("î", "i"), ("ô", "o"), ("ç", "c")): s = s.replace(a, b)
    s = re.sub(r"[^a-z]", "", s)
    if s == "christelle": s = "christelle-" + (nom[:1].lower() or "x")
    if s == "florian": s = "flo"
    return s
def codes(path):
    rows = json.load(open(path)); rows = rows.get("values", rows) if isinstance(rows, dict) else rows
    out = {}
    for r in rows[1:]:
        r = (r + [""] * 7)[:7]
        prenom, nom, code, role, autres, actif = r[0].strip(), r[1].strip(), r[2].strip(), r[3], r[4], r[5]
        if not prenom or not code or actif.strip().lower() == "non": continue
        slug = slugify(prenom, nom)
        nm = prenom if slug not in ("christelle-l", "christelle-g") else prenom + ("" if slug == "christelle-l" else " G.")
        out[slug] = {"nom": nm, "code": code, "admin": role.strip().lower() == "admin", "alias": [a.strip() for a in (autres or "").split(",") if a.strip()] + [prenom, prenom + " " + nom]}
    save(os.path.join(WORK, "codes.json"), out); print("ok", len(out), "codes")

def name_to_slug(name, C):
    n = name.strip().lower()
    if not n: return None
    for s, c in C.items():
        for a in [c["nom"]] + c["alias"]:
            if a and (n == a.lower() or n.startswith(a.lower() + " ") or n.startswith(a.lower() + " (")): return s
    for s, c in C.items():
        if n.split(" ")[0].split("(")[0] == c["nom"].lower().split(" ")[0]: return s
    return None

# ---------- fiche Sheets -> événement ----------
SECS = [("📌", "infos"), ("⚠️", "chg"), ("⏰", "plan"), ("🚆", "traj"), ("🚕", "run"), ("🛏", "dodo"), ("📞", "cont"), ("🚗", "acc"), ("🎵", "set"), ("👕", "tenue"), ("📝", "rem")]
HDR = {"chg", "plan", "traj", "run", "cont", "set", "rem"}
ETAT = {"✓ ok": "ok", "ok": "ok", "à faire": "a_faire", "a faire": "a_faire", "à vérifier": "a_verifier", "a verifier": "a_verifier"}
def strip_b(t): return (t or "").replace("**", "")
def keep_bold(new, olds):
    for o in olds:
        if strip_b(o) == new: return o
    return new
def split_ic(label):
    m = re.match(r"^(\S+)\s+(.*)$", label.strip())
    if m and not re.match(r"[\wÀ-ÿ]", m.group(1)[0]): return m.group(1), m.group(2)
    return "•", label.strip()

def sheet(ev_id, path):
    S = load(STATE); C = load(os.path.join(WORK, "codes.json"), {})
    e = next(x for x in S["events"] if x["id"] == ev_id)
    vals = json.load(open(path)); vals = vals.get("values", vals) if isinstance(vals, dict) else vals
    rows = [[str(c) for c in (r + [""] * 5)[:5]] for r in vals]
    blocks, cur, skip = {}, None, False
    for r in rows:
        a = r[0].strip()
        if a.startswith("— fin"): break
        word = re.sub(r"^\W+", "", a).split(" ")[0] if a else ""
        sec = next((k for p, k in SECS if a.startswith(p)), None) if (word and word.upper() == word and len(word) > 2) else None
        if sec and not any(r[1:]):
            cur, skip = sec, sec in HDR; blocks.setdefault(cur, []); continue
        if cur is None: continue
        if skip: skip = False; continue
        if not any(x.strip() for x in r): continue
        blocks[cur].append(r)
    old = json.loads(json.dumps(e))
    kv = lambda b: [(r[0].strip(), r[2].strip()) for r in blocks.get(b, [])]
    # infos
    for k, v in kv("infos"):
        kl = k.lower()
        if kl == "date": e["date_txt"] = v
        elif kl == "lieu": e["lieu"] = v
        elif kl == "adresse": e["adresse"] = v
        elif kl == "artiste": e["artiste"] = v
        elif kl.startswith("équipe") and C:
            q = [name_to_slug(x, C) for x in re.split(r",|\+| et ", v) if x.strip()]
            q = [x for x in q if x]
            if q: e["qui"] = list(dict.fromkeys(q))
        elif kl.startswith("visible"): e["visible"] = not v.strip().lower().startswith("non")
    if "chg" in blocks: e["changements"] = [r[1].strip() for r in blocks["chg"] if r[1].strip()]
    if "plan" in blocks: e["planning"] = [{"heure": r[0].strip(), "quoi": r[1].strip(), "detail": r[2].strip()} for r in blocks["plan"] if r[0].strip() or r[1].strip()]
    if "traj" in blocks:
        out = []; prev = old.get("trajets", []); used_p = set()
        for i, r in enumerate(blocks["traj"]):
            qui = r[0].strip(); sd = [x.strip() for x in r[1].split("·", 1)]; sens = sd[0]; date = sd[1] if len(sd) > 1 else ""
            hor = [x.strip() for x in r[2].split("→")] if "→" in r[2] else [r[2].strip(), ""]
            t = r[3].strip(); de = vers = ""; det = t
            first, _, rest = t.partition(" · ")
            if "→" in first: de, vers = [x.strip() for x in first.split("→", 1)]; det = rest.strip()
            used_p = used_p if i else set()
            cands = [j for j, x in enumerate(prev) if j not in used_p and x["qui"] == qui and x["sens"] == sens]
            j = next((j for j in cands if prev[j].get("date") == date and prev[j].get("dep") == hor[0]), None)
            if j is None: j = next((j for j in cands if prev[j].get("date") == date), None)
            if j is None and i < len(prev) and i not in used_p and prev[i]["qui"] == qui: j = i
            if j is None and cands: j = cands[0]
            p = prev[j] if j is not None else {}
            if j is not None: used_p.add(j)
            if not de and p.get("vers") and not p.get("de"): vers = p["vers"]
            etat = ETAT.get(r[4].strip().lower(), p.get("etat", "a_verifier"))
            l = {"qui": qui, "sens": sens, "date": date, "dep": hor[0], "arr": hor[1] if len(hor) > 1 else "", "de": de, "vers": vers, "detail": det, "etat": etat, "billets": p.get("billets", [])}
            for k in ("sansbillet", "badge"):
                if p.get(k): l[k] = p[k]
            out.append(l)
        e["trajets"] = out
    if "run" in blocks:
        prev = old.get("run", []) if isinstance(old.get("run"), list) else []
        e["run"] = []
        for i, r in enumerate(blocks["run"]):
            if not (r[0].strip() or r[1].strip()): continue
            ic0, b0 = split_ic(r[0])
            b = b0 if ic0 != "•" else r[0].strip()
            p = next((x for x in prev if x.get("b") == b), {})
            ic = ic0 if ic0 != "•" else p.get("ic", "🚕")
            e["run"].append({"ic": ic, "b": b, "l": [x.strip() for x in r[1].split("\n") if x.strip()]})
    def items(block, base):
        prev = (base or {}).get("items", []) if isinstance(base, dict) else []
        out = []
        for k, v in kv(block):
            if not v: continue
            ic, b = split_ic(k)
            p = next((x for x in prev if x.get("b") == b), {})
            t = keep_bold(v, [p.get("t", "")])
            if t == v and ("code" in b.lower() or ic == "🔢"): t = re.sub(r"(\d{3,})", r"**\1**", v)
            out.append({"ic": p.get("ic", ic), "b": b, "t": t})
        return out
    if "dodo" in blocks:
        hb = dict(old.get("hebergement") or {}); its = []
        for k, v in kv("dodo"):
            if k == "Nom": hb["nom"] = v
            elif k.startswith("Adresse"):
                hb["adresse"] = v
            elif k.startswith("Gare"):
                hb["gare"] = v
                if v: hb["gare_maps"] = "https://www.google.com/maps/search/?api=1&query=" + urllib.parse.quote(v)
        if hb.get("adresse"):
            q = (hb.get("nom", "") + ", " + hb["adresse"]) if hb.get("nom") and hb["nom"].lower() not in hb["adresse"].lower() else hb["adresse"]
            hb["maps"] = "https://www.google.com/maps/search/?api=1&query=" + urllib.parse.quote(q)
        blocks["dodo2"] = [r for r in blocks["dodo"] if r[0].strip() not in ("Nom",) and not r[0].strip().startswith("Adresse") and not r[0].strip().startswith("Gare")]
        hb["items"] = items("dodo2", old.get("hebergement"))
        e["hebergement"] = hb if (hb.get("nom") or hb["items"]) else {}
    if "acc" in blocks: e["acces"] = {"items": items("acc", old.get("acces"))}
    if "cont" in blocks: e["contacts"] = [{"nom": r[0].strip(), "role": r[2].strip(), "tel": r[3].strip()} for r in blocks["cont"] if r[0].strip()]
    if "set" in blocks:
        prev = {s["titre"]: s for s in old.get("setlist", [])}; out = []
        for r in blocks["set"]:
            if r[0].startswith("ℹ️"): e["setlist_note"] = r[0].replace("ℹ️", "").strip(); continue
            if not r[1].strip(): continue
            n = r[0].strip(); n = int(n) if n.isdigit() else n
            out.append({"n": n, "titre": r[1].strip(), "qui": r[3].strip(), "doc": prev.get(r[1].strip(), {}).get("doc", "")})
        e["setlist"] = out
    tk = kv("tenue")
    for k, v in tk:
        if k.lower().startswith("concert"): e["tenue"] = v
    if any(k.lower().startswith(("habill", "interpr")) for k, v in tk): e["habille"] = True
    elif any(k.lower().startswith("journ") for k, v in tk): e.pop("habille", None)
    if "rem" in blocks: e["remarques"] = [r[1].strip() for r in blocks["rem"] if r[1].strip()]
    save(STATE, S)
    changed = json.dumps(old, sort_keys=True) != json.dumps(e, sort_keys=True)
    print("changé" if changed else "identique", ev_id)

# ---------- ajout ----------
def addevent(path):
    S = load(STATE); e = json.load(open(path))
    S.setdefault("titres_billets", {}).update(e.pop("billets_titres", {}) or {})
    for k, v in (("run", []), ("hebergement", {}), ("acces", {}), ("setlist", []), ("planning", []), ("contacts", []), ("remarques", []), ("changements", []), ("trajets", [])):
        if e.get(k) is None: e[k] = v
    for l in e["trajets"]:
        for b in l.get("billets", []):
            pdf = os.path.join(WORK, "pdf", b + ".pdf")
            if os.path.exists(pdf): stash(e["id"], b, pdf, S)
        l["billets"] = [b for b in l.get("billets", []) if b in S["keys"]["billets_ok"]]
    S["events"] = [x for x in S["events"] if x["id"] != e["id"]] + [e]
    S["events"].sort(key=lambda x: x["date"]); save(STATE, S); print("ok", e["id"])

def evkey(S, ev_id):
    K = S["keys"]
    if ev_id not in K["events"]: K["events"][ev_id] = base64.b64encode(secrets.token_bytes(32)).decode()
    return base64.b64decode(K["events"][ev_id])

def stash(ev_id, fid, pdf, S):
    raw = open(pdf, "rb").read()
    if raw[:5] != b"%PDF-": raise SystemExit("pas un PDF : " + pdf)
    K = S["keys"]; name = K["billets"].setdefault(ev_id + ":" + fid, secrets.token_hex(12))
    ek = evkey(S, ev_id); iv = secrets.token_bytes(12)
    os.makedirs(os.path.join(REPO, "b"), exist_ok=True)
    open(os.path.join(REPO, "b", name + ".txt"), "w").write(base64.b64encode(iv + AESGCM(ek).encrypt(iv, raw, None)).decode())
    K.setdefault("billets_ok", [])
    if fid not in K["billets_ok"]: K["billets_ok"].append(fid)

def addbillet(ev_id, qui, sens, fid, titre, pdf):
    S = load(STATE); e = next(x for x in S["events"] if x["id"] == ev_id)
    if fid in S.get("billets_retires", []): print("ignoré (billet retiré, plus valable)", fid); return
    stash(ev_id, fid, pdf, S); S.setdefault("titres_billets", {})[fid] = titre
    l = next((x for x in e["trajets"] if x["qui"].lower() == qui.lower() and x["sens"].lower() == sens.lower()), None)
    if l is None:
        l = {"qui": qui, "sens": sens.capitalize(), "date": "", "dep": "", "arr": "", "de": "", "vers": "", "detail": "", "etat": "ok", "billets": []}; e["trajets"].append(l)
    if fid not in l["billets"]: l["billets"].append(fid)
    if l["etat"] in ("a_faire", "a_verifier") and l["dep"]: l["etat"] = "ok"
    save(STATE, S); print("ok", ev_id, qui, sens)

def rmbillet(ev_id, fid):
    """Retire de l'appli un billet qui n'est plus valable (échangé, annulé, rangé dans « Erreurs »).
    Le fichier du Drive n'est pas touché."""
    S = load(STATE); e = next(x for x in S["events"] if x["id"] == ev_id)
    n = 0
    for l in e.get("trajets", []):
        if fid in l.get("billets", []): l["billets"].remove(fid); n += 1
    K = S["keys"]; name = K.get("billets", {}).pop(ev_id + ":" + fid, None)
    if name and os.path.exists(os.path.join(REPO, "b", name + ".txt")): os.remove(os.path.join(REPO, "b", name + ".txt"))
    if fid in K.get("billets_ok", []) and not any(fid in l.get("billets", []) for x in S["events"] for l in x.get("trajets", [])):
        K["billets_ok"].remove(fid)
    S.setdefault("billets_retires", [])
    if fid not in S["billets_retires"]: S["billets_retires"].append(fid)
    save(STATE, S); print("ok retiré", ev_id, fid, n)

# ---------- construction de l'appli ----------
def build():
    S = load(STATE); C = load(os.path.join(WORK, "codes.json"))
    S["today"] = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    if not C: raise SystemExit("codes.json manquant : lance d'abord 'codes'")
    K = S["keys"]; salt = base64.b64decode(K["salt"]); admin = base64.b64decode(K["admin"])
    enc = lambda key, data: (lambda iv: base64.b64encode(iv + AESGCM(key).encrypt(iv, data, None)).decode())(secrets.token_bytes(12))
    cache = K.setdefault("pk_cache", {})
    pkeys = {}
    for s, c in C.items():
        h = hashlib.sha256((K["salt"] + c["code"]).encode()).hexdigest()
        if cache.get(s, {}).get("h") == h: pkeys[s] = base64.b64decode(cache[s]["k"]); continue
        pkeys[s] = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITER).derive(c["code"].encode())
        cache[s] = {"h": h, "k": base64.b64encode(pkeys[s]).decode()}
    for s in list(cache):
        if s not in C: cache.pop(s)
    noms = {s: c["nom"] for s, c in C.items()}; noms.setdefault("aurelie", "Aurélie"); noms.setdefault("perinne", "Périnne")
    persons = [enc(pkeys[s], json.dumps({"slug": s, "nom": noms[s], **({"adm": enc(pkeys[s], admin)} if C[s]["admin"] else {})}).encode()) for s in pkeys]
    random.shuffle(persons)
    teamkey = secrets.token_bytes(32)
    tw = [enc(k, teamkey) for k in list(pkeys.values()) + [admin]]; random.shuffle(tw)
    titles = S.get("titres_billets", {})
    pub = []; used = set()
    for e in sorted(S["events"], key=lambda x: x["date"]):
        if e.get("visible") is False or e.get("fin", e["date"]) < S.get("today", "0000"): continue
        ek = evkey(S, e["id"]); bil = {}
        for l in e["trajets"]:
            for b in l.get("billets", []):
                name = K["billets"].get(e["id"] + ":" + b)
                if not name or not os.path.exists(os.path.join(REPO, "b", name + ".txt")): continue
                used.add(name + ".txt")
                bil[b] = {"f": "b/" + name + ".txt", "t": titles.get(b, "Billet").replace(".pdf", "").split(" (")[0]}
        payload = {k: v for k, v in e.items() if k not in ("id", "date", "fin", "qui")}; payload["billets"] = bil
        prive = bool(e.get("prive"))
        wr = ([] if prive else [enc(pkeys[s], ek) for s in e["qui"] if s in pkeys]) + [enc(admin, ek)]; random.shuffle(wr)
        # Rien en clair : l'en-tête (id, date, qui, catégorie) est chiffré.
        # Événement normal -> lisible par toute l'équipe (clé d'équipe).
        # Prestation d'entreprise -> lisible seulement avec la clé admin (Aurélie, Périnne).
        head = {"id": e["id"], "date": e["date"], "fin": e.get("fin", e["date"]), "qui": [] if prive else e["qui"], "c": e.get("cat") or ("tb" if prive else "")}
        if prive: head["a"] = 1
        item = {"h": enc(admin if prive else teamkey, json.dumps(head, ensure_ascii=False).encode()), "wraps": wr, "data": enc(ek, json.dumps(payload, ensure_ascii=False).encode())}
        pub.append(item)
    random.shuffle(pub)
    DATA = {"salt": K["salt"], "iter": ITER, "persons": persons, "team": {"wraps": tw, "data": enc(teamkey, json.dumps(S["memo"], ensure_ascii=False).encode()), "noms": enc(teamkey, json.dumps(noms, ensure_ascii=False).encode())}, "events": pub}
    html = open(os.path.join(TOOLS, "template.html")).read().replace("__DATA__", json.dumps(DATA, ensure_ascii=False)).replace("__PHOTOS__", "{}")
    open(os.path.join(REPO, "index.html"), "w").write(html)
    for f in ("manifest.json", "icon-192.png", "icon-512.png", "icon-maskable-512.png"): shutil.copy(os.path.join(TOOLS, f), os.path.join(REPO, f))
    sw = open(os.path.join(TOOLS, "sw.js")).read().replace('const C="fdr-v1"', 'const C="fdr-' + secrets.token_hex(4) + '"')
    open(os.path.join(REPO, "sw.js"), "w").write(sw)
    for f in glob.glob(os.path.join(REPO, "b", "*.txt")):
        if os.path.basename(f) not in used: os.remove(f)
    save(STATE, S); print("ok", len(pub), "événements,", len(used), "billets")

def sheetgen(ev_id, out):
    S = load(STATE); C = load(os.path.join(WORK, "codes.json"), {})
    tmp = os.path.join(WORK, "sg"); os.makedirs(os.path.join(tmp, "data"), exist_ok=True); os.makedirs(os.path.join(tmp, "secret"), exist_ok=True)
    json.dump(S["events"], open(os.path.join(tmp, "data", "events.json"), "w"), ensure_ascii=False)
    json.dump({s: [c["nom"], ""] for s, c in C.items()}, open(os.path.join(tmp, "secret", "codes.json"), "w"), ensure_ascii=False)
    shutil.copy(os.path.join(TOOLS, "sheetgen.py"), os.path.join(tmp, "sheetgen.py"))
    subprocess.run([sys.executable, "-I", os.path.join(tmp, "sheetgen.py"), ev_id, out], check=True)

def meta(op, key, val=None):
    S = load(STATE)
    if op == "get": print(S.get(key, ""))
    else: S[key] = val; save(STATE, S); print("ok")

def setev(ev_id, field, val):
    S = load(STATE); e = next(x for x in S["events"] if x["id"] == ev_id)
    if val in ("true", "false"): val = val == "true"
    e[field] = val; save(STATE, S); print("ok", ev_id, field)

def fiches():
    S = load(STATE)
    print(json.dumps({(e.get("fiche") or "").split("/d/")[-1].split("/")[0]: e["id"] for e in S["events"] if e.get("fiche")}, indent=1))

def lst():
    S = load(STATE)
    for e in S["events"]: print(e["id"], e["date"], ",".join(e["qui"]), (e.get("fiche") or "").split("/d/")[-1].split("/")[0], "drive:" + (e.get("drive") or ""))

if __name__ == "__main__":
    c, a = sys.argv[1], sys.argv[2:]
    {"unlock": unlock, "lock": lock, "codes": codes, "sheet": sheet, "addevent": addevent, "addbillet": addbillet, "rmbillet": rmbillet, "build": build, "sheetgen": sheetgen, "list": lst, "meta": meta, "setev": setev, "fiches": fiches}[c](*a)
