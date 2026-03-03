"""Source service domain errors."""


class SourceError(Exception):
    """Base exception for Source service errors."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


class DuplicateNameError(SourceError):
    """Raised when attempting to create a duplicate name on same platform."""

    def __init__(self, name: str, platform: str):
        super().__init__(
            code="DUPLICATE_NAME",
            message="同一平台下公司名称已存在 (Company name already exists on this platform)",
        )
        self.name = name
        self.platform = platform


class DuplicateIdentifierError(SourceError):
    """Raised when platform+identifier already exists."""

    def __init__(self, platform: str, identifier: str):
        super().__init__(
            code="DUPLICATE_IDENTIFIER",
            message="该平台下标识符已存在 (Identifier already exists on this platform)",
        )
        self.platform = platform
        self.identifier = identifier


class SourceNotFoundError(SourceError):
    """Raised when a source is not found."""

    def __init__(self):
        super().__init__(code="NOT_FOUND", message="数据源不存在")


class HasReferencesError(SourceError):
    """Raised when attempting to delete a source with associated records."""

    def __init__(self):
        super().__init__(
            code="HAS_REFERENCES", message="该数据源有关联的抓取记录，无法删除。建议禁用而非删除"
        )


class HasMutationBlockError(SourceError):
    """Raised when platform or identifier update is blocked by existing job/sync-run references."""

    def __init__(self):
        super().__init__(
            code="HAS_MUTATION_BLOCK",
            message="该数据源有关联的职位或抓取记录，无法修改平台或标识符",
        )
