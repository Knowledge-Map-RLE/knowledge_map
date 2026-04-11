"""
CLI entry point for auto-review.
Thin wrapper around application.actions.auto_review.auto_review_pending_edges.

Usage:
    python auto_review.py <doc_id> [--dry]
"""
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.dirname(__file__))

from neomodel import config
config.DATABASE_URL = 'bolt://neo4j:password@127.0.0.1:7687'

from adapters.repositories.action_repository import ActionRepository


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Auto-review pending LEADS_TO edges')
    parser.add_argument('doc_id', help='Document ID')
    parser.add_argument('--dry', action='store_true', help='Dry run (no updates)')
    args = parser.parse_args()

    import asyncio
    from application.actions.auto_review import auto_review_pending_edges

    repo = ActionRepository()
    result = asyncio.run(auto_review_pending_edges(
        doc_id=args.doc_id,
        action_repo=repo,
        dry_run=args.dry,
    ))

    mode = 'DRY RUN' if args.dry else 'LIVE'
    print(f"\n{mode} — Results for doc {args.doc_id}:")
    print(f"  Confirmed: {result.confirmed}")
    print(f"  Rejected:  {result.rejected}")
    print(f"  Total:     {result.total}")

    if result.confirmed_edges:
        print("\n=== CONFIRMED ===")
        for e in result.confirmed_edges:
            print(f"  [{e['relation_subtype']}] {e['src_phrase'][:45]} --> {e['tgt_phrase'][:45]}  ({e['reason']})")

    if result.rejected_edges:
        print("\n=== REJECTED ===")
        for e in result.rejected_edges:
            print(f"  [{e['relation_subtype']}] {e['src_phrase'][:45]} --> {e['tgt_phrase'][:45]}  ({e['reason']})")


if __name__ == '__main__':
    main()
