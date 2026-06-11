import httpx

KEY = "$2a$10$KoACzRcY64gqyT2LnOQ9UOG06ZE8gub8FZLzOm3B5nwUxz7mDEN92"

# Test creating a bin
r = httpx.post(
    "https://api.jsonbin.io/v3/b",
    headers={
        "X-Master-Key": KEY,
        "Content-Type": "application/json",
        "X-Bin-Name": "oren-test",
    },
    json=[{"test": 1}],
    timeout=15,
)
print("Status:", r.status_code)
print("Response:", r.text[:500])
