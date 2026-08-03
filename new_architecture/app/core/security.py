# app/core/security.py

"""
Security Module
Handles authentication, authorization, password hashing, JWT tokens, and security utilities

Features:
- Password hashing (bcrypt)
- JWT token generation and validation
- Access token and refresh token management
- Password strength validation
- Security utilities (rate limiting, IP validation, etc.)
- Two-factor authentication support
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Union
import secrets
import hashlib
import re
from passlib.context import CryptContext
from jose import JWTError, jwt
from fastapi import HTTPException, status, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import pyotp
import qrcode
from io import BytesIO
import base64

from app.core.config import settings
from app.core.logging import logger

# ═══════════════════════════════════════════════════════════
# PASSWORD HASHING
# ═══════════════════════════════════════════════════════════

# Password context for hashing
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=12  # Number of rounds for bcrypt (higher = more secure but slower)
)


def get_password_hash(password: str) -> str:
    """
    Hash a password using bcrypt

    Args:
        password: Plain text password

    Returns:
        Hashed password

    Example:
        >>> hashed = get_password_hash("mypassword123")
        >>> print(hashed)
        $2b$12$...
    """
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a password against its hash

    Args:
        plain_password: Plain text password to verify
        hashed_password: Hashed password to compare against

    Returns:
        True if password matches

    Example:
        >>> hashed = get_password_hash("mypassword123")
        >>> verify_password("mypassword123", hashed)
        True
        >>> verify_password("wrongpassword", hashed)
        False
    """
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception as e:
        logger.error(f"Error verifying password: {e}")
        return False


def needs_rehash(hashed_password: str) -> bool:
    """
    Check if password hash needs to be updated
    (e.g., if algorithm or rounds changed)

    Args:
        hashed_password: Hashed password to check

    Returns:
        True if needs rehashing
    """
    return pwd_context.needs_update(hashed_password)


# ═══════════════════════════════════════════════════════════
# PASSWORD STRENGTH VALIDATION
# ═══════════════════════════════════════════════════════════

class PasswordStrength:
    """Password strength levels"""
    WEAK = "weak"
    FAIR = "fair"
    GOOD = "good"
    STRONG = "strong"
    VERY_STRONG = "very_strong"


def validate_password_strength(
        password: str,
        min_length: int = 8,
        require_uppercase: bool = True,
        require_lowercase: bool = True,
        require_digit: bool = True,
        require_special: bool = True
) -> tuple[bool, str, str]:
    """
    Validate password strength

    Args:
        password: Password to validate
        min_length: Minimum password length
        require_uppercase: Require at least one uppercase letter
        require_lowercase: Require at least one lowercase letter
        require_digit: Require at least one digit
        require_special: Require at least one special character

    Returns:
        Tuple of (is_valid, message, strength_level)

    Example:
        >>> valid, msg, strength = validate_password_strength("MyPass123!")
        >>> print(valid, strength)
        True strong
    """
    if len(password) < min_length:
        return False, f"Password must be at least {min_length} characters long", PasswordStrength.WEAK

    if len(password) > 128:
        return False, "Password is too long (max 128 characters)", PasswordStrength.WEAK

    # Check requirements
    has_uppercase = bool(re.search(r'[A-Z]', password))
    has_lowercase = bool(re.search(r'[a-z]', password))
    has_digit = bool(re.search(r'\d', password))
    has_special = bool(re.search(r'[!@#$%^&*(),.?":{}|<>_\-+=\[\]\\\/;`~]', password))

    if require_uppercase and not has_uppercase:
        return False, "Password must contain at least one uppercase letter", PasswordStrength.WEAK

    if require_lowercase and not has_lowercase:
        return False, "Password must contain at least one lowercase letter", PasswordStrength.WEAK

    if require_digit and not has_digit:
        return False, "Password must contain at least one digit", PasswordStrength.WEAK

    if require_special and not has_special:
        return False, "Password must contain at least one special character", PasswordStrength.WEAK

    # Calculate strength
    strength_score = 0

    # Length score
    if len(password) >= 8:
        strength_score += 1
    if len(password) >= 12:
        strength_score += 1
    if len(password) >= 16:
        strength_score += 1

    # Character variety score
    if has_uppercase:
        strength_score += 1
    if has_lowercase:
        strength_score += 1
    if has_digit:
        strength_score += 1
    if has_special:
        strength_score += 1

    # Determine strength level
    if strength_score <= 3:
        strength = PasswordStrength.WEAK
    elif strength_score <= 4:
        strength = PasswordStrength.FAIR
    elif strength_score <= 5:
        strength = PasswordStrength.GOOD
    elif strength_score <= 6:
        strength = PasswordStrength.STRONG
    else:
        strength = PasswordStrength.VERY_STRONG

    return True, "Password meets requirements", strength


