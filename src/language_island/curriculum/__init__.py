"""Validated curriculum configuration for language islands."""

from language_island.curriculum.loader import CurriculumError, load_curriculum
from language_island.curriculum.models import CurriculumBundle

__all__ = ["CurriculumBundle", "CurriculumError", "load_curriculum"]
