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


TypesDictType: TypeAlias = dict[DeclType, CursorKind]
VarsDictType: TypeAlias = dict[VarSourceType, dict[str, Cursor]]
NodesDictType: TypeAlias = dict[DeclType, VarsDictType]
FunctionDictType: TypeAlias = dict[str, list[str]]

TYPES: TypesDictType = {
    DeclType.VAR_TYPE: CursorKind.VAR_DECL,  # type: ignore
    DeclType.FUNCTION_TYPE: CursorKind.FUNCTION_DECL,  # type: ignore
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
        else:
            string_to_print += f"{indent}No code before this commit.\n"

        if self.after_lines:
            string_to_print += f"{indent}After this commit:\n"
            string_to_print += f"{indent}{self.join_lines(self.after_lines, indent)}\n\n"
        else:
            string_to_print += f"{indent}No code after this commit.\n"

        return string_to_print


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
            string_to_print += f"{indent_plus}AST:\n"
            string_to_print += f"{indent_plus}{self.ast_string(self.before_ast)}\n\n"
        else:
            string_to_print += f"{indent_plus}No code before this commit.\n"

        string_to_print += f"{indent}After this commit:\n"
        if self.after_lines:
            string_to_print += f"{indent_plus}Code:\n"
            string_to_print += f"{indent_plus}{self.join_lines(self.after_lines, indent_plus)}\n\n"
            string_to_print += f"{indent_plus}AST:\n"
            string_to_print += f"{indent_plus}{self.ast_string(self.after_ast)}\n\n"
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

    filename = filepath.split("/")[-1]  # only take filename bit of the filepath

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

    function_def_pattern = r"\)\s*{"
    new_function_def = "){"
    whitespace_pattern = r"\s+"
    # unnecessary_space_pattern_1 = r'(\W)\s+(\w)'
    # unnecessary_space_pattern_2 = r'(\w)\s+(\W)'

    comment_pattern = r"^\s*(\/\*|\*|\/\/)"
    comment_in_code_line_pattern = r"(\/\*.*\*\/|\\\\.*)"

    snippet = re.sub(function_def_pattern, new_function_def, snippet)

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

            stripped_lines.append(line.strip())

    return stripped_lines


def find_diff_between_commits(before_commit: Commit, after_commit: Commit) -> dict[str, FileDiff]:
    # find the diffs:
    diffs = before_commit.diff(after_commit, create_patch=True)
    filename_diffs: dict[str, FileDiff] = {}

    files_checked: list[str] = []

    for diff in diffs:
        logger.debug(f"\nDiff for file: {diff.b_path}")

        filename = diff.b_path

        if filename is not None:
            files_checked.append(filename)
            file_extensions = [".c", ".h"]

            regex_pattern = r"("
            for i, extension in enumerate(file_extensions):
                regex_pattern += re.escape(extension) + "$"
                if i < len(file_extensions) - 1:
                    regex_pattern += "|"
                else:
                    regex_pattern += ")"

            if not re.search(regex_pattern, filename):
                continue
        else:
            if diff.a_path is None:
                continue
            else:
                filename = diff.a_path
                logger.debug(f"diff b_path is none, diff a_path is: {filename}, file deleted.")

        change_type = ChangeType.FUNCTIONAL_CHANGE

        before_file: Optional[str] = None
        before_file_lines: list[str] = []
        after_file: Optional[str] = None
        after_file_lines: list[str] = []

        try:
            before_file = (before_commit.tree / filename).data_stream.read().decode("utf-8")

        except KeyError:
            change_type = ChangeType.FILE_ADDED

        try:
            after_file = (after_commit.tree / filename).data_stream.read().decode("utf-8")

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
            before_variables: VarsDictType = before_nodes[DeclType.VAR_TYPE] if before_nodes else {}
            after_variables: VarsDictType = after_nodes[DeclType.VAR_TYPE] if after_nodes else {}

            new_diff_functions = {}
            for function_name in diff_functions:
                function_before = diff_functions[function_name].before_lines
                function_after = diff_functions[function_name].after_lines

                is_functional = is_diff_functional(function_before, function_after, before_variables, after_variables)

                if is_functional:
                    new_diff_functions[function_name] = copy.deepcopy(diff_functions[function_name])

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

            logger.debug(f"FileDiffs print for {filename}:")
            logger.debug(str(filename_diffs[filename]))

            # logger.info(filename)
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

                if not functions_same:
                    # diff in these functions so make the diff
                    diff = make_diff(before[function_name], after[function_name])

                    # for line in before[function_name]:
                    #     if line not in after[function_name]:
                    #         diff.append(f"-{line}")

                    # for line in after[function_name]:
                    #     if line not in before[function_name]:
                    #         diff.append(f"+{line}")

                    diff_functions[function_name] = FunctionDiff(
                        function_name,
                        before_lines=before[function_name],
                        after_lines=after[function_name],
                        diff_lines=diff,
                    )
            else:
                diff = make_diff(
                    before[function_name], after[function_name]
                )  # [f"-{line}" for line in before[function_name]]
                diff_functions[function_name] = FunctionDiff(
                    function_name, before_lines=before[function_name], diff_lines=diff
                )

    if after_functions:
        for function_name in after_functions:
            diff = make_diff(
                before[function_name], after[function_name]
            )  # [f"+{line}" for line in after[function_name]]
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
            function_name_pattern = r"\b" + function_name + r"\b"
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


def get_variable_snippets(full_snippet: list[str], variable_name: str) -> list[str]:

    variable_refs = []
    full_snippet = copy.deepcopy(full_snippet)

    for line in full_snippet:
        if variable_name in line:
            variable_refs.append(line)

    return variable_refs


def get_function_variables(code_lines: list[str], variables: VarsDictType) -> dict[VarType, list[str]]:

    local_variables = []
    other_variables = []

    for line in code_lines:
        for variable in variables[VarSourceType.FILE_LOCAL]:
            if variable in line:
                if variable not in local_variables:
                    local_variables.append(variable)

        for variable in variables[VarSourceType.IMPORTED]:
            if variable in line:
                if variable not in other_variables:
                    other_variables.append(variable)

    return {VarType.FUNCTION_LOCAL: local_variables, VarType.OTHER: other_variables}


def check_functional_diff_in_variable_lines_order(
    before_code: list[str], after_code: list[str], variable_names: list[str]
) -> bool:

    for variable_name in variable_names:
        variable_before_lines = get_variable_snippets(before_code, variable_name)
        variable_after_lines = get_variable_snippets(after_code, variable_name)

        if not variable_before_lines == variable_after_lines:
            return True

        # if compare_lists_exact(variable_before_lines, variable_after_lines):
        #     print(f"{variable_name} lines are the same in both diffs")
        # else:
        #     print(f"some sort of potentially functional diff with {variable_name}")
        # return True

    return False  # I think?


def is_diff_functional(
    function_before_code: list[str],
    function_after_code: list[str],
    before_variables: VarsDictType,
    after_variables: VarsDictType,
) -> bool:  # function_before_ast, function_after_ast):

    # are they exactly the same? - essentially is it just whitespace or other formatting that's been changed?
    if function_before_code == function_after_code:  # could also probs check the asts here instead??
        return False  # no functional change made

    variable_names_before = get_function_variables(function_before_code, before_variables)
    variable_names_after = get_function_variables(function_after_code, after_variables)

    local_variables_same = variable_names_before[VarType.FUNCTION_LOCAL] == variable_names_after[VarType.FUNCTION_LOCAL]
    other_variables_same = variable_names_before[VarType.OTHER] == variable_names_after[VarType.OTHER]

    if not other_variables_same:
        # potential difference as these are defined outside the function?
        other_variables_before = set(variable_names_before[VarType.OTHER])
        other_variables_after = set(variable_names_after[VarType.OTHER])
        if other_variables_before != other_variables_after:
            return True

        # check for other variable reordering
        if check_functional_diff_in_variable_lines_order(
            function_before_code, function_after_code, variable_names_before[VarType.OTHER]
        ):
            return True
        # else -> the other variables are the same (or at least not a functional diff?) so check the local ones now?

    if local_variables_same:
        # check for non-functional reordering
        return check_functional_diff_in_variable_lines_order(
            function_before_code, function_after_code, variable_names_before[VarType.FUNCTION_LOCAL]
        )

    else:
        # check if a variable has been renamed (also checks for non-functional reordering of the code here too)
        # check list size of variables is the same as otherwise might not be renaming
        if len(variable_names_before[VarType.FUNCTION_LOCAL]) != len(variable_names_after[VarType.FUNCTION_LOCAL]):
            return True

        # find the different variable/s
        unique_variable_names_before = []
        unique_variable_names_after = []
        for variable_name in variable_names_before:
            if variable_name not in variable_names_after:
                unique_variable_names_before.append(variable_name)

        for variable_name in variable_names_after:
            if variable_name not in variable_names_before:
                unique_variable_names_after.append(variable_name)

        for before_variable in unique_variable_names_before:
            variable_before_lines = get_variable_snippets(function_before_code, before_variable)

            for after_variable in unique_variable_names_after:
                variable_after_lines = get_variable_snippets(function_after_code, after_variable)

                # replace new variable_name with the old one and compare code
                for i, line in enumerate(variable_after_lines):
                    variable_after_lines[i] = re.sub(after_variable, before_variable, line)

                if not variable_before_lines == variable_after_lines:
                    return True
                # if compare_lists_exact(variable_before_lines, variable_after_lines):
                #     print(f"variable {before_variable} renamed to {after_variable} with no functional difference?")
                # else:
                #     return True

    return False  # any functional diff should have been returned by this point I think?


# test code below -> leaving for now so that I can use again when setting up the Java stuff
# C code string
code = """
#include <stdio.h>
#include <string.h>
#include <unistd.h>

char items[3][10];

void func_a(){
    char* buff;
    int i = 0;
    do{
        printf("input item:");
        buff = &items[i][0];
        i++;
        fgets(buff, 40, stdin);
        buff[strcspn(buff, "\\n")] = 0;
    }while(strlen(buff)!=0);
    i--;
}

void func_b(){
    char *buff;
    printf("done adding items\\n");
    int j;
    printf("display item #:");
    scanf("%d", &j);
    buff = &items[j][0];
    printf("item %d: %s\\n", j, buff);
}

#ifndef ___TEST___
int main()
{

    func_a();

    func_b();


    return 0;
}
#endif

"""

# code_lines = clean_up_snippet(code)
# ast = parse_snippet(code, "test.c")

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


# variables = get_function_variables(functions["func_a"], nodes[VAR_TYPE])
