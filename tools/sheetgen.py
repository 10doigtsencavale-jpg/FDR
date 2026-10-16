"""Build a Sheets batchUpdate for one FDR (feuille de route) sheet. Usage: sheetgen.py <event_id|MODELE> <out.json>"""
import json, sys, os
D = os.path.dirname(os.path.abspath(__file__))
def rgb(h): h = h.lstrip('#'); return {"red": round(int(h[0:2], 16)/255,3), "green": round(int(h[2:4], 16)/255,3), "blue": round(int(h[4:6], 16)/255,3)}
SID = 0
DARK, WHITE, MUTED, LINE = "#1d2033", "#ffffff", "#646a85", "#e3e5ef"
SEC = {"infos": "#eef0f7", "chg": "#fdebd0", "plan": "#fdebd0", "run": "#dbeafc", "traj": "#dcf5e6", "dodo": "#e9e1fb",
       "cont": "#dcf5e6", "acc": "#eef0f7", "set": "#e9e1fb", "tenue": "#eef0f7", "rem": "#fff3c4"}

rows = []   # each: dict(cells=[(col, value, span)], kind, fill)
def R(kind, cells, fill=None, status=False):
    rows.append({"kind": kind, "cells": cells, "fill": fill, "status": status})

ev_id = sys.argv[1]
if ev_id == "MODELE":
    e = {"titre": "[NOM DE L'ÉVÉNEMENT]", "date": "", "lieu": "", "adresse": "", "artiste": "", "equipe": "", "planning": [{"heure": "00h00", "quoi": "Balances", "detail": ""}, {"heure": "00h00", "quoi": "CONCERT", "detail": "jusqu'à 00h00"}],
         "run": {"aller": "", "retour": ""}, "trajets": [{"qui": "Prénom", "sens": "Aller", "date": "", "dep": "", "arr": "", "de": "", "vers": "", "detail": "", "etat": "a_faire"}],
         "hebergement": {}, "contacts": [{"nom": "", "role": "Référent(e) salle / festival", "tel": ""}], "acces": {}, "setlist": [{"n": 1, "titre": "", "qui": "", "doc": ""}],
         "tenue": "", "remarques": [], "changements": []}
    title = "MODÈLE - FDR (feuille de route appli 10DEC - FDR)"
else:
    evs = json.load(open(os.path.join(D, "data/events.json")))
    e = [x for x in evs if x["id"] == ev_id][0]
    codes = json.load(open(os.path.join(D, "secret/codes.json")))
    noms = {k: v[0] for k, v in codes.items()}; noms.update({"perinne": "Périnne", "aurelie": "Aurélie", "christelle-l": "Christelle (Livet)"})
    e = dict(e, equipe=", ".join(noms.get(q, q) for q in e["qui"]))
    title = None

ST = {"ok": "✓ OK", "a_faire": "à faire", "a_verifier": "à vérifier", "orga": "✓ OK"}
# ---- content
R("title", [(0, "🗺️ " + e["titre"].upper(), 5)])
R("sub", [(0, ("'" if (e.get("date_txt") or e.get("date")) and not e.get("lieu") else "") + (e.get("date_txt") or e.get("date", "")) + ("  ·  " + e["lieu"] if e.get("lieu") else ""), 5)])
R("help", [(0, "Statut en colonne E : ✓ OK (vert) · à vérifier (violet) · à faire (bordeaux). L'appli 10DEC - FDR se met à jour depuis cette fiche toutes les heures (8h-23h).", 5)])
R("gap", [])
def section(key, label, header=None):
    R("sec", [(0, label, 5)], SEC[key])
    if header: R("hdr", header)
def kv(label, value):
    R("kv", [(0, label, 2), (2, value, 3)])

section("infos", "📌 INFOS")
kv("Date", ("'" if (e.get("date_txt") or e.get("date")) else "") + (e.get("date_txt") or e.get("date", "")))
kv("Lieu", e.get("lieu", "")); kv("Adresse", e.get("adresse", "")); kv("Artiste", e.get("artiste", ""))
kv("Équipe 10 Doigts", e.get("equipe", "")); kv("Visible dans l'appli", "Oui")
R("gap", [])
section("chg", "⚠️ CHANGEMENTS  (s'affichent en orange en haut de l'appli)", [(0, "Date", 1), (1, "Changement", 3), (4, "Statut", 1)])
for c in e.get("changements") or [""]:
    R("row", [(0, "", 1), (1, c, 3), (4, "", 1)], status=True)
R("gap", [])
section("plan", "⏰ PLANNING DU JOUR J", [(0, "Heure", 1), (1, "Quoi", 1), (2, "Détail", 2), (4, "Statut", 1)])
for p in e["planning"]:
    R("row", [(0, p["heure"], 1), (1, p["quoi"], 1), (2, p.get("detail", ""), 2), (4, "" if ev_id == "MODELE" else "à vérifier", 1)], status=True)
