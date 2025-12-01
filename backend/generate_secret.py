import secrets

# Generate a 64-byte (512-bit) hex string, which is very secure for HS256/HS512
secret_key = secrets.token_hex(64)
print(f"Your new SECRET_KEY:\n{secret_key}")
