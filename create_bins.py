import httpx

KEY = "$2a$10$KoACzRcY64gqyT2LnOQ9UOG06ZE8gub8FZLzOm3B5nwUxz7mDEN92"

for name in ["oren-ratings", "oren-feedback"]:
    r = httpx.post(
        "https://api.jsonbin.io/v3/b",
        headers={
            "X-Master-Key": KEY,
            "Content-Type": "application/json",
            "X-Bin-Name": name,
        },
        json=[{"init": True}],
        timeout=15,
    )
    print(f"{name}: {r.status_code} - {r.text[:200]}")
