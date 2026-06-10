class DomainError(Exception):
    """База для доменных ошибок."""


class TaskNotFound(DomainError):
    pass


class InvalidStatusTransition(DomainError):
    pass
