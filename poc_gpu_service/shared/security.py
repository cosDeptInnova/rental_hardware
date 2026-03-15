from fastapi import Header, HTTPException, status


def validate_api_key(api_key: str, allowed_keys: list[str]) -> str:
    if api_key not in allowed_keys:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
    return api_key


def validate_internal_token(token: str, expected: str) -> str:
    if token != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid internal token")
    return token


async def api_key_header(x_api_key: str = Header(default="")) -> str:
    return x_api_key


async def internal_token_header(x_internal_token: str = Header(default="")) -> str:
    return x_internal_token
