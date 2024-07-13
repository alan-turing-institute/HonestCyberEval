import copy
import difflib
import re
from dataclasses import KW_ONLY, dataclass, field
from enum import IntEnum, auto
from typing import Optional, TypeAlias, Union

import clang.cindex
from clang.cindex import Cursor, CursorKind
from git import Commit
from strenum import StrEnum

from logger import logger

# Set the path to the libclang shared library
clang.cindex.Config.set_library_file("/usr/lib/x86_64-linux-gnu/libclang-14.so")

# constants used throughout this
FILE_CODE = "file_code"


class AbstractReplacementTerms(StrEnum):
    STRING_LITERAL = auto()
    LOCAL_VARIABLE = auto()
    IMPORTED_VARIABLE = auto()
    LOCAL_FUNCTION = auto()
    IMPORTED_FUNCTION = auto()
    LOCAL_STRUCT = auto()
    IMPORTED_STRUCT = auto()
    LOCAL_STRUCT_FIELD = auto()
    IMPORTED_STRUCT_FIELD = auto()
    PARAM = auto()
    NUMBER = auto()
    LOCAL_ENUM_CONST = auto()
    IMPORTED_ENUM_CONST = auto()


class ChangeType(IntEnum):
    FUNCTIONAL_CHANGE = auto()
    FILE_REMOVED = 1
    FILE_ADDED = 2


class VarType(StrEnum):
    FUNCTION_LOCAL = auto()
    OTHER = auto()


class VarSourceType(StrEnum):
    FILE_LOCAL = auto()
    IMPORTED = auto()


class DeclType(StrEnum):
    FUNCTION_TYPE = auto()
    VAR_TYPE = auto()
    STRUCT_TYPE = auto()
    STRING_TYPE = auto()
    PARAM_TYPE = auto()
    ENUM_TYPE = auto()
    ENUM_CONST_TYPE = auto()
    FIELD_TYPE = auto()
    DECL_REF_TYPE = auto()


TypesDictType: TypeAlias = dict[DeclType, CursorKind]
VarsDictType: TypeAlias = dict[VarSourceType, dict[str, Cursor]]
NodesDictType: TypeAlias = dict[DeclType, VarsDictType]
FunctionDictType: TypeAlias = dict[str, list[str]]

TYPES: TypesDictType = {
    DeclType.VAR_TYPE: CursorKind.VAR_DECL,  # type: ignore
    DeclType.PARAM_TYPE: CursorKind.PARM_DECL,  # type: ignore
    DeclType.FUNCTION_TYPE: CursorKind.FUNCTION_DECL,  # type: ignore
    DeclType.ENUM_CONST_TYPE: CursorKind.ENUM_CONSTANT_DECL,  # type: ignore
    DeclType.PARAM_TYPE: CursorKind.PARM_DECL,  # type: ignore
    DeclType.STRUCT_TYPE: CursorKind.STRUCT_DECL,  # type: ignore
    DeclType.DECL_REF_TYPE: CursorKind.DECL_REF_EXPR,  # type: ignore
}

TYPES_FOR_EXTERNAL_DEFINED_VARS: TypesDictType = {
    DeclType.VAR_TYPE: CursorKind.VAR_DECL,  # type: ignore
    DeclType.PARAM_TYPE: CursorKind.PARM_DECL,  # type: ignore
    DeclType.DECL_REF_TYPE: CursorKind.DECL_REF_EXPR,  # type: ignore
}

TYPES_FOR_ABSTRACT: TypesDictType = {
    DeclType.VAR_TYPE: CursorKind.VAR_DECL,  # type: ignore
    DeclType.FUNCTION_TYPE: CursorKind.FUNCTION_DECL,  # type: ignore
    DeclType.STRUCT_TYPE: CursorKind.STRUCT_DECL,  # type: ignore
    DeclType.STRING_TYPE: CursorKind.STRING_LITERAL,  # type: ignore
    DeclType.PARAM_TYPE: CursorKind.PARM_DECL,  # type: ignore
    # DeclType.ENUM_TYPE: CursorKind.ENUM_DECL, # type: ignore
    DeclType.ENUM_CONST_TYPE: CursorKind.ENUM_CONSTANT_DECL,  # type: ignore
    DeclType.FIELD_TYPE: CursorKind.FIELD_DECL,  # type: ignore
}


@dataclass
class BaseDiff:
    name: str
    before_lines: list[str] = field(default_factory=list)
    after_lines: list[str] = field(default_factory=list)
    diff_lines: list[str] = field(default_factory=list)

    def print(self, info: str, lines: Union[list[str], None]) -> str:

        if lines is None:
            logger.debug(f"Cannot print the code from {info} this commit, as it does not exist.")
            return f"No code from {info.lower()} this commit."

        string_to_print = f"{type(self)} - {self.name} - {info}:\n"
        string_to_print += "\n".join(lines)

        return string_to_print

    def print_before(self):
        return self.print("Before", self.before_lines)

    def print_after(self):
        return self.print("After", self.after_lines)

    def after_str(self):
        return "\n".join(self.after_lines)

    def before_str(self):
        return "\n".join(self.before_lines)

    def print_diff(self):
        return self.print("Diff", self.diff_lines)

    def diff_str(self):
        return "\n".join(self.diff_lines)

    def join_lines(self, lines, indent=""):
        return ("\n" + indent).join(lines)

    def ast_string(self, ast: Union[Cursor, None], string_to_print: str = "", depth: int = 0) -> str:

        if ast is None:
            if string_to_print:
                return string_to_print
            else:
                return "No AST to print."

        indent = "  " * depth

        if ast.spelling:
            string_to_print += f"{indent}Kind: {ast.kind}, Spelling: {ast.spelling}, Location: {ast.location}\n"
        else:
            string_to_print += f"{indent}Kind: {ast.kind}, Location: {ast.location}\n"

        for child in ast.get_children():
            string_to_print = self.ast_string(child, string_to_print, depth + 1)

        return string_to_print


@dataclass
class FunctionDiff(BaseDiff):
    _: KW_ONLY
    after_external_variable_decls: dict[str, str] = field(default_factory=dict)
    before_external_variable_decls: dict[str, str] = field(default_factory=dict)

    # _external_variable_decls: dict[str, str]

    def __str__(self):
        return self.build_full_string(indent="")

    def build_full_string(self, indent):
        string_to_print = f"{indent}Function {self.name}:\n"
        indent += "\t"
        string_to_print += f"{indent}Diff:\n"
        string_to_print += f"{indent}{self.join_lines(self.diff_lines, indent)}\n\n"
        if self.before_lines:
            string_to_print += f"{indent}Before this commit:\n"
            string_to_print += f"{indent}{self.join_lines(self.before_lines, indent)}\n\n"
            if self.before_external_variable_decls:
                string_to_print += f"{indent}Externally declared variables:\n"
                string_to_print += (
                    f"{indent}{self.join_lines(list(self.before_external_variable_decls.values()), indent)}\n\n"
                )

        else:
            string_to_print += f"{indent}No code before this commit.\n"

        if self.after_lines:
            string_to_print += f"{indent}After this commit:\n"
            string_to_print += f"{indent}{self.join_lines(self.after_lines, indent)}\n\n"
            if self.after_external_variable_decls:
                string_to_print += f"{indent}Externally declared variables:\n"
                string_to_print += (
                    f"{indent}{self.join_lines(list(self.after_external_variable_decls.values()), indent)}\n\n"
                )

        else:
            string_to_print += f"{indent}No code after this commit.\n"

        return string_to_print

    def append_external_variable_decls_to_code_lines(self):

        key_order = []
        change_occurred = False

        if self.before_external_variable_decls:
            change_occurred = True
            # get the variable declarations from the dictionary
            key_order = list(self.before_external_variable_decls.keys())
            new_before_lines = list(self.before_external_variable_decls.values())

            # stack the variable declarations above the code lines
            new_before_lines = new_before_lines + self.before_lines
            self.before_lines = new_before_lines

        if self.after_external_variable_decls:
            change_occurred = True
            new_after_lines = []
            # keep the order of declarations the same as the before_lines if applicable
            if key_order:
                for key in key_order:
                    if key in self.after_external_variable_decls:
                        new_after_lines.append(self.after_external_variable_decls[key])

            # add on any potentially other variables not in the before
            for key in self.after_external_variable_decls:
                if key not in key_order:  # prevent duplicates
                    new_after_lines.append(self.after_external_variable_decls[key])

            # stack them with the code lines
            new_after_lines = new_after_lines + self.after_lines
            self.after_lines = new_after_lines

        if change_occurred:
            # update the diff
            self.diff = make_diff(self.before_lines, self.after_lines)

        return


