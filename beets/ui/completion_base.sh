# This file is part of beets.
# Copyright (c) 2014, Thomas Scholtes.
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.



# Completion for the `beet` command
# =================================
#
# Load this script to complete beets subcommands, options, and
# queries.
#
# If a beets command is found on the command line it completes filenames and
# the subcommand's options. Otherwise it will complete global options and
# subcommands. If the previous option on the command line expects an argument,
# it also completes filenames or directories.  Options are only
# completed if '-' has already been typed on the command line.
#
# Note that completion of plugin commands only works for those plugins
# that were enabled when running `beet completion`. It does not check
# plugins dynamically
#
# Currently, only Bash 3.2 and newer is supported and the
# `bash-completion` package (v2.8 or newer) is required.
#
# TODO
# ----
#
# * There are some issues with arguments that are quoted on the command line.
#
# * Complete arguments for the `--format` option by expanding field variables.
#
#     beet ls -f "$tit[TAB]
#     beet ls -f "$title
#
# * Support long options with `=`, e.g. `--config=file`. Debian's bash
#   completion package can handle this.
#
# Note that 'bash-completion' v2.8 is a part of Debian 10, which is part of
# LTS until 2024-06-30.  After this date, the minimum version requirement can
# be changed, and newer features can be used unconditionally.  See PR#5301.
#

if [[ ${BASH_COMPLETION_VERSINFO[0]} -ne 2 \
   || ${BASH_COMPLETION_VERSINFO[1]} -lt 8 ]]; then
  echo "Incompatible version of 'bash-completion'!"
  return 1
fi

# The later code relies on 'bash-completion' version 2.12, but older versions
# are still supported.  Here, we provide implementations of the newer functions
# in terms of older ones, if 'bash-completion' is too old to have them.

if [[ ${BASH_COMPLETION_VERSINFO[1]} -lt 12 ]]; then
  _comp_get_words() {
    _get_comp_words_by_ref "$@"
  }

  _comp_compgen_filedir() {
    _filedir "$@"
  }
fi

# Determines the beets subcommand and dispatches the completion
# accordingly.
_beet_dispatch() {
  local cur prev cmd=

  COMPREPLY=()
  _comp_get_words -n : cur prev

  # Look for the beets subcommand
  local arg
  for (( i=1; i < COMP_CWORD; i++ )); do
      arg="${COMP_WORDS[i]}"
      if _list_include_item "${opts___global}" $arg; then
        ((i++))
      elif [[ "$arg" != -* ]]; then
        cmd="$arg"
        break
      fi
  done

  # Replace command shortcuts
  if [[ -n $cmd ]] && _list_include_item "$aliases" "$cmd"; then
    eval "cmd=\$alias__${cmd//-/_}"
  fi

  case $cmd in
    help)
      COMPREPLY+=( $(compgen -W "$commands" -- $cur) )
      ;;
    list|remove|move|update|write|stats)
      _beet_complete_query
      ;;
    "")
      _beet_complete_global
      ;;
    *)
      _beet_complete
      ;;
  esac
}


# Adds option and file completion to COMPREPLY for the subcommand $cmd
_beet_complete() {
  if [[ $cur == -* ]]; then
    local opts flags completions
    eval "opts=\$opts__${cmd//-/_}"
    eval "flags=\$flags__${cmd//-/_}"
    completions="${flags___common} ${opts} ${flags}"
    COMPREPLY+=( $(compgen -W "$completions"  -- $cur) )
  else
    _comp_compgen_filedir
  fi
}


# Add global options and subcommands to the completion
_beet_complete_global() {
  case $prev in
    -h|--help)
      # Complete commands
      COMPREPLY+=( $(compgen -W "$commands" -- $cur) )
      return
      ;;
    -l|--library|-c|--config)
      # Filename completion
      _comp_compgen_filedir
      return
      ;;
    -d|--directory)
      # Directory completion
      _comp_compgen_filedir -d
      return
      ;;
  esac

  if [[ $cur == -* ]]; then
    local completions="$opts___global $flags___global"
    COMPREPLY+=( $(compgen -W "$completions" -- $cur) )
  elif [[ -n $cur ]] && _list_include_item "$aliases" "$cur"; then
    local cmd
    eval "cmd=\$alias__${cur//-/_}"
    COMPREPLY+=( "$cmd" )
  else
    COMPREPLY+=( $(compgen -W "$commands" -- $cur) )
  fi
}

_beet_complete_query() {
  local opts
  eval "opts=\$opts__${cmd//-/_}"

  if [[ $cur == -* ]] || _list_include_item "$opts" "$prev"; then
    _beet_complete
  elif [[ $cur != \'* && $cur != \"* &&
          $cur != *:* ]]; then
    # Do not complete quoted queries or those who already have a field
    # set.
    compopt -o nospace
    COMPREPLY+=( $(compgen -S : -W "$fields" -- $cur) )
    return 0
  fi
}

# Returns true if the space separated list $1 includes $2
_list_include_item() {
  [[ " $1 " == *[[:space:]]$2[[:space:]]* ]]
}

# This is where beets dynamically adds the _beet function. This
# function sets the variables $flags, $opts, $commands, and $aliases.
complete -o filenames -F _beet beet
