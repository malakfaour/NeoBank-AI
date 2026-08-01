"""
DEVATTECH-94: monthly account statement generation.

Pure/synchronous CSV and PDF generation (stdlib csv / reportlab) plus
async balance-reconstruction, kept out of the endpoint per this
codebase's services/ layer convention.

Balance reconstruction walks Transaction rows backward from each
wallet's CURRENT (always-correct) balance to derive opening/closing
balances for the requested month. This is only reliable for a currency
whose relevant transactions all postdate the three ledger fixes
(Exchange.exchange_leg, Reversal/Adjustment.ledger_direction).

IMPORTANT: a pre-fix row's real effect on the wallet was already
correctly applied to wallet.balance at the time it happened -- what's
missing is only the ABILITY to reconstruct which DIRECTION that
already-happened effect was, from Transaction data alone. Treating an
unknown direction as zero would silently produce a plausible-looking
but WRONG number (the reconstruction error would propagate backward
through every earlier month too, not just the one containing the
ambiguous row) -- so this module does NOT do that. If any transaction
in the walk for a given currency has an unresolvable direction
(exchange_leg or ledger_direction is None on a category that requires
it), that currency's opening_balance/closing_balance are omitted
entirely (None) and balance_reconciled=False is set instead -- the
individual transaction rows are still returned/rendered, since those
are recorded facts, not inferred values.
"""
import csv
import io
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.transaction import ExchangeLegType, LedgerDirection, Transaction
from app.models.user import User
from app.models.wallet import Wallet


@dataclass
class StatementTransactionRow:
    id: int
    created_at: datetime
    category: str | None
    type_label: str
    amount: Decimal
    status: str
    counterparty_name: str | None


@dataclass
class CurrencyStatement:
    currency: str
    opening_balance: Decimal | None
    closing_balance: Decimal | None
    balance_reconciled: bool
    transactions: list[StatementTransactionRow]


def _derive_type_label(tx: Transaction, user_id: int) -> str:
    """
    Independent, minimal copy of transactions.py's private
    _derive_transaction_type -- not imported from there, to avoid a
    circular import (transactions.py imports FROM this module for the
    new endpoint). Kept in sync manually if transactions.py's category
    taxonomy changes.
    """
    if tx.sender_id == tx.receiver_id:
        if tx.category == "Exchange":
            return "exchange"
        if tx.category == "Bills":
            return "bill"
        if tx.category == "Adjustment":
            return "adjustment"
        if tx.category == "Reversal":
            return "reversal"
        return "topup"
    return "send" if tx.sender_id == user_id else "receive"


def _signed_effect(tx: Transaction, user_id: int) -> Decimal | None:
    """
    Signed effect of `tx` on `user_id`'s wallet balance, in tx's own
    currency. Returns None if the effect cannot be determined from
    available data -- see module docstring.
    """
    if tx.sender_id != tx.receiver_id:
        return -tx.amount if tx.sender_id == user_id else tx.amount

    if tx.category == "TopUp":
        return tx.amount
    if tx.category == "Bills":
        return -tx.amount
    if tx.category == "Exchange":
        if tx.exchange_leg is None:
            return None
        return tx.amount if tx.exchange_leg == ExchangeLegType.credit else -tx.amount
    if tx.category in ("Reversal", "Adjustment"):
        if tx.ledger_direction is None:
            return None
        return tx.amount if tx.ledger_direction == LedgerDirection.credit else -tx.amount

    # Unrecognized self-transaction category (shouldn't occur in
    # practice) -- defensive fallback only, NOT the same "known
    # ambiguous, data exists but direction is missing" case handled by
    # the None-returns above.
    return Decimal("0")


