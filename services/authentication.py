from datetime import datetime, timedelta, timezone
from argon2.exceptions import InvalidHashError, VerificationError
from pymongo.errors import DuplicateKeyError
from argon2 import PasswordHasher
from bson.errors import InvalidId
from bson import ObjectId
import secrets, anyio, jwt, os

from services.db import get_database
from services.rbac import DEFAULT_ROLES, Role
from basemodels.authentication import PasswordUpdate, TokenData, \
    TokenResponse, UserCreate, UserResponse

JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY")
JWT_ALGORITHM = "HS256"
# Idle window: a token stays valid this long after the last authenticated request
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", 120))
# Hard cap on a session however actively it is used, counted from first login
JWT_MAX_SESSION_MINUTES = int(os.environ.get("JWT_MAX_SESSION_MINUTES", 1440))
LOGIN_MAX_ATTEMPTS = int(os.environ.get("LOGIN_MAX_ATTEMPTS", 5))
LOGIN_LOCKOUT_MINUTES = int(os.environ.get("LOGIN_LOCKOUT_MINUTES", 15))

if not JWT_SECRET_KEY or len(JWT_SECRET_KEY) < 32:
    raise RuntimeError("JWT_SECRET_KEY must be set and at least 32 characters")

# OWASP-recommended Argon2id parameters, ~5ms per hash
_hasher = PasswordHasher(memory_cost=19456, time_cost=2, parallelism=4)
# Compared against when no account matches, so a missing account costs the
# same time as a wrong password and cannot be probed
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(16))

class AuthenticationError(Exception):
    pass

class RateLimitedError(AuthenticationError):
    pass

def _object_id(value: str) -> ObjectId:
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        raise AuthenticationError("Invalid user id")

def _verify_sync(password: str, hashed: str) -> bool:
    try:
        return _hasher.verify(hashed, password)
    except (VerificationError, InvalidHashError):
        return False

# Hashing is CPU-bound, so it runs off the event loop
async def hash_password(password: str) -> str:
    return await anyio.to_thread.run_sync(_hasher.hash, password)

async def verify_password(password: str, hashed: str) -> bool:
    return await anyio.to_thread.run_sync(_verify_sync, password, hashed)

def _issue_token(email: str, user_id: str, roles: list[str], version: int,
                 session_start: datetime, now: datetime) -> tuple[str, datetime]:
    # A refreshed token never outlives the absolute session cap
    expires = min(now + timedelta(minutes=JWT_ACCESS_TOKEN_EXPIRE_MINUTES),
                  session_start + timedelta(minutes=JWT_MAX_SESSION_MINUTES))
    token = jwt.encode(
        {
            "sub": email,
            "user_id": user_id,
            "roles": roles,
            "ver": version,
            # Constant across refreshes. Sent as an epoch int because PyJWT
            # only converts datetimes for the registered exp/iat/nbf claims.
            "sst": int(session_start.timestamp()),
            "iat": now,
            "exp": expires,
            "jti": secrets.token_urlsafe(16)
        },
        JWT_SECRET_KEY, algorithm=JWT_ALGORITHM
    )
    return token, expires

def refresh_token(token_data: TokenData) -> str | None:
    """Slide the expiry forward while a session is in use, or None if there is
    nothing to extend. Called on every authenticated request."""
    now = datetime.now(timezone.utc)
    session_end = token_data.session_start + timedelta(minutes=JWT_MAX_SESSION_MINUTES)

    if now >= session_end:
        return None

    # Only remint past the halfway mark, so an active client is not handed a
    # new token on every single request
    if token_data.expires_at - now > timedelta(minutes=JWT_ACCESS_TOKEN_EXPIRE_MINUTES / 2):
        return None

    token, expires = _issue_token(
        token_data.email, token_data.user_id, token_data.roles,
        token_data.token_version, token_data.session_start, now
    )
    # Near the cap the new expiry stops moving; no point reissuing
    return token if expires > token_data.expires_at else None

def _user_response(user: dict) -> UserResponse:
    return UserResponse(
        id=str(user["_id"]),
        email=user["email"],
        full_name=user.get("full_name"),
        roles=user.get("roles", []),
        created_at=user["created_at"]
    )