@dataclass()
class FileDiff(BaseDiff):
    _: KW_ONLY
    change_type: ChangeType
    before_commit: Commit
    after_commit: Commit
    before_ast: Optional[Cursor]
    after_ast: Optional[Cursor]
    diff_functions: dict[str, FunctionDiff]
    og_diff: list[str]

    def __str__(self):
        string_to_print = self.build_full_string("")

        for function_diff in self.diff_functions:
            string_to_print += self.diff_functions[function_diff].build_full_string("\t\t")

        return string_to_print

    def build_full_string(self, indent):
        string_to_print = f"{indent}File {self.name}:\n"
        indent += "\t"
        string_to_print += f"{indent}Change Type: {self.change_type}\n"
        string_to_print += f"{indent}Diff:\n"
        string_to_print += f"{indent}{self.join_lines(self.diff_lines, indent)}\n\n"
        string_to_print += f"{indent}Before this commit:\n"
        indent_plus = indent + "\t"

        if self.before_lines:
            string_to_print += f"{indent_plus}Code:\n"
            string_to_print += f"{indent_plus}{self.join_lines(self.before_lines, indent_plus)}\n\n"
            # string_to_print += f"{indent_plus}AST:\n"
            # string_to_print += f"{indent_plus}{self.ast_string(self.before_ast)}\n\n"
        else:
            string_to_print += f"{indent_plus}No code before this commit.\n"

        string_to_print += f"{indent}After this commit:\n"
        if self.after_lines:
            string_to_print += f"{indent_plus}Code:\n"
            string_to_print += f"{indent_plus}{self.join_lines(self.after_lines, indent_plus)}\n\n"
            # string_to_print += f"{indent_plus}AST:\n"
            # string_to_print += f"{indent_plus}{self.ast_string(self.after_ast)}\n\n"
        else:
            string_to_print += f"{indent_plus}No code after this commit.\n"

        return string_to_print


# TODO: set up the cleaned commits as a class so that it can have the C/Java swap stuff more easily maybe?
# TODO: set up a refactoring check using the asts maybe? if code is 'x = a + b; y = x + z;' -> 'y = a + b + z;' kind of check?
# TODO: set up using Java


def build_regex_pattern_from_list(pattern_list, word_boundary=True):
    if word_boundary:
        regex_pattern = r"(\s|\W|^)("
    else:
        regex_pattern = r"("

    if pattern_list:
        for i, pattern_item in enumerate(pattern_list):
            if pattern_item != "":
                pattern_name = re.escape(pattern_item)
                regex_pattern += pattern_name
                if i < (len(pattern_list) - 1):
                    regex_pattern += "|"
                else:
                    if word_boundary:
                        regex_pattern += r")(?=\s|\W|$)"
                    else:
                        regex_pattern += r")"
    else:
        regex_pattern = None

    return regex_pattern


def search_line_and_replace(line, pattern, replace_term):
    for match in re.findall(pattern, line):

        if not isinstance(match, str):
            match = r"\b" + re.escape(match[1]) + r"\b"  # match will be the three capture groups?
        else:
            match = re.escape(match)

        line = re.sub(match, replace_term, line)

    return line


def abstract_code(code_snippet, ast, filename):
    nodes = search_ast_for_node_types(ast, TYPES_FOR_ABSTRACT, filename)

    patterns = {}
    # FIELD_DECL, ENUM_DECL, ENUM_CONSTANT_DECL
    patterns[AbstractReplacementTerms.STRING_LITERAL] = build_regex_pattern_from_list(
        (
            list(nodes[DeclType.STRING_TYPE][VarSourceType.FILE_LOCAL].keys())
            + list(nodes[DeclType.STRING_TYPE][VarSourceType.IMPORTED].keys())
        ),
        word_boundary=False,
    )
    patterns[AbstractReplacementTerms.LOCAL_VARIABLE] = build_regex_pattern_from_list(
        nodes[DeclType.VAR_TYPE][VarSourceType.FILE_LOCAL]
    )
    patterns[AbstractReplacementTerms.IMPORTED_VARIABLE] = build_regex_pattern_from_list(
        nodes[DeclType.VAR_TYPE][VarSourceType.IMPORTED]
    )
    patterns[AbstractReplacementTerms.LOCAL_FUNCTION] = build_regex_pattern_from_list(
        nodes[DeclType.FUNCTION_TYPE][VarSourceType.FILE_LOCAL]
    )
    patterns[AbstractReplacementTerms.IMPORTED_FUNCTION] = build_regex_pattern_from_list(
        nodes[DeclType.FUNCTION_TYPE][VarSourceType.IMPORTED]
    )
    patterns[AbstractReplacementTerms.LOCAL_STRUCT] = build_regex_pattern_from_list(
        nodes[DeclType.STRUCT_TYPE][VarSourceType.FILE_LOCAL]
    )
    patterns[AbstractReplacementTerms.IMPORTED_STRUCT] = build_regex_pattern_from_list(
        nodes[DeclType.STRUCT_TYPE][VarSourceType.IMPORTED]
    )
    patterns[AbstractReplacementTerms.LOCAL_STRUCT_FIELD] = build_regex_pattern_from_list(
        nodes[DeclType.FIELD_TYPE][VarSourceType.FILE_LOCAL]
    )
    patterns[AbstractReplacementTerms.IMPORTED_STRUCT_FIELD] = build_regex_pattern_from_list(
        nodes[DeclType.FIELD_TYPE][VarSourceType.IMPORTED]
    )
    patterns[AbstractReplacementTerms.PARAM] = build_regex_pattern_from_list((
        list(nodes[DeclType.PARAM_TYPE][VarSourceType.FILE_LOCAL].keys())
        + list(nodes[DeclType.PARAM_TYPE][VarSourceType.IMPORTED].keys())
    ))
    patterns[AbstractReplacementTerms.LOCAL_ENUM_CONST] = build_regex_pattern_from_list(
        nodes[DeclType.ENUM_CONST_TYPE][VarSourceType.FILE_LOCAL]
    )
    patterns[AbstractReplacementTerms.IMPORTED_ENUM_CONST] = build_regex_pattern_from_list(
        nodes[DeclType.ENUM_CONST_TYPE][VarSourceType.IMPORTED]
    )

    for i, line in enumerate(code_snippet):

        if line[0] != "#":

            for abstract_term in patterns:
                pattern = patterns[abstract_term]
                if pattern is not None:
                    code_snippet[i] = search_line_and_replace(code_snippet[i], pattern, abstract_term)

            code_snippet[i] = re.sub(r"\b[0-9]+\b", AbstractReplacementTerms.NUMBER, code_snippet[i])

    return code_snippet


