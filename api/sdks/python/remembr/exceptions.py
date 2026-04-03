class RemembrError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class AuthError(RemembrError):
    pass


class NotFoundError(RemembrError):
    pass


class RateLimitError(RemembrError):
    pass


class ValidationError(RemembrError):
    pass
