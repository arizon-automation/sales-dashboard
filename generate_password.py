"""
Helper script to generate password hashes for users
Run this to create hashed passwords for your team members
"""
import bcrypt

def hash_password(password):
    """Generate a bcrypt hash for a password"""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')

if __name__ == "__main__":
    print("=== Password Hash Generator ===")
    print("This will help you create password hashes for your team members\n")
    
    while True:
        password = input("Enter password (or 'quit' to exit): ")
        if password.lower() == 'quit':
            break
        
        hashed = hash_password(password)
        print(f"\nHashed password: {hashed}")
        print("\nCopy this hash and paste it in .streamlit/secrets.toml\n")
        print("-" * 50 + "\n")

