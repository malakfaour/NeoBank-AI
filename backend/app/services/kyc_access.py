from fastapi import HTTPException, status

from app.models.user import KYCStatus, User


def kyc_restriction_detail(
    kyc_status: KYCStatus, *, submitted: bool = True
) -> dict[str, str]:
    if kyc_status == KYCStatus.pending and submitted:
        message = (
            "Your identity verification is under review. Transfers, Currency "
            "Exchange, and Top Ups will be available after approval."
        )
    elif kyc_status == KYCStatus.rejected:
        message = (
            "Your identity verification needs attention. Review and update "
            "the required information."
        )
    elif kyc_status == KYCStatus.flagged:
        message = (
            "Your identity verification requires manual review. Financial "
            "actions will be available after approval."
        )
    else:
        message = (
            "Complete your profile and identity verification to unlock "
            "Transfers, Currency Exchange, and Top Ups."
        )
    return {
        "error": "kyc_approval_required",
        "message": message,
        "kyc_status": kyc_status.value,
        "action": "complete_profile",
        "route": "/kyc",
    }


def assert_approved_kyc(user: User, *, submitted: bool = True) -> None:
    if user.kyc_status != KYCStatus.approved:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=kyc_restriction_detail(user.kyc_status, submitted=submitted),
        )
