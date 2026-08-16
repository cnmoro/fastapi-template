from fastapi import Depends, HTTPException, status
from basemodels.authentication import TokenData
from enum import StrEnum

class Role(StrEnum):
    """Add a role by adding a member here, then grant it in ROLE_IMPLIES."""
    USER = "user"
    ADMIN = "admin"

# A role automatically carries every role it implies, so `require_roles(Role.USER)`
# also accepts an admin. Keep this flat - it is expanded transitively below.
ROLE_IMPLIES: dict[Role, set[Role]] = {
    Role.ADMIN: {Role.USER},
}

# Roles every new account starts with. Admins are granted out of band with
# create_admin.py, so registration can never hand out a privileged role.
DEFAULT_ROLES: list[str] = [Role.USER]

def expand_roles(roles: list[str] | set[str]) -> set[str]:
    """Expand roles through ROLE_IMPLIES, following chains."""
    resolved: set[str] = set()
    pending = list(roles)
    while pending:
        role = pending.pop()
        if role in resolved:
            continue
        resolved.add(role)
        pending.extend(ROLE_IMPLIES.get(role, ()))
    return resolved

def require_roles(*required: str, require_all: bool = False):
    """Dependency factory guarding an endpoint by role.

        @router.get("/admin", dependencies=[Depends(require_roles(Role.ADMIN))])

    By default any one of `required` grants access; pass require_all=True to
    demand every one of them.
    """
    # Imported here to avoid a circular import: routers.authentication imports rbac
    from routers.authentication import get_current_user_token_data

    # tradeoff: roles come from the token, so no database read per request and
    # a role change lands on next login. Depend on get_current_user instead if
    # revocation has to be immediate.
    needed = {str(r) for r in required}

    async def dependency(
        token_data: TokenData = Depends(get_current_user_token_data)
    ) -> TokenData:
        held = expand_roles(token_data.roles)
        ok = needed <= held if require_all else bool(needed & held)
        if not ok:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions"
            )
        return token_data

    return dependency