def is_node_local(cursor: Cursor, filename: str) -> bool:
    # check if the node passed in is defined in this file or elsewhere
    return cursor.location.file and cursor.location.file.name == filename


def parse_snippet(snippet: str, filepath: str) -> Cursor:
    filename = filepath  # filepath.split("/")[-1]  # only take filename bit of the filepath

    # set up unsaved files so can use string of the c code with the libclang parser
    unsaved_files = [(filename, snippet)]

    # Create an index
    index = clang.cindex.Index.create()

    # Parse the code from the string
    translation_unit = index.parse(
        path=filename, unsaved_files=unsaved_files, options=clang.cindex.TranslationUnit.PARSE_NONE
    )

    return translation_unit.cursor


def search_ast_for_node_types(node: Cursor, types: TypesDictType, filename: str) -> NodesDictType:
    # returns a dict with the type as the key and a nested dict containing the separated local and imported sets of
    # the relevant nodes
    nodes: NodesDictType = {}

    # initialise the empty sets
    for node_type in types:
        nodes[node_type] = {VarSourceType.FILE_LOCAL: {}, VarSourceType.IMPORTED: {}}

    # recursively search AST (might need to change this to for loop though as python isn't that good with high
    # recursion depths?)
    nodes = _search_ast_for_node_type(node, types, nodes, filename)

    return nodes


def _search_ast_for_node_type(node: Cursor, types: TypesDictType, nodes: NodesDictType, filename: str) -> NodesDictType:
    for node_type in types:
        if node.kind == types[node_type]:
            if is_node_local(node, filename):
                nodes[node_type][VarSourceType.FILE_LOCAL][node.spelling] = node
            else:
                nodes[node_type][VarSourceType.IMPORTED][node.spelling] = node
    for child in node.get_children():
        nodes = _search_ast_for_node_type(child, types, nodes, filename)

    return nodes


def clean_up_snippet(snippet: str) -> list[str]:
    whitespace_pattern = r"\s+"
    # unnecessary_space_pattern_1 = r'(\W)\s+(\w)'
    # unnecessary_space_pattern_2 = r'(\w)\s+(\W)'

    comment_pattern = r"^\s*(\/\*|\*|\/\/)"
    comment_in_code_line_pattern = r"(\/\*.*\*\/|\\\\.*)"

    stripped_lines = []

    for line in snippet.splitlines():
        # remove empty lines and also strip leading and trailing white space from each line
        if re.search(comment_pattern, line):
            # ignore comments
            continue
        if line.strip() != "":
            # reduce any occurrences of multiple whitespaces to just one
            line = re.sub(whitespace_pattern, " ", line)
            line = re.sub(comment_in_code_line_pattern, "", line)  # remove comments

            # # remove any spaces that are unnecessary
            # all_matches = re.findall(unnecessary_space_pattern_1, line)
            # matches = re.findall(unnecessary_space_pattern_2, line)

            # if matches is not None:
            #     if all_matches is not None:
            #         all_matches = all_matches + matches
            #     else:
            #         all_matches = matches

            # for match in all_matches:
            #     match_string =
            #     new_match = match.replace(" ", "")
            #     line = re.sub(match, new_match, line)

            if line != "":
                stripped_lines.append(line.strip())

    return stripped_lines


def find_diff_between_commits(before_commit: Commit, after_commit: Commit) -> dict[str, FileDiff]:
    # find the diffs:
    diffs = before_commit.diff(after_commit, create_patch=True)
    filename_diffs: dict[str, FileDiff] = {}

    files_checked: list[str] = []

    for diff in diffs:
        logger.debug(f"\nDiff for file: {diff.b_path}")

        filepath = diff.b_path

        if filepath is not None:
            files_checked.append(filepath)
            file_extensions = [".c", ".h"]

            regex_pattern = r"("
            for i, extension in enumerate(file_extensions):
                regex_pattern += re.escape(extension) + "$"
                if i < len(file_extensions) - 1:
                    regex_pattern += "|"
                else:
                    regex_pattern += ")"

            if not re.search(regex_pattern, filepath):
                continue
        else:
            if diff.a_path is None:
                continue
            else:
                filepath = diff.a_path
                logger.debug(f"Diff b_path is none so file was deleted in commit, diff a_path is: {filepath}.")

        # filename = (filepath.split("/"))[-1]
        filename = filepath

        change_type = ChangeType.FUNCTIONAL_CHANGE

        before_file: Optional[str] = None
        before_file_lines: list[str] = []
        after_file: Optional[str] = None
        after_file_lines: list[str] = []

        try:
            before_file = (before_commit.tree / filepath).data_stream.read().decode("utf-8")

        except KeyError:
            change_type = ChangeType.FILE_ADDED

        try:
            after_file = (after_commit.tree / filepath).data_stream.read().decode("utf-8")

        except KeyError:
            change_type = ChangeType.FILE_REMOVED

        before_function_lines: FunctionDictType = {}
        after_function_lines: FunctionDictType = {}
        before_file_ast: Optional[Cursor] = None
        after_file_ast: Optional[Cursor] = None
        before_nodes: NodesDictType = {}
        after_nodes: NodesDictType = {}

        if change_type in {ChangeType.FUNCTIONAL_CHANGE, ChangeType.FILE_REMOVED} and before_file is not None:
            before_file_lines = clean_up_snippet(before_file)
            before_file_ast = parse_snippet(before_file, filename)
            before_nodes = search_ast_for_node_types(before_file_ast, TYPES, filename)
            before_function_lines = get_full_function_snippets(
                before_file_lines, before_nodes[DeclType.FUNCTION_TYPE][VarSourceType.FILE_LOCAL]
            )

        if change_type in {ChangeType.FUNCTIONAL_CHANGE, ChangeType.FILE_ADDED} and after_file is not None:
            after_file_lines = clean_up_snippet(after_file)
            after_file_ast = parse_snippet(after_file, filename)
            after_nodes = search_ast_for_node_types(after_file_ast, TYPES, filename)
            after_function_lines = get_full_function_snippets(
                after_file_lines, after_nodes[DeclType.FUNCTION_TYPE][VarSourceType.FILE_LOCAL]
            )

        diff_functions = get_function_diffs(before_function_lines, after_function_lines)

        if change_type == ChangeType.FUNCTIONAL_CHANGE:

            before_refs = []

            if before_nodes:
                for type_key in before_nodes:
                    before_refs = before_refs + list(before_nodes[type_key][VarSourceType.FILE_LOCAL].keys())
                    before_refs = before_refs + list(before_nodes[type_key][VarSourceType.IMPORTED].keys())

            after_refs = []
            if after_nodes:
                for type_key in after_nodes:
                    after_refs = after_refs + list(before_nodes[type_key][VarSourceType.FILE_LOCAL].keys())
                    after_refs = after_refs + list(before_nodes[type_key][VarSourceType.IMPORTED].keys())

            new_diff_functions = {}
            for function_name in diff_functions:
                function_before = diff_functions[function_name].before_lines
                function_after = diff_functions[function_name].after_lines

                is_functional = is_diff_functional(function_before, function_after, before_refs, after_refs, filename)

                logger.debug(f"Is {function_name} diff functional? {is_functional}")

                if is_functional:
                    new_diff_functions[function_name] = copy.deepcopy(diff_functions[function_name])

                    if FILE_CODE in after_function_lines:
                        new_diff_functions[function_name].after_external_variable_decls = (
                            get_function_external_variables_decl(
                                function_name, after_nodes, after_function_lines[FILE_CODE]
                            )
                        )

                    if FILE_CODE in before_function_lines:
                        new_diff_functions[function_name].before_external_variable_decls = (
                            get_function_external_variables_decl(
                                function_name, before_nodes, before_function_lines[FILE_CODE]
                            )
                        )

                    new_diff_functions[function_name].append_external_variable_decls_to_code_lines()

            diff_functions = new_diff_functions

        if diff_functions:
            full_file_diff_lines = make_diff(before_file_lines, after_file_lines, filename)
            og_diff = diff.diff.decode("utf-8")
            filename_diffs[filename] = FileDiff(
                filename,
                before_file_lines,
                after_file_lines,
                full_file_diff_lines,
                change_type=change_type,
                before_commit=before_commit,
                after_commit=after_commit,
                before_ast=before_file_ast,
                after_ast=after_file_ast,
                diff_functions=diff_functions,
                og_diff=og_diff,
            )

            logger.debug(f"FileDiff created for {filename}.")
            # logger.debug(f"FileDiffs print for {filename}:")
            # logger.debug(str(filename_diffs[filename]))
            # logger.info(abstract_code(before_file_lines, before_file_ast, filename))

    return filename_diffs


