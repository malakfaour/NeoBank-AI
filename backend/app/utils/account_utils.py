import random
import string

def generate_account_number() -> str:
    """Generate a 16-digit account number with LB prefix"""
    digits = ''.join(random.choices(string.digits, k=14))
    return f"LB{digits}"

def _iban_mod97(iban: str) -> int:
    """ISO 7064 mod-97-10 check: move country code + check digits to the
    end, convert letters to numbers (A=10...Z=35), and reduce mod 97 --
    matches the algorithm in beneficiaries.py's validate_iban() exactly,
    so an IBAN built with check digits from this function always passes
    that endpoint's checksum validation."""
    rearranged = iban[4:] + iban[:4]
    numeric_iban = ""
    for char in rearranged:
        numeric_iban += char if char.isdigit() else str(ord(char) - 55)
    return int(numeric_iban) % 97


def generate_iban(account_number: str) -> str:
    """Generate IBAN in Lebanese format: LB + 2 check digits + 20 char BBAN"""
    bban = account_number.replace("LB", "").zfill(20)
    # Compute real ISO 7064 mod-97-10 check digits (placeholder "00" first,
    # per the standard algorithm) instead of a random 2-digit number --
    # random digits pass the checksum by chance only ~1/97 of the time,
    # which made saving a real transfer recipient as a beneficiary fail
    # with "Invalid IBAN checksum" for nearly every generated IBAN.
    remainder = _iban_mod97(f"LB00{bban}")
    check_digits = f"{98 - remainder:02d}"
    return f"LB{check_digits}{bban}"