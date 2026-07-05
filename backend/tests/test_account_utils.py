from app.utils.account_utils import generate_account_number, generate_iban

def test_account_number_format():
    acc = generate_account_number()
    assert acc.startswith("LB")
    assert len(acc) == 16

def test_iban_format():
    acc = generate_account_number()
    iban = generate_iban(acc)
    assert iban.startswith("LB")
    assert len(iban) <= 34

def test_account_number_unique():
    numbers = {generate_account_number() for _ in range(100)}
    assert len(numbers) == 100