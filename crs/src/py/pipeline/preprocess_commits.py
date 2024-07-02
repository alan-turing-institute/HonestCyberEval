import re
import copy
import clang.cindex

# Set the path to the libclang shared library
clang.cindex.Config.set_library_file('/usr/lib/x86_64-linux-gnu/libclang-14.so')

# constants used throughout this
FILE_CODE = "file_code"
FUNCTIONAL_CHANGE = 0
FILE_REMOVED = 1
FILE_ADDED = 2

FUNCTION_LOCAL = "function_local"
OTHER = "other"
FILE_LOCAL = "file local"
IMPORTED = "imported"
FUNCTION_TYPE = "function"
VAR_TYPE = "variables"
TYPES = {VAR_TYPE: getattr(clang.cindex.CursorKind, 'VAR_DECL', None), FUNCTION_TYPE: getattr(clang.cindex.CursorKind, 'FUNCTION_DECL', None)}

class FunctionDiffs:
    def __init__(self, before_lines=None, after_lines=None, diff_lines=None):
        self.before_lines = before_lines
        self.after_lines = after_lines
        self.diff_lines = diff_lines

    def print(self):
        print(f"\t\tbefore: {self.before_lines}")
        print(f"\t\tafter: {self.after_lines}")
        print(f"\t\tdiff: {self.diff_lines}")

class FileDiff:
    def __init__(self, change_type, before_commit, after_commit, filename, before_ast, after_ast, diff_functions):
        self.change_type = change_type
        self.before_commit = before_commit
        self.after_commit = after_commit
        self.filename = filename
        self.before_ast = before_ast
        self.after_ast = after_ast
        self.diff_functions = diff_functions

    def print(self):
        print(f"\tchange type: {self.change_type}")
        print(f"\tfilename: {self.filename}")
        print(f"\tfunction diffs:")
        for function_diff in self.diff_functions:
            self.diff_functions[function_diff].print()

# TODO: set up the cleaned commits as a class so that it can have the C/Java swap stuff more easily maybe?
# TODO: set up a refactoring check using the asts maybe? if code is 'x = a + b; y = x + z;' -> 'y = a + b + z;' kind of check?
# TODO: set up using Java

def is_node_local(cursor, filename):
    # check if the node passed in is defined in this file or elsewhere
    return cursor.location.file and cursor.location.file.name == filename

def parse_snippet(snippet, filepath):

    filename = filepath.split("/")[-1] # only take filename bit of the filepath

    # set up unsaved files so can use string of the c code with the libclang parser
    unsaved_files = [(filename, snippet)]

    # Create an index
    index = clang.cindex.Index.create()

    # Parse the code from the string
    translation_unit = index.parse(
        path=filename,
        unsaved_files=unsaved_files,
        options=clang.cindex.TranslationUnit.PARSE_NONE
    )

    return translation_unit.cursor

def search_ast_for_node_types(node, types, filename):
    # types is dictionary of string type and then the CursorKind
    # returns a dict with the type as the key and a nested dict containing the separated local and imported sets of the relevant nodes
    nodes = {}

    # initialise the empty sets
    for node_type in types:
        nodes[node_type] = {FILE_LOCAL: {}, IMPORTED: {}}

    # recursively search AST (might need to change this to for loop though as python isn't that good with high recursion depths?)
    nodes = _search_ast_for_node_type(node, types, nodes, filename)

    return nodes

def _search_ast_for_node_type(node, types, nodes, filename):

    for node_type in types:
        if node.kind == types[node_type]:
            if is_node_local(node, filename):
                nodes[node_type][FILE_LOCAL][node.spelling] = node
            else:
                nodes[node_type][IMPORTED][node.spelling] = node
    for child in node.get_children():
        nodes = _search_ast_for_node_type(child, types, nodes, filename)

    return nodes

def clean_up_snippet(snippet):

    function_def_pattern = r'\)\s*{'
    new_function_def = "){"
    whitespace_pattern = r'\s+'
    # unnecessary_space_pattern_1 = r'(\W)\s+(\w)'
    # unnecessary_space_pattern_2 = r'(\w)\s+(\W)'

    comment_pattern = r'^\s*(\/\*|\*|\/\/)'
    comment_in_code_line_pattern = r'(\/\*.*\*\/|\\\\.*)'

    snippet = re.sub(function_def_pattern, new_function_def, snippet)

    stripped_lines = []

    for line in snippet.splitlines():
        # remove empty lines and also strip leading and trailing white space from each line
        if re.search(comment_pattern, line):
            # ignore comments
            continue
        if line.strip() != "":
            # reduce any occurences of multiple whitespaces to just one
            line = re.sub(whitespace_pattern, ' ', line)
            line = re.sub(comment_in_code_line_pattern, '', line) # remove comments

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