def check_common_passwords(password: str) -> bool:
    """
    Check if password is in common passwords list

    Args:
        password: Password to check

    Returns:
        True if password is common (should be rejected)
    """
    # Common passwords list (top 100 most common)
    common_passwords = {
        "password", "123456", "123456789", "12345678", "12345", "1234567",
        "password1", "123123", "1234567890", "000000", "abc123", "qwerty",
        "iloveyou", "monkey", "dragon", "111111", "letmein", "admin",
        "welcome", "sunshine", "master", "password123", "123", "654321",
        # Add more as needed
    }

    return password.lower() in common_passwords


# ═══════════════════════════════════════════════════════════
# JWT TOKEN MANAGEMENT
# ═══════════════════════════════════════════════════════════

def create_access_token(
        data: Dict[str, Any],
        expires_delta: Optional[timedelta] = None
) -> str:
    """
    Create JWT access token

    Args:
        data: Data to encode in token (usually {"sub": user_id})
        expires_delta: Token expiration time (default from settings)

    Returns:
        Encoded JWT token

    Example:
        >>> token = create_access_token({"sub": "123", "email": "user@example.com"})
        >>> print(token)
        eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
    """
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "access"
    })

    encoded_jwt = jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM
    )

    return encoded_jwt


def create_refresh_token(
        data: Dict[str, Any],
        expires_delta: Optional[timedelta] = None
) -> str:
    """
    Create JWT refresh token

    Args:
        data: Data to encode in token
        expires_delta: Token expiration time (default from settings)

    Returns:
        Encoded JWT refresh token

    Example:
        >>> token = create_refresh_token({"sub": "123"})
    """
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "refresh"
    })

    encoded_jwt = jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM
    )

    return encoded_jwt


