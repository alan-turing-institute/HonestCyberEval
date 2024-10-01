import copy
import difflib
import os
import re
import tempfile
from dataclasses import KW_ONLY, dataclass, field
from enum import IntEnum, auto
from typing import Optional, TypeAlias, Union

import clang.cindex
import javalang
from clang.cindex import Cursor, CursorKind
from git import Commit
from strenum import StrEnum

from logger import logger

# constants used throughout this
FILE_CODE = "file_code"
CLANG_LIBRARY_SET = False


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


class CDeclType(StrEnum):
    FUNCTION_TYPE = auto()
    VAR_TYPE = auto()
    STRUCT_TYPE = auto()
    STRING_TYPE = auto()
    PARAM_TYPE = auto()
    ENUM_TYPE = auto()
    ENUM_CONST_TYPE = auto()
    FIELD_TYPE = auto()
    DECL_REF_TYPE = auto()


class JavaDeclType(StrEnum):
    METHOD_TYPE = auto()
    VAR_TYPE = auto()
    IMPORT_TYPE = auto()
    CLASS_TYPE = auto()
    INTERFACES_TYPE = auto()
    ENUM_TYPE = auto()
    FIELD_TYPE = auto()
    ANNOTATION_TYPE = auto()


CTypesDictType: TypeAlias = dict[CDeclType, CursorKind]
VarsDictType: TypeAlias = dict[VarSourceType, dict[str, Cursor]]
NodesDictType: TypeAlias = dict[CDeclType, VarsDictType]
FunctionDictType: TypeAlias = dict[str, list[str]]

C_TYPES: CTypesDictType = {
    CDeclType.VAR_TYPE: CursorKind.VAR_DECL,  # type: ignore
    CDeclType.PARAM_TYPE: CursorKind.PARM_DECL,  # type: ignore
    CDeclType.FUNCTION_TYPE: CursorKind.FUNCTION_DECL,  # type: ignore
    CDeclType.ENUM_CONST_TYPE: CursorKind.ENUM_CONSTANT_DECL,  # type: ignore
    CDeclType.PARAM_TYPE: CursorKind.PARM_DECL,  # type: ignore
    CDeclType.STRUCT_TYPE: CursorKind.STRUCT_DECL,  # type: ignore
    CDeclType.DECL_REF_TYPE: CursorKind.DECL_REF_EXPR,  # type: ignore
}

C_TYPES_FOR_EXTERNAL_DEFINED_VARS: CTypesDictType = {
    CDeclType.VAR_TYPE: CursorKind.VAR_DECL,  # type: ignore
    CDeclType.PARAM_TYPE: CursorKind.PARM_DECL,  # type: ignore
    CDeclType.DECL_REF_TYPE: CursorKind.DECL_REF_EXPR,  # type: ignore
}

C_TYPES_FOR_ABSTRACT: CTypesDictType = {
    CDeclType.VAR_TYPE: CursorKind.VAR_DECL,  # type: ignore
    CDeclType.FUNCTION_TYPE: CursorKind.FUNCTION_DECL,  # type: ignore
    CDeclType.STRUCT_TYPE: CursorKind.STRUCT_DECL,  # type: ignore
    CDeclType.STRING_TYPE: CursorKind.STRING_LITERAL,  # type: ignore
    CDeclType.PARAM_TYPE: CursorKind.PARM_DECL,  # type: ignore
    # CDeclType.ENUM_TYPE: CursorKind.ENUM_DECL, # type: ignore
    CDeclType.ENUM_CONST_TYPE: CursorKind.ENUM_CONSTANT_DECL,  # type: ignore
    CDeclType.FIELD_TYPE: CursorKind.FIELD_DECL,  # type: ignore
}

JavaTypesDictType: TypeAlias = dict[JavaDeclType, javalang.ast.MetaNode]  # type: ignore

