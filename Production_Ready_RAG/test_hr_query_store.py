from hr_queries.hr_query_store import HRQueryStore


store = HRQueryStore()

query_id = store.save_query(
    question="What is the XYZ employee benefit policy?",
    session_id="demo-session-001"
)

print("Saved Query ID:", query_id)

print()
print("Stored HR Queries")
print("=" * 70)

queries = store.get_all_queries()

for query in queries:

    print(
        f"ID       : {query[0]}"
    )

    print(
        f"Question : {query[1]}"
    )

    print(
        f"Session  : {query[2]}"
    )

    print(
        f"Created  : {query[3]}"
    )

    print(
        f"Status   : {query[4]}"
    )

    print("-" * 70)