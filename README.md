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

**Hebergement reel actuel** : auto-heberge sur un PC personnel (Ubuntu Server, service systemd
`agents-platform`), expose publiquement via Cloudflare Tunnel (`cloudflared`, aucun port ouvert
sur la box) sur `https://studio.maelya.tech`, avec Cloudflare Access en 2e barriere (code email
avant meme la page de connexion) sur tout le hostname SAUF les chemins publics `/media/*`,
`/demande*` et `/static/*` (policy "Bypass" dediee sur chacun -- voir section portail client).
`deploy/` garde des templates generiques (`setup_server.sh`, `agents-platform.service`) utiles
comme reference si un jour le service change de machine.

**Deploiement : "push pour deployer"**. Le serveur a un depot git bare (`~/agents.git`) avec un
hook `post-receive` qui checkout la branche `master` dans `~/agents` (`.env`/`webapp.sqlite*`
jamais touches, exclus du suivi git), reinstalle `requirements.txt` (idempotent) puis termine le
process (`pkill -u mrohc -f 'uvicorn webapp.app:app'`) -- `systemd` (`Restart=always`) le relance
immediatement avec le nouveau code, sans sudo. Pour deployer :

```bash
git push production master
```

`production` pointe vers `mrohc@ssh.maelya.tech:agents.git`. **SSH a distance** (meme hors du
reseau de la maison) passe par le meme tunnel Cloudflare que le dashboard, avec Cloudflare
Access en 2e barriere sur `ssh.maelya.tech` : policy Allow par email (acces manuel du
proprietaire) + policy Allow par **Service Token** (Zero Trust -> Access -> Service Auth,
`CF-Access-Client-Id`/`CF-Access-Client-Secret`) pour un acces automatise/non-interactif.
`cloudflared access ssh` avec `--service-token-id`/`--service-token-secret` est casse dans les
versions clientes >= 2026.6.0 (regression connue, ignore le jeton et retombe sur une
authentification navigateur) -- utiliser 2026.5.1 pour le client qui fait le
`ProxyCommand`/`~/.ssh/config`.

## Portail client public (`/demande`)

Formulaire public (aucune authentification) ou un prospect decrit son projet -- genere
automatiquement, via `research_agent` **seul, jamais via le supervisor complet**, les 4
documents de cadrage habituels (cahier des charges, choix techno, devis, trame de contrat) dans
un dossier jetable `output/intake/<id>/`. Rien n'est jamais montre ou envoye au prospect
automatiquement : le resultat atterrit dans `/submissions` (authentifie) pour relecture humaine
avant tout retour au client, comme pour les publications reelles.

**Pourquoi `research_agent` seul et pas le supervisor** : le brief est ecrit par un inconnu sur
internet (injection de prompt possible). `research_agent` n'a que `read_file`/`write_file`
(bornes au dossier jetable, voir `common/workdir.py`) et une recherche web -- **pas d'outil
shell**, contrairement a `backend_agent`/`frontend_agent`/`test_deploy_agent`. Le supervisor
complet n'est donc jamais atteignable depuis ce formulaire.

**Protections anti-abus** (chaque soumission declenche un vrai appel OpenAI payant) :
Cloudflare Turnstile (captcha invisible, cles `TURNSTILE_SITE_KEY`/`TURNSTILE_SECRET_KEY` dans
`.env`, widget cree dans le dashboard Cloudflare), rate-limit par IP (3/heure,
`webapp/rate_limit.py`), plafond global de 20 demandes/jour.

**Cote Cloudflare Access** : le formulaire doit rester accessible sans le mur email destine a
l'operateur -- necessite une Application Access dediee sur `studio.maelya.tech` + path
`/demande*` avec une policy **Bypass** (pas "Allow", qui exigerait quand meme une connexion).
Meme mecanisme utilise pour `/media/*` (images publicitaires servies a Meta).

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

## Deploiement autonome de projets (Vercel)

`test_deploy_agent` peut proposer un vrai deploiement Vercel du projet en cours
(`stage_vercel_deploy`) -- **jamais deploye directement**, meme principe que la publication :
en attente dans `/approvals` jusqu'a validation humaine. Le jeton Vercel du client (obtenu sur
vercel.com/account/tokens) se configure sur `/clients/<id>`, section "Identifiants Vercel".