JAVA_TYPES: JavaTypesDictType = {
    JavaDeclType.METHOD_TYPE: javalang.tree.MethodDeclaration,  # type: ignore
    JavaDeclType.VAR_TYPE: javalang.tree.VariableDeclarator,  # type: ignore
    JavaDeclType.IMPORT_TYPE: javalang.tree.Import,  # type: ignore
    JavaDeclType.CLASS_TYPE: javalang.tree.ClassDeclaration,  # type: ignore
    JavaDeclType.INTERFACES_TYPE: javalang.tree.InterfaceDeclaration,  # type: ignore
    JavaDeclType.ENUM_TYPE: javalang.tree.EnumDeclaration,  # type: ignore
    JavaDeclType.FIELD_TYPE: javalang.tree.FieldDeclaration,  # type: ignore
    JavaDeclType.ANNOTATION_TYPE: javalang.tree.Annotation,  # type: ignore
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
    filepath: str

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


# TODO: set up a refactoring check using the asts maybe? if code is 'x = a + b; y = x + z;' -> 'y = a + b + z;' kind of check?


def initialise_clang_cindex_library():

    global CLANG_LIBRARY_SET

    if not CLANG_LIBRARY_SET:
        # Set the path to the libclang shared library
        clang.cindex.Config.set_library_file("/usr/lib/x86_64-linux-gnu/libclang-14.so")
        CLANG_LIBRARY_SET = True


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
    nodes = search_ast_for_node_types(ast, C_TYPES_FOR_ABSTRACT, filename)

    patterns = {}
    # FIELD_DECL, ENUM_DECL, ENUM_CONSTANT_DECL
    patterns[AbstractReplacementTerms.STRING_LITERAL] = build_regex_pattern_from_list(
        (
            list(nodes[CDeclType.STRING_TYPE][VarSourceType.FILE_LOCAL].keys())
            + list(nodes[CDeclType.STRING_TYPE][VarSourceType.IMPORTED].keys())
        ),
        word_boundary=False,
    )
    patterns[AbstractReplacementTerms.LOCAL_VARIABLE] = build_regex_pattern_from_list(
        nodes[CDeclType.VAR_TYPE][VarSourceType.FILE_LOCAL]
    )
    patterns[AbstractReplacementTerms.IMPORTED_VARIABLE] = build_regex_pattern_from_list(
        nodes[CDeclType.VAR_TYPE][VarSourceType.IMPORTED]
    )
    patterns[AbstractReplacementTerms.LOCAL_FUNCTION] = build_regex_pattern_from_list(
        nodes[CDeclType.FUNCTION_TYPE][VarSourceType.FILE_LOCAL]
    )
    patterns[AbstractReplacementTerms.IMPORTED_FUNCTION] = build_regex_pattern_from_list(
        nodes[CDeclType.FUNCTION_TYPE][VarSourceType.IMPORTED]
    )
    patterns[AbstractReplacementTerms.LOCAL_STRUCT] = build_regex_pattern_from_list(
        nodes[CDeclType.STRUCT_TYPE][VarSourceType.FILE_LOCAL]
    )
    patterns[AbstractReplacementTerms.IMPORTED_STRUCT] = build_regex_pattern_from_list(
        nodes[CDeclType.STRUCT_TYPE][VarSourceType.IMPORTED]
    )
    patterns[AbstractReplacementTerms.LOCAL_STRUCT_FIELD] = build_regex_pattern_from_list(
        nodes[CDeclType.FIELD_TYPE][VarSourceType.FILE_LOCAL]
    )
    patterns[AbstractReplacementTerms.IMPORTED_STRUCT_FIELD] = build_regex_pattern_from_list(
        nodes[CDeclType.FIELD_TYPE][VarSourceType.IMPORTED]
    )
    patterns[AbstractReplacementTerms.PARAM] = build_regex_pattern_from_list((
        list(nodes[CDeclType.PARAM_TYPE][VarSourceType.FILE_LOCAL].keys())
        + list(nodes[CDeclType.PARAM_TYPE][VarSourceType.IMPORTED].keys())
    ))
    patterns[AbstractReplacementTerms.LOCAL_ENUM_CONST] = build_regex_pattern_from_list(
        nodes[CDeclType.ENUM_CONST_TYPE][VarSourceType.FILE_LOCAL]
    )
    patterns[AbstractReplacementTerms.IMPORTED_ENUM_CONST] = build_regex_pattern_from_list(
        nodes[CDeclType.ENUM_CONST_TYPE][VarSourceType.IMPORTED]
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


def get_included_files_content(tree, included_filenames, included_files, prefix="", parser_prefix=""):

    for item in tree.trees:
        path = prefix + "/" + item.name if prefix else item.name
        # logger.info(f"{item.name} is a {item.type} - {item.trees}")
        for file in item:
            if file.name in included_filenames:
                # logger.info(file.name)
                filepath = prefix + "/" + file.name
                file_snippet = (item / file.name).data_stream.read().decode("utf-8")
                # file_tupple = (f'{parser_prefix}{file.name}', file_snippet)
                file_tupple = (f"./{file.name}", file_snippet)
                included_files.append(file_tupple)
        if item.trees:
            included_files = get_included_files_content(item, included_filenames, included_files, path, parser_prefix)

    return included_files


def get_included_file_names(snippet):
    # get the include files
    include_pattern = re.compile(r'#include\s*[<"]([^>"]+)[>"]')

    # Find all matches in the C code string
    included_filenames = include_pattern.findall(snippet)

    return set(included_filenames)


def get_included_files(snippet, commit):

    # get included files from the main code:
    included_filenames = get_included_file_names(snippet)

    # get the actual file content for each of those files
    included_files = []
    included_files = get_included_files_content(commit.tree, included_filenames, included_files)

    include_files_to_search = copy.deepcopy(included_filenames)

    files_to_search = True if len(include_files_to_search) != 0 else False

    parser_prefix = ""

    while files_to_search:

        parser_prefix = "./"
        files_to_search = False
        next_files_to_search = set()

        # now for each include file included, find the include files it requires (if any)
        for file_name, file_string in included_files:
            if file_name in include_files_to_search:
                # if name isn't in the list anymore means it's already been searched so don't need to re-search it
                this_files_include_files = get_included_file_names(file_string)

                # find the include files we haven't looked at yet
                different_include_files = this_files_include_files - included_filenames

                if len(different_include_files) != 0:
                    files_to_search = True

                next_files_to_search = next_files_to_search.union(different_include_files)
                # included_files_to_search =

                # remove this file from the search list:
                # include_files_to_search.remove(file_name)

        # then get the include file snippets
        included_files = get_included_files_content(commit.tree, include_files_to_search, included_files)

        include_files_to_search = next_files_to_search

    return included_files


def make_fake_header(full_filename):
    # ifndef _NGX_CONFIG_H_INCLUDED_
    # define _NGX_CONFIG_H_INCLUDED_

    # endif

    # file name will be of form: name.h

    # get name out:
    filename_match = re.search(r"\w+\.", full_filename)
    filename = ""
    if filename_match is not None:
        filename = filename_match.group(0)
    filename = filename[:-1]
    filename = filename.upper()

    # make fake contents
    contents = f"#ifndef _{filename}_H_INCLUDED_\n#define _{filename}_H_INCLUDED_\n#endif"

    return contents


def _parse_c_files(unsaved_files, filename, options):
    index = clang.cindex.Index.create()
    # Parse the code from the string
    translation_unit = index.parse(path=filename, unsaved_files=unsaved_files, options=options)

    for diagnostic in translation_unit.diagnostics:
        logger.debug(f"Parsing Diagnostics: {diagnostic}")
        if "fatal error" in str(diagnostic):

            if re.search(r"'.+'", str(diagnostic)):
                failed_header_match = re.search(r"'.+'", str(diagnostic))
                failed_header_name = ""

                if failed_header_match is not None:
                    failed_header_name = failed_header_match.group(0)

                logger.debug(f"Parsing failed due to not finding this header file: {failed_header_name}")

                fake_file_content = make_fake_header(failed_header_name)

                failed_header_path = "./" + failed_header_name[1:-1]  # remove the quotes
                unsaved_files.append((failed_header_path, fake_file_content))
                return _parse_c_files(unsaved_files, filename, options)
            else:
                logger.debug(f"Parsing failed.")

    return translation_unit


def parse_c_snippet(snippet: str, filepath: str, commit) -> Cursor:

    filename = filepath.split("/")[-1]  # only take filename bit of the filepath

    logger.debug(f"Parsing {filename}")

    # set up unsaved files so can use string of the c code with the libclang parser
    unsaved_files = [(filename, snippet)]

    included_files = get_included_files(snippet, commit)

    not_header_file = True
    options = clang.cindex.TranslationUnit.PARSE_NONE

    if re.search(r"\.h$", filename):
        not_header_file = False
        # need to make a fake c file so it can parse
        fake_c_file = """
                        #include "{filename}"
                        """
        fake_c_file += """
                        int main() {
                            return 0;
                        }
                        """

        unsaved_files = [("fake_c_file.c", fake_c_file), (f"./{filename}", snippet)]
        unsaved_files.append(("fake_c_file.c", fake_c_file))

        options = clang.cindex.TranslationUnit.PARSE_INCOMPLETE

    unsaved_files = unsaved_files + included_files

    filename_for_parsing = filename if not_header_file else "fake_c_file.c"

    translation_unit = _parse_c_files(unsaved_files, filename_for_parsing, options)

    return translation_unit.cursor


def search_ast_for_node_types(node: Cursor, types: CTypesDictType, filename: str) -> NodesDictType:
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


def _search_ast_for_node_type(
    node: Cursor, types: CTypesDictType, nodes: NodesDictType, filename: str
) -> NodesDictType:
    for node_type in types:
        if node.kind == types[node_type]:
            if is_node_local(node, filename):
                nodes[node_type][VarSourceType.FILE_LOCAL][node.spelling] = node
            else:
                nodes[node_type][VarSourceType.IMPORTED][node.spelling] = node
    for child in node.get_children():
        nodes = _search_ast_for_node_type(child, types, nodes, filename)

    return nodes


def parse_java_snippet(java_snippet):

    try:
        tree: javalang.tree.CompilationUnit = javalang.parse.parse(java_snippet)  # type: ignore
    except javalang.parser.JavaSyntaxError as e:  # type: ignore
        error_location = e.at
        logger.debug(f"JavaSyntaxError: {e.description} at {error_location}")
        return None, {}

    declarations = {
        JavaDeclType.METHOD_TYPE: set(),
        JavaDeclType.CLASS_TYPE: set(),
        JavaDeclType.FIELD_TYPE: set(),
        JavaDeclType.INTERFACES_TYPE: set(),
        JavaDeclType.ENUM_TYPE: set(),
        JavaDeclType.ANNOTATION_TYPE: set(),
        JavaDeclType.VAR_TYPE: set(),
        JavaDeclType.IMPORT_TYPE: set(),
    }

    for path, node in tree:
        for node_type in JAVA_TYPES:
            if isinstance(node, JAVA_TYPES[node_type]):
                if node_type == JavaDeclType.FIELD_TYPE:
                    for declarator in node.declarators:
                        declarations[node_type].add(declarator.name)
                elif node_type == JavaDeclType.IMPORT_TYPE:
                    declarations[node_type].add(node.path)
                else:
                    declarations[node_type].add(node.name)

    return tree, declarations


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
    initialise_clang_cindex_library()

    # find the diffs:
    diffs = before_commit.diff(after_commit, create_patch=True)
    filename_diffs: dict[str, FileDiff] = {}

    files_checked: list[str] = []

    for diff in diffs:
        logger.debug(f"\nDiff for file: {diff.b_path}")

        filepath = diff.b_path

        if filepath is not None:
            files_checked.append(filepath)
            file_extensions = [".c", ".h", ".java", ".in"]

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

        filename = (filepath.split("/"))[-1]

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

        before_file_lines = []
        after_file_lines = []
        before_file_ast: Optional[Cursor] = None
        after_file_ast: Optional[Cursor] = None
        diff_functions = {}

        if change_type in {ChangeType.FUNCTIONAL_CHANGE, ChangeType.FILE_REMOVED} and before_file is not None:
            before_file_lines = clean_up_snippet(before_file)

        if change_type in {ChangeType.FUNCTIONAL_CHANGE, ChangeType.FILE_ADDED} and after_file is not None:
            after_file_lines = clean_up_snippet(after_file)

        # basic check for whitespace changes only:
        if before_file_lines and after_file_lines:
            if before_file_lines == after_file_lines:
                logger.debug(f"Nonfunctional change only in {filename} from {after_commit.hexsha}.")
                continue  # as only whitespace/comment changes have occurred

        make_file_diff = (
            True  # using this for now as parsing is causing more issues with this not finding header files stuff
        )

        # make_file_diff = False
        # c_file_pattern = re.escape(".c") + "$"
        # java_file_pattern = re.escape(".java") + "$"
        # if re.search(c_file_pattern, filename):
        #     # c file
        #     diff_found, diff_functions = c_file_check(
        #         filename, before_commit, after_commit, before_file_lines, after_file_lines, change_type
        #     )

        #     if diff_found or diff_functions:
        #         make_file_diff = True
        # if re.search(java_file_pattern, filename):
        #     # c file
        #     diff_found, diff_functions = java_file_check(
        #         filename, before_commit, after_commit, before_file_lines, after_file_lines, change_type
        #     )

        #     if diff_found or diff_functions:
        #         make_file_diff = True
        # else:
        #     # essentially if header file or java so only the whitespace check is used for filtering in those cases atm
        #     make_file_diff = True

        if make_file_diff:
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
                filepath=filepath,
            )

            logger.debug(f"FileDiff created for {filename}.")

    logger.debug(
        f"{len(filename_diffs)} out of {len(diffs)} files have potentially functional differences in commit {after_commit.hexsha}."
    )

    return filename_diffs


def c_file_check(
    filename,
    before_commit,
    after_commit,
    before_file_lines,
    after_file_lines,
    change_type,
):

    before_function_lines: FunctionDictType = {}
    after_function_lines: FunctionDictType = {}
    before_file_ast: Optional[Cursor] = None
    after_file_ast: Optional[Cursor] = None
    before_nodes: NodesDictType = {}
    after_nodes: NodesDictType = {}

    if change_type in {ChangeType.FUNCTIONAL_CHANGE, ChangeType.FILE_REMOVED} and before_file_lines:
        before_file_ast = parse_c_snippet("\n".join(before_file_lines), filename, before_commit)
        before_nodes = search_ast_for_node_types(before_file_ast, C_TYPES, filename)
        before_function_lines = get_full_function_snippets(
            before_file_lines,
            set(before_nodes[CDeclType.FUNCTION_TYPE][VarSourceType.FILE_LOCAL].keys()),
        )
        logger.info(set(before_nodes[CDeclType.FUNCTION_TYPE][VarSourceType.FILE_LOCAL].keys()))
        for key in before_function_lines:
            logger.info(key)
            logger.info("\n".join(before_function_lines[key]))

    if change_type in {ChangeType.FUNCTIONAL_CHANGE, ChangeType.FILE_ADDED} and after_file_lines:
        after_file_ast = parse_c_snippet("\n".join(after_file_lines), filename, after_commit)
        after_nodes = search_ast_for_node_types(after_file_ast, C_TYPES, filename)
        after_function_lines = get_full_function_snippets(
            after_file_lines,
            set(after_nodes[CDeclType.FUNCTION_TYPE][VarSourceType.FILE_LOCAL].keys()),
        )

    diff_functions = get_function_diffs(before_function_lines, after_function_lines)

    if change_type == ChangeType.FUNCTIONAL_CHANGE:

        before_refs = set()
        if before_nodes:
            for type_key in before_nodes:
                before_refs = before_refs.union(set(before_nodes[type_key][VarSourceType.FILE_LOCAL].keys()))
                before_refs = before_refs.union(set(before_nodes[type_key][VarSourceType.IMPORTED].keys()))

        after_refs = set()
        if after_nodes:
            for type_key in after_nodes:
                after_refs = after_refs.union(set(after_nodes[type_key][VarSourceType.FILE_LOCAL].keys()))
                after_refs = after_refs.union(set(after_nodes[type_key][VarSourceType.IMPORTED].keys()))

        if len(before_refs) == 0 or len(after_refs) == 0:
            return True, {}

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
                        get_c_function_external_variables_decl(
                            function_name, after_nodes, after_function_lines[FILE_CODE]
                        )
                    )

                if FILE_CODE in before_function_lines:
                    new_diff_functions[function_name].before_external_variable_decls = (
                        get_c_function_external_variables_decl(
                            function_name,
                            before_nodes,
                            before_function_lines[FILE_CODE],
                        )
                    )

                new_diff_functions[function_name].append_external_variable_decls_to_code_lines()

        diff_functions = new_diff_functions

    diff_found = True if diff_functions else False

    return diff_found, diff_functions


