def success_response(message: str, data=None, meta=None) -> dict:
    return {
        "success": True,
        "message": message,
        "data": data if data is not None else {},
        "meta": meta if meta is not None else {},
    }


def error_response(message: str, code: str, details=None) -> dict:
    return {
        "success": False,
        "message": message,
        "error": {
            "code": code,
            "details": details if details is not None else [],
        },
    }
