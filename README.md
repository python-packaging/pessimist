# pessimist

The name "optimist" was already taken?

Given your listed requirements, and how to run your tests, tries various
versions to ensure the minimums are accurate.


## Usage

```
python -m pessimist [-c 'make test'] [--fast] [--extend=name[,name...]] [--requirements=requirements*.txt] /path/to/repo
```

* `-c` -- command to run.  If you're using a src/ layout you can use `cd src;
  python -m unittest` or so.
* `--fast` -- only verify min and max versions
* `--extend` -- ignore specifiers entirely for the listed canonical names;
  intended to let you go back past `==` and may be improved to do something more
  like that in the future.  Also allows `*` as a name to mean all names that are
  "variable"
* `--requirements` -- comma-separated globs which represented "fixed"
  requirements.
* `--verbose` -- show logs as it's working


## Fixed and variable

* Fixed requirements are from `requirements*.txt`.  If these match more than one
  version, only the newest is kept.
* Variable requirements are from your setup.py/setup.cfg/etc that make it into
  the metadata.  These are the ones we're interested in trying.
* If a name is in both sets, the variable logic is followed.


## Strategy

1. Try newest versions of everything. Bail if this fails to pass.
2. For each dep independently, try progressively older versions.
3. Try oldest versions of all.  Bail if this fails to pass.

I subscribe to the "requirements.txt should be concrete versions you want to
use in CI" school of thought; the constraints in setup.py/setup.cfg/pyproject.toml
should be `>=` the minimum version that works, and `<` the next major version
("compatible", in poetry terms).

My goal in creating this is to have an automated check that we haven't broken
compatibility with an older version unintentionally.  You could have a simpler
version of this that does `sed -e 's/>=/==/` on your requirements files, but if
that fails, finding the new minimum is still a research projct that's automated
by this one.


# License

pessimist is copyright [Tim Hatch](https://timhatch.com/), and licensed under
the MIT license.  I am providing code in this repository to you under an open
source license.  This is my personal repository; the license you receive to
my code is from me and not from my employer. See the `LICENSE` file for details.
