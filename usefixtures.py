from __future__ import annotations

import argparse
import ast
import sys
from typing import Any
from typing import Sequence

from tokenize_rt import Offset
from tokenize_rt import reversed_enumerate
from tokenize_rt import src_to_tokens
from tokenize_rt import Token
from tokenize_rt import tokens_to_src


def _unused_args(function_body: ast.stmt) -> set[str]:
    names = set()

    class NameFinder(ast.NodeVisitor):
        def visit_Name(self, name: ast.Name) -> None:
            names.add(name.id)

    NameFinder().visit(function_body)
    return names


def _is_usefixtures_dec(dec: Any) -> bool:
    # TODO: fix type annotation
    return (
        isinstance(dec, ast.Call) and
        isinstance(dec.func, ast.Attribute) and
        dec.func.attr == 'usefixtures'
    )


def _fix_src_1st_pass(contents_text: str, fname: str) -> str:
    """create decorators"""
    unused_args: set[Offset] = set()
    decorator_to_be_created: set[Offset] = set()
    tree = ast.parse(contents_text, filename=fname)
    for node in ast.walk(tree):
        if (
                (
                    isinstance(node, ast.FunctionDef) or
                    isinstance(node, ast.AsyncFunctionDef)
                ) and
                'test' in node.name and
                _has_args(node)
        ):
            function_arg_names = {arg_name for arg_name in node.args.args}
            names_in_body: set[str] = set()
            for b in node.body:
                names_in_body = names_in_body | _unused_args(b)

            for f in function_arg_names:
                if f.arg not in names_in_body:
                    unused_args.add(Offset(f.lineno, f.col_offset))

            # other decorator
            if unused_args and node.decorator_list:
                if not any(
                    [_is_usefixtures_dec(dec) for dec in node.decorator_list],
                ):
                    decorator_to_be_created.add(
                        Offset(node.lineno, node.col_offset),
                    )
            # no decorators at all
            if unused_args and not node.decorator_list:
                decorator_to_be_created.add(
                    Offset(node.lineno, node.col_offset),
                )

    tokens = src_to_tokens(contents_text)
    for idx, token in reversed_enumerate(tokens):
        if token.offset in decorator_to_be_created:
            tokens.insert(idx, Token('NEWLINE', '\n'))
            tokens.insert(idx, Token('OP', ')'))
            tokens.insert(idx, Token('OP', '('))
            tokens.insert(idx, Token('NAME', 'usefixtures'))
            tokens.insert(idx, Token('OP', '.'))
            tokens.insert(idx, Token('NAME', 'mark'))
            tokens.insert(idx, Token('OP', '.'))
            tokens.insert(idx, Token('NAME', 'pytest'))
            tokens.insert(idx, Token('OP', '@'))

    return tokens_to_src(tokens)


def _fix_src_2nd_pass(contents_text: str, fname: str) -> str:
    """add fixtures to decorator"""
    dec_offsets: dict[Offset, list[str]] = {}
    tree = ast.parse(contents_text, filename=fname)
    for node in ast.walk(tree):
        if (
                (
                    isinstance(node, ast.FunctionDef) or
                    isinstance(node, ast.AsyncFunctionDef)
                ) and
                'test' in node.name and
                _has_args(node)
        ):
            unused = []
            function_arg_names = {arg_name for arg_name in node.args.args}
            names_in_body: set[str] = set()
            for b in node.body:
                names_in_body = names_in_body | _unused_args(b)

            for f in function_arg_names:
                if f.arg not in names_in_body:
                    unused.append(f.arg)

            # get corresponding decorator
            for dec in node.decorator_list:
                if (
                        isinstance(dec, ast.Call) and
                        isinstance(dec.func, ast.Attribute) and
                        dec.func.attr == 'usefixtures'
                ):
                    dec_offsets[Offset(dec.lineno, dec.col_offset)] = unused

    tokens = src_to_tokens(contents_text)
    for idx, token in reversed_enumerate(tokens):
        if token.offset in dec_offsets:
            # find closing parens
            i = idx
            while i < len(tokens):
                if tokens[i].src == '(':
                    opening_paren_idx = i
                if tokens[i].src == ')':
                    closing_paren_idx = i
                    break
                i += 1
            else:
                raise AssertionError('past end')

            if closing_paren_idx == opening_paren_idx + 1:
                dec_has_fixture = False
            else:
                dec_has_fixture = True

            fixtures = sorted(dec_offsets[token.offset], reverse=True)
            for fixture_idx, fixture in enumerate(fixtures):
                if fixture_idx > 0:
                    tokens.insert(
                        closing_paren_idx,
                        Token('UNIMPORTANT_WS', ' '),
                    )
                    tokens.insert(closing_paren_idx, Token('OP', ','))
                tokens.insert(closing_paren_idx, Token(name='STRING', src="'"))
                tokens.insert(closing_paren_idx, Token('NAME', fixture))
                tokens.insert(closing_paren_idx, Token(name='STRING', src="'"))
                if dec_has_fixture:
                    tokens.insert(
                        closing_paren_idx, Token('UNIMPORTANT_WS', ' '),
                    )
                    tokens.insert(closing_paren_idx, Token('OP', ','))

    return tokens_to_src(tokens)


def _fix_src_3rd_pass(contents_text: str, fname: str) -> str:
    """remove fixtures as arguments"""
    unused_args: set[Offset] = set()
    tree = ast.parse(contents_text, filename=fname)
    for node in ast.walk(tree):
        if (
                (
                    isinstance(node, ast.FunctionDef) or
                    isinstance(node, ast.AsyncFunctionDef)
                ) and
                'test' in node.name and
                _has_args(node)
        ):
            function_arg_names = {i for i in node.args.args}
            names_in_body: set[str] = set()
            for i in node.body:
                names_in_body = names_in_body | _unused_args(i)

            for f in function_arg_names:
                if f.arg not in names_in_body:
                    unused_args.add(Offset(f.lineno, f.col_offset))

    tokens = src_to_tokens(contents_text)
    for idx, token in reversed_enumerate(tokens):
        if token.offset in unused_args:
            del tokens[idx]
            if tokens[idx-1].name == 'UNIMPORTANT_WS':
                del tokens[idx-1]
            if tokens[idx-2].src == ',':
                del tokens[idx-2]
                # TODO: trailing comma
    return tokens_to_src(tokens)


def _has_args(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    if any((
        node.args.posonlyargs,
        node.args.args,
        node.args.kwonlyargs,
    )):
        return True
    else:
        return False


def _fix_file(filename: str) -> int:
    if filename == '-':
        contents = sys.stdin.buffer.read().decode(encoding='UTF-8')
    else:
        with open(filename, 'rb') as f:
            contents = f.read().decode(encoding='UTF-8')

    contents_orig = contents_text = contents
    contents_1st_pass = _fix_src_1st_pass(contents_text, fname=filename)
    contents_2nd_pass = _fix_src_2nd_pass(contents_1st_pass, fname=filename)
    contents_text = _fix_src_3rd_pass(contents_2nd_pass, fname=filename)

    if filename == '-':
        print(contents_text, end='')
    elif contents_text != contents_orig:
        print(f'Rewriting {filename}', file=sys.stderr)
        with open(filename, 'wb') as f:
            f.write(contents_text.encode())

    return contents_text != contents_orig


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('filenames', nargs='*')
    args = parser.parse_args(argv)
    ret = 0
    for filename in args.filenames:
        ret |= _fix_file(filename)

    return ret


if __name__ == '__main__':
    raise SystemExit(main())
