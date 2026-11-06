# V5.5.2 — scénario A42 préparé, NON PUBLIÉ

## Scénarios et distribution

Le choix manuel `scenario` offre `monaco` (défaut) et `a42-pilot`. Monaco conserve sa source, ses coordonnées, son costing et ses vérifications ; les 34 tests historiques passent. Une seule construction de graphe par job, puis deux itinéraires A42 sur ce graphe. Aucun serveur permanent, aucun tarif.

Source A42 prévue :
https://github.com/NogeomHub/valhalla-routing-poc/releases/download/a42-pilot-20261102-v1/a42-meximieux-amberieu.osm.pbf

Cette release et cet asset NE SONT PAS PUBLIÉS. Un essai distant est impossible tant qu'ils ne le sont pas. Le tag est versionné ; l'immuabilité du contenu est imposée par SHA-256 ET taille, pas supposée à partir du tag.
- 1 064 733 octets
- e5912f17f620535e9b3be7dbd2e2b9963c778a7d1a873614b6ae901d1b793235

Le manifeste d'extraction est conservé dans le dépôt proposé et lié par empreinte dans a42-source.json. Son pilote/parent et ses dépendances sont vérifiés avant téléchargement. Le PBF téléchargé est recontrôlé avant/après le build et c'est exactement ce fichier qui est lu pour les preuves OSM. Aucun téléchargement Overpass/OSM courant, aucune substitution de version.

Les quatre assets préparés dans release-staging/a42-pilot-20261102-v1 sont le PBF, le manifeste d'extraction, l'audit indépendant et SHA256SUMS. À publier uniquement après accord sur cette release du dépôt personnel public. ODbL 1.0, © OpenStreetMap contributors, parent Geofabrik ; ni données tarifaires ni fichiers EDF. Pas de Git LFS, forfait ou runner payant.

## Itinéraires

Extrémités communes : Meximieux 45.904129,5.197079 → Ambérieu 45.958414,5.368862.
- via-a42 : préférence autoroute et péage 1 ; passage through au point 45.9130243,5.24914505, milieu du segment OSM 2 de la voie 477698628 dans le PBF figé, sens nord. L'utilisation d'A42 est quand même vérifiée sur les way_id de trace_attributes et leurs tags source ; ce waypoint ne suffit pas à lui seul.
- no-motorway : préférences use_highways=0 et use_tolls=0 ; l'absence de motorway/motorway_link est vérifiée sur CHAQUE arête. Préférence ≠ exclusion garantie.

## Contrôles

Les réponses et requêtes de chaque cas sont dans un dossier séparé avec manifestes et empreintes. Les erreurs HTTP sont aussi sauvegardées avant propagation de l'échec. Les deux cas sont tentés même si le premier échoue ; tout cas échoué impose un job rouge.

Récupération terminale inchangée V5.4.8 : uniquement un segment final manquant après préfixe exact, appel edge_walk séparé, preuves PBF de même voie/nœuds/direction, seuil 20 cm. Pas de map_snap, pas de découpage arbitraire pour contourner 443. Les réponses brutes et cumuls temporels restent séparés.

Audit A42 : index SQLite mémoire éphémère depuis CE PBF, alignement point/segment sur le way_id réellement fourni, nœuds ordonnés et direction ; mouvements entre edges ET internes. Aucune connexion par proximité ni référence routière. Géométrie/projection ambiguë, sens ou connexion non prouvés : refus. Les relations présentes dans le PBF sont conservées comme preuves ; les restrictions simples pertinentes sont évaluées pour chaque mouvement. Via-way, condition, exception ou forme non prise en charge : UNKNOWN explicite. Une interdiction démontrée bloque le test.

Les permissions de voies/nœuds nécessitant du contexte restent inconnues. Même avec un succès technique, frontières et restrictions globales restent INCOMPLETE ; jamais de certificat global ni de tarif.

## Essais locaux réels

Un graphe A42 construit avec la même image Valhalla 3.9.1 épinglée, sans téléchargement ou modification OSM. Le journal de build indique environ 1,37 seconde (mesure des timestamps de log, pas une mesure RSS).
- via-a42 : route calculée 30,692 km, 1324,263 s ; trace_attributes strict échoue 443 « Exact route match algorithm failed to find path ». Utilisation A42 NON prouvée par les arêtes puisque cette réponse manque. Échec conservé.
- no-motorway : route 16,616 km, 980,096 s ; 362 points, erreur géométrique maximale 0 m, 360 mouvements démontrés, 0 motorway/motorway_link et 0 A42. Deux restrictions simples évaluées ALLOWED relativement au PBF : 21510800 et 17598393. Zéro interdiction démontrée. Une permission de nœud reste inconnue (12590488073, lift_gate/access=yes/opening_hours=24/7) : pas de règle de permission nouvelle inventée.

Les appels locaux utilisent le mode CLI ponctuel du moteur, pas un serveur durable. Les artefacts sont dans local-a42/work/out et les appels bruts dans local-a42/work/calls. Aucune de ces données de travail n'est dans le paquet de code à publier.

## Tests et décision

34 tests Monaco + 12 tests de scénario + 6 tests d'audit PBF synthétique = 52/52. YAML analysé, scripts shell contrôlés, modules Python compilés. Le lecteur pyosmium fonctionne dans le venv isolé existant. Les tests synthétiques ne sont pas présentés comme un succès du scénario réel complet.

NO-GO pour lancer maintenant un workflow censé valider les deux parcours. Blocages : asset versionné non publié (attendu) ET échec réel 443 du premier itinéraire (technique). La prochaine étape utile est le diagnostic ciblé de cet échec sur les artefacts déjà conservés, sans nouveau benchmark ni relâchement de fiabilité. Cette préparation n'a déclenché aucun run et n'a publié aucun fichier.

## Mise à jour locale V5.5.3 — correctif démontré

Le NO-GO 443 décrit ci-dessus correspond à V5.5.2. La cause a été isolée : le waypoint A42 de milieu de segment introduisait un sommet absent de la forme du graphe. Le waypoint est désormais le nœud OSM existant 309487296 (45.9134166,5.2498414), même chaussée et même sens. Essai réel : route inchangée sauf retrait de ce sommet artificiel, 626 points, 160 arêtes, 15 arêtes A42, erreur 0 m, 624 mouvements prouvés. 57/57 tests passent. GO technique pour ce correctif ; source release toujours non publiée et aucune certification globale. Voir diagnostic-v5.5.3/REPORT.md.

## État de publication V5.5.5

La release de données a42-pilot-20261102-v1 est publiée après vérification des quatre assets. Le waypoint actif est le nœud 309487296. Monaco reste le scénario manuel par défaut ; a42-pilot utilise cette release publique figée. Aucun run de routage GitHub Actions n’est exécuté pendant cette publication. Les inconnues et la certification globale restent INCOMPLETE.