def make_diff(before: list[str], after: list[str], filename: str = "") -> list[str]:
    return list(difflib.unified_diff(before, after, lineterm="", fromfile=filename, tofile=filename))


def get_function_diffs(before: FunctionDictType, after: FunctionDictType) -> dict[str, FunctionDiff]:
    diff_functions: dict[str, FunctionDiff] = {}
    after_functions: list[str] = []

    if after:
        after_functions = list(after.keys())

    if before is not None:
        for function_name in before:

            if after_functions and function_name in after:
                # function exists in both files
                after_functions.remove(function_name)

                # check if functions are same:
                functions_same = before[function_name] == after[function_name]

                # logger.info(f"{function_name} is not diff = {functions_same}")
                # logger.info(f"diff: {make_diff(before[function_name], after[function_name])}")

                if not functions_same:
                    # diff in these functions so make the diff
                    diff = make_diff(before[function_name], after[function_name])

                    diff_functions[function_name] = FunctionDiff(
                        function_name,
                        before_lines=before[function_name],
                        after_lines=after[function_name],
                        diff_lines=diff,
                    )
            else:
                after_function = [""] if function_name not in after else after[function_name]

                diff = make_diff(before[function_name], after_function)
                diff_functions[function_name] = FunctionDiff(
                    function_name, before_lines=before[function_name], diff_lines=diff
                )

    if after_functions:
        for function_name in after_functions:
            before_function = [""] if function_name not in before else before[function_name]
            diff = make_diff(before_function, after[function_name])
            diff_functions[function_name] = FunctionDiff(
                function_name, after_lines=after[function_name], diff_lines=diff
            )

    return diff_functions


def get_full_function_snippets(full_file: list[str], functions: dict[str, Cursor]) -> FunctionDictType:
    open_code_block_pattern = r"{"
    close_code_block_pattern = r"}"
    lines = copy.deepcopy(full_file)

    functions_code = {}
    file_code = []

    while lines:
        function_name_mentioned = None
        for function_name in functions:
            function_name_pattern = r"\b" + function_name + r"\(.*\)\s*{?$"
            if re.search(function_name_pattern, lines[0]):
                function_name_mentioned = function_name
                break

        if function_name_mentioned is not None and function_name_mentioned not in functions_code:
            # assuming that the first instance of a file local function name appearing will be in the function
            # definition so if it hasn't been added to the keys yet, then it should be the first declaration?
            function_lines = []
            open_brackets = 0

            for line in lines:
                function_lines.append(line)

                if re.search(open_code_block_pattern, line):
                    open_brackets += len(re.findall(open_code_block_pattern, line))

                if re.search(close_code_block_pattern, line):
                    open_brackets -= len(re.findall(close_code_block_pattern, line))
                    if open_brackets == 0:
                        break

            lines = lines[len(function_lines) :]

            functions_code[function_name_mentioned] = function_lines
        else:
            file_code.append(lines[0])
            lines.pop(0)

    functions_code[FILE_CODE] = file_code

    return functions_code


def get_function_external_variables_decl(function_name, full_file_nodes, non_function_code_snippets):
    if FILE_CODE == function_name:
        return {}

    function_ast = full_file_nodes[DeclType.FUNCTION_TYPE][VarSourceType.FILE_LOCAL][function_name]

    all_function_names = list(full_file_nodes[DeclType.FUNCTION_TYPE][VarSourceType.FILE_LOCAL].keys()) + list(
        full_file_nodes[DeclType.FUNCTION_TYPE][VarSourceType.IMPORTED].keys()
    )

    imported_to_file_vars = list(full_file_nodes[DeclType.VAR_TYPE][VarSourceType.IMPORTED].keys())

    # get the nodes for the variables declared and the variables/functions referenced
    nodes = search_ast_for_node_types(function_ast, TYPES_FOR_EXTERNAL_DEFINED_VARS, function_ast.location.file.name)

    vars_declared = nodes[DeclType.VAR_TYPE][VarSourceType.FILE_LOCAL]  # should only be local to the function

    if DeclType.PARAM_TYPE in nodes:
        # include function parameters
        vars_declared = vars_declared | nodes[DeclType.PARAM_TYPE][VarSourceType.FILE_LOCAL]

    undeclared_vars = []

    for decl_ref in nodes[DeclType.DECL_REF_TYPE][VarSourceType.FILE_LOCAL]:
        if decl_ref not in all_function_names and decl_ref not in imported_to_file_vars:
            # then it should be declared within this function, as a parameter to the function or in the body of the function
            if decl_ref not in vars_declared:
                # if it isn't, then it must be declared in the file outside of the function
                undeclared_vars.append(decl_ref)

    external_var_declarations = {}
    for line in non_function_code_snippets:
        for undeclared_var in undeclared_vars:
            if undeclared_var in line:
                # assuming that the first line a variable is mentioned is it's declaration (think it has to be at least?)
                external_var_declarations[undeclared_var] = line
                undeclared_vars.remove(undeclared_var)

    return external_var_declarations


def get_variable_snippets(full_snippet: list[str], variable_name: str) -> list[str]:
    variable_refs = []
    full_snippet = copy.deepcopy(full_snippet)

    for line in full_snippet:
        if variable_name in line:
            variable_refs.append(line)

    return variable_refs


def check_functional_diff_in_variable_lines_order(
    before_code: list[str], after_code: list[str], variable_names: set[str]
) -> bool:
    for variable_name in variable_names:
        variable_before_lines = get_variable_snippets(before_code, variable_name)
        variable_after_lines = get_variable_snippets(after_code, variable_name)

        # logger.info(variable_before_lines)
        # logger.info(variable_after_lines)
        # logger.info(f'{variable_name} code is same in both? {variable_before_lines == variable_after_lines}')

        if not variable_before_lines == variable_after_lines:
            return True

    return False  # I think?


