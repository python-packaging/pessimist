# pessimist

The name "optimist" was already taken?

Given a `requirements.txt` and some basic information about how to run your
tests, finds accurate minimum versions.


## Usage

```
python -m pessimist.manager [-c 'make test'] [--fast] [--extend] /path/to/repo
```

* `-c` -- command to run.  If you're using a src/ layout you can use `cd src;
  python -m unittest` or so.
* `--fast` -- only verify min and max versions
* `--extend` -- ignore specifiers entirely; intended to let you go back past
  `==` and may be improved to do something more like that in the future.
* `--verbose` -- show logs as it's working


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