R("gap", [])
section("traj", "🚆 TRAJETS & BILLETS", [(0, "Qui", 1), (1, "Sens · date", 1), (2, "Horaires", 1), (3, "Trajet · détail", 1), (4, "Statut", 1)])
for l in e["trajets"]:
    hor = f'{l["dep"]} → {l["arr"]}' if (l.get("dep") or l.get("arr")) else ""
    tr = (f'{l["de"]} → {l["vers"]}' if l.get("de") else "") + ((" · " if l.get("de") and l.get("detail") else "") + (l.get("detail") or ""))
    R("row", [(0, l["qui"], 1), (1, f'{l["sens"]} · {l["date"]}'.strip(" ·"), 1), (2, hor, 1), (3, tr, 1), (4, ST.get(l["etat"], ""), 1)], status=True)
R("gap", [])
section("run", "🚕 RUN / NAVETTE", [(0, "Quand", 1), (1, "Détail (une info par ligne)", 3), (4, "Statut", 1)])
run = e.get("run") or []
if isinstance(run, dict): run = [{"b": k.capitalize(), "l": [v]} for k, v in run.items() if v]
for r in run or [{"b": "", "l": [""]}]:
    R("row", [(0, r.get("b", ""), 1), (1, "\n".join(r.get("l", [])), 3), (4, "à vérifier" if r.get("l") and ev_id != "MODELE" else "", 1)], status=True)
R("gap", [])
section("dodo", "🛏️ HÉBERGEMENT")
hb = e.get("hebergement") or {}
kv("Nom", hb.get("nom", "")); kv("Adresse (GPS)", hb.get("adresse", ""))
for it in hb.get("items") or [{"ic": "🔑", "b": "Arrivée", "t": ""}, {"ic": "🚪", "b": "Départ", "t": ""}, {"ic": "🔢", "b": "Code", "t": ""}]:
    kv(f'{it.get("ic","")} {it.get("b","")}'.strip(), it.get("t", "").replace("**", ""))
R("gap", [])
section("cont", "📞 CONTACTS SUR PLACE", [(0, "Nom", 2), (2, "Rôle", 1), (3, "Téléphone", 1), (4, "Statut", 1)])
for c in e["contacts"]:
    R("row", [(0, c["nom"], 2), (2, c.get("role", ""), 1), (3, c.get("tel", ""), 1), (4, "" if ev_id == "MODELE" else "à vérifier", 1)], status=True)
R("gap", [])
section("acc", "🚗 ACCÈS / ACCRÉDITATIONS")
a = e.get("acces") or {}
for it in a.get("items") or [{"ic": "🎫", "b": "Badges", "t": ""}, {"ic": "🚗", "b": "Voiture / parking", "t": ""}, {"ic": "🚪", "b": "Entrée artistes", "t": ""}]:
    kv(f'{it.get("ic","")} {it.get("b","")}'.strip(), it.get("t", "").replace("**", ""))
R("gap", [])
section("set", "🎵 SETLIST", [(0, "N°", 1), (1, "Titre", 2), (3, "Qui signe", 1), (4, "Paroles", 1)])
for s in e["setlist"] or [{"n": "", "titre": "", "qui": "", "doc": ""}]:
    link = f'=HYPERLINK("{s["doc"]}";"Paroles ↗")' if s.get("doc") else ""
    R("row", [(0, s["n"], 1), (1, s["titre"], 2), (3, s.get("qui", ""), 1), (4, link, 1)])
if e.get("setlist_note"): R("note", [(0, "ℹ️ " + e["setlist_note"], 5)])
R("gap", [])
section("tenue", "👕 TENUE")
import re as _re
if e.get("habille") or e.get("cat") == "interpretation" or _re.search(r"conf|table ronde|rencontre|colloque", e.get("type", ""), _re.I): kv("Habillée", "Tenue habillée, noire ou couleur sombre"); kv("Concert", e.get("tenue", ""))
else: kv("Journée", "Tee-shirt + pull 10 DEC + bas au choix (habillé)"); kv("Concert", e.get("tenue", ""))
R("gap", [])
section("rem", "📝 INFOS & REMARQUES  (les remarques écrites dans l'appli arrivent ici)", [(0, "Date", 1), (1, "Remarque", 3), (4, "Source", 1)])
for r in e.get("remarques") or [""]:
    R("row", [(0, "", 1), (1, r, 3), (4, "Mails" if r else "", 1)])
R("end", [(0, "— fin de la fiche —", 5)])