def java_file_check(
    filename,
    before_commit,
    after_commit,
    before_file_lines,
    after_file_lines,
    change_type,
):

    before_function_lines: FunctionDictType = {}
    after_function_lines: FunctionDictType = {}
    before_file_ast: Optional[javalang.tree.CompilationUnit] = None  # type: ignore
    after_file_ast: Optional[javalang.tree.CompilationUnit] = None  # type: ignore
    before_nodes = {}
    after_nodes = {}

    if change_type in {ChangeType.FUNCTIONAL_CHANGE, ChangeType.FILE_REMOVED} and before_file_lines:
        before_file_ast, before_nodes = parse_java_snippet("\n".join(before_file_lines))
        before_function_lines = get_full_function_snippets(
            before_file_lines, set(before_nodes[JavaDeclType.METHOD_TYPE])
        )

    if change_type in {ChangeType.FUNCTIONAL_CHANGE, ChangeType.FILE_ADDED} and after_file_lines:
        after_file_ast, after_nodes = parse_java_snippet("\n".join(after_file_lines))
        after_function_lines = get_full_function_snippets(after_file_lines, set(after_nodes[JavaDeclType.METHOD_TYPE]))

    diff_functions = get_function_diffs(before_function_lines, after_function_lines)

    if change_type == ChangeType.FUNCTIONAL_CHANGE:

        before_refs = set()

        if before_nodes:
            for type_key in before_nodes:
                before_refs = before_refs.union(before_nodes[type_key])

        after_refs = set()
        if after_nodes:
            for type_key in after_nodes:
                after_refs = after_refs.union(after_nodes[type_key])

        if len(before_refs) == 0 or len(after_refs) == 0:
            return True, {}

        new_diff_functions = {}
        for function_name in diff_functions:
            function_before = diff_functions[function_name].before_lines
            function_after = diff_functions[function_name].after_lines

            is_functional = is_diff_functional(function_before, function_after, before_refs, after_refs, filename)

            logger.debug(f"Is {function_name} diff functional? {is_functional}")

            if is_functional:
                new_diff_functions[function_name] = copy.deepcopy(diff_functions[function_name])

                # if FILE_CODE in after_function_lines:
                #     new_diff_functions[function_name].after_external_variable_decls = (
                #         get_function_external_variables_decl(
                #             function_name, after_nodes, after_function_lines[FILE_CODE]
                #         )
                #     )

                # if FILE_CODE in before_function_lines:
                #     new_diff_functions[function_name].before_external_variable_decls = (
                #         get_function_external_variables_decl(
                #             function_name, before_nodes, before_function_lines[FILE_CODE]
                #         )
                #     )

                # new_diff_functions[function_name].append_external_variable_decls_to_code_lines()

        diff_functions = new_diff_functions

    diff_found = True if diff_functions else False

    return diff_found, diff_functions


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


