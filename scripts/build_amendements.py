#!/usr/bin/env python3
"""Construit amendements.json : tous les amendements déposés sur le PLF 2027 (AN, texte n° 3210),
à partir de l'open data de l'Assemblée nationale. Exécuté chaque jour par GitHub Actions."""
import urllib.error
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


def S(v):
    if isinstance(v, str):
        return v
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, dict):
        for k in ("libelle", "#text", "value"):
            if isinstance(v.get(k), str):
                return v[k]
    return ""


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
    t = html.unescape(re.sub(r"<[^>]+>", " ", h)).replace("&amp;", "&")
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) <= n:
        return t
    cut = t[: n]
    m = max(cut.rfind(". "), cut.rfind(" ; "), cut.rfind("! "), cut.rfind("? "))
    return cut[: m + 1] if m > n * 0.5 else cut.rsplit(" ", 1)[0] + "…"


SENT = re.compile(r"(?<=[.!?…])\s+(?=[«\"(A-ZÀ-ÖØ-Ý])")
STRONG = re.compile(r"\b(cet|ce|le présent|du présent|notre|leur|un)\s+(sous-)?amendement|cet article additionnel|par le présent|^il est proposé|^nous proposons|la (présente )?mesure proposée|le dispositif proposé|^il s.agit de|^l.objet de cet|^cet article|^le groupe [^.]{0,60} (propose|souhaite|vise)", re.I)
GOOD = re.compile(r"(amendement|article additionnel|dispositif|présente? (mesure|proposition))[^.]{0,120}?\b(vise|visent|a pour (objet|but|effet)|ont pour objet|propose|tend|prévoi|permet|supprim|rétabli|port|étend|exclu|ouvr|instaur|cré|institu|relèv|abaiss|rédui|augment|proro|plafonn|exon|limit|appliqu|align|corrig|précis|modifi|remplac|ramèn|fix|introdui|sécuris|rend|transform|interdi|soumet|assujetti|mett?r?e? fin|revien)", re.I)
GENERIC = re.compile(r"(aborde ce budget|pacte entre les générations|nos enfants en hériteront|amendement d.appel|amendement de repli\.?$)", re.I)


def sentences(t):
    return [x.strip() for x in SENT.split(t) if len(x.strip()) > 2]


def resume(expo, disp, art):
    ss = sentences(expo)
    pick = []
    cands = [i for i, x in enumerate(ss) if STRONG.search(x) and GOOD.search(x) and not GENERIC.search(x)]
    cands = cands or [i for i, x in enumerate(ss) if STRONG.search(x) and not GENERIC.search(x)]
    cands = cands or [i for i, x in enumerate(ss) if GOOD.search(x) and not GENERIC.search(x)]
    for i in cands[:1]:
        x = ss[i]
        if True:
            pick = [x]
            if i > 0 and re.search(r"\b(ces|cette|celle-ci|celui-ci|ce dispositif|ce régime|cette taxe|cette mesure)\b", x, re.I) and len(ss[i - 1]) < 260 and not GENERIC.search(ss[i - 1]):
                pick.insert(0, ss[i - 1])
            elif len(x) < 90 and i + 1 < len(ss):
                pick.append(ss[i + 1])
            break
    if not pick:
        good = [x for x in ss if not GENERIC.search(x)]
        if good:
            pick = [good[0]] + ([good[1]] if len(good[0]) < 90 and len(good) > 1 else [])
    r = " ".join(pick)
    if len(r) > 480:
        r = r[:480].rsplit(" ", 1)[0] + "…"
    d = disp.strip()
    if re.match(r"^Supprimer (cet|l.)article", d, re.I):
        r = (f"Supprime l'{art.lower()}." if art else "Amendement de suppression.") + (" " + r if r else "")
    elif not r and d:
        r = d if len(d) <= 300 else d[:300].rsplit(" ", 1)[0] + "…"
    return r


PENDING = ("A discuter", "En traitement", "En recevabilité", "")


