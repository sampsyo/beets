############
Contributing
############

.. contents::
    :depth: 3

Thank you!
==========

First off, thank you for considering contributing to beets! It’s people
like you that make beets continue to succeed.

These guidelines describe how you can help most effectively. By
following these guidelines, you can make life easier for the development
team as it indicates you respect the maintainers’ time; in return, the
maintainers will reciprocate by helping to address your issue, review
changes, and finalize pull requests.

Types of Contributions
======================

We love to get contributions from our community—you! There are many ways
to contribute, whether you’re a programmer or not.

The first thing to do, regardless of how you'd like to contribute to the
project, is to check out our :doc:`Code of Conduct <code_of_conduct>` and to
keep that in mind while interacting with other contributors and users.

Non-Programming
---------------

-  Promote beets! Help get the word out by telling your friends, writing
   a blog post, or discussing it on a forum you frequent.
-  Improve the `documentation`_. It’s
   incredibly easy to contribute here: just find a page you want to
   modify and hit the “Edit on GitHub” button in the upper-right. You
   can automatically send us a pull request for your changes.
-  GUI design. For the time being, beets is a command-line-only affair.
   But that’s mostly because we don’t have any great ideas for what a
   good GUI should look like. If you have those great ideas, please get
   in touch.
-  Benchmarks. We’d like to have a consistent way of measuring speed
   improvements in beets’ tagger and other functionality as well as a
   way of comparing beets’ performance to other tools. You can help by
   compiling a library of freely-licensed music files (preferably with
   incorrect metadata) for testing and measurement.
-  Think you have a nice config or cool use-case for beets? We’d love to
   hear about it! Submit a post to our `discussion board
   <https://github.com/beetbox/beets/discussions/categories/show-and-tell>`__
   under the “Show and Tell” category for a chance to get featured in `the
   docs <https://beets.readthedocs.io/en/stable/guides/advanced.html>`__.
-  Consider helping out fellow users by by `responding to support requests
   <https://github.com/beetbox/beets/discussions/categories/q-a>`__ .

Programming
-----------

-  As a programmer (even if you’re just a beginner!), you have a ton of
   opportunities to get your feet wet with beets.
-  For developing plugins, or hacking away at beets, there’s some good
   information in the `“For Developers” section of the
   docs <https://beets.readthedocs.io/en/stable/dev/>`__.

.. _development-tools:

Development Tools
^^^^^^^^^^^^^^^^^

In order to develop beets, you will need a few tools installed:

-  `poetry`_ for packaging, virtual environment and dependency management
-  `poethepoet`_ to run tasks, such as linting, formatting, testing

Python community recommends using `pipx`_ to install stand-alone command-line
applications such as above. `pipx`_ installs each application in an isolated
virtual environment, where its dependencies will not interfere with your system
and other CLI tools.

If you do not have `pipx`_ installed in your system, follow `pipx-installation-instructions`_ or

.. code-block:: sh

    $ python3 -m pip install --user pipx

Install `poetry`_ and `poethepoet`_ using `pipx`_::

    $ pipx install poetry poethepoet

.. _pipx: https://pipx.pypa.io/stable
.. _pipx-installation-instructions: https://pipx.pypa.io/stable/installation/

.. _getting-the-source:

Getting the Source
^^^^^^^^^^^^^^^^^^

The easiest way to get started with the latest beets source is to clone the
repository and install ``beets`` in a local virtual environment using `poetry`_.
This can be done with:

.. code-block:: bash

    $ git clone https://github.com/beetbox/beets.git
    $ cd beets
    $ poetry install

This will install ``beets`` and all development dependencies into its own
virtual environment in your ``$POETRY_CACHE_DIR``. See ``poetry install
--help`` for installation options, including installing ``extra`` dependencies
for plugins.

In order to run something within this virtual environment, start the command
with ``poetry run`` to them, for example ``poetry run pytest``.

On the other hand, it may get tedious to type ``poetry run`` before every
command. Instead, you can activate the virtual environment in your shell with::

    $ poetry shell

You should see ``(beets-py3.9)`` prefix in your shell prompt. Now you can run
commands directly, for example::

    $ (beets-py3.9) pytest

Additionally, `poethepoet`_ task runner assists us with the most common
operations. Formatting, linting, testing are defined as ``poe`` tasks in
`pyproject.toml`_. Run::

    $ poe

to see all available tasks. They can be used like this, for example

.. code-block:: sh

    $ poe lint                  # check code style
    $ poe format                # fix formatting issues
    $ poe test                  # run tests
    # ... fix failing tests
    $ poe test --lf             # re-run failing tests (note the additional pytest option)
    $ poe check-types --pretty  # check types with an extra option for mypy


Code Contribution Ideas
^^^^^^^^^^^^^^^^^^^^^^^

