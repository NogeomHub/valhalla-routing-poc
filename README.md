# Valhalla GitHub Actions — prototype V5.4.8

Ce dépôt autonome effectue un seul essai de construction et de routage sur Monaco. Aucun tarif, moteur APRR, fichier EDF ni dépendance à Route Optimizer. Aucun déploiement. Aucun certificat global COMPLETE.

## Fichiers à publier

```
valhalla-routing-poc/
├── .github/workflows/valhalla-poc.yml
├── .gitignore
├── README.md
├── source.json
├── tests.py
├── requirements-osm.txt
├── tests_data/terminal-real.json
└── scripts/
    ├── run.sh
    ├── poc.py
    ├── terminal.py
    └── read_osm.py
```

Le dépôt comprend désormais onze fichiers, dont les quatre ajouts V5.4.8 décrits ci-dessous. Ne pas publier `sources/`, `static-validation/`, `work/` ou les prototypes voisins. Le workflow doit être exactement sous `.github/workflows/valhalla-poc.yml`, pas à la racine.

## Premier lancement — à effectuer par l'utilisateur

1. Sur son compte GitHub PERSONNEL, vérifier le quota d'artefacts et la facturation. Créer un dépôt PUBLIC nommé exactement `valhalla-routing-poc`. Ne pas utiliser un compte, dépôt, abonnement ou runner EDF.
2. Ajouter les onze fichiers en conservant l'arborescence, sur la branche par défaut. Aucun secret à créer. Les ajouts ne déclenchent pas de workflow : seul `workflow_dispatch` est configuré.
3. Ouvrir Actions → Standalone Valhalla smoke test → Run workflow → choisir la branche par défaut → Run workflow.
4. Attendre le résultat du job. S'il est « skipped », vérifier le nom exact du dépôt, sa visibilité publique et son propriétaire de type User.
5. Télécharger `valhalla-smoke-report` avant expiration (un jour). Le job doit être vert ET `manifest.json.stage` doit être `SMOKE_TEST_PASSED`. Tout échec obligatoire doit rendre le job rouge ; un artefact de diagnostic n'est pas une réussite.
6. Examiner `actualPbfSHA256`, `actualPbfBytes`, le digest d'image, `status.json`, `graph-files.json`, `route.json`, `trace-0.json` et les logs. Une réussite ne certifie ni la topologie ni l'exhaustivité des restrictions.

## Source et logiciel figés

- PBF : extrait Geofabrik Monaco `monaco-261102.osm.pbf`, URL, taille et SHA-256 dans `source.json`. Aucun découpage supplémentaire. Date d'édition dans le nom : 02/11/2026 ; Last-Modified HTTP : 03/11/2026, qui ne prouve pas la date de réplication interne. Taille et SHA réels revérifiés avant et après construction puis enregistrés dans le manifeste.
- Image : `ghcr.io/valhalla/valhalla@sha256:18cb42988e03c70dc4bc4ca095a259ec4db5e5df928be65956fc1c64c280b47a`, publication sélectionnée `3.9.1-amd64`. Pas de tag flottant au lancement.
- La couche d'installation de cette image a été inspectée : `valhalla_build_tiles`, `valhalla_build_config`, `valhalla_service` présents et exécutables. Le générateur Python extrait de cette couche accepte les options utilisées. Leur exécution native reste à vérifier sur le runner.
- Actions : checkout `11d5960a326750d5838078e36cf38b85af677262`, upload-artifact `ea165f8d65b6e75b540449e92b4886f43607fa02`. Les fichiers action.yml de ces références ont été vérifiés ; tous deux utilisent node20.
- Valhalla 3.9.1 : `valhalla/baldr/attributes_controller.h` et `src/baldr/attributes_controller.cc` confirment shape, edge.way_id, edge.begin_shape_index, edge.end_shape_index, edge.toll, edge.length, node.elapsed_time. La présence effective de tous ces champs est vérifiée sur la réponse du premier essai.

## Garde-fous

- Dépôt personnel public uniquement ; runner hébergé `ubuntu-24.04`, aucun runner auto-hébergé, aucun checkout d'un autre dépôt. Permissions explicites `contents:read` ; le jeton GitHub éphémère standard est utilisé par les actions, aucun secret utilisateur.
- 30 minutes maximum pour le job ; 25 pour les tests et le script principal ; limites additionnelles pull 5 minutes et construction 15 minutes. Échec immédiat des commandes obligatoires (`set -euo pipefail`), sans continue-on-error. Seul le nettoyage tolère des erreurs.
- Configuration `httpd.service.listen=tcp://*:8002` contrôlée avant lancement, Docker publié uniquement sur `127.0.0.1:8002:8002`. Arrêt/suppression des conteneurs en fin d'exécution, même en échec normal ; le runner entier est éphémère en cas d'arrêt forcé.
- Uniquement checkout/actions épinglées, image épinglée et PBF identifié. Une roue pyosmium 4.3.2 cp312 x86_64, épinglée par SHA-256, est installée avec pip --no-deps dans work/osm-env. Aucun apt, téléchargement d'admins, fuseaux, élévation ou autre données. Construction avec `--network none`.
- Préparation nettoie son workspace éphémère pour empêcher la réutilisation de preuves périmées. Contrôles de taille ET SHA ; empreintes configuration et tuiles liées au marqueur de construction.
- Rapport de succès seulement après commande de construction réussie, tuiles non vides, route status=0, trace complète et way_id valides. Le rapport revérifie les artefacts sauvegardés, le PBF, les tuiles et la configuration. Le finaliseur ne convertit jamais l'échec de l'étape principale en succès et retire le rapport de réussite en cas d'échec.
- Polylines décodées en points polyline6 ordonnés ; même nombre de points et écart maximal <=20 cm. Échantillonnages différents : correspondance non démontrée, arrêt explicite. Cette cohérence géométrique n'est JAMAIS une preuve de nœud partagé, de sens, de permission ou de restriction.
- Restrictions, frontières et permission globale restent INCOMPLETE, même après succès. Aucun tarif produit.

