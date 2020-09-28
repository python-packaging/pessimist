import volatile
import unittest
import attr

@attr.s
class Foo:
    tmp = attr.ib(factory=list)


class Test(unittest.TestCase):
    def test_main(self):
        with volatile.dir():
            f = Foo()

