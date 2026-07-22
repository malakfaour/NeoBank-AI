import pytest
from sqlalchemy import select

from app.models.user import User
from app.models.wallet import Wallet, WalletCurrency
from app.services import account_service


async def _create_user(db_session, *, name: str, email: str, phone: str) -> User:
    user = User(
        full_name=name,
        email=email,
        phone=phone,
        password_hash="test-password-hash",
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.mark.asyncio
async def test_create_wallets_retries_after_account_number_collision(
    db_session,
    monkeypatch,
):
    collision_account = "LB00000000000000"

    seed_user = await _create_user(
        db_session,
        name="Account Collision Seed",
        email="account-collision-seed@neobank.test",
        phone="+96179990126",
    )
    db_session.add(
        Wallet(
            user_id=seed_user.id,
            currency=WalletCurrency.USD,
            balance=0,
            account_number=collision_account,
            # Deliberately different from the generated IBAN so this attempt
            # violates only the account_number unique constraint.
            iban="LB30" + ("8" * 20),
        )
    )
    await db_session.commit()

    # Keep the target user uncommitted. This matches registration, where the
    # user is flushed before create_wallets_for_user() is called.
    target_user = await _create_user(
        db_session,
        name="Account Collision Target",
        email="account-collision-target@neobank.test",
        phone="+96179990127",
    )

    generated_accounts = iter(
        [
            collision_account,
            "LB00000000000001",
            "LB00000000000002",
            "LB00000000000003",
        ]
    )
    generator_calls: list[str] = []

    def fake_generate_account_number() -> str:
        account_number = next(generated_accounts)
        generator_calls.append(account_number)
        return account_number

    def fake_generate_iban(account_number: str) -> str:
        return f"LB10{account_number[2:].zfill(20)}"

    monkeypatch.setattr(
        account_service,
        "generate_account_number",
        fake_generate_account_number,
    )
    monkeypatch.setattr(
        account_service,
        "generate_iban",
        fake_generate_iban,
    )

    created_wallets = await account_service.create_wallets_for_user(
        target_user.id,
        db_session,
    )

    result = await db_session.execute(
        select(Wallet).where(Wallet.user_id == target_user.id)
    )
    persisted_wallets = result.scalars().all()

    persisted_user = await db_session.get(User, target_user.id)

    assert persisted_user is not None
    assert len(created_wallets) == len(WalletCurrency)
    assert len(persisted_wallets) == len(WalletCurrency)
    assert generator_calls == [
        collision_account,
        "LB00000000000001",
        "LB00000000000002",
        "LB00000000000003",
    ]
    assert collision_account not in {
        wallet.account_number for wallet in persisted_wallets
    }
    assert len(
        {wallet.account_number for wallet in persisted_wallets}
    ) == len(WalletCurrency)
    assert len(
        {wallet.iban for wallet in persisted_wallets}
    ) == len(WalletCurrency)


@pytest.mark.asyncio
async def test_create_wallets_hard_fails_after_five_iban_collisions(
    db_session,
    monkeypatch,
):
    collision_iban = "LB20" + ("9" * 20)

    seed_user = await _create_user(
        db_session,
        name="IBAN Collision Seed",
        email="iban-collision-seed@neobank.test",
        phone="+96179990128",
    )
    db_session.add(
        Wallet(
            user_id=seed_user.id,
            currency=WalletCurrency.LBP,
            balance=0,
            account_number="LB88888888888888",
            iban=collision_iban,
        )
    )
    await db_session.commit()

    # As in registration, this user is flushed but not committed.
    target_user = await _create_user(
        db_session,
        name="IBAN Collision Target",
        email="iban-collision-target@neobank.test",
        phone="+96179990129",
    )

    generated_accounts = [
        "LB70000000000000",
        "LB70000000000001",
        "LB70000000000002",
        "LB70000000000003",
        "LB70000000000004",
    ]
    generated_iter = iter(generated_accounts)
    generator_calls: list[str] = []

    def fake_generate_account_number() -> str:
        account_number = next(generated_iter)
        generator_calls.append(account_number)
        return account_number

    def fake_generate_iban(account_number: str) -> str:
        # Every account number is unique; only the IBAN collides.
        return collision_iban

    monkeypatch.setattr(
        account_service,
        "generate_account_number",
        fake_generate_account_number,
    )
    monkeypatch.setattr(
        account_service,
        "generate_iban",
        fake_generate_iban,
    )

    with pytest.raises(
        account_service.AccountIdentifierGenerationError,
        match=r"Unable to generate unique account identifiers after 5 attempts",
    ):
        await account_service.create_wallets_for_user(
            target_user.id,
            db_session,
        )

    assert generator_calls == generated_accounts

    result = await db_session.execute(
        select(Wallet).where(Wallet.user_id == target_user.id)
    )
    assert result.scalars().all() == []

    # The failed savepoints must not roll back the caller's outer transaction.
    persisted_user = await db_session.get(User, target_user.id)
    assert persisted_user is not None

    await db_session.rollback()
