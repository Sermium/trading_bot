"""
Secure API Configuration
NEVER hardcode API keys - use environment variables or .env file
"""
import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class ExchangeCredentials:
    """Secure credential storage"""
    api_key: str
    api_secret: str
    passphrase: Optional[str] = None
    
    @classmethod
    def from_env(cls, exchange: str) -> 'ExchangeCredentials':
        """
        Load credentials from environment variables
        
        Expected env vars:
        - {EXCHANGE}_API_KEY
        - {EXCHANGE}_API_SECRET
        - {EXCHANGE}_PASSPHRASE (optional)
        
        Example for Blofin:
        - BLOFIN_API_KEY
        - BLOFIN_API_SECRET
        - BLOFIN_PASSPHRASE
        """
        prefix = exchange.upper()
        
        api_key = os.getenv(f'{prefix}_API_KEY')
        api_secret = os.getenv(f'{prefix}_API_SECRET')
        passphrase = os.getenv(f'{prefix}_PASSPHRASE')
        
        if not api_key or not api_secret:
            raise ValueError(
                f"Missing API credentials. Set environment variables:\n"
                f"  export {prefix}_API_KEY='your_api_key'\n"
                f"  export {prefix}_API_SECRET='your_api_secret'\n"
                f"  export {prefix}_PASSPHRASE='your_passphrase'  # if required"
            )
        
        return cls(
            api_key=api_key,
            api_secret=api_secret,
            passphrase=passphrase
        )
    
    @classmethod
    def from_env_file(cls, exchange: str, env_file: str = '.env') -> 'ExchangeCredentials':
        """Load credentials from .env file"""
        if os.path.exists(env_file):
            with open(env_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        os.environ[key.strip()] = value.strip().strip('"\'')
        
        return cls.from_env(exchange)


# Template for .env file
ENV_TEMPLATE = """# Trading Bot Configuration
# NEVER commit this file to git!

# Blofin Credentials
BLOFIN_API_KEY=your_api_key_here
BLOFIN_API_SECRET=your_api_secret_here
BLOFIN_PASSPHRASE=your_passphrase_here

# MEXC Credentials (optional)
MEXC_API_KEY=
MEXC_API_SECRET=

# Hyperliquid Credentials (optional)
HYPERLIQUID_PRIVATE_KEY=

# Trading Settings
DEFAULT_LEVERAGE=10
DEFAULT_CAPITAL_PCT=10
TESTNET_MODE=true
"""


def create_env_template(filepath: str = '.env.template'):
    """Create a template .env file"""
    with open(filepath, 'w') as f:
        f.write(ENV_TEMPLATE)
    print(f"Created {filepath} - copy to .env and fill in your credentials")


def setup_credentials_interactive():
    """Interactive setup for credentials"""
    print("\n" + "="*50)
    print("  SECURE CREDENTIAL SETUP")
    print("="*50)
    print("\nThis will create a .env file with your credentials.")
    print("The .env file should NEVER be shared or committed to git.\n")
    
    exchange = input("Exchange (blofin/mexc/hyperliquid): ").strip().lower()
    
    if exchange == 'blofin':
        api_key = input("API Key: ").strip()
        api_secret = input("API Secret: ").strip()
        passphrase = input("Passphrase: ").strip()
        
        env_content = f"""# Blofin Credentials - KEEP SECRET!
BLOFIN_API_KEY={api_key}
BLOFIN_API_SECRET={api_secret}
BLOFIN_PASSPHRASE={passphrase}

# Settings
TESTNET_MODE=true
DEFAULT_LEVERAGE=10
"""
    elif exchange == 'mexc':
        api_key = input("API Key: ").strip()
        api_secret = input("API Secret: ").strip()
        
        env_content = f"""# MEXC Credentials - KEEP SECRET!
MEXC_API_KEY={api_key}
MEXC_API_SECRET={api_secret}

# Settings
TESTNET_MODE=true
DEFAULT_LEVERAGE=10
"""
    elif exchange == 'hyperliquid':
        private_key = input("Private Key: ").strip()
        
        env_content = f"""# Hyperliquid Credentials - KEEP SECRET!
HYPERLIQUID_PRIVATE_KEY={private_key}

# Settings
TESTNET_MODE=true
DEFAULT_LEVERAGE=10
"""
    else:
        print(f"Unknown exchange: {exchange}")
        return
    
    # Write .env file
    with open('.env', 'w') as f:
        f.write(env_content)
    
    # Create .gitignore if it doesn't exist
    gitignore_content = """# Secrets - NEVER commit
.env
*.pem
*_secret*
*_key*

# Python
__pycache__/
*.pyc
.venv/
venv/

# Logs
*.log
logs/
"""
    
    if not os.path.exists('.gitignore'):
        with open('.gitignore', 'w') as f:
            f.write(gitignore_content)
        print("Created .gitignore to protect your secrets")
    
    print(f"\n[OK] Credentials saved to .env")
    print("[WARNING]  NEVER share or commit this file!")
    print("\nYou can now run: python run_backtest_live.py")


if __name__ == "__main__":
    setup_credentials_interactive()
