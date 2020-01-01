"""Classes and Metaclasses used for config handling in my_weather."""
import os
import typing as ty
from abc import abstractmethod
from collections import Mapping

import tregex


class RepositoryConfigError(Exception):
    """Errors raised by the repo config."""
    pass


class RepositoryConfigBase(Mapping):
    """Unpackable (**) Container for repository configuration arguments."""

    def __new__(cls, *args, **kwargs):
        for unpack_prop in cls._unpack_props:
            if unpack_prop not in cls.__dict__:
                raise RepositoryConfigError(f'Class {cls.__name__} has a bad unpack property {unpack_prop}.')
        return super(RepositoryConfigBase, cls).__new__(cls)

    @property
    @abstractmethod
    def _unpack_props(self) -> ty.List[str]:
        """A list containing all properties we want to unpack with **."""

    def __iter__(self):
        for key in self._unpack_props:
            yield key

    def __len__(self):
        return len(self._unpack_props)

    def __getitem__(self, item):
        return getattr(self, item)


class EnvironmentVariablesConfigBase:
    """Superclass containing methods for verifying and getting environment variables."""

    @staticmethod
    def verify_env_var(var: str) -> str:
        """Simple check if variable exists in environment."""
        if var not in os.environ:
            raise EnvironmentError(f"Can't find environment variable {var}. "
                                   f"Closest match is {tregex.find_best(var, [var for var in os.environ])}.")
        return var

    @staticmethod
    def get_env_var(var: str) -> str:
        """Simple check if variable exists in environment."""
        return os.environ.get(var, None)