def get_function_refs(function_lines, ref_names):
    function_refs = set()
    function_string = "\n".join(function_lines)

    for ref_name in ref_names:
        ref_name_regex = r"\b" + re.escape(ref_name) + r"\b"
        if re.search(ref_name_regex, function_string):
            function_refs.add(ref_name)

    return function_refs


def is_diff_functional(
    function_before_code: list[str],
    function_after_code: list[str],
    all_refs_before,
    all_refs_after,
    filename,
) -> bool:
    # are they exactly the same? - essentially is it just whitespace or other formatting that's been changed?
    if function_before_code == function_after_code:  # could also probs check the asts here instead??
        return False  # no functional change made

    # decl_ref_types = {
    #     DeclType.VAR_TYPE: CursorKind.VAR_DECL, # type: ignore
    #     DeclType.DECL_REF_TYPE: CursorKind.DECL_REF_EXPR, # type: ignore
    #     DeclType.PARAM_TYPE: CursorKind.PARAM_DECL, # type: ignore
    #     }
    # before_nodes = search_ast_for_node_types(before_ast, decl_ref_types, filename)
    # after_nodes = search_ast_for_node_types(after_ast, decl_ref_types, filename)

    # vars referenced only?
    # before_refs = set(list(before_nodes[DeclType.DECL_REF_TYPE][VarSourceType.FILE_LOCAL].keys()) + list(before_nodes[DeclType.DECL_REF_TYPE][VarSourceType.IMPORTED].keys()))
    # after_refs = set(list(after_nodes[DeclType.DECL_REF_TYPE][VarSourceType.FILE_LOCAL].keys()) + list(after_nodes[DeclType.DECL_REF_TYPE][VarSourceType.IMPORTED].keys()))

    before_refs = get_function_refs(function_before_code, all_refs_before)
    after_refs = get_function_refs(function_after_code, all_refs_after)

    # logger.info(f'variables referenced: {after_refs}')

    variables_same = before_refs == after_refs

    # logger.info(f'variables are the same? {variables_same}')
    if variables_same:
        # check for non-functional reordering
        # logger.info(f"variable_lines reordered?: {check_functional_diff_in_variable_lines_order(function_before_code, function_after_code, before_refs)}")

        return check_functional_diff_in_variable_lines_order(function_before_code, function_after_code, before_refs)

    else:
        # check if a variable has been renamed (also checks nonfunctional reordering changes too)
        # check list size of variables is the same as if they aren't then likely functional change (i.e. not just variable renaming)
        if len(before_refs) != len(after_refs):
            return True

        # find the different variable/s
        unique_variable_names_before = list(before_refs - after_refs)
        unique_variable_names_after = list(after_refs - before_refs)

        for before_variable in unique_variable_names_before:
            variable_before_lines = get_variable_snippets(function_before_code, before_variable)

            variables_swapped = False

            for after_variable in unique_variable_names_after:
                variable_after_lines = get_variable_snippets(function_after_code, after_variable)

                # replace new variable_name with the old one and compare code
                for i, line in enumerate(variable_after_lines):
                    variable_after_lines[i] = re.sub(after_variable, before_variable, line)

                if variable_before_lines == variable_after_lines:
                    variables_swapped = True
                    break

            if not variables_swapped:
                return True

    return False  # any functional diff should have been returned by this point I think?


ProcessedCommits: TypeAlias = dict[str, dict[str, FileDiff]]


def find_functional_changes(project_read_only, cp_source) -> ProcessedCommits:

    repo, ref = project_read_only.repos[cp_source]

    logger.info("Preprocessing commits")

    # for each commit compare with it's parent to find the relevant files changed and the functional
    # changes within each file
    preprocessed_commits = {}

    for commit in repo.iter_commits(ref):
        if commit.parents:
            parent_commit = commit.parents[0]
            diffs = find_diff_between_commits(parent_commit, commit)
            # logger.info(f"Commit: {commit.hexsha}:\n{diffs}")

            if diffs:
                preprocessed_commits[commit.hexsha] = diffs

    logger.debug(f"Functional changes found in the following commits: {list(preprocessed_commits.keys())}")
    logger.info(
        f"{len(preprocessed_commits)} out of {len(list(repo.iter_commits(ref)))} commits have potentially functional differences."
    )

    return preprocessed_commits


def create_patch(function_name, file_lines, new_function_lines, filename=""):
    open_code_block_pattern = r"{"
    close_code_block_pattern = r"}"
    lines = copy.deepcopy(file_lines)
    function_name_pattern = r"\b" + function_name + r"\b"

    start_index = -1
    end_index = -1

    open_brackets = 0

    for i, line in enumerate(lines):

        if start_index < 0 and re.search(function_name_pattern, line):
            start_index = i

        if start_index > 0:
            if re.search(open_code_block_pattern, line):
                open_brackets += len(re.findall(open_code_block_pattern, line))

            if re.search(close_code_block_pattern, line):
                open_brackets -= len(re.findall(close_code_block_pattern, line))
                if open_brackets == 0:
                    end_index = i + 1
                    break

    start_file = lines[:start_index]
    end_file = lines[end_index:]

    new_file = start_file + new_function_lines + end_file

    diff = make_diff(file_lines, new_file, filename)

    return diff


# test code below -> leaving for now so that I can use again when setting up the Java stuff
# C code string
# code = """
# #include <stdio.h>
# #include <string.h>
# #include <unistd.h>

# char items[3][10];

# void func_a(){
#     char* buff;
#     int i = 0;
#     do{
#         printf("input item:");
#         buff = &items[i][0];
#         i++;
#         fgets(buff, 40, stdin);
#         buff[strcspn(buff, "\\n")] = 0;
#     }while(strlen(buff)!=0);
#     i--;
# }

# void func_b(){
#     char *buff;
#     printf("done adding items\\n");
#     int j;
#     printf("display item #:");
#     scanf("%d", &j);
#     buff = &items[j][0];
#     printf("item %d: %s\\n", j, buff);
# }

# #ifndef ___TEST___
# int main()
# {

#     func_a();

#     func_b();

#     return 0;
# }
# #endif
# """

# new_func = """
# void func_b(){
#     char *buff;
#     printf("done adding items but this is a change\\n");
#     int j;
#     printf("display item #:");
#     scanf("%d", &j);
#     buff = &items[j][1];
#     printf("item %d: %s\\n", j, buff);
# }
# """

