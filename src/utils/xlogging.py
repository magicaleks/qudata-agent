import sys
from functools import lru_cache
from logging import FileHandler, Formatter, StreamHandler, getLogger
from typing import Optional


class XLogger:

    def __init__(self, service_name: str) -> None:
        self._service_name = service_name
        self._logger = getLogger(service_name)
        self._setting()

    def _setting(self) -> None:
        self._logger.setLevel("DEBUG")
        self._logger.handlers.clear()

        filename = "logs.txt"  # TODO: make prod logs output
        self._logger.addHandler(FileHandler(filename=filename, encoding="utf-8"))
        self._logger.addHandler(StreamHandler(stream=sys.stdout))

        for handler in self._logger.handlers:
            handler.setFormatter(
                Formatter(fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
            )

    def info(self, message: str) -> None:
        self._logger.info(message)

    def warning(self, message: str) -> None:
        self._logger.warning(message)

    def error(
        self, message: str, exc: Optional[Exception] = None, exc_info: bool = True
    ) -> None:
        if exc:
            self._logger.error(message, exc_info=exc)
        else:
            self._logger.error(message, exc_info=exc_info)


@lru_cache
def get_logger(service_name: str) -> XLogger:
    return XLogger(service_name)
