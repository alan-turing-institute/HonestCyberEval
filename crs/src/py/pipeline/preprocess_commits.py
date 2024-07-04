import re
import copy
import clang.cindex
import difflib

from logger import logger

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

class BaseDiff:
    def print(self, info, lines):
        print(f'Function {self.name} {info}:')
        print('\n'.join(lines))

    def print_before(self):
        self.print('Before', self.before_lines)
        return

    def print_after(self):
        self.print('After', self.after_lines)
        return

    def print_diff(self):
        self.print('Diff', self.diff_lines)
        return
    
    def join_lines(self, lines, indent=''):
        return ("\n" + indent).join(lines)


class FunctionDiff(BaseDiff):
    def __init__(self, function_name, before_lines=None, after_lines=None, diff_lines=None):
        self.name = function_name
        self.before_lines = before_lines
        self.after_lines = after_lines
        self.diff_lines = diff_lines

    def __str__(self):
        return self.build_full_string(indent='')
    
    def build_full_string(self, indent):
        string_to_print = f'{indent}Function {self.name}:\n'
        indent += '\t'
        string_to_print += f'{indent}Diff:\n'
        string_to_print += f'{indent}{self.join_lines(self.diff_lines, indent)}\n\n'
        string_to_print += f'{indent}Before this commit:\n'
        string_to_print += f'{indent}{self.join_lines(self.before_lines, indent)}\n\n'
        string_to_print += f'{indent}After this commit:\n'
        string_to_print += f'{indent}{self.join_lines(self.after_lines, indent)}\n\n'

        return string_to_print


class FileDiff(BaseDiff):
    def __init__(self, change_type, before_commit, after_commit, filename, before_ast, after_ast, diff_functions, before_lines, after_lines, diff_lines):
        self.change_type = change_type
        self.before_commit = before_commit
        self.after_commit = after_commit
        self.filename = filename
        self.before_ast = before_ast
        self.after_ast = after_ast
        self.diff_functions = diff_functions
        self.before_lines = before_lines
        self.after_lines = after_lines
        self.diff_lines = diff_lines

    def print_full(self, indent='\t'):
        string_to_print = f"{indent}Change type: {self.change_type}"
        string_to_print += f"{indent}Filename: {self.filename}"
        string_to_print += f"{indent}Function Diffs:"
        for function_diff in self.diff_functions:
            string_to_print += str(self.diff_functions[function_diff])

        return string_to_print

    def __str__(self):
        string_to_print = self.build_full_string('')

        for function_diff in self.diff_functions:
            string_to_print += self.diff_functions[function_diff].build_full_string('\t\t')

        return string_to_print

    def build_full_string(self, indent):
        string_to_print = f'{indent}File {self.filename}:\n'
        indent += '\t'
        string_to_print += f'{indent}Change Type: {self.change_type}\n'
        string_to_print += f'{indent}Diff:\n'
        string_to_print += f'{indent}{self.join_lines(self.diff_lines, indent)}\n\n'
        string_to_print += f'{indent}Before this commit:\n'
        string_to_print += f'{indent}\tCode:\n'
        indent_plus = indent + "\t"
        string_to_print += f'{indent}\t{self.join_lines(self.before_lines, indent_plus)}\n\n'
        # string_to_print += f'{indent}\AST:\n'
        # string_to_print += f'{indent}\t{self.ast_string(self.before_ast)}\n\n'        
        string_to_print += f'{indent}After this commit:\n'
        string_to_print += f'{indent}\tCode:\n'
        string_to_print += f'{indent}\t{self.join_lines(self.after_lines, indent_plus)}\n\n'
        # string_to_print += f'{indent}\AST:\n'
        # string_to_print += f'{indent}\t{self.ast_string(self.after_ast)}\n\n'     

        return string_to_print

    # def find_diff(self):




# TODO: set up the cleaned commits as a class so that it can have the C/Java swap stuff more easily maybe?
# TODO: set up a refactoring check using the asts maybe? if code is 'x = a + b; y = x + z;' -> 'y = a + b + z;' kind of check?
# TODO: set up using Java

def build_regex_pattern_from_list(pattern_list):
    regex_pattern = r'('

    for i, pattern_item in enumerate(pattern_list):
        regex_pattern += pattern_item
        if i < (len(pattern_list) - 1):
            regex_pattern += r'|'
        else:
            regex_pattern += r')'
        
    return regex_pattern

def print_ast(cursor, depth=0):
    indent = '  ' * depth
    print(f'{indent}Kind: {cursor.kind}, Spelling: {cursor.spelling}, Location: {cursor.location}')
    if 'printf' in cursor.spelling:
        info = {'Location': cursor.location,
            'Extent Start': cursor.extent.start,
            'Extent End': cursor.extent.end,
            'semantic_parent': cursor.semantic_parent,
            'Linkage': cursor.linkage,
            'Storage Class': cursor.storage_class,
            'Access Specifier': cursor.access_specifier,
            'USR': cursor.get_usr(),
            'Mangling': cursor.mangled_name}
        print(info)
    for child in cursor.get_children():
        print_ast(child, depth + 1)