code = """

/*
 * Copyright (C) Igor Sysoev
 * Copyright (C) Nginx, Inc.
 */


#include <ngx_config.h>
#include <ngx_core.h>
#include <ngx_event.h>


#if 0
#define NGX_SENDFILE_LIMIT  4096
#endif

/*
 * When DIRECTIO is enabled FreeBSD, Solaris, and MacOSX read directly
 * to an application memory from a device if parameters are aligned
 * to device sector boundary (512 bytes).  They fallback to usual read
 * operation if the parameters are not aligned.
 * Linux allows DIRECTIO only if the parameters are aligned to a filesystem
 * sector boundary, otherwise it returns EINVAL.  The sector size is
 * usually 512 bytes, however, on XFS it may be 4096 bytes.
 */

#define NGX_NONE            1


static ngx_inline ngx_int_t
    ngx_output_chain_as_is(ngx_output_chain_ctx_t *ctx, ngx_buf_t *buf);
static ngx_int_t ngx_output_chain_add_copy(ngx_pool_t *pool,
    ngx_chain_t **chain, ngx_chain_t *in);
static ngx_int_t ngx_output_chain_align_file_buf(ngx_output_chain_ctx_t *ctx,
    off_t bsize);
static ngx_int_t ngx_output_chain_get_buf(ngx_output_chain_ctx_t *ctx,
    off_t bsize);
static ngx_int_t ngx_output_chain_copy_buf(ngx_output_chain_ctx_t *ctx);


ngx_int_t
ngx_output_chain(ngx_output_chain_ctx_t *ctx, ngx_chain_t *in)
{
    off_t         bsize;
    ngx_int_t     rc, last;
    ngx_chain_t  *cl, *out, **last_out;

    if (ctx->in == NULL && ctx->busy == NULL
#if (NGX_HAVE_FILE_AIO || NGX_THREADS)
        && !ctx->aio
#endif
       )
    {
        /*
         * the short path for the case when the ctx->in and ctx->busy chains
         * are empty, the incoming chain is empty too or has the single buf
         * that does not require the copy
         */

        if (in == NULL) {
            return ctx->output_filter(ctx->filter_ctx, in);
        }

        if (in->next == NULL
#if (NGX_SENDFILE_LIMIT)
            && !(in->buf->in_file && in->buf->file_last > NGX_SENDFILE_LIMIT)
#endif
            && ngx_output_chain_as_is(ctx, in->buf))
        {
            return ctx->output_filter(ctx->filter_ctx, in);
        }
    }

    /* add the incoming buf to the chain ctx->in */

    if (in) {
        if (ngx_output_chain_add_copy(ctx->pool, &ctx->in, in) == NGX_ERROR) {
            return NGX_ERROR;
        }
    }

    out = NULL;
    last_out = &out;
    last = NGX_NONE;

    for ( ;; ) {

#if (NGX_HAVE_FILE_AIO || NGX_THREADS)
        if (ctx->aio) {
            return NGX_AGAIN;
        }
#endif

        while (ctx->in) {

            /*
             * cycle while there are the ctx->in bufs
             * and there are the free output bufs to copy in
             */

            bsize = ngx_buf_size(ctx->in->buf);

            if (bsize == 0 && !ngx_buf_special(ctx->in->buf)) {

                ngx_log_error(NGX_LOG_ALERT, ctx->pool->log, 0,
                              "zero size buf in output "
                              "t:%d r:%d f:%d %p %p-%p %p %O-%O",
                              ctx->in->buf->temporary,
                              ctx->in->buf->recycled,
                              ctx->in->buf->in_file,
                              ctx->in->buf->start,
                              ctx->in->buf->pos,
                              ctx->in->buf->last,
                              ctx->in->buf->file,
                              ctx->in->buf->file_pos,
                              ctx->in->buf->file_last);

                ngx_debug_point();

                cl = ctx->in;
                ctx->in = cl->next;

                ngx_free_chain(ctx->pool, cl);

                continue;
            }

            if (bsize < 0) {

                ngx_log_error(NGX_LOG_ALERT, ctx->pool->log, 0,
                              "negative size buf in output "
                              "t:%d r:%d f:%d %p %p-%p %p %O-%O",
                              ctx->in->buf->temporary,
                              ctx->in->buf->recycled,
                              ctx->in->buf->in_file,
                              ctx->in->buf->start,
                              ctx->in->buf->pos,
                              ctx->in->buf->last,
                              ctx->in->buf->file,
                              ctx->in->buf->file_pos,
                              ctx->in->buf->file_last);

                ngx_debug_point();

                return NGX_ERROR;
            }

            if (ngx_output_chain_as_is(ctx, ctx->in->buf)) {

                /* move the chain link to the output chain */

                cl = ctx->in;
                ctx->in = cl->next;

                *last_out = cl;
                last_out = &cl->next;
                cl->next = NULL;

                continue;
            }

            if (ctx->buf == NULL) {

                rc = ngx_output_chain_align_file_buf(ctx, bsize);

                if (rc == NGX_ERROR) {
                    return NGX_ERROR;
                }

                if (rc != NGX_OK) {

                    if (ctx->free) {

                        /* get the free buf */

                        cl = ctx->free;
                        ctx->buf = cl->buf;
                        ctx->free = cl->next;

                        ngx_free_chain(ctx->pool, cl);

                    } else if (out || ctx->allocated == ctx->bufs.num) {

                        break;

                    } else if (ngx_output_chain_get_buf(ctx, bsize) != NGX_OK) {
                        return NGX_ERROR;
                    }
                }
            }

            rc = ngx_output_chain_copy_buf(ctx);

            if (rc == NGX_ERROR) {
                return rc;
            }

            if (rc == NGX_AGAIN) {
                if (out) {
                    break;
                }

                return rc;
            }

            /* delete the completed buf from the ctx->in chain */

            if (ngx_buf_size(ctx->in->buf) == 0) {
                cl = ctx->in;
                ctx->in = cl->next;

                ngx_free_chain(ctx->pool, cl);
            }

            cl = ngx_alloc_chain_link(ctx->pool);
            if (cl == NULL) {
                return NGX_ERROR;
            }

            cl->buf = ctx->buf;
            cl->next = NULL;
            *last_out = cl;
            last_out = &cl->next;
            ctx->buf = NULL;
        }

        if (out == NULL && last != NGX_NONE) {

            if (ctx->in) {
                return NGX_AGAIN;
            }

            return last;
        }

        last = ctx->output_filter(ctx->filter_ctx, out);

        if (last == NGX_ERROR || last == NGX_DONE) {
            return last;
        }

        ngx_chain_update_chains(ctx->pool, &ctx->free, &ctx->busy, &out,
                                ctx->tag);
        last_out = &out;
    }
}


static ngx_inline ngx_int_t
ngx_output_chain_as_is(ngx_output_chain_ctx_t *ctx, ngx_buf_t *buf)
{
    ngx_uint_t  sendfile;

    if (ngx_buf_special(buf)) {
        return 1;
    }

#if (NGX_THREADS)
    if (buf->in_file) {
        buf->file->thread_handler = ctx->thread_handler;
        buf->file->thread_ctx = ctx->filter_ctx;
    }
#endif

    sendfile = ctx->sendfile;

#if (NGX_SENDFILE_LIMIT)

    if (buf->in_file && buf->file_pos >= NGX_SENDFILE_LIMIT) {
        sendfile = 0;
    }

#endif

#if !(NGX_HAVE_SENDFILE_NODISKIO)

    /*
     * With DIRECTIO, disable sendfile() unless sendfile(SF_NOCACHE)
     * is available.
     */

    if (buf->in_file && buf->file->directio) {
        sendfile = 0;
    }

#endif

    if (!sendfile) {

        if (!ngx_buf_in_memory(buf)) {
            return 0;
        }

        buf->in_file = 0;
    }

    if (ctx->need_in_memory && !ngx_buf_in_memory(buf)) {
        return 0;
    }

    if (ctx->need_in_temp && (buf->memory || buf->mmap)) {
        return 0;
    }

    return 1;
}


static ngx_int_t
ngx_output_chain_add_copy(ngx_pool_t *pool, ngx_chain_t **chain,
    ngx_chain_t *in)
{
    ngx_chain_t  *cl, **ll;
#if (NGX_SENDFILE_LIMIT)
    ngx_buf_t    *b, *buf;
#endif

    ll = chain;

    for (cl = *chain; cl; cl = cl->next) {
        ll = &cl->next;
    }

    while (in) {

        cl = ngx_alloc_chain_link(pool);
        if (cl == NULL) {
            return NGX_ERROR;
        }

#if (NGX_SENDFILE_LIMIT)

        buf = in->buf;

        if (buf->in_file
            && buf->file_pos < NGX_SENDFILE_LIMIT
            && buf->file_last > NGX_SENDFILE_LIMIT)
        {
            /* split a file buf on two bufs by the sendfile limit */

            b = ngx_calloc_buf(pool);
            if (b == NULL) {
                return NGX_ERROR;
            }

            ngx_memcpy(b, buf, sizeof(ngx_buf_t));

            if (ngx_buf_in_memory(buf)) {
                buf->pos += (ssize_t) (NGX_SENDFILE_LIMIT - buf->file_pos);
                b->last = buf->pos;
            }

            buf->file_pos = NGX_SENDFILE_LIMIT;
            b->file_last = NGX_SENDFILE_LIMIT;

            cl->buf = b;

        } else {
            cl->buf = buf;
            in = in->next;
        }

#else
        cl->buf = in->buf;
        in = in->next;

#endif

        cl->next = NULL;
        *ll = cl;
        ll = &cl->next;
    }

    return NGX_OK;
}


static ngx_int_t
ngx_output_chain_align_file_buf(ngx_output_chain_ctx_t *ctx, off_t bsize)
{
    size_t      size;
    ngx_buf_t  *in;

    in = ctx->in->buf;

    if (in->file == NULL || !in->file->directio) {
        return NGX_DECLINED;
    }

    ctx->directio = 1;

    size = (size_t) (in->file_pos - (in->file_pos & ~(ctx->alignment - 1)));

    if (size == 0) {

        if (bsize >= (off_t) ctx->bufs.size) {
            return NGX_DECLINED;
        }

        size = (size_t) bsize;

    } else {
        size = (size_t) ctx->alignment - size;

        if ((off_t) size > bsize) {
            size = (size_t) bsize;
        }
    }

    ctx->buf = ngx_create_temp_buf(ctx->pool, size);
    if (ctx->buf == NULL) {
        return NGX_ERROR;
    }

    /*
     * we do not set ctx->buf->tag, because we do not want
     * to reuse the buf via ctx->free list
     */

#if (NGX_HAVE_ALIGNED_DIRECTIO)
    ctx->unaligned = 1;
#endif

    return NGX_OK;
}


static ngx_int_t
ngx_output_chain_get_buf(ngx_output_chain_ctx_t *ctx, off_t bsize)
{
    size_t       size;
    ngx_buf_t   *b, *in;
    ngx_uint_t   recycled;

    in = ctx->in->buf;
    size = ctx->bufs.size;
    recycled = 1;

    if (in->last_in_chain) {

        if (bsize < (off_t) size) {

            /*
             * allocate a small temp buf for a small last buf
             * or its small last part
             */

            size = (size_t) bsize;
            recycled = 0;

        } else if (!ctx->directio
                   && ctx->bufs.num == 1
                   && (bsize < (off_t) (size + size / 4)))
        {
            /*
             * allocate a temp buf that equals to a last buf,
             * if there is no directio, the last buf size is lesser
             * than 1.25 of bufs.size and the temp buf is single
             */

            size = (size_t) bsize;
            recycled = 0;
        }
    }

    b = ngx_calloc_buf(ctx->pool);
    if (b == NULL) {
        return NGX_ERROR;
    }

    if (ctx->directio) {

        /*
         * allocate block aligned to a disk sector size to enable
         * userland buffer direct usage conjunctly with directio
         */

        b->start = ngx_pmemalign(ctx->pool, size, (size_t) ctx->alignment);
        if (b->start == NULL) {
            return NGX_ERROR;
        }

    } else {
        b->start = ngx_palloc(ctx->pool, size);
        if (b->start == NULL) {
            return NGX_ERROR;
        }
    }

    b->pos = b->start;
    b->last = b->start;
    b->end = b->last + size;
    b->temporary = 1;
    b->tag = ctx->tag;
    b->recycled = recycled;

    ctx->buf = b;
    ctx->allocated++;

    return NGX_OK;
}


static ngx_int_t
ngx_output_chain_copy_buf(ngx_output_chain_ctx_t *ctx)
{
    off_t        size;
    ssize_t      n;
    ngx_buf_t   *src, *dst;
    ngx_uint_t   sendfile;

    src = ctx->in->buf;
    dst = ctx->buf;

    size = ngx_buf_size(src);
    size = ngx_min(size, dst->end - dst->pos);

    sendfile = ctx->sendfile && !ctx->directio;

#if (NGX_SENDFILE_LIMIT)

    if (src->in_file && src->file_pos >= NGX_SENDFILE_LIMIT) {
        sendfile = 0;
    }

#endif

    if (ngx_buf_in_memory(src)) {
        ngx_memcpy(dst->pos, src->pos, (size_t) size);
        src->pos += (size_t) size;
        dst->last += (size_t) size;

        if (src->in_file) {

            if (sendfile) {
                dst->in_file = 1;
                dst->file = src->file;
                dst->file_pos = src->file_pos;
                dst->file_last = src->file_pos + size;

            } else {
                dst->in_file = 0;
            }

            src->file_pos += size;

        } else {
            dst->in_file = 0;
        }

        if (src->pos == src->last) {
            dst->flush = src->flush;
            dst->last_buf = src->last_buf;
            dst->last_in_chain = src->last_in_chain;
        }

    } else {

#if (NGX_HAVE_ALIGNED_DIRECTIO)

        if (ctx->unaligned) {
            if (ngx_directio_off(src->file->fd) == NGX_FILE_ERROR) {
                ngx_log_error(NGX_LOG_ALERT, ctx->pool->log, ngx_errno,
                              ngx_directio_off_n " \"%s\" failed",
                              src->file->name.data);
            }
        }

#endif

#if (NGX_HAVE_FILE_AIO)
        if (ctx->aio_handler) {
            n = ngx_file_aio_read(src->file, dst->pos, (size_t) size,
                                  src->file_pos, ctx->pool);
            if (n == NGX_AGAIN) {
                ctx->aio_handler(ctx, src->file);
                return NGX_AGAIN;
            }

        } else
#endif
#if (NGX_THREADS)
        if (ctx->thread_handler) {
            src->file->thread_task = ctx->thread_task;
            src->file->thread_handler = ctx->thread_handler;
            src->file->thread_ctx = ctx->filter_ctx;

            n = ngx_thread_read(src->file, dst->pos, (size_t) size,
                                src->file_pos, ctx->pool);
            if (n == NGX_AGAIN) {
                ctx->thread_task = src->file->thread_task;
                return NGX_AGAIN;
            }

        } else
#endif
        {
            n = ngx_read_file(src->file, dst->pos, (size_t) size,
                              src->file_pos);
        }

#if (NGX_HAVE_ALIGNED_DIRECTIO)

        if (ctx->unaligned) {
            ngx_err_t  err;

            err = ngx_errno;

            if (ngx_directio_on(src->file->fd) == NGX_FILE_ERROR) {
                ngx_log_error(NGX_LOG_ALERT, ctx->pool->log, ngx_errno,
                              ngx_directio_on_n " \"%s\" failed",
                              src->file->name.data);
            }

            ngx_set_errno(err);

            ctx->unaligned = 0;
        }

#endif

        if (n == NGX_ERROR) {
            return (ngx_int_t) n;
        }

        if (n != size) {
            ngx_log_error(NGX_LOG_ALERT, ctx->pool->log, 0,
                          ngx_read_file_n " read only %z of %O from \"%s\"",
                          n, size, src->file->name.data);
            return NGX_ERROR;
        }

        dst->last += n;

        if (sendfile) {
            dst->in_file = 1;
            dst->file = src->file;
            dst->file_pos = src->file_pos;
            dst->file_last = src->file_pos + n;

        } else {
            dst->in_file = 0;
        }

        src->file_pos += n;

        if (src->file_pos == src->file_last) {
            dst->flush = src->flush;
            dst->last_buf = src->last_buf;
            dst->last_in_chain = src->last_in_chain;
        }
    }

    return NGX_OK;
}


ngx_int_t
ngx_chain_writer(void *data, ngx_chain_t *in)
{
    ngx_chain_writer_ctx_t *ctx = data;

    off_t              size;
    ngx_chain_t       *cl, *ln, *chain;
    ngx_connection_t  *c;

    c = ctx->connection;

    for (size = 0; in; in = in->next) {

        if (ngx_buf_size(in->buf) == 0 && !ngx_buf_special(in->buf)) {

            ngx_log_error(NGX_LOG_ALERT, ctx->pool->log, 0,
                          "zero size buf in chain writer "
                          "t:%d r:%d f:%d %p %p-%p %p %O-%O",
                          in->buf->temporary,
                          in->buf->recycled,
                          in->buf->in_file,
                          in->buf->start,
                          in->buf->pos,
                          in->buf->last,
                          in->buf->file,
                          in->buf->file_pos,
                          in->buf->file_last);

            ngx_debug_point();

            continue;
        }

        if (ngx_buf_size(in->buf) < 0) {

            ngx_log_error(NGX_LOG_ALERT, ctx->pool->log, 0,
                          "negative size buf in chain writer "
                          "t:%d r:%d f:%d %p %p-%p %p %O-%O",
                          in->buf->temporary,
                          in->buf->recycled,
                          in->buf->in_file,
                          in->buf->start,
                          in->buf->pos,
                          in->buf->last,
                          in->buf->file,
                          in->buf->file_pos,
                          in->buf->file_last);

            ngx_debug_point();

            return NGX_ERROR;
        }

        size += ngx_buf_size(in->buf);

        ngx_log_debug2(NGX_LOG_DEBUG_CORE, c->log, 0,
                       "chain writer buf fl:%d s:%uO",
                       in->buf->flush, ngx_buf_size(in->buf));

        cl = ngx_alloc_chain_link(ctx->pool);
        if (cl == NULL) {
            return NGX_ERROR;
        }

        cl->buf = in->buf;
        cl->next = NULL;
        *ctx->last = cl;
        ctx->last = &cl->next;
    }

    ngx_log_debug1(NGX_LOG_DEBUG_CORE, c->log, 0,
                   "chain writer in: %p", ctx->out);

    for (cl = ctx->out; cl; cl = cl->next) {

        if (ngx_buf_size(cl->buf) == 0 && !ngx_buf_special(cl->buf)) {

            ngx_log_error(NGX_LOG_ALERT, ctx->pool->log, 0,
                          "zero size buf in chain writer "
                          "t:%d r:%d f:%d %p %p-%p %p %O-%O",
                          cl->buf->temporary,
                          cl->buf->recycled,
                          cl->buf->in_file,
                          cl->buf->start,
                          cl->buf->pos,
                          cl->buf->last,
                          cl->buf->file,
                          cl->buf->file_pos,
                          cl->buf->file_last);

            ngx_debug_point();

            continue;
        }

        if (ngx_buf_size(cl->buf) < 0) {

            ngx_log_error(NGX_LOG_ALERT, ctx->pool->log, 0,
                          "negative size buf in chain writer "
                          "t:%d r:%d f:%d %p %p-%p %p %O-%O",
                          cl->buf->temporary,
                          cl->buf->recycled,
                          cl->buf->in_file,
                          cl->buf->start,
                          cl->buf->pos,
                          cl->buf->last,
                          cl->buf->file,
                          cl->buf->file_pos,
                          cl->buf->file_last);

            ngx_debug_point();

            return NGX_ERROR;
        }

        size += ngx_buf_size(cl->buf);
    }

    if (size == 0 && !c->buffered) {
        return NGX_OK;
    }

    chain = c->send_chain(c, ctx->out, ctx->limit);

    ngx_log_debug1(NGX_LOG_DEBUG_CORE, c->log, 0,
                   "chain writer out: %p", chain);

    if (chain == NGX_CHAIN_ERROR) {
        return NGX_ERROR;
    }

    if (chain && c->write->ready) {
        ngx_post_event(c->write, &ngx_posted_next_events);
    }

    for (cl = ctx->out; cl && cl != chain; /* void */) {
        ln = cl;
        cl = cl->next;
        ngx_free_chain(ctx->pool, ln);
    }

    ctx->out = chain;

    if (ctx->out == NULL) {
        ctx->last = &ctx->out;

        if (!c->buffered) {
            return NGX_OK;
        }
    }

    return NGX_AGAIN;
}
"""

