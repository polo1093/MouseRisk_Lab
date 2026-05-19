# Environnement de test réel

Ce projet peut être testé avec de vrais mouvements de souris au niveau de l'écran. Le script `tools/real_mouse_lab.py` déplace le curseur, clique dans la zone de jeu, puis lit la télémétrie exposée par l'API.

## Préparer

Installez les dépendances du serveur :

```bash
pip install -r requirements.txt
```

Installez les dépendances du lab :

```bash
pip install -r requirements-test.txt
```

Lancez l'application :

```bash
python run_server.py
```

Ouvrez ensuite `http://127.0.0.1:8000` dans le navigateur.

## Calibrer la zone

Le script a besoin d'une région écran au format `x1,y1,x2,y2`. Cette région doit couvrir uniquement la zone de jeu, pas le panneau de score.

Exemple :

```text
100,390,1100,760
```

Sous Windows, utilisez un outil d'affichage des coordonnées souris, ou faites une première estimation puis ajustez.

## Lancer un test

Profil humain :

```bash
python tools/real_mouse_lab.py --region 100,390,1100,760 --mode human --count 12
```

Profil ligne droite rapide :

```bash
python tools/real_mouse_lab.py --region 100,390,1100,760 --mode linear --count 12
```

Profil téléportation :

```bash
python tools/real_mouse_lab.py --region 100,390,1100,760 --mode teleport --count 12
```

Profil grille :

```bash
python tools/real_mouse_lab.py --region 100,390,1100,760 --mode grid --count 12
```

Profil double-clics rapides :

```bash
python tools/real_mouse_lab.py --region 100,390,1100,760 --mode double --count 12
```

## Lancer depuis le site

Vous pouvez aussi lancer un programme directement depuis l'interface web.

1. Placez un fichier Python dans `mouse_programs/`.
2. Rechargez la page `http://127.0.0.1:8000`.
3. Dans la section `Programmes de test`, choisissez le fichier.
4. Cliquez sur `Utiliser la zone visible` ou saisissez une région écran manuelle.
5. Cliquez sur `Lancer le programme`.

Les programmes fournis acceptent tous les arguments suivants :

```bash
--base-url http://127.0.0.1:8000 --region 100,390,1100,760 --count 20 --focus-wait 3
```

Le serveur exécute uniquement les fichiers `.py` présents dans `mouse_programs/`.

Programme adversarial plus réaliste :

```bash
python mouse_programs/adaptive_spiral_human.py --region 100,390,1100,760 --count 20 --focus-wait 3
```

Ce profil utilise des courbes de Bézier, une petite spirale de stabilisation avant le clic, du jitter contrôlé et des pauses variables. Il sert à tester si l'heuristique souris résiste à un script plus soigné.

Variante contrainte dans une box centrale :

```bash
python mouse_programs/adaptive_spiral_human_plus.py --region 100,390,1100,760 --count 20 --focus-wait 3 --inner-box-scale 0.70 --click-box-scale 0.35 --delay-chance 0.5
```

Cette variante utilise `--region` comme zone de jeu, genere une box rouge aleatoire a l'interieur, genere une box verte aleatoire dans la rouge, puis declenche `mouseDown` / timer / `mouseUp` des que la trajectoire entre dans la box verte. La souris continue ensuite sa course jusqu'a la cible dans cette zone.
La spirale est lissee par trajet : sa frequence est choisie une seule fois, avec un bruit faible et continu pour eviter les tremblements.

## Profils disponibles

| Mode | But |
| --- | --- |
| `human` | Mouvement humanisé avec durée variable |
| `linear` | Déplacement rapide et plus régulier |
| `teleport` | Déplacement quasi instantané vers la cible |
| `grid` | Clics réguliers sur une grille |
| `center` | Clics répétés au centre |
| `double` | Double-clics rapides |

## Lecture des résultats

Chaque clic affiche une ligne :

```text
01 score=0.120 mouse=0.120 botd=0.000 reason=click session=...
```

Le résumé final donne la moyenne, le minimum et le maximum :

```text
Summary: clicks=12 scores=12 avg=0.184 min=0.000 max=0.420
```

## Attention

Le script contrôle réellement la souris. Avant de le lancer :

- ouvrez la page de test ;
- mettez la fenêtre au premier plan ;
- vérifiez que la région ne couvre que la zone de jeu ;
- ne touchez pas la souris pendant l'exécution.