def decode_token(token: str) -> Dict[str, Any]:
    """
    Decode and validate JWT token

    Args:
        token: JWT token to decode

    Returns:
        Decoded token payload

    Raises:
        HTTPException: If token is invalid or expired

    Example:
        >>> payload = decode_token(token)
        >>> user_id = payload["sub"]
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM]
        )
        return payload
    except JWTError as e:
        logger.error(f"JWT decode error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


def verify_token(token: str, token_type: str = "access") -> Dict[str, Any]:
    """
    Verify JWT token and check type

    Args:
        token: JWT token to verify
        token_type: Expected token type ("access" or "refresh")

    Returns:
        Decoded token payload

    Raises:
        HTTPException: If token is invalid, expired, or wrong type
    """
    payload = decode_token(token)

    # Check token type
    if payload.get("type") != token_type:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token type. Expected {token_type}",
        )

    return payload


# ═══════════════════════════════════════════════════════════
# TOKEN UTILITIES
# ═══════════════════════════════════════════════════════════

def generate_password_reset_token(email: str) -> str:
    """
    Generate password reset token

    Args:
        email: User email

    Returns:
        Password reset token
    """
    delta = timedelta(hours=settings.PASSWORD_RESET_TOKEN_EXPIRE_HOURS)
    return create_access_token(
        data={"sub": email, "type": "password_reset"},
        expires_delta=delta
    )


def verify_password_reset_token(token: str) -> Optional[str]:
    """
    Verify password reset token

    Args:
        token: Password reset token

    Returns:
        Email if token is valid, None otherwise
    """
    try:
        payload = decode_token(token)
        if payload.get("type") != "password_reset":
            return None
        email: str = payload.get("sub")
        return email
    except HTTPException:
        return None


def generate_email_verification_token(email: str) -> str:
    """
    Generate email verification token

    Args:
        email: User email

    Returns:
        Email verification token
    """
    delta = timedelta(hours=settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS)
    return create_access_token(
        data={"sub": email, "type": "email_verification"},
        expires_delta=delta
    )


def verify_email_verification_token(token: str) -> Optional[str]:
    """
    Verify email verification token

    Args:
        token: Email verification token

    Returns:
        Email if token is valid, None otherwise
    """
    try:
        payload = decode_token(token)
        if payload.get("type") != "email_verification":
            return None
        email: str = payload.get("sub")
        return email
    except HTTPException:
        return None


# ═══════════════════════════════════════════════════════════
# API KEY MANAGEMENT
# ═══════════════════════════════════════════════════════════

def generate_api_key(prefix: str = "rag") -> str:
    """
    Generate secure API key

    Args:
        prefix: Prefix for API key (e.g., "rag", "sk")

    Returns:
        API key in format: prefix_randomstring

    Example:
        >>> api_key = generate_api_key("rag")
        >>> print(api_key)
        rag_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6
    """
    random_part = secrets.token_urlsafe(32)
    return f"{prefix}_{random_part}"


def hash_api_key(api_key: str) -> str:
    """
    Hash API key for storage

    Args:
        api_key: API key to hash

    Returns:
        SHA-256 hash of API key
    """
    return hashlib.sha256(api_key.encode()).hexdigest()


def verify_api_key(api_key: str, hashed_key: str) -> bool:
    """
    Verify API key against hash

    Args:
        api_key: Plain API key
        hashed_key: Hashed API key

    Returns:
        True if API key matches
    """
    return hash_api_key(api_key) == hashed_key


# ═══════════════════════════════════════════════════════════
# TWO-FACTOR AUTHENTICATION (2FA)
# ═══════════════════════════════════════════════════════════

def generate_totp_secret() -> str:
    """
    Generate TOTP secret for 2FA

    Returns:
        Base32 encoded secret

    Example:
        >>> secret = generate_totp_secret()
        >>> print(secret)
        JBSWY3DPEHPK3PXP
    """
    return pyotp.random_base32()


def generate_totp_uri(secret: str, email: str, issuer: str = None) -> str:
    """
    Generate TOTP provisioning URI for QR code

    Args:
        secret: TOTP secret
        email: User email
        issuer: App name (from settings if not provided)

    Returns:
        TOTP URI

    Example:
        >>> uri = generate_totp_uri(secret, "user@example.com")
        >>> print(uri)
        otpauth://totp/RAG%20System:user@example.com?secret=JBSWY3DPEHPK3PXP&issuer=RAG%20System
    """
    if issuer is None:
        issuer = settings.PROJECT_NAME

    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(name=email, issuer_name=issuer)


def generate_qr_code(data: str) -> str:
    """
    Generate QR code image as base64 string

    Args:
        data: Data to encode (usually TOTP URI)

    Returns:
        Base64 encoded PNG image

    Example:
        >>> uri = generate_totp_uri(secret, "user@example.com")
        >>> qr_code = generate_qr_code(uri)
        >>> # Use in HTML: <img src="data:image/png;base64,{qr_code}" />
    """
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(data)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")

    # Convert to base64
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    img_str = base64.b64encode(buffer.getvalue()).decode()

    return img_str


def verify_totp_code(secret: str, code: str) -> bool:
    """
    Verify TOTP code

    Args:
        secret: TOTP secret
        code: 6-digit code from authenticator app

    Returns:
        True if code is valid

    Example:
        >>> verify_totp_code(secret, "123456")
        True
    """
    totp = pyotp.TOTP(secret)
    return totp.verify(code, valid_window=1)  # Allow 1 window before/after for clock skew


def generate_backup_codes(count: int = 10) -> List[str]:
    """
    Generate backup codes for 2FA recovery

    Args:
        count: Number of backup codes to generate

    Returns:
        List of backup codes

    Example:
        >>> codes = generate_backup_codes(10)
        >>> print(codes)
        ['A1B2-C3D4-E5F6', 'G7H8-I9J0-K1L2', ...]
    """
    codes = []
    for _ in range(count):
        # Generate 12-character code in format: XXXX-XXXX-XXXX
        code = secrets.token_hex(6).upper()
        formatted = f"{code[0:4]}-{code[4:8]}-{code[8:12]}"
        codes.append(formatted)
    return codes


# ═══════════════════════════════════════════════════════════
# SECURITY UTILITIES
# ═══════════════════════════════════════════════════════════

def generate_secure_token(length: int = 32) -> str:
    """
    Generate cryptographically secure random token

    Args:
        length: Token length in bytes

    Returns:
        URL-safe token

    Example:
        >>> token = generate_secure_token()
        >>> print(token)
        a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6
    """
    return secrets.token_urlsafe(length)


def generate_numeric_code(length: int = 6) -> str:
    """
    Generate numeric code (for SMS, email verification, etc.)

    Args:
        length: Code length

    Returns:
        Numeric code

    Example:
        >>> code = generate_numeric_code(6)
        >>> print(code)
        123456
    """
    return ''.join([str(secrets.randbelow(10)) for _ in range(length)])


def constant_time_compare(a: str, b: str) -> bool:
    """
    Compare two strings in constant time (prevents timing attacks)

    Args:
        a: First string
        b: Second string

    Returns:
        True if strings are equal
    """
    return secrets.compare_digest(a.encode(), b.encode())


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename to prevent path traversal attacks

    Args:
        filename: Original filename

    Returns:
        Sanitized filename

    Example:
        >>> sanitize_filename("../../etc/passwd")
        'etcpasswd'
        >>> sanitize_filename("document.pdf")
        'document.pdf'
    """
    # Remove path components
    filename = filename.replace('\\', '/').split('/')[-1]

    # Remove dangerous characters
    filename = re.sub(r'[^\w\s\-\.]', '', filename)

    # Limit length
    if len(filename) > 255:
        name, ext = filename.rsplit('.', 1) if '.' in filename else (filename, '')
        filename = name[:250] + ('.' + ext if ext else '')

    return filename