# code_lines = clean_up_snippet(code)
# new_func_lines = clean_up_snippet(new_func)
# diff = create_patch("func_b", code_lines, new_func_lines, "example.c")
# print("\n".join(diff))

# ast = parse_snippet(code, "test.c")

# after_nodes = search_ast_for_node_types(ast, TYPES, 'test.c')
# after_function_lines = get_full_function_snippets(code_lines, after_nodes[DeclType.FUNCTION_TYPE][VarSourceType.FILE_LOCAL])
# get_functions_external_variables_decl(after_nodes[DeclType.FUNCTION_TYPE][VarSourceType.FILE_LOCAL], after_nodes, after_function_lines[FILE_CODE])

# test = FileDiff(name='test.c', before_ast=ast, change_type=0, before_commit=None, after_commit=None, after_ast=None, diff_functions=[], og_diff="")

# print(test.ast_string(ast))

# print("\n".join(code_lines))
# print()
# print("\n".join(abstract_code(code_lines, ast, 'test.c')))

# pattern_test = r'\b"?/sys/block/%s/device/unload_heads"?\b'
# test_string = '"/sys/block/%s/device/unload_heads", device+5);'
# print(re.search(pattern_test, test_string))
# test = re.sub(pattern_test, "TEST", test_string)
# print(test)

# # types = {VAR_TYPE: clang.cindex.CursorKind.VAR_DECL, FUNCTION_TYPE: clang.cindex.CursorKind.FUNCTION_DECL}

# # after_nodes = search_ast_for_node_types(after_file_ast, TYPES, filename)
# # after_function_lines = get_full_function_snippets(after_file_lines, after_nodes[FUNCTION_TYPE][FILE_LOCAL])


# nodes = search_ast_for_node_types(ast, TYPES, "test.c")

# code_lines = clean_up_snippet(code)

# functions = get_full_function_snippets(code_lines, nodes[FUNCTION_TYPE][FILE_LOCAL])

# # print_ast(nodes[FUNCTION_TYPE][FILE_LOCAL]['protect'])
# print(functions['protect'])