async def verify_token(token: str) -> TokenData:
    try:
        payload = jwt.decode(
            token, JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM],   # pinned, so "alg": "none" is rejected
            options={"require": ["exp", "iat", "sub", "user_id"]}
        )
    except jwt.PyJWTError:
        raise AuthenticationError("Invalid token")

    return TokenData(
        email=payload["sub"],
        user_id=payload["user_id"],
        roles=payload.get("roles", []),
        token_version=payload.get("ver", 0),
        session_start=datetime.fromtimestamp(payload.get("sst", payload["iat"]), timezone.utc),
        expires_at=datetime.fromtimestamp(payload["exp"], timezone.utc)
    )

async def create_user(user_data: UserCreate) -> UserResponse:
    """Create a new user. Roles are fixed here; admin is granted out of band."""
    now = datetime.now(timezone.utc)
    user = {
        "email": user_data.email.lower(),
        "password": await hash_password(user_data.password),
        "full_name": user_data.full_name,
        "roles": list(DEFAULT_ROLES),
        # Bumped on credential or role changes, invalidating older tokens
        "token_version": 0,
        "created_at": now,
        "updated_at": now
    }

    try:
        user["_id"] = (await get_database()['USERS'].insert_one(user)).inserted_id
    except DuplicateKeyError:
        raise AuthenticationError("User with this email already exists")

    return _user_response(user)

async def authenticate_user(email: str, password: str) -> dict | None:
    user = await get_database()['USERS'].find_one({"email": email.lower()})

    if not user:
        await verify_password(password, _DUMMY_HASH)
        return None

    return user if await verify_password(password, user["password"]) else None

async def login(username: str, password: str, client_ip: str = "unknown") -> TokenResponse:
    """Authenticate and issue an access token, locking out repeated failures."""
    email = username.lower()
    attempts = get_database()['LOGIN_ATTEMPTS']
    key = f"{email}|{client_ip}"

    record = await attempts.find_one({"_id": key})
    if record and record["count"] >= LOGIN_MAX_ATTEMPTS:
        raise RateLimitedError(
            f"Too many failed login attempts. Try again in {LOGIN_LOCKOUT_MINUTES} minutes."
        )

    user = await authenticate_user(email, password)
    now = datetime.now(timezone.utc)

    if not user:
        # A TTL index on expires_at clears the counter once the window passes
        await attempts.update_one(
            {"_id": key},
            {"$inc": {"count": 1},
             "$set": {"expires_at": now + timedelta(minutes=LOGIN_LOCKOUT_MINUTES)}},
            upsert=True
        )
        raise AuthenticationError("Invalid email or password")

    await attempts.delete_one({"_id": key})

    token, expires = _issue_token(
        user["email"], str(user["_id"]), user.get("roles", []),
        user.get("token_version", 0), session_start=now, now=now
    )

    return TokenResponse(
        access_token=token,
        expires_in=int((expires - now).total_seconds())
    )

async def get_current_user(token_data: TokenData) -> UserResponse:
    """Load the user behind a token, rejecting tokens older than the last
    password or role change."""
    user = await get_database()['USERS'].find_one({"_id": _object_id(token_data.user_id)})

    if not user:
        raise AuthenticationError("User not found")

    if token_data.token_version != user.get("token_version", 0):
        raise AuthenticationError("Token has been revoked")

    return _user_response(user)

async def update_password(user_id: str, password_data: PasswordUpdate) -> bool:
    """Change a password, signing out every session holding an older token."""
    users = get_database()['USERS']
    user = await users.find_one({"_id": _object_id(user_id)})

    if not user:
        raise AuthenticationError("User not found")

    if not await verify_password(password_data.current_password, user["password"]):
        raise AuthenticationError("Current password is incorrect")

    if password_data.new_password == password_data.current_password:
        raise AuthenticationError("New password must differ from the current one")

    result = await users.update_one(
        {"_id": user["_id"]},
        {"$set": {"password": await hash_password(password_data.new_password),
                  "updated_at": datetime.now(timezone.utc)},
         "$inc": {"token_version": 1}}
    )

    return result.modified_count > 0

async def set_user_roles(user_id: str, roles: list[str]) -> UserResponse:
    """Replace a user's roles, invalidating tokens carrying the old set."""
    unknown = set(roles) - {str(r) for r in Role}
    if unknown:
        raise AuthenticationError(f"Unknown role(s): {', '.join(sorted(unknown))}")

    user = await get_database()['USERS'].find_one_and_update(
        {"_id": _object_id(user_id)},
        {"$set": {"roles": roles, "updated_at": datetime.now(timezone.utc)},
         "$inc": {"token_version": 1}},
        return_document=True
    )

    if not user:
        raise AuthenticationError("User not found")

    return _user_response(user)
