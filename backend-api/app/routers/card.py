from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import require_mobile_user
from ..models import CampusCardAccount, SysUser
from ..responses import success
from ..utils import fmt_dt

router = APIRouter(prefix="/card", tags=["校园卡账户"])


def mask_card_no(card_no: str) -> str:
    return card_no[:4] + "****" + card_no[-4:] if len(card_no) >= 8 else card_no


@router.get("/balance")
def my_balance(user: SysUser = Depends(require_mobile_user), db: Session = Depends(get_db)):
    """只按当前登录用户查询本人账户，不接受学号/卡号参数，避免越权查询他人余额。"""
    account = (db.query(CampusCardAccount)
               .filter(CampusCardAccount.user_id == user.id).first())
    if account is None:
        return success({"account": None, "message": "未找到本人的校园卡账户，请联系学校卡务中心"})
    return success({"account": {
        "card_no": mask_card_no(account.card_no),
        "balance": str(account.balance),
        "status": account.status,
        "last_transaction_at": fmt_dt(account.last_transaction_at),
    }})
