# Custom option and option-parser classes with emphasis on
# natural, easy-to-use syntax for option declaration and parsing.
#
# Copyright (C) 2009-2014 Collin J. Sutton.  All rights reserved.
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details. 
#
# The GNU General Public License version 2 may be found at
# <http://www.gnu.org/licenses/gpl-2.0.html>.

# This file is ported from Ruby, so please excuse the YARDoc comments.

import sys

# Option-data storage/representation.  Used to declare/define a single program
# option.
class Option:
    LINE_WRAP_COLUMN=96
    short_name = None
    long_name = None
    description = None
    argument_description = None
    argument_optional = None
    callback = None
    
    # Initialize a new Option instance.
    #
    # @param [String] short_name Single-character value to identify the option's
    #     short form (single-dash prefix).
    #
    # @param [String] long_name Long-form (double-dash style) name for the option.
    #
    # @param [String] description Description of what the option does.
    #
    # @param [String,nil] argument_description If non-`nil`, a single-word
    #     (upper-case preferred) that suggests the kind of argument the option
    #     takes.
    #
    # @param [Boolean] argument_optional Whether the option's argument is optional;
    #     only meaningful if an argument description was given.
    #
    # @param [Array<String>,nil] argumentCandidates An array of accepted values
    #     for the argument, or `nil`.
    #
    # @param [String,nil] defaultArgument Default value for the argument; only
    #     meaningful if an argument description was given and the argument was
    #     specified as optional.
    #
    # @param [block] handlerProc Option handler.  If the option takes an argument,
    #     it will be passed to the block.
    def __init__(self, short_name, long_name, description,
                 argument_description = None, argument_optional = False):
        if short_name == None and long_name == None:
            raise ArgumentError.new('Short name and long name cannot both be `nil\'!')
        self.short_name = short_name
        self.long_name = long_name
        self.description = description
        self.argument_description = argument_description
        self.argument_optional = argument_optional
        self.callback = None

    # Specify a callable object to invoke when the option is recieved.  This
    # method is unique to Python, because it lacks the elegance afforded by
    # Ruby's "block" arguments.  (Oh P.S. Python is so very Special and can't
    # make assignments in lambda functions.  What a pity.)
    def handle(self, callback):
        self.callback = callback
        return self

    # Another uniquely-Pythonic method.  This one lets you specify something to
    # store the option's argument in.  With no `ref` argument, the value will
    # be stored in the dict returned by `OptionParser.parse`.
    def store(self, ref=None, multiple=False):
        self.callback = ref
        self.multiple_allowed = multiple
        return self


    def received(self, arg, _store_in=None):
        """Called when the option is received.

        '''arg''' is the argument's value, or `True` if no argument was given.
        '''_store_in''' (optional) is the dict in which to store `arg`.

        """

        if isinstance(self.callback, str):
            lcls = globals()
            lcls[self.callback] = arg
        elif callable(self.callback):
            self.callback(arg)
        elif isinstance(self.callback, dict):
            self.store_in(self.callback, arg)
        elif isinstance(_store_in, dict):
            self.store_in(_store_in, arg)

    # Helper for `received` that takes care of storing the value in dicts and
    # multiple values etc.
    def store_in(self, where, arg):
        preferred_key = self.get_preferred_key()
        if preferred_key in where and self.multiple_allowed:
            if not isinstance(where[preferred_key], list):
                where[preferred_key] = [where[preferred_key]]
            where[preferred_key].append(arg)
        else:
            if self.multiple_allowed:
                where[preferred_key] = [arg]
            else:
                where[preferred_key] = arg


    @property
    def takes_argument(self):
        return self.argument_description != None


    def to_string(self, wrap_start_col):
        out = '  '
        
        if self.short_name != None:
            out += '-' + self.short_name 
        if self.short_name != None and self.long_name != None:
            out += ', '
        if self.long_name != None:
            out += '--' + self.long_name


        if self.argument_description != None:
            if not self.argument_optional:
                out += ' ' 
                out += self.argument_description
            else:
                out += '[='
                out += self.argument_description
                out += ']'

        return ('%%-%ds%%s' % wrap_start_col) % (out,
                                                 self.wrap_text(self.description, wrap_start_col,
                                                                Option.LINE_WRAP_COLUMN))


    @classmethod
    def wrap_text(self, s, start_col=0, max_col=75):
        width = max_col - start_col

        if len(s) <= width:
            return s
        else:
            out = ''
            while len(s) > width:
                front = s[0:width]
                parts = front.rpartition(' ')
                s = parts[2].strip() + s[width:]
                out += "%s\n%s" % (parts[0], ' ' * start_col)
            out += s.strip()
            return out


    def get_preferred_key(self):
        if self.long_name != None:
            return self.long_name
        else:
            return self.short_name

