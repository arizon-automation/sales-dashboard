import requests
import hmac
import hashlib
import base64

api_id = "57cffc0f-8d6b-4aee-9e6a-f40730280617"
api_key = "nyEfy1kms7ksRTmY3CUY8A8sF36Gqe9qMB5huZNwP29q4Jk3CO9WvYK1BFPYQQwmpbO3sxORCweX0sGuitCWw=="

# According to Unleashed docs, the signature should be:
# HMAC-SHA256 of the query string using the API key

# Test 1: Simple request with page parameter (required)
endpoint = "/SalesOrders"
params = "page=1"  # Query string as simple string
full_url = f"{endpoint}?{params}"

print(f"Testing: {full_url}")
print(f"Query string for signature: {params}")

# Generate signature from query string only (not the full path)
message = params.encode('utf-8')
signature_bytes = hmac.new(api_key.encode('utf-8'), message, hashlib.sha256).digest()
signature = base64.b64encode(signature_bytes).decode('utf-8')

print(f"Signature: {signature}")

headers = {
    'Accept': 'application/json',
    'api-auth-id': api_id,
    'api-auth-signature': signature
}

response = requests.get(f"https://api.unleashedsoftware.com{full_url}", headers=headers)
print(f"Status Code: {response.status_code}")
if response.status_code == 200:
    print(f"SUCCESS! Response: {response.text[:200]}")
else:
    print(f"Error: {response.text}")

print("\n" + "="*50 + "\n")

# Test 2: According to docs, signature should be generated from ENTIRE query string
params2 = "pageSize=1&page=1"
full_url2 = f"{endpoint}?{params2}"

print(f"Testing: {full_url2}")
print(f"Query string for signature: {params2}")

message2 = params2.encode('utf-8')
signature_bytes2 = hmac.new(api_key.encode('utf-8'), message2, hashlib.sha256).digest()
signature2 = base64.b64encode(signature_bytes2).decode('utf-8')

headers2 = {
    'Accept': 'application/json',
    'api-auth-id': api_id,
    'api-auth-signature': signature2
}

response2 = requests.get(f"https://api.unleashedsoftware.com{full_url2}", headers=headers2)
print(f"Status Code: {response2.status_code}")
if response2.status_code == 200:
    print(f"SUCCESS! Response: {response2.text[:200]}")
else:
    print(f"Error: {response2.text}")