def find_diff_between_commits(before_commit, after_commit):

    # find the diffs:
    diffs = before_commit.diff(after_commit)
    filename_diffs = {}

    files_checked = []

    for diff in diffs:
        # print(f"\nDiff for file: {diff.b_path}")

        filename = diff.b_path

        if filename is not None:
            files_checked.append(filename)
            if not (".c" in filename or ".h" in filename):
                continue
        else:
            # print(f"diff b_path is none: {diff}")
            continue

        change_type = FUNCTIONAL_CHANGE

        before_file = None
        after_file = None

        try:
            before_file = (before_commit.tree/filename).data_stream.read().decode('utf-8')

        except KeyError:
            change_type = FILE_ADDED

        try:
            after_file = (after_commit.tree/filename).data_stream.read().decode('utf-8')

        except KeyError:
            change_type = FILE_REMOVED

        before_function_lines = None
        after_function_lines = None
        before_file_ast = None
        after_file_ast = None
        before_nodes = None
        after_nodes = None

        if change_type in {FUNCTIONAL_CHANGE, FILE_REMOVED} and before_file is not None:
            before_file_lines = clean_up_snippet(before_file)
            before_file_ast = parse_snippet(before_file, filename)
            before_nodes = search_ast_for_node_types(before_file_ast, TYPES, filename)
            before_function_lines = get_full_function_snippets(before_file_lines, before_nodes[FUNCTION_TYPE][FILE_LOCAL])

        if change_type in {FUNCTIONAL_CHANGE, FILE_ADDED} and after_file is not None:
            after_file_lines = clean_up_snippet(after_file)
            after_file_ast = parse_snippet(after_file, filename)
            after_nodes = search_ast_for_node_types(after_file_ast, TYPES, filename)
            after_function_lines = get_full_function_snippets(after_file_lines, after_nodes[FUNCTION_TYPE][FILE_LOCAL])

        diff_functions = get_function_diffs(before_function_lines, after_function_lines)

        if change_type == FUNCTIONAL_CHANGE:
            before_variables = None if before_nodes is None else before_nodes[VAR_TYPE]
            after_variables = None if after_nodes is None else after_nodes[VAR_TYPE]

            new_diff_functions = {}
            for function_name in diff_functions:
                function_before = diff_functions[function_name].before_lines
                function_after = diff_functions[function_name].after_lines

                is_functional = is_diff_functional(function_before, function_after, before_variables, after_variables)

                if is_functional:
                    new_diff_functions[function_name] = copy.deepcopy(diff_functions[function_name])

            diff_functions = new_diff_functions

        if diff_functions:
            filename_diffs[filename] = FileDiff(change_type, before_commit, after_commit, filename, before_file_ast, after_file_ast, diff_functions)

    # TODO: check if I even need this bit? Was to catch file added things but think they might be caught already?
    # diffs = after_commit.diff(before_commit)

    # for diff in diffs:
    #     if diff.b_path is not None and diff.b_path not in files_checked:
    #         print(diff.b_path)

    return filename_diffs

def get_function_diffs(before, after):

    diff_functions = {}

    after_functions = None
    if after is not None:
        after_functions = list(after.keys())

    if before is not None:
        for function_name in before:

            if after_functions is not None and function_name in after:
                # function exists in both files

                after_functions.remove(function_name)

                # check if functions are same:
                functions_same = before[function_name] == after[function_name]

                if not functions_same:
                    # diff in these functions so make the diff
                    diff = []
                    for line in before[function_name]:
                        if line not in after[function_name]:
                            diff.append(f"-{line}")

                    for line in after[function_name]:
                        if line not in before[function_name]:
                            diff.append(f"+{line}")

                    diff_functions[function_name] = FunctionDiffs(before_lines=before[function_name], after_lines=after[function_name], diff_lines=diff)
            else:
                diff = [f"-{line}" for line in before[function_name]]
                diff_functions[function_name] = FunctionDiffs(before_lines=before[function_name], diff_lines=diff)

    if after_functions is not None:
        for function_name in after_functions:
            diff = [f"+{line}" for line in after[function_name]]
            diff_functions[function_name] = FunctionDiffs(after_lines=after[function_name], diff_lines=diff)

    return diff_functions

