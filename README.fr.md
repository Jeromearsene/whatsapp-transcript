# WhatsApp Transcript

*[Read in English](README.md)*

[![CI](https://github.com/jeromearsene/whatsapp-transcript/actions/workflows/ci.yml/badge.svg)](https://github.com/jeromearsene/whatsapp-transcript/actions/workflows/ci.yml)
[![Licence MIT](https://img.shields.io/badge/licence-MIT-blue.svg)](LICENSE)
[![Python 3.10–3.15](https://img.shields.io/badge/python-3.10%E2%80%933.15-blue.svg)](pyproject.toml)
[![Lint: ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

Trois scripts qui transforment une discussion WhatsApp (texte, vocaux, photos,
vidéos, liens) en un livre au format Markdown. Tout tourne en local sur ton
Mac, rien ne part sur un serveur distant (hormis le tout premier téléchargement
du modèle de transcription, qui se fait une seule fois).

**Python :** testé avec la version **3.12** (fixée dans `.python-version`).
Toute version **3.10 à 3.15** convient (`mlx`, la bibliothèque sous-jacente de
`mlx-whisper`, prend en charge cette plage sur Apple Silicon — voir la
contrainte dans `pyproject.toml`).

**Licence :** [MIT](LICENSE).

> ⚠️ **Avant ton premier commit public :** le dossier `data/` et `book.md`
> contiennent le contenu réel de ta discussion. Ils sont exclus par
> `.gitignore` — vérifie juste avec `git status` qu'aucun des deux ne s'y
> glisse.

```
extract.py     étape 1 : transforme l'export WhatsApp en messages.json structuré
transcribe.py  étape 2 : transcrit les vocaux (.opus) avec mlx-whisper
compile.py     étape 3 : assemble tout en un livre, groupé par jour
               (Markdown, JSON ou texte brut — au choix)
```

## Installation (une seule fois)

```bash
# ffmpeg est nécessaire pour décoder les fichiers audio .opus
brew install ffmpeg

# Poetry, si tu ne l'as pas déjà
brew install poetry

# dépendances Python (mlx-whisper, optimisé pour Apple Silicon), dans un
# environnement virtuel géré par Poetry
poetry install
```

Les commandes des étapes suivantes sont à lancer avec `poetry run` devant
(ça exécute la commande dans l'environnement virtuel du projet), par exemple
`poetry run python3 extract.py ...`. Tu peux aussi faire `poetry shell` une
fois pour activer l'environnement, puis lancer les commandes `python3 ...`
telles quelles pour le reste de la session de terminal.

## Étape 0 — obtenir l'export WhatsApp

Sur le Mac, dans l'app WhatsApp Desktop (pas besoin de l'iPhone) :

1. Ouvre la discussion.
2. Clique sur le nom du contact en haut (ou le menu "…") puis **Exporter la
   discussion**.
3. Choisis **Joindre les médias** (sinon les vocaux, photos et vidéos ne
   seront pas inclus).
4. Le fichier `.zip` atterrit dans ton dossier **Téléchargements**.

## Étape 1 — extraction

```bash
poetry run python3 extract.py --export "~/Downloads/WhatsApp Chat avec XXX.zip" --out ./data
```

Pour te limiter à une période précise :

```bash
poetry run python3 extract.py --export "~/Downloads/WhatsApp Chat avec XXX.zip" --out ./data \
    --since 01/10/2026 --until 31/10/2026
```

Le script affiche un décompte par type de message et la période couverte.
**Vérifie que la date la plus ancienne affichée correspond bien au vrai début
de votre discussion** — si WhatsApp avait tronqué l'export (ça arrive sur de
très longues discussions), ça se verrait ici.

## Étape 2 — transcription des vocaux

```bash
poetry run python3 transcribe.py --data ./data
```

Utilise par défaut le modèle `large-v3` (le plus précis, recommandé vu que
certains vocaux sont de qualité sonore moyenne) et la langue française. Ça
peut prendre un moment pour ~500 vocaux de 5 minutes — c'est normal, et le
script sauvegarde sa progression au fur et à mesure (tu peux interrompre avec
Ctrl+C et relancer la même commande, il reprendra où il s'était arrêté sans
retranscrire ce qui est déjà fait).

Avant transcription, chaque fichier passe par un prétraitement `ffmpeg`
(normalisation de volume + réduction de bruit léger), pour aider sur les
vocaux de qualité sonore moyenne. Si `ffmpeg` échoue sur un fichier précis, le
script bascule automatiquement sur le fichier brut plutôt que d'abandonner.
Pour désactiver ce prétraitement : `--skip-preprocess`.

Plutôt que de signaler un vocal de 5 minutes en entier dès qu'un passage est
incertain, seuls les **segments** à faible confiance sont listés — avec leur
horodatage précis dans le fichier audio — dans `data/to_review.md`. Tu n'as
qu'à écouter les quelques secondes concernées, pas tout le vocal.

Les fichiers qui échouent complètement (audio corrompu, etc.) sont consignés
dans `data/errors.json` plutôt que juste affichés dans le terminal, et sont
automatiquement retentés au prochain lancement du script.

Options utiles : `--threshold` (sensibilité de détection des passages
incertains, par défaut `-0.8`), `--no-speech-threshold` (détecte les segments
probablement muets/bruités, par défaut `0.6`), `--skip-preprocess`.

## Étape 3 — compilation en livre

```bash
poetry run python3 compile.py --data ./data                    # -> book.md (par défaut)
poetry run python3 compile.py --data ./data --format json      # -> book.json
poetry run python3 compile.py --data ./data --format text      # -> book.txt
poetry run python3 compile.py --data ./data --format text --out ./discussion.txt
```

`--format` choisit le format de sortie : `markdown` (par défaut), `json` ou
`text`. Si `--out` n'est pas précisé, le nom de fichier prend par défaut
`book.md`, `book.json` ou `book.txt` selon le format choisi.

- **markdown** (par défaut) : un fil chronologique groupé par jour, avec les
  photos intégrées, les vidéos et vocaux en lien (le vocal est remplacé par
  sa transcription, avec un lien vers le fichier audio d'origine et un ⚠️ si
  la confiance était faible), et les liens texte laissés tels quels.
- **text** : le même contenu, sans syntaxe Markdown — des lignes simples et
  lisibles, groupées par jour.
- **json** : un tableau plat de messages, dans l'ordre chronologique
  (`id`, `datetime`, `day`, `sender`, `type`, `content`, `media_file`,
  `transcript`, `transcript_flagged`), pensé pour être traité par un script
  ou réimporté ailleurs plutôt que lu directement.

Remarque : dans les formats markdown et texte, les titres de jour et
quelques courtes annotations intégrées au livre restent en français,
puisque le livre se veut une copie lisible d'une discussion en français.
Tout le reste — le code, la ligne de commande, ce README — est en anglais.

## Pour importer la suite plus tard

Quand la discussion continue, répète les 3 étapes :

1. Refais un **export WhatsApp** (étape 0) — il contient tout l'historique,
   pas seulement les nouveautés, ce n'est pas grave.
2. Relance `extract.py` vers le **même** dossier `--out ./data` (ça écrase
   `messages.json` avec la version à jour, mais les transcriptions déjà
   faites dans `transcripts.json` restent en cache).
3. Relance `transcribe.py` — seuls les nouveaux vocaux seront transcrits.
4. Relance `compile.py` — seuls les messages postérieurs au dernier import
   (`data/cursor.json`) sont ajoutés à `book.md`.

## Tests et lint

```bash
poetry run pytest        # 27 tests (fonctions pures + bout-en-bout sur chaque script)
poetry run ruff check .  # lint (style, imports, bugs fréquents)
```

Les tests n'ont pas besoin de `mlx-whisper` pour passer : `transcribe.py`
s'importe et se comporte correctement même sans Apple Silicon (il s'arrête
proprement avec un message clair), ce qui permet de les lancer sur n'importe
quelle machine. Un seul test (prétraitement `ffmpeg`) est sauté si `ffmpeg`
n'est pas installé.

## Intégration continue

`.github/workflows/ci.yml` tourne sur un runner macOS (Apple Silicon requis
pour `mlx`) à chaque push/PR sur `main` : il installe le projet avec Poetry,
vérifie la syntaxe des trois scripts, lance le lint (`ruff check .`) et la
suite de tests (`pytest`). Il ne lance pas de vraie transcription (trop long,
et sans contenu audio de test versionné — volontairement, vu la
confidentialité des vocaux).

## Limites connues

- L'export natif WhatsApp plafonne à ~10 000 messages avec médias (~40 000
  sans). Avec le rythme actuel de votre discussion, c'est très large, mais si
  ça devient un jour un sujet, le script `extract.py` peut être adapté pour
  lire directement la base de données locale (via l'outil
  `whatsapp-chat-exporter`) plutôt que l'export grand public — on peut en
  reparler le moment venu.
- Les messages système WhatsApp (changement de numéro, notice de chiffrement,
  etc.) ne sont pas toujours reconnus comme tels et peuvent être silencieusement
  absorbés dans le message précédent. Sans impact sur le texte, les vocaux, les
  photos/vidéos ou les liens.
- Si un import incrémental reprend en plein milieu d'une journée déjà commencée
  dans `book.md`, le titre du jour peut apparaître deux fois — à fusionner à la
  main si ça gêne.
- La fonction `mlx_whisper.transcribe()` et la structure de ses segments
  (`start`, `end`, `avg_logprob`, `no_speech_prob`) ont pu changer selon la
  version installée. Si `transcribe.py` plante dessus, fais
  `poetry run python3 -c "import mlx_whisper; help(mlx_whisper.transcribe)"`
  pour voir le nom exact des paramètres à ajuster — c'est une ligne à
  corriger, pas plus.
- L'ID de chaque message est maintenant un hash de son contenu (stable d'un
  import à l'autre), donc si un message est édité ou supprimé côté WhatsApp
  après avoir été transcrit, sa transcription existante devient orpheline (pas
  réutilisée, pas supprimée) et le "nouveau" message sera retranscrit comme
  s'il était neuf.
- Changer de `--format` d'un lancement à l'autre ne convertit pas ce qui a
  déjà été compilé : seuls les messages nouvellement importés sont ajoutés
  au fichier correspondant au nouveau format. Pour une reconstruction
  complète dans un format différent, supprime d'abord `data/cursor.json` et
  l'ancien fichier de sortie.
