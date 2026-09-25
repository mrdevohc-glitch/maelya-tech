# Equipe d'agents autonomes (LangGraph)

Deux equipes d'agents autonomes construites avec LangGraph, independantes du Claude Agent SDK
pour pouvoir brancher n'importe quel fournisseur de modele (Anthropic aujourd'hui, OpenAI ou
autre demain) sans reecrire l'orchestration.

- **`coding_team`** : research → frontend → backend → test/deploy → security → content,
  coordonnes par un supervisor. Travaille sur un vrai dossier de projet (fichiers + shell),
  avec des garde-fous contre les commandes destructrices.
- **`marketing_team`** : email, social, SEO/contenu, pub/CRO, coordonnes par un supervisor.
  Ne produit que des brouillons (`output/marketing/`) — aucun outil d'envoi, de publication
  ou de depense n'existe dans le code, donc rien de reel ne peut partir tout seul.

## Installation

```bash
cd agents
python -m venv .venv
source .venv/Scripts/activate   # Windows Git Bash ; sous cmd/PowerShell : .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium     # necessaire pour frontend_agent (screenshot_page)
cp .env.example .env            # puis remplir la cle du fournisseur utilise (voir config/models.yaml)
```

Chaque agent utilise le fournisseur defini dans [config/models.yaml](config/models.yaml) — il
faut la cle API correspondante dans `.env` (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, ou
`OPENROUTER_API_KEY` selon ce qui est configure). Configuration actuelle : tous les agents
passent par OpenRouter (`OPENROUTER_API_KEY`) et utilisent des modeles Claude -- OpenRouter
facture ces modeles au meme prix que directement chez Anthropic (voir section OpenRouter plus
bas). Ces cles sont distinctes de tout abonnement Claude/ChatGPT — ce projet appelle les API
directement et facture a l'usage.

Avant de lancer l'equipe marketing (ou `content_agent` cote code), remplis
[context/business.md](context/business.md) : plus il est precis, moins les agents posent de
questions et plus les brouillons sont pertinents.

## Utilisation

```bash
# Equipe de developpement : cree un dossier projet et travaille dedans
python cli.py code "API REST pour gerer une liste de taches, avec auth par email/mot de passe"

# Cibler un dossier existant plutot qu'un nouveau projet auto-nomme
python cli.py code "ajoute un endpoint de reset de mot de passe" --project-dir ../mon-app

# Autoriser explicitement git push pour ce run (bloque par defaut)
python cli.py code "..." --allow-push

# Equipe marketing : ecrit des brouillons dans output/marketing/
python cli.py marketing "sequence de bienvenue de 3 emails pour un SaaS de facturation"
```

### Ce n'est PAS un chat -- comment repondre a une question d'un agent

Chaque commande est un aller-retour unique : l'agent repond, le programme se termine, la main
revient au terminal. Si le resume affiche une question, **ne tape pas ta reponse directement
dans le terminal** (PowerShell/cmd essaiera de l'executer comme une commande et affichera une
erreur). Relance `cli.py` avec ta reponse comme nouvelle "tache", en gardant :
- **`code`** : le MEME `--project-dir` (celui affiche par la commande precedente,
  `[coding_team] repertoire de travail : ...`)