# def abstract_code(code_snippet, ast, filename):
#     types = {VAR_TYPE: getattr(clang.cindex.CursorKind, 'VAR_DECL', None), 
#              FUNCTION_TYPE: getattr(clang.cindex.CursorKind, 'FUNCTION_DECL', None),
#              'CUSTOM_TYPES': getattr(clang.cindex.CursorKind, '')}
# STRING_LITERAL, INTEGER_LITERAL
#     nodes = search_ast_for_node_types(ast, TYPES, filename)
#     custom_variables_pattern = build_regex_pattern_from_list(nodes[VAR_TYPE][FILE_LOCAL])
#     imported_variables_pattern = build_regex_pattern_from_list(nodes[VAR_TYPE][IMPORTED])
#     custom_functions_pattern = build_regex_pattern_from_list(nodes[FUNCTION_TYPE][FILE_LOCAL])
#     imported_functions_pattern = build_regex_pattern_from_list(nodes[FUNCTION_TYPE][IMPORTED])
#     custom_type_pattern = build_regex_pattern_from_list(nodes[FUNCTION_TYPE][IMPORTED])
#     numbers_pattern = r'\b[0-9]\b'

#     for i, line in enumerate(code_snippet):

#         # replace custom variables
#         code_snippet[i] = re.sub(custom_variables_pattern, 'LOCAL_VARIABLE', line)
#         # replace imported variables
#         code_snippet[i] = re.sub(imported_variables_pattern, 'IMPORTED_VARIABLE', line)
#         # replace custom functions
#         code_snippet[i] = re.sub(custom_functions_pattern, 'CUS_FUNC', line)
#         # replace imported functions
#         code_snippet[i] = re.sub(imported_functions_pattern, 'IMPORTED_FUNC', line)
#         # replace numbers??
#         code_snippet[i] = re.sub(numbers_pattern, 'NUM', line)

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

    if isinstance(snippet, list):
        # should be just a string to begin with in here, but can make it into a single string?
        snippet = "\n".join(snippet)

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
        logger.debug(f"\nDiff for file: {diff.b_path}")

        filename = diff.b_path

        if filename is not None:
            files_checked.append(filename)
            if not (".c" in filename or ".h" in filename):
                continue
        else:
            if diff.a_path is None:
                continue
            else:
                filename = diff.a_path
                logger.debug(f"diff b_path is none, diff a_path is: {filename}, file deleted.")
        
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
            full_file_diff_lines = make_diff(before_file_lines, after_file_lines)
            filename_diffs[filename] = FileDiff(change_type, before_commit, after_commit, filename, before_file_ast, after_file_ast, diff_functions, before_file_lines, after_file_lines, full_file_diff_lines)

            logger.debug(f'FileDiffs print for {filename}:')
            logger.debug(str(filename_diffs[filename]))

    return filename_diffs

def make_diff(before, after):
    return list(difflib.unified_diff(before, after, lineterm=''))

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
                    diff = make_diff(before[function_name], after[function_name])

                    # for line in before[function_name]:
                    #     if line not in after[function_name]:
                    #         diff.append(f"-{line}")

                    # for line in after[function_name]:
                    #     if line not in before[function_name]:
                    #         diff.append(f"+{line}")

                    diff_functions[function_name] = FunctionDiff(function_name, before_lines=before[function_name], after_lines=after[function_name], diff_lines=diff)
            else:
                diff = difflib.unified_diff(before[function_name], after[function_name], lineterm='') #[f"-{line}" for line in before[function_name]]
                diff_functions[function_name] = FunctionDiff(function_name, before_lines=before[function_name], diff_lines=diff)

    if after_functions is not None:
        for function_name in after_functions:
            diff = difflib.unified_diff(before[function_name], after[function_name], lineterm='') #[f"+{line}" for line in after[function_name]]
            diff_functions[function_name] = FunctionDiff(function_name, after_lines=after[function_name], diff_lines=diff)

    return diff_functions