def get_full_function_snippets(full_file, functions):

    open_code_block_pattern = r'{'
    close_code_block_pattern = r'}'
    lines = full_file#.splitlines()

    functions_code = {}
    file_code = []

    while lines:

        function_name_mentioned = None
        for function_name in functions:
            if function_name in lines[0]:
                function_name_mentioned = function_name
                break

        if function_name_mentioned is not None and function_name_mentioned not in functions_code:
            # assuming that the first instance of a file local function name appearing will be in the function definition
            # so if it hasn't been added to the keys yet then it should be the first declaration?
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
            
            lines = lines[len(function_lines):]
        
            functions_code[function_name_mentioned] = function_lines
        else:
            file_code.append(lines[0])
            lines.pop(0)

    functions_code[FILE_CODE] = file_code

    return functions_code

def get_variable_snippets(full_snippet, variable_name):

    variable_refs = []

    for line in full_snippet:
        if variable_name in line:
            variable_refs.append(line)

    return variable_refs

def get_function_variables(code_lines, variables):

    local_variables = []
    other_variables = []

    for line in code_lines:
        for variable in variables[FILE_LOCAL]:
            if variable in line:
                if variable not in local_variables:
                    local_variables.append(variable)
        
        for variable in variables[IMPORTED]:
            if variable in line:
                if variable not in other_variables:
                    other_variables.append(variable)

    return {FUNCTION_LOCAL: local_variables, OTHER: other_variables}

def check_functional_diff_in_variable_lines_order(before_code, after_code, variable_names):
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

    return False # I think?

def is_diff_functional(function_before_code, function_after_code, before_variables, after_variables):#function_before_ast, function_after_ast):

    # are they exactly the same? - essentially is it just whitespace or other formatting that's been changed?
    if function_before_code == function_after_code: # could also probs check the asts here instead??
        return False # no functional change made

    variable_names_before = get_function_variables(function_before_code, before_variables)
    variable_names_after = get_function_variables(function_after_code, after_variables)

    local_variables_same = variable_names_before[FUNCTION_LOCAL] == variable_names_after[FUNCTION_LOCAL]
    other_variables_same = variable_names_before[OTHER] == variable_names_after[OTHER]

    if not other_variables_same:
        # potential difference as these are defined outside the function?
        other_variables_before = set(variable_names_before[OTHER])
        other_variables_after = set(variable_names_after[OTHER])
        if other_variables_before != other_variables_after:
            return True
    
        # check for other variable reordering
        if check_functional_diff_in_variable_lines_order(function_before_code, function_after_code, variable_names_before[OTHER]):
            return True
        # else -> the other variables are the same (or at least not a functional diff?) so check the local ones now?

    if local_variables_same:
        # check for non-functional reordering
        return check_functional_diff_in_variable_lines_order(function_before_code, function_after_code, variable_names_before[FUNCTION_LOCAL])
    else:
        # check if a variable has been renamed (also checks for non-functional reordering of the code here too)
        # check list size of variables is the same as otherwise might not be renaming
        if len(variable_names_before[FUNCTION_LOCAL]) != len(variable_names_after[FUNCTION_LOCAL]):
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
                for line in variable_after_lines:
                    line = re.sub(after_variable, before_variable, line)

                if not variable_before_lines == variable_after_lines:
                    return True
                # if compare_lists_exact(variable_before_lines, variable_after_lines):
                #     print(f"variable {before_variable} renamed to {after_variable} with no functional difference?")
                # else:
                #     return True

    return False # any functional diff should have been returned by this point I think?

# test code below -> leaving for now so that I can use again when setting up the Java stuff
# C code string
# code = '''
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
# '''

# ast = parse_snippet(code, "test.c")

# types = {VAR_TYPE: clang.cindex.CursorKind.VAR_DECL, FUNCTION_TYPE: clang.cindex.CursorKind.FUNCTION_DECL}

# nodes = search_ast_for_node_types(ast.cursor, types, "test.c")

# functions = get_full_function_snippets(code.splitlines(), nodes[FUNCTION_TYPE][FILE_LOCAL])

# variables = get_function_variables(functions["func_a"], nodes[VAR_TYPE])

# print(functions["func_a"])
# print(variables)

# print(functions["main"])
# print(functions["func_b"])