- **`marketing`** : le MEME `--thread` (par defaut `default` si tu ne l'as pas precise)

Une memoire de conversation (SQLite, dans `.state/` a l'interieur du projet ou de
`output/marketing/`) fait que l'agent se souvient de l'echange precedent au lieu de repartir de
zero. Chaque reponse de la CLI affiche la commande exacte a copier pour continuer.

Chaque run de `code` cree par defaut `output/projects/<slug-de-la-tache>/` s'il n'y a pas de
`--project-dir` — pratique pour experimenter sans risquer d'ecrire ailleurs par erreur.

## Changer de modele (multi-fournisseur)

Tout est dans [config/models.yaml](config/models.yaml) : un `model` par agent au format
`"fournisseur:id-du-modele"`. Pour passer un agent sur OpenAI par exemple :

```yaml
backend_agent:
  model: "openai:gpt-5"
  max_tokens: 8000
  max_iterations: 25
```

Il faut alors avoir `OPENAI_API_KEY` dans `.env` (deja dans `.env.example`, `langchain-openai`
deja dans `requirements.txt`). Aucun fichier de code n'a besoin de changer.

### Ajouter un modele via OpenRouter (une seule cle pour Llama, Gemini, Mistral, Grok...)

OpenRouter expose une API compatible OpenAI pour des dizaines de modeles derriere une seule
cle. Deux champs optionnels dans `config/models.yaml` suffisent :

```yaml
mon_agent:
  model: "openai:meta-llama/llama-3.3-70b-instruct"   # id EXACT tel qu'OpenRouter l'attend
  base_url: "https://openrouter.ai/api/v1"
  api_key_env: "OPENROUTER_API_KEY"                    # doit exister dans .env
  max_tokens: 4000
  max_iterations: 15
```

Cree une cle sur https://openrouter.ai/keys, mets-la dans `OPENROUTER_API_KEY` (`.env`), et
trouve l'id exact du modele voulu sur https://openrouter.ai/models (le prefixe `openai:` ici
signifie juste "parle le protocole OpenAI", pas "modele OpenAI" — l'id apres les deux points
peut etre n'importe quel modele liste par OpenRouter).

## Plateforme web (piloter les agents a distance)

En plus de la CLI, `webapp/` expose un tableau de bord web (FastAPI + HTMX) pour donner des
instructions aux agents depuis un navigateur -- meme mecanisme que `cli.py` en arriere-plan
(un seul job execute a la fois, memes garde-fous), avec un mot de passe et une file de jobs
persistante.

```bash
# Une seule fois : definir le mot de passe de connexion
.venv\Scripts\python.exe webapp\set_password.py

# Lancer le serveur en local
.venv\Scripts\python.exe -m uvicorn webapp.app:app --reload
# -> http://127.0.0.1:8000
```

Le dashboard liste les projets/conversations existants, permet d'en lancer un nouveau ou de
repondre a un job en cours (equivalent web du "relance avec le meme --project-dir/--thread" de
la CLI), et suit le statut en direct (rafraichissement automatique pendant qu'un job tourne).

Hebergement (acces depuis n'importe ou) : voir `deploy/` -- prevu pour un petit VPS (ex.
Hetzner CPX22, ~5,50 $/mois) derriere un Cloudflare Tunnel (aucun port ouvert sur le serveur)
+ Cloudflare Access (deuxieme barriere avant meme la page de connexion). Cette etape se fait
ensemble (creation du compte serveur, DNS, etc.) -- `deploy/setup_server.sh` sert de reference
pour la premiere installation, `deploy/deploy.sh` pour chaque mise a jour ensuite (`git pull` +
redemarrage, une seule commande).

## Publication reelle multi-client (Facebook/Instagram)

`social_agent` et `ads_cro_agent` peuvent desormais, pour un **client** donne (voir `/clients`
dans le tableau de bord) :
- Mettre en attente un vrai post Facebook/Instagram (`stage_facebook_post`,
  `stage_instagram_post`) -- **jamais publie directement**, toujours en attente dans
  `/approvals` jusqu'a validation humaine explicite.
- Generer de vraies images de creas (`generate_ad_image`, via l'API OpenAI) -- pas
  d'approbation necessaire, ca n'ecrit qu'un fichier local.

Chaque client a ses propres identifiants, chiffres au repos (`common/crypto.py`,
`PLATFORM_CREDENTIALS_KEY` genere automatiquement) et strictement isoles -- un job pour le
client A n'a jamais acces aux identifiants du client B.

### Obtenir un jeton Facebook Page (pour un client)

1. Cree une app sur [developers.facebook.com](https://developers.facebook.com/apps/) (type
   "Business").
2. Ajoute le produit "Facebook Login for Business", demande les permissions
   `pages_manage_posts` et `pages_read_engagement` (et `instagram_content_publish` si tu veux
   aussi publier sur Instagram).
3. Genere un jeton d'acces longue duree pour la Page du client (Graph API Explorer, ou echange
   d'un jeton court contre un jeton longue duree via l'endpoint `oauth/access_token`).
4. Dans le tableau de bord, va sur `/clients/<id>`, section "Identifiants Facebook/Instagram",
   colle le `Page ID`, le jeton et (pour Instagram) l'`ig_user_id` -- ils sont chiffres
   immediatement, plus jamais affiches.

**Instagram** : fonctionne pleinement une fois le tableau de bord hebergee publiquement
(voir section Hebergement) et `PLATFORM_PUBLIC_URL` renseigne dans `.env` (ex.
`https://studio.maelya.tech`) -- l'API Meta exige une URL d'image publiquement accessible,
servie sans authentification via `/media/<fichier>` (noms de fichiers en UUID, pas
devinables). Les posts Facebook texte fonctionnent aussi bien en local qu'heberge.

### Prochaines plateformes (memes principes)

LinkedIn, Google Ads et X/Twitter suivront le meme schema (`stage_*` -> `/approvals` ->
executeur dedie dans `tools/publishing/`) -- chacune est une passe separee, Google Ads en
particulier necessite une demarche d'approbation d'acces cote Google independante du code.

## Garde-fous securite (equipe code)

`common/guardrails.py` bloque systematiquement, quoi que l'agent demande :
- `git push` (sauf si tu relances avec `--allow-push`)
- `git push --force`, `git reset --hard`, `git clean -f` (toujours bloques, aucune option ne les debloque)
- `rm -rf` en dehors du dossier `output/` du projet

## Suivi de consommation

Chaque appel modele est logge dans `output/usage.log` (un JSON par ligne : agent, tokens
entree/sortie). Utile pour reperer vite quel agent coute cher et ajuster son modele dans
`config/models.yaml`.

## Etendre le projet

- **Nouvel agent** : cree un fichier dans `coding_team/` ou `marketing_team/` suivant le
  modele des agents existants (model + tools + prompt + `create_react_agent`), ajoute-le a la
  liste `agents=[...]` du supervisor concerne, ajoute son entree dans `config/models.yaml`.
- **Envoi/publication reels (marketing)** : actuellement hors scope par choix (voir
  `tools/marketing_output.py`). Pour l'ajouter plus tard : creer un nouvel outil (ex.
  `tools/email_send.py` via l'API Resend/Mailchimp) et ne le donner **qu'a** l'agent concerne,
  jamais en tool par defaut — garder l'envoi comme une action explicite et separee de la
  generation.
- **Skills marketing** : copiees depuis le plugin `marketing-skills` sous `skills/`. Pour
  ajouter une skill supplementaire, copie son dossier depuis
  `~/.claude/plugins/cache/claude-code-skills/marketing-skills/<version>/skills/<nom>/` et
  reference son `SKILL.md` dans l'agent concerne via `common/skills.py`.