def refresh(rows):
    """Le fichier global de l'open data est en retard sur les votes : pour chaque amendement encore
    « à discuter » ou « en traitement », on relit sa fiche officielle individuelle (mise à jour en continu)."""
    from concurrent.futures import ThreadPoolExecutor
    todo = [r for r in rows if r.get("uid") and r.get("s", "") in PENDING]
    print("statuts à vérifier sur les fiches individuelles :", len(todo), flush=True)

    def one(r):
        url = f"https://www.assemblee-nationale.fr/dyn/opendata/{r['uid']}.xml"
        for i in range(2):
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as resp:
                    x = resp.read().decode("utf-8", "replace")
                break
            except Exception:
                x = ""
                time.sleep(1 + i)
        if not x:
            return r, None
        def tag(name):
            m = re.search(rf"<{name}>([^<]*)</{name}>", x)
            return html.unescape(m.group(1)).strip() if m else ""
        sort = tag("sort")
        m_e = re.search(r"<etat>.*?<libelle>([^<]*)</libelle>", x, re.S)
        m_se = re.search(r"<sousEtat>.*?<libelle>([^<]*)</libelle>", x, re.S)
        st = sort or (html.unescape(m_se.group(1)).strip() if m_se else "") or (html.unescape(m_e.group(1)).strip() if m_e else "")
        sd = tag("seanceDiscussionRef")
        if sd.startswith("RU"):
            r["_sd"] = sd
        return r, (st, tag("dateSort")[:10])

    changed = 0
    for passe, workers in ((1, 6), (2, 2), (3, 1)):
        failed = []
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for r, res in ex.map(one, todo):
                if res is None:
                    failed.append(r)
                    continue
                st, ds = res
                if st and st != r["s"]:
                    r["s"] = st
                    changed += 1
                if ds and not r.get("ds"):
                    r["ds"] = ds
        print(f"passe {passe} : {len(todo) - len(failed)} lues, {len(failed)} illisibles", flush=True)
        if not failed:
            break
        todo = failed
        time.sleep(20)
    print(f"statuts mis à jour : {changed} | fiches restées illisibles : {len(failed)}", flush=True)


SUFX = r"(?:bis|ter|quater|quinquies|sexies|septies|octies|nonies|decies|undecies|duodecies|terdecies|quaterdecies|quindecies|sexdecies|septdecies|octodecies|novodecies|vicies)"
REF = rf"(?-i:(?:L\.?\s*|R\.?\s*|A\.?\s*)?)\d{{1,4}}(?:\s*-\s*\d{{1,2}}(?!\d))?(?:\s+(?:(?-i:[A-Z]{{1,2}})|{SUFX})\b){{0,4}}"
REFLIST = re.compile(rf"\barticles?\s+({REF}(?:\s*(?:,|\bet\b|\bou\b|\bà\b)\s*{REF})*)", re.I)
CODE = re.compile(r"^[^.;]{0,90}?\b(du\s+code\s+général\s+des\s+impôts|du\s+CGI|du\s+même\s+code|dudit\s+code|du\s+livre\s+des\s+procédures\s+fiscales|du\s+LPF|de\s+l.annexe\s+[IV]+\s+au\s+code\s+général)", re.I)
OTHER = re.compile(r"^[^.;]{0,40}?\b(du\s+code\s+(de\s+la|du|de\s+l|des|monétaire|civil|de\s+commerce|rural|des\s+douanes|de\s+la\s+sécurité)|de\s+la\s+loi|de\s+l.ordonnance|du\s+décret|de\s+la\s+présente\s+loi|du\s+présent\s+projet)", re.I)


def norm_ref(x):
    x = re.sub(r"\s+", " ", x.replace("\u2011", "-").replace("\u2010", "-")).strip().lower()
    x = re.sub(r"\s*-\s*", "-", x)
    x = re.sub(r"^([lra])\.?\s*", r"\1. ", x) if re.match(r"^[lra]\.?\s*\d", x) else x
    return x


def cgi_refs(*texts):
    out = []
    for t in texts:
        t = (t or "").replace("\u00a0", " ").replace("\u202f", " ").replace("\u2011", "-")
        for m in REFLIST.finditer(t):
            after = t[m.end(): m.end() + 120]
            if OTHER.match(after) and not CODE.match(after):
                continue
            if not CODE.match(after):
                continue
            for ref in re.findall(REF, m.group(1)):
                r = norm_ref(ref)
                if r and r not in out:
                    out.append(r)
    return out[:30]


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