def validate_email(email: str) -> bool:
    """
    Validate email format

    Args:
        email: Email to validate

    Returns:
        True if email is valid

    Example:
        >>> validate_email("user@example.com")
        True
        >>> validate_email("invalid-email")
        False
    """
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def validate_url(url: str) -> bool:
    """
    Validate URL format

    Args:
        url: URL to validate

    Returns:
        True if URL is valid
    """
    pattern = r'^https?://[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(/.*)?$'
    return bool(re.match(pattern, url))


def is_safe_redirect_url(url: str, allowed_hosts: List[str] = None) -> bool:
    """
    Check if redirect URL is safe (prevents open redirect vulnerabilities)

    Args:
        url: URL to check
        allowed_hosts: List of allowed hosts (from settings if not provided)

    Returns:
        True if URL is safe to redirect to
    """
    if not url:
        return False

    # Relative URLs are safe
    if url.startswith('/') and not url.startswith('//'):
        return True

    # Check against allowed hosts
    if allowed_hosts is None:
        allowed_hosts = settings.ALLOWED_REDIRECT_HOSTS if hasattr(settings, 'ALLOWED_REDIRECT_HOSTS') else []

    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        return parsed.netloc in allowed_hosts
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════
# RATE LIMITING
# ═══════════════════════════════════════════════════════════

class RateLimiter:
    """
    Simple in-memory rate limiter

    For production, use Redis-based rate limiting
    """

    def __init__(self):
        self._requests: Dict[str, List[datetime]] = {}

    def is_allowed(
            self,
            key: str,
            max_requests: int = 100,
            window_seconds: int = 60
    ) -> bool:
        """
        Check if request is allowed based on rate limit

        Args:
            key: Unique key (e.g., IP address, user ID)
            max_requests: Maximum requests allowed
            window_seconds: Time window in seconds

        Returns:
            True if request is allowed
        """
        now = datetime.utcnow()
        window_start = now - timedelta(seconds=window_seconds)

        # Get existing requests for this key
        if key not in self._requests:
            self._requests[key] = []

        # Remove old requests outside the window
        self._requests[key] = [
            req_time for req_time in self._requests[key]
            if req_time > window_start
        ]

        # Check if limit exceeded
        if len(self._requests[key]) >= max_requests:
            return False

        # Add current request
        self._requests[key].append(now)
        return True

    def clear(self, key: str):
        """Clear rate limit for key"""
        if key in self._requests:
            del self._requests[key]


# Global rate limiter instance
rate_limiter = RateLimiter()

# ═══════════════════════════════════════════════════════════
# HTTP BEARER AUTHENTICATION
# ═══════════════════════════════════════════════════════════