# ---- requests
req = []
N = len(rows)
req.append({"updateSheetProperties": {"properties": {"sheetId": SID, "title": "FDR", "gridProperties": {"rowCount": N + 20, "columnCount": 5, "hideGridlines": True}}, "fields": "title,gridProperties.rowCount,gridProperties.columnCount,gridProperties.hideGridlines"}})
for i, w in enumerate([90, 200, 170, 320, 115]):
    req.append({"updateDimensionProperties": {"range": {"sheetId": SID, "dimension": "COLUMNS", "startIndex": i, "endIndex": i + 1}, "properties": {"pixelSize": w}, "fields": "pixelSize"}})
# base format
req.append({"repeatCell": {"range": {"sheetId": SID, "startRowIndex": 0, "endRowIndex": N + 20, "startColumnIndex": 0, "endColumnIndex": 5},
            "cell": {"userEnteredFormat": {"textFormat": {"fontFamily": "Atkinson Hyperlegible", "fontSize": 11}, "wrapStrategy": "WRAP", "verticalAlignment": "MIDDLE", "padding": {"top": 4, "bottom": 4, "left": 6, "right": 6}}},
            "fields": "userEnteredFormat.textFormat,userEnteredFormat.wrapStrategy,userEnteredFormat.verticalAlignment,userEnteredFormat.padding"}})
def val(v):
    if isinstance(v, (int, float)) and v != "": return {"numberValue": v}
    if isinstance(v, str) and v.startswith("="): return {"formulaValue": v}
    return {"stringValue": str(v)}
rowdata = []
status_rows = []
merges = {}
def tf(**k):
    t={}
    if "bold" in k: t["bold"]=k["bold"]
    if "italic" in k: t["italic"]=k["italic"]
    if "size" in k: t["fontSize"]=k["size"]
    if "font" in k: t["fontFamily"]=k["font"]
    if "color" in k: t["foregroundColorStyle"]={"rgbColor":rgb(k["color"])}
    return t
def fmask(f):
    out=[]
    for key,v in f.items():
        if key=="textFormat": out+=["userEnteredFormat.textFormat."+x for x in v]
        else: out.append("userEnteredFormat."+key)
    return ",".join(out)
KF={"title":({"backgroundColorStyle":{"rgbColor":rgb(DARK)},"textFormat":tf(bold=True,size=18,font="Fredoka",color=WHITE)},46),
 "sub":({"backgroundColorStyle":{"rgbColor":rgb(DARK)},"textFormat":tf(size=12,color="#cfd3e6")},28),
 "help":({"textFormat":tf(italic=True,size=10,color=MUTED)},None),"note":({"textFormat":tf(italic=True,size=10,color=MUTED)},None),"end":({"textFormat":tf(italic=True,size=10,color=MUTED)},None),
 "hdr":({"textFormat":tf(bold=True,size=9,color=MUTED),"borders":{"bottom":{"style":"SOLID","colorStyle":{"rgbColor":rgb(LINE)}}}},22),
 "gap":(None,12),"row":({"borders":{"bottom":{"style":"SOLID","colorStyle":{"rgbColor":rgb(LINE)}}}},None),"kv":({"borders":{"bottom":{"style":"SOLID","colorStyle":{"rgbColor":rgb(LINE)}}}},None)}
def runs(pred):
    out=[];st=None
    for i,r in enumerate(rows):
        if pred(r):
            if st is None: st=i
        elif st is not None: out.append((st,i)); st=None
    if st is not None: out.append((st,len(rows)))
    return out
def G(a,b,c0=0,c1=5): return {"sheetId":SID,"startRowIndex":a,"endRowIndex":b,"startColumnIndex":c0,"endColumnIndex":c1}
for i, r in enumerate(rows):
    vals = [{} for _ in range(5)]
    for col, v, span in r["cells"]:
        vals[col] = {"userEnteredValue": val(v)} if v != "" else {}
        if span > 1: merges.setdefault((col,span),[]).append(i)
    rowdata.append({"values": vals})
    if r["kind"]=="sec":
        req.append({"repeatCell":{"range":G(i,i+1),"cell":{"userEnteredFormat":{"backgroundColorStyle":{"rgbColor":rgb(r["fill"])},"textFormat":tf(bold=True,size=13,font="Fredoka")}},"fields":"userEnteredFormat.backgroundColorStyle,userEnteredFormat.textFormat.bold,userEnteredFormat.textFormat.fontSize,userEnteredFormat.textFormat.fontFamily"}})
    if r["status"]: status_rows.append(i)
for (col,span),idx in merges.items():
    a=idx[0];p=idx[0]
    for i in idx[1:]+[None]:
        if i is not None and i==p+1: p=i; continue
        req.append({"mergeCells":{"range":G(a,p+1,col,col+span),"mergeType":"MERGE_ROWS"}})
        if i is not None: a=p=i
