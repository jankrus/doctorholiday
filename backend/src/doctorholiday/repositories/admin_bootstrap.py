"""The first-admin bootstrap (exam brief §4, BR-04; #15): the first successful login becomes ADMIN.

The state is the single row of `admin_bootstrap` (id = 1). It only ever goes from "not
bootstrapped" to "bootstrapped" in the app; a database reset re-arms it.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from doctorholiday.models import AdminBootstrap, Role, User


def _bootstrap_row(session: Session, *, lock: bool) -> AdminBootstrap:
    statement = (
        select(AdminBootstrap)
        .where(AdminBootstrap.id == 1)
        # Reload even if the row is already in the session, so the check never sees stale state.
        .execution_options(populate_existing=True)
    )
    if lock:
        statement = statement.with_for_update()
    return session.scalars(statement).one()


def promote_if_first_admin(session: Session, user: User) -> bool:
    """Make `user` the ADMIN if no account has been bootstrapped yet. True if it was promoted.

    Call it only after the password check succeeded, in the transaction that creates the session.
    The row is locked with `SELECT … FOR UPDATE` until that transaction ends: of concurrent first
    logins exactly one is promoted, the others wait for the lock, then see `bootstrapped` and
    keep their role. The unlocked read first is safe because the state never goes back, and it
    keeps every later login from queueing behind this one row.
    """
    if _bootstrap_row(session, lock=False).bootstrapped:
        return False
    bootstrap = _bootstrap_row(session, lock=True)
    if bootstrap.bootstrapped:
        return False

    user.role = Role.ADMIN
    # Only patients may decline the MFA offer (users_mfa_offer_patient_check).
    user.mfa_offer_declined_at = None
    bootstrap.bootstrapped = True
    bootstrap.admin_id = user.id
    bootstrap.bootstrapped_at = func.now()  # database clock
    session.flush()
    return True