def get_full_function_snippets(full_file, functions):

    open_code_block_pattern = r'{'
    close_code_block_pattern = r'}'
    lines = full_file

    if len(lines) == 0:
        # should already be split into lines by the time it gets here?
        lines = clean_up_snippet(lines)

    functions_code = {}
    file_code = []

    while lines:

        function_name_mentioned = None
        for function_name in functions:
            function_name_pattern = r'\b' + function_name + '\\b'
            if re.search(function_name_pattern, lines[0]):
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
code = '''
// SPDX-License-Identifier: GPL-2.0-only
/* Disk protection for HP/DELL machines.
 *
 * Copyright 2008 Eric Piel
 * Copyright 2009 Pavel Machek <pavel@ucw.cz>
 * Copyright 2012 Sonal Santan
 * Copyright 2014 Pali Rohár <pali@kernel.org>
 */

#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <string.h>
#include <stdint.h>
#include <errno.h>
#include <signal.h>
#include <sys/mman.h>
#include <sched.h>
#include <syslog.h>

static int noled;
static char unload_heads_path[64];
static char device_path[32];
static const char app_name[] = "FREE FALL";

static int set_unload_heads_path(char *device)
{
	if (strlen(device) <= 5 || strncmp(device, "/dev/", 5) != 0)
		return -EINVAL;
	strncpy(device_path, device, sizeof(device_path) - 1);

	snprintf(unload_heads_path, sizeof(unload_heads_path) - 1,
				"/sys/block/%s/device/unload_heads", device+5);
	return 0;
}

static int valid_disk(void)
{
	int fd = open(unload_heads_path, O_RDONLY);

	if (fd < 0) {
		perror(unload_heads_path);
		return 0;
	}

	close(fd);
	return 1;
}

static void write_int(char *path, int i)
{
	char buf[1024];
	int fd = open(path, O_RDWR);

	if (fd < 0) {
		perror("open");
		exit(1);
	}

	sprintf(buf, "%d", i);

	if (write(fd, buf, strlen(buf)) != strlen(buf)) {
		perror("write");
		exit(1);
	}

	close(fd);
}

static void set_led(int on)
{
	if (noled)
		return;
	write_int("/sys/class/leds/hp::hddprotect/brightness", on);
}

static void protect(int seconds)
{
	const char *str = (seconds == 0) ? "Unparked" : "Parked";

	write_int(unload_heads_path, seconds*1000);
	syslog(LOG_INFO, "%s %s disk head\n", str, device_path);
}

static int on_ac(void)
{
	/* /sys/class/power_supply/AC0/online */
	return 1;
}

static int lid_open(void)
{
	/* /proc/acpi/button/lid/LID/state */
	return 1;
}

static void ignore_me(int signum)
{
	protect(0);
	set_led(0);
}

int main(int argc, char **argv)
{
	int fd, ret;
	struct stat st;
	struct sched_param param;

	if (argc == 1)
		ret = set_unload_heads_path("/dev/sda");
	else if (argc == 2)
		ret = set_unload_heads_path(argv[1]);
	else
		ret = -EINVAL;

	if (ret || !valid_disk()) {
		fprintf(stderr, "usage: %s <device> (default: /dev/sda)\n",
				argv[0]);
		exit(1);
	}

	fd = open("/dev/freefall", O_RDONLY);
	if (fd < 0) {
		perror("/dev/freefall");
		return EXIT_FAILURE;
	}

	if (stat("/sys/class/leds/hp::hddprotect/brightness", &st))
		noled = 1;

	if (daemon(0, 0) != 0) {
		perror("daemon");
		return EXIT_FAILURE;
	}

	openlog(app_name, LOG_CONS | LOG_PID | LOG_NDELAY, LOG_LOCAL1);

	param.sched_priority = sched_get_priority_max(SCHED_FIFO);
	sched_setscheduler(0, SCHED_FIFO, &param);
	mlockall(MCL_CURRENT|MCL_FUTURE);

	signal(SIGALRM, ignore_me);

	for (;;) {
		unsigned char count;

		ret = read(fd, &count, sizeof(count));
		alarm(0);
		if ((ret == -1) && (errno == EINTR)) {
			/* Alarm expired, time to unpark the heads */
			continue;
		}

		if (ret != sizeof(count)) {
			perror("read");
			break;
		}

		protect(21);
		set_led(1);
		if (1 || on_ac() || lid_open())
			alarm(2);
		else
			alarm(20);
	}

	closelog();
	close(fd);
	return EXIT_SUCCESS;
}
'''

# code_lines = clean_up_snippet(code)
# ast = parse_snippet(code, "test.c")


# # types = {VAR_TYPE: clang.cindex.CursorKind.VAR_DECL, FUNCTION_TYPE: clang.cindex.CursorKind.FUNCTION_DECL}

# # after_nodes = search_ast_for_node_types(after_file_ast, TYPES, filename)
# # after_function_lines = get_full_function_snippets(after_file_lines, after_nodes[FUNCTION_TYPE][FILE_LOCAL])


# nodes = search_ast_for_node_types(ast, TYPES, "test.c")

# code_lines = clean_up_snippet(code)

# functions = get_full_function_snippets(code_lines, nodes[FUNCTION_TYPE][FILE_LOCAL])

# # print_ast(nodes[FUNCTION_TYPE][FILE_LOCAL]['protect'])
# print(functions['protect'])


# variables = get_function_variables(functions["func_a"], nodes[VAR_TYPE])