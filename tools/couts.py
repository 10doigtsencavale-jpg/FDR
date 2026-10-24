"""Ajoute à une fiche FDR les colonnes de coûts (F « 💶 Prix », G « 🧾 Réf. · remarque ») et le bloc
« 💶 COÛTS » sous « — fin de la fiche — » (l'appli ne lit que A:E jusqu'à « — fin », donc rien de tout ça
n'apparaît dans l'appli).

Usage : python3 -I couts.py <colA.json> <columnCount> <out_prefix>
   ou : python3 -I couts.py <ligne en-tête trajets> <ligne 🛏️ HÉBERGEMENT|0> <ligne « — fin »> <columnCount> <bloc déjà là 0|1> <out_prefix>
  colA.json   : résultat get_values de FDR!A1:A250 (ou son tableau « values »)
  columnCount : nombre de colonnes actuel de l'onglet FDR (get_spreadsheet)
Sorties :
  <out_prefix>.req.json    → update_spreadsheet (requests)
  <out_prefix>.values.json → liste de {range, values} à écrire avec update_values (USER_ENTERED)
  <out_prefix>.info.json   → {traj_hdr, nom_rows, fin, deja} (numéros de ligne 1-based)
Idempotent : si le bloc « 💶 COÛTS » existe déjà, ne réécrit que ce qui manque.
"""
import json, sys

if len(sys.argv) == 7:   # mode direct : <traj_hdr> <dodo|0> <fin> <columnCount> <deja 0|1> <out_prefix>
    traj_hdr, dodo, fin, ncols, deja = [int(x) for x in sys.argv[1:6]]; out = sys.argv[6]
    dodo = dodo or None; couts = bool(deja); nom_rows = []
else:
    vals = json.load(open(sys.argv[1]))
    vals = vals.get("values", vals) if isinstance(vals, dict) else vals
    ncols = int(sys.argv[2]); out = sys.argv[3]
    A = [(r[0] if r else "").strip() for r in vals]
    traj_hdr = fin = couts = dodo = None; in_dodo = False; nom_rows = []
    for i, a in enumerate(A, 1):
        if a.startswith("🚆 TRAJETS"): traj_hdr = i + 1
        if a.startswith("🛏️ HÉBERGEMENT"): in_dodo = True; dodo = i; continue
        if in_dodo and a.startswith(("📞 CONTACTS", "🚗 ACCÈS", "🎵 SETLIST", "👕 TENUE", "📝 INFOS", "— fin")):
            in_dodo = False
        if in_dodo and a == "Nom": nom_rows.append(i)
        if a.startswith("— fin"): fin = i
        if a.startswith("💶 COÛTS"): couts = i
    if not fin or not traj_hdr:
        print(json.dumps({"erreur": "fiche non reconnue (pas de « 🚆 TRAJETS » ou de « — fin »)"})); sys.exit(1)

def rgb(h): h = h.lstrip('#'); return {"red": int(h[0:2], 16)/255, "green": int(h[2:4], 16)/255, "blue": int(h[4:6], 16)/255}
G = lambda r0, r1, c0, c1: {"sheetId": 0, "startRowIndex": r0, "endRowIndex": r1, "startColumnIndex": c0, "endColumnIndex": c1}
req = []
if ncols < 7:
    req.append({"appendDimension": {"sheetId": 0, "dimension": "COLUMNS", "length": 7 - ncols}})
req.append({"updateDimensionProperties": {"range": {"sheetId": 0, "dimension": "COLUMNS", "startIndex": 5, "endIndex": 6}, "properties": {"pixelSize": 90}, "fields": "pixelSize"}})
req.append({"updateDimensionProperties": {"range": {"sheetId": 0, "dimension": "COLUMNS", "startIndex": 6, "endIndex": 7}, "properties": {"pixelSize": 220}, "fields": "pixelSize"}})
# en-têtes F/G : gras, fond doré doux (couleur hors code vert/orange/rouge)
req.append({"repeatCell": {"range": G(traj_hdr - 1, traj_hdr, 5, 7), "cell": {"userEnteredFormat": {"textFormat": {"bold": True}, "backgroundColorStyle": {"rgbColor": rgb("#f6edd9")}}}, "fields": "userEnteredFormat.textFormat.bold,userEnteredFormat.backgroundColorStyle"}})
# prix : format euro
req.append({"repeatCell": {"range": G(0, fin + 6, 5, 6), "cell": {"userEnteredFormat": {"numberFormat": {"type": "CURRENCY", "pattern": "#,##0.00 €"}, "horizontalAlignment": "RIGHT"}}, "fields": "userEnteredFormat.numberFormat,userEnteredFormat.horizontalAlignment"}})
req.append({"repeatCell": {"range": G(0, fin + 6, 6, 7), "cell": {"userEnteredFormat": {"wrapStrategy": "WRAP", "textFormat": {"fontSize": 9}}}, "fields": "userEnteredFormat.wrapStrategy,userEnteredFormat.textFormat.fontSize"}})

values = [{"range": f"FDR!F{traj_hdr}:G{traj_hdr}", "values": [["💶 Prix", "🧾 Réf. · remarque"]]}]
if dodo:  # prix d'un logement : colonne F de sa ligne « Nom » (en-tête sur la ligne de section, hors A:E)
    values.append({"range": f"FDR!F{dodo}:G{dodo}", "values": [["💶 Prix", "🧾 Réf. · remarque"]]})
if not couts:
    s = fin + 2; last = fin - 1
    values.append({"range": f"FDR!A{s}:C{s + 3}", "values": [
        ["💶 COÛTS — pas visible dans l'appli", "", ""],
        ["Total transport", "", f'=SUMIF(A$1:A${last};"<>Nom";F$1:F${last})'],
        ["Total hébergement", "", f'=SUMIF(A$1:A${last};"Nom";F$1:F${last})'],
        ["Total général", "", f"=C{s + 1}+C{s + 2}"]]})
    req.append({"repeatCell": {"range": G(s - 1, s, 0, 7), "cell": {"userEnteredFormat": {"textFormat": {"bold": True}, "backgroundColorStyle": {"rgbColor": rgb("#f6edd9")}}}, "fields": "userEnteredFormat.textFormat.bold,userEnteredFormat.backgroundColorStyle"}})
    req.append({"repeatCell": {"range": G(s, s + 3, 2, 3), "cell": {"userEnteredFormat": {"numberFormat": {"type": "CURRENCY", "pattern": "#,##0.00 €"}, "textFormat": {"bold": True}}}, "fields": "userEnteredFormat.numberFormat,userEnteredFormat.textFormat.bold"}})

json.dump(req, open(out + ".req.json", "w"), ensure_ascii=False)
json.dump(values, open(out + ".values.json", "w"), ensure_ascii=False)
json.dump({"traj_hdr": traj_hdr, "nom_rows": nom_rows, "fin": fin, "deja": bool(couts)}, open(out + ".info.json", "w"))
print(json.dumps({"traj_hdr": traj_hdr, "nom_rows": nom_rows, "fin": fin, "deja": bool(couts)}))
