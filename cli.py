#!/usr/bin/env python3
"""Point d'entree unique de l'equipe d'agents.

IMPORTANT -- ce n'est PAS un chat interactif : chaque commande est un aller-retour unique qui
se termine et rend la main au terminal. Si un agent pose une question dans son resume, ne tape
PAS ta reponse a la suite dans le terminal (PowerShell/cmd essaiera de l'executer comme une
commande) -- relance cli.py avec ta reponse comme nouvelle tache, en gardant le MEME
--project-dir (code) ou --thread (marketing) : grace a la memoire persistante (SQLite, dans
.state/ du projet), la conversation continue plutot que de repartir de zero.

Usage:
    python cli.py code "description de la tache/du projet" [--project-dir PATH] [--allow-push]
    python cli.py marketing "brief marketing" [--thread NOM]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver

from common.guardrails import set_allow_push
from common.models import get_max_iterations
from common.paths import OUTPUT_DIR
from common.usage_tracking import usage_callbacks
from common.workdir import set_working_directory


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:50] or "projet"


def _print_final_message(result: dict) -> None:
    messages = result.get("messages", [])
    if not messages:
        print("(aucune reponse)")
        return
    content = getattr(messages[-1], "content", messages[-1])
    print("\n--- Resume ---")
    print(content)


def run_code(args: argparse.Namespace) -> None:
    from coding_team.supervisor import build_supervisor

    set_allow_push(args.allow_push)
    project_dir = (
        Path(args.project_dir) if args.project_dir else OUTPUT_DIR / "projects" / _slugify(args.task)
    )
    resolved = set_working_directory(project_dir)
    print(f"[coding_team] repertoire de travail : {resolved}")
    if not args.allow_push:
        print("[coding_team] garde-fou actif : git push bloque (relancer avec --allow-push pour l'autoriser)")

    checkpoint_db = resolved / ".state" / "conversation.sqlite"
    checkpoint_db.parent.mkdir(parents=True, exist_ok=True)

    with SqliteSaver.from_conn_string(str(checkpoint_db)) as checkpointer:
        supervisor = build_supervisor(checkpointer=checkpointer)
        result = supervisor.invoke(
            {"messages": [{"role": "user", "content": args.task}]},
            config={
                "recursion_limit": args.max_iterations,
                "callbacks": usage_callbacks("coding_supervisor"),
                "configurable": {"thread_id": "main"},
            },
        )
    _print_final_message(result)
    print(
        f"\n[coding_team] Pour repondre ou continuer, relance avec le MEME dossier :\n"
        f'  .venv\\Scripts\\python.exe cli.py code "ta reponse" --project-dir "{resolved}"'
    )


def run_marketing(args: argparse.Namespace) -> None:
    from marketing_team.supervisor import build_supervisor

    marketing_dir = OUTPUT_DIR / "marketing"
    checkpoint_db = marketing_dir / ".state" / f"conversation-{args.thread}.sqlite"
    checkpoint_db.parent.mkdir(parents=True, exist_ok=True)

    with SqliteSaver.from_conn_string(str(checkpoint_db)) as checkpointer:
        supervisor = build_supervisor(checkpointer=checkpointer)
        result = supervisor.invoke(
            {"messages": [{"role": "user", "content": args.brief}]},
            config={
                "recursion_limit": args.max_iterations,
                "callbacks": usage_callbacks("marketing_supervisor"),
                "configurable": {"thread_id": args.thread},
            },
        )
    _print_final_message(result)
    print(f"[marketing_team] brouillons dans : {marketing_dir}")
    print(
        f'[marketing_team] Pour continuer cette conversation : '
        f'.venv\\Scripts\\python.exe cli.py marketing "ta reponse" --thread {args.thread}'
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Equipe d'agents autonomes (coding + marketing).")
    subparsers = parser.add_subparsers(dest="command", required=True)

    code_parser = subparsers.add_parser("code", help="Lance l'equipe de developpement sur une tache.")
    code_parser.add_argument("task", help="Description de la tache/du projet.")
    code_parser.add_argument(
        "--project-dir", help="Dossier du projet cible (par defaut : output/projects/<slug-de-la-tache>)."
    )
    code_parser.add_argument("--allow-push", action="store_true", help="Autorise git push pour ce run.")
    code_parser.add_argument(
        "--max-iterations", type=int, default=get_max_iterations("coding_supervisor") * 6,
        help="Limite d'etapes du graphe multi-agent (garde-fou anti-boucle-infinie).",
    )
    code_parser.set_defaults(func=run_code)

    marketing_parser = subparsers.add_parser("marketing", help="Lance l'equipe marketing sur un brief.")
    marketing_parser.add_argument(
        "brief", help="Brief marketing (ex: 'sequence de bienvenue 3 emails pour un SaaS de facturation')."
    )
    marketing_parser.add_argument(
        "--max-iterations", type=int, default=get_max_iterations("marketing_supervisor") * 6,
        help="Limite d'etapes du graphe multi-agent (garde-fou anti-boucle-infinie).",
    )
    marketing_parser.add_argument(
        "--thread", default="default",
        help="Nom de la conversation a continuer (meme nom = memoire conservee). Defaut : 'default'.",
    )
    marketing_parser.set_defaults(func=run_marketing)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