# ---------------------------------------------------------------- liens vers les débats
BASE = "https://www.assemblee-nationale.fr"
CF_ORGANE = "PO59048"   # commission des finances
AGENDA_URL = f"https://data.assemblee-nationale.fr/static/openData/repository/{LEG}/vp/reunions/Agenda.json.zip"


def get_page(url, tries=3):
    """Renvoie (url finale, html) ou (None, '')."""
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (veille-plf-2027)"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.geturl(), resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None, ""
            time.sleep(2 + 3 * i)
        except Exception:
            time.sleep(2 + 3 * i)
    return None, ""


def seance_links(rows):
    """Séance publique : chaque amendement porte la référence de la séance où il a été discuté ;
    le sommaire du compte rendu donne une ancre par amendement (classe crs-sommaire-lienAdt)."""
    from concurrent.futures import ThreadPoolExecutor
    refs = sorted({r["_sd"] for r in rows if r.get("_sd", "").startswith("RU")})
    print("séances de discussion référencées :", len(refs), flush=True)

    def one(ref):
        url, h = get_page(f"{BASE}/dyn/crSeanceRedirect/{ref}")
        if not url or "/comptes-rendus/seance/" not in url:
            return ref, None, {}
        url = url.split("#")[0]
        anchors = {}
        for m in re.finditer(r'class="crs-sommaire-lienAdt"\s+href="#([^"]+)"\s*>([^<]+)<', h):
            for n in re.findall(r"\d+", m.group(2)):
                anchors.setdefault(n, m.group(1))
        return ref, url, anchors

    with ThreadPoolExecutor(max_workers=4) as ex:
        res = {ref: (u, a) for ref, u, a in ex.map(one, refs)}
    ok = deep = 0
    for r in rows:
        u, anchors = res.get(r.get("_sd", ""), (None, {}))
        if not u:
            continue
        n = re.sub(r"\D", "", re.sub(r"^I+-", "", r["n"]))
        if n in anchors:
            r["dl"] = f"{u}#{anchors[n]}"; deep += 1
        else:
            r["dl"] = u
        ok += 1
    print(f"liens débats séance : {ok} (dont {deep} pointant sur le passage) | comptes rendus indisponibles : {sum(1 for v in res.values() if not v[0])}", flush=True)


def plain(h):
    h = re.sub(r"<[^>]+>", "", h)
    h = html.unescape(h).replace("‑", "-").replace("‐", "-").replace("\xa0", " ")
    return h


def commission_links(rows):
    """Commission des finances : comptes rendus des réunions (open data « Agenda » → compteRenduRef),
    puis recherche de la première mention de chaque amendement I-CF / II-CF ; lien avec fragment de texte."""
    cf = [r for r in rows if re.match(r"^I+-CF\d+$", r["n"])]
    if not cf:
        return
    data = fetch(AGENDA_URL)
    if not data:
        print("agenda indisponible : pas de liens débats en commission", flush=True)
        return
    reus = []
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for name in z.namelist():
            if not name.endswith(".json"):
                continue
            raw = z.read(name)
            if CF_ORGANE.encode() not in raw or b"3210" not in raw:
                continue
            try:
                ru = json.loads(raw).get("reunion", {})
            except Exception:
                continue
            if ru.get("organeReuniRef") != CF_ORGANE:
                continue
            ts = S(ru.get("timeStampDebut"))
            cr = S(ru.get("compteRenduRef"))
            if ts >= "2026-10-01" and cr.startswith("CR"):
                reus.append((ts, cr))
    reus.sort()
    print("réunions de la commission des finances sur le PLF avec compte rendu :", len(reus), flush=True)
    found = {}   # numéro -> [(date, url)]
    for ts, cr in reus:
        url = f"{BASE}/dyn/opendata/{cr}.html"
        u, h = get_page(url)
        if not u or len(h) < 5000:
            continue
        t = plain(h)
        for m in re.finditer(r"(?<![A-Z])(I{1,2})\s?-\s?CF\s?(\d+)", t):
            key = f"{m.group(1)}-CF{m.group(2)}"
            lst = found.setdefault(key, [])
            if not lst or lst[-1][1] != url:
                lst.append((ts[:10], url))
    n = 0
    for r in cf:
        lst = found.get(r["n"])
        if not lst:
            continue
        same = [x for x in lst if r.get("ds") and x[0] == r["ds"]]
        d, url = (same or lst)[0]
        num = re.sub(r"^I+-", "", r["n"])
        r["dl"] = f"{url}#:~:text={num}"
        n += 1
    print(f"liens débats commission : {n} / {len(cf)} amendements de commission", flush=True)