async def reconstruct_currency_statements(
    db: AsyncSession,
    user_id: int,
    month_start: date,
    month_end: date,
) -> list[CurrencyStatement]:
    """
    One CurrencyStatement per wallet the user holds, covering all
    currencies in a single pass -- never combining balances across
    currencies (per approved scope).
    """
    wallets_result = await db.execute(select(Wallet).where(Wallet.user_id == user_id))
    wallets = wallets_result.scalars().all()

    tx_result = await db.execute(
        select(Transaction)
        .where(
            or_(Transaction.sender_id == user_id, Transaction.receiver_id == user_id),
            Transaction.created_at >= month_start,
        )
        .order_by(Transaction.created_at.asc())
    )
    all_relevant_transactions = tx_result.scalars().all()

    month_end_dt = datetime.combine(
    month_end,
    datetime.min.time(),
    )
    
    within_month = [
    tx for tx in all_relevant_transactions
    if tx.created_at.replace(tzinfo=None) < month_end_dt
    ]

    after_month_end = [
    tx for tx in all_relevant_transactions
    if tx.created_at.replace(tzinfo=None) >= month_end_dt
    ]

    counterparty_ids = {
        (tx.receiver_id if tx.sender_id == user_id else tx.sender_id)
        for tx in within_month
        if tx.sender_id != tx.receiver_id
    }
    users_by_id = {}
    if counterparty_ids:
        users_result = await db.execute(select(User).where(User.id.in_(counterparty_ids)))
        users_by_id = {u.id: u for u in users_result.scalars().all()}

    statements: list[CurrencyStatement] = []
    for wallet in wallets:
        currency_value = wallet.currency.value

        after_month_end_same_currency = [
            tx for tx in after_month_end if tx.currency.value == currency_value
        ]
        within_month_same_currency = [
            tx for tx in within_month if tx.currency.value == currency_value
        ]

        reconciled = True
        closing_balance = wallet.balance
        for tx in after_month_end_same_currency:
            effect = _signed_effect(tx, user_id)
            if effect is None:
                reconciled = False
                break
            closing_balance -= effect

        opening_balance = closing_balance
        if reconciled:
            for tx in within_month_same_currency:
                effect = _signed_effect(tx, user_id)
                if effect is None:
                    reconciled = False
                    break
                opening_balance -= effect

        rows = []
        for tx in within_month_same_currency:
            is_self = tx.sender_id == tx.receiver_id
            is_sender = tx.sender_id == user_id
            counterparty = (
                None if is_self else users_by_id.get(tx.receiver_id if is_sender else tx.sender_id)
            )
            rows.append(
                StatementTransactionRow(
                    id=tx.id,
                    created_at=tx.created_at,
                    category=tx.category,
                    type_label=_derive_type_label(tx, user_id),
                    amount=tx.amount,
                    status=tx.status.value,
                    counterparty_name=counterparty.full_name if counterparty else None,
                )
            )

        statements.append(
            CurrencyStatement(
                currency=currency_value,
                opening_balance=opening_balance if reconciled else None,
                closing_balance=closing_balance if reconciled else None,
                balance_reconciled=reconciled,
                transactions=rows,
            )
        )

    return statements


def generate_csv_bytes(month: str, currency_statements: list[CurrencyStatement]) -> bytes:
    """Pure Python (stdlib csv), per the ticket's AC -- no third-party CSV library."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([f"NeoBank Lebanon Monthly Statement - {month}"])
    writer.writerow([])

    for stmt in currency_statements:
        writer.writerow([f"Currency: {stmt.currency}"])
        if stmt.balance_reconciled:
            writer.writerow(["Opening Balance", str(stmt.opening_balance)])
            writer.writerow(["Closing Balance", str(stmt.closing_balance)])
        else:
            writer.writerow([
                "Opening Balance",
                "Not available: pre-ledger-fix transactions present, cannot be reconstructed accurately",
            ])
            writer.writerow([
                "Closing Balance",
                "Not available: pre-ledger-fix transactions present, cannot be reconstructed accurately",
            ])
        writer.writerow([])
        writer.writerow(["Date", "Category", "Type", "Amount", "Status", "Counterparty"])
        for row in stmt.transactions:
            writer.writerow([
                row.created_at.strftime("%Y-%m-%d"),
                row.category or "",
                row.type_label,
                str(row.amount),
                row.status,
                row.counterparty_name or "",
            ])
        writer.writerow([])

    return buffer.getvalue().encode("utf-8")


def generate_pdf_bytes(month: str, currency_statements: list[CurrencyStatement]) -> bytes:
    """reportlab, per the ticket's AC."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    story = [
        Paragraph(f"NeoBank Lebanon Monthly Statement - {month}", styles["Title"]),
        Spacer(1, 12),
    ]

    for stmt in currency_statements:
        story.append(Paragraph(f"Currency: {stmt.currency}", styles["Heading2"]))
        if stmt.balance_reconciled:
            story.append(Paragraph(f"Opening Balance: {stmt.opening_balance}", styles["Normal"]))
            story.append(Paragraph(f"Closing Balance: {stmt.closing_balance}", styles["Normal"]))
        else:
            story.append(
                Paragraph(
                    "Balances not available: this currency has pre-ledger-fix "
                    "transactions whose direction cannot be reliably reconstructed.",
                    styles["Normal"],
                )
            )
        story.append(Spacer(1, 8))

        table_data = [["Date", "Category", "Type", "Amount", "Status", "Counterparty"]]
        for row in stmt.transactions:
            table_data.append([
                row.created_at.strftime("%Y-%m-%d"),
                row.category or "",
                row.type_label,
                str(row.amount),
                row.status,
                row.counterparty_name or "",
            ])
        table = Table(table_data, repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                ]
            )
        )
        story.append(table)
        story.append(Spacer(1, 16))

    doc.build(story)
    return buffer.getvalue()
