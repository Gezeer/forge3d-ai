class Forge3DError(Exception):
    """Base exception for errors safe to map at the API boundary."""


class InvalidUploadError(Forge3DError):
    pass


class GenerationError(Forge3DError):
    def __init__(self, message: str, *, details: str = "") -> None:
        super().__init__(message)
        self.details = details


class GenerationTimeoutError(GenerationError):
    pass


class ServiceUnavailableError(Forge3DError):
    pass


class ArtifactNotFoundError(GenerationError):
    pass


class EngineRegistryError(Forge3DError):
    pass


class EngineAlreadyRegisteredError(EngineRegistryError):
    pass


class EngineNotFoundError(EngineRegistryError):
    pass


class EngineUnavailableError(EngineRegistryError):
    pass


class JobQueueError(Forge3DError):
    pass


class JobQueueFullError(JobQueueError):
    pass