def debats(rows):
    try:
        seance_links(rows)
    except Exception as e:
        print("!! liens séance :", e, flush=True)
    try:
        commission_links(rows)
    except Exception as e:
        print("!! liens commission :", e, flush=True)


# ---------------------------------------------------------------- rapport général (tome II)
RAPPORT = {
    "c": ("RAPPANR5L17B3291-tII-v1", "commentaire"),   # commentaires des articles (1re partie)
    "e": ("RAPPANR5L17B3291-tII-v2", "examen"),        # comptes rendus de l'examen des articles en commission
}
ART_RE = re.compile(r"^(?:(après|avant)\s+l\W?\s*)?article\s+(liminaire|premier|1er|\d+)(\s+(?:%s))?\b" % "bis|ter|quater|quinquies|sexies|septies|octies|nonies|decies", re.I)


def art_key(t):
    t = re.sub(r"\s+", " ", t.replace("\xa0", " ")).strip()
    m = ART_RE.match(t)
    if not m:
        return None
    n = m.group(2).lower()
    n = "1ER" if n in ("premier", "1er", "1") else n.upper()
    k = f"ART. {n}{(' ' + m.group(3).strip().upper()) if m.group(3) else ''}"
    if m.group(1):
        k = ("APRÈS " if m.group(1).lower().startswith("apr") else "AVANT ") + k
    return k


def rapport_links():
    out = {}
    for code, (uid, label) in RAPPORT.items():
        url = f"{BASE}/dyn/opendata/{uid}.html"
        u, h = get_page(url)
        if not u:
            print("rapport indisponible :", uid, flush=True)
            continue
        n = 0
        for m in re.finditer(r'<a href="#([^"]+)"[^>]*>(.*?)</a>', h, re.S):
            t = html.unescape(re.sub(r"<[^>]+>", "", m.group(2)))
            k = art_key(t)
            if k and code not in out.setdefault(k, {}):
                out[k][code] = f"{url}#{m.group(1)}"; n += 1
        print(f"rapport {label} ({uid}) : {n} articles ancrés", flush=True)
    return out


