import random
import string

def generate_account_number() -> str:
    """Generate a 16-digit account number with LB prefix"""
    digits = ''.join(random.choices(string.digits, k=14))
    return f"LB{digits}"

def generate_iban(account_number: str) -> str:
    """Generate IBAN in Lebanese format: LB + 2 check digits + 20 char BBAN"""
    bban = account_number.replace("LB", "").zfill(20)
    # Lebanese IBAN format: LB + check digits + BBAN
    check_digits = str(random.randint(10, 99))
    return f"LB{check_digits}{bban}"