security = HTTPBearer()


async def get_current_user_from_token(
        credentials: HTTPAuthorizationCredentials = Depends(security)
) -> Dict[str, Any]:
    """
    Get current user from JWT token

    Args:
        credentials: HTTP Bearer credentials

    Returns:
        Token payload (contains user info)

    Raises:
        HTTPException: If token is invalid

    Usage:
        @app.get("/protected")
        async def protected_route(user = Depends(get_current_user_from_token)):
            return {"user_id": user["sub"]}
    """
    token = credentials.credentials
    payload = verify_token(token, token_type="access")
    return payload


# ═══════════════════════════════════════════════════════════
# IP ADDRESS UTILITIES
# ═══════════════════════════════════════════════════════════

def get_client_ip(request: Request) -> str:
    """
    Get client IP address from request

    Args:
        request: FastAPI request object

    Returns:
        Client IP address
    """
    # Check X-Forwarded-For header (if behind proxy)
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()

    # Check X-Real-IP header
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip

    # Fall back to direct connection
    return request.client.host if request.client else "unknown"


def is_ip_allowed(ip: str, allowed_ips: List[str] = None) -> bool:
    """
    Check if IP address is in allowed list

    Args:
        ip: IP address to check
        allowed_ips: List of allowed IPs (from settings if not provided)

    Returns:
        True if IP is allowed
    """
    if allowed_ips is None:
        allowed_ips = settings.ALLOWED_IPS if hasattr(settings, 'ALLOWED_IPS') else []

    if not allowed_ips:
        return True  # No restrictions

    return ip in allowed_ips


# ═══════════════════════════════════════════════════════════
# CORS UTILITIES
# ═══════════════════════════════════════════════════════════

def is_origin_allowed(origin: str, allowed_origins: List[str] = None) -> bool:
    """
    Check if origin is allowed for CORS

    Args:
        origin: Origin to check
        allowed_origins: List of allowed origins (from settings if not provided)

    Returns:
        True if origin is allowed
    """
    if allowed_origins is None:
        allowed_origins = settings.ALLOWED_ORIGINS if hasattr(settings, 'ALLOWED_ORIGINS') else ["*"]

    if "*" in allowed_origins:
        return True

    return origin in allowed_origins


# ═══════════════════════════════════════════════════════════
# ENCRYPTION UTILITIES (for sensitive data)
# ═══════════════════════════════════════════════════════════

from cryptography.fernet import Fernet


def generate_encryption_key() -> bytes:
    """
    Generate encryption key for Fernet

    Returns:
        Encryption key
    """
    return Fernet.generate_key()


def encrypt_data(data: str, key: bytes = None) -> str:
    """
    Encrypt data using Fernet

    Args:
        data: Data to encrypt
        key: Encryption key (uses settings key if not provided)

    Returns:
        Encrypted data (base64 encoded)
    """
    if key is None:
        key = settings.ENCRYPTION_KEY.encode() if hasattr(settings, 'ENCRYPTION_KEY') else generate_encryption_key()

    f = Fernet(key)
    encrypted = f.encrypt(data.encode())
    return encrypted.decode()


def decrypt_data(encrypted_data: str, key: bytes = None) -> str:
    """
    Decrypt data using Fernet

    Args:
        encrypted_data: Encrypted data (base64 encoded)
        key: Encryption key (uses settings key if not provided)

    Returns:
        Decrypted data
    """
    if key is None:
        key = settings.ENCRYPTION_KEY.encode() if hasattr(settings, 'ENCRYPTION_KEY') else generate_encryption_key()

    f = Fernet(key)
    decrypted = f.decrypt(encrypted_data.encode())
    return decrypted.decode()


# ═══════════════════════════════════════════════════════════
# SECURITY HEADERS
# ═══════════════════════════════════════════════════════════

def get_security_headers() -> Dict[str, str]:
    """
    Get recommended security headers

    Returns:
        Dictionary of security headers

    Usage:
        @app.middleware("http")
        async def add_security_headers(request, call_next):
            response = await call_next(request)
            for key, value in get_security_headers().items():
                response.headers[key] = value
            return response
    """
    return {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "X-XSS-Protection": "1; mode=block",
        "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
        "Content-Security-Policy": "default-src 'self'",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    }