def get_full_function_snippets(full_file: list[str], functions: set[str]) -> FunctionDictType:
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


def get_c_function_external_variables_decl(function_name, full_file_nodes, non_function_code_snippets):
    if FILE_CODE == function_name:
        return {}

    function_ast = full_file_nodes[CDeclType.FUNCTION_TYPE][VarSourceType.FILE_LOCAL][function_name]

    all_function_names = list(full_file_nodes[CDeclType.FUNCTION_TYPE][VarSourceType.FILE_LOCAL].keys()) + list(
        full_file_nodes[CDeclType.FUNCTION_TYPE][VarSourceType.IMPORTED].keys()
    )

    imported_to_file_vars = list(full_file_nodes[CDeclType.VAR_TYPE][VarSourceType.IMPORTED].keys())

    # get the nodes for the variables declared and the variables/functions referenced
    nodes = search_ast_for_node_types(function_ast, C_TYPES_FOR_EXTERNAL_DEFINED_VARS, function_ast.location.file.name)

    vars_declared = nodes[CDeclType.VAR_TYPE][VarSourceType.FILE_LOCAL]  # should only be local to the function

    if CDeclType.PARAM_TYPE in nodes:
        # include function parameters
        vars_declared = vars_declared | nodes[CDeclType.PARAM_TYPE][VarSourceType.FILE_LOCAL]

    undeclared_vars = []

    for decl_ref in nodes[CDeclType.DECL_REF_TYPE][VarSourceType.FILE_LOCAL]:
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

    before_refs = get_function_refs(function_before_code, all_refs_before)
    after_refs = get_function_refs(function_after_code, all_refs_after)

    if len(function_before_code) != len(function_after_code):
        # as white space is removed, if the length is different can likely assume a more functional change has occurred?
        return True

    variables_same = before_refs == after_refs

    # logger.info(f'variables are the same? {variables_same}')
    if variables_same:
        # check for non-functional reordering

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


