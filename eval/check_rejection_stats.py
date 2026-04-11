from neomodel import config, db
config.DATABASE_URL = 'bolt://neo4j:password@127.0.0.1:7687'

# Overall stats
total, _ = db.cypher_query('MATCH ()-[r:LEADS_TO]->() RETURN count(r)')
confirmed, _ = db.cypher_query('MATCH ()-[r:LEADS_TO {status: "confirmed"}]->() RETURN count(r)')
rejected, _ = db.cypher_query('MATCH ()-[r:LEADS_TO {status: "rejected"}]->() RETURN count(r)')
pending, _ = db.cypher_query('MATCH ()-[r:LEADS_TO {status: "pending"}]->() RETURN count(r)')

print(f"Total:      {total[0][0]}")
print(f"Confirmed:  {confirmed[0][0]}")
print(f"Rejected:   {rejected[0][0]}")
print(f"Pending:    {pending[0][0]}")
if total[0][0] > 0:
    print(f"Reject rate: {rejected[0][0]/total[0][0]*100:.1f}%")

# Rejection reasons
print("\nTop rejection reasons:")
rows, _ = db.cypher_query(
    'MATCH ()-[r:LEADS_TO {status: "rejected"}]->() '
    'RETURN r.reason AS reason, count(*) AS cnt '
    'ORDER BY cnt DESC LIMIT 20'
)
for r in rows:
    print(f"  {r[1]:>6}  {r[0]}")
