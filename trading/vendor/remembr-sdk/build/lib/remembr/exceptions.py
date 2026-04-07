class RemembrException(Exception):
    pass


class AuthenticationException(RemembrException):
    pass


class MemoryNotFoundException(RemembrException):
    pass