def create_file_patch(file_lines, new_lines, filename=""):

    generic_function_name_pattern = r"\b\w+\(.*\)\s*{?$"
    close_code_block_pattern = r"}"

    start_of_functions_index = -1
    end_of_functions_index = -1

    for i, line in enumerate(file_lines):
        if re.search(generic_function_name_pattern, line):
            start_of_functions_index = i

    for i, line in enumerate(file_lines[::-1]):
        if re.search(close_code_block_pattern, line):
            end_of_functions_index = len(file_lines) - i

    old_trailing_lines = file_lines[end_of_functions_index:]

    new_file = new_lines[: -len(old_trailing_lines)]
    new_file += file_lines[start_of_functions_index:end_of_functions_index]
    new_file += new_lines[-len(old_trailing_lines) :]

    diff = make_diff(file_lines, new_file, filename)

    return diff


def create_patch(function_name, file_lines, new_function_lines, filename=""):

    if not isinstance(file_lines, list):
        file_lines = clean_up_snippet(file_lines)

    open_code_block_pattern = r"{"
    close_code_block_pattern = r"}"
    lines = copy.deepcopy(file_lines)

    if function_name == FILE_CODE:
        return create_file_patch(file_lines, new_function_lines, filename=filename)

    function_name_pattern = r"\b" + function_name + r"\(.*\)\s*{?$"

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


