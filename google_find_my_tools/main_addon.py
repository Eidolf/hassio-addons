import sys
from Auth.adm_token_retrieval import get_adm_token
from Auth.username_provider import get_username

def main():
    print("[Add-on] Starting Authentication Flow...")
    try:
        # This will trigger the auth flow if secrets are missing,
        # or just load them if they exist.
        get_adm_token(get_username())
        
        print("[Add-on] Authentication successful. Secrets are generated/loaded.")
        print("[Add-on] Exiting python script to allow secrets copying...")
        sys.exit(0)
    except Exception as e:
        print(f"[Add-on] Authentication failed: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
