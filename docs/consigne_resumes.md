# Résumés de portée des amendements au PLF 2027 (Assemblée nationale)

Lecteur : avocat fiscaliste d'affaires. Il lit UNE phrase et doit comprendre la PORTÉE de l'amendement, sans ouvrir le texte.

## Entrée
Un fichier JSON : liste d'objets {n (numéro), art (article du PLF visé), s (sort), e (exposé sommaire), p (dispositif = texte juridique de l'amendement)}. Les deux textes peuvent être tronqués (« … »).

## Sortie
Un fichier JSON objet {"<n>": "<résumé>", …} avec une entrée pour CHAQUE amendement de l'entrée.

## Règles du résumé
- Une seule phrase, 15 à 40 mots, commençant par un verbe à l'indicatif présent (« Porte… », « Supprime… », « Étend… », « Exclut… », « Crée… », « Plafonne… », « Reporte… »).
- Dis ce que l'amendement CHANGE concrètement : le dispositif ou l'impôt visé, le paramètre modifié (de X à Y), le champ (qui est concerné), la date d'effet si elle figure, et l'article du CGI/LPF quand il est cité (format « CGI, art. 219 »).
- Appuie-toi d'abord sur le dispositif (p), qui fait foi ; l'exposé (e) sert à comprendre l'intention et à nommer le régime. Si les deux divergent, suis le dispositif.
- Amendement de suppression d'article : « Supprime l'article N du PLF, qui prévoyait … » (décris en quelques mots ce que l'article prévoyait, d'après l'exposé).
- Sous-amendement : commence par « Sous-amendement : » puis la portée.
- Amendements rédactionnels, de coordination ou de précision : « Amendement rédactionnel / de coordination sur … » en le disant clairement.
- Plafonds de taxes affectées, crédits, tableaux : dis quel plafond ou quelle ressource est modifiée et de combien si c'est indiqué.
- RIEN D'INVENTÉ : aucun chiffre, taux, date, article ou effet absent des textes. Si le dispositif est tronqué et ne permet pas de connaître un paramètre, n'en parle pas. Pas d'opinion, pas de jugement (« injuste », « bienvenu »…), pas de « cet amendement vise à ».
- Français juridique impeccable, sans guillemets superflus, sans abréviations obscures (tu peux garder IS, TVA, CGI, LPF, PME, ETI, CIR, JEI, PLF).

## Exemples
- « Porte de 12 % à 16 % la quote-part de frais et charges réintégrée sur les plus-values de cession de titres de participation (CGI, art. 219, I-a quinquies), pour les exercices clos à compter du 31 décembre 2027. »
- « Supprime l'article 15 du PLF, qui prorogeait pour un troisième exercice la contribution exceptionnelle sur les bénéfices des grandes entreprises. »
- « Étend le suramortissement des investissements industriels 4.0 (CGI, art. 39 decies H) aux logiciels et équipements recourant à l'intelligence artificielle. »

## Contrôle final (obligatoire)
Vérifie par script : JSON valide, toutes les clés n présentes, aucune valeur vide, chaque résumé fait une seule phrase de 15 à 45 mots. Puis réponds en une ligne : nombre de résumés écrits et résultat du contrôle.
