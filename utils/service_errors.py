"""Stable, content-free dependency errors for translation at API boundaries."""


class ServiceError(Exception):
    error_code = "DEPENDENCY_ERROR"
    status_code = 503

    def __init__(self, public_message: str):
        super().__init__(public_message)
        self.public_message = public_message


class InvalidRequestError(ServiceError, ValueError):
    error_code = "INVALID_REQUEST"
    status_code = 400


class ServiceTimeoutError(ServiceError):
    error_code = "DEPENDENCY_TIMEOUT"
    status_code = 504


class ServiceUnavailableError(ServiceError):
    error_code = "DEPENDENCY_UNAVAILABLE"
    status_code = 503


class ServiceProtocolError(ServiceError, ValueError):
    error_code = "DEPENDENCY_INVALID_RESPONSE"
    status_code = 502


class ServiceOverloadedError(ServiceError):
    error_code = "SERVICE_BUSY"
    status_code = 503
