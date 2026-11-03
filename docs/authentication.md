# Configuration et diagnostic de l’authentification

## Parcours

1. Le formulaire demande `site_id` (code de raccordement numérique) et `pin`.
   Le site normalisé sert d’identifiant unique ; un doublon est arrêté avant
   tout appel réseau. Un identifiant d’appareil UUID est généré.
2. `salt` reçoit uniquement `id_site`, converti en entier.
3. Le sel décodé en Base64 est concaténé au PIN encodé en UTF-16LE. Les
   empreintes SHA-1 et SHA-256, encodées en Base64, sont envoyées à `site`
   dans les champs `pin` et `password`, avec `partage="1"` et `id_device`.
   Le transport reste du JSON sous le Content-Type attendu par l’application.
4. Les statuts `site` 0 et 10 restent acceptés si un jeton est présent.
   Le statut 10 conserve les restrictions de commande existantes.
5. Une lecture `panel-status` doit réussir avant de créer l’entrée. Si la
   session est rejetée (2/3/4), une seule réauthentification et une seule
   nouvelle lecture sont effectuées. Aucun ordre d’alarme n’est envoyé.
6. Après création, le coordinateur effectue sa première lecture puis une
   lecture toutes les 30 secondes. Seul un échec d’authentification déclenche
   `ConfigEntryAuthFailed` ; les indisponibilités passent par `UpdateFailed`.
7. La réauthentification demande seulement le nouveau PIN, conserve le site
   et l’identifiant d’appareil et valide les mêmes appels avant de sauvegarder.

## Défauts de classification corrigés

En 0.1.4, tous les échecs fonctionnels de `salt`, un sel absent, le verrouillage
`site` 7 et tout statut `site` autre que 0/10 produisent la même exception
`NexecurAuthenticationError`. Les deux formulaires traduisent cette exception
en `invalid_auth`. Une session encore rejetée après authentification réussie
produit aussi cette erreur, alors que le service vient d’accepter le PIN.

| Réponse simulée / situation | Erreur du formulaire après correction |
| --- | --- |
| Sel absent, vide ou Base64 invalide ; statut absent ou non entier | `cannot_connect` |
| Échec fonctionnel de `salt` | `service_unavailable` |
| `site` 7 (verrouillage déjà identifié par le client) | `account_locked` |
| `site` 2/3/4 (codes d’authentification/session déjà présents dans le client) | `invalid_auth` |
| Autre statut `site` non reconnu | `service_unavailable` |
| Jeton absent après succès ; HTTP non 2xx ; timeout ; JSON invalide | `cannot_connect` |
| Centrale indisponible ou nouvelle session encore rejetée | `service_unavailable` |

L’API est privée : aucun journal du déclarant ne permet encore d’identifier
sa réponse réelle. Les simulations vérifient les comportements du client,
pas la signification de tous les codes du serveur. Les codes inconnus sont
traités conservativement comme une indisponibilité, sans affirmer que le PIN
est erroné. Aucun nouveau code serveur ni variante du protocole n’est inventé.

## Texte « Choix de la version » dans l’issue #1

Le titre et la description visibles sur la capture ne figurent ni dans
l’historique du dépôt, ni dans les traductions française et anglaise de
l’archive publiée 0.1.4. Les libellés bruts `site_id`, `pin` et `invalid_auth`
suggèrent aussi une résolution incorrecte des traductions.

Des traductions en cache, des fichiers locaux provenant d’une autre version
ou une autre intégration utilisant le même domaine sont des hypothèses à
vérifier auprès du déclarant. La capture ne permet pas de choisir entre elles.
Le code n’utilise aucun sélecteur ni paramètre de version de centrale : en
ajouter un sans connaître une variante API compatible n’aurait aucun effet utile.

## Diagnostics sans secrets

Activer temporairement :

```yaml
logger:
  logs:
    custom_components.nexecur: debug
```

Avec le correctif, seuls le nom du service (`salt`, `site`, `panel-status`),
le statut HTTP et le statut numérique du service sont consignés. Les corps
HTTP d’erreur et les textes libres renvoyés par le serveur ne sont pas inclus
dans les messages d’erreur. Ne pas activer une trace HTTP globale ni publier
les requêtes/réponses brutes.

Demander le nom exact de l’application officielle, le modèle de centrale si
connu, la méthode d’installation, le chemin de l’intégration, les versions,
une capture nettoyée du formulaire et les seules lignes de journal pertinentes.
Ne jamais demander le PIN, le code de raccordement, les empreintes, le sel,
les jetons, les sauvegardes ou les fichiers `.storage`.

## Vérifications reproductibles

```sh
python3.14 -m venv .venv
. .venv/bin/activate
pip install -r requirements_test.txt
pytest -q
ruff check custom_components/nexecur/api.py custom_components/nexecur/config_flow.py tests
ruff format --check custom_components/nexecur/api.py custom_components/nexecur/config_flow.py tests
```

Les tests utilisent Home Assistant et ses vrais flux de configuration. Seule
la frontière HTTP `ClientSession.post` est simulée ; les sockets réseau sont
bloquées. Ils couvrent aussi les empreintes envoyées, le renouvellement unique
de session, la réauthentification et l’absence de secrets dans les diagnostics.
La CI exécute les tests avec Home Assistant 2026.10.3 et 2026.10.4, ainsi que
les workflows HACS et Hassfest existants. Ces tests ne remplacent pas une
validation ultérieure avec le matériel du déclarant.
