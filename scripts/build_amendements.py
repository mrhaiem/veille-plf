#!/usr/bin/env python3
"""Construit amendements.json : tous les amendements déposés sur le PLF 2027 (AN, texte n° 3210),
à partir de l'open data de l'Assemblée nationale. Exécuté chaque jour par GitHub Actions."""
import io, json, os, re, sys, time, urllib.request, zipfile, html

TEXTE = "B3210"          # PLF 2027
LEG = "17"
UA = {"User-Agent": "veille-plf-2027 (GitHub Actions)"}
AMDT_URLS = [
    f"https://data.assemblee-nationale.fr/static/openData/repository/{LEG}/loi/amendements_div_legis/Amendements.json.zip",
    f"https://data.assemblee-nationale.fr/static/openData/repository/{LEG}/loi/amendements_legis/Amendements.json.zip",
]
ORG_URLS = [
    f"https://data.assemblee-nationale.fr/static/openData/repository/{LEG}/amo/deputes_actifs_mandats_actifs_organes/AMO10_deputes_actifs_mandats_actifs_organes.json.zip",
    f"https://data.assemblee-nationale.fr/static/openData/repository/{LEG}/amo/tous_acteurs_mandats_organes_xi_legislature/AMO30_tous_acteurs_tous_mandats_tous_organes_historique.json.zip",
]


def fetch(url, tries=3):
    for i in range(tries):
        try:
            print("GET", url, flush=True)
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=600) as r:
                data = r.read()
            print("  ->", len(data) // 1024, "Ko", flush=True)
            return data
        except Exception as e:
            print("  !!", e, flush=True)
            time.sleep(5 * (i + 1))
    return None


def first(*urls):
    for u in urls:
        d = fetch(u)
        if d:
            return d
    return None


def get(o, *path):
    for p in path:
        if isinstance(o, dict):
            o = o.get(p)
        else:
            return None
    return o


def find_key(o, key):
    """Premier valeur trouvée pour une clé, en profondeur."""
    if isinstance(o, dict):
        if key in o and o[key] not in (None, "", {}):
            return o[key]
        for v in o.values():
            r = find_key(v, key)
            if r not in (None, "", {}):
                return r
    elif isinstance(o, list):
        for v in o:
            r = find_key(v, key)
            if r not in (None, "", {}):
                return r
    return None


def text(h, n):
    if not isinstance(h, str):
        return ""
    t = html.unescape(re.sub(r"<[^>]+>", " ", h))
    t = re.sub(r"\s+", " ", t).strip()
    return t if len(t) <= n else t[: n].rsplit(" ", 1)[0] + "…"


def groups_map():
    data = first(*ORG_URLS)
    m = {}
    if not data:
        return m
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for name in z.namelist():
            if "/organe/" not in name and not name.split("/")[-1].startswith("PO"):
                continue
            try:
                o = json.loads(z.read(name)).get("organe", {})
            except Exception:
                continue
            if o.get("codeType") == "GP" and o.get("uid"):
                m[o["uid"]] = o.get("libelleAbrev") or o.get("libelleAbrege") or o.get("libelle", "")
    print("groupes :", len(m), flush=True)
    return m


def main(out="amendements.json"):
    data = first(*AMDT_URLS)
    if not data:
        print("ERREUR : open data indisponible", flush=True)
        sys.exit(1)
    grp = groups_map()
    rows, sample = [], None
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = [n for n in z.namelist() if n.endswith(".json")]
        print("fichiers dans l'archive :", len(names), flush=True)
        cand = [n for n in names if TEXTE in n]
        print("fichiers du texte", TEXTE, ":", len(cand), flush=True)
        scan = cand if cand else names
        for name in scan:
            try:
                j = json.loads(z.read(name))
            except Exception:
                continue
            a = j.get("amendement", j)
            ref = json.dumps(get(a, "texteLegislatifRef") or a.get("texteLegislatifRef") or name)
            if TEXTE not in ref and TEXTE not in name:
                continue
            if sample is None:
                sample = a
            ident = a.get("identification", {}) or {}
            num = ident.get("numeroLong") or find_key(a, "numeroLong") or ""
            ordre = ident.get("numeroOrdreDepot") or find_key(a, "numeroOrdreDepot") or ""
            prefixe = ident.get("prefixeOrganeExamen") or ""
            uid = a.get("uid", "")
            cv = a.get("cycleDeVie", {}) or {}
            sort = cv.get("sort") or ""
            if isinstance(sort, dict):
                sort = sort.get("libelle") or sort.get("#text") or ""
            etat = get(cv, "etatDesTraitements", "etat", "libelle") or ""
            sous = get(cv, "etatDesTraitements", "sousEtat", "libelle") or ""
            statut = sort or sous or etat
            div = get(a, "pointeurFragmentTexte", "division") or {}
            art = div.get("articleDesignationCourte") or div.get("titre") or ""
            pos = div.get("avant_A_Apres") or ""
            if pos and pos.lower() not in ("a", "à") and art and not art.lower().startswith(("avant", "après", "apres")):
                art = f"{'Après' if pos.lower().startswith('apr') else 'Avant'} {art}"
            sig = a.get("signataires", {}) or {}
            aut = sig.get("libelle") or ""
            gref = get(sig, "auteur", "groupePolitiqueRef") or ""
            typeaut = get(sig, "auteur", "typeAuteur") or ""
            corps = get(a, "corps", "contenuAuteur") or a.get("corps") or {}
            expo = text(corps.get("exposeSommaire") if isinstance(corps, dict) else "", 700)
            disp = text(corps.get("dispositif") if isinstance(corps, dict) else "", 350)
            cf = "CF" in str(num) or "CION_FIN" in name or "CF" in prefixe
            partie = "B" if str(num).startswith("II-") else "A"
            n_only = re.sub(r"^I+-", "", str(num)).replace("CF", "")
            url = f"https://www.assemblee-nationale.fr/dyn/{LEG}/amendements/3210{partie}/{'CION_FIN/CF' if cf else 'AN/'}{n_only}" if n_only else ""
            rows.append({
                "n": num, "o": ordre, "uid": uid,
                "d": (cv.get("dateDepot") or "")[:10], "ds": (cv.get("dateSort") or "")[:10],
                "s": statut, "art": art, "aut": aut if aut else typeaut,
                "g": grp.get(gref, ""), "x": expo, "p": disp,
                "c": "commission" if cf else "séance", "u": url,
            })
    if sample is not None:
        print("EXEMPLE (clés) :", list(sample.keys()), flush=True)
        print(json.dumps(sample, ensure_ascii=False)[:2500], flush=True)
    rows.sort(key=lambda r: (r["c"] != "séance", -int(re.sub(r"\D", "", str(r["o"])) or 0)))
    from collections import Counter
    print("amendements :", len(rows), "| statuts :", Counter(r["s"] for r in rows).most_common(12), flush=True)
    if not rows:
        print("ERREUR : aucun amendement trouvé pour", TEXTE, flush=True)
        sys.exit(1)
    meta = {"maj": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "texte": "PLF 2027 (AN n° 3210)",
            "total": len(rows), "source": "Open data de l'Assemblée nationale"}
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "amendements": rows}, f, ensure_ascii=False, separators=(",", ":"))
    print("écrit", out, os.path.getsize(out) // 1024, "Ko", flush=True)


if __name__ == "__main__":
    main(*sys.argv[1:])