MAX_LINES_FOR_SPLIT = 450


def split_file_for_patching(file_lines):
    if not isinstance(file_lines, list):
        file_lines = clean_up_snippet(file_lines)

    open_code_block_pattern = r"{"
    close_code_block_pattern = r"}"

    file_length = len(file_lines)
    split_files_length = 0

    split_files = []
    potential_cut_off = MAX_LINES_FOR_SPLIT - 100

    if len(file_lines) <= MAX_LINES_FOR_SPLIT:
        return ["\n".join(file_lines)]

    while True:
        num_split_lines = 0
        new_split_lines = []

        open_brackets = 0
        last_convenient_cut_off = -1

        for i, line in enumerate(file_lines):
            new_split_lines.append(line)

            if len(new_split_lines) >= MAX_LINES_FOR_SPLIT:
                if last_convenient_cut_off > 0:
                    new_split_lines = new_split_lines[:last_convenient_cut_off]
                    break

            if re.search(open_code_block_pattern, line):
                open_brackets += len(re.findall(open_code_block_pattern, line))

            if re.search(close_code_block_pattern, line):
                open_brackets -= len(re.findall(close_code_block_pattern, line))
                if open_brackets == 0:
                    last_convenient_cut_off = i + 1

            # if len(new_split_lines) > potential_cut_off and len(new_split_lines) < MAX_LINES_FOR_SPLIT:
            #     # cut off reached:
            #     if last_convenient_cut_off > 0:
            #         new_split_lines = new_split_lines[:last_convenient_cut_off]
            #         break

        split_files_length += len(new_split_lines)

        split_files.append("\n".join(new_split_lines))

        if last_convenient_cut_off > 0:
            file_lines = file_lines[last_convenient_cut_off:]
        elif len(file_lines) < MAX_LINES_FOR_SPLIT:
            break

        if not file_lines:
            break

    # logger.info(f"new total length: {split_files_length}, old length {file_length}")
    # assert split_files_length == file_length

    return split_files
