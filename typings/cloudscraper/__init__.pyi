from typing import Any, Type, Optional
from types import TracebackType

class ResponseMock:
    text: str
    content: bytes
    status_code: int

    def raise_for_status(self) -> None: ...

class ScraperMock:
    headers: dict[str, str]

    def get(self, url: str, **kwargs: Any) -> ResponseMock: ...
    def post(self, url: str, **kwargs: Any) -> ResponseMock: ...
    def __enter__(self) -> 'ScraperMock': ...
    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType]
    ) -> Optional[bool]: ...

def create_scraper(*args: Any, **kwargs: Any) -> ScraperMock: ...
