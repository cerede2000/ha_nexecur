<p align="center">
  <img src="brand/icon.png" alt="NEXECUR pour Home Assistant" width="150">
</p>

# NEXECUR pour Home Assistant

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
[![GitHub release](https://img.shields.io/github/v/release/cerede2000/ha_nexecur)](https://github.com/cerede2000/ha_nexecur/releases)
[![Validate](https://github.com/cerede2000/ha_nexecur/actions/workflows/validate.yml/badge.svg)](https://github.com/cerede2000/ha_nexecur/actions/workflows/validate.yml)
[![License](https://img.shields.io/github/license/cerede2000/ha_nexecur)](LICENSE)

[![Ajouter le dépôt dans HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=cerede2000&repository=ha_nexecur&category=integration)

[![Configurer l’intégration](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=nexecur)

Intégration Home Assistant non officielle pour les alarmes pilotées par
l’application **Mon NEXECUR**. Elle crée une entité standard
`alarm_control_panel`, utilisable dans les tableaux de bord, automatisations et
scripts Home Assistant.

## Fonctionnalités

- Consultation de l’état de l’alarme toutes les 30 secondes
- Activation totale
- Activation partielle 1
- Activation partielle 2
- Désactivation
- Configuration complète depuis l’interface Home Assistant
- Renouvellement automatique de la session NEXECUR
- Prise en charge de plusieurs sites NEXECUR
- Traductions française et anglaise
- Aucune dépendance Python supplémentaire
- Version installée visible dans les informations de l’appareil et dans
  l’attribut `integration_version`

| Action Home Assistant | Mode NEXECUR |
| --- | --- |
| Désarmer | Désactivé |
| Armer en absence | Activation totale |
| Armer à domicile | Partiel 1 |
| Armer de nuit | Partiel 2 |

Les commandes Partiel 1 et Partiel 2 ne sont proposées que si le site les
autorise.

## Installation avec HACS

1. Cliquez sur le bouton **Ajouter le dépôt dans HACS** ci-dessus.
2. Téléchargez **NEXECUR** dans HACS.
3. Redémarrez Home Assistant.
4. Ouvrez **Paramètres → Appareils et services → Ajouter une intégration**.
5. Recherchez **NEXECUR**.
6. Saisissez le code de raccordement et le PIN utilisés dans Mon NEXECUR.

Il est également possible d’ajouter manuellement
`https://github.com/cerede2000/ha_nexecur` dans **HACS → Intégrations → Dépôts
personnalisés**, avec la catégorie **Intégration**.

## Installation manuelle

Copiez le dossier `custom_components/nexecur` dans le dossier
`custom_components` de votre configuration Home Assistant, puis redémarrez
Home Assistant.

La structure finale doit être :

```text
/config/custom_components/nexecur/
├── __init__.py
├── alarm_control_panel.py
├── api.py
├── config_flow.py
├── const.py
├── coordinator.py
├── manifest.json
└── translations/
```

## Tableau de bord

Après la configuration, ajoutez la carte native **Panneau d’alarme** et
sélectionnez l’entité créée, généralement `alarm_control_panel.nexecur`.

```yaml
type: alarm-panel
entity: alarm_control_panel.nexecur
name: Alarme maison
states:
  - arm_away
  - arm_home
  - arm_night
```

## Automatisations

### Activation totale

```yaml
action: alarm_control_panel.alarm_arm_away
target:
  entity_id: alarm_control_panel.nexecur
```

### Activation partielle 1

```yaml
action: alarm_control_panel.alarm_arm_home
target:
  entity_id: alarm_control_panel.nexecur
```

### Activation partielle 2

```yaml
action: alarm_control_panel.alarm_arm_night
target:
  entity_id: alarm_control_panel.nexecur
```

### Désactivation

```yaml
action: alarm_control_panel.alarm_disarm
target:
  entity_id: alarm_control_panel.nexecur
```

## Sécurité des commandes

Le service NEXECUR peut renvoyer une erreur HTTP 500, une réponse vide ou une
réponse non JSON après avoir réellement transmis un ordre à la centrale. Dans
ce cas, l’intégration **ne renvoie jamais automatiquement la commande**. Elle
relit l’état de la centrale jusqu’à confirmation ou expiration du délai, afin
d’éviter les commandes en double.

Le PIN est enregistré dans la configuration interne de Home Assistant. Il
n’est jamais exposé comme attribut d’entité ni écrit dans les journaux de
l’intégration. Les sauvegardes Home Assistant doivent néanmoins être protégées,
car elles contiennent les identifiants des intégrations.

## Dépannage

### L’intégration n’apparaît pas

- Vérifiez que le dossier est bien `/config/custom_components/nexecur`.
- Redémarrez complètement Home Assistant après l’installation.
- Videz le cache du navigateur si nécessaire.

### Identifiants refusés

Utilisez le **code de raccordement numérique** et le **PIN du site**, et non les
identifiants d’un compte web différent. Vérifiez qu’ils fonctionnent encore
dans l’application Mon NEXECUR.

### La centrale met du temps à changer d’état

C’est normal : l’ordre est transmis par le service NEXECUR puis confirmé par
la centrale. Home Assistant attend cette confirmation pendant environ une
minute.

### Journaux de diagnostic

Ajoutez temporairement ceci dans `configuration.yaml`, redémarrez Home
Assistant, puis reproduisez le problème :

```yaml
logger:
  logs:
    custom_components.nexecur: debug
```

Les journaux ne contiennent ni le PIN ni le jeton de session.

## Limites connues

- L’intégration dépend d’un service cloud : une connexion Internet est requise.
- L’API utilisée est privée et non documentée officiellement.
- Une modification de l’application ou du service NEXECUR peut nécessiter une
  mise à jour de l’intégration.
- Ce projet n’est ni affilié à NEXECUR, ni approuvé, ni maintenu par NEXECUR.

## Signaler un problème

Ouvrez une [issue GitHub](https://github.com/cerede2000/ha_nexecur/issues) en
indiquant la version de Home Assistant, la version de l’intégration et les
journaux pertinents après suppression de toute donnée personnelle.

## Licence

Distribué sous licence [MIT](LICENSE).