**A savoir** : Vercel protege par defaut chaque URL de deploiement derriere sa propre connexion
(SSO) sur un compte personnel/Hobby -- ce n'est pas un bug de ce projet. Pour un site
publiquement accessible sans connexion Vercel, desactive "Deployment Protection" dans les
parametres du projet Vercel, ou assigne-lui un domaine de production.

## Tests d'intrusion hebdomadaires (`/security`)

Scan actif reel (nmap : ports ; nikto : vulnerabilites web) contre des cibles **explicitement
autorisees** par toi dans `/security` -- jamais une cible devinee ou fournie par un agent. Un
planificateur interne (`webapp/job_runner.py`, thread separe du worker de jobs) relance
automatiquement chaque cible toutes les 7 jours.

**Important -- conditions d'utilisation des hebergeurs tiers** : scanner activement un projet
heberge chez un tiers (Vercel, Netlify...) peut violer leurs conditions d'utilisation, meme
si c'est ton propre projet -- l'infrastructure sous-jacente est partagee. `/security` affiche
un avertissement a l'ajout d'une cible "tierce", mais la responsabilite de verifier les
conditions de l'hebergeur avant d'autoriser reste la tienne. Aucun risque de ce type pour notre
propre serveur (infrastructure entierement possedee).

Necessite `nmap` et `nikto` installes sur le serveur (`sudo apt install nmap nikto`).

## Chatbot WhatsApp

Meme API Graph que Facebook/Instagram -- ajoute le produit **"WhatsApp Business Platform"** a
l'app Meta for Developers deja utilisee pour Facebook/Instagram (pas une nouvelle app). A
l'inverse de Meta/Vercel, les identifiants WhatsApp sont **au niveau plateforme** (un seul
numero pour toute l'agence), dans `.env` :

1. Dans l'app Meta, section WhatsApp -> ajoute un numero de test (ou un numero verifie pour la
   prod), recupere le `Phone number ID`, le jeton d'acces temporaire (ou permanent via un
   utilisateur systeme) et l'**App Secret** (Parametres de l'app -> De base).
2. Renseigne `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_APP_SECRET` dans
   `.env`. Choisis une chaine pour `WHATSAPP_WEBHOOK_VERIFY_TOKEN` (n'importe quoi, juste
   utilise aussi cote Meta a l'etape suivante).
3. Configure le webhook cote Meta : URL `https://studio.maelya.tech/webhooks/whatsapp`, jeton
   de verification = celui choisi a l'etape 2, champ d'abonnement `messages`.
4. Renseigne ton propre numero (format E.164, ex. `2250700000000`) dans
   `OWNER_WHATSAPP_NUMBER` -- c'est ce qui te donne le controle complet, tout autre numero est
   traite comme un prospect.
5. Nouvelle Application Cloudflare Access (Bypass) sur `/webhooks/whatsapp*` -- meme mecanisme
   que `/media`, `/demande`, `/static` (Meta ne peut pas passer par le mur email interactif).

**Usage proprietaire** : `code: <instruction>` ou `marketing: <instruction>` cree un job comme
depuis le tableau de bord ; tout autre message renvoie l'aide. **Aucune approbation ne se fait
depuis WhatsApp** -- une publication/un deploiement propose reste a valider sur `/approvals`,
WhatsApp ne contourne jamais cette barriere.

**Usage prospect/client** : n'importe quel autre numero qui ecrit est traite exactement comme
`/demande` (memes protections, `research_agent` seul jamais le supervisor complet, meme
plafond quotidien). Le numero WhatsApp du client est enregistre automatiquement et sert aux
notifications de suivi (devis pret, site deploye) -- textes fixes uniquement, jamais le contenu
genere par un agent sans relecture humaine au prealable.

**Securite critique** : `X-Hub-Signature-256` est verifiee sur chaque requete entrante avant
de faire confiance a quoi que ce soit dans le payload -- sans ca, n'importe qui pourrait
usurper `OWNER_WHATSAPP_NUMBER` dans une requete forgee.

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
