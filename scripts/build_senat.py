#!/usr/bin/env python3
"""Construit senat.json : amendements déposés au Sénat sur le PLF 2027 (texte n° 155, session 2026-2027),
à partir du « jeu complet » CSV publié par le Sénat (Ameli). Exécuté par GitHub Actions avec la collecte AN.
Même format de lignes que amendements.json, avec ch = "S"."""
import csv, io, json, os, re, sys, time, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_amendements import text, resume, cgi_refs  # noqa: E402

SESSION, NUM = "2026-2027", "155"
CSV_URL = f"https://www.senat.fr/amendements/{SESSION}/{NUM}/jeu_complet_{SESSION}_{NUM}.csv"
UA = {"User-Agent": "Mozilla/5.0 (veille-plf-2027)"}

SORTS = {
    "recevable art. 40 c / lolf": "A discuter",
    "en attente de recevabilité financière": "En traitement",
    "": "En traitement",
    "cet amendement est retiré avant séance": "Retiré avant séance",
    "cet amendement n'a pas été soutenu": "Non soutenu",
}


def fetch(url, tries=3):
    for i in range(tries):
        try:
            print("GET", url, flush=True)
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=300) as r:
                d = r.read()
            print("  ->", len(d) // 1024, "Ko", flush=True)
            return d
        except Exception as e:
            print("  !!", e, flush=True)
            time.sleep(5 * (i + 1))
    return None


def sort_of(s):
    s = re.sub(r"\s+", " ", s or "").strip()
    return SORTS.get(s.lower(), s)


def art_of(sub):
    s = re.sub(r"\s+", " ", sub or "").strip()
    m = re.match(r"^art\.?\s*add\.?\s*(après|avant)\s+(?:l.)?article\s+(.+)$", s, re.I)
    if m:
        return f"{'APRÈS' if m.group(1).lower().startswith('apr') else 'AVANT'} ART. {m.group(2).upper()}"
    m = re.match(r"^article\s+(.+)$", s, re.I)
    if m:
        n = m.group(1).upper()
        return "ART. " + ("1ER" if n in ("PREMIER", "1") else n)
    return s


def auteur(a):
    a = re.sub(r"\s+", " ", a or "").strip()
    # « M. HUSSON » -> « M. Husson »
    return re.sub(r"\b([A-ZÀ-ÖØ-Ý][A-ZÀ-ÖØ-Ý'\-]+)\b", lambda m: m.group(1).capitalize() if len(m.group(1)) > 1 else m.group(1), a)


def main(out="senat.json"):
    raw = fetch(CSV_URL)
    if not raw:
        print("ERREUR : jeu complet du Sénat indisponible", flush=True)
        sys.exit(1)
    t = raw.decode("cp1252", "replace")
    if t.startswith("sep="):
        t = t.split("\n", 1)[1]
    rd = csv.DictReader(io.StringIO(t), delimiter="\t")
    rows, textes = [], []
    for x in rd:
        x = {(k or "").strip(): (v or "") for k, v in x.items()}
        num = x.get("Numéro", "").strip()
        expo_full = text(x.get("Objet", ""), 100000)
        disp_full = text(x.get("Dispositif", ""), 100000)
        if not num or not (expo_full or disp_full):
            continue   # retirés avant séance : fiche vide
        nature = x.get("Nature", "").strip()
        art = art_of(x.get("Subdivision", ""))
        s = sort_of(x.get("Sort", ""))
        url = x.get("Url amendement", "").strip()
        if url.startswith("//"):
            url = "https:" + url
        nom = x.get("Au nom de", "").strip()
        rows.append({
            "n": num, "ch": "S", "d": x.get("Date de dépôt", "").strip()[:10],
            "ds": x.get("Date de saisie du sort", "").strip()[:10], "s": s, "art": art,
            "aut": auteur(x.get("Auteur", "")), "g": nom.replace("groupe ", "") if nom.startswith("groupe") else nom,
            "r": resume(expo_full, disp_full, art), "k": cgi_refs(disp_full, expo_full),
            "x": text(expo_full, 700), "p": text(disp_full, 260), "c": "séance", "u": url,
            **({"sa": 1} if nature.upper().startswith("S/") else {}),
        })
        if num.startswith("I-"):
            textes.append({"n": num, "art": art, "s": s, "e": text(expo_full, 2500), "p": text(disp_full, 2500)})
    if not rows:
        print("ERREUR : aucun amendement lu", flush=True)
        sys.exit(1)
    try:
        res = json.load(open("resumes_senat.json", encoding="utf-8"))
    except Exception:
        res = {}
    for r in rows:
        if res.get(r["n"]):
            r["r"] = res[r["n"]]; r["rs"] = 1
    rows.sort(key=lambda r: (r["ds"] or r["d"]), reverse=True)
    from collections import Counter
    print("amendements Sénat :", len(rows), "| statuts :", Counter(r["s"] for r in rows).most_common(12), flush=True)
    os.makedirs("textes", exist_ok=True)
    with open("textes/senat_premiere_partie.json", "w", encoding="utf-8") as f:
        json.dump(textes, f, ensure_ascii=False, separators=(",", ":"))
    meta = {"maj": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "texte": f"PLF 2027 (Sénat n° {NUM}, {SESSION})",
            "total": len(rows), "source": "Jeu complet des amendements publié par le Sénat",
            "liste": f"https://www.senat.fr/amendements/{SESSION}/{NUM}/accueil.html"}
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "amendements": rows}, f, ensure_ascii=False, separators=(",", ":"))
    print("écrit", out, os.path.getsize(out) // 1024, "Ko", flush=True)


if __name__ == "__main__":
    main(*sys.argv[1:])