secs=[i for i,r in enumerate(rows) if r["kind"]=="sec"]
if secs: req.append({"updateDimensionProperties":{"range":{"sheetId":SID,"dimension":"ROWS","startIndex":secs[0],"endIndex":secs[0]+1},"properties":{"pixelSize":34},"fields":"pixelSize"}})
for i in secs[1:]: req.append({"updateDimensionProperties":{"range":{"sheetId":SID,"dimension":"ROWS","startIndex":i,"endIndex":i+1},"properties":{"pixelSize":34},"fields":"pixelSize"}})
for kind,(f,h) in KF.items():
    for a,b in runs(lambda r:r["kind"]==kind):
        if f: req.append({"repeatCell":{"range":G(a,b),"cell":{"userEnteredFormat":f},"fields":fmask(f)}})
        if h: req.append({"updateDimensionProperties":{"range":{"sheetId":SID,"dimension":"ROWS","startIndex":a,"endIndex":b},"properties":{"pixelSize":h},"fields":"pixelSize"}})
for a,b in runs(lambda r:r["kind"]=="kv"):
    req.append({"repeatCell":{"range":G(a,b,0,2),"cell":{"userEnteredFormat":{"textFormat":tf(bold=True,size=10,color=MUTED)}},"fields":"userEnteredFormat.textFormat.bold,userEnteredFormat.textFormat.fontSize,userEnteredFormat.textFormat.foregroundColorStyle"}})
for a,b in runs(lambda r:r["kind"]=="row"):
    req.append({"repeatCell":{"range":G(a,b,0,1),"cell":{"userEnteredFormat":{"textFormat":tf(bold=True)}},"fields":"userEnteredFormat.textFormat.bold"}})
for a,b in runs(lambda r:r["status"]):
    req.append({"setDataValidation":{"range":G(a,b,4,5),"rule":{"condition":{"type":"ONE_OF_LIST","values":[{"userEnteredValue":"✓ OK"},{"userEnteredValue":"à vérifier"},{"userEnteredValue":"à faire"}]},"showCustomUi":True,"strict":False}}})
req.append({"repeatCell":{"range":G(0,len(rows)+20,4,5),"cell":{"userEnteredFormat":{"horizontalAlignment":"CENTER"}},"fields":"userEnteredFormat.horizontalAlignment"}})
vals2=[[ (c.get("userEnteredValue",{}).get("stringValue") if "stringValue" in c.get("userEnteredValue",{}) else c.get("userEnteredValue",{}).get("formulaValue", c.get("userEnteredValue",{}).get("numberValue",""))) if c else "" for c in rd["values"]] for rd in rowdata]
json.dump(vals2, open(sys.argv[2].replace(".json",".values.json"),"w"), ensure_ascii=False, separators=(",",":"))
for i in []:
    rng = {"sheetId": SID, "startRowIndex": i, "endRowIndex": i + 1, "startColumnIndex": 4, "endColumnIndex": 5}
    req.append({"setDataValidation": {"range": rng, "rule": {"condition": {"type": "ONE_OF_LIST", "values": [{"userEnteredValue": "✓ OK"}, {"userEnteredValue": "à vérifier"}, {"userEnteredValue": "à faire"}]}, "showCustomUi": True, "strict": False}}})
    req.append({"repeatCell": {"range": rng, "cell": {"userEnteredFormat": {"horizontalAlignment": "CENTER", "textFormat": {"bold": True, "fontSize": 10, "fontFamily": "Atkinson Hyperlegible"}}}, "fields": "userEnteredFormat.horizontalAlignment,userEnteredFormat.textFormat"}})
colE = {"sheetId": SID, "startRowIndex": 0, "endRowIndex": N + 20, "startColumnIndex": 4, "endColumnIndex": 5}
for txt, bg, fg in (("à vérifier", "#e9e1fb", "#7246d6"), ("à faire", "#f8dde3", "#9b1c3c"), ("✓ OK", "#dcf5e6", "#1f9d57")):
    req.append({"addConditionalFormatRule": {"index": 0, "rule": {"ranges": [colE], "booleanRule": {"condition": {"type": "TEXT_EQ", "values": [{"userEnteredValue": txt}]}, "format": {"backgroundColorStyle": {"rgbColor": rgb(bg)}, "textFormat": {"foregroundColorStyle": {"rgbColor": rgb(fg)}}}}}}})
if title:
    req.append({"updateSpreadsheetProperties": {"properties": {"title": title}, "fields": "title"}})
json.dump(req, open(sys.argv[2], "w"), ensure_ascii=False, separators=(",", ":"))
print(sys.argv[2], len(req), "requests", os.path.getsize(sys.argv[2]), "bytes", N, "rows")