class OptionParser:
    """Stateless option-parser functions."""

    @classmethod
    def handle_options(self, option_list, arguments = sys.argv[1:], stop_args=[]):
        """Handle script arguments according to the given options array."""
        out = {}

        short_option_map = { }
        long_option_map = { }
        for o in option_list:
            short_option_map[o.short_name] = o
            long_option_map[o.long_name] = o
        i = 0
        while ( i < len(arguments) ):
            next_arg = None
            if i + 1 < len(arguments):
                next_arg = arguments[i+1]
            n = OptionParser.check_option(short_option_map, long_option_map, arguments[i], next_arg,
                                          stop_args, out)
            if type(n) == bool and n == False:
                break
            elif n == 0:
                i += 1
            else:
                j = i
                while j < i + n:
                    del arguments[i]
                    j += 1
        return out

    @classmethod
    def show_usage(self, usage, io = sys.stdout):
        """
        Print a usage string, with alignment adjustments for multi-usage programs, to an
        arbitrary stream.

        """
        io.write(self.format_usage(usage))
        
    @classmethod
    def format_usage(self, usage):

        # Fix alignment for multi-line usage strings.
        if usage.find("\n") >= 0:
            usage = "\n       ".join(usage.split("\n"))
        return "Usage: %s\n" % usage


    @classmethod
    def show_help(self, option_list, usage, description, io=sys.stdout):
        """
        Print a formatted help message (as is often triggered via a program's `--help`
        command-line option) to an arbitrary stream.

        """
        io.write("%s\n" % self.format_help(option_list, usage, description))

    @classmethod
    def format_help(self, option_list, usage, description):
        out = ''

        max_len = 0
        for o in option_list:
            optarg_length = 0

            if o.short_name != None or o.long_name != None:
                # Well, that should always be true anyway.
                # This is for the two-space left margin.
                optarg_length += 2
            if o.long_name != None:
                optarg_length += len(o.long_name) + 2
            if o.short_name != None:
                optarg_length += len(o.short_name) + 1
            if o.short_name != None and o.long_name != None:
                optarg_length += 2
                
            if not o.argument_description == None:
                optarg_length += 1 + len(o.argument_description)
                if o.argument_optional:
                    optarg_length += 3

            if optarg_length > max_len:
                max_len = optarg_length

        desc_start_col = (max_len + 2)

        out += OptionParser.format_usage(usage)
        if description != None:
            out += "\n%s\n" % description

        if isinstance(option_list, list) and len(option_list) > 0:
            out += "\nOptions:\n"
            for o in option_list:
                out += "%s\n" % o.to_string(desc_start_col)

        return out

    @classmethod
    def handle_long_option(self, long_option_map, arg, next_arg, out):
        equals_index = arg.find('=')

        option_name = None
        if equals_index == -1:
            option_name = arg[2:]
        else:
            option_name = arg[2:equals_index]

        if option_name in long_option_map:
            option = long_option_map[option_name];
            if option.takes_argument:
                if option.argument_optional:
                    if equals_index == -1:
                        if not next_arg == None:
                            sys.stderr.write('Warning: Please use `--long-option=value\' syntax for optional arguments.'+"\n")
                        option.received(True, out)
                        return 1
                    else:
                        option.received(arg[(equals_index + 1):], out)
                        return 1
                else:
                    if equals_index == -1:
                        if next_arg == None:
                            raise ValueError('Missing required argument to `--' + option_name + '\'!')
                        option.received(next_arg, out)
                        return 2
                    else:
                        option.received(arg[(equals_index + 1):], out)
                        return 1

            else:
                option.received(True, out)
                return 1
        else:
            raise ValueError('No such option, `--' + option_name + '\'!')

    @classmethod
    def handle_short_options(self, short_option_map, arg, next_arg, out):
        consumed = 0
        i = 1
        while ( i < len(arg) ):
            if arg[i] in short_option_map:
                option = short_option_map[arg[i]]
                n = None
                if option.takes_argument:
                    if option.argument_optional:
                        if next_arg != None:
                            sys.stderr.write('Warning: Please use `--long-option=VALUE\' syntax when specifying optional arguments.'+"\n")
                        option.received(True, out)
                        n = 1
                    else:
                        if i < len(arg) - 1:
                            option.received(arg[(i+1):], out)
                            i = len(arg)
                            n = 1
                        else:
                            if next_arg == None:
                                raise ValueError('Missing required argument to `-' + arg[i] + '\'!')
                            option.received(next_arg, out)
                            n = 2
                else:
                    option.received(True, out)
                    n = 1
            else:
                raise RuntimeError('No such option, `-' + arg[i] + '\'!')

            if n > consumed:
                consumed = n
            i += 1
        return consumed


    @classmethod
    def check_option(self, short_option_map, long_option_map, arg, next_arg,
                     stop_args, out):
        if arg in stop_args:
            return False

        if arg != None and len(arg) > 0 and arg[0] == '-':
            if len(arg) > 1:
                if arg[1] == '-':
                    if len(arg) == 2:
                        # This case handles the special argument '--', which by convention means
                        # "don't parse anything after this as an option". 
                        return False
                    else:
                        return OptionParser.handle_long_option(long_option_map, arg, next_arg, out)
                else:
                    return OptionParser.handle_short_options(short_option_map, arg, next_arg, out)
            else:
                return 0
        else:
            return 0