-  We maintain a set of `issues marked as
   “bite-sized” <https://github.com/beetbox/beets/labels/bitesize>`__.
   These are issues that would serve as a good introduction to the
   codebase. Claim one and start exploring!
-  Like testing? Our `test
   coverage <https://codecov.io/github/beetbox/beets>`__ is somewhat
   low. You can help out by finding low-coverage modules or checking out
   other `testing-related
   issues <https://github.com/beetbox/beets/labels/testing>`__.
-  There are several ways to improve the tests in general (see :ref:`testing` and some
   places to think about performance optimization (see
   `Optimization <https://github.com/beetbox/beets/wiki/Optimization>`__).
-  Not all of our code is up to our coding conventions. In particular,
   the `library API
   documentation <https://beets.readthedocs.io/en/stable/dev/library.html>`__
   are currently quite sparse. You can help by adding to the docstrings
   in the code and to the documentation pages themselves. beets follows
   `PEP-257 <https://www.python.org/dev/peps/pep-0257/>`__ for
   docstrings and in some places, we also sometimes use `ReST autodoc
   syntax for
   Sphinx <https://www.sphinx-doc.org/en/master/usage/extensions/autodoc.html>`__
   to, for example, refer to a class name.

.. _poethepoet: https://poethepoet.natn.io/index.html
.. _poetry: https://python-poetry.org/docs/

Your First Contribution
=======================

If this is your first time contributing to an open source project,
welcome! If you are confused at all about how to contribute or what to
contribute, take a look at `this great
tutorial <http://makeapullrequest.com/>`__, or stop by our
`discussion board <https://github.com/beetbox/beets/discussions/>`__
if you have any questions.

We maintain a list of issues we reserved for those new to open source
labeled `“first timers
only” <https://github.com/beetbox/beets/issues?q=is%3Aopen+is%3Aissue+label%3A%22first+timers+only%22>`__.
Since the goal of these issues is to get users comfortable with
contributing to an open source project, please do not hesitate to ask
any questions.

How to Submit Your Work
=======================

Do you have a great bug fix, new feature, or documentation expansion
you’d like to contribute? Follow these steps to create a GitHub pull
request and your code will ship in no time.

1. Fork the beets repository and clone it (see above) to create a
   workspace.
2. Install pre-commit, following the instructions `here
   <https://pre-commit.com/>`_.
3. Make your changes.
4. Add tests. If you’ve fixed a bug, write a test to ensure that you’ve
   actually fixed it. If there’s a new feature or plugin, please
   contribute tests that show that your code does what it says.
5. Add documentation. If you’ve added a new command flag, for example,
   find the appropriate page under ``docs/`` where it needs to be
   listed.
6. Add a changelog entry to ``docs/changelog.rst`` near the top of the
   document.
7. Run the tests and style checker, see :ref:`testing`.
8. Push to your fork and open a pull request! We’ll be in touch shortly.
9. If you add commits to a pull request, please add a comment or
   re-request a review after you push them since GitHub doesn’t
   automatically notify us when commits are added.

Remember, code contributions have four parts: the code, the tests, the
documentation, and the changelog entry. Thank you for contributing!

The Code
========

The documentation has a section on the
`library API <https://beets.readthedocs.io/en/stable/dev/library.html>`__
that serves as an introduction to beets’ design.

Coding Conventions
==================

General
-------
There are a few coding conventions we use in beets:

-  Whenever you access the library database, do so through the provided
   Library methods or via a Transaction object. Never call
   ``lib.conn.*`` directly. For example, do this:

   .. code-block:: python

       with g.lib.transaction() as tx:
             rows = tx.query("SELECT DISTINCT '{0}' FROM '{1}' ORDER BY '{2}'"
                             .format(field, model._table, sort_field))

   To fetch Item objects from the database, use lib.items(…) and supply
   a query as an argument. Resist the urge to write raw SQL for your
   query. If you must use lower-level queries into the database, do
   this:

   .. code-block:: python

       with lib.transaction() as tx:
           rows = tx.query("SELECT …")

   Transaction objects help control concurrent access to the database
   and assist in debugging conflicting accesses.
-  Always use the `future
   imports <http://docs.python.org/library/__future__.html>`__
   ``print_function``, ``division``, and ``absolute_import``, but *not*
   ``unicode_literals``. These help keep your code modern and will help
   in the eventual move to Python 3.
-  ``str.format()`` should be used instead of the ``%`` operator
-  Never ``print`` informational messages; use the
   `logging <http://docs.python.org/library/logging.html>`__ module
   instead. In particular, we have our own logging shim, so you’ll see
   ``from beets import logging`` in most files.

   -  The loggers use
      `str.format <http://docs.python.org/library/stdtypes.html#str.format>`__-style
      logging instead of ``%``-style, so you can type
      ``log.debug("{0}", obj)`` to do your formatting.

-  Exception handlers must use ``except A as B:`` instead of
   ``except A, B:``.

Style
-----

We use `ruff`_ to format and lint the codebase.

Run ``poe check-format`` and ``poe lint`` to check your code for style and
linting errors. Running ``poe format`` will automatically format your code
according to the specifications required by the project.

.. _ruff: https://docs.astral.sh/ruff/

Handling Paths
--------------

A great deal of convention deals with the handling of **paths**. Paths
are stored internally—in the database, for instance—as byte strings
(i.e., ``bytes`` instead of ``str`` in Python 3). This is because POSIX
operating systems’ path names are only reliably usable as byte
strings—operating systems typically recommend but do not require that
filenames use a given encoding, so violations of any reported encoding
are inevitable. On Windows, the strings are always encoded with UTF-8;
on Unix, the encoding is controlled by the filesystem. Here are some
guidelines to follow:

-  If you have a Unicode path or you’re not sure whether something is
   Unicode or not, pass it through ``bytestring_path`` function in the
   ``beets.util`` module to convert it to bytes.
-  Pass every path name through the ``syspath`` function (also in
   ``beets.util``) before sending it to any *operating system* file
   operation (``open``, for example). This is necessary to use long
   filenames (which, maddeningly, must be Unicode) on Windows. This
   allows us to consistently store bytes in the database but use the
   native encoding rule on both POSIX and Windows.
-  Similarly, the ``displayable_path`` utility function converts
   bytestring paths to a Unicode string for displaying to the user.
   Every time you want to print out a string to the terminal or log it
   with the ``logging`` module, feed it through this function.

Editor Settings
---------------

Personally, I work on beets with `vim`_. Here are
some ``.vimrc`` lines that might help with PEP 8-compliant Python
coding::

    filetype indent on
    autocmd FileType python setlocal shiftwidth=4 tabstop=4 softtabstop=4 expandtab shiftround autoindent

Consider installing `this alternative Python indentation
plugin <https://github.com/mitsuhiko/vim-python-combined>`__. I also
like `neomake <https://github.com/neomake/neomake>`__ with its flake8
checker.

.. _testing:

Testing
=======

Running the Tests
-----------------

Use ``poe`` to run tests::

    $ poe test [pytest options]

You can disable a hand-selected set of "slow" tests by setting the
environment variable ``SKIP_SLOW_TESTS``, for example::

    $ SKIP_SLOW_TESTS=1 poe test

Coverage
^^^^^^^^

The ``test`` command does not include coverage as it slows down testing. In
order to measure it, use the ``test-with-coverage`` task

    $ poe test-with-coverage [pytest options]

You are welcome to explore coverage by opening the HTML report in
``.reports/html/index.html``.

Note that for each covered line the report shows **which tests cover it**
(expand the list on the right-hand side of the affected line).

You can find project coverage status on `Codecov`_.

Red Flags
^^^^^^^^^

The `pytest-random`_ plugin makes it easy to randomize the order of
tests. ``poe test --random`` will occasionally turn up failing tests
that reveal ordering dependencies—which are bad news!

Test Dependencies
^^^^^^^^^^^^^^^^^

The tests have a few more dependencies than beets itself. (The additional
dependencies consist of testing utilities and dependencies of non-default
plugins exercised by the test suite.) The dependencies are listed under the
``tool.poetry.group.test.dependencies`` section in `pyproject.toml`_.

Writing Tests
-------------

Writing tests is done by adding or modifying files in folder `test`_.
Take a look at
`https://github.com/beetbox/beets/blob/master/test/test_template.py#L224`_
to get a basic view on how tests are written. Since we are currently migrating
the tests from `unittest`_ to `pytest`_, new tests should be written using
`pytest`_. Contributions migrating existing tests are welcome!

External API requests under test should be mocked with `requests-mock`_,
However, we still want to know whether external APIs are up and that they
return expected responses, therefore we test them weekly with our `integration
test`_ suite.

In order to add such a test, mark your test with the ``integration_test`` marker

.. code-block:: python

  @pytest.mark.integration_test
  def test_external_api_call():
      ...

This way, the test will be run only in the integration test suite.

.. _Codecov: https://codecov.io/github/beetbox/beets
.. _pytest-random: https://github.com/klrmn/pytest-random
.. _pytest: https://docs.pytest.org/en/stable/
.. _pyproject.toml: https://github.com/beetbox/beets/tree/master/pyproject.toml
.. _test: https://github.com/beetbox/beets/tree/master/test
.. _`https://github.com/beetbox/beets/blob/master/test/test_template.py#L224`: https://github.com/beetbox/beets/blob/master/test/test_template.py#L224
.. _unittest: https://docs.python.org/3/library/unittest.html
.. _integration test: https://github.com/beetbox/beets/actions?query=workflow%3A%22integration+tests%22
.. _requests-mock: https://requests-mock.readthedocs.io/en/latest/response.html
.. _documentation: https://beets.readthedocs.io/en/stable/
.. _vim: https://www.vim.org/