TEXTES = []


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
                print("EXEMPLE BRUT :", json.dumps(a, ensure_ascii=False)[:3000], flush=True)
            ident = a.get("identification")
            ident = ident if isinstance(ident, dict) else {}
            num = S(ident.get("numeroLong")) or S(find_key(a, "numeroLong"))
            ordre = S(ident.get("numeroOrdreDepot")) or S(find_key(a, "numeroOrdreDepot"))
            prefixe = S(ident.get("prefixeOrganeExamen"))
            uid = S(a.get("uid"))
            cv = a.get("cycleDeVie")
            cv = cv if isinstance(cv, dict) else {}
            sort = S(cv.get("sort"))
            etat = S(get(cv, "etatDesTraitements", "etat", "libelle"))
            sous = S(get(cv, "etatDesTraitements", "sousEtat", "libelle"))
            statut = sort or sous or etat
            div = get(a, "pointeurFragmentTexte", "division")
            div = div if isinstance(div, dict) else {}
            art = S(div.get("articleDesignationCourte")) or S(div.get("titre"))
            pos = S(div.get("avant_A_Apres"))
            if pos and pos.lower() not in ("a", "à") and art and not art.lower().startswith(("avant", "après", "apres")):
                art = f"{'Après' if pos.lower().startswith('apr') else 'Avant'} {art}"
            sig = a.get("signataires")
            sig = sig if isinstance(sig, dict) else {}
            aut = html.unescape(S(sig.get("libelle"))).replace("\xa0", " ")
            aut = re.sub(r"\s+", " ", aut).strip()
            if "," in aut or " et " in aut:
                aut = re.split(r",| et ", aut)[0].strip() + " et al."
            gref = S(get(sig, "auteur", "groupePolitiqueRef"))
            typeaut = S(get(sig, "auteur", "typeAuteur"))
            corps = get(a, "corps", "contenuAuteur") or a.get("corps") or {}
            expo_full = text(corps.get("exposeSommaire") if isinstance(corps, dict) else "", 100000)
            disp_full = text(corps.get("dispositif") if isinstance(corps, dict) else "", 100000)
            expo = text(expo_full, 700)
            disp = text(disp_full, 260)
            res = resume(expo_full, disp_full, art)
            refs = cgi_refs(disp_full, expo_full)
            cf = prefixe.upper() == "CF" or re.match(r"^I+-CF", str(num) or "") is not None
            autre_org = bool(prefixe) and prefixe.upper() not in ("AN", "CF")
            partie = "B" if str(num).startswith("II-") else "A"
            m_num = re.search(r"(\d+)", re.sub(r"^I+-", "", str(num)))
            n_only = m_num.group(1) if m_num else ""
            url = f"https://www.assemblee-nationale.fr/dyn/{LEG}/amendements/3210{partie}/{'CION_FIN/CF' if cf else 'AN/'}{n_only}" if (n_only and not autre_org) else ""
            puid = S(a.get("amendementParentRef"))
            if str(num).startswith("I-"):
                TEXTES.append({"n": num, "art": art, "e": text(expo_full, 2500), "p": text(disp_full, 2500)})
            rows.append({
                "n": num, "o": ordre, "uid": uid, "_puid": puid, "_sd": S(a.get("seanceDiscussionRef")),
                "d": S(cv.get("dateDepot"))[:10], "ds": S(cv.get("dateSort"))[:10],
                "s": statut, "art": art, "aut": aut if aut else typeaut,
                "g": grp.get(gref, ""), "r": res, "k": refs, "x": expo, "p": disp,
                "c": "commission" if (cf or autre_org) else "séance", "u": url,
            })
    if sample is not None:
        print("EXEMPLE (clés) :", list(sample.keys()), flush=True)
        print(json.dumps(sample, ensure_ascii=False)[:2500], flush=True)
    rows.sort(key=lambda r: (r["c"] != "séance", -int(re.sub(r"\D", "", str(r["o"])) or 0)))
    refresh(rows)
    by_uid = {r["uid"]: r["n"] for r in rows if r.get("uid")}
    for r in rows:
        pu = r.pop("_puid", "")
        if pu and pu in by_uid:
            r["par"] = by_uid[pu]
    print("sous-amendements rattachés :", sum(1 for r in rows if r.get("par")), flush=True)
    debats(rows)
    for r in rows:
        r.pop("uid", None); r.pop("o", None); r.pop("_sd", None)
    from collections import Counter
    print("amendements :", len(rows), "| statuts :", Counter(r["s"] for r in rows).most_common(12), flush=True)
    if not rows:
        print("ERREUR : aucun amendement trouvé pour", TEXTE, flush=True)
        sys.exit(1)
    from collections import Counter as _C
    print("statuts après vérification :", _C(r["s"] for r in rows).most_common(10), flush=True)
    print("amendements avec références CGI/LPF :", sum(1 for r in rows if r.get("k")), flush=True)
    # textes intégraux de la 1re partie (pour la rédaction des résumés) et résumés rédigés
    os.makedirs("textes", exist_ok=True)
    stat = {r["n"]: r["s"] for r in rows}
    for t in TEXTES:
        t["s"] = stat.get(t["n"], "")
    with open("textes/premiere_partie.json", "w", encoding="utf-8") as f:
        json.dump(TEXTES, f, ensure_ascii=False, separators=(",", ":"))
    try:
        res = json.load(open("resumes.json", encoding="utf-8"))
    except Exception:
        res = {}
    nres = 0
    for r in rows:
        if res.get(r["n"]):
            r["r"] = res[r["n"]]; r["rs"] = 1; nres += 1
    print("résumés rédigés appliqués :", nres, flush=True)
    meta = {"maj": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "texte": "PLF 2027 (AN n° 3210)",
            "total": len(rows), "source": "Open data de l'Assemblée nationale"}
    try:
        meta["rap"] = rapport_links()
    except Exception as e:
        print("!! rapport :", e, flush=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "amendements": rows}, f, ensure_ascii=False, separators=(",", ":"))
    print("écrit", out, os.path.getsize(out) // 1024, "Ko", flush=True)


if __name__ == "__main__":
    main(*sys.argv[1:])
