#!/usr/bin/env python3
"""
Quick Setup Script for Trading Bot
Run this first to configure your exchange credentials
"""
import os
import sys


def print_banner():
    print("""
==============================================================
         BTC SCALPING BOT - QUICK SETUP                       
         StochRSI + MACD Strategy                             
==============================================================
    """)


def setup_blofin():
    print("\n[NOTE] BLOFIN SETUP")
    print("-" * 40)
    print("API keys are OPTIONAL for backtesting!")
    print("Public data (candlesticks) doesn't need auth.")
    print("")
    print("Only enter keys if you want to do LIVE trading.")
    print("Press Enter to skip any field.\n")
    
    api_key = input("API Key (or press Enter to skip): ").strip()
    api_secret = input("API Secret (or press Enter to skip): ").strip()
    passphrase = input("Passphrase (or press Enter to skip): ").strip()
    
    return {
        'BLOFIN_API_KEY': api_key,
        'BLOFIN_API_SECRET': api_secret,
        'BLOFIN_PASSPHRASE': passphrase
    }


def setup_mexc():
    print("\n📝 MEXC SETUP")
    print("-" * 40)
    print("Enter your MEXC API credentials.\n")
    
    api_key = input("API Key: ").strip()
    api_secret = input("API Secret: ").strip()
    
    if not all([api_key, api_secret]):
        print("❌ All fields are required!")
        return False
    
    return {
        'MEXC_API_KEY': api_key,
        'MEXC_API_SECRET': api_secret
    }


def save_env(credentials: dict):
    """Save credentials to .env file"""
    
    # Check if .env exists
    if os.path.exists('.env'):
        overwrite = input("\n[WARNING] .env file exists. Overwrite? (y/n): ").strip().lower()
        if overwrite != 'y':
            print("Cancelled.")
            return False
    
    # Build env content
    content = "# Trading Bot Credentials\n"
    content += "# WARNING: NEVER share this file or commit to git!\n\n"
    
    for key, value in credentials.items():
        content += f"{key}={value}\n"
    
    content += "\n# Trading Settings\n"
    content += "TESTNET_MODE=false\n"
    content += "DEFAULT_LEVERAGE=10\n"
    content += "DEFAULT_CAPITAL_PCT=10\n"
    
    # Write file
    with open('.env', 'w', encoding='utf-8') as f:
        f.write(content)
    
    # Create/update .gitignore
    gitignore_content = ".env\n*.pyc\n__pycache__/\n*.log\n"
    
    if os.path.exists('.gitignore'):
        with open('.gitignore', 'r', encoding='utf-8') as f:
            if '.env' not in f.read():
                with open('.gitignore', 'a', encoding='utf-8') as f:
                    f.write("\n.env\n")
    else:
        with open('.gitignore', 'w', encoding='utf-8') as f:
            f.write(gitignore_content)
    
    print("\n[OK] Credentials saved to .env")
    print("[OK] .gitignore updated to protect your secrets")
    
    return True


def test_connection(exchange: str):
    """Test the exchange connection"""
    print(f"\n[TEST] Testing {exchange.upper()} connection...")
    
    # Load .env
    if os.path.exists('.env'):
        with open('.env', 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()
    
    if exchange == 'blofin':
        try:
            from exchanges.blofin_data import BlofinDataFetcher
            
            fetcher = BlofinDataFetcher(
                api_key=os.getenv('BLOFIN_API_KEY'),
                api_secret=os.getenv('BLOFIN_API_SECRET'),
                passphrase=os.getenv('BLOFIN_PASSPHRASE')
            )
            
            return fetcher.test_connection()
        except ImportError:
            print("[WARNING] Could not import Blofin module")
            return False
        except Exception as e:
            print(f"[ERROR] Connection error: {e}")
            return False
    
    return False


def main():
    print_banner()
    
    print("Which exchange do you want to configure?")
    print("  1. Blofin")
    print("  2. MEXC")
    print("  3. Exit")
    
    choice = input("\nSelect (1-3): ").strip()
    
    if choice == '1':
        credentials = setup_blofin()
        exchange = 'blofin'
    elif choice == '2':
        credentials = setup_mexc()
        exchange = 'mexc'
    elif choice == '3':
        print("Goodbye!")
        return
    else:
        print("Invalid choice")
        return
    
    if not credentials:
        return
    
    if save_env(credentials):
        # Test connection
        test = input("\nTest connection now? (y/n): ").strip().lower()
        if test == 'y':
            if test_connection(exchange):
                print("\n[SUCCESS] Setup complete! You can now run:")
                print(f"   python run_backtest_live.py --exchange {exchange} --days 30")
            else:
                print("\n[WARNING] Connection test failed. Check your credentials.")
        else:
            print("\n[SUCCESS] Setup complete! Run:")
            print(f"   python run_backtest_live.py --exchange {exchange} --days 30")


if __name__ == "__main__":
    main()
