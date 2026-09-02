# -*- coding: utf-8 -*-
import asyncio, time
from neomodel import config as neo_config
from infrastructure.config import settings
neo_config.DATABASE_URL = settings.get_database_url()

async def main():
    from services.pattern_miner_service import PatternMinerService
    svc = PatternMinerService()
    t = time.time()
    try:
        res = await asyncio.wait_for(
            svc.generate_all(
                check_existing=True,
                limit_per_method=20,
                min_support=0.15,
                max_pool_size=500,
                statements_per_doc_cap=60,
            ),
            timeout=90,
        )
        print('OK %ss, corpus=%d, pool=%d' % (
            round(time.time()-t, 1), res['corpus_size'], res['corpus_pool_size']))
        for m in res.get('methods', []):
            print('  %s: %d groups, %d new' % (m['label'], len(m['groups']), m['count']))
            for g in m['groups'][:2]:
                ns = g.get('new_statements', [])[:1]
                if ns:
                    s = ns[0]
                    chk = s.get('check') or {}
                    print('    [%s] %s -[%s]-> %s  (%s)' % (
                        g['operation_label'], s['subject_text'],
                        s['predicate'], s['object_text'], chk.get('status', '-')))
    except asyncio.TimeoutError:
        print('TIMEOUT after %ss' % round(time.time()-t, 1))
    except Exception as e:
        import traceback
        print('ERROR: %s' % type(e).__name__)
        traceback.print_exc()

asyncio.run(main())