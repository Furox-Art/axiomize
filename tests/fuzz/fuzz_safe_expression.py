"""Atheris harness for the bounded mathematical-expression parser."""

import sys

import atheris

from axiomize.safe_expression import validate_expression


def TestOneInput(data: bytes) -> None:
    fdp = atheris.FuzzedDataProvider(data)
    expression = fdp.ConsumeUnicodeNoSurrogates(4096)
    try:
        validate_expression(expression, allowed_names={"x", "y"})
    except ValueError:
        return


atheris.Setup(sys.argv, TestOneInput)
atheris.Fuzz()