## Ressources, coût, licence

Runner standard public annoncé : 4 CPU, 16 Go RAM, 14 Go SSD. Le workflow exige au moins 4 Gio libres et 7 Gio de RAM totale, limite la construction à 2 CPU/6 Gio. Estimation pour Monaco : 5–15 minutes, sans garantie ; 30 minutes maximum. Il n'établit pas la capacité à construire Rhône-Alpes.

Calcul standard sur dépôt public gratuit, mais les artefacts restent soumis aux quotas du compte (GitHub Free : 500 Mo annoncés). Vérifier les quotas déjà utilisés et le blocage des dépassements payants. Aucune promesse de gratuité absolue si le compte stocke déjà d'autres artefacts. Rétention un jour, logs limités à 2 Mio chacun ; ni PBF ni tuiles uploadés. En privé, quota de calcul puis facturation : ce workflow refuse les dépôts privés.

Valhalla : MIT, conserver licence/copyright si redistribué ; les dépendances de l'image ont leurs propres licences. L'image n'est pas republiée. OSM : ODbL 1.0, © OpenStreetMap contributors ; extrait Geofabrik. Conserver attribution/provenance des géométries ; une future redistribution de base ou de graphe nécessiterait une vérification des obligations ODbL. Aucun catalogue APRR publié.

## Validation avant publication

`python3 tests.py -v` : tests entièrement synthétiques et hors réseau. Ils ne lancent pas Docker. Les contrôles statiques du workflow et le générateur de config ont aussi été vérifiés localement, sans installation de logiciel supplémentaire.

Pas de construction réelle, serveur Valhalla lancé ou workflow GitHub exécuté lors de la préparation. Les preuves statiques ne garantissent pas le succès du runner. La prochaine étape est UNIQUEMENT l'exécution réelle de ce prototype, pas une nouvelle version de développement.

Sources :
- https://docs.github.com/en/actions/reference/runners/github-hosted-runners
- https://docs.github.com/en/actions/reference/limits
- https://docs.github.com/en/billing/concepts/product-billing/github-actions
- https://github.com/valhalla/valhalla/tree/3.9.1
- https://www.openstreetmap.org/copyright
- https://download.geofabrik.de/

## V5.4.8 — récupération terminale explicite

Ajouts : `scripts/terminal.py`, `scripts/read_osm.py`, `requirements-osm.txt`, `tests_data/terminal-real.json`. Les tests utilisent des données archivées du run 42095224159, sans réseau. Dépendance de lecture : roue binaire pyosmium 4.3.2, Python système 3.12 Ubuntu 24.04, hash vérifié, environnement isolé ; le lecteur PBF local utilisé n'importe pas les dépendances requests non installées. Pas de modification du Python global.

Un seul appel edge_walk supplémentaire est autorisé, uniquement pour UN segment terminal manquant après un préfixe exactement identique. Les réponses principale et terminale, requêtes et preuve OSM sont conservées séparément. La preuve est extraite du PBF dont le SHA réel a été vérifié ; les identifiants de voie, trois nœuds ordonnés et la direction doivent concorder. Cas ambigu, portion résiduelle, direction incompatible ou condition non évaluée : échec. Aucun secours map_snap, aucune interpolation ou attribution par proximité seule.

Le manifeste distingue `routingTest=PASSED`, `geometricEdgeCoverage=COMPLETE` et `globalCertificate=INCOMPLETE`. `terminalRecovery` indique si cette méthode a été utilisée, `timingsCombined=false` interdit de lire le résultat comme un cumul fabriqué. Les durées, distances et indicateurs de péage des réponses restent bruts et séparés. Les empreintes des appels et preuves sont liées au résultat du test et revérifiées avant le rapport.

L'égalité ou la cohérence des géométries n'est jamais un certificat global. Les restrictions/frontières globales restent INCOMPLETE. Cette version est testée localement ; aucune exécution GitHub n'a encore validé la version 5.4.8.

## Scénario A42 préparé V5.5.2

Voir [A42-PLAN.md](A42-PLAN.md) pour la distribution versionnée, les nouveaux fichiers et les résultats locaux. Le choix par défaut reste Monaco. Le scénario A42 est actuellement NO-GO pour valider les deux parcours : le premier appel edge_walk retourne 443. Aucun certificat global.

## Publication du pilote A42 V5.5.4

Le blocage 443 historique décrit en V5.5.2 est corrigé par le waypoint sur le nœud OSM 309487296 (45.9134166,5.2498414). Essai réel V5.5.3 : 626 points, 160 arêtes identifiées dont 15 A42, erreur 0 m ; contrôles de sens/continuité conservés, permissions inconnues toujours INCOMPLETE. 57 tests locaux passent. Monaco reste le choix par défaut.

Le scénario a42-pilot utilise la release de données a42-pilot-20261102-v1 et vérifie taille et SHA-256 avant toute construction. Sélectionner Actions → Standalone Valhalla smoke test → Run workflow → scenario: a42-pilot. Aucune exécution distante de cette version n’est revendiquée dans cette documentation